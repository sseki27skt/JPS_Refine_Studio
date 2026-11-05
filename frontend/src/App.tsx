import React, { useState } from 'react';
import { useWorkspace } from './hooks/useWorkspace';
import { useJobStatus } from './hooks/useJobStatus';
import { api } from './api/client';
import { Header } from './components/Header';
import { Sidebar, ViewType } from './components/Sidebar';
import { JobProgressBar } from './components/JobProgressBar';
import { WorkspaceView } from './views/WorkspaceView';
import { DashboardView } from './views/DashboardView';
import { FetchView } from './views/FetchView';
import { TypeFilterView } from './views/TypeFilterView';
import { AboutFilterView } from './views/AboutFilterView';
import { NgramFilterView } from './views/NgramFilterView';
import { LlmFilterView } from './views/LlmFilterView';
import { ReviewView } from './views/ReviewView';
import { ExportView } from './views/ExportView';
import { Plus, Database } from 'lucide-react';

export const App: React.FC = () => {
  const {
    workspaces,
    activeWsId,
    activeWorkspace,
    loading,
    selectWorkspace,
    refreshWorkspaces
  } = useWorkspace();

  const { job } = useJobStatus(activeWsId);

  const [activeTab, setActiveTab] = useState<ViewType>('dashboard');
  const [createModalOpen, setCreateModalOpen] = useState(false);
  const [newWsId, setNewWsId] = useState('');
  const [newWsName, setNewWsName] = useState('');
  const [newWsTheme, setNewWsTheme] = useState('');
  const [newWsDesc, setNewWsDesc] = useState('');
  const [cloneFrom, setCloneFrom] = useState('');

  const handleCreateSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newWsId.trim() || !newWsName.trim()) return;

    try {
      await api.createWorkspace({
        id: newWsId.trim(),
        name: newWsName.trim(),
        research_theme: newWsTheme.trim(),
        description: newWsDesc.trim(),
        clone_from: cloneFrom || null
      });
      await refreshWorkspaces();
      selectWorkspace(newWsId.trim());
      setCreateModalOpen(false);
      setNewWsId('');
      setNewWsName('');
      setNewWsTheme('');
      setNewWsDesc('');
      setCloneFrom('');
    } catch (err: any) {
      alert(err.message || '作成に失敗しました');
    }
  };

  const renderActiveView = () => {
    if (activeTab === 'workspace') {
      return (
        <WorkspaceView
          workspaces={workspaces}
          activeWsId={activeWsId}
          onSelectWorkspace={selectWorkspace}
          onRefreshWorkspaces={refreshWorkspaces}
        />
      );
    }

    if (!activeWsId) {
      return (
        <div className="py-24 text-center max-w-lg mx-auto space-y-4">
          <div className="w-16 h-16 bg-sky-50 text-sky-600 rounded-2xl flex items-center justify-center mx-auto">
            <Database className="w-8 h-8" />
          </div>
          <h2 className="text-xl font-bold text-slate-800">プロジェクトが選択されていません</h2>
          <p className="text-sm text-slate-500">
            ヘッダーのドロップダウンから既存のワークスペースを選択するか、新しく作成してください。
          </p>
          <button
            onClick={() => setCreateModalOpen(true)}
            className="inline-flex items-center px-4 py-2 border border-transparent rounded-lg shadow-sm text-sm font-semibold text-white bg-sky-600 hover:bg-sky-700"
          >
            <Plus className="w-4 h-4 mr-2" />
            新規プロジェクトを作成
          </button>
        </div>
      );
    }

    switch (activeTab) {
      case 'dashboard':
        return <DashboardView workspace={activeWorkspace} onNavigate={setActiveTab} />;
      case 'step1_fetch':
        return <FetchView workspace={activeWorkspace} onJobStarted={() => {}} />;
      case 'step2_type':
        return <TypeFilterView workspaceId={activeWsId} />;
      case 'step2a_about':
        return <AboutFilterView workspaceId={activeWsId} />;
      case 'step2b_ngram':
        return <NgramFilterView workspaceId={activeWsId} />;
      case 'step3_llm':
        return <LlmFilterView workspaceId={activeWsId} />;
      case 'step4_review':
        return <ReviewView workspaceId={activeWsId} />;
      case 'step5_export':
        return <ExportView workspaceId={activeWsId} />;
      default:
        return <DashboardView workspace={activeWorkspace} onNavigate={setActiveTab} />;
    }
  };

  return (
    <div className="min-h-screen bg-slate-50 flex flex-col text-slate-900 font-sans antialiased">
      {/* グローバルジョブ常駐バー */}
      <JobProgressBar job={job} />

      {/* ヘッダー */}
      <Header
        workspaces={workspaces}
        activeWsId={activeWsId}
        onSelectWorkspace={selectWorkspace}
        onOpenCreateModal={() => setCreateModalOpen(true)}
      />

      {/* メインレイアウト */}
      <div className="flex-1 flex overflow-hidden">
        {/* サイドバー */}
        <Sidebar
          currentView={activeTab}
          onNavigate={setActiveTab}
        />

        {/* コンテンツメイン領域 */}
        <main className="flex-1 overflow-y-auto p-6 md:p-8">
          <div className="max-w-7xl mx-auto">
            {renderActiveView()}
          </div>
        </main>
      </div>

      {/* ワークスペース作成モーダル */}
      {createModalOpen && (
        <div className="fixed inset-0 z-50 bg-slate-900/40 backdrop-blur-xs flex items-center justify-center p-4">
          <div className="bg-white rounded-2xl shadow-2xl max-w-lg w-full p-6 space-y-4">
            <h3 className="text-lg font-bold text-slate-800">新規プロジェクトの作成</h3>
            <form onSubmit={handleCreateSubmit} className="space-y-4">
              <div>
                <label className="block text-xs font-semibold text-slate-700 mb-1">
                  プロジェクトID (半角英数記号) *
                </label>
                <input
                  type="text"
                  required
                  pattern="[a-zA-Z0-9_\-]+"
                  value={newWsId}
                  onChange={(e) => setNewWsId(e.target.value)}
                  placeholder="gagaku_scores_2026"
                  className="w-full px-3 py-2 text-sm border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-sky-500"
                />
              </div>

              <div>
                <label className="block text-xs font-semibold text-slate-700 mb-1">
                  プロジェクト表示名 *
                </label>
                <input
                  type="text"
                  required
                  value={newWsName}
                  onChange={(e) => setNewWsName(e.target.value)}
                  placeholder="雅楽楽譜コレクション"
                  className="w-full px-3 py-2 text-sm border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-sky-500"
                />
              </div>

              <div>
                <label className="block text-xs font-semibold text-slate-700 mb-1">
                  研究主題 (Research Theme)
                </label>
                <input
                  type="text"
                  value={newWsTheme}
                  onChange={(e) => setNewWsTheme(e.target.value)}
                  placeholder="日本の伝統雅楽に関する楽譜・文献メタデータの構築"
                  className="w-full px-3 py-2 text-sm border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-sky-500"
                />
              </div>

              <div>
                <label className="block text-xs font-semibold text-slate-700 mb-1">
                  説明 (任意)
                </label>
                <textarea
                  rows={2}
                  value={newWsDesc}
                  onChange={(e) => setNewWsDesc(e.target.value)}
                  placeholder="メモやプロジェクト概要..."
                  className="w-full px-3 py-2 text-sm border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-sky-500"
                />
              </div>

              <div>
                <label className="block text-xs font-semibold text-slate-700 mb-1">
                  クローン元プロジェクト (既存データとルールを継承)
                </label>
                <select
                  value={cloneFrom}
                  onChange={(e) => setCloneFrom(e.target.value)}
                  className="w-full px-3 py-2 text-sm border border-slate-300 rounded-lg bg-white focus:outline-none focus:ring-2 focus:ring-sky-500"
                >
                  <option value="">新規に空で作成</option>
                  {workspaces.map(w => (
                    <option key={w.id} value={w.id}>
                      {w.name} ({w.id})
                    </option>
                  ))}
                </select>
              </div>

              <div className="flex justify-end space-x-3 pt-3 border-t border-slate-100">
                <button
                  type="button"
                  onClick={() => setCreateModalOpen(false)}
                  className="px-4 py-2 text-sm text-slate-600 hover:text-slate-800"
                >
                  キャンセル
                </button>
                <button
                  type="submit"
                  className="px-4 py-2 text-sm font-semibold text-white bg-sky-600 hover:bg-sky-700 rounded-lg shadow-sm"
                >
                  作成する
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
};

export default App;
