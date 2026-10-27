# -*- coding: utf-8 -*-
"""
グローバル・パイプライン・ステータスバー コンポーネント
画面上部に配置され、パイプラインの各段階の進捗およびサバイバル件数を常時可視化します。
"""
import os
import streamlit as st
from typing import Dict, Any


def get_pipeline_metrics(paths: dict) -> Dict[str, Any]:
    """パイプラインの各段階のレコード数を高速取得（DuckDB優先）"""
    duckdb_path = paths.get('PATH_DUCKDB', '')
    raw_path = paths.get('PATH_RAW_METADATA', '')
    verified_path = paths.get('PATH_VERIFIED_JSONL', '')
    export_json_path = paths.get('PATH_EXPORT_JSON', '')

    metrics = {
        "total": 0,
        "type_pass": 0,
        "type_disc": 0,
        "rule_ok": 0,
        "rule_ng": 0,
        "rule_grey": 0,
        "final_adopted": 0,
        "has_data": False,
        "step1_done": False,
        "step2_type_done": False,
        "step2_rule_done": False,
        "step3_llm_done": False,
        "step4_review_done": False,
        "step5_export_done": False,
    }

    if duckdb_path and os.path.exists(duckdb_path):
        try:
            from modules.duckdb_manager import DuckDBManager
            db = DuckDBManager(db_path=duckdb_path)
            stats = db.get_prisma_flow_stats()
            total = stats.get("total_records", 0)
            if total > 0:
                metrics["total"] = total
                metrics["type_pass"] = stats.get("type_passed", total)
                metrics["type_disc"] = stats.get("type_discarded", 0)
                metrics["rule_ok"] = stats.get("rule_ok", 0)
                metrics["rule_ng"] = stats.get("rule_ng", 0)
                metrics["rule_grey"] = stats.get("rule_grey", 0)
                metrics["final_adopted"] = stats.get("final_adopted", 0)
                metrics["has_data"] = True
                metrics["step1_done"] = True
                metrics["step2_type_done"] = (stats.get("type_discarded", 0) > 0 or os.path.exists(paths.get('PATH_TYPE_FILTERED', '')))
                metrics["step2_rule_done"] = (stats.get("rule_ok", 0) > 0 or stats.get("rule_ng", 0) > 0)
                metrics["step3_llm_done"] = (stats.get("llm_evaluated_total", 0) > 0 or os.path.exists(paths.get('PATH_LLM_JUDGMENTS', '')))
                metrics["step4_review_done"] = os.path.exists(verified_path) and os.path.getsize(verified_path) > 0
                metrics["step5_export_done"] = os.path.exists(export_json_path) and os.path.getsize(export_json_path) > 0
                db.close()
                return metrics
            db.close()
        except Exception:
            pass

    # フォールバック (ファイル存在判定)
    if os.path.exists(raw_path) and os.path.getsize(raw_path) > 0:
        metrics["has_data"] = True
        metrics["step1_done"] = True
    if os.path.exists(paths.get('PATH_TYPE_FILTERED', '')):
        metrics["step2_type_done"] = True
    if os.path.exists(paths.get('PATH_ABOUT_FILTERED', '')) or os.path.exists(paths.get('PATH_NGRAM_FILTERED', '')):
        metrics["step2_rule_done"] = True
    if os.path.exists(paths.get('PATH_LLM_JUDGMENTS', '')):
        metrics["step3_llm_done"] = True
    if os.path.exists(verified_path) and os.path.getsize(verified_path) > 0:
        metrics["step4_review_done"] = True
    if os.path.exists(export_json_path) and os.path.getsize(export_json_path) > 0:
        metrics["step5_export_done"] = True

    return metrics


