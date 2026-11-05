// -*- coding: utf-8 -*-
/**
 * JPS Refine Studio API クライアント
 */
import {
  WorkspaceMeta,
  DashboardStats,
  JobProgress,
  PaginatedRecordsResponse,
  ReviewMetrics,
  FacetsResponse,
  RuleImpactResponse,
  QueryExpandResponse,
  ClusterItem,
  TypeStatsItem,
  SuffixClusterItem
} from '../types/api';

const BASE_URL = '/api';

async function fetchJson<T>(url: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE_URL}${url}`, {
    headers: {
      'Content-Type': 'application/json',
      ...(options?.headers || {})
    },
    ...options
  });
  if (!res.ok) {
    let errText = res.statusText;
    try {
      const errJson = await res.json();
      errText = errJson.detail || JSON.stringify(errJson);
    } catch {
      // fallback
    }
    throw new Error(errText);
  }
  return res.json();
}

export const api = {
  // ワークスペース
  getWorkspaces: () => fetchJson<WorkspaceMeta[]>('/workspaces'),
  getWorkspace: (id: string) => fetchJson<WorkspaceMeta>(`/workspaces/${id}`),
  createWorkspace: (data: { id: string; name: string; description?: string; research_theme?: string; clone_from?: string | null }) =>
    fetchJson<WorkspaceMeta>('/workspaces', { method: 'POST', body: JSON.stringify(data) }),
  deleteWorkspace: (id: string) => fetchJson<{ message: string }>(`/workspaces/${id}`, { method: 'DELETE' }),
  getDashboardStats: (id: string) => fetchJson<DashboardStats>(`/workspaces/${id}/dashboard`),
  getSnapshots: (id: string) => fetchJson<any[]>(`/workspaces/${id}/snapshots`),
  createSnapshot: (id: string, name: string, description?: string) =>
    fetchJson<any>(`/workspaces/${id}/snapshots`, { method: 'POST', body: JSON.stringify({ name, description }) }),
  restoreSnapshot: (id: string, snapId: string) =>
    fetchJson<any>(`/workspaces/${id}/snapshots/${snapId}/restore`, { method: 'POST' }),

  // ジョブ制御
  getJobs: (workspaceId?: string) =>
    fetchJson<JobProgress[]>(`/jobs${workspaceId ? `?workspace_id=${workspaceId}` : ''}`),
  getJob: (jobId: string) => fetchJson<JobProgress>(`/jobs/${jobId}`),
  stopJob: (jobId: string) => fetchJson<{ message: string }>(`/jobs/${jobId}/stop`, { method: 'POST' }),

  // レコード & 査読ポータル
  getRecords: (wsId: string, params: {
    page?: number;
    page_size?: number;
    filter_status?: string;
    search_query?: string;
    stage?: string;
    target_type?: string;
    provider?: string;
    year_from?: number;
    year_to?: number;
    has_image?: boolean;
    creator?: string;
    filter_source?: string;
  }) => {
    const q = new URLSearchParams();
    if (params.page) q.set('page', params.page.toString());
    if (params.page_size) q.set('page_size', params.page_size.toString());
    if (params.filter_status) q.set('filter_status', params.filter_status);
    if (params.search_query) q.set('search_query', params.search_query);
    if (params.stage) q.set('stage', params.stage);
    if (params.target_type) q.set('target_type', params.target_type);
    if (params.provider) q.set('provider', params.provider);
    if (params.year_from !== undefined) q.set('year_from', params.year_from.toString());
    if (params.year_to !== undefined) q.set('year_to', params.year_to.toString());
    if (params.has_image !== undefined) q.set('has_image', params.has_image.toString());
    if (params.creator) q.set('creator', params.creator);
    if (params.filter_source) q.set('filter_source', params.filter_source);
    return fetchJson<PaginatedRecordsResponse>(`/workspaces/${wsId}/records?${q.toString()}`);
  },
  getReviewMetrics: (wsId: string) => fetchJson<ReviewMetrics>(`/workspaces/${wsId}/records/metrics`),
  getFacets: (wsId: string) => fetchJson<FacetsResponse>(`/workspaces/${wsId}/records/facets`),
  updateDecision: (wsId: string, recordId: string, human_decision: string | null) =>
    fetchJson<{ message: string }>(`/workspaces/${wsId}/records/decision`, {
      method: 'POST',
      body: JSON.stringify({ record_id: recordId, human_decision })
    }),
  exportVerified: (wsId: string) =>
    fetchJson<{ message: string; count: number }>(`/workspaces/${wsId}/records/export-verified`, { method: 'POST' }),

  // ルール管理 & クラスタリング
  getTypeRules: (wsId: string) =>
    fetchJson<{ rules: { NG: string[]; OK: string[] }; stats: TypeStatsItem[] }>(`/workspaces/${wsId}/rules/type`),
  saveTypeRules: (wsId: string, NG: string[], OK: string[] = []) =>
    fetchJson<{ message: string }>(`/workspaces/${wsId}/rules/type`, {
      method: 'PUT',
      body: JSON.stringify({ NG, OK })
    }),
  getAboutRules: (wsId: string) => fetchJson<Record<string, string>>(`/workspaces/${wsId}/rules/about`),
  saveAboutRules: (wsId: string, rules: Record<string, string>) =>
    fetchJson<{ message: string }>(`/workspaces/${wsId}/rules/about`, {
      method: 'PUT',
      body: JSON.stringify({ rules })
    }),
  getAboutClusters: (wsId: string) => fetchJson<ClusterItem[]>(`/workspaces/${wsId}/rules/about/clusters`),
  getNgramRules: (wsId: string) => fetchJson<Record<string, string>>(`/workspaces/${wsId}/rules/ngram`),
  saveNgramRules: (wsId: string, rules: Record<string, string>) =>
    fetchJson<{ message: string }>(`/workspaces/${wsId}/rules/ngram`, {
      method: 'PUT',
      body: JSON.stringify({ rules })
    }),
  getNgramRankings: (wsId: string) =>
    fetchJson<{ rankings: Record<string, { word: string; count: number }[]>; suffix_clusters: SuffixClusterItem[] }>(`/workspaces/${wsId}/rules/ngram/rankings`),

  // ★ ルール影響レコード完全一覧 (ページネーション & 衝突警告)
  queryImpactRecords: (wsId: string, body: {
    rule_type: string;
    rule_value: string;
    rule_action?: string;
    page?: number;
    page_size?: number;
    search_query?: string;
    warning_only?: boolean;
  }) => fetchJson<RuleImpactResponse>(`/workspaces/${wsId}/rules/impact-records`, {
    method: 'POST',
    body: JSON.stringify(body)
  }),

  // ルール適用
  applyRules: (wsId: string) =>
    fetchJson<{ job_id: string; message: string }>(`/workspaces/${wsId}/rules/apply`, { method: 'POST' }),

  // SPARQL取得 & LLM
  expandQuery: (wsId: string, data: { theme: string; existing_keywords?: string[]; provider?: string; api_key?: string; model?: string }) =>
    fetchJson<QueryExpandResponse>(`/workspaces/${wsId}/fetch/expand-query`, { method: 'POST', body: JSON.stringify(data) }),
  startFetch: (wsId: string, data: {
    keywords: string[];
    ndc_codes?: string[];
    exclude_ndc_codes?: string[];
    title_regex?: string;
    desc_regex?: string;
    domain_definition?: string;
    batch_size?: number;
    resume?: boolean;
  }) => fetchJson<{ job_id: string; message: string }>(`/workspaces/${wsId}/fetch/start`, { method: 'POST', body: JSON.stringify(data) }),
  startLlm: (wsId: string, data: {
    domain_definition: string;
    provider?: string;
    api_base?: string;
    api_key?: string;
    model?: string;
    max_workers?: number;
    limit?: number;
    stage2?: boolean;
  }) => fetchJson<{ job_id: string; message: string }>(`/workspaces/${wsId}/llm/start`, { method: 'POST', body: JSON.stringify(data) }),

  // NDC SPARQL 解決
  resolveNdcBatch: (ndc_numbers: string[]) =>
    fetchJson<Record<string, { label: string; is_exact: boolean; parent_code: string }>>('/ndc/resolve-batch', {
      method: 'POST',
      body: JSON.stringify({ ndc_numbers })
    })
};
