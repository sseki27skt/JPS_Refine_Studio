// -*- coding: utf-8 -*-
/**
 * ワークスペース・スナップショット管理画面
 */
import React, { useState, useEffect } from 'react';
import { WorkspaceMeta } from '../types/api';
import { api } from '../api/client';
import { FolderKanban, Plus, Trash2, Camera, RotateCcw, Clock, HardDrive, CheckCircle2 } from 'lucide-react';

interface Props {
  workspaces: WorkspaceMeta[];
  activeWsId: string | null;
  onSelectWorkspace: (id: string) => void;
  onRefreshWorkspaces: () => void;
}

export const WorkspaceView: React.FC<Props> = ({
  workspaces,
  activeWsId,
  onSelectWorkspace,
  onRefreshWorkspaces
}) => {
  const [snapshots, setSnapshots] = useState<any[]>([]);
  const [snapName, setSnapName] = useState('');
  const [snapDesc, setSnapDesc] = useState('');
  const [isCreatingSnap, setIsCreatingSnap] = useState(false);
  const [loading, setLoading] = useState(false);

  const fetchSnapshots = async () => {
    if (!activeWsId) return;
    try {
      const list = await api.getSnapshots(activeWsId);
      setSnapshots(list);
    } catch (err) {
      console.error('Failed to load snapshots:', err);
    }
  };

  useEffect(() => {
    fetchSnapshots();
  }, [activeWsId]);

  const handleCreateSnapshot = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!activeWsId || !snapName.trim()) return;
    setIsCreatingSnap(true);
    try {
      await api.createSnapshot(activeWsId, snapName.trim(), snapDesc.trim());
      setSnapName('');
      setSnapDesc('');
      fetchSnapshots();
      alert('スナップショットを保存しました。');
    } catch (err: any) {
      alert(`スナップショット保存失敗: ${err.message}`);
    } finally {
      setIsCreatingSnap(false);
    }
  };

  const handleRestoreSnapshot = async (snapId: string) => {
    if (!activeWsId) return;
    if (!window.confirm('このスナップショットの状態にルールと判定を復元しますか？')) return;
    try {
      await api.restoreSnapshot(activeWsId, snapId);
      alert('スナップショットを復元しました。');
    } catch (err: any) {
      alert(`復元失敗: ${err.message}`);
    }
  };

  const handleDeleteWorkspace = async (wsId: string) => {
    if (!window.confirm(`ワークスペース '${wsId}' を完全に削除しますか？`)) return;
    try {
      await api.deleteWorkspace(wsId);
      onRefreshWorkspaces();
    } catch (err: any) {
      alert(`削除失敗: ${err.message}`);
    }
  };

  const activeWs = workspaces.find(w => w.id === activeWsId);

  return (
    <div className="p-8 max-w-6xl mx-auto space-y-8">
      <div>
        <h2 className="text-2xl font-bold text-slate-900 flex items-center gap-2.5">
          <FolderKanban className="w-7 h-7 text-sky-600" />
          研究プロジェクト・履歴マネージャー
        </h2>
        <p className="text-sm text-slate-500 mt-1">
          研究テーマごとの独立したワークスペース管理、および試行錯誤の途中経過（スナップショット）の保存・復元を行います。
        </p>
      </div>

      {/* ワークスペース一覧カード */}
      <div className="bg-white rounded-xl border border-slate-200 shadow-xs overflow-hidden">
        <div className="px-6 py-4 border-b border-slate-200 bg-slate-50/70 flex items-center justify-between">
          <h3 className="font-bold text-slate-800 text-sm">研究プロジェクト一覧 ({workspaces.length}件)</h3>
        </div>

        <div className="divide-y divide-slate-100">
          {workspaces.map(w => {
            const isActive = w.id === activeWsId;
            return (
              <div
                key={w.id}
                className={`p-6 flex flex-col md:flex-row md:items-center justify-between gap-4 transition-colors ${
                  isActive ? 'bg-sky-50/50' : 'hover:bg-slate-50'
                }`}
              >
                <div className="space-y-1">
                  <div className="flex items-center gap-2.5">
                    <span className="font-bold text-base text-slate-900">{w.name}</span>
                    <span className="text-xs px-2 py-0.5 rounded font-mono bg-slate-100 text-slate-600 border border-slate-200">
                      ID: {w.id}
                    </span>
                    {isActive && (
                      <span className="text-xs px-2.5 py-0.5 rounded-full font-bold bg-sky-600 text-white flex items-center gap-1">
                        <CheckCircle2 className="w-3 h-3" />
                        選択中
                      </span>
                    )}
                  </div>
                  {w.description && <p className="text-xs text-slate-600">{w.description}</p>}
                  {w.research_theme && (
                    <p className="text-xs text-slate-500">
                      <span className="font-semibold text-slate-700">研究テーマ:</span> {w.research_theme}
                    </p>
                  )}
                  <div className="flex items-center gap-4 text-[11px] text-slate-400 mt-2 font-mono">
                    <span className="flex items-center gap-1">
                      <Clock className="w-3 h-3" /> 作成: {w.created_at?.slice(0, 16) || '不明'}
                    </span>
                    <span className="flex items-center gap-1">
                      <HardDrive className="w-3 h-3" /> 容量: {((w.disk_size_bytes || 0) / (1024 * 1024)).toFixed(1)} MB
                    </span>
                  </div>
                </div>

                <div className="flex items-center gap-2 flex-shrink-0">
                  {!isActive && (
                    <button
                      onClick={() => onSelectWorkspace(w.id)}
                      className="px-4 py-1.5 bg-sky-600 hover:bg-sky-700 text-white rounded-lg text-xs font-semibold shadow-xs transition-colors"
                    >
                      切替
                    </button>
                  )}
                  {workspaces.length > 1 && (
                    <button
                      onClick={() => handleDeleteWorkspace(w.id)}
                      className="p-1.5 text-slate-400 hover:text-rose-600 rounded-lg hover:bg-rose-50 transition-colors"
                      title="プロジェクト削除"
                    >
                      <Trash2 className="w-4 h-4" />
                    </button>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* スナップショット管理 */}
      {activeWs && (
        <div className="bg-white rounded-xl border border-slate-200 shadow-xs p-6 space-y-6">
          <div className="flex items-center justify-between border-b border-slate-100 pb-4">
            <div>
              <h3 className="font-bold text-slate-900 text-base flex items-center gap-2">
                <Camera className="w-5 h-5 text-amber-600" />
                スナップショット保存・復元 (試行錯誤の履歴)
              </h3>
              <p className="text-xs text-slate-500 mt-0.5">
                選択中プロジェクト「{activeWs.name}」のルール設定およびDuckDB判定ステータスを即時退避・復元できます。
              </p>
            </div>
          </div>

          <form onSubmit={handleCreateSnapshot} className="flex flex-col md:flex-row gap-3 items-end bg-slate-50 p-4 rounded-lg border border-slate-200">
            <div className="flex-1 space-y-1">
              <label className="text-xs font-bold text-slate-700">スナップショット名</label>
              <input
                type="text"
                placeholder="例: Type除外完了時点, N-gramルール精査前"
                value={snapName}
                onChange={(e) => setSnapName(e.target.value)}
                required
                className="w-full px-3 py-1.5 bg-white border border-slate-300 rounded-lg text-xs outline-none focus:border-sky-500"
              />
            </div>
            <div className="flex-1 space-y-1">
              <label className="text-xs font-bold text-slate-700">メモ・説明 (任意)</label>
              <input
                type="text"
                placeholder="例: 近世楽譜の系譜を除外した直後"
                value={snapDesc}
                onChange={(e) => setSnapDesc(e.target.value)}
                className="w-full px-3 py-1.5 bg-white border border-slate-300 rounded-lg text-xs outline-none focus:border-sky-500"
              />
            </div>
            <button
              type="submit"
              disabled={isCreatingSnap || !snapName.trim()}
              className="px-4 py-2 bg-slate-800 hover:bg-slate-900 text-white rounded-lg text-xs font-bold shadow-xs transition-colors flex items-center gap-1.5 disabled:opacity-50 flex-shrink-0"
            >
              <Camera className="w-3.5 h-3.5" />
              スナップショット保存
            </button>
          </form>

          {/* スナップショット一覧 */}
          <div className="space-y-3">
            <h4 className="font-bold text-xs text-slate-700">保存済みスナップショット ({snapshots.length}件)</h4>
            {snapshots.length === 0 ? (
              <p className="text-xs text-slate-400 py-4 text-center">保存されたスナップショットはありません。</p>
            ) : (
              <div className="divide-y divide-slate-100 border border-slate-200 rounded-lg overflow-hidden">
                {snapshots.map(s => (
                  <div key={s.id} className="p-4 flex items-center justify-between hover:bg-slate-50 gap-4">
                    <div>
                      <div className="flex items-center gap-2">
                        <span className="font-bold text-sm text-slate-800">{s.name}</span>
                        <span className="text-[10px] font-mono text-slate-400">({s.id})</span>
                      </div>
                      {s.description && <p className="text-xs text-slate-500 mt-0.5">{s.description}</p>}
                      <div className="flex items-center gap-3 text-[11px] text-slate-400 mt-1 font-mono">
                        <span>保存日時: {s.created_at?.slice(0, 16)}</span>
                        {s.metrics && (
                          <span>
                            採用: {s.metrics.adopted?.toLocaleString()} 件 / 除外: {s.metrics.discarded?.toLocaleString()} 件
                          </span>
                        )}
                      </div>
                    </div>
                    <button
                      onClick={() => handleRestoreSnapshot(s.id)}
                      className="px-3 py-1.5 bg-white border border-slate-300 hover:bg-slate-100 text-slate-700 rounded text-xs font-semibold flex items-center gap-1.5 shadow-xs transition-colors"
                    >
                      <RotateCcw className="w-3.5 h-3.5 text-amber-600" />
                      この状態へ復元
                    </button>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
};

