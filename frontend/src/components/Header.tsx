// -*- coding: utf-8 -*-
/**
 * システム共通ヘッダーコンポーネント
 */
import React from 'react';
import { WorkspaceMeta } from '../types/api';
import { Layers, Database, Plus } from 'lucide-react';

interface Props {
  workspaces: WorkspaceMeta[];
  activeWsId: string | null;
  onSelectWorkspace: (id: string) => void;
  onOpenCreateModal: () => void;
}

export const Header: React.FC<Props> = ({
  workspaces,
  activeWsId,
  onSelectWorkspace,
  onOpenCreateModal
}) => {
  return (
    <header className="bg-white border-b border-slate-200 px-6 py-3 flex items-center justify-between sticky top-0 z-30 shadow-xs">
      <div className="flex items-center gap-3">
        <div className="w-8 h-8 rounded-lg bg-sky-600 flex items-center justify-center text-white font-bold text-base shadow-sm">
          J
        </div>
        <div>
          <h1 className="font-bold text-slate-900 text-base leading-tight flex items-center gap-2">
            JPS Refine Studio
            <span className="text-xs px-2 py-0.5 bg-sky-100 text-sky-800 rounded font-semibold">v2.0 SPA</span>
          </h1>
          <p className="text-xs text-slate-500">文化資源メタデータ精緻化・構造化システム</p>
        </div>
      </div>

      <div className="flex items-center gap-3">
        <div className="flex items-center gap-2 bg-slate-100 border border-slate-200 rounded-lg px-3 py-1.5">
          <Database className="w-4 h-4 text-slate-500" />
          <span className="text-xs font-medium text-slate-600">プロジェクト:</span>
          <select
            value={activeWsId || ''}
            onChange={(e) => onSelectWorkspace(e.target.value)}
            className="bg-transparent text-sm font-semibold text-slate-800 outline-none cursor-pointer max-w-[200px] truncate"
          >
            {workspaces.map((w) => (
              <option key={w.id} value={w.id}>
                {w.name} ({w.id})
              </option>
            ))}
          </select>
        </div>

        <button
          onClick={onOpenCreateModal}
          className="flex items-center gap-1.5 px-3 py-1.5 bg-sky-600 hover:bg-sky-700 text-white rounded-lg text-xs font-semibold shadow-xs transition-colors"
        >
          <Plus className="w-3.5 h-3.5" />
          新規
        </button>
      </div>
    </header>
  );
};

