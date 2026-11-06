import React, { useState, useEffect } from 'react';
import { DashboardStats } from '../types/api';
import { api } from '../api/client';
import { 
  Bot, 
  Play, 
  RefreshCw, 
  AlertCircle, 
  CheckCircle2, 
  HelpCircle, 
  Settings,
  Sparkles,
  Cpu
} from 'lucide-react';

interface LlmFilterViewProps {
  workspaceId: string;
}

export const LlmFilterView: React.FC<LlmFilterViewProps> = ({ workspaceId }) => {
  const [stats, setStats] = useState<DashboardStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [starting, setStarting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [successMsg, setSuccessMsg] = useState<string | null>(null);

  // フォーム設定
  const [domainDefinition, setDomainDefinition] = useState('雅楽に関する楽譜、文献、音源、公演資料');
  const [provider, setProvider] = useState('openrouter');
  const [model, setModel] = useState('google/gemini-2.0-flash-001');
  const [apiKey, setApiKey] = useState('');
  const [maxWorkers, setMaxWorkers] = useState(5);
  const [limit, setLimit] = useState(0);

  const loadStats = async () => {
    try {
      setLoading(true);
      setError(null);
      const res = await api.getDashboardStats(workspaceId);
      setStats(res);
    } catch (err: any) {
      setError(err.message || 'ダッシュボード統計の取得に失敗しました');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadStats();
  }, [workspaceId]);

  const handleStartLlm = async () => {
    if (!domainDefinition.trim()) {
      setError('主題・判定基準のドメイン定義を入力してください');
      return;
    }

    try {
      setStarting(true);
      setError(null);
      setSuccessMsg(null);
      const res = await api.startLlm(workspaceId, {
        domain_definition: domainDefinition,
        provider,
        api_key: apiKey.trim() || undefined,
        model,
        max_workers: maxWorkers,
        limit: limit > 0 ? limit : undefined,
        stage2: true,
      });
      setSuccessMsg(res.message);
      await loadStats();
    } catch (err: any) {
      setError(err.message || 'LLM推論ジョブの開始に失敗しました');
    } finally {
      setStarting(false);
    }
  };

  const isJobRunning = Boolean(stats?.active_job && stats.active_job.status === 'RUNNING');

  return (
    <div className="space-y-6">
      {/* 画面ヘッダー */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <div className="flex items-center space-x-2 text-sm text-slate-500 mb-1">
            <span className="font-semibold text-indigo-600">Step 3</span>
            <span>•</span>
            <span>セマンティック推論</span>
          </div>
          <h1 className="text-2xl font-bold text-slate-800">LLMセマンティック適合判定</h1>
          <p className="text-sm text-slate-600 mt-1">
            ルールでは判断がつかないグレーゾーン（判定保留）のレコードに対し、LLM（Gemini等）が文脈を解釈して合否を自動判定します。
          </p>
        </div>

        <button
          onClick={loadStats}
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

      {successMsg && (
        <div className="p-4 bg-emerald-50 border border-emerald-200 rounded-lg flex items-center space-x-2 text-emerald-700 text-sm">
          <CheckCircle2 className="w-5 h-5 flex-shrink-0" />
          <span>{successMsg}</span>
        </div>
      )}

      {/* ステータスサマリーカード */}
      {stats && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <div className="bg-white p-4 rounded-xl border border-slate-200 shadow-sm">
            <div className="text-xs text-slate-500 font-medium">総レコード数</div>
            <div className="text-2xl font-bold text-slate-800 mt-1">
              {stats.total_records.toLocaleString()}
            </div>
            <div className="text-xs text-slate-400 mt-1">ワークスペース全体</div>
          </div>

          <div className="bg-white p-4 rounded-xl border border-slate-200 shadow-sm">
            <div className="text-xs text-slate-500 font-medium">ルール通過レコード</div>
            <div className="text-2xl font-bold text-indigo-600 mt-1">
              {stats.step2c_ngram_survivors.toLocaleString()}
            </div>
            <div className="text-xs text-slate-400 mt-1">Step 2-C 残存件数</div>
          </div>

          <div className="bg-white p-4 rounded-xl border border-slate-200 shadow-sm">
            <div className="text-xs text-slate-500 font-medium">LLM判定完了レコード</div>
            <div className="text-2xl font-bold text-emerald-600 mt-1 flex items-center">
              <CheckCircle2 className="w-5 h-5 mr-1" />
              {stats.step3_llm_evaluated.toLocaleString()}
            </div>
            <div className="text-xs text-slate-400 mt-1">セマンティック適合済み</div>
          </div>

          <div className="bg-white p-4 rounded-xl border border-slate-200 shadow-sm">
            <div className="text-xs text-slate-500 font-medium">確定査読数</div>
            <div className="text-2xl font-bold text-slate-800 mt-1 flex items-center">
              <HelpCircle className="w-5 h-5 mr-1 text-slate-400" />
              {stats.step4_human_reviewed.toLocaleString()}
            </div>
            <div className="text-xs text-slate-400 mt-1">専門家査読完了</div>
          </div>
        </div>
      )}

      {/* 推論実行設定カード */}
      <div className="bg-white rounded-xl border border-slate-200 shadow-sm p-6 space-y-6">
        <div className="flex items-center space-x-2 border-b border-slate-100 pb-3">
          <Settings className="w-5 h-5 text-indigo-600" />
          <h2 className="text-lg font-bold text-slate-800">推論パラメーター設定</h2>
        </div>

        <div className="space-y-4">
          <div>
            <label className="block text-sm font-semibold text-slate-700 mb-1">
              主題・判定基準のドメイン定義（LLMプロンプトの核）
            </label>
            <textarea
              rows={3}
              value={domainDefinition}
              onChange={(e) => setDomainDefinition(e.target.value)}
              placeholder="例: 日本の伝統音楽である雅楽に関する楽譜、文献、音源、楽器、公演記録を採択し、西洋音楽や関係のない現代ポップス等は除外する。"
              className="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
              disabled={isJobRunning}
            />
          </div>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <div>
              <label className="block text-sm font-semibold text-slate-700 mb-1">
                プロバイダー
              </label>
              <select
                value={provider}
                onChange={(e) => setProvider(e.target.value)}
                className="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm bg-white focus:outline-none focus:ring-2 focus:ring-indigo-500"
                disabled={isJobRunning}
              >
                <option value="openrouter">OpenRouter (Gemini, Claude, GPT)</option>
                <option value="gemini">Google Gemini Direct</option>
              </select>
            </div>

            <div>
              <label className="block text-sm font-semibold text-slate-700 mb-1">
                モデル名
              </label>
              <input
                type="text"
                value={model}
                onChange={(e) => setModel(e.target.value)}
                className="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
                disabled={isJobRunning}
              />
            </div>

            <div>
              <label className="block text-sm font-semibold text-slate-700 mb-1">
                APIキー（省略時は環境変数を使用）
              </label>
              <input
                type="password"
                placeholder="sk-or-..."
                value={apiKey}
                onChange={(e) => setApiKey(e.target.value)}
                className="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
                disabled={isJobRunning}
              />
            </div>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-semibold text-slate-700 mb-1">
                並列ワーカー数 (Concurrency)
              </label>
              <input
                type="number"
                min={1}
                max={20}
                value={maxWorkers}
                onChange={(e) => setMaxWorkers(Number(e.target.value))}
                className="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
                disabled={isJobRunning}
              />
            </div>

            <div>
              <label className="block text-sm font-semibold text-slate-700 mb-1">
                処理件数上限（0で全件処理）
              </label>
              <input
                type="number"
                min={0}
                value={limit}
                onChange={(e) => setLimit(Number(e.target.value))}
                className="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
                disabled={isJobRunning}
              />
            </div>
          </div>
        </div>

        <div className="pt-4 border-t border-slate-100 flex items-center justify-between">
          <div className="text-xs text-slate-500">
            {isJobRunning ? (
              <span className="flex items-center text-indigo-600 font-semibold">
                <span className="inline-block animate-spin rounded-full h-3 w-3 border-2 border-indigo-600 border-t-transparent mr-2" />
                推論ジョブがバックグラウンドで実行中です。ブラウザを閉じても中断されません。
              </span>
            ) : (
              <span>※ バックグラウンドワーカーで実行され、リアルタイムに進捗が更新されます。</span>
            )}
          </div>

          <button
            onClick={handleStartLlm}
            disabled={isJobRunning || starting}
            className="inline-flex items-center px-6 py-2.5 border border-transparent rounded-lg shadow-sm text-sm font-semibold text-white bg-indigo-600 hover:bg-indigo-700 disabled:opacity-50 transition-colors"
          >
            <Sparkles className="w-4 h-4 mr-2" />
            {starting ? '起動中...' : isJobRunning ? '推論実行中...' : 'LLM推論ジョブを開始'}
          </button>
        </div>
      </div>
    </div>
  );
};
