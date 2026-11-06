# -*- coding: utf-8 -*-
"""
JPS Refine Studio - 非同期ジョブマネージャー (JobManager)
SPARQL全件取得、LLMバッチ推論、ルール一括適用等の長時間タスクを管理し、
Server-Sent Events (SSE) でリアルタイムに進捗をストリーミング配信します。
"""
import os
import json
import time
import uuid
import asyncio
from concurrent.futures import ThreadPoolExecutor
from typing import Dict, Any, Optional, Set, AsyncGenerator
from collections import defaultdict

from ..schemas.job import JobProgress, JobStatus
from ..config import WORKSPACES_DIR
from ..modules.logger import logger


class JobManager:
    """
    非同期ジョブ制御とSSE配信を司るマネージャー
    """
    def __init__(self):
        self._jobs: Dict[str, JobProgress] = {}
        self._active_workspace_jobs: Dict[str, str] = {}  # workspace_id -> current active job_id
        self._stop_requested: Set[str] = set()
        self._subscribers: Dict[str, Set[asyncio.Queue]] = defaultdict(set)
        self._executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="jps_worker")
        self._lock = asyncio.Lock()

    def get_job(self, job_id: str) -> Optional[JobProgress]:
        return self._jobs.get(job_id)

    def get_active_job_for_workspace(self, workspace_id: str) -> Optional[JobProgress]:
        job_id = self._active_workspace_jobs.get(workspace_id)
        if job_id:
            job = self._jobs.get(job_id)
            if job and job.status in (JobStatus.PENDING, JobStatus.RUNNING):
                return job
        return None

    def list_jobs(self, workspace_id: Optional[str] = None) -> list[JobProgress]:
        jobs = list(self._jobs.values())
        if workspace_id:
            jobs = [j for j in jobs if j.workspace_id == workspace_id]
        jobs.sort(key=lambda j: j.updated_at or "", reverse=True)
        return jobs

    def create_job(self, workspace_id: str, job_type: str, stage: str = "開始準備中", total: int = 0) -> JobProgress:
        """新規ジョブを作成して登録"""
        job_id = f"job_{job_type}_{int(time.time())}_{uuid.uuid4().hex[:6]}"
        now_str = time.strftime("%Y-%m-%d %H:%M:%S")

        job = JobProgress(
            job_id=job_id,
            workspace_id=workspace_id,
            type=job_type,
            stage=stage,
            status=JobStatus.PENDING,
            current=0,
            total=total,
            percentage=0.0,
            eta_seconds=None,
            started_at=now_str,
            updated_at=now_str
        )
        self._jobs[job_id] = job
        self._active_workspace_jobs[workspace_id] = job_id
        self._persist_job_status(job)
        return job

    def update_progress(
        self,
        job_id: str,
        current: Optional[int] = None,
        total: Optional[int] = None,
        stage: Optional[str] = None,
        status: Optional[JobStatus] = None,
        eta_seconds: Optional[int] = None,
        error_message: Optional[str] = None,
        extra_data: Optional[Dict[str, Any]] = None
    ):
        """スレッドセーフに進捗を更新し、全SSEサブスクライバーへブロードキャスト"""
        job = self._jobs.get(job_id)
        if not job:
            return

        now_str = time.strftime("%Y-%m-%d %H:%M:%S")
        if current is not None:
            job.current = current
        if total is not None:
            job.total = total
        if stage is not None:
            job.stage = stage
        if status is not None:
            job.status = status
        if eta_seconds is not None:
            job.eta_seconds = eta_seconds
        if error_message is not None:
            job.error_message = error_message
        if extra_data is not None:
            job.extra_data = extra_data

        if job.total > 0:
            job.percentage = round(min(100.0, (job.current / job.total) * 100.0), 1)

        job.updated_at = now_str
        self._persist_job_status(job)

        # SSE キューへプッシュ
        data_json = job.model_dump_json()
        for q in list(self._subscribers.get(job_id, [])):
            try:
                q.put_nowait(data_json)
            except Exception:
                pass

    def request_stop(self, job_id: str) -> bool:
        """ジョブ中断を要求"""
        job = self._jobs.get(job_id)
        if not job or job.status not in (JobStatus.PENDING, JobStatus.RUNNING):
            return False
        self._stop_requested.add(job_id)
        self.update_progress(
            job_id,
            status=JobStatus.STOPPED,
            stage="中断リクエスト受信済み",
            error_message="ユーザーにより処理が中断されました。"
        )
        logger.info(f"[JobManager] ジョブ中断リクエスト: {job_id}")
        return True

    def should_stop(self, job_id: str) -> bool:
        """ワーカー側から定期的に中断フラグをポーリング"""
        return job_id in self._stop_requested

    async def subscribe(self, job_id: str) -> AsyncGenerator[str, None]:
        """
        SSEクライアント用の非同期ジェネレータ。
        ジョブの最新状態を即時送信し、以後更新があるたびにイベントを配信。
        """
        q = asyncio.Queue()
        self._subscribers[job_id].add(q)

        try:
            # 接続直後に現在の最新状態を1回送信
            current_job = self._jobs.get(job_id)
            if current_job:
                yield f"event: progress\ndata: {current_job.model_dump_json()}\n\n"

            while True:
                # キューから進捗メッセージを待機（最大15秒でハートビート）
                try:
                    data = await asyncio.wait_for(q.get(), timeout=15.0)
                    yield f"event: progress\ndata: {data}\n\n"

                    # 終了ステータスの場合はストリームを終了
                    parsed = json.loads(data)
                    if parsed.get("status") in ("COMPLETED", "STOPPED", "FAILED"):
                        yield f"event: done\ndata: {json.dumps({'job_id': job_id, 'status': parsed.get('status')})}\n\n"
                        break
                except asyncio.TimeoutError:
                    # ハートビート送信（接続維持用）
                    yield f": heartbeat {time.time()}\n\n"
                    # ジョブがすでに終了しているか再確認
                    job = self._jobs.get(job_id)
                    if job and job.status in (JobStatus.COMPLETED, JobStatus.STOPPED, JobStatus.FAILED):
                        yield f"event: done\ndata: {job.model_dump_json()}\n\n"
                        break
        finally:
            self._subscribers[job_id].discard(q)

    def run_in_background(self, job_id: str, target_func, *args, **kwargs):
        """別スレッドで同期関数を実行し、完了・エラーを自動キャッチ"""
        def _wrapper():
            job = self._jobs.get(job_id)
            if not job:
                return
            self.update_progress(job_id, status=JobStatus.RUNNING)
            try:
                # target_func に should_stop コールバックを渡せるようにする
                res = target_func(
                    *args,
                    progress_callback=lambda cur, tot=None, stg=None, eta=None: self.update_progress(
                        job_id, current=cur, total=tot, stage=stg, eta_seconds=eta
                    ),
                    should_stop=lambda: self.should_stop(job_id),
                    **kwargs
                )
                if not self.should_stop(job_id):
                    self.update_progress(
                        job_id,
                        status=JobStatus.COMPLETED,
                        stage="完了",
                        current=job.total if job.total > 0 else job.current,
                        eta_seconds=0
                    )
            except Exception as e:
                logger.error(f"[JobManager] ジョブ実行時エラー ({job_id}): {e}", exc_info=True)
                self.update_progress(
                    job_id,
                    status=JobStatus.FAILED,
                    stage="エラー終了",
                    error_message=str(e)
                )
            finally:
                self._stop_requested.discard(job_id)

        self._executor.submit(_wrapper)

    def _persist_job_status(self, job: JobProgress):
        """ワークスペース内の fetch_job_status.json に即時永続化"""
        try:
            ws_dir = os.path.join(WORKSPACES_DIR, job.workspace_id, "data")
            os.makedirs(ws_dir, exist_ok=True)
            status_file = os.path.join(ws_dir, "fetch_job_status.json")
            status_dict = {
                "job_id": job.job_id,
                "status": job.status.value,
                "stage": job.stage,
                "total_target": job.total,
                "processed_count": job.current,
                "percentage": job.percentage,
                "eta_seconds": job.eta_seconds,
                "error_message": job.error_message,
                "started_at": job.started_at,
                "updated_at": job.updated_at,
                "type": job.type
            }
            tmp = status_file + ".tmp"
            with open(tmp, 'w', encoding='utf-8') as f:
                json.dump(status_dict, f, ensure_ascii=False, indent=2)
            os.replace(tmp, status_file)
        except Exception:
            pass


# グローバルシングルトン
job_manager = JobManager()

