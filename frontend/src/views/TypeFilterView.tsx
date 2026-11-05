import React, { useState, useEffect } from 'react';
import { TypeStatsItem } from '../types/api';
import { api } from '../api/client';
import { RuleImpactDrawer } from '../components/RuleImpactDrawer';
import { 
  Filter, 
  Save, 
  Play, 
  Search, 
  Eye, 
  CheckSquare, 
  Square, 
  AlertCircle,
  HelpCircle,
  Layers
} from 'lucide-react';

interface TypeFilterViewProps {
  workspaceId: string;
}

export const TypeFilterView: React.FC<TypeFilterViewProps> = ({ workspaceId }) => {
  const [stats, setStats] = useState<TypeStatsItem[]>([]);
  const [excludedTypes, setExcludedTypes] = useState<string[]>([]);
  const [originalExcluded, setOriginalExcluded] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [applying, setApplying] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState('');

  // インパクトドロワー用
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [drawerRuleValue, setDrawerRuleValue] = useState('');
  const [drawerRuleLabel, setDrawerRuleLabel] = useState('');

  const loadData = async () => {
    try {
      setLoading(true);
      setError(null);
      const res = await api.getTypeRules(workspaceId);
      setStats(res.stats || []);
      setExcludedTypes(res.rules?.NG || []);
      setOriginalExcluded(res.rules?.NG || []);
    } catch (err: any) {
      setError(err.message || 'データ種別の取得に失敗しました');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadData();
  }, [workspaceId]);

  const hasChanges = JSON.stringify(excludedTypes.slice().sort()) !== JSON.stringify(originalExcluded.slice().sort());

  const handleToggle = (uri: string) => {
    if (excludedTypes.includes(uri)) {
      setExcludedTypes(excludedTypes.filter(u => u !== uri));
    } else {
      setExcludedTypes([...excludedTypes, uri]);
    }
  };

  const handleSave = async () => {
    try {
      setSaving(true);
      setError(null);
      await api.saveTypeRules(workspaceId, excludedTypes, []);
      setOriginalExcluded(excludedTypes);
    } catch (err: any) {
      setError(err.message || 'ルールの保存に失敗しました');
    } finally {
      setSaving(false);
    }
  };

  const handleApplyRules = async () => {
    try {
      if (hasChanges) {
        await api.saveTypeRules(workspaceId, excludedTypes, []);
        setOriginalExcluded(excludedTypes);
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

  const openImpactDrawer = (item: TypeStatsItem) => {
    setDrawerRuleValue(item.type_uri);
    setDrawerRuleLabel(item.short_label || item.type_uri);
    setDrawerOpen(true);
  };

  const filteredStats = stats.filter(s => 
    (s.short_label && s.short_label.toLowerCase().includes(searchQuery.toLowerCase())) ||
    s.type_uri.toLowerCase().includes(searchQuery.toLowerCase())
  );

  const totalRecords = stats.reduce((acc, curr) => acc + curr.count, 0);
  const totalExcludedCount = stats
    .filter(s => excludedTypes.includes(s.type_uri))
    .reduce((acc, curr) => acc + curr.count, 0);

  return (
    <div className="space-y-6">
      {/* 画面ヘッダー */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <div className="flex items-center space-x-2 text-sm text-slate-500 mb-1">
            <span className="font-semibold text-indigo-600">Step 2-A</span>
            <span>•</span>
            <span>ルールベース・フィルタリング</span>
          </div>
          <h1 className="text-2xl font-bold text-slate-800">データ種別（rdf:type）除外</h1>
          <p className="text-sm text-slate-600 mt-1">
            メタデータに付与されているリソース種別を分析し、対象外の種別を一括除外ルールとして設定します。
          </p>
        </div>

        <div className="flex items-center space-x-3">
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

      {/* サマリーカード */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div className="bg-white p-4 rounded-xl border border-slate-200 shadow-sm flex items-center space-x-3">
          <div className="p-3 bg-blue-50 text-blue-600 rounded-lg">
            <Layers className="w-6 h-6" />
          </div>
          <div>
            <div className="text-xs text-slate-500 font-medium">検出された種別数</div>
            <div className="text-xl font-bold text-slate-800">{stats.length.toLocaleString()} 種別</div>
          </div>
        </div>
        <div className="bg-white p-4 rounded-xl border border-slate-200 shadow-sm flex items-center space-x-3">
          <div className="p-3 bg-red-50 text-red-600 rounded-lg">
            <Filter className="w-6 h-6" />
          </div>
          <div>
            <div className="text-xs text-slate-500 font-medium">除外設定中の種別</div>
            <div className="text-xl font-bold text-red-600">
              {excludedTypes.length} 種別
              <span className="text-xs text-slate-400 ml-2 font-normal">
                (対象 {totalExcludedCount.toLocaleString()} 件)
              </span>
            </div>
          </div>
        </div>
        <div className="bg-white p-4 rounded-xl border border-slate-200 shadow-sm flex items-center space-x-3">
          <div className="p-3 bg-slate-50 text-slate-600 rounded-lg">
            <HelpCircle className="w-6 h-6" />
          </div>
          <div>
            <div className="text-xs text-slate-500 font-medium">除外後の推定残存比率</div>
            <div className="text-xl font-bold text-slate-800">
              {totalRecords > 0 
                ? `${Math.round(((totalRecords - totalExcludedCount) / totalRecords) * 100)}%` 
                : '0%'}
              <span className="text-xs text-slate-400 ml-2 font-normal">
                ({(totalRecords - totalExcludedCount).toLocaleString()} / {totalRecords.toLocaleString()} 件)
              </span>
            </div>
          </div>
        </div>
      </div>

      {/* メインテーブル領域 */}
      <div className="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
        {/* テーブルツールバー */}
        <div className="p-4 border-b border-slate-100 flex flex-col sm:flex-row items-center justify-between gap-3">
          <div className="relative w-full sm:w-72">
            <Search className="w-4 h-4 text-slate-400 absolute left-3 top-1/2 -translate-y-1/2" />
            <input
              type="text"
              placeholder="種別ラベルまたはURIを検索..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="w-full pl-9 pr-3 py-1.5 text-sm border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-indigo-500"
            />
          </div>
          <div className="flex items-center space-x-2 text-xs text-slate-500">
            <span>表示件数: {filteredStats.length} / {stats.length} 件</span>
          </div>
        </div>

        {/* テーブル本体 */}
        {loading ? (
          <div className="py-20 text-center text-slate-400">
            <div className="inline-block animate-spin rounded-full h-8 w-8 border-4 border-indigo-500 border-t-transparent mb-2"></div>
            <p>種別統計を分析中...</p>
          </div>
        ) : filteredStats.length === 0 ? (
          <div className="py-16 text-center text-slate-400">
            種別データが見つかりませんでした
          </div>
        ) : (
          <div className="overflow-x-auto max-h-[600px] overflow-y-auto">
            <table className="min-w-full divide-y divide-slate-200">
              <thead className="bg-slate-50 sticky top-0 z-10">
                <tr>
                  <th scope="col" className="px-4 py-3 text-left text-xs font-semibold text-slate-500 w-16">
                    除外
                  </th>
                  <th scope="col" className="px-4 py-3 text-left text-xs font-semibold text-slate-500">
                    種別名 / URI
                  </th>
                  <th scope="col" className="px-4 py-3 text-right text-xs font-semibold text-slate-500 w-32">
                    レコード件数
                  </th>
                  <th scope="col" className="px-4 py-3 text-left text-xs font-semibold text-slate-500 w-48">
                    全体割合
                  </th>
                  <th scope="col" className="px-4 py-3 text-center text-xs font-semibold text-slate-500 w-28">
                    影響確認
                  </th>
                </tr>
              </thead>
              <tbody className="bg-white divide-y divide-slate-100">
                {filteredStats.map((item) => {
                  const isExcluded = excludedTypes.includes(item.type_uri);
                  const percentage = totalRecords > 0 ? (item.count / totalRecords) * 100 : 0;
                  return (
                    <tr 
                      key={item.type_uri}
                      className={`hover:bg-slate-50 transition-colors ${isExcluded ? 'bg-red-50/40' : ''}`}
                    >
                      <td className="px-4 py-3 whitespace-nowrap text-center">
                        <button
                          type="button"
                          onClick={() => handleToggle(item.type_uri)}
                          className="text-slate-400 hover:text-indigo-600 focus:outline-none"
                        >
                          {isExcluded ? (
                            <CheckSquare className="w-5 h-5 text-red-500" />
                          ) : (
                            <Square className="w-5 h-5 text-slate-300" />
                          )}
                        </button>
                      </td>
                      <td className="px-4 py-3">
                        <div className="flex flex-col">
                          <span className={`text-sm font-medium ${isExcluded ? 'text-red-700 line-through' : 'text-slate-900'}`}>
                            {item.short_label || item.type_uri}
                          </span>
                          <span className="text-xs text-slate-400 font-mono truncate max-w-lg">
                            {item.type_uri}
                          </span>
                          {item.sample_titles && item.sample_titles.length > 0 && (
                            <span className="text-2xs text-slate-400 truncate max-w-md mt-0.5">
                              例: {item.sample_titles.join(', ')}
                            </span>
                          )}
                        </div>
                      </td>
                      <td className="px-4 py-3 whitespace-nowrap text-right">
                        <span className="text-sm font-semibold text-slate-700">
                          {item.count.toLocaleString()}
                        </span>
                      </td>
                      <td className="px-4 py-3 whitespace-nowrap">
                        <div className="flex items-center space-x-2">
                          <div className="flex-1 bg-slate-100 rounded-full h-2 overflow-hidden">
                            <div 
                              className={`h-full rounded-full ${isExcluded ? 'bg-red-400' : 'bg-indigo-500'}`}
                              style={{ width: `${Math.min(100, percentage)}%` }}
                            />
                          </div>
                          <span className="text-xs text-slate-500 w-12 text-right">
                            {percentage.toFixed(1)}%
                          </span>
                        </div>
                      </td>
                      <td className="px-4 py-3 whitespace-nowrap text-center">
                        <button
                          type="button"
                          onClick={() => openImpactDrawer(item)}
                          className="inline-flex items-center px-2 py-1 text-xs font-medium text-slate-600 bg-slate-100 hover:bg-slate-200 hover:text-indigo-600 rounded transition-colors"
                          title="該当する全レコードおよびOK衝突警告を確認"
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
        )}
      </div>

      {/* 影響レコードドロワー */}
      <RuleImpactDrawer
        isOpen={drawerOpen}
        onClose={() => setDrawerOpen(false)}
        workspaceId={workspaceId}
        ruleType="type"
        ruleValue={drawerRuleValue}
        ruleLabel={drawerRuleLabel}
      />
    </div>
  );
};
