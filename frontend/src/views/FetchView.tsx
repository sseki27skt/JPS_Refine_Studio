// -*- coding: utf-8 -*-
/**
 * Step 1: LLMクエリ拡張 & Japan Search メタデータ一括取得画面
 */
import React, { useState } from 'react';
import { api } from '../api/client';
import { WorkspaceMeta, QueryExpandResponse } from '../types/api';
import { DownloadCloud, Sparkles, Play, CheckCircle2, Settings } from 'lucide-react';

interface Props {
  workspace: WorkspaceMeta | null;
  onJobStarted: (jobId: string) => void;
}

export const FetchView: React.FC<Props> = ({ workspace, onJobStarted }) => {
  const [theme, setTheme] = useState(workspace?.research_theme || '日本伝統音楽の古典籍における楽譜資料');
  const [keywordsText, setKeywordsText] = useState('楽譜, 箏譜, 尺八譜, 笛譜, 雅楽譜, 工工四, 声明博士, 文化譜');
  const [ndcCodesText, setNdcCodesText] = useState('768, 760');
  const [excludeNdcText, setExcludeNdcText] = useState('40, 41, 42, 50, 51, 60');
  const [titleRegex, setTitleRegex] = useState('.*');
  const [domainDef, setDomainDef] = useState('日本の古典籍における楽譜・音楽資料');

  const [isExpanding, setIsExpanding] = useState(false);
  const [isStartingFetch, setIsStartingFetch] = useState(false);

  if (!workspace) return <div className="p-8">プロジェクトを選択してください。</div>;

  const handleExpandQuery = async () => {
    if (!theme.trim()) return;
    setIsExpanding(true);
    try {
      const existing = keywordsText.split(/[,、\n]+/).map(w => w.trim()).filter(Boolean);
      const res = await api.expandQuery(workspace.id, {
        theme: theme.trim(),
        existing_keywords: existing,
        provider: 'gemini'
      });
      setKeywordsText(res.keywords.join(', '));
      setNdcCodesText(res.ndc_codes.join(', '));
      setExcludeNdcText(res.exclude_ndc_codes.join(', '));
      setTitleRegex(res.title_regex);
      setDomainDef(res.domain_definition);
      alert('LLMによるクエリ拡張が完了しました。');
    } catch (err: any) {
      alert(`クエリ拡張失敗: ${err.message}`);
    } finally {
      setIsExpanding(false);
    }
  };

  const handleStartFetch = async () => {
    const kws = keywordsText.split(/[,、\n]+/).map(w => w.trim()).filter(Boolean);
    const ndcs = ndcCodesText.split(/[,、\n]+/).map(w => w.trim()).filter(Boolean);
    const exNdcs = excludeNdcText.split(/[,、\n]+/).map(w => w.trim()).filter(Boolean);

    if (kws.length === 0) {
      alert('検索キーワードを少なくとも1つ入力してください。');
      return;
    }

    setIsStartingFetch(true);
    try {
      const res = await api.startFetch(workspace.id, {
        keywords: kws,
        ndc_codes: ndcs,
        exclude_ndc_codes: exNdcs,
        title_regex: titleRegex,
        domain_definition: domainDef,
        batch_size: 10,
        resume: true
      });
      onJobStarted(res.job_id);
    } catch (err: any) {
      alert(`取得ジョブ起動失敗: ${err.message}`);
    } finally {
      setIsStartingFetch(false);
    }
  };

  return (
    <div className="p-8 max-w-5xl mx-auto space-y-8">
      <div>
        <h2 className="text-2xl font-bold text-slate-900 flex items-center gap-2.5">
          <DownloadCloud className="w-7 h-7 text-sky-600" />
          Step 1: LLMクエリ拡張 ＆ Japan Search メタデータ一括取得
        </h2>
        <p className="text-sm text-slate-500 mt-1">
          自然言語の研究テーマからLLMが関連語彙・NDC分類を自動拡張し、ジャパンサーチのSPARQLエンドポイントから3階層トリプル（親・子・孫ノード）を再帰取得します。
        </p>
      </div>

      {/* テーマ入力 & LLM拡張パネル */}
      <div className="bg-white p-6 rounded-xl border border-slate-200 shadow-xs space-y-4">
        <h3 className="font-bold text-slate-800 text-sm flex items-center gap-2">
          <Sparkles className="w-4 h-4 text-sky-600" />
          自然言語による研究テーマ設定 ＆ LLM語彙拡張
        </h3>

        <div className="space-y-2">
          <label className="text-xs font-semibold text-slate-700">研究対象ドメイン・収集テーマ</label>
          <div className="flex gap-3">
            <input
              type="text"
              value={theme}
              onChange={(e) => setTheme(e.target.value)}
              placeholder="例: 日本伝統音楽における古典籍の楽譜資料"
              className="flex-1 px-4 py-2 bg-slate-50 border border-slate-300 rounded-lg text-sm outline-none focus:border-sky-500"
            />
            <button
              onClick={handleExpandQuery}
              disabled={isExpanding || !theme.trim()}
              className="px-5 py-2 bg-gradient-to-r from-sky-600 to-indigo-600 hover:from-sky-700 hover:to-indigo-700 text-white rounded-lg text-xs font-bold shadow-xs transition-all flex items-center gap-2 disabled:opacity-50"
            >
              <Sparkles className="w-4 h-4" />
              {isExpanding ? 'LLM語彙拡張中...' : 'LLMで検索語彙を自動拡張'}
            </button>
          </div>
        </div>
      </div>

      {/* 検索条件パラメータ設定 */}
      <div className="bg-white p-6 rounded-xl border border-slate-200 shadow-xs space-y-6">
        <h3 className="font-bold text-slate-800 text-sm flex items-center gap-2">
          <Settings className="w-4 h-4 text-slate-600" />
          SPARQL検索条件パラメータ
        </h3>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          <div className="space-y-2">
            <label className="text-xs font-semibold text-slate-700">検索キーワード (カンマ区切り)</label>
            <textarea
              rows={3}
              value={keywordsText}
              onChange={(e) => setKeywordsText(e.target.value)}
              className="w-full p-3 bg-slate-50 border border-slate-300 rounded-lg text-xs font-mono outline-none focus:border-sky-500"
            />
            <p className="text-[11px] text-slate-400">タイトル・説明文・主題を横断全文検索します。</p>
          </div>

          <div className="space-y-2">
            <label className="text-xs font-semibold text-slate-700">ドメイン定義 (LLM判定用)</label>
            <textarea
              rows={3}
              value={domainDef}
              onChange={(e) => setDomainDef(e.target.value)}
              className="w-full p-3 bg-slate-50 border border-slate-300 rounded-lg text-xs outline-none focus:border-sky-500"
            />
            <p className="text-[11px] text-slate-400">Step 3 のセマンティック推論時に依拠する定義文。</p>
          </div>

          <div className="space-y-2">
            <label className="text-xs font-semibold text-slate-700">OK対象 NDC分類コード (カンマ区切り)</label>
            <input
              type="text"
              value={ndcCodesText}
              onChange={(e) => setNdcCodesText(e.target.value)}
              className="w-full px-3 py-2 bg-slate-50 border border-slate-300 rounded-lg text-xs font-mono outline-none focus:border-sky-500"
            />
          </div>

          <div className="space-y-2">
            <label className="text-xs font-semibold text-slate-700">事前除外 NDCコード (自然科学・工学等)</label>
            <input
              type="text"
              value={excludeNdcText}
              onChange={(e) => setExcludeNdcText(e.target.value)}
              className="w-full px-3 py-2 bg-slate-50 border border-slate-300 rounded-lg text-xs font-mono outline-none focus:border-sky-500"
            />
          </div>
        </div>

        {/* 実行ボタン */}
        <div className="pt-4 border-t border-slate-100 flex items-center justify-between">
          <p className="text-xs text-slate-500">
            ※ バックグラウンドで非同期実行され、ブラウザを閉じても中断されません。
          </p>
          <button
            onClick={handleStartFetch}
            disabled={isStartingFetch}
            className="px-6 py-2.5 bg-sky-600 hover:bg-sky-700 text-white rounded-lg text-xs font-bold shadow-md transition-colors flex items-center gap-2 disabled:opacity-50"
          >
            <Play className="w-4 h-4 fill-current" />
            {isStartingFetch ? 'ジョブ起動中...' : 'SPARQL全件取得ジョブを開始'}
          </button>
        </div>
      </div>
    </div>
  );
};

