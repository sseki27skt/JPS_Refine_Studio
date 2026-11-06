import React, { useState, useEffect } from 'react';
import { DashboardStats, WorkspaceMeta } from '../types/api';
import { api } from '../api/client';
import { 
  Download, 
  CheckCircle2, 
  FileText, 
  Database, 
  RefreshCw, 
  AlertCircle,
  FolderArchive,
  Layers,
  Sparkles
} from 'lucide-react';

interface ExportViewProps {
  workspaceId: string;
}

export const ExportView: React.FC<ExportViewProps> = ({ workspaceId }) => {
  const [stats, setStats] = useState<DashboardStats | null>(null);
  const [workspace, setWorkspace] = useState<WorkspaceMeta | null>(null);
  const [loading, setLoading] = useState(true);
  const [exporting, setExporting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [resultMessage, setResultMessage] = useState<string | null>(null);

  const loadData = async () => {
    try {
      setLoading(true);
      setError(null);
      const [s, w] = await Promise.all([
        api.getDashboardStats(workspaceId),
        api.getWorkspace(workspaceId)
      ]);
      setStats(s);
      setWorkspace(w);
    } catch (err: any) {
      setError(err.message || 'データ読み込みに失敗しました');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadData();
  }, [workspaceId]);

  const handleExport = async () => {
    try {
      setExporting(true);
      setError(null);
      setResultMessage(null);
      const res = await api.exportVerified(workspaceId);
      setResultMessage(res.message);
      await loadData();
    } catch (err: any) {
      setError(err.message || 'エクスポートに失敗しました');
    } finally {
      setExporting(false);
    }
  };

  return (
    <div className="space-y-6">
      {/* 画面ヘッダー */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <div className="flex items-center space-x-2 text-sm text-slate-500 mb-1">
            <span className="font-semibold text-indigo-600">Step 5</span>
            <span>•</span>
            <span>データセット確定</span>
          </div>
          <h1 className="text-2xl font-bold text-slate-800">確定データセットのエクスポート</h1>
          <p className="text-sm text-slate-600 mt-1">
            多段階クレンジングおよび専門家査読を経て確定した特定主題の高品質メタデータセットをファイル出力します。
          </p>
        </div>

        <button
          onClick={loadData}
          disabled={loading}
          className="inline-flex items-center px-3 py-2 border border-slate-300 rounded-md shadow-sm text-sm font-medium text-slate-700 bg-white hover:bg-slate-50 disabled:opacity-50"
        >
          <RefreshCw className={`w-4 h-4 mr-2 ${loading ? 'animate-spin' : ''}`} />
          状態更新
        </button>
      </div>

      {error && (
        <div className="p-4 bg-red-50 border border-red-200 rounded-lg flex items-center space-x-2 text-red-700 text-sm">
          <AlertCircle className="w-5 h-5 flex-shrink-0" />
          <span>{error}</span>
        </div>
      )}

      {resultMessage && (
        <div className="p-4 bg-emerald-50 border border-emerald-200 rounded-lg flex items-center space-x-2 text-emerald-700 text-sm">
          <CheckCircle2 className="w-5 h-5 flex-shrink-0" />
          <span>{resultMessage}</span>
        </div>
      )}

      {/* サマリーカード */}
      {stats && (
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <div className="bg-white p-5 rounded-xl border border-slate-200 shadow-sm flex items-center space-x-4">
            <div className="p-3 bg-emerald-50 text-emerald-600 rounded-lg">
              <CheckCircle2 className="w-8 h-8" />
            </div>
            <div>
              <div className="text-xs text-slate-500 font-medium">確定合格レコード数</div>
              <div className="text-2xl font-bold text-emerald-600">
                {stats.step5_export_ready.toLocaleString()} 件
              </div>
              <div className="text-xs text-slate-400 mt-0.5">エクスポート対象</div>
            </div>
          </div>

          <div className="bg-white p-5 rounded-xl border border-slate-200 shadow-sm flex items-center space-x-4">
            <div className="p-3 bg-indigo-50 text-indigo-600 rounded-lg">
              <Layers className="w-8 h-8" />
            </div>
            <div>
              <div className="text-xs text-slate-500 font-medium">専門家査読完了数</div>
              <div className="text-2xl font-bold text-slate-800">
                {stats.step4_human_reviewed.toLocaleString()} 件
              </div>
              <div className="text-xs text-slate-400 mt-0.5">Verified フラグ済み</div>
            </div>
          </div>

          <div className="bg-white p-5 rounded-xl border border-slate-200 shadow-sm flex items-center space-x-4">
            <div className="p-3 bg-slate-50 text-slate-600 rounded-lg">
              <Database className="w-8 h-8" />
            </div>
            <div>
              <div className="text-xs text-slate-500 font-medium">母集団メタデータ総数</div>
              <div className="text-2xl font-bold text-slate-800">
                {stats.total_records.toLocaleString()} 件
              </div>
              <div className="text-xs text-slate-400 mt-0.5">
                残存率: {stats.total_records > 0 ? ((stats.step5_export_ready / stats.total_records) * 100).toFixed(1) : 0}%
              </div>
            </div>
          </div>
        </div>
      )}

      {/* エクスポート実行カード */}
      <div className="bg-white rounded-xl border border-slate-200 shadow-sm p-6 space-y-6">
        <div className="border-b border-slate-100 pb-4">
          <h2 className="text-lg font-bold text-slate-800">確定データセットの同期とファイル出力</h2>
          <p className="text-xs text-slate-500 mt-1">
            DuckDBの最新査読・判定結果を反映した確定JSONLファイル（<code>human_verified_cleaned.jsonl</code>）を出力します。
          </p>
        </div>

        <div className="bg-slate-50 rounded-xl p-4 border border-slate-200 space-y-3">
          <div className="font-semibold text-slate-700 text-sm flex items-center">
            <FileText className="w-4 h-4 mr-2 text-indigo-600" />
            出力成果物一覧
          </div>
          <div className="text-xs text-slate-600 space-y-1.5 pl-6">
            <p>
              • <code>data/workspaces/{workspaceId}/human_verified_cleaned.jsonl</code> : 
              専門家査読およびルール・LLMで合格となった確定メタデータ一覧（改行区切りJSON）
            </p>
            <p>
              • <code>data/workspaces/{workspaceId}/raw_metadata.duckdb</code> : 
              全判定履歴、除外理由、メタデータ原本を含む完全DuckDBデータベースファイル
            </p>
            <p>
              • <code>data/workspaces/{workspaceId}/rules/</code> : 
              Type, About, N-gram の適用ルール設定JSONファイル群
            </p>
          </div>
        </div>

        <div className="flex items-center justify-between pt-2">
          <div className="text-xs text-slate-500">
            ※ ファイルはサーバー上のワークスペースディレクトリに即時保存されます。
          </div>

          <button
            onClick={handleExport}
            disabled={exporting}
            className="inline-flex items-center px-6 py-2.5 border border-transparent rounded-lg shadow-sm text-sm font-semibold text-white bg-indigo-600 hover:bg-indigo-700 disabled:opacity-50 transition-colors"
          >
            <Download className="w-4 h-4 mr-2" />
            {exporting ? 'エクスポート中...' : '確定データセットを同期出力'}
          </button>
        </div>
      </div>
    </div>
  );
};

