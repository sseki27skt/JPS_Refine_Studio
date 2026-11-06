// -*- coding: utf-8 -*-
/**
 * 常駐型バックグラウンドジョブ進捗バー
 */
import React from 'react';
import { JobProgress } from '../types/api';
import { api } from '../api/client';
import { Loader2, StopCircle, CheckCircle, AlertCircle } from 'lucide-react';

interface Props {
  job: JobProgress | null;
  onJobStopped?: () => void;
}

export const JobProgressBar: React.FC<Props> = ({ job, onJobStopped }) => {
  if (!job || job.status === 'IDLE') return null;

  const isRunning = job.status === 'RUNNING' || job.status === 'PENDING';
  const isCompleted = job.status === 'COMPLETED';
  const isFailed = job.status === 'FAILED';
  const isStopped = job.status === 'STOPPED';

  const handleStop = async () => {
    if (!window.confirm('進行中のバックグラウンド処理を中断しますか？')) return;
    try {
      await api.stopJob(job.job_id);
      if (onJobStopped) onJobStopped();
    } catch (err: any) {
      alert(`中断リクエスト失敗: ${err.message}`);
    }
  };

  const etaStr = job.eta_seconds && job.eta_seconds > 0
    ? `残り推定: 約${Math.floor(job.eta_seconds / 60)}分${job.eta_seconds % 60}秒`
    : '残り推定: 計算中...';

  return (
    <div className={`border-b px-6 py-2.5 transition-colors shadow-sm flex flex-col md:flex-row md:items-center justify-between gap-3 ${
      isRunning ? 'bg-sky-50 border-sky-200' :
      isCompleted ? 'bg-emerald-50 border-emerald-200' :
      isFailed ? 'bg-rose-50 border-rose-200' : 'bg-slate-100 border-slate-200'
    }`}>
      <div className="flex items-center gap-3">
        {isRunning && <Loader2 className="w-5 h-5 text-sky-600 animate-spin flex-shrink-0" />}
        {isCompleted && <CheckCircle className="w-5 h-5 text-emerald-600 flex-shrink-0" />}
        {isFailed && <AlertCircle className="w-5 h-5 text-rose-600 flex-shrink-0" />}
        {isStopped && <StopCircle className="w-5 h-5 text-slate-500 flex-shrink-0" />}

        <div>
          <div className="flex items-center gap-2">
            <span className="font-semibold text-sm text-slate-800">
              {job.type === 'sparql_fetch' && 'SPARQLメタデータ一括取得'}
              {job.type === 'apply_rules' && 'ルール一括適用・DuckDB同期'}
              {job.type === 'llm_classification' && 'LLMセマンティック適合判定'}
              {job.type === 'llm_stage2' && 'LLM判定不能群の再推論'}
              {!['sparql_fetch', 'apply_rules', 'llm_classification', 'llm_stage2'].includes(job.type) && job.type}
            </span>
            <span className="text-xs px-2 py-0.5 rounded font-mono font-medium bg-white/70 border border-slate-200">
              {job.status}
            </span>
          </div>
          <p className="text-xs text-slate-600 mt-0.5">
            {job.stage}
            {isRunning && job.total > 0 && ` (${job.current.toLocaleString()} / ${job.total.toLocaleString()} 件 - ${job.percentage}%)`}
            {isRunning && job.total > 0 && <span className="ml-2 font-mono text-slate-500">{etaStr}</span>}
          </p>
          {job.error_message && (
            <p className="text-xs text-rose-600 font-medium mt-0.5">{job.error_message}</p>
          )}
        </div>
      </div>

      <div className="flex items-center gap-4 flex-shrink-0">
        {isRunning && (
          <div className="w-48 bg-slate-200 rounded-full h-2.5 overflow-hidden border border-slate-300">
            <div
              className="bg-sky-600 h-2.5 rounded-full transition-all duration-300"
              style={{ width: `${Math.min(100, Math.max(5, job.percentage))}%` }}
            />
          </div>
        )}
        {isRunning && (
          <button
            onClick={handleStop}
            className="flex items-center gap-1.5 px-3 py-1 bg-white hover:bg-rose-50 text-rose-600 border border-rose-300 rounded text-xs font-medium shadow-sm transition-colors"
          >
            <StopCircle className="w-3.5 h-3.5" />
            中断
          </button>
        )}
      </div>
    </div>
  );
};

