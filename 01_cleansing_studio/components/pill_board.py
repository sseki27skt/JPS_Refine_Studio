import math
import urllib.parse
import streamlit as st
import streamlit.components.v1 as components
from components.file_utils import make_rich_search_links_md, make_rich_search_links

@st.fragment
def render_pill_board(
    items: list, 
    active_samples_map: dict, 
    current_ng: set, 
    current_ok: set, 
    draft_dict: dict, 
    click_action_mode: str,
    page_session_key: str,
    parent_rule_func=None,
    items_per_page: int = 36
):
    """
    キーワード/フレーズのピル（Pill）一覧をインタラクティブかつ爆速描画する汎用コンポーネント
    スクロールに応じた完全自動追加読み込み（Auto Infinite Scroll）に対応
    """
    total_items = len(items)
    if total_items == 0:
        st.info("条件に一致する判定対象キーワードはありません。")
        return

    limit_key = f"limit_{page_session_key}"
    if limit_key not in st.session_state:
        st.session_state[limit_key] = items_per_page
    
    cur_limit = min(total_items, int(st.session_state.get(limit_key, items_per_page)))
    st.session_state[limit_key] = cur_limit

    # 操作・表示ステータスバー
    st.markdown(
        f"<div style='padding: 4px 0 8px 0;'><b>📋 表示中: {cur_limit:,} 件 ／ 全 {total_items:,} 件</b> "
        f"<span style='color: #4CAF50; font-size: 0.85rem; margin-left: 8px;'>⚡ スクロールで自動追加読み込み</span></div>", 
        unsafe_allow_html=True
    )

    page_items = items[:cur_limit]

    # ボードコンテナ (縦スクロール可能)
    board_container = st.container(height=600)
    with board_container:
        grid_cols = st.columns(3)
        for idx, item in enumerate(page_items):
            col = grid_cols[idx % 3]
            
            w = item[0]
            cnt = item[1]
            raw_samples = item[2] if len(item) > 2 else []

            parent_type, parent_word = (None, None)
            if parent_rule_func:
                parent_type, parent_word = parent_rule_func(w)

            active_info = active_samples_map.get(w, {})
            if isinstance(active_info, dict):
                eff_c = active_info.get("eff_cnt", 0)
                display_samples = active_info.get("samples", [])
            elif isinstance(active_info, list):
                eff_c = len(active_info)
                display_samples = active_info
            else:
                eff_c = cnt
                display_samples = raw_samples

            from components.ndc_utils import format_about_keyword_display
            disp_w = format_about_keyword_display(w, max_label_len=24)

            cnt_str = f"({cnt}件)" if eff_c == cnt else f"(未判定 {eff_c}件 / 全{cnt}件)"

            # ツールチップ用テキスト
            sample_titles = []
            for s in display_samples[:10]:
                if isinstance(s, dict):
                    sample_titles.append(s.get("title", ""))
                else:
                    sample_titles.append(str(s))

            sample_lines = [f"• {t}" for t in sample_titles if t]
            sample_header = f"【『{disp_w}』の未判定資料例 ({len(sample_lines)}件表示)】:\n" if sample_lines else f"【『{disp_w}』の件数: {cnt_str}】\n"
            tooltip_txt = sample_header + "\n".join(sample_lines)

            # ドラフト ＆ 既存ルールのステータス判定
            draft_status = draft_dict.get(w)
            if draft_status == "NG":
                is_ng, is_ok = True, False
                d_tag = " [仮NG]"
            elif draft_status == "OK":
                is_ng, is_ok = False, True
                d_tag = " [仮OK]"
            elif draft_status == "RESET":
                is_ng, is_ok = False, False
                d_tag = " [仮未判定]"
            else:
                is_ng = w in current_ng
                is_ok = w in current_ok
                d_tag = ""

            if is_ng:
                btn_label = f"🚫 {disp_w} {cnt_str}{d_tag}"
            elif is_ok:
                btn_label = f"✅ {disp_w} {cnt_str}{d_tag}"
            elif parent_type == "NG":
                btn_label = f"🚫 {disp_w} [親:{parent_word}] {cnt_str}{d_tag}"
            elif parent_type == "OK":
                btn_label = f"✅ {disp_w} [親:{parent_word}] {cnt_str}{d_tag}"
            else:
                btn_label = f"❓ {disp_w} {cnt_str}{d_tag}"

            c_btn, c_pop = col.columns([6, 1])
            with c_btn:
                if st.button(btn_label, key=f"btn_pills_{page_session_key}_{w}_{idx}", help=tooltip_txt, use_container_width=True):
                    mode_str = str(click_action_mode)
                    if "NG" in mode_str:
                        draft_dict[w] = "NG"
                    elif "OK" in mode_str:
                        draft_dict[w] = "OK"
                    elif "未判定" in mode_str or "RESET" in mode_str or "リセット" in mode_str:
                        draft_dict[w] = "RESET"
                    else:
                        draft_dict[w] = "NG"
                    st.rerun(scope="fragment")

            with c_pop:
                with st.popover("🔍", help=f"『{w}』の外部検索・該当資料詳細"):
                    st.markdown(f"### 🔍 『{w}』")
                    st.markdown(make_rich_search_links_md(w))
                    st.markdown(f"- **件数内訳**: 未判定 **{eff_c:,} 件** ／ 全 **{cnt:,} 件**")
                    if parent_type:
                        st.info(f"親ルール継承: **{parent_type}** (親パターン: 『{parent_word}』)")

                    # ポップオーバー内ダイレクト判定
                    c_act_ng, c_act_ok, c_act_rst = st.columns(3)
                    with c_act_ng:
                        if st.button("🚫 NGに設定", key=f"pop_ng_{page_session_key}_{w}_{idx}", use_container_width=True, type="primary" if is_ng else "secondary"):
                            draft_dict[w] = "NG"
                            st.rerun(scope="fragment")
                    with c_act_ok:
                        if st.button("✅ OKに設定", key=f"pop_ok_{page_session_key}_{w}_{idx}", use_container_width=True, type="primary" if is_ok else "secondary"):
                            draft_dict[w] = "OK"
                            st.rerun(scope="fragment")
                    with c_act_rst:
                        if st.button("🔄 リセット", key=f"pop_rst_{page_session_key}_{w}_{idx}", use_container_width=True):
                            draft_dict[w] = "RESET"
                            st.rerun(scope="fragment")

                    st.write("---")
                    st.caption(f"📄 **該当資料一覧 (全 {len(display_samples):,} 件をスクロール確認可能)**:")
                    with st.container(height=320):
                        if not display_samples:
                            st.info("該当する資料サンプルはありません。")
                        
                        from components.file_utils import make_jps_item_url, make_jps_keyword_url
                        for s in display_samples:
                            if isinstance(s, dict):
                                s_title = s.get("title") or "（無題）"
                                s_id = s.get("id", "")
                                s_desc = s.get("desc", "")
                                s_creator = s.get("creator", "")

                                item_link = make_jps_item_url(s_id, s_title)
                                title_link = f"[📖 **{s_title}**]({item_link})"

                                meta_parts = []
                                if s_creator:
                                    meta_parts.append(f"著者: `{s_creator}`")
                                if s_id:
                                    meta_parts.append(f"[🔗 JPS]({item_link})")
                                
                                meta_str = f" <span style='color: #888; font-size: 0.8rem;'>({' ｜ '.join(meta_parts)})</span>" if meta_parts else ""
                                st.markdown(f"• {title_link}{meta_str}", unsafe_allow_html=True)
                            else:
                                s_str = str(s)
                                jps_search_url = make_jps_keyword_url(s_str)
                                st.markdown(f"• [📖 **{s_str}**]({jps_search_url})")

    # ボトムの追加読み込みバー
    if cur_limit < total_items:
        btn_txt = f"🔽 次の {items_per_page} 件を読み込む (現在 {cur_limit:,} 件 / 全 {total_items:,} 件)"
        trigger_btn_id = f"load_more_{page_session_key}_{cur_limit}"
        if st.button(btn_txt, key=trigger_btn_id, type="secondary", use_container_width=True):
            st.session_state[limit_key] = min(total_items, cur_limit + items_per_page)
            st.rerun(scope="fragment")
    else:
        st.caption(f"✅ 全 {total_items:,} 件のキーワードを表示完了しました。")

