// -*- coding: utf-8 -*-
/**
 * 選択中ワークスペースの管理フック
 */
import { useState, useEffect } from 'react';
import { WorkspaceMeta } from '../types/api';
import { api } from '../api/client';

export function useWorkspace() {
  const [workspaces, setWorkspaces] = useState<WorkspaceMeta[]>([]);
  const [activeWsId, setActiveWsId] = useState<string | null>(() => {
    return localStorage.getItem('jps_active_ws_id');
  });
  const [loading, setLoading] = useState(true);

  const fetchWorkspaces = async () => {
    try {
      setLoading(true);
      const list = await api.getWorkspaces();
      setWorkspaces(list);
      if (list.length > 0) {
        // 現在選択中のIDが存在しなければ先頭を選択
        if (!activeWsId || !list.some(w => w.id === activeWsId)) {
          const firstId = list[0].id;
          setActiveWsId(firstId);
          localStorage.setItem('jps_active_ws_id', firstId);
        }
      } else {
        setActiveWsId(null);
        localStorage.removeItem('jps_active_ws_id');
      }
    } catch (err) {
      console.error('Failed to load workspaces:', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchWorkspaces();
  }, []);

  const selectWorkspace = (wsId: string) => {
    setActiveWsId(wsId);
    localStorage.setItem('jps_active_ws_id', wsId);
  };

  const activeWorkspace = workspaces.find(w => w.id === activeWsId) || null;

  return {
    workspaces,
    activeWsId,
    activeWorkspace,
    loading,
    selectWorkspace,
    refreshWorkspaces: fetchWorkspaces
  };
}

