import math
import urllib.parse
import streamlit as st
import streamlit.components.v1 as components
from components.file_utils import make_rich_search_links_md, make_rich_search_links

def render_pill_board(
    items: list, 
    active_samples_map: dict, 
    current_ng: set, 
    current_ok: set, 
    draft_dict: dict, 
    click_action_mode: str,
    page_session_key: str,
    parent_rule_func=None,
    items_per_page: int = 36,
    on_confirm_save=None
):
    """
    キーワード/フレーズのピル（Pill）一覧をインタラクティブかつ爆速描画する汎用コンポーネント
    スクロールに応じた完全自動追加読み込み（Auto Infinite Scroll）に対応
    """
    total_items = len(items)
    if total_items == 0:
        st.info("条件に一致する判定対象キーワードはありません。")
        return

    # ツールチップ残存バグ防止 CSS
    st.markdown(
        """
        <style>
        /* BaseWeb Tooltip 残存防止: マウスイベントを透過させてゴースト化を防止 */
        div[data-baseweb="tooltip"], div[role="tooltip"] {
            pointer-events: none !important;
            transition: opacity 0.1s ease-out !important;
        }
        </style>
        """,
        unsafe_allow_html=True
    )

    limit_key = f"limit_{page_session_key}"
    if limit_key not in st.session_state:
        st.session_state[limit_key] = items_per_page
    
    cur_limit = min(total_items, int(st.session_state.get(limit_key, items_per_page)))
    st.session_state[limit_key] = cur_limit

    # 仮選択件数のバッジ表示
    draft_cnt = len(draft_dict) if isinstance(draft_dict, dict) else 0

    # 操作・表示ステータスバー（仮選択がある場合はその場で即時確定保存できるボタンを表示）
    if draft_cnt > 0 and on_confirm_save is not None:
        c_stat, c_save = st.columns([3, 2])
        with c_stat:
            st.markdown(
                f"<div style='padding: 6px 0;'><b>📋 表示中: {cur_limit:,} 件 ／ 全 {total_items:,} 件</b> "
                f"<span style='color: #ff4b4b; font-weight: bold; margin-left: 8px;'>⚡ {draft_cnt} 件を仮選択中</span></div>",
                unsafe_allow_html=True
            )
        with c_save:
            if st.button(
                f"⚡ 仮設定 ({draft_cnt}件) を確定して保存", 
                key=f"btn_inline_save_{page_session_key}", 
                type="primary", 
                use_container_width=True
            ):
                on_confirm_save()
    else:
        draft_tag = f" ｜ <span style='color: #ff4b4b; font-weight: bold;'>⚡ {draft_cnt} 件を仮選択中</span>" if draft_cnt > 0 else ""
        st.markdown(
            f"<div style='padding: 4px 0 8px 0;'><b>📋 表示中: {cur_limit:,} 件 ／ 全 {total_items:,} 件</b> "
            f"{draft_tag}"
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

            # ツールチップ用テキスト (最大2件のコンパクトプレビュー)
            sample_titles = []
            for s in display_samples[:2]:
                if isinstance(s, dict):
                    sample_titles.append(s.get("title", ""))
                else:
                    sample_titles.append(str(s))

            sample_lines = [f"• {t[:40]}..." if len(t) > 40 else f"• {t}" for t in sample_titles if t]
            sample_header = f"【『{disp_w}』 {cnt_str}】\n"
            if sample_lines:
                tooltip_txt = sample_header + "\n".join(sample_lines) + "\n※クリックで切替 / 右の🔍で詳細"
            else:
                tooltip_txt = sample_header + f"クリックで切替 / 現在アクション: 【{click_action_mode}】"

            # ドラフト ＆ 既存ルールのステータス判定
            draft_status = draft_dict.get(w)
            if draft_status == "NG":
                is_ng, is_ok = True, False
                d_tag = " ⚡[仮NG]"
            elif draft_status == "OK":
                is_ng, is_ok = False, True
                d_tag = " ⚡[仮OK]"
            elif draft_status == "RESET":
                is_ng, is_ok = False, False
                d_tag = " 🔄[仮解除]"
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

            # トグル対応のクリックハンドラ
            def _handle_pill_click(word=w, mode_str=str(click_action_mode), cur_draft=draft_status, cur_ng=is_ng, cur_ok=is_ok):
                target_status = "NG"
                if "OK" in mode_str:
                    target_status = "OK"
                elif "未判定" in mode_str or "RESET" in mode_str or "リセット" in mode_str:
                    target_status = "RESET"

                # 既に同じ仮設定がある場合はトグル解除
                if cur_draft == target_status:
                    draft_dict.pop(word, None)
                elif cur_draft is not None:
                    # 別の仮設定がある場合は上書き
                    draft_dict[word] = target_status
                else:
                    # まだ仮設定がない場合
                    if target_status == "NG" and cur_ng:
                        # 既にNGのものをクリックした場合は解除を仮設定
                        draft_dict[word] = "RESET"
                    elif target_status == "OK" and cur_ok:
                        # 既にOKのものをクリックした場合は解除を仮設定
                        draft_dict[word] = "RESET"
                    else:
                        draft_dict[word] = target_status

            c_btn, c_pop = col.columns([6, 1])
            with c_btn:
                # 仮選択中は目立つように primary 表示
                btn_type = "primary" if draft_status in ("NG", "OK") else "secondary"
                st.button(
                    btn_label, 
                    key=f"btn_pills_{page_session_key}_{w}", 
                    help=tooltip_txt, 
                    type=btn_type,
                    use_container_width=True,
                    on_click=_handle_pill_click,
                    args=(w, str(click_action_mode), draft_status, is_ng, is_ok)
                )

            with c_pop:
                with st.popover("🔍", help=f"『{w}』の外部検索・該当資料詳細"):
                    st.markdown(f"### 🔍 『{w}』")
                    st.markdown(make_rich_search_links_md(w))
                    st.markdown(f"- **件数内訳**: 未判定 **{eff_c:,} 件** ／ 全 **{cnt:,} 件**")
                    if parent_type:
                        st.info(f"親ルール継承: **{parent_type}** (親パターン: 『{parent_word}』)")

                    from components.file_utils import make_jps_item_url, make_jps_keyword_url
                    sample_md_parts = []
                    for s in display_samples[:8]:
                        if isinstance(s, dict):
                            s_title = s.get("title") or "（無題）"
                            s_id = s.get("id", "")
                            s_creator = s.get("creator", "")
                            item_link = make_jps_item_url(s_id, s_title)
                            meta_info = f" `({s_creator})`" if s_creator else ""
                            sample_md_parts.append(f"• [📖 **{s_title}**]({item_link}){meta_info}")
                        else:
                            s_str = str(s)
                            jps_search_url = make_jps_keyword_url(s_str)
                            sample_md_parts.append(f"• [📖 **{s_str}**]({jps_search_url})")

                    samples_text = "\n".join(sample_md_parts) if sample_md_parts else "該当する資料サンプルはありません。"
                    st.markdown(f"📄 **該当資料例 (最大8件)**:\n\n{samples_text}")

    # ボトムの追加読み込みバー
    if cur_limit < total_items:
        btn_txt = f"🔽 次の {items_per_page} 件を読み込む (現在 {cur_limit:,} 件 / 全 {total_items:,} 件)"
        trigger_btn_id = f"load_more_{page_session_key}_{cur_limit}"
        def _load_more():
            st.session_state[limit_key] = min(total_items, cur_limit + items_per_page)
        st.button(btn_txt, key=trigger_btn_id, type="secondary", use_container_width=True, on_click=_load_more)
    else:
        st.caption(f"✅ 全 {total_items:,} 件のキーワードを表示完了しました。")