def render_global_pipeline_bar(paths: dict, current_choice: str, workspace_name: str):
    """
    メイン領域上部にグローバル・パイプライン・ステータスバーを描画
    """
    # プロジェクト管理画面では表示を省略
    if current_choice == "プロジェクト・履歴マネージャー":
        return

    m = get_pipeline_metrics(paths)

    # 現在のアクティブステップを特定
    active_idx = -1
    if "Step 1" in current_choice:
        active_idx = 0
    elif "Step 2-A" in current_choice:
        active_idx = 1
    elif "Step 2-B" in current_choice or "Step 2-C" in current_choice:
        active_idx = 2
    elif "Step 3" in current_choice:
        active_idx = 3
    elif "Step 4" in current_choice:
        active_idx = 4
    elif "Step 5" in current_choice:
        active_idx = 5

    # 各ノードのステータスとラベル
    nodes = [
        {
            "step": "Step 1: 収集",
            "count": f"{m['total']:,} 件" if m["total"] > 0 else ("完了" if m["step1_done"] else "未着手"),
            "completed": m["step1_done"],
            "idx": 0
        },
        {
            "step": "Step 2-A: 種別",
            "count": f"残存 {m['type_pass']:,} 件" if m["total"] > 0 and m["step2_type_done"] else ("適用済" if m["step2_type_done"] else "未着手"),
            "completed": m["step2_type_done"],
            "idx": 1
        },
        {
            "step": "Step 2-B/C: ルール",
            "count": f"合格 {m['rule_ok']:,} 件" if m["rule_ok"] > 0 else ("設定済" if m["step2_rule_done"] else "未着手"),
            "completed": m["step2_rule_done"],
            "idx": 2
        },
        {
            "step": "Step 3: LLM推論",
            "count": f"保留 {m['rule_grey']:,} 件" if m["rule_grey"] > 0 else ("推論済" if m["step3_llm_done"] else "未着手"),
            "completed": m["step3_llm_done"],
            "idx": 3
        },
        {
            "step": "Step 4: 査読",
            "count": f"確定 {m['final_adopted']:,} 件" if m["final_adopted"] > 0 else ("確定済" if m["step4_review_done"] else "未確定"),
            "completed": m["step4_review_done"],
            "idx": 4
        },
        {
            "step": "Step 5: 出力",
            "count": "出力完了" if m["step5_export_done"] else "未出力",
            "completed": m["step5_export_done"],
            "idx": 5
        }
    ]

    # サバイバル集約メッセージ
    if m["final_adopted"] > 0:
        surv_text = f"最終確定採択: <span class='pipeline-survival-count'>{m['final_adopted']:,}</span> 件 （初期母集団: {m['total']:,} 件）"
    elif m["total"] > 0:
        cur_active = m["type_pass"] if m["type_pass"] > 0 else m["total"]
        surv_text = f"現在残存母集団: <span class='pipeline-survival-count'>{cur_active:,}</span> 件 （初期収集: {m['total']:,} 件）"
    else:
        surv_text = "初期データ未取得 （Step 1 より開始してください）"

    # HTML構築
    nodes_html = []
    for i, node in enumerate(nodes):
        state_class = "pending"
        if node["idx"] == active_idx:
            state_class = "active"
        elif node["completed"]:
            state_class = "completed"

        node_box = f"""
        <div class="pipeline-step-node {state_class}">
            <span class="pipeline-step-title">{node['step']}</span>
            <span class="pipeline-step-count">{node['count']}</span>
        </div>
        """
        nodes_html.append(node_box)
        if i < len(nodes) - 1:
            nodes_html.append("<span class='pipeline-arrow'>-></span>")

    steps_content = "".join(nodes_html)

    bar_html = f"""
    <div class="pipeline-bar-container">
        <div class="pipeline-bar-header">
            <span class="pipeline-ws-tag">
                <span class="status-badge status-badge-neutral">研究プロジェクト</span>
                <b>{workspace_name}</b>
            </span>
            <span class="pipeline-survival-metrics">{surv_text}</span>
        </div>
        <div class="pipeline-steps-wrapper">
            {steps_content}
        </div>
    </div>
    """

    st.markdown(bar_html, unsafe_allow_html=True)
