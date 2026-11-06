# -*- coding: utf-8 -*-
"""
End-to-End 統合検証スクリプト
"""
import sys
import os

# backend ディレクトリをパスに追加
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "backend")))

from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def test_full_pipeline():
    print("=== [1] ワークスペース一覧取得 ===")
    res = client.get("/api/workspaces")
    assert res.status_code == 200, res.text
    workspaces = res.json()
    print(f"ワークスペース件数: {len(workspaces)}")
    ws_ids = [w["id"] for w in workspaces]
    print(f"ワークスペースID一覧: {ws_ids}")
    assert "score4gagaku" in ws_ids

    ws_id = "score4gagaku"

    print(f"\n=== [2] {ws_id} のダッシュボード集計取得 ===")
    res = client.get(f"/api/workspaces/{ws_id}/dashboard")
    assert res.status_code == 200, res.text
    stats = res.json()
    print(f"総レコード数: {stats.get('total_records')}")
    print(f"PRISMAフロー: Raw={stats.get('step1_raw')}, Type生存={stats.get('step2a_type_survivors')}, About生存={stats.get('step2b_about_survivors')}, Ngram生存={stats.get('step2c_ngram_survivors')}, LLM評価={stats.get('step3_llm_evaluated')}, 査読済={stats.get('step4_human_reviewed')}, 確定出力={stats.get('step5_export_ready')}")
    assert stats.get("total_records") > 0

    print(f"\n=== [3] Step 2-A: Type ルール & 統計取得 ===")
    res = client.get(f"/api/workspaces/{ws_id}/rules/type")
    assert res.status_code == 200, res.text
    type_data = res.json()
    print(f"Type統計件数: {len(type_data.get('stats', []))}")
    print(f"NGルール件数: {len(type_data.get('rules', {}).get('NG', []))}")

    print(f"\n=== [4] Step 2-B: About NDC階層ツリー & 典拠クラスタ取得 ===")
    res = client.get(f"/api/workspaces/{ws_id}/rules/about/clusters")
    assert res.status_code == 200, res.text
    clusters = res.json()
    print(f"検出クラスタ件数: {len(clusters)}")
    ndc_clusters = [c for c in clusters if c["category"].startswith("NDC")]
    authority_clusters = [c for c in clusters if not c["category"].startswith("NDC")]
    print(f"  - NDCクラスタ数: {len(ndc_clusters)}")
    print(f"  - 典拠クラスタ数: {len(authority_clusters)}")

    print(f"\n=== [5] Step 2-C: N-gram ランキング & 接尾辞クラスタ取得 ===")
    res = client.get(f"/api/workspaces/{ws_id}/rules/ngram/rankings")
    assert res.status_code == 200, res.text
    ngram_data = res.json()
    print(f"接尾辞クラスタグループ数: {len(ngram_data.get('suffix_clusters', []))}")
    for sc in ngram_data.get('suffix_clusters', [])[:3]:
        print(f"  - 末尾パターン: 「{sc['name']}」 (件数: {sc['total_count']}, 語句数: {len(sc['items'])})")

    print(f"\n=== [6] ★ ルール影響レコード完全一覧 & 衝突警告検証 ===")
    # 雅楽で影響レコードを検索
    res = client.post(f"/api/workspaces/{ws_id}/rules/impact-records", json={
        "rule_type": "about",
        "rule_value": "雅楽",
        "rule_action": "NG",
        "page": 1,
        "page_size": 20,
        "search_query": "",
        "warning_only": False
    })
    assert res.status_code == 200, res.text
    impact_page1 = res.json()
    total_impact = impact_page1["total_impact_count"]
    warning_conflict = impact_page1["warning_conflict_count"]
    print(f"「雅楽」除外時の影響全レコード件数: {total_impact}")
    print(f"「雅楽」除外時の巻き添え衝突警告件数 (確定OKレコード): {warning_conflict}")
    print(f"Page 1 レコード件数: {len(impact_page1['records'])}")
    assert total_impact > 0

    if total_impact > 20:
        # 51件目以降も取得できるページネーション検証
        res = client.post(f"/api/workspaces/{ws_id}/rules/impact-records", json={
            "rule_type": "about",
            "rule_value": "雅楽",
            "rule_action": "NG",
            "page": 2,
            "page_size": 20,
            "search_query": "",
            "warning_only": False
        })
        assert res.status_code == 200
        impact_page2 = res.json()
        print(f"Page 2 レコード件数: {len(impact_page2['records'])}")
        assert len(impact_page2['records']) > 0
        # 1ページ目と2ページ目のレコードIDが重複していないことを確認
        ids_p1 = {r["id"] for r in impact_page1["records"]}
        ids_p2 = {r["id"] for r in impact_page2["records"]}
        assert len(ids_p1.intersection(ids_p2)) == 0
        print("  ✓ ページネーション整合性確認: ページ間のID重複なし")

    # 衝突警告のみ抽出タブの検証
    res = client.post(f"/api/workspaces/{ws_id}/rules/impact-records", json={
        "rule_type": "about",
        "rule_value": "雅楽",
        "rule_action": "NG",
        "page": 1,
        "page_size": 20,
        "search_query": "",
        "warning_only": True
    })
    assert res.status_code == 200
    warn_page = res.json()
    print(f"衝突警告のみ抽出結果: {len(warn_page['records'])} 件")
    for r in warn_page['records'][:3]:
        print(f"  - 巻き添えレコード: ID={r['id']}, Title={r['title'][:30]}")

    print(f"\n=== [7] Step 4: 査読ポータル (レコード一覧 & ファセット & 手動判定) ===")
    res = client.get(f"/api/workspaces/{ws_id}/records?page=1&page_size=10")
    assert res.status_code == 200, res.text
    records_res = res.json()
    print(f"取得レコード数: {len(records_res['records'])}, 全体件数: {records_res['total']}")
    target_record = records_res['records'][0]
    target_id = target_record['id']
    orig_decision = target_record['human_decision']
    print(f"検証対象レコード: ID={target_id}, Title={target_record['title'][:30]}, 現在判定={orig_decision}")

    # 手動オーバーライド更新 (合格) - POST /decision (ボディ指定)
    res = client.post(f"/api/workspaces/{ws_id}/records/decision", json={"record_id": target_id, "human_decision": "合格"})
    assert res.status_code == 200, res.text
    print(f"手動更新 (合格): {res.json()['message']}")

    # 更新後の再取得検証
    res = client.get(f"/api/workspaces/{ws_id}/records?page=1&page_size=10&search_query={target_id}")
    assert res.status_code == 200
    updated_rec = res.json()['records'][0]
    assert updated_rec['human_decision'] == "合格"
    assert updated_rec['status'] == "合格"
    print("  ✓ 手動オーバーライド更新のDuckDB即時反映を確認")

    # 元の状態に復元
    res = client.post(f"/api/workspaces/{ws_id}/records/decision", json={"record_id": target_id, "human_decision": orig_decision})
    assert res.status_code == 200
    print("  ✓ 手動オーバーライド判定のクリーン復元完了")

    print(f"\n=== [8] Step 5: 確定データセットエクスポート ===")
    res = client.post(f"/api/workspaces/{ws_id}/records/export-verified")
    assert res.status_code == 200, res.text
    export_res = res.json()
    print(f"エクスポート実行結果: {export_res['message']} (件数: {export_res['count']})")

    print("\n==========================================")
    print("🎉 全 End-to-End パイプライン統合テスト完全合格！")
    print("==========================================")

if __name__ == "__main__":
    test_full_pipeline()
