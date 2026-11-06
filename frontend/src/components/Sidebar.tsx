// -*- coding: utf-8 -*-
/**
 * サイドバー・ナビゲーションコンポーネント
 */
import React from 'react';
import {
  FolderKanban,
  BarChart3,
  DownloadCloud,
  Layers,
  Tag,
  Hash,
  BrainCircuit,
  CheckCheck,
  FileSpreadsheet
} from 'lucide-react';

export type ViewType =
  | 'workspace'
  | 'dashboard'
  | 'step1_fetch'
  | 'step2_type'
  | 'step2a_about'
  | 'step2b_ngram'
  | 'step3_llm'
  | 'step4_review'
  | 'step5_export';

interface Props {
  currentView: ViewType;
  onNavigate: (view: ViewType) => void;
  statusMap?: Record<string, boolean>;
}

export const Sidebar: React.FC<Props> = ({ currentView, onNavigate }) => {
  const navItems = [
    { id: 'workspace' as ViewType, label: 'プロジェクト管理', icon: FolderKanban, group: 'メイン' },
    { id: 'dashboard' as ViewType, label: '進捗ダッシュボード', icon: BarChart3, group: 'メイン' },

    { id: 'step1_fetch' as ViewType, label: 'Step 1: メタデータ取得', sub: 'LLMクエリ拡張・SPARQL', icon: DownloadCloud, group: '精緻化パイプライン' },
    { id: 'step2_type' as ViewType, label: 'Step 2-A: データ種別', sub: 'rdf:type 除外', icon: Layers, group: '精緻化パイプライン' },
    { id: 'step2a_about' as ViewType, label: 'Step 2-B: 主題キーワード', sub: 'NDCツリー・NDL典拠', icon: Tag, group: '精緻化パイプライン' },
    { id: 'step2b_ngram' as ViewType, label: 'Step 2-C: タイトル語彙', sub: 'N-gram接尾辞クラスタ', icon: Hash, group: '精緻化パイプライン' },
    { id: 'step3_llm' as ViewType, label: 'Step 3: LLM適合判定', sub: '保留群のセマンティック分類', icon: BrainCircuit, group: '精緻化パイプライン' },
    { id: 'step4_review' as ViewType, label: 'Step 4: 専門家査読', sub: '高速目視確認・合否確定', icon: CheckCheck, group: '精緻化パイプライン', highlight: true },
    { id: 'step5_export' as ViewType, label: 'Step 5: 出力', sub: 'サブセットエクスポート', icon: FileSpreadsheet, group: '精緻化パイプライン' },
  ];

  return (
    <aside className="w-64 bg-white border-r border-slate-200 flex flex-col flex-shrink-0 h-[calc(100vh-57px)] sticky top-[57px] overflow-y-auto">
      <div className="p-4 space-y-6">
        <div>
          <p className="text-[11px] font-bold tracking-wider text-slate-400 uppercase mb-2">プロジェクト</p>
          <div className="space-y-1">
            {navItems.filter(i => i.group === 'メイン').map(item => {
              const Icon = item.icon;
              const isActive = currentView === item.id;
              return (
                <button
                  key={item.id}
                  onClick={() => onNavigate(item.id)}
                  className={`w-full flex items-center gap-3 px-3 py-2 rounded-lg text-sm font-medium transition-colors ${
                    isActive
                      ? 'bg-sky-50 text-sky-700 font-semibold border border-sky-200'
                      : 'text-slate-600 hover:bg-slate-100 hover:text-slate-900'
                  }`}
                >
                  <Icon className={`w-4 h-4 ${isActive ? 'text-sky-600' : 'text-slate-400'}`} />
                  {item.label}
                </button>
              );
            })}
          </div>
        </div>

        <div>
          <p className="text-[11px] font-bold tracking-wider text-slate-400 uppercase mb-2">精緻化パイプライン</p>
          <div className="space-y-1">
            {navItems.filter(i => i.group === '精緻化パイプライン').map(item => {
              const Icon = item.icon;
              const isActive = currentView === item.id;
              return (
                <button
                  key={item.id}
                  onClick={() => onNavigate(item.id)}
                  className={`w-full flex flex-col items-start px-3 py-2 rounded-lg text-left transition-colors ${
                    isActive
                      ? 'bg-sky-50 text-sky-700 font-semibold border border-sky-200'
                      : item.highlight
                      ? 'bg-amber-50/60 hover:bg-amber-100/70 text-slate-700 border border-amber-200/50'
                      : 'text-slate-600 hover:bg-slate-100 hover:text-slate-900'
                  }`}
                >
                  <div className="flex items-center gap-2.5 w-full">
                    <Icon className={`w-4 h-4 flex-shrink-0 ${
                      isActive ? 'text-sky-600' : item.highlight ? 'text-amber-600' : 'text-slate-400'
                    }`} />
                    <span className="text-sm font-medium leading-none">{item.label}</span>
                  </div>
                  {item.sub && (
                    <span className="text-[11px] text-slate-400 mt-1 pl-6 leading-tight">
                      {item.sub}
                    </span>
                  )}
                </button>
              );
            })}
          </div>
        </div>
      </div>
    </aside>
  );
};

