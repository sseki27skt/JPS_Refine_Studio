// -*- coding: utf-8 -*-
/**
 * ルール影響レコード完全一覧ドロワー (上限打ち切りなし & 巻き添え衝突警告タブ付き)
 */
import React, { useState, useEffect } from 'react';
import { api } from '../api/client';
import { RuleImpactResponse } from '../types/api';
import { X, AlertTriangle, Search, ChevronLeft, ChevronRight, Check, Ban, ExternalLink, ShieldAlert } from 'lucide-react';

interface Props {
  isOpen: boolean;
  onClose: () => void;
  workspaceId: string;
  ruleType: 'type' | 'about' | 'ngram';
  ruleValue: string;
  ruleLabel?: string;
  onApplyRule?: (action: 'OK' | 'NG') => void;
}

export const RuleImpactDrawer: React.FC<Props> = ({
  isOpen,
  onClose,
  workspaceId,
  ruleType,
  ruleValue,
  ruleLabel,
  onApplyRule
}) => {
  const [data, setData] = useState<RuleImpactResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [page, setPage] = useState(1);
  const [searchQuery, setSearchQuery] = useState('');
  const [warningOnly, setWarningOnly] = useState(false);

  const fetchRecords = async (p = 1, wOnly = warningOnly, sq = searchQuery) => {
    if (!isOpen || !ruleValue) return;
    setLoading(true);
    try {
      const res = await api.queryImpactRecords(workspaceId, {
        rule_type: ruleType,
        rule_value: ruleValue,
        page: p,
        page_size: 50,
        search_query: sq,
        warning_only: wOnly
      });
      setData(res);
      setPage(p);
    } catch (err) {
      console.error('Failed to query impact records:', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (isOpen && ruleValue) {
      setPage(1);
      setSearchQuery('');
      setWarningOnly(false);
      fetchRecords(1, false, '');
    }
  }, [isOpen, ruleType, ruleValue, workspaceId]);

  if (!isOpen) return null;

  const handleTabChange = (wOnly: boolean) => {
    setWarningOnly(wOnly);
    setPage(1);
    fetchRecords(1, wOnly, searchQuery);
  };

  const handleSearchSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    fetchRecords(1, warningOnly, searchQuery);
  };

  const hasConflict = (data?.warning_conflict_count || 0) > 0;

  return (
    <div className="fixed inset-0 z-50 overflow-hidden flex justify-end bg-black/40 backdrop-blur-xs transition-opacity">
      <div className="w-full max-w-3xl bg-white h-full shadow-2xl flex flex-col animate-in slide-in-from-right duration-200">
        {/* ヘッダー */}
        <div className="px-6 py-4 border-b border-slate-200 flex items-center justify-between bg-slate-50">
          <div>
            <div className="flex items-center gap-2">
              <span className="text-xs font-semibold px-2 py-0.5 rounded bg-slate-200 text-slate-700 uppercase">
                {ruleType.toUpperCase()} ルール影響検証
              </span>
              <h2 className="text-lg font-bold text-slate-900 truncate max-w-md">
                「{ruleLabel || ruleValue}」
              </h2>
            </div>
            <p className="text-xs text-slate-500 mt-1">
              この条件に合致する全レコード（上限打ち切りなし）を一覧・検証できます。
            </p>
          </div>
          <button
            onClick={onClose}
            className="p-2 text-slate-400 hover:text-slate-600 rounded-lg hover:bg-slate-200 transition-colors"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* タブ切り替え & 検索バー */}
        <div className="px-6 py-3 border-b border-slate-200 flex flex-col md:flex-row md:items-center justify-between gap-3 bg-white">
          <div className="flex items-center gap-2">
            <button
              onClick={() => handleTabChange(false)}
              className={`px-3 py-1.5 rounded-lg text-xs font-semibold transition-colors flex items-center gap-1.5 ${
                !warningOnly
                  ? 'bg-sky-600 text-white'
                  : 'bg-slate-100 text-slate-600 hover:bg-slate-200'
              }`}
            >
              影響を受ける全レコード
              <span className={`px-1.5 py-0.2 rounded-full text-[10px] ${!warningOnly ? 'bg-sky-700' : 'bg-slate-300 text-slate-700'}`}>
                {data ? data.total_impact_count.toLocaleString() : '...'}
              </span>
            </button>

            <button
              onClick={() => handleTabChange(true)}
              className={`px-3 py-1.5 rounded-lg text-xs font-semibold transition-colors flex items-center gap-1.5 ${
                warningOnly
                  ? 'bg-rose-600 text-white'
                  : hasConflict
                  ? 'bg-rose-50 text-rose-700 border border-rose-300 hover:bg-rose-100'
                  : 'bg-slate-100 text-slate-400'
              }`}
            >
              <ShieldAlert className="w-3.5 h-3.5" />
              巻き添え・衝突警告
              <span className={`px-1.5 py-0.2 rounded-full text-[10px] font-bold ${
                warningOnly ? 'bg-rose-700' : hasConflict ? 'bg-rose-600 text-white' : 'bg-slate-200 text-slate-500'
              }`}>
                {data ? data.warning_conflict_count.toLocaleString() : '0'}
              </span>
            </button>
          </div>

          <form onSubmit={handleSearchSubmit} className="relative flex items-center">
            <input
              type="text"
              placeholder="影響レコード内を検索..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="pl-8 pr-3 py-1.5 bg-slate-100 border border-slate-200 rounded-lg text-xs outline-none focus:border-sky-500 w-48 transition-all"
            />
            <Search className="w-3.5 h-3.5 text-slate-400 absolute left-2.5 pointer-events-none" />
          </form>
        </div>

        {/* 衝突警告バナー */}
        {hasConflict && !warningOnly && (
          <div className="mx-6 mt-4 p-3 bg-amber-50 border border-amber-300 rounded-lg flex items-start gap-2.5">
            <AlertTriangle className="w-4 h-4 text-amber-600 flex-shrink-0 mt-0.5" />
            <div className="text-xs text-amber-900">
              <span className="font-bold">注意: 確定合格済み（またはLLM適合）の資料が {data?.warning_conflict_count} 件 含まれています。</span>
              <p className="mt-0.5 text-amber-800">
                このルールを除外（NG）に設定すると、これらの資料も除外対象として巻き添えになります。「巻き添え・衝突警告」タブでご確認ください。
              </p>
            </div>
          </div>
        )}

        {/* レコード一覧 (スクロール可能) */}
        <div className="flex-1 overflow-y-auto px-6 py-4 divide-y divide-slate-100">
          {loading ? (
            <div className="py-20 text-center text-slate-400 text-sm">
              影響レコードを高速検索中...
            </div>
          ) : !data || data.records.length === 0 ? (
            <div className="py-20 text-center text-slate-400 text-sm">
              該当するレコードはありません。
            </div>
          ) : (
            data.records.map((rec) => (
              <div key={rec.id} className="py-3 flex flex-col gap-1.5 hover:bg-slate-50/80 px-2 rounded-lg transition-colors">
                <div className="flex items-start justify-between gap-3">
                  <div className="flex items-center gap-2">
                    {rec.is_conflict && (
                      <span className="px-1.5 py-0.5 bg-rose-100 text-rose-700 text-[10px] font-bold rounded flex items-center gap-1">
                        <AlertTriangle className="w-3 h-3" />
                        確定合格
                      </span>
                    )}
                    <span className={`px-2 py-0.5 rounded text-[10px] font-bold ${
                      rec.cur_status === '合格' ? 'bg-emerald-100 text-emerald-800' :
                      rec.cur_status === '除外' ? 'bg-rose-100 text-rose-800' : 'bg-slate-200 text-slate-700'
                    }`}>
                      {rec.cur_status}
                    </span>
                    <a
                      href={rec.id}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="font-bold text-sm text-sky-800 hover:text-sky-600 hover:underline flex items-center gap-1"
                    >
                      {rec.title}
                      <ExternalLink className="w-3 h-3 text-slate-400" />
                    </a>
                  </div>
                </div>

                {rec.description && (
                  <p className="text-xs text-slate-600 line-clamp-2 leading-relaxed">
                    {rec.description}
                  </p>
                )}

                <div className="flex items-center gap-2 text-[11px] text-slate-500 mt-1 flex-wrap">
                  {rec.provider && (
                    <span className="bg-slate-100 px-2 py-0.5 rounded text-slate-600 font-medium">
                      所蔵: {rec.provider}
                    </span>
                  )}
                  {rec.published_year && (
                    <span className="bg-slate-100 px-2 py-0.5 rounded text-slate-600">
                      年: {rec.published_year}
                    </span>
                  )}
                  {rec.about_list && rec.about_list.length > 0 && (
                    <div className="flex items-center gap-1 flex-wrap">
                      <span className="text-slate-400">About:</span>
                      {rec.about_list.slice(0, 4).map((a, idx) => (
                        <span key={idx} className="bg-slate-200/70 text-slate-700 px-1.5 py-0.2 rounded text-[10px]">
                          {a}
                        </span>
                      ))}
                      {rec.about_list.length > 4 && (
                        <span className="text-[10px] text-slate-400">+{rec.about_list.length - 4}</span>
                      )}
                    </div>
                  )}
                </div>
              </div>
            ))
          )}
        </div>

        {/* ページネーション & アクションフッター */}
        <div className="px-6 py-4 border-t border-slate-200 bg-slate-50 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <button
              onClick={() => fetchRecords(page - 1)}
              disabled={page <= 1 || loading}
              className="p-1.5 border border-slate-300 rounded bg-white text-slate-600 hover:bg-slate-100 disabled:opacity-40"
            >
              <ChevronLeft className="w-4 h-4" />
            </button>
            <span className="text-xs text-slate-600 font-medium font-mono">
              {page} / {data?.total_pages || 1} ページ ({data?.total_impact_count.toLocaleString()} 件中)
            </span>
            <button
              onClick={() => fetchRecords(page + 1)}
              disabled={!data || page >= data.total_pages || loading}
              className="p-1.5 border border-slate-300 rounded bg-white text-slate-600 hover:bg-slate-100 disabled:opacity-40"
            >
              <ChevronRight className="w-4 h-4" />
            </button>
          </div>

          {onApplyRule && (
            <div className="flex items-center gap-3">
              <button
                onClick={() => onApplyRule('OK')}
                className="flex items-center gap-1.5 px-4 py-2 bg-emerald-600 hover:bg-emerald-700 text-white rounded-lg text-xs font-bold shadow-xs transition-colors"
              >
                <Check className="w-4 h-4" />
                合格 (OK) として登録
              </button>

              <button
                onClick={() => onApplyRule('NG')}
                className="flex items-center gap-1.5 px-4 py-2 bg-rose-600 hover:bg-rose-700 text-white rounded-lg text-xs font-bold shadow-xs transition-colors"
              >
                <Ban className="w-4 h-4" />
                除外 (NG) として登録
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
