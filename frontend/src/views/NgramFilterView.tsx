import React, { useState, useEffect } from 'react';
import { SuffixClusterItem } from '../types/api';
import { api } from '../api/client';
import { RuleImpactDrawer } from '../components/RuleImpactDrawer';
import { 
  FileText, 
  Layers, 
  Save, 
  Play, 
  Search, 
  Eye, 
  CheckSquare, 
  Square, 
  AlertCircle,
  Hash,
  ChevronRight,
  ChevronDown,
  RefreshCw
} from 'lucide-react';

interface NgramFilterViewProps {
  workspaceId: string;
}

export const NgramFilterView: React.FC<NgramFilterViewProps> = ({ workspaceId }) => {
  const [activeTab, setActiveTab] = useState<'suffix' | 'all'>('suffix');
  const [rankings, setRankings] = useState<Record<string, { word: string; count: number }[]>>({});
  const [suffixClusters, setSuffixClusters] = useState<SuffixClusterItem[]>([]);
  const [rules, setRules] = useState<Record<string, string>>({});
  const [originalRules, setOriginalRules] = useState<Record<string, string>>({});
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [applying, setApplying] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedNgramLen, setSelectedNgramLen] = useState<string>('2');

  // クラスタの開閉状態
  const [expandedClusters, setExpandedClusters] = useState<Record<string, boolean>>({});

  // インパクトドロワー用
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [drawerRuleValue, setDrawerRuleValue] = useState('');
  const [drawerRuleLabel, setDrawerRuleLabel] = useState('');

  const loadData = async () => {
    try {
      setLoading(true);
      setError(null);
      const [rulesRes, rankingsRes] = await Promise.all([
        api.getNgramRules(workspaceId),
        api.getNgramRankings(workspaceId)
      ]);
      setRules(rulesRes || {});
      setOriginalRules(rulesRes || {});
      setRankings(rankingsRes.rankings || {});
      setSuffixClusters(rankingsRes.suffix_clusters || []);
    } catch (err: any) {
      setError(err.message || 'N-gram情報の取得に失敗しました');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadData();
  }, [workspaceId]);

  const hasChanges = JSON.stringify(rules) !== JSON.stringify(originalRules);

  const handleToggle = (term: string) => {
    setRules(prev => {
      const next = { ...prev };
      if (next[term] === '除外') {
        delete next[term];
      } else {
        next[term] = '除外';
      }
      return next;
    });
  };

  const handleToggleCluster = (cluster: SuffixClusterItem) => {
    const isExcluded = cluster.items.every(i => rules[i.word] === '除外');
    setRules(prev => {
      const next = { ...prev };
      if (isExcluded) {
        cluster.items.forEach(i => delete next[i.word]);
      } else {
        cluster.items.forEach(i => { next[i.word] = '除外'; });
      }
      return next;
    });
  };

  const handleSave = async () => {
    try {
      setSaving(true);
      setError(null);
      await api.saveNgramRules(workspaceId, rules);
      setOriginalRules(rules);
    } catch (err: any) {
      setError(err.message || 'ルールの保存に失敗しました');
    } finally {
      setSaving(false);
    }
  };

  const handleApplyRules = async () => {
    try {
      if (hasChanges) {
        await api.saveNgramRules(workspaceId, rules);
        setOriginalRules(rules);
      }
      setApplying(true);
      setError(null);
      await api.applyRules(workspaceId);
    } catch (err: any) {
      setError(err.message || 'ルールの適用ジョブ開始に失敗しました');
    } finally {
      setApplying(false);
    }
  };

  const toggleClusterOpen = (id: string) => {
    setExpandedClusters(prev => ({
      ...prev,
      [id]: !prev[id]
    }));
  };

  const openImpactDrawer = (ngram: string) => {
    setDrawerRuleValue(ngram);
    setDrawerRuleLabel(`タイトル含む: "${ngram}"`);
    setDrawerOpen(true);
  };

  const currentRankings = (rankings[selectedNgramLen] || []).filter(item =>
    !searchQuery || item.word.toLowerCase().includes(searchQuery.toLowerCase())
  );

  return (
    <div className="space-y-6">
      {/* 画面ヘッダー */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <div className="flex items-center space-x-2 text-sm text-slate-500 mb-1">
            <span className="font-semibold text-indigo-600">Step 2-C</span>
            <span>•</span>
            <span>ルールベース・フィルタリング</span>
          </div>
          <h1 className="text-2xl font-bold text-slate-800">タイトルN-gram・接尾辞クラスタ除外</h1>
          <p className="text-sm text-slate-600 mt-1">
            タイトルに含まれる頻出語句および「〜譜」「〜集」「〜史」などの接尾辞パターンをクラスタリングし、対象外の文書類型を除外します。
          </p>
        </div>

        <div className="flex items-center space-x-3">
          <button
            onClick={loadData}
            disabled={loading}
            className="inline-flex items-center px-3 py-2 border border-slate-300 rounded-md shadow-sm text-sm font-medium text-slate-700 bg-white hover:bg-slate-50 disabled:opacity-50"
          >
            <RefreshCw className={`w-4 h-4 mr-2 ${loading ? 'animate-spin' : ''}`} />
            再読み込み
          </button>
          <button
            onClick={handleSave}
            disabled={!hasChanges || saving}
            className={`inline-flex items-center px-4 py-2 border rounded-md shadow-sm text-sm font-medium ${
              hasChanges 
                ? 'border-indigo-600 text-indigo-600 bg-white hover:bg-indigo-50' 
                : 'border-slate-300 text-slate-400 bg-slate-50 cursor-not-allowed'
            }`}
          >
            <Save className="w-4 h-4 mr-2" />
            {saving ? '保存中...' : 'ルールを保存'}
          </button>
          <button
            onClick={handleApplyRules}
            disabled={applying}
            className="inline-flex items-center px-4 py-2 border border-transparent rounded-md shadow-sm text-sm font-medium text-white bg-indigo-600 hover:bg-indigo-700 disabled:opacity-50"
          >
            <Play className="w-4 h-4 mr-2" />
            {applying ? '適用開始...' : '全ルールを一括適用'}
          </button>
        </div>
      </div>

      {error && (
        <div className="p-4 bg-red-50 border border-red-200 rounded-lg flex items-center space-x-2 text-red-700 text-sm">
          <AlertCircle className="w-5 h-5 flex-shrink-0" />
          <span>{error}</span>
        </div>
      )}

      {/* タブナビゲーション */}
      <div className="flex border-b border-slate-200">
        <button
          onClick={() => setActiveTab('suffix')}
          className={`py-3 px-4 text-sm font-medium border-b-2 flex items-center space-x-2 ${
            activeTab === 'suffix'
              ? 'border-indigo-600 text-indigo-600'
              : 'border-transparent text-slate-500 hover:text-slate-700 hover:border-slate-300'
          }`}
        >
          <Layers className="w-4 h-4" />
          <span>接尾辞クラスタリング</span>
          <span className="ml-1.5 px-2 py-0.5 text-xs bg-slate-100 text-slate-600 rounded-full">
            {suffixClusters.length} グループ
          </span>
        </button>

        <button
          onClick={() => setActiveTab('all')}
          className={`py-3 px-4 text-sm font-medium border-b-2 flex items-center space-x-2 ${
            activeTab === 'all'
              ? 'border-indigo-600 text-indigo-600'
              : 'border-transparent text-slate-500 hover:text-slate-700 hover:border-slate-300'
          }`}
        >
          <Hash className="w-4 h-4" />
          <span>頻出N-gram全件</span>
          <span className="ml-1.5 px-2 py-0.5 text-xs bg-slate-100 text-slate-600 rounded-full">
            {Object.values(rankings).reduce((acc, curr) => acc + curr.length, 0)} 語句
          </span>
        </button>
      </div>

      {/* タブコンテンツ */}
      {loading ? (
        <div className="py-20 text-center text-slate-400 bg-white rounded-xl border border-slate-200">
          <div className="inline-block animate-spin rounded-full h-8 w-8 border-4 border-indigo-500 border-t-transparent mb-2"></div>
          <p>N-gramインデックスを分析中...</p>
        </div>
      ) : (
        <>
          {/* 1. 接尾辞クラスタリングタブ */}
          {activeTab === 'suffix' && (
            <div className="space-y-4">
              <div className="p-4 bg-indigo-50 border border-indigo-100 rounded-xl text-xs text-indigo-800">
                💡 <b>タイトル末尾の接尾辞パターン（〜譜、〜集、〜録、〜図等）によるクラスタリング:</b>
                <br />
                特定の文献類型（目録、報告書、会報等）を一括選択して除外できます。
              </div>

              {suffixClusters.length === 0 ? (
                <div className="bg-white p-12 text-center text-slate-400 rounded-xl border border-slate-200">
                  接尾辞クラスタが見つかりませんでした
                </div>
              ) : (
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  {suffixClusters.map(cluster => {
                    const isExpanded = !!expandedClusters[cluster.cluster_id];
                    const allSelected = cluster.items.length > 0 && cluster.items.every(item => rules[item.word] === '除外');
                    const someSelected = !allSelected && cluster.items.some(item => rules[item.word] === '除外');

                    return (
                      <div 
                        key={cluster.cluster_id}
                        className="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden flex flex-col"
                      >
                        {/* クラスタヘッダー */}
                        <div className="p-4 bg-slate-50 border-b border-slate-100 flex items-center justify-between">
                          <div className="flex items-center space-x-2">
                            <button
                              type="button"
                              onClick={() => handleToggleCluster(cluster)}
                              className="text-slate-400 hover:text-indigo-600 focus:outline-none"
                            >
                              {allSelected ? (
                                <CheckSquare className="w-5 h-5 text-red-500" />
                              ) : someSelected ? (
                                <div className="w-5 h-5 bg-red-100 border border-red-500 rounded flex items-center justify-center">
                                  <div className="w-2.5 h-0.5 bg-red-600 rounded" />
                                </div>
                              ) : (
                                <Square className="w-5 h-5 text-slate-300" />
                              )}
                            </button>
                            <span className="font-bold text-slate-800">
                              {cluster.name}
                            </span>
                            <span className="text-xs px-2 py-0.5 bg-slate-200 text-slate-700 rounded-full font-medium">
                              {cluster.items.length} 語句
                            </span>
                          </div>

                          <div className="flex items-center space-x-2">
                            <span className="text-xs font-semibold text-slate-600">
                              計 {cluster.total_count.toLocaleString()} 件
                            </span>
                            <button
                              type="button"
                              onClick={() => toggleClusterOpen(cluster.cluster_id)}
                              className="p-1 text-slate-400 hover:text-slate-600 rounded"
                            >
                              {isExpanded ? <ChevronDown className="w-4 h-4" /> : <ChevronRight className="w-4 h-4" />}
                            </button>
                          </div>
                        </div>

                        {/* クラスタ内語句リスト */}
                        <div className="p-3 divide-y divide-slate-100 flex-1 max-h-56 overflow-y-auto">
                          {cluster.items.map(item => {
                            const isExcluded = rules[item.word] === '除外';
                            return (
                              <div 
                                key={item.word}
                                className={`flex items-center justify-between py-1.5 px-2 hover:bg-slate-50 rounded text-xs ${
                                  isExcluded ? 'bg-red-50/50' : ''
                                }`}
                              >
                                <div className="flex items-center space-x-2">
                                  <button
                                    type="button"
                                    onClick={() => handleToggle(item.word)}
                                    className="text-slate-400 hover:text-indigo-600"
                                  >
                                    {isExcluded ? (
                                      <CheckSquare className="w-4 h-4 text-red-500" />
                                    ) : (
                                      <Square className="w-4 h-4 text-slate-300" />
                                    )}
                                  </button>
                                  <span className={`font-mono ${isExcluded ? 'text-red-700 line-through' : 'text-slate-800'}`}>
                                    {item.word}
                                  </span>
                                </div>

                                <div className="flex items-center space-x-2">
                                  <span className="text-slate-500 font-medium">
                                    {item.count.toLocaleString()} 件
                                  </span>
                                  <button
                                    type="button"
                                    onClick={() => openImpactDrawer(item.word)}
                                    className="p-0.5 text-slate-400 hover:text-indigo-600"
                                    title="影響レコードを確認"
                                  >
                                    <Eye className="w-3.5 h-3.5" />
                                  </button>
                                </div>
                              </div>
                            );
                          })}
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          )}

          {/* 2. 頻出N-gram全件タブ */}
          {activeTab === 'all' && (
            <div className="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
              <div className="p-4 border-b border-slate-100 flex flex-wrap items-center justify-between gap-3">
                <div className="flex items-center space-x-3">
                  <div className="relative w-64">
                    <Search className="w-4 h-4 text-slate-400 absolute left-3 top-1/2 -translate-y-1/2" />
                    <input
                      type="text"
                      placeholder="語句を検索..."
                      value={searchQuery}
                      onChange={(e) => setSearchQuery(e.target.value)}
                      className="w-full pl-9 pr-3 py-1.5 text-sm border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-indigo-500"
                    />
                  </div>

                  <div className="flex items-center space-x-1">
                    <span className="text-xs text-slate-500 mr-1">文字長:</span>
                    {Object.keys(rankings).map(len => (
                      <button
                        key={len}
                        type="button"
                        onClick={() => setSelectedNgramLen(len)}
                        className={`px-2 py-1 text-xs rounded font-medium ${
                          selectedNgramLen === len
                            ? 'bg-indigo-600 text-white'
                            : 'bg-slate-100 text-slate-600 hover:bg-slate-200'
                        }`}
                      >
                        {len}-gram
                      </button>
                    ))}
                  </div>
                </div>

                <div className="text-xs text-slate-500">
                  表示件数: {currentRankings.length} 件
                </div>
              </div>

              <div className="overflow-x-auto max-h-[600px] overflow-y-auto">
                <table className="min-w-full divide-y divide-slate-200">
                  <thead className="bg-slate-50 sticky top-0 z-10">
                    <tr>
                      <th scope="col" className="px-4 py-3 text-left text-xs font-semibold text-slate-500 w-16">
                        除外
                      </th>
                      <th scope="col" className="px-4 py-3 text-left text-xs font-semibold text-slate-500">
                        N-gram 語句
                      </th>
                      <th scope="col" className="px-4 py-3 text-right text-xs font-semibold text-slate-500 w-32">
                        出現件数
                      </th>
                      <th scope="col" className="px-4 py-3 text-center text-xs font-semibold text-slate-500 w-28">
                        影響確認
                      </th>
                    </tr>
                  </thead>
                  <tbody className="bg-white divide-y divide-slate-100">
                    {currentRankings.map(item => {
                      const isExcluded = rules[item.word] === '除外';
                      return (
                        <tr key={item.word} className={`hover:bg-slate-50 ${isExcluded ? 'bg-red-50/40' : ''}`}>
                          <td className="px-4 py-3 text-center">
                            <button
                              type="button"
                              onClick={() => handleToggle(item.word)}
                              className="text-slate-400 hover:text-indigo-600"
                            >
                              {isExcluded ? (
                                <CheckSquare className="w-5 h-5 text-red-500" />
                              ) : (
                                <Square className="w-5 h-5 text-slate-300" />
                              )}
                            </button>
                          </td>
                          <td className="px-4 py-3">
                            <span className={`text-sm font-medium font-mono ${isExcluded ? 'text-red-700 line-through' : 'text-slate-800'}`}>
                              {item.word}
                            </span>
                          </td>
                          <td className="px-4 py-3 text-right font-semibold text-sm text-slate-700">
                            {item.count.toLocaleString()}
                          </td>
                          <td className="px-4 py-3 text-center">
                            <button
                              type="button"
                              onClick={() => openImpactDrawer(item.word)}
                              className="inline-flex items-center px-2 py-1 text-xs font-medium text-slate-600 bg-slate-100 hover:bg-slate-200 rounded"
                            >
                              <Eye className="w-3.5 h-3.5 mr-1" />
                              確認
                            </button>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </>
      )}

      {/* 影響レコードドロワー */}
      <RuleImpactDrawer
        isOpen={drawerOpen}
        onClose={() => setDrawerOpen(false)}
        workspaceId={workspaceId}
        ruleType="ngram"
        ruleValue={drawerRuleValue}
        ruleLabel={drawerRuleLabel}
      />
    </div>
  );
};
