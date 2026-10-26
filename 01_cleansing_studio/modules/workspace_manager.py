# -*- coding: utf-8 -*-
"""
JS-Refine Studio - ワークスペース ＆ フィルタリング経過（スナップショット）マネージャー
研究テーマ（ワークスペース）の分離、試行錯誤の経過（スナップショット）保存・復元、
および他者への引き継ぎ（ZIPパッケージのエクスポート/インポート）を統括管理します。
"""

import os
import sys
import json
import shutil
import tarfile
import zipfile
import datetime
from typing import List, Dict, Any, Optional

try:
    from .logger import logger
except (ImportError, ValueError):
    from logger import logger

try:
    import duckdb
except ImportError:
    duckdb = None


class WorkspaceManager:
    """
    研究プロジェクト（ワークスペース）とフィルタリングスナップショットの管理クラス
    """

    DEFAULT_WORKSPACE_ID = "gagaku_default"
    DEFAULT_WORKSPACE_NAME = "雅楽コレクション（デフォルト）"

    def __init__(self, project_root: Optional[str] = None):
        if project_root is None:
            # 01_cleansing_studio の親ディレクトリ
            current_dir = os.path.dirname(os.path.abspath(__file__))
            self.base_dir = os.path.abspath(os.path.join(current_dir, ".."))
            self.project_root = os.path.abspath(os.path.join(self.base_dir, ".."))
        else:
            self.project_root = os.path.abspath(project_root)
            self.base_dir = os.path.join(self.project_root, "01_cleansing_studio")

        self.data_root = os.path.join(self.project_root, "data")
        self.workspaces_root = os.path.join(self.data_root, "workspaces")
        self.default_rules_dir = os.path.join(self.base_dir, "rules")
        self.viewer_dir = os.path.join(self.project_root, "02_search_viewer")

        os.makedirs(self.workspaces_root, exist_ok=True)
        self._migrate_legacy_data_if_needed()

    def _migrate_legacy_data_if_needed(self):
        """
        既存の data/ 直下および 01_cleansing_studio/rules/ の資産を検知し、
        安全に gagaku_default ワークスペースへ移行・シンボリックリンク維持
        """
        default_ws_dir = os.path.join(self.workspaces_root, self.DEFAULT_WORKSPACE_ID)
        meta_file = os.path.join(default_ws_dir, "workspace_meta.json")

        if os.path.exists(meta_file):
            return  # 既に移行済み

        logger.info(f"[WorkspaceManager] 既存データの初期ワークスペース '{self.DEFAULT_WORKSPACE_ID}' への移行を確認中...")

        # ワークスペースディレクトリ作成
        ws_data_dir = os.path.join(default_ws_dir, "data")
        ws_rules_dir = os.path.join(default_ws_dir, "rules")
        ws_snapshots_dir = os.path.join(default_ws_dir, "snapshots")
        ws_exports_dir = os.path.join(default_ws_dir, "exports")
        os.makedirs(ws_data_dir, exist_ok=True)
        os.makedirs(ws_rules_dir, exist_ok=True)
        os.makedirs(ws_snapshots_dir, exist_ok=True)
        os.makedirs(ws_exports_dir, exist_ok=True)

        # 1. 既存ルールのコピー
        if os.path.exists(self.default_rules_dir):
            for fname in os.listdir(self.default_rules_dir):
                src = os.path.join(self.default_rules_dir, fname)
                dst = os.path.join(ws_rules_dir, fname)
                if os.path.isfile(src) and not os.path.exists(dst):
                    try:
                        shutil.copy2(src, dst)
                    except Exception as e:
                        logger.warning(f"Error copying rule file {fname}: {e}")

        # 2. 既存データファイルの移行（巨大ファイルは移動 + シンボリックリンク維持で後方互換性を確保）
        legacy_data_files = [
            "raw_metadata.jsonl",
            "metadata_store.duckdb",
            "target_uris.csv",
            "acquisition_manifest.json",
            "current_fetch_params.json",
            "fetch_job_status.json",
            "complete_audit_trail.csv",
            "prisma_flow_summary.json",
            "human_verified_cleaned.jsonl",
            "llm_judgments.jsonl",
            "type_filtered.jsonl",
            "about_filtered.jsonl",
            "ngram_filtered.jsonl",
            "target_for_llm.jsonl",
            "confirmed_ok_rules.jsonl",
            "discarded_rules.csv",
            "benchmark_sample_10k.jsonl"
        ]

        for fname in legacy_data_files:
            src = os.path.join(self.data_root, fname)
            dst = os.path.join(ws_data_dir, fname)

            if os.path.exists(src) and not os.path.islink(src):
                try:
                    # 実体をワークスペース側に移動
                    shutil.move(src, dst)
                    # 既存の絶対パス/相対パス参照を壊さないため、元位置にシンボリックリンクを作成
                    try:
                        # 相対シンボリックリンク
                        rel_target = os.path.relpath(dst, self.data_root)
                        os.symlink(rel_target, src)
                    except Exception as sym_err:
                        logger.debug(f"Symlink creation skipped or failed: {sym_err}")
                except Exception as e:
                    logger.warning(f"Error migrating {fname}: {e}")

        # 3. メタデータの生成
        now_str = datetime.datetime.now().isoformat()
        meta = {
            "id": self.DEFAULT_WORKSPACE_ID,
            "name": self.DEFAULT_WORKSPACE_NAME,
            "description": "初期構築された雅楽関連の書誌メタデータプールおよび精緻化ルール",
            "created_at": now_str,
            "updated_at": now_str
        }
        with open(meta_file, 'w', encoding='utf-8') as f:
            json.dump(meta, f, ensure_ascii=False, indent=2)

        logger.info(f"[WorkspaceManager] 初期ワークスペース '{self.DEFAULT_WORKSPACE_ID}' のセットアップが完了しました。")

    def list_workspaces(self) -> List[Dict[str, Any]]:
        """全ワークスペースの一覧を取得"""
        workspaces = []
        if not os.path.exists(self.workspaces_root):
            return workspaces

        for entry in os.listdir(self.workspaces_root):
            ws_dir = os.path.join(self.workspaces_root, entry)
            if not os.path.isdir(ws_dir):
                continue
            meta_path = os.path.join(ws_dir, "workspace_meta.json")
            if os.path.exists(meta_path):
                try:
                    with open(meta_path, 'r', encoding='utf-8') as f:
                        meta = json.load(f)
                    
                    # ディスク使用量とレコード数の概算
                    meta["disk_size_bytes"] = self._get_dir_size(ws_dir)
                    meta["has_raw_metadata"] = os.path.exists(os.path.join(ws_dir, "data", "raw_metadata.jsonl"))
                    meta["has_duckdb"] = os.path.exists(os.path.join(ws_dir, "data", "metadata_store.duckdb"))
                    
                    workspaces.append(meta)
                except Exception as e:
                    logger.warning(f"Error loading workspace meta for {entry}: {e}")
            else:
                # meta がないディレクトリ
                workspaces.append({
                    "id": entry,
                    "name": entry,
                    "description": "",
                    "created_at": "",
                    "updated_at": ""
                })

        # デフォルトを先頭、あとは作成日降順
        workspaces.sort(key=lambda x: (x.get("id") != self.DEFAULT_WORKSPACE_ID, x.get("created_at", "")), reverse=True)
        # default を最優先
        workspaces.sort(key=lambda x: 0 if x.get("id") == self.DEFAULT_WORKSPACE_ID else 1)
        return workspaces

    def get_workspace(self, ws_id: str) -> Optional[Dict[str, Any]]:
        """特定ワークスペースの情報を取得"""
        ws_dir = os.path.join(self.workspaces_root, ws_id)
        meta_path = os.path.join(ws_dir, "workspace_meta.json")
        if not os.path.exists(meta_path):
            return None
        try:
            with open(meta_path, 'r', encoding='utf-8') as f:
                meta = json.load(f)
            meta["disk_size_bytes"] = self._get_dir_size(ws_dir)
            return meta
        except Exception:
            return None

    def create_workspace(self, ws_id: str, name: str, description: str = "", clone_from: Optional[str] = None) -> Dict[str, Any]:
        """新規ワークスペースを作成（既存ワークスペースからのルール等の複製も対応）"""
        clean_id = self._sanitize_id(ws_id)
        ws_dir = os.path.join(self.workspaces_root, clean_id)
        if os.path.exists(ws_dir):
            raise ValueError(f"ワークスペースID '{clean_id}' は既に存在します。")

        ws_data_dir = os.path.join(ws_dir, "data")
        ws_rules_dir = os.path.join(ws_dir, "rules")
        ws_snapshots_dir = os.path.join(ws_dir, "snapshots")
        ws_exports_dir = os.path.join(ws_dir, "exports")
        os.makedirs(ws_data_dir, exist_ok=True)
        os.makedirs(ws_rules_dir, exist_ok=True)
        os.makedirs(ws_snapshots_dir, exist_ok=True)
        os.makedirs(ws_exports_dir, exist_ok=True)

        # ルールの初期化（clone_from が指定されている場合はそのルールを複製、なければデフォルトルールテンプレートから）
        source_rules_dir = None
        if clone_from:
            source_rules_dir = os.path.join(self.workspaces_root, clone_from, "rules")
        if not source_rules_dir or not os.path.exists(source_rules_dir):
            source_rules_dir = self.default_rules_dir

        if os.path.exists(source_rules_dir):
            for fname in os.listdir(source_rules_dir):
                src = os.path.join(source_rules_dir, fname)
                dst = os.path.join(ws_rules_dir, fname)
                if os.path.isfile(src):
                    shutil.copy2(src, dst)

        now_str = datetime.datetime.now().isoformat()
        meta = {
            "id": clean_id,
            "name": name.strip() or clean_id,
            "description": description.strip(),
            "created_at": now_str,
            "updated_at": now_str,
            "cloned_from": clone_from
        }
        meta_path = os.path.join(ws_dir, "workspace_meta.json")
        with open(meta_path, 'w', encoding='utf-8') as f:
            json.dump(meta, f, ensure_ascii=False, indent=2)

        logger.info(f"[WorkspaceManager] 新規ワークスペース作成完了: {clean_id} ({name})")
        return meta

    def delete_workspace(self, ws_id: str) -> bool:
        """ワークスペースを削除（デフォルトワークスペースは保護）"""
        if ws_id == self.DEFAULT_WORKSPACE_ID:
            raise ValueError("デフォルトワークスペースは削除できません。")

        ws_dir = os.path.join(self.workspaces_root, ws_id)
        if not os.path.exists(ws_dir):
            return False

        shutil.rmtree(ws_dir)
        logger.info(f"[WorkspaceManager] ワークスペース削除完了: {ws_id}")
        return True

    def get_workspace_paths(self, ws_id: str) -> Dict[str, str]:
        """
        既存の app.py の PATHS 辞書と100%互換のパス辞書を生成
        """
        clean_id = self._sanitize_id(ws_id)
        ws_dir = os.path.join(self.workspaces_root, clean_id)
        if not os.path.exists(ws_dir):
            # 存在しない場合はデフォルトにフォールバック
            clean_id = self.DEFAULT_WORKSPACE_ID
            ws_dir = os.path.join(self.workspaces_root, clean_id)

        ws_data_dir = os.path.join(ws_dir, "data")
        ws_rules_dir = os.path.join(ws_dir, "rules")
        ws_snapshots_dir = os.path.join(ws_dir, "snapshots")
        ws_exports_dir = os.path.join(ws_dir, "exports")

        os.makedirs(ws_data_dir, exist_ok=True)
        os.makedirs(ws_rules_dir, exist_ok=True)
        os.makedirs(ws_snapshots_dir, exist_ok=True)
        os.makedirs(ws_exports_dir, exist_ok=True)

        return {
            # --- 既存 PATHS 辞書互換キー ---
            "PATH_RAW_METADATA": os.path.join(ws_data_dir, "raw_metadata.jsonl"),
            "PATH_TARGET_URIS": os.path.join(ws_data_dir, "target_uris.csv"),
            "PATH_TYPE_RULES": os.path.join(ws_rules_dir, "type_rules.json"),
            "PATH_TYPE_FILTERED": os.path.join(ws_data_dir, "type_filtered.jsonl"),
            "PATH_ABOUT_RULES": os.path.join(ws_rules_dir, "about_rules.json"),
            "PATH_NGRAM_RULES": os.path.join(ws_rules_dir, "ngram_rules.json"),
            "PATH_ABOUT_FILTERED": os.path.join(ws_data_dir, "about_filtered.jsonl"),
            "PATH_NGRAM_FILTERED": os.path.join(ws_data_dir, "ngram_filtered.jsonl"),
            "PATH_TARGET_FOR_LLM": os.path.join(ws_data_dir, "target_for_llm.jsonl"),
            "PATH_CONFIRMED_OK": os.path.join(ws_data_dir, "confirmed_ok_rules.jsonl"),
            "PATH_DISCARDED_RULES": os.path.join(ws_data_dir, "discarded_rules.csv"),
            "PATH_LLM_JUDGMENTS": os.path.join(ws_data_dir, "llm_judgments.jsonl"),
            "PATH_VERIFIED_JSONL": os.path.join(ws_data_dir, "human_verified_cleaned.jsonl"),
            "PATH_EXPORT_JSON": os.path.join(self.viewer_dir, "scores_data.json"),  # 公開用ビューア直下
            "PATH_DUCKDB": os.path.join(ws_data_dir, "metadata_store.duckdb"),
            "PATH_JOB_STATUS": os.path.join(ws_data_dir, "fetch_job_status.json"),
            "PATH_ACQUISITION_MANIFEST": os.path.join(ws_data_dir, "acquisition_manifest.json"),
            
            # --- 追加の便利なメタパス ---
            "WORKSPACE_ID": clean_id,
            "DIR_WORKSPACE": ws_dir,
            "DIR_DATA": ws_data_dir,
            "DIR_RULES": ws_rules_dir,
            "DIR_SNAPSHOTS": ws_snapshots_dir,
            "DIR_EXPORTS": ws_exports_dir,
            "PATH_CURRENT_PARAMS": os.path.join(ws_data_dir, "current_fetch_params.json"),
            "PATH_PRISMA_SUMMARY": os.path.join(ws_data_dir, "prisma_flow_summary.json"),
            "PATH_AUDIT_TRAIL": os.path.join(ws_data_dir, "complete_audit_trail.csv"),
            "PATH_LOCAL_EXPORT_JSON": os.path.join(ws_exports_dir, "scores_data.json")
        }

    # =========================================================================
    # Layer 2: フィルタリング経過（スナップショット）マネジメント
    # =========================================================================

    def save_snapshot(self, ws_id: str, name: str, description: str = "") -> Dict[str, Any]:
        """
        現在のフィルタリングルールおよびDuckDB判定ステータスカラムをスナップショット保存
        """
        paths = self.get_workspace_paths(ws_id)
        snapshots_dir = paths["DIR_SNAPSHOTS"]
        rules_dir = paths["DIR_RULES"]
        duckdb_path = paths["PATH_DUCKDB"]

        now = datetime.datetime.now()
        snap_id = f"snap_{now.strftime('%Y%m%d_%H%M%S')}"
        target_dir = os.path.join(snapshots_dir, snap_id)
        os.makedirs(target_dir, exist_ok=True)

        # 1. ルール群の退避
        snap_rules_dir = os.path.join(target_dir, "rules")
        os.makedirs(snap_rules_dir, exist_ok=True)
        if os.path.exists(rules_dir):
            for fname in os.listdir(rules_dir):
                src = os.path.join(rules_dir, fname)
                if os.path.isfile(src):
                    shutil.copy2(src, os.path.join(snap_rules_dir, fname))

        # 2. DuckDB から判定カラムのみを Parquet に高速ダンプ
        metrics = {"total": 0, "adopted": 0, "discarded": 0, "grey": 0}
        parquet_path = os.path.join(target_dir, "decisions.parquet")
        
        if os.path.exists(duckdb_path) and duckdb:
            try:
                con = duckdb.connect(duckdb_path, read_only=True)
                # テーブル存在確認
                tbl_check = con.execute("SELECT count(*) FROM information_schema.tables WHERE table_name = 'metadata_records';").fetchone()
                if tbl_check and tbl_check[0] > 0:
                    # 集計メトリクス取得
                    m_row = con.execute("""
                        SELECT 
                            count(*) AS total,
                            count(*) FILTER (WHERE final_decision = 'OK' OR human_decision = 'ADOPT') AS adopted,
                            count(*) FILTER (WHERE final_decision = 'NG' OR human_decision = 'DISCARD') AS discarded,
                            count(*) FILTER (WHERE (final_decision = 'GREY' OR final_decision IS NULL) AND human_decision IS NULL) AS grey
                        FROM metadata_records;
                    """).fetchone()
                    if m_row:
                        metrics = {
                            "total": int(m_row[0]),
                            "adopted": int(m_row[1]),
                            "discarded": int(m_row[2]),
                            "grey": int(m_row[3])
                        }

                    # Parquet へのダンプ
                    con.execute(f"""
                        COPY (
                            SELECT 
                                id,
                                type_status,
                                type_reason,
                                about_status,
                                about_reason,
                                ngram_status,
                                ngram_reason,
                                llm_status,
                                llm_reason,
                                final_decision,
                                human_decision,
                                review_reasons,
                                llm_evaluated,
                                adopted_stage,
                                drop_stage,
                                primary_reason
                            FROM metadata_records
                        ) TO '{parquet_path}' (FORMAT 'PARQUET', COMPRESSION 'ZSTD');
                    """)
                con.close()
            except Exception as e:
                logger.error(f"[WorkspaceManager] Error dumping decisions to parquet: {e}")

        # 3. スナップショットメタ情報の保存
        snap_meta = {
            "id": snap_id,
            "name": name.strip() or snap_id,
            "description": description.strip(),
            "created_at": now.isoformat(),
            "metrics": metrics,
            "has_decisions_parquet": os.path.exists(parquet_path)
        }
        meta_file = os.path.join(target_dir, "snapshot_meta.json")
        with open(meta_file, 'w', encoding='utf-8') as f:
            json.dump(snap_meta, f, ensure_ascii=False, indent=2)

        logger.info(f"[WorkspaceManager] スナップショット保存完了: {snap_id} ({name})")
        return snap_meta

    def list_snapshots(self, ws_id: str) -> List[Dict[str, Any]]:
        """ワークスペース内のスナップショット一覧を取得（新しい順）"""
        paths = self.get_workspace_paths(ws_id)
        snapshots_dir = paths["DIR_SNAPSHOTS"]
        snapshots = []

        if not os.path.exists(snapshots_dir):
            return snapshots

        for entry in os.listdir(snapshots_dir):
            snap_dir = os.path.join(snapshots_dir, entry)
            if not os.path.isdir(snap_dir):
                continue
            meta_path = os.path.join(snap_dir, "snapshot_meta.json")
            if os.path.exists(meta_path):
                try:
                    with open(meta_path, 'r', encoding='utf-8') as f:
                        meta = json.load(f)
                    meta["disk_size_bytes"] = self._get_dir_size(snap_dir)
                    snapshots.append(meta)
                except Exception as e:
                    logger.warning(f"Error loading snapshot meta {entry}: {e}")

        snapshots.sort(key=lambda x: x.get("created_at", ""), reverse=True)
        return snapshots

    def restore_snapshot(self, ws_id: str, snapshot_id: str) -> bool:
        """
        スナップショットからルールおよびDuckDB判定ステータスを復元（ロールバック）
        """
        paths = self.get_workspace_paths(ws_id)
        snapshots_dir = paths["DIR_SNAPSHOTS"]
        rules_dir = paths["DIR_RULES"]
        duckdb_path = paths["PATH_DUCKDB"]

        snap_dir = os.path.join(snapshots_dir, snapshot_id)
        if not os.path.exists(snap_dir):
            raise ValueError(f"スナップショット '{snapshot_id}' が見つかりません。")

        # 1. ルールファイルの復元
        snap_rules_dir = os.path.join(snap_dir, "rules")
        if os.path.exists(snap_rules_dir):
            for fname in os.listdir(snap_rules_dir):
                src = os.path.join(snap_rules_dir, fname)
                dst = os.path.join(rules_dir, fname)
                if os.path.isfile(src):
                    shutil.copy2(src, dst)

        # 2. DuckDB 判定カラムの一括バッチ更新
        parquet_path = os.path.join(snap_dir, "decisions.parquet")
        if os.path.exists(duckdb_path) and os.path.exists(parquet_path) and duckdb:
            try:
                con = duckdb.connect(duckdb_path)
                con.execute(f"""
                    UPDATE metadata_records AS m
                    SET
                        type_status = s.type_status,
                        type_reason = s.type_reason,
                        about_status = s.about_status,
                        about_reason = s.about_reason,
                        ngram_status = s.ngram_status,
                        ngram_reason = s.ngram_reason,
                        llm_status = s.llm_status,
                        llm_reason = s.llm_reason,
                        final_decision = s.final_decision,
                        human_decision = s.human_decision,
                        review_reasons = s.review_reasons,
                        llm_evaluated = s.llm_evaluated,
                        adopted_stage = s.adopted_stage,
                        drop_stage = s.drop_stage,
                        primary_reason = s.primary_reason
                    FROM read_parquet('{parquet_path}') AS s
                    WHERE m.id = s.id;
                """)
                con.close()
                logger.info(f"[WorkspaceManager] DuckDB 判定ステータスをスナップショット '{snapshot_id}' から復元完了")
            except Exception as e:
                logger.error(f"[WorkspaceManager] Error restoring decisions from parquet: {e}")
                return False

        logger.info(f"[WorkspaceManager] スナップショット復元完了: {snapshot_id}")
        return True

    def delete_snapshot(self, ws_id: str, snapshot_id: str) -> bool:
        """スナップショットを削除"""
        paths = self.get_workspace_paths(ws_id)
        snap_dir = os.path.join(paths["DIR_SNAPSHOTS"], snapshot_id)
        if not os.path.exists(snap_dir):
            return False
        shutil.rmtree(snap_dir)
        logger.info(f"[WorkspaceManager] スナップショット削除完了: {snapshot_id}")
        return True

    # =========================================================================
    # Layer 3: データ共有・他者引継ぎパッケージ（Export / Import）
    # =========================================================================

    def export_package(self, ws_id: str, output_path: str, export_type: str = "recipe") -> str:
        """
        ワークスペースをZIPアーカイブとしてエクスポート
        :param export_type: 'recipe' (ルール＋マニフェスト等の軽量版) または 'full' (生データ・DuckDB含む完全版)
        """
        paths = self.get_workspace_paths(ws_id)
        ws_dir = paths["DIR_WORKSPACE"]
        os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)

        meta = self.get_workspace(ws_id) or {"id": ws_id, "name": ws_id}
        package_manifest = {
            "version": "1.0",
            "export_type": export_type,
            "exported_at": datetime.datetime.now().isoformat(),
            "workspace_meta": meta
        }

        with zipfile.ZipFile(output_path, 'w', compression=zipfile.ZIP_DEFLATED) as zf:
            # パッケージマニフェスト書き込み
            zf.writestr("package_manifest.json", json.dumps(package_manifest, ensure_ascii=False, indent=2))

            # ルール群の追加
            rules_dir = paths["DIR_RULES"]
            if os.path.exists(rules_dir):
                for root, _, files in os.walk(rules_dir):
                    for f in files:
                        p = os.path.join(root, f)
                        arcname = os.path.join("rules", os.path.relpath(p, rules_dir))
                        zf.write(p, arcname)

            # データディレクトリ内のファイル
            data_dir = paths["DIR_DATA"]
            recipe_allowed_files = [
                "acquisition_manifest.json",
                "current_fetch_params.json",
                "prisma_flow_summary.json",
                "human_verified_cleaned.jsonl",
                "complete_audit_trail.csv"
            ]

            if os.path.exists(data_dir):
                for root, _, files in os.walk(data_dir):
                    for f in files:
                        p = os.path.join(root, f)
                        rel_p = os.path.relpath(p, data_dir)
                        if export_type == "recipe":
                            if f in recipe_allowed_files:
                                zf.write(p, os.path.join("data", rel_p))
                        else:  # full
                            zf.write(p, os.path.join("data", rel_p))

            # エクスポートディレクトリ内の成果物
            exports_dir = paths["DIR_EXPORTS"]
            if os.path.exists(exports_dir):
                for root, _, files in os.walk(exports_dir):
                    for f in files:
                        p = os.path.join(root, f)
                        arcname = os.path.join("exports", os.path.relpath(p, exports_dir))
                        zf.write(p, arcname)

        logger.info(f"[WorkspaceManager] パッケージエクスポート完了: {output_path} (Type: {export_type})")
        return output_path

    def import_package(self, package_zip_path: str, new_ws_id: Optional[str] = None, new_name: Optional[str] = None) -> Dict[str, Any]:
        """
        ZIPアーカイブからワークスペースを新規復元・展開
        """
        if not os.path.exists(package_zip_path):
            raise FileNotFoundError(f"パッケージファイルが見つかりません: {package_zip_path}")

        with zipfile.ZipFile(package_zip_path, 'r') as zf:
            # マニフェストの読み込み
            if "package_manifest.json" not in zf.namelist():
                raise ValueError("無効なパッケージファイルです（package_manifest.json が見つかりません）。")

            manifest_bytes = zf.read("package_manifest.json")
            pkg_manifest = json.loads(manifest_bytes.decode('utf-8'))
            orig_meta = pkg_manifest.get("workspace_meta", {})

            # ワークスペースIDの決定
            target_id = new_ws_id or orig_meta.get("id") or "imported_workspace"
            target_id = self._sanitize_id(target_id)

            # 重複回避
            candidate_id = target_id
            counter = 1
            while os.path.exists(os.path.join(self.workspaces_root, candidate_id)):
                candidate_id = f"{target_id}_{counter}"
                counter += 1
            target_id = candidate_id

            target_name = new_name or orig_meta.get("name") or target_id
            target_desc = orig_meta.get("description", "") + f" (インポート元: {os.path.basename(package_zip_path)})"

            # 新規ワークスペース作成
            new_meta = self.create_workspace(target_id, target_name, target_desc)
            ws_paths = self.get_workspace_paths(target_id)
            ws_dir = ws_paths["DIR_WORKSPACE"]

            # ファイル展開
            for member in zf.namelist():
                if member in ("package_manifest.json", "workspace_meta.json"):
                    continue
                # ディレクトリトラバーサル防止
                if member.startswith("/") or ".." in member:
                    continue
                zf.extract(member, ws_dir)

            logger.info(f"[WorkspaceManager] パッケージインポート完了: {target_id} ({target_name})")
            return self.get_workspace(target_id) or new_meta

    # =========================================================================
    # ユーティリティ
    # =========================================================================

    def _sanitize_id(self, raw_id: str) -> str:
        """安全な英数字+アンダースコアのIDにサニタイズ"""
        import re
        s = re.sub(r"[^a-zA-Z0-9_\-]", "_", raw_id.strip())
        return s or "workspace"

    def _get_dir_size(self, path: str) -> int:
        """ディレクトリの合計サイズ（バイト）を計算"""
        total = 0
        try:
            for root, _, files in os.walk(path):
                for f in files:
                    fp = os.path.join(root, f)
                    if os.path.exists(fp) and not os.path.islink(fp):
                        total += os.path.getsize(fp)
        except Exception:
            pass
        return total
