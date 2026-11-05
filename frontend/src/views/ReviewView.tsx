import React, { useState, useEffect, useCallback, useRef } from 'react';
import { RecordItem, FacetsResponse, ReviewMetrics } from '../types/api';
import { api } from '../api/client';
import { 
  Check, 
  X, 
  Search, 
  ExternalLink, 
  Filter, 
  ChevronLeft, 
  ChevronRight, 
  Keyboard, 
  Sparkles, 
  HelpCircle,
  Image as ImageIcon,
  CheckCircle2,
  XCircle,
  MinusCircle,
  RefreshCw,
  SlidersHorizontal,
  BookmarkCheck,
  RotateCcw
} from 'lucide-react';

interface ReviewViewProps {
  workspaceId: string;
}

export const ReviewView: React.FC<ReviewViewProps> = ({ workspaceId }) => {
  const [records, setRecords] = useState<RecordItem[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(50);
  const [loading, setLoading] = useState(true);
  const [facets, setFacets] = useState<FacetsResponse | null>(null);
  const [metrics, setMetrics] = useState<ReviewMetrics | null>(null);

  // フィルター
  const [search, setSearch] = useState('');
  const [selectedProvider, setSelectedProvider] = useState<string>('');
  const [selectedHasImage, setSelectedHasImage] = useState<string>(''); // '', 'true', 'false'
  const [filterStatus, setFilterStatus] = useState<string>('すべて'); // 'すべて', '合格', '除外', '未処理'
  const [stageFilter, setStageFilter] = useState<string>('');

  // フォーカス行（キーボード操作用）
  const [selectedIndex, setSelectedIndex] = useState<number>(0);
  const [selectedRecord, setSelectedRecord] = useState<RecordItem | null>(null);

  const tableContainerRef = useRef<HTMLDivElement>(null);

  // データ取得
  const loadRecords = useCallback(async () => {
    try {
      setLoading(true);
      const res = await api.getRecords(workspaceId, {
        page,
        page_size: pageSize,
        search_query: search.trim() || undefined,
        filter_status: filterStatus,
        provider: selectedProvider || undefined,
        has_image: selectedHasImage === '' ? undefined : selectedHasImage === 'true',
        stage: stageFilter || undefined,
      });
      setRecords(res.records || []);
      setTotal(res.total || 0);
      if (res.records && res.records.length > 0) {
        setSelectedIndex(0);
        setSelectedRecord(res.records[0]);
      } else {
        setSelectedRecord(null);
      }
    } catch (err) {
      console.error('Failed to load records:', err);
    } finally {
      setLoading(false);
    }
  }, [
    workspaceId, 
    page, 
    pageSize, 
    search, 
    filterStatus, 
    selectedProvider, 
    selectedHasImage, 
    stageFilter
  ]);

  const loadFacetsAndMetrics = async () => {
    try {
      const [f, m] = await Promise.all([
        api.getFacets(workspaceId),
        api.getReviewMetrics(workspaceId)
      ]);
      setFacets(f);
      setMetrics(m);
    } catch (err) {
      console.error('Failed to load facets/metrics:', err);
    }
  };

  useEffect(() => {
    loadFacetsAndMetrics();
  }, [workspaceId]);

  useEffect(() => {
    loadRecords();
  }, [loadRecords]);

  // 手動判定更新（楽観的UI更新）
  const updateDecision = async (recordId: string, decision: '合格' | '除外' | null) => {
    // 楽観的更新
    setRecords(prev => prev.map(r => {
      if (r.id === recordId) {
        return { 
          ...r, 
          human_decision: decision, 
          status: decision || r.status,
          is_override: decision !== null 
        };
      }
      return r;
    }));
    if (selectedRecord && selectedRecord.id === recordId) {
      setSelectedRecord({ 
        ...selectedRecord, 
        human_decision: decision, 
        status: decision || selectedRecord.status,
        is_override: decision !== null 
      });
    }

    try {
      await api.updateDecision(workspaceId, recordId, decision);
      // メトリクスを非同期で更新
      api.getReviewMetrics(workspaceId).then(setMetrics).catch(() => {});
    } catch (err) {
      console.error('Failed to update decision:', err);
      // ロールバック
      loadRecords();
    }
  };

  // キーボードショートカットハンドラー
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (['INPUT', 'TEXTAREA', 'SELECT'].includes((e.target as HTMLElement).tagName)) {
        return;
      }

      if (records.length === 0) return;

      if (e.key === 'j' || e.key === 'J' || e.key === 'ArrowDown') {
        e.preventDefault();
        setSelectedIndex(prev => {
          const next = Math.min(prev + 1, records.length - 1);
          setSelectedRecord(records[next]);
          return next;
        });
      } else if (e.key === 'k' || e.key === 'K' || e.key === 'ArrowUp') {
        e.preventDefault();
        setSelectedIndex(prev => {
          const next = Math.max(prev - 1, 0);
          setSelectedRecord(records[next]);
          return next;
        });
      } else if (e.key === 'a' || e.key === 'A') {
        // 採択（合格）
        e.preventDefault();
        const current = records[selectedIndex];
        if (current) {
          updateDecision(current.id, '合格');
          // 自動で次へ
          if (selectedIndex < records.length - 1) {
            setSelectedIndex(prev => prev + 1);
            setSelectedRecord(records[selectedIndex + 1]);
          }
        }
      } else if (e.key === 'd' || e.key === 'D') {
        // 除外
        e.preventDefault();
        const current = records[selectedIndex];
        if (current) {
          updateDecision(current.id, '除外');
          // 自動で次へ
          if (selectedIndex < records.length - 1) {
            setSelectedIndex(prev => prev + 1);
            setSelectedRecord(records[selectedIndex + 1]);
          }
        }
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [records, selectedIndex, selectedRecord]);

  const totalPages = Math.ceil(total / pageSize);

  return (
    <div className="space-y-4">
      {/* 画面ヘッダー */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <div className="flex items-center space-x-2 text-sm text-slate-500 mb-1">
            <span className="font-semibold text-indigo-600">Step 4</span>
            <span>•</span>
            <span>専門家査読</span>
          </div>
          <h1 className="text-2xl font-bold text-slate-800">専門家査読ポータル</h1>
          <p className="text-sm text-slate-600 mt-1">
            キーボード操作（J/Kで移動、Aで採択、Dで除外）により、大量のメタデータを高速に検証します。
          </p>
        </div>

        {/* ショートカット操作ガイド */}
        <div className="bg-slate-100 border border-slate-200 rounded-lg p-2.5 flex items-center space-x-4 text-xs text-slate-700">
          <div className="flex items-center space-x-1 font-semibold text-indigo-700">
            <Keyboard className="w-4 h-4" />
            <span>爆速キー操作:</span>
          </div>
          <div><kbd className="px-1.5 py-0.5 bg-white border border-slate-300 rounded shadow-xs font-mono font-bold">J</kbd> 次へ</div>
          <div><kbd className="px-1.5 py-0.5 bg-white border border-slate-300 rounded shadow-xs font-mono font-bold">K</kbd> 前へ</div>
          <div><kbd className="px-1.5 py-0.5 bg-emerald-100 border border-emerald-300 text-emerald-800 rounded shadow-xs font-mono font-bold">A</kbd> 適合(合格)</div>
          <div><kbd className="px-1.5 py-0.5 bg-red-100 border border-red-300 text-red-800 rounded shadow-xs font-mono font-bold">D</kbd> 除外</div>
        </div>
      </div>

      {/* メトリクスバー */}
      {metrics && (
        <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
          <div className="bg-white p-3 rounded-lg border border-slate-200 shadow-xs">
            <span className="text-2xs text-slate-400 font-medium block">全レコード</span>
            <span className="text-lg font-bold text-slate-800">{metrics.total.toLocaleString()}</span>
          </div>
          <div className="bg-white p-3 rounded-lg border border-slate-200 shadow-xs">
            <span className="text-2xs text-emerald-600 font-medium block">合格 (採択)</span>
            <span className="text-lg font-bold text-emerald-600">{metrics.passed_cnt.toLocaleString()}</span>
          </div>
          <div className="bg-white p-3 rounded-lg border border-slate-200 shadow-xs">
            <span className="text-2xs text-red-600 font-medium block">除外</span>
            <span className="text-lg font-bold text-red-600">{metrics.reject_cnt.toLocaleString()}</span>
          </div>
          <div className="bg-white p-3 rounded-lg border border-slate-200 shadow-xs">
            <span className="text-2xs text-indigo-600 font-medium block">手動オーバーライド</span>
            <span className="text-lg font-bold text-indigo-600">{metrics.override_cnt.toLocaleString()}</span>
          </div>
          <div className="bg-white p-3 rounded-lg border border-slate-200 shadow-xs">
            <span className="text-2xs text-slate-400 font-medium block">未判定・保留</span>
            <span className="text-lg font-bold text-slate-600">{metrics.null_cnt.toLocaleString()}</span>
          </div>
        </div>
      )}

      {/* フィルターバー */}
      <div className="bg-white p-4 rounded-xl border border-slate-200 shadow-sm space-y-3">
        <div className="grid grid-cols-1 md:grid-cols-4 gap-3">
          {/* 検索入力 */}
          <div className="relative md:col-span-2">
            <Search className="w-4 h-4 text-slate-400 absolute left-3 top-1/2 -translate-y-1/2" />
            <input
              type="text"
              placeholder="タイトル、著者、分類等を検索..."
              value={search}
              onChange={(e) => { setSearch(e.target.value); setPage(1); }}
              className="w-full pl-9 pr-3 py-1.5 text-sm border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-indigo-500"
            />
          </div>

          {/* 提供者フィルター */}
          <div>
            <select
              value={selectedProvider}
              onChange={(e) => { setSelectedProvider(e.target.value); setPage(1); }}
              className="w-full py-1.5 px-3 text-sm border border-slate-300 rounded-lg bg-white focus:outline-none focus:ring-2 focus:ring-indigo-500"
            >
              <option value="">全提供機関 (Provider)</option>
              {facets?.top_providers.map(p => (
                <option key={p.name} value={p.name}>
                  {p.name} ({p.count.toLocaleString()})
                </option>
              ))}
            </select>
          </div>

          {/* 判定ステータスフィルター */}
          <div>
            <select
              value={filterStatus}
              onChange={(e) => { setFilterStatus(e.target.value); setPage(1); }}
              className="w-full py-1.5 px-3 text-sm border border-slate-300 rounded-lg bg-white focus:outline-none focus:ring-2 focus:ring-indigo-500"
            >
              <option value="すべて">ステータス: すべて</option>
              <option value="合格">合格 (採択) のみ</option>
              <option value="除外">除外 のみ</option>
              <option value="未処理">未処理・保留 のみ</option>
            </select>
          </div>
        </div>

        {/* サブフィルター */}
        <div className="flex flex-wrap items-center justify-between pt-2 border-t border-slate-100 text-xs text-slate-600 gap-2">
          <div className="flex flex-wrap items-center gap-3">
            <div className="flex items-center space-x-1">
              <span>画像:</span>
              <select
                value={selectedHasImage}
                onChange={(e) => { setSelectedHasImage(e.target.value); setPage(1); }}
                className="py-0.5 px-2 text-xs border border-slate-300 rounded bg-white"
              >
                <option value="">すべて</option>
                <option value="true">画像あり ({facets?.has_image_count.toLocaleString()})</option>
                <option value="false">画像なし ({facets?.no_image_count.toLocaleString()})</option>
              </select>
            </div>

            <div className="flex items-center space-x-1">
              <span>ステージ:</span>
              <select
                value={stageFilter}
                onChange={(e) => { setStageFilter(e.target.value); setPage(1); }}
                className="py-0.5 px-2 text-xs border border-slate-300 rounded bg-white"
              >
                <option value="">すべて</option>
                <option value="TYPE">Step 2-A: Type</option>
                <option value="RULE_ABOUT">Step 2-B: About/NDC</option>
                <option value="RULE_NGRAM">Step 2-C: N-gram</option>
                <option value="LLM">Step 3: LLM</option>
              </select>
            </div>
          </div>

          <div className="flex items-center space-x-2">
            <span className="font-semibold text-slate-700">
              ヒット: {total.toLocaleString()} 件
            </span>
          </div>
        </div>
      </div>

      {/* メイングリッド（左: 一覧テーブル、右: 詳細プレビュー） */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        {/* レコード一覧テーブル（2カラム分） */}
        <div className="lg:col-span-2 bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden flex flex-col h-[700px]">
          <div className="flex-1 overflow-y-auto" ref={tableContainerRef}>
            {loading ? (
              <div className="py-24 text-center text-slate-400">
                <div className="inline-block animate-spin rounded-full h-8 w-8 border-4 border-indigo-500 border-t-transparent mb-2"></div>
                <p>レコードを読み込み中...</p>
              </div>
            ) : records.length === 0 ? (
              <div className="py-24 text-center text-slate-400">
                条件に一致するレコードが見つかりませんでした
              </div>
            ) : (
              <table className="min-w-full divide-y divide-slate-100 text-left text-sm">
                <thead className="bg-slate-50 sticky top-0 z-10 text-xs font-semibold text-slate-500">
                  <tr>
                    <th className="px-3 py-2.5 w-12 text-center">#</th>
                    <th className="px-3 py-2.5 w-24 text-center">判定操作</th>
                    <th className="px-3 py-2.5">タイトル / 著者 / 提供館</th>
                    <th className="px-3 py-2.5 w-24 text-center">判定状態</th>
                    <th className="px-3 py-2.5 w-16 text-center">画像</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {records.map((r, idx) => {
                    const isSelected = idx === selectedIndex;
                    const isPassed = r.status === '合格';
                    return (
                      <tr
                        key={r.id}
                        onClick={() => {
                          setSelectedIndex(idx);
                          setSelectedRecord(r);
                        }}
                        className={`cursor-pointer transition-colors ${
                          isSelected ? 'bg-indigo-50/80 ring-1 ring-inset ring-indigo-500' : 'hover:bg-slate-50'
                        }`}
                      >
                        <td className="px-3 py-2 text-center text-xs text-slate-400 font-mono">
                          {(page - 1) * pageSize + idx + 1}
                        </td>
                        <td className="px-3 py-2 text-center whitespace-nowrap">
                          <div className="inline-flex items-center space-x-1">
                            <button
                              type="button"
                              onClick={(e) => { e.stopPropagation(); updateDecision(r.id, '合格'); }}
                              className={`p-1 rounded transition-colors ${
                                r.human_decision === '合格' 
                                  ? 'bg-emerald-600 text-white' 
                                  : 'text-slate-300 hover:text-emerald-600 hover:bg-emerald-50'
                              }`}
                              title="採択 (合格) [A]"
                            >
                              <Check className="w-3.5 h-3.5" />
                            </button>
                            <button
                              type="button"
                              onClick={(e) => { e.stopPropagation(); updateDecision(r.id, '除外'); }}
                              className={`p-1 rounded transition-colors ${
                                r.human_decision === '除外' 
                                  ? 'bg-red-600 text-white' 
                                  : 'text-slate-300 hover:text-red-600 hover:bg-red-50'
                              }`}
                              title="除外 [D]"
                            >
                              <X className="w-3.5 h-3.5" />
                            </button>
                            {r.is_override && (
                              <button
                                type="button"
                                onClick={(e) => { e.stopPropagation(); updateDecision(r.id, null); }}
                                className="p-1 text-slate-300 hover:text-slate-600 hover:bg-slate-100 rounded"
                                title="手動判定をリセット"
                              >
                                <RotateCcw className="w-3 h-3" />
                              </button>
                            )}
                          </div>
                        </td>
                        <td className="px-3 py-2">
                          <div className="font-medium text-slate-900 line-clamp-1 text-sm">
                            {r.title || '（無題）'}
                          </div>
                          <div className="text-xs text-slate-500 flex items-center space-x-2 mt-0.5">
                            {r.creator && <span className="truncate max-w-[140px]">{r.creator}</span>}
                            {r.creator && r.provider && <span>•</span>}
                            {r.provider && <span className="truncate max-w-[120px]">{r.provider}</span>}
                            {r.published_year && (
                              <span className="font-mono text-slate-400">({r.published_year})</span>
                            )}
                          </div>
                        </td>
                        <td className="px-3 py-2 text-center whitespace-nowrap">
                          <span className={`px-2 py-0.5 text-xs font-semibold rounded ${
                            isPassed 
                              ? 'bg-emerald-50 text-emerald-700 border border-emerald-200' 
                              : 'bg-red-50 text-red-700 border border-red-200'
                          }`}>
                            {r.status}
                          </span>
                          {r.is_override && (
                            <span className="block text-3xs text-indigo-600 mt-0.5">手動変更</span>
                          )}
                        </td>
                        <td className="px-3 py-2 text-center text-slate-400">
                          {r.has_image ? <ImageIcon className="w-3.5 h-3.5 mx-auto text-blue-500" /> : '-'}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            )}
          </div>

          {/* ページネーションコントロール */}
          <div className="p-3 bg-slate-50 border-t border-slate-100 flex items-center justify-between text-xs text-slate-600">
            <div className="flex items-center space-x-2">
              <span>ページサイズ:</span>
              <select
                value={pageSize}
                onChange={(e) => { setPageSize(Number(e.target.value)); setPage(1); }}
                className="py-0.5 px-2 border border-slate-300 rounded bg-white text-xs"
              >
                <option value={20}>20</option>
                <option value={50}>50</option>
                <option value={100}>100</option>
              </select>
              <span>
                {(page - 1) * pageSize + 1} - {Math.min(page * pageSize, total)} / {total.toLocaleString()} 件
              </span>
            </div>

            <div className="flex items-center space-x-1">
              <button
                onClick={() => setPage(p => Math.max(1, p - 1))}
                disabled={page <= 1}
                className="p-1 rounded border border-slate-300 bg-white hover:bg-slate-100 disabled:opacity-40"
              >
                <ChevronLeft className="w-4 h-4" />
              </button>
              <span className="px-2 font-medium">
                {page} / {totalPages || 1}
              </span>
              <button
                onClick={() => setPage(p => Math.min(totalPages, p + 1))}
                disabled={page >= totalPages}
                className="p-1 rounded border border-slate-300 bg-white hover:bg-slate-100 disabled:opacity-40"
              >
                <ChevronRight className="w-4 h-4" />
              </button>
            </div>
          </div>
        </div>

        {/* 詳細プレビューパネル（1カラム分） */}
        <div className="bg-white rounded-xl border border-slate-200 shadow-sm p-4 flex flex-col h-[700px] overflow-y-auto">
          {selectedRecord ? (
            <div className="space-y-4">
              <div className="flex items-start justify-between border-b border-slate-100 pb-3">
                <div>
                  <div className="text-2xs font-semibold text-slate-400 font-mono uppercase">
                    ID: {selectedRecord.id}
                  </div>
                  <h3 className="text-base font-bold text-slate-900 mt-1 leading-snug">
                    {selectedRecord.title || '（無題）'}
                  </h3>
                </div>
                <a
                  href={`https://jpsearch.go.jp/item/${selectedRecord.id}`}
                  target="_blank"
                  rel="noreferrer"
                  className="p-1.5 text-slate-400 hover:text-indigo-600 hover:bg-indigo-50 rounded"
                  title="ジャパンサーチ公式ページを開く"
                >
                  <ExternalLink className="w-4 h-4" />
                </a>
              </div>

              {/* 手動判定クイックボタン */}
              <div className="flex items-center space-x-2">
                <button
                  type="button"
                  onClick={() => updateDecision(selectedRecord.id, '合格')}
                  className={`flex-1 py-2 rounded-lg text-xs font-semibold flex items-center justify-center space-x-1 border transition-colors ${
                    selectedRecord.human_decision === '合格'
                      ? 'bg-emerald-600 text-white border-emerald-600 shadow-sm'
                      : 'border-slate-300 text-slate-700 bg-white hover:bg-emerald-50 hover:text-emerald-700'
                  }`}
                >
                  <Check className="w-4 h-4" />
                  <span>適合 (合格) [A]</span>
                </button>
                <button
                  type="button"
                  onClick={() => updateDecision(selectedRecord.id, '除外')}
                  className={`flex-1 py-2 rounded-lg text-xs font-semibold flex items-center justify-center space-x-1 border transition-colors ${
                    selectedRecord.human_decision === '除外'
                      ? 'bg-red-600 text-white border-red-600 shadow-sm'
                      : 'border-slate-300 text-slate-700 bg-white hover:bg-red-50 hover:text-red-700'
                  }`}
                >
                  <X className="w-4 h-4" />
                  <span>除外 [D]</span>
                </button>
              </div>

              {/* メタデータプロパティ一覧 */}
              <div className="space-y-3 text-xs">
                <div>
                  <span className="text-slate-400 font-medium block">著者・作成者 (Creator):</span>
                  <span className="text-slate-800 font-medium">{selectedRecord.creator || '（なし）'}</span>
                </div>

                <div className="grid grid-cols-2 gap-2">
                  <div>
                    <span className="text-slate-400 font-medium block">出版年:</span>
                    <span className="text-slate-800 font-mono">{selectedRecord.published_year || '不明'}</span>
                  </div>
                  <div>
                    <span className="text-slate-400 font-medium block">提供元 (Provider):</span>
                    <span className="text-slate-800 truncate block">{selectedRecord.provider || '不明'}</span>
                  </div>
                </div>

                <div>
                  <span className="text-slate-400 font-medium block">リソース種別 (Type):</span>
                  <div className="flex flex-wrap gap-1 mt-1">
                    {selectedRecord.type_list && selectedRecord.type_list.length > 0 ? (
                      selectedRecord.type_list.map(t => (
                        <span key={t} className="px-1.5 py-0.5 bg-slate-100 text-slate-600 rounded text-2xs font-mono">
                          {t}
                        </span>
                      ))
                    ) : (
                      <span className="text-slate-400">（なし）</span>
                    )}
                  </div>
                </div>

                <div>
                  <span className="text-slate-400 font-medium block">主題・分類 (About / NDC):</span>
                  <div className="flex flex-wrap gap-1 mt-1 max-h-32 overflow-y-auto">
                    {selectedRecord.about_list && selectedRecord.about_list.length > 0 ? (
                      selectedRecord.about_list.map(a => (
                        <span key={a} className="px-1.5 py-0.5 bg-blue-50 text-blue-700 rounded text-2xs">
                          {a}
                        </span>
                      ))
                    ) : (
                      <span className="text-slate-400">（なし）</span>
                    )}
                  </div>
                </div>

                {selectedRecord.description && (
                  <div>
                    <span className="text-slate-400 font-medium block">概要 (Description):</span>
                    <div className="text-slate-700 bg-slate-50 p-2 rounded border border-slate-100 max-h-28 overflow-y-auto leading-relaxed">
                      {selectedRecord.description}
                    </div>
                  </div>
                )}
              </div>

              {/* 判定内訳サマリー */}
              <div className="bg-slate-50 rounded-lg p-3 border border-slate-100 space-y-2 text-xs">
                <div className="font-semibold text-slate-700">自動判定理由・内訳</div>
                <div className="flex justify-between items-center text-slate-600">
                  <span>Type判定:</span>
                  <span className="font-semibold">{selectedRecord.type_status || '未判定'}</span>
                </div>
                <div className="flex justify-between items-center text-slate-600">
                  <span>About判定:</span>
                  <span className="font-semibold">{selectedRecord.about_status || '未判定'}</span>
                </div>
                <div className="flex justify-between items-center text-slate-600">
                  <span>N-gram判定:</span>
                  <span className="font-semibold">{selectedRecord.ngram_status || '未判定'}</span>
                </div>
                <div className="flex justify-between items-center text-slate-600">
                  <span>LLM推論:</span>
                  <span className="font-semibold">{selectedRecord.llm_status || '未判定'}</span>
                </div>
                {selectedRecord.primary_reason && (
                  <div className="pt-1 border-t border-slate-200 text-2xs text-slate-500">
                    主理由: {selectedRecord.primary_reason}
                  </div>
                )}
              </div>
            </div>
          ) : (
            <div className="h-full flex items-center justify-center text-slate-400 text-sm">
              レコードを選択すると詳細が表示されます
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
