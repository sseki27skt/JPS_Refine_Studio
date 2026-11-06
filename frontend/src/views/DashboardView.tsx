// -*- coding: utf-8 -*-
/**
 * パイプライン全体進捗ダッシュボード (PRISMAフロー風サマリー)
 */
import React, { useState, useEffect } from 'react';
import { api } from '../api/client';
import { DashboardStats, WorkspaceMeta } from '../types/api';
import { BarChart3, ArrowRight, Layers, Tag, Hash, BrainCircuit, CheckCheck, FileSpreadsheet, DownloadCloud } from 'lucide-react';
import { ViewType } from '../components/Sidebar';

interface Props {
  workspace: WorkspaceMeta | null;
  onNavigate: (view: ViewType) => void;
}

export const DashboardView: React.FC<Props> = ({ workspace, onNavigate }) => {
  const [stats, setStats] = useState<DashboardStats | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!workspace) return;
    setLoading(true);
    api.getDashboardStats(workspace.id)
      .then(setStats)
      .catch(console.error)
      .finally(() => setLoading(false));
  }, [workspace]);

  if (!workspace) {
    return (
      <div className="p-12 text-center text-slate-500">
        プロジェクトが選択されていません。左側のメニューからプロジェクトを選択または新規作成してください。
      </div>
    );
  }

  const s1 = stats?.step1_raw || 0;
  const s2a = stats?.step2a_type_survivors || 0;
  const s2b = stats?.step2b_about_survivors || 0;
  const s2c = stats?.step2c_ngram_survivors || 0;
  const s3 = stats?.step3_llm_evaluated || 0;
  const s4 = stats?.step4_human_reviewed || 0;
  const s5 = stats?.step5_export_ready || 0;

  return (
    <div className="p-8 max-w-6xl mx-auto space-y-8">
      {/* ヒーローヘッダー */}
      <div className="bg-gradient-to-r from-sky-900 to-indigo-900 rounded-2xl p-8 text-white shadow-md relative overflow-hidden">
        <div className="relative z-10 space-y-2">
          <div className="inline-block px-3 py-1 bg-white/20 rounded-full text-xs font-semibold backdrop-blur-xs">
            プロジェクト: {workspace.name}
          </div>
          <h2 className="text-3xl font-extrabold tracking-tight">
            メタデータ精緻化パイプライン進捗
          </h2>
          <p className="text-sm text-sky-100 max-w-2xl leading-relaxed">
            人文学文化資源メタデータの網羅的収集から多層ルール除外、LLM判定、専門家査読を経て高品質サブセットを構築します。
          </p>
        </div>
      </div>

      {/* PRISMA フロー進捗カード群 */}
      <div className="space-y-4">
        <h3 className="font-bold text-slate-800 text-base flex items-center gap-2">
          <BarChart3 className="w-5 h-5 text-sky-600" />
          多段階削ぎ落としフロー (PRISMAフロー概況)
        </h3>

        <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
          {/* Step 1 */}
          <div className="bg-white p-5 rounded-xl border border-slate-200 shadow-xs flex flex-col justify-between">
            <div>
              <span className="text-[11px] font-bold text-slate-400 uppercase">初期候補データセット</span>
              <p className="text-2xl font-black text-slate-900 mt-1 font-mono">
                {s1.toLocaleString()} <span className="text-xs font-normal text-slate-500">件</span>
              </p>
              <p className="text-xs text-slate-500 mt-1">SPARQL網羅的取得</p>
            </div>
            <button
              onClick={() => onNavigate('step1_fetch')}
              className="mt-4 w-full flex items-center justify-center gap-1.5 py-1.5 bg-slate-100 hover:bg-slate-200 text-slate-700 text-xs font-semibold rounded-lg transition-colors"
            >
              Step 1 へ <ArrowRight className="w-3.5 h-3.5" />
            </button>
          </div>

          {/* Step 2 ルール群 */}
          <div className="bg-white p-5 rounded-xl border border-slate-200 shadow-xs flex flex-col justify-between">
            <div>
              <span className="text-[11px] font-bold text-slate-400 uppercase">ルール通過残存件数</span>
              <div className="space-y-1.5 mt-2 text-xs">
                <div className="flex justify-between items-center">
                  <span className="text-slate-600">2-A 種別 (Type):</span>
                  <span className="font-bold font-mono text-slate-800">{s2a.toLocaleString()} 件</span>
                </div>
                <div className="flex justify-between items-center">
                  <span className="text-slate-600">2-B 主題 (About):</span>
                  <span className="font-bold font-mono text-slate-800">{s2b.toLocaleString()} 件</span>
                </div>
                <div className="flex justify-between items-center">
                  <span className="text-slate-600">2-C 語彙 (N-gram):</span>
                  <span className="font-bold font-mono text-slate-800">{s2c.toLocaleString()} 件</span>
                </div>
              </div>
            </div>
            <button
              onClick={() => onNavigate('step2_type')}
              className="mt-4 w-full flex items-center justify-center gap-1.5 py-1.5 bg-slate-100 hover:bg-slate-200 text-slate-700 text-xs font-semibold rounded-lg transition-colors"
            >
              Step 2 ルール設定へ <ArrowRight className="w-3.5 h-3.5" />
            </button>
          </div>

          {/* Step 3 & 4 */}
          <div className="bg-white p-5 rounded-xl border border-slate-200 shadow-xs flex flex-col justify-between">
            <div>
              <span className="text-[11px] font-bold text-slate-400 uppercase">判定・専門家査読</span>
              <div className="space-y-1.5 mt-2 text-xs">
                <div className="flex justify-between items-center">
                  <span className="text-slate-600">Step 3 LLM適合判定:</span>
                  <span className="font-bold font-mono text-slate-800">{s3.toLocaleString()} 件</span>
                </div>
                <div className="flex justify-between items-center">
                  <span className="text-amber-700 font-bold">Step 4 査読確定数:</span>
                  <span className="font-black font-mono text-amber-700">{s4.toLocaleString()} 件</span>
                </div>
              </div>
            </div>
            <button
              onClick={() => onNavigate('step4_review')}
              className="mt-4 w-full flex items-center justify-center gap-1.5 py-1.5 bg-amber-500 hover:bg-amber-600 text-white text-xs font-bold rounded-lg transition-colors shadow-xs"
            >
              Step 4 査読ポータルへ <ArrowRight className="w-3.5 h-3.5" />
            </button>
          </div>

          {/* Step 5 */}
          <div className="bg-white p-5 rounded-xl border border-slate-200 shadow-xs flex flex-col justify-between">
            <div>
              <span className="text-[11px] font-bold text-slate-400 uppercase">完成サブセット出力</span>
              <p className="text-2xl font-black text-emerald-700 mt-1 font-mono">
                {s5.toLocaleString()} <span className="text-xs font-normal text-slate-500">件</span>
              </p>
              <p className="text-xs text-slate-500 mt-1">ポータル・二次利用向けJSON</p>
            </div>
            <button
              onClick={() => onNavigate('step5_export')}
              className="mt-4 w-full flex items-center justify-center gap-1.5 py-1.5 bg-slate-100 hover:bg-slate-200 text-slate-700 text-xs font-semibold rounded-lg transition-colors"
            >
              Step 5 出力へ <ArrowRight className="w-3.5 h-3.5" />
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};

