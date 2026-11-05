import React, { useState, useEffect } from 'react';
import { ClusterItem } from '../types/api';
import { api } from '../api/client';
import { RuleImpactDrawer } from '../components/RuleImpactDrawer';
import { 
  FolderTree, 
  Tag, 
  Save, 
  Play, 
  Search, 
  Eye, 
  CheckSquare, 
  Square, 
  AlertCircle,
  ChevronRight,
  ChevronDown,
  RefreshCw,
  BookOpen
} from 'lucide-react';

interface AboutFilterViewProps {
  workspaceId: string;
}

export const AboutFilterView: React.FC<AboutFilterViewProps> = ({ workspaceId }) => {
  const [activeTab, setActiveTab] = useState<'ndc' | 'authority' | 'all'>('ndc');
  const [clusters, setClusters] = useState<ClusterItem[]>([]);
  const [rules, setRules] = useState<Record<string, string>>({});
  const [originalRules, setOriginalRules] = useState<Record<string, string>>({});
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [applying, setApplying] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState('');

  // アコーディオン開閉状態
  const [expandedNodes, setExpandedNodes] = useState<Record<string, boolean>>({});

  // 典拠タイプの絞り込み
  const [authorityFilter, setAuthorityFilter] = useState<'ALL' | 'TOPICAL' | 'PERSON' | 'CORPORATE'>('ALL');

  // インパクトドロワー用
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [drawerRuleValue, setDrawerRuleValue] = useState('');
  const [drawerRuleLabel, setDrawerRuleLabel] = useState('');

  const loadData = async () => {
    try {
      setLoading(true);
      setError(null);
      const [rulesRes, clustersRes] = await Promise.all([
        api.getAboutRules(workspaceId),
        api.getAboutClusters(workspaceId)
      ]);
      setRules(rulesRes || {});
      setOriginalRules(rulesRes || {});
      setClusters(clustersRes || []);
    } catch (err: any) {
      setError(err.message || '主題キーワードの取得に失敗しました');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadData();
  }, [workspaceId]);

  const hasChanges = JSON.stringify(rules) !== JSON.stringify(originalRules);

  const handleToggle = (key: string) => {
    setRules(prev => {
      const next = { ...prev };
      if (next[key] === '除外') {
        delete next[key];
      } else {
        next[key] = '除外';
      }
      return next;
    });
  };

  const handleToggleCluster = (cluster: ClusterItem) => {
    const isExcluded = cluster.keywords.every(k => rules[k] === '除外');
    setRules(prev => {
      const next = { ...prev };
      if (isExcluded) {
        cluster.keywords.forEach(k => delete next[k]);
      } else {
        cluster.keywords.forEach(k => { next[k] = '除外'; });
      }
      return next;
    });
  };

  const handleSave = async () => {
    try {
      setSaving(true);
      setError(null);
      await api.saveAboutRules(workspaceId, rules);
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
        await api.saveAboutRules(workspaceId, rules);
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

  const toggleNode = (id: string) => {
    setExpandedNodes(prev => ({
      ...prev,
      [id]: !prev[id]
    }));
  };

  const openImpactDrawer = (keyword: string, label?: string) => {
    setDrawerRuleValue(keyword);
    setDrawerRuleLabel(label || keyword);
    setDrawerOpen(true);
  };

  // NDCクラスタと典拠クラスタの分離
  const ndcClusters = clusters.filter(c => c.category.startsWith('NDC'));
  const authorityClusters = clusters.filter(c => {
    if (c.category.startsWith('NDC')) return false;
    if (authorityFilter === 'ALL') return true;
    if (authorityFilter === 'TOPICAL') return c.category.includes('TOPICAL');
    if (authorityFilter === 'PERSON') return c.category.includes('PERSON');
    if (authorityFilter === 'CORPORATE') return c.category.includes('CORPORATE');
    return true;
  });

  const filteredClusters = clusters.filter(c => 
    c.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
    (c.resolved_label && c.resolved_label.toLowerCase().includes(searchQuery.toLowerCase())) ||
    c.keywords.some(k => k.toLowerCase().includes(searchQuery.toLowerCase()))
  );

  return (
    <div className="space-y-6">
      {/* 画面ヘッダー */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <div className="flex items-center space-x-2 text-sm text-slate-500 mb-1">
            <span className="font-semibold text-indigo-600">Step 2-B</span>
            <span>•</span>
            <span>ルールベース・フィルタリング</span>
          </div>
          <h1 className="text-2xl font-bold text-slate-800">主題・NDC分類（schema:about）除外</h1>
          <p className="text-sm text-slate-600 mt-1">
            Web NDL Authorities SPARQLと連携し、NDC階層ツリーおよびNDL典拠キーワードを分析・除外します。
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
          onClick={() => setActiveTab('ndc')}
          className={`py-3 px-4 text-sm font-medium border-b-2 flex items-center space-x-2 ${
            activeTab === 'ndc'
              ? 'border-indigo-600 text-indigo-600'
              : 'border-transparent text-slate-500 hover:text-slate-700 hover:border-slate-300'
          }`}
        >
          <FolderTree className="w-4 h-4" />
          <span>NDC 3段階階層ツリー</span>
          <span className="ml-1.5 px-2 py-0.5 text-xs bg-slate-100 text-slate-600 rounded-full">
            {ndcClusters.length}
          </span>
        </button>

        <button
          onClick={() => setActiveTab('authority')}
          className={`py-3 px-4 text-sm font-medium border-b-2 flex items-center space-x-2 ${
            activeTab === 'authority'
              ? 'border-indigo-600 text-indigo-600'
              : 'border-transparent text-slate-500 hover:text-slate-700 hover:border-slate-300'
          }`}
        >
          <BookOpen className="w-4 h-4" />
          <span>NDL典拠キーワード</span>
          <span className="ml-1.5 px-2 py-0.5 text-xs bg-slate-100 text-slate-600 rounded-full">
            {authorityClusters.length}
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
          <Tag className="w-4 h-4" />
          <span>全クラスタ・検索</span>
          <span className="ml-1.5 px-2 py-0.5 text-xs bg-slate-100 text-slate-600 rounded-full">
            {clusters.length}
          </span>
        </button>
      </div>

      {/* タブコンテンツ */}
      {loading ? (
        <div className="py-20 text-center text-slate-400 bg-white rounded-xl border border-slate-200">
          <div className="inline-block animate-spin rounded-full h-8 w-8 border-4 border-indigo-500 border-t-transparent mb-2"></div>
          <p>NDC階層および典拠データを分析中...</p>
        </div>
      ) : (
        <>
          {/* 1. NDC階層ツリータブ */}
          {activeTab === 'ndc' && (
            <div className="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
              <div className="p-4 bg-slate-50 border-b border-slate-100 flex items-center justify-between text-xs text-slate-600">
                <span>
                  ※ NDC記号のチェックを入れると、該当分類に属するキーワードが一括除外されます。
                </span>
                <span className="text-slate-400">
                  典拠参照: Web NDL Authorities SPARQL
                </span>
              </div>
              <div className="divide-y divide-slate-100 max-h-[700px] overflow-y-auto">
                {ndcClusters.length === 0 ? (
                  <div className="p-8 text-center text-slate-400">
                    NDC分類データがありません
                  </div>
                ) : (
                  ndcClusters.map(cluster => {
                    const isExpanded = !!expandedNodes[cluster.cluster_id];
                    const isExcluded = cluster.keywords.length > 0 && cluster.keywords.every(k => rules[k] === '除外');
                    const hasSub = cluster.sub_clusters && cluster.sub_clusters.length > 0;

                    return (
                      <div key={cluster.cluster_id} className="border-b border-slate-100 last:border-b-0">
                        <div className={`flex items-center justify-between py-2.5 px-4 hover:bg-slate-50 transition-colors ${
                          isExcluded ? 'bg-red-50/40' : ''
                        }`}>
                          <div className="flex items-center space-x-3 flex-1 min-w-0">
                            {hasSub ? (
                              <button 
                                type="button"
                                onClick={() => toggleNode(cluster.cluster_id)}
                                className="text-slate-400 hover:text-slate-600 p-0.5 rounded"
                              >
                                {isExpanded ? <ChevronDown className="w-4 h-4" /> : <ChevronRight className="w-4 h-4" />}
                              </button>
                            ) : (
                              <span className="w-5" />
                            )}

                            <button
                              type="button"
                              onClick={() => handleToggleCluster(cluster)}
                              className="text-slate-400 hover:text-indigo-600 focus:outline-none"
                            >
                              {isExcluded ? (
                                <CheckSquare className="w-4 h-4 text-red-500" />
                              ) : (
                                <Square className="w-4 h-4 text-slate-300" />
                              )}
                            </button>

                            <span className="font-mono text-xs font-semibold px-2 py-0.5 bg-slate-100 text-slate-700 rounded">
                              {cluster.name}
                            </span>

                            <span className={`text-sm truncate ${isExcluded ? 'text-red-700 line-through' : 'text-slate-800'}`}>
                              {cluster.resolved_label || '（名称未設定）'}
                            </span>
                          </div>

                          <div className="flex items-center space-x-4">
                            <span className="text-xs font-medium text-slate-500">
                              {cluster.total_count.toLocaleString()} 件
                            </span>
                            <button
                              type="button"
                              onClick={() => openImpactDrawer(cluster.name, `${cluster.name} (${cluster.resolved_label || ''})`)}
                              className="p-1 text-slate-400 hover:text-indigo-600 rounded"
                              title="影響レコードを確認"
                            >
                              <Eye className="w-4 h-4" />
                            </button>
                          </div>
                        </div>

                        {hasSub && isExpanded && (
                          <div className="bg-slate-50/50 pl-10 pr-4 py-2 space-y-1">
                            {cluster.sub_clusters!.map(sub => {
                              const isSubExcluded = sub.keywords.every(k => rules[k] === '除外');
                              return (
                                <div key={sub.id} className="flex items-center justify-between py-1 text-xs text-slate-600">
                                  <div className="flex items-center space-x-2">
                                    <button
                                      type="button"
                                      onClick={() => {
                                        setRules(prev => {
                                          const next = { ...prev };
                                          if (isSubExcluded) {
                                            sub.keywords.forEach(k => delete next[k]);
                                          } else {
                                            sub.keywords.forEach(k => { next[k] = '除外'; });
                                          }
                                          return next;
                                        });
                                      }}
                                    >
                                      {isSubExcluded ? <CheckSquare className="w-3.5 h-3.5 text-red-500" /> : <Square className="w-3.5 h-3.5 text-slate-300" />}
                                    </button>
                                    <span className="font-mono font-medium">{sub.name}</span>
                                    <span>({sub.keywords.join(', ')})</span>
                                  </div>
                                  <span>{sub.count.toLocaleString()} 件</span>
                                </div>
                              );
                            })}
                          </div>
                        )}
                      </div>
                    );
                  })
                )}
              </div>
            </div>
          )}

          {/* 2. NDL典拠キーワードタブ */}
          {activeTab === 'authority' && (
            <div className="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
              <div className="p-4 border-b border-slate-100 flex flex-wrap items-center justify-between gap-3">
                <div className="flex items-center space-x-2">
                  <span className="text-xs text-slate-500 font-medium">種別フィルタ:</span>
                  {(['ALL', 'TOPICAL', 'PERSON', 'CORPORATE'] as const).map(f => (
                    <button
                      key={f}
                      type="button"
                      onClick={() => setAuthorityFilter(f)}
                      className={`px-2.5 py-1 text-xs rounded-full font-medium ${
                        authorityFilter === f
                          ? 'bg-indigo-600 text-white'
                          : 'bg-slate-100 text-slate-600 hover:bg-slate-200'
                      }`}
                    >
                      {f === 'ALL' ? 'すべて' : f === 'TOPICAL' ? '普通件名' : f === 'PERSON' ? '人名' : '団体名'}
                    </button>
                  ))}
                </div>
                <div className="text-xs text-slate-500">
                  該当: {authorityClusters.length} 件
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
                        典拠ラベル / クラスタ名
                      </th>
                      <th scope="col" className="px-4 py-3 text-left text-xs font-semibold text-slate-500 w-32">
                        カテゴリ
                      </th>
                      <th scope="col" className="px-4 py-3 text-right text-xs font-semibold text-slate-500 w-32">
                        件数
                      </th>
                      <th scope="col" className="px-4 py-3 text-center text-xs font-semibold text-slate-500 w-28">
                        影響確認
                      </th>
                    </tr>
                  </thead>
                  <tbody className="bg-white divide-y divide-slate-100">
                    {authorityClusters.map(c => {
                      const isExcluded = c.keywords.length > 0 && c.keywords.every(k => rules[k] === '除外');
                      return (
                        <tr key={c.cluster_id} className={`hover:bg-slate-50 ${isExcluded ? 'bg-red-50/40' : ''}`}>
                          <td className="px-4 py-3 text-center">
                            <button
                              type="button"
                              onClick={() => handleToggleCluster(c)}
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
                            <span className={`text-sm font-medium ${isExcluded ? 'text-red-700 line-through' : 'text-slate-800'}`}>
                              {c.name}
                            </span>
                            {c.resolved_label && (
                              <span className="text-xs text-slate-400 ml-2">({c.resolved_label})</span>
                            )}
                          </td>
                          <td className="px-4 py-3">
                            <span className="px-2 py-0.5 text-xs rounded-full bg-slate-100 text-slate-600 font-medium">
                              {c.category}
                            </span>
                          </td>
                          <td className="px-4 py-3 text-right font-semibold text-sm text-slate-700">
                            {c.total_count.toLocaleString()}
                          </td>
                          <td className="px-4 py-3 text-center">
                            <button
                              type="button"
                              onClick={() => openImpactDrawer(c.name)}
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

          {/* 3. 全クラスタ・検索タブ */}
          {activeTab === 'all' && (
            <div className="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
              <div className="p-4 border-b border-slate-100 flex items-center justify-between gap-3">
                <div className="relative w-72">
                  <Search className="w-4 h-4 text-slate-400 absolute left-3 top-1/2 -translate-y-1/2" />
                  <input
                    type="text"
                    placeholder="キーワードまたはラベルを検索..."
                    value={searchQuery}
                    onChange={(e) => setSearchQuery(e.target.value)}
                    className="w-full pl-9 pr-3 py-1.5 text-sm border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-indigo-500"
                  />
                </div>
                <div className="text-xs text-slate-500">
                  表示件数: {filteredClusters.length} / {clusters.length} 件
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
                        クラスタ / キーワード
                      </th>
                      <th scope="col" className="px-4 py-3 text-left text-xs font-semibold text-slate-500 w-32">
                        カテゴリ
                      </th>
                      <th scope="col" className="px-4 py-3 text-right text-xs font-semibold text-slate-500 w-32">
                        件数
                      </th>
                      <th scope="col" className="px-4 py-3 text-center text-xs font-semibold text-slate-500 w-28">
                        影響確認
                      </th>
                    </tr>
                  </thead>
                  <tbody className="bg-white divide-y divide-slate-100">
                    {filteredClusters.map(c => {
                      const isExcluded = c.keywords.length > 0 && c.keywords.every(k => rules[k] === '除外');
                      return (
                        <tr key={c.cluster_id} className={`hover:bg-slate-50 ${isExcluded ? 'bg-red-50/40' : ''}`}>
                          <td className="px-4 py-3 text-center">
                            <button
                              type="button"
                              onClick={() => handleToggleCluster(c)}
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
                            <div className="flex items-center space-x-2">
                              <span className={`text-sm font-medium ${isExcluded ? 'text-red-700 line-through' : 'text-slate-800'}`}>
                                {c.name}
                              </span>
                              {c.resolved_label && (
                                <span className="text-xs text-slate-500">
                                  ({c.resolved_label})
                                </span>
                              )}
                            </div>
                          </td>
                          <td className="px-4 py-3">
                            <span className="px-2 py-0.5 text-xs rounded-full bg-slate-100 text-slate-600">
                              {c.category}
                            </span>
                          </td>
                          <td className="px-4 py-3 text-right font-semibold text-sm text-slate-700">
                            {c.total_count.toLocaleString()}
                          </td>
                          <td className="px-4 py-3 text-center">
                            <button
                              type="button"
                              onClick={() => openImpactDrawer(c.name, c.resolved_label ? `${c.name} (${c.resolved_label})` : c.name)}
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
        ruleType="about"
        ruleValue={drawerRuleValue}
        ruleLabel={drawerRuleLabel}
      />
    </div>
  );
};
