// -*- coding: utf-8 -*-
/**
 * JPS Refine Studio フロントエンド TypeScript 型定義
 */

export interface WorkspaceMeta {
  id: string;
  name: string;
  description: string;
  research_theme: string;
  created_at: string;
  updated_at: string;
  disk_size_bytes: number;
  has_raw_metadata: boolean;
  has_duckdb: boolean;
  cloned_from?: string | null;
}

export interface DashboardStats {
  step1_raw: number;
  step2a_type_survivors: number;
  step2b_about_survivors: number;
  step2c_ngram_survivors: number;
  step3_llm_evaluated: number;
  step4_human_reviewed: number;
  step5_export_ready: number;
  total_records: number;
  active_job?: JobProgress | null;
}

export type JobStatusType = 'IDLE' | 'PENDING' | 'RUNNING' | 'COMPLETED' | 'STOPPED' | 'FAILED';

export interface JobProgress {
  job_id: string;
  workspace_id: string;
  type: string;
  stage: string;
  status: JobStatusType;
  current: number;
  total: number;
  percentage: number;
  eta_seconds?: number | null;
  error_message?: string | null;
  started_at?: string | null;
  updated_at?: string | null;
  extra_data?: Record<string, any> | null;
}

export interface RecordItem {
  id: string;
  title: string;
  description: string;
  about_list: string[];
  type_list: string[];
  provider?: string;
  published_year?: number | null;
  has_image: boolean;
  creator?: string;
  final_decision: 'OK' | 'NG' | 'GREY';
  status: string;
  cur_status: string;
  human_decision?: string | null;
  is_override: boolean;
  is_conflict?: boolean;
  matched_reason?: string;
  primary_reason?: string;
  reasons?: string;
  type_status?: string | null;
  type_reason?: string | null;
  about_status?: string | null;
  about_reason?: string | null;
  ngram_status?: string | null;
  ngram_reason?: string | null;
  llm_status?: string | null;
  llm_target?: boolean | null;
  llm_reason?: string;
  external_info?: string;
  raw_item?: Record<string, any>;
}

export interface PaginatedRecordsResponse {
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
  records: RecordItem[];
}

export interface ReviewMetrics {
  total: number;
  passed_cnt: number;
  reject_cnt: number;
  override_cnt: number;
  null_cnt: number;
}

export interface FacetItem {
  name: string;
  count: number;
}

export interface EraDistributionItem {
  era: string;
  count: number;
}

export interface FacetsResponse {
  top_providers: FacetItem[];
  era_distribution: EraDistributionItem[];
  has_image_count: number;
  no_image_count: number;
}

export interface TypeStatsItem {
  type_uri: string;
  short_label: string;
  count: number;
  pct: number;
  sample_titles: string[];
}

export interface ClusterSubItem {
  id: string;
  name: string;
  count: number;
  keywords: string[];
}

export interface ClusterItem {
  cluster_id: string;
  name: string;
  category: string;
  keywords: string[];
  total_count: number;
  resolved_label?: string | null;
  sub_clusters?: ClusterSubItem[] | null;
}

export interface RuleImpactResponse {
  total_impact_count: number;
  warning_conflict_count: number;
  page: number;
  page_size: number;
  total_pages: number;
  records: RecordItem[];
}

export interface QueryExpandResponse {
  keywords: string[];
  ndc_codes: string[];
  exclude_ndc_codes: string[];
  domain_definition: string;
  title_regex: string;
  desc_regex: string;
}

export interface SuffixClusterItem {
  cluster_id: string;
  name: string;
  suffix: string;
  total_count: number;
  items: { word: string; count: number }[];
}

