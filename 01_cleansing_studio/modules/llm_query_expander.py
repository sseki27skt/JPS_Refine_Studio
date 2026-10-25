# -*- coding: utf-8 -*-
"""
LLMアシスト型 網羅的検索キーワード拡張 & ドメイン定義生成モジュール (Gemini API / OpenAI / Local対応)
網羅性（Recall 100%志向）重視バージョン
"""

import json
import os
import re
from collections import defaultdict
import requests
from .logger import logger

DEFAULT_LLM_URL = os.environ.get("LLM_API_BASE", "http://localhost:1234/v1")
DEFAULT_MODEL = os.environ.get("LLM_MODEL", "local-model")

# 日本十進分類法 (NDC) 二次区分マスター辞書 (00-99)
NDC_MASTER = {
    "00": "00:総記", "01": "01:図書館・図書館情報学", "02": "02:図書・書誌学", "03": "03:百科事典", "04": "04:一般論文集",
    "05": "05:逐次刊行物", "06": "06:団体・博物館", "07": "07:ジャーナリズム・新聞", "08": "08:叢書・全集", "09": "09:貴重書・郷土資料",
    "10": "10:哲学", "11": "11:哲学各論", "12": "12:東洋哲学", "13": "13:西洋哲学", "14": "14:心理学",
    "15": "15:倫理学・道徳", "16": "16:宗教", "17": "17:神道", "18": "18:仏教", "19": "19:キリスト教",
    "20": "20:歴史・文化史", "21": "21:日本史", "22": "22:アジア史", "23": "23:ヨーロッパ史", "24": "24:アフリカ史",
    "25": "25:北アメリカ史", "26": "26:南アメリカ史", "27": "27:オセアニア史", "28": "28:伝記", "29": "29:地理・地誌・紀行",
    "30": "30:社会科学", "31": "31:政治", "32": "32:法律", "33": "33:経済", "34": "34:財政",
    "35": "35:統計", "36": "36:社会", "37": "37:教育", "38": "38:風俗習慣・民俗学", "39": "39:国防・軍事",
    "40": "40:自然科学", "41": "41:数学", "42": "42:物理学", "43": "43:化学", "44": "44:天文学",
    "45": "45:地球科学", "46": "46:生物科学", "47": "47:植物学", "48": "48:動物学", "49": "49:医学・薬学",
    "50": "50:技術・工学", "51": "51:建設・土木", "52": "52:建築学", "53": "53:機械工学", "54": "54:電気工学",
    "55": "55:海洋・軍事工学", "56": "56:金属・鉱山", "57": "57:化学工業", "58": "58:製造工業", "59": "59:家政学",
    "60": "60:産業", "61": "61:農業", "62": "62:園芸", "63": "63:蚕糸業", "64": "64:畜産業",
    "65": "65:林業", "66": "66:水産業", "67": "67:商業", "68": "68:運輸・交通・観光", "69": "69:通信事業",
    "70": "70:芸術・美術", "71": "71:彫刻", "72": "72:絵画・書道", "73": "73:版画・印章・印譜", "74": "74:写真・印刷",
    "75": "75:工芸", "76": "76:音楽・舞踊", "77": "77:演劇・映画・大衆芸能", "78": "78:スポーツ", "79": "79:諸芸・娯楽",
    "80": "80:言語", "81": "81:日本語", "82": "82:中国語・東洋諸語", "83": "83:英語", "84": "84:ドイツ語",
    "85": "85:フランス語", "86": "86:スペイン・ポルトガル語", "87": "87:イタリア語", "88": "88:ロシア語", "89": "89:その他言語",
    "90": "90:文学", "91": "91:日本文学", "92": "92:中国文学・東洋文学", "93": "93:英米文学", "94": "94:ドイツ文学",
    "95": "95:フランス文学", "96": "96:スペイン文学", "97": "97:イタリア文学", "98": "98:ロシア文学", "99": "99:その他文学"
}

# Japan Search 主要 rdf:type マスター辞書 (件数上位抜粋)
TYPE_MASTER = {
    "アクセス情報": "https://jpsearch.go.jp/term/type/アクセス情報",
    "ソース情報": "https://jpsearch.go.jp/term/type/ソース情報",
    "図書": "https://jpsearch.go.jp/term/type/図書",
    "Agent": "https://jpsearch.go.jp/term/type/Agent",
    "行政文書": "https://jpsearch.go.jp/term/type/行政文書",
    "動物標本": "https://jpsearch.go.jp/term/type/動物標本",
    "植物標本": "https://jpsearch.go.jp/term/type/植物標本",
    "雑誌": "https://jpsearch.go.jp/term/type/雑誌",
    "Manifest": "http://iiif.io/api/presentation/2#Manifest",
    "記事": "https://jpsearch.go.jp/term/type/記事",
    "古書・古文書": "https://jpsearch.go.jp/term/type/古書・古文書",
    "記事・論文": "https://jpsearch.go.jp/term/type/記事・論文",
    "内閣文庫": "https://jpsearch.go.jp/term/type/内閣文庫",
    "歴史資料": "https://jpsearch.go.jp/term/type/歴史資料",
    "資料一般": "https://jpsearch.go.jp/term/type/資料一般",
    "Keyword": "https://jpsearch.go.jp/term/type/Keyword",
    "新聞": "https://jpsearch.go.jp/term/type/新聞",
    "記録写真": "https://jpsearch.go.jp/term/type/記録写真",
    "録音資料": "https://jpsearch.go.jp/term/type/録音資料",
    "地図資料": "https://jpsearch.go.jp/term/type/地図資料",
    "NIJL閲覧": "https://jpsearch.go.jp/term/nctype/OAR_arc#NIJL閲覧",
    "IIIFmf": "https://jpsearch.go.jp/term/nctype/OAR_arc#IIIFmf",
    "芸術・美術": "https://jpsearch.go.jp/term/type/芸術・美術",
    "博物資料": "https://jpsearch.go.jp/term/type/博物資料",
    "文章要素": "https://jpsearch.go.jp/term/type/文章要素",
    "版画": "https://jpsearch.go.jp/term/type/版画",
    "写真": "https://jpsearch.go.jp/term/type/写真",
    "出版物": "https://jpsearch.go.jp/term/type/出版物",
    "静止画資料": "https://jpsearch.go.jp/term/type/静止画資料",
    "映像資料": "https://jpsearch.go.jp/term/type/映像資料",
    "CreativeWork": "http://schema.org/CreativeWork",
    "科学写真": "https://jpsearch.go.jp/term/type/科学写真",
    "アニメーション": "https://jpsearch.go.jp/term/type/アニメーション",
    "資料・情報": "https://jpsearch.go.jp/term/type/資料・情報",
    "構成要素": "https://jpsearch.go.jp/term/type/構成要素",
    "公演": "https://jpsearch.go.jp/term/type/公演",
    "文書資料": "https://jpsearch.go.jp/term/type/文書資料",
    "電子資料": "https://jpsearch.go.jp/term/type/電子資料",
    "PDF": "https://jpsearch.go.jp/term/nctype/PDF",
    "標本": "https://jpsearch.go.jp/term/type/標本",
    "記述情報": "https://jpsearch.go.jp/term/type/記述情報",
    "ORG閲覧": "https://jpsearch.go.jp/term/nctype/OAR_arc#ORG閲覧",
    "菌標本": "https://jpsearch.go.jp/term/type/菌標本",
    "考古": "https://jpsearch.go.jp/term/type/考古",
    "絵画": "https://jpsearch.go.jp/term/type/絵画",
    "法人文書": "https://jpsearch.go.jp/term/type/法人文書",
    "展覧会": "https://jpsearch.go.jp/term/type/展覧会",
    "HTML": "https://jpsearch.go.jp/term/nctype/HTML",
    "ゲーム": "https://jpsearch.go.jp/term/type/ゲーム",
    "上演": "https://jpsearch.go.jp/term/type/上演",
    "司法文書": "https://jpsearch.go.jp/term/type/司法文書",
    "Ukiyo-e.org": "https://jpsearch.go.jp/term/nctype/OAR_arc#Ukiyo-e.org",
    "絵葉書": "https://jpsearch.go.jp/term/type/絵葉書",
    "和古書": "https://jpsearch.go.jp/term/type/和古書",
    "ORG_Site": "https://jpsearch.go.jp/term/nctype/OAR_arc#ORG_Site",
    "ORG縮小": "https://jpsearch.go.jp/term/nctype/OAR_arc#ORG縮小",
    "書跡": "https://jpsearch.go.jp/term/type/書跡",
    "収録作品": "https://jpsearch.go.jp/term/type/収録作品",
    "絵画等": "https://jpsearch.go.jp/term/type/絵画等",
    "硬貨": "https://jpsearch.go.jp/term/type/硬貨",
    "Place": "https://jpsearch.go.jp/term/type/Place",
    "寄贈寄託文書": "https://jpsearch.go.jp/term/type/寄贈寄託文書",
    "Role": "https://jpsearch.go.jp/term/type/Role",
    "Person": "https://jpsearch.go.jp/term/type/Person",
    "建築": "https://jpsearch.go.jp/term/type/建築",
    "金工": "https://jpsearch.go.jp/term/type/金工",
    "MFA検索": "https://jpsearch.go.jp/term/nctype/OAR_arc#MFA検索",
    "ORG_img": "https://jpsearch.go.jp/term/nctype/OAR_arc#ORG_img",
    "Excel": "https://jpsearch.go.jp/term/nctype/Excel",
    "陶磁": "https://jpsearch.go.jp/term/type/陶磁",
    "Time": "https://jpsearch.go.jp/term/type/Time",
    "データセット": "https://jpsearch.go.jp/term/type/データセット",
    "楽譜": "https://jpsearch.go.jp/term/type/楽譜",
    "政府刊行物": "https://jpsearch.go.jp/term/type/政府刊行物",
    "工芸": "https://jpsearch.go.jp/term/type/工芸",
    "書写資料": "https://jpsearch.go.jp/term/type/書写資料",
    "メディア芸術": "https://jpsearch.go.jp/term/type/メディア芸術",
    "端物印刷物": "https://jpsearch.go.jp/term/type/端物印刷物",
    "仮IIIFマニフェスト": "https://jpsearch.go.jp/term/nctype/仮IIIFマニフェスト",
    "ORGsite": "https://jpsearch.go.jp/term/nctype/OAR_arc#ORGsite",
    "Movie": "http://schema.org/Movie",
    "染織": "https://jpsearch.go.jp/term/type/染織",
    "Concept": "http://www.w3.org/2004/02/skos/core#Concept",
    "彫刻": "https://jpsearch.go.jp/term/type/彫刻",
    "漆工": "https://jpsearch.go.jp/term/type/漆工",
    "ORGimg": "https://jpsearch.go.jp/term/nctype/OAR_arc#ORGimg",
    "レーザーディスク": "https://jpsearch.go.jp/term/type/レーザーディスク",
    "CSV": "https://jpsearch.go.jp/term/nctype/CSV",
    "BM検索": "https://jpsearch.go.jp/term/nctype/OAR_arc#BM検索",
    "映画": "https://jpsearch.go.jp/term/type/映画",
    "民族資料": "https://jpsearch.go.jp/term/type/民族資料",
    "装飾・工芸": "https://jpsearch.go.jp/term/type/装飾・工芸",
    "個人・団体の文書資料": "https://jpsearch.go.jp/term/type/個人・団体の文書資料",
    "ORG_IMG": "https://jpsearch.go.jp/term/nctype/OAR_arc#ORG_IMG",
    "書簡": "https://jpsearch.go.jp/term/type/書簡",
    "AnimationTVRegularSeries": "https://mediaarts-db.artmuseums.go.jp/data/class#AnimationTVRegularSeries",
    "刀剣": "https://jpsearch.go.jp/term/type/刀剣",
    "ORG画像": "https://jpsearch.go.jp/term/nctype/OAR_arc#ORG画像",
    "MRAH.DB": "https://jpsearch.go.jp/term/nctype/OAR_arc#MRAH.DB",
    "史跡": "https://jpsearch.go.jp/term/type/史跡",
    "放送番組": "https://jpsearch.go.jp/term/type/放送番組",
    "素描": "https://jpsearch.go.jp/term/type/素描",
    "デザイン": "https://jpsearch.go.jp/term/type/デザイン",
    "画像要素": "https://jpsearch.go.jp/term/type/画像要素",
    "Collection": "http://schema.org/Collection",
    "ORG検索": "https://jpsearch.go.jp/term/nctype/OAR_arc#ORG検索",
    "漢籍": "https://jpsearch.go.jp/term/type/漢籍",
    "史跡名勝天然記念物等": "https://jpsearch.go.jp/term/type/史跡名勝天然記念物等",
    "ORGsearch": "https://jpsearch.go.jp/term/nctype/OAR_arc#ORGsearch",
    "Report": "http://schema.org/Report",
    "AnimationMovieSeries": "https://mediaarts-db.artmuseums.go.jp/data/class#AnimationMovieSeries",
    "ポスター": "https://jpsearch.go.jp/term/type/ポスター",
    "建造物・建築": "https://jpsearch.go.jp/term/type/建造物・建築",
    "風俗・祭事": "https://jpsearch.go.jp/term/type/風俗・祭事",
    "音楽": "https://jpsearch.go.jp/term/type/音楽",
    "Image": "https://jpsearch.go.jp/term/nctype/Image",
    "1": "https://jpsearch.go.jp/term/nctype/1",
    "2": "https://jpsearch.go.jp/term/nctype/2",
    "PDF": "file:///home/virtuoso/jps-jobrunner/PDF",
    "水彩": "https://jpsearch.go.jp/term/type/水彩",
    "zip": "https://jpsearch.go.jp/term/nctype/zip",
    "3": "https://jpsearch.go.jp/term/nctype/3",
    "Section": "http://jla.or.jp/vocab/ndcvocab#Section",
    "AchieveAction": "http://schema.org/AchieveAction",
    "OskiCat": "https://jpsearch.go.jp/term/nctype/OAR_arc#OskiCat",
    "FamilyRank": "https://jpsearch.go.jp/term/nctype/FamilyRank",
    "xml": "https://jpsearch.go.jp/term/nctype/xml",
    "雑誌・新聞・継続資料": "https://jpsearch.go.jp/term/type/雑誌・新聞・継続資料",
    "機関・施設情報": "https://jpsearch.go.jp/term/type/機関・施設情報",
    "ARC近代書籍": "https://jpsearch.go.jp/term/nctype/OAR_arc#ARC近代書籍",
    "GenusRank": "https://jpsearch.go.jp/term/nctype/GenusRank",
    "ORG_Img": "https://jpsearch.go.jp/term/nctype/OAR_arc#ORG_Img",
    "番付DB": "https://jpsearch.go.jp/term/nctype/OAR_arc#番付DB",
    "古文書": "https://jpsearch.go.jp/term/type/古文書",
    "書跡・典籍": "https://jpsearch.go.jp/term/type/書跡・典籍",
    "4": "https://jpsearch.go.jp/term/nctype/4",
    "古典籍DB.": "https://jpsearch.go.jp/term/nctype/OAR_arc#古典籍DB.",
    "Class": "http://www.w3.org/2000/01/rdf-schema#Class",
    "視聴覚資料": "https://jpsearch.go.jp/term/type/視聴覚資料",
    "国文研(IIIFmf)": "https://jpsearch.go.jp/term/nctype/OAR_arc#国文研(IIIFmf)",
    "国文研(nijl)": "https://jpsearch.go.jp/term/nctype/OAR_arc#国文研(nijl)",
    "YoutubePage": "https://jpsearch.go.jp/term/nctype/YoutubePage",
    "石碑": "https://jpsearch.go.jp/term/type/石碑",
    "Video": "https://jpsearch.go.jp/term/nctype/OAR_arc#Video",
    "天然記念物": "https://jpsearch.go.jp/term/type/天然記念物",
    "ORGdetail": "https://jpsearch.go.jp/term/nctype/OAR_arc#ORGdetail",
    "Variant": "http://jla.or.jp/vocab/ndcvocab#Variant",
    "面": "https://jpsearch.go.jp/term/type/面",
    "ARC近代DB": "https://jpsearch.go.jp/term/nctype/OAR_arc#ARC近代DB",
    "視覚障害者向け資料": "https://jpsearch.go.jp/term/type/視覚障害者向け資料",
    "考古資料": "https://jpsearch.go.jp/term/type/考古資料",
    "稀覯書": "https://jpsearch.go.jp/term/type/稀覯書",
    "CalendarEra": "https://jpsearch.go.jp/term/type/CalendarEra",
    "板木閲覧": "https://jpsearch.go.jp/term/nctype/OAR_arc#板木閲覧",
    "建築・芸術": "https://jpsearch.go.jp/term/type/建築・芸術",
    "Property": "http://www.w3.org/1999/02/22-rdf-syntax-ns#Property",
    "古典籍DB": "https://jpsearch.go.jp/term/nctype/OAR_arc#古典籍DB",
    "金工・武器": "https://jpsearch.go.jp/term/type/金工・武器",
    "Collection": "http://www.w3.org/2004/02/skos/core#Collection",
    "詳細検索": "https://jpsearch.go.jp/term/nctype/OAR_arc#詳細検索",
    "kmz": "https://jpsearch.go.jp/term/nctype/kmz",
    "5": "https://jpsearch.go.jp/term/nctype/5",
    "OrderRank": "https://jpsearch.go.jp/term/nctype/OrderRank",
    "Alt._URL": "https://jpsearch.go.jp/term/nctype/OAR_arc#Alt._URL",
    "浮世絵DB.": "https://jpsearch.go.jp/term/nctype/OAR_arc#浮世絵DB.",
    "木工": "https://jpsearch.go.jp/term/type/木工",
    "Flash画像有": "https://jpsearch.go.jp/term/nctype/OAR_arc#Flash画像有",
    "DVD・CD": "https://jpsearch.go.jp/term/type/DVD・CD",
    "ReferencePolicy": "http://purl.org/net/ns/policy#ReferencePolicy",
    "AboutPage": "http://schema.org/AboutPage",
    "町並み保存": "https://jpsearch.go.jp/term/type/町並み保存",
    "Organization": "http://schema.org/Organization",
    "国会DC": "https://jpsearch.go.jp/term/nctype/OAR_arc#国会DC",
    "QuadMapFormat": "http://www.openlinksw.com/schemas/virtrdf#QuadMapFormat",
    "ウェブサイト": "https://jpsearch.go.jp/term/type/ウェブサイト",
    "3D資料": "https://jpsearch.go.jp/term/type/3D資料",
    "解説": "https://jpsearch.go.jp/term/nctype/OAR_arc#解説",
    "Country": "https://jpsearch.go.jp/term/type/Country",
    "Periodical": "http://schema.org/Periodical",
    "ビデオテープ": "https://jpsearch.go.jp/term/type/ビデオテープ",
    "名勝": "https://jpsearch.go.jp/term/type/名勝",
    "pptx": "https://jpsearch.go.jp/term/nctype/pptx",
    "宝石": "https://jpsearch.go.jp/term/type/宝石",
    "Division": "http://jla.or.jp/vocab/ndcvocab#Division",
    "武器": "https://jpsearch.go.jp/term/type/武器",
    "array-of-QuadMapFormat": "http://www.openlinksw.com/schemas/virtrdf#array-of-QuadMapFormat",
    "浮世絵DB": "https://jpsearch.go.jp/term/nctype/OAR_arc#浮世絵DB",
    "画帖閲覧": "https://jpsearch.go.jp/term/nctype/OAR_arc#画帖閲覧",
    "epub": "https://jpsearch.go.jp/term/nctype/epub",
    "JASS演奏": "https://jpsearch.go.jp/term/nctype/OAR_arc#JASS演奏",
    "HistoricalEra": "https://jpsearch.go.jp/term/type/HistoricalEra",
    "XLS": "https://jpsearch.go.jp/term/nctype/XLS",
    "Audio": "https://jpsearch.go.jp/term/nctype/Audio",
    "IndividualPolicyStatement": "http://purl.org/net/ns/policy#IndividualPolicyStatement",
    "License": "http://creativecommons.org/ns#License",
    "6": "https://jpsearch.go.jp/term/nctype/6",
    "竹工芸": "https://jpsearch.go.jp/term/type/竹工芸",
    "MOVIE": "https://jpsearch.go.jp/term/nctype/MOVIE",
    "インスタレーション": "https://jpsearch.go.jp/term/type/インスタレーション",
    "演博検索": "https://jpsearch.go.jp/term/nctype/OAR_arc#演博検索",
    "PDF有": "https://jpsearch.go.jp/term/nctype/OAR_arc#PDF有",
    "拓本": "https://jpsearch.go.jp/term/type/拓本",
    "ORG詳細": "https://jpsearch.go.jp/term/nctype/OAR_arc#ORG詳細",
    "会議録": "https://jpsearch.go.jp/term/type/会議録",
    "屏風": "https://jpsearch.go.jp/term/type/屏風",
    "SOUND": "https://jpsearch.go.jp/term/nctype/SOUND",
    "AnimationTVSpecialSeries": "https://mediaarts-db.artmuseums.go.jp/data/class#AnimationTVSpecialSeries",
    "印仏": "https://jpsearch.go.jp/term/type/印仏",
    "ClassRank": "https://jpsearch.go.jp/term/nctype/ClassRank",
    "マイクロ資料": "https://jpsearch.go.jp/term/type/マイクロ資料",
    "馬具": "https://jpsearch.go.jp/term/type/馬具",
    "doc": "https://jpsearch.go.jp/term/nctype/doc",
    "SubOrderRank": "https://jpsearch.go.jp/term/nctype/SubOrderRank",
    "docx": "https://jpsearch.go.jp/term/nctype/docx",
    "古典籍Page": "https://jpsearch.go.jp/term/nctype/OAR_arc#古典籍Page",
    "3DView": "https://jpsearch.go.jp/term/nctype/3DView",
    "ObjectProperty": "http://www.w3.org/2002/07/owl#ObjectProperty",
    "オンライン資料": "https://jpsearch.go.jp/term/type/オンライン資料",
    "Century": "https://jpsearch.go.jp/term/type/Century",
    "板木DB": "https://jpsearch.go.jp/term/nctype/OAR_arc#板木DB",
    "番付DB.": "https://jpsearch.go.jp/term/nctype/OAR_arc#番付DB.",
    "7": "https://jpsearch.go.jp/term/nctype/7",
    "CreativeWorkSeries": "http://schema.org/CreativeWorkSeries",
    "asp": "https://jpsearch.go.jp/term/nctype/asp",
    "楽器": "https://jpsearch.go.jp/term/type/楽器",
    "画集・画本": "https://jpsearch.go.jp/term/type/画集・画本",
    "txt": "https://jpsearch.go.jp/term/nctype/txt",
    "WebPage": "http://schema.org/WebPage",
    "絵本番付": "https://jpsearch.go.jp/term/nctype/OAR_arc#絵本番付",
    "RightsStatement": "http://purl.org/dc/terms/RightsStatement",
    "AnnotationProperty": "http://www.w3.org/2002/07/owl#AnnotationProperty",
    "地図": "https://jpsearch.go.jp/term/type/地図",
    "PhylumRank": "https://jpsearch.go.jp/term/nctype/PhylumRank",
    "SuperOrderRank": "https://jpsearch.go.jp/term/nctype/SuperOrderRank",
    "Org閲覧": "https://jpsearch.go.jp/term/nctype/OAR_arc#Org閲覧",
    "Video": "https://jpsearch.go.jp/term/nctype/Video",
    "Class": "http://www.w3.org/2002/07/owl#Class",
    "解説頁": "https://jpsearch.go.jp/term/nctype/OAR_arc#解説頁",
    "翻刻解題": "https://jpsearch.go.jp/term/nctype/OAR_arc#翻刻解題",
    "SubFamilyRank": "https://jpsearch.go.jp/term/nctype/SubFamilyRank",
    "8": "https://jpsearch.go.jp/term/nctype/8",
    "DisambiguationEntity": "https://jpsearch.go.jp/term/type/DisambiguationEntity",
    "php": "https://jpsearch.go.jp/term/nctype/php",
    "コレクション": "https://jpsearch.go.jp/term/type/コレクション",
    "MainClass": "http://jla.or.jp/vocab/ndcvocab#MainClass",
    "動画資料": "https://jpsearch.go.jp/term/type/動画資料",
    "完成形1": "https://jpsearch.go.jp/term/nctype/OAR_arc#完成形1",
    "QuadMapColumn": "http://www.openlinksw.com/schemas/virtrdf#QuadMapColumn",
    "全体閲覧": "https://jpsearch.go.jp/term/nctype/OAR_arc#全体閲覧",
    "QuadMapValue": "http://www.openlinksw.com/schemas/virtrdf#QuadMapValue",
    "array-of-QuadMapColumn": "http://www.openlinksw.com/schemas/virtrdf#array-of-QuadMapColumn",
    "公文書": "https://jpsearch.go.jp/term/type/公文書",
    "SuperFamilyRank": "https://jpsearch.go.jp/term/nctype/SuperFamilyRank",
    "9": "https://jpsearch.go.jp/term/nctype/9",
    "完成形2": "https://jpsearch.go.jp/term/nctype/OAR_arc#完成形2",
    "be": "https://jpsearch.go.jp/term/nctype/be",
    "InfraClassRank": "https://jpsearch.go.jp/term/nctype/InfraClassRank",
    "Requirement": "http://creativecommons.org/ns#Requirement",
    "演奏": "https://jpsearch.go.jp/term/type/演奏",
    "翻刻縦書本文": "https://jpsearch.go.jp/term/nctype/OAR_arc#翻刻縦書本文",
    "蛍光X線分析": "https://jpsearch.go.jp/term/nctype/OAR_arc#蛍光X線分析",
    "kml": "https://jpsearch.go.jp/term/nctype/kml",
    "Datatype": "http://www.w3.org/2000/01/rdf-schema#Datatype",
    "jtd": "https://jpsearch.go.jp/term/nctype/jtd",
    "パフォーマンス": "https://jpsearch.go.jp/term/type/パフォーマンス",
    "同板表紙": "https://jpsearch.go.jp/term/nctype/OAR_arc#同板表紙",
    "完成形": "https://jpsearch.go.jp/term/nctype/OAR_arc#完成形",
    "工芸品": "https://jpsearch.go.jp/term/type/工芸品",
    "翻刻": "https://jpsearch.go.jp/term/nctype/OAR_arc#翻刻",
    "解説2": "https://jpsearch.go.jp/term/nctype/OAR_arc#解説2",
    "OntologyProperty": "http://www.w3.org/2002/07/owl#OntologyProperty",
    "SubClassRank": "https://jpsearch.go.jp/term/nctype/SubClassRank",
    "同板表示": "https://jpsearch.go.jp/term/nctype/OAR_arc#同板表示",
    "SymmetricProperty": "http://www.w3.org/2002/07/owl#SymmetricProperty",
    "Ontology": "http://www.w3.org/2002/07/owl#Ontology",
    "Permission": "http://creativecommons.org/ns#Permission",
    "解説1": "https://jpsearch.go.jp/term/nctype/OAR_arc#解説1",
    "役割番付": "https://jpsearch.go.jp/term/nctype/OAR_arc#役割番付",
    "QuadMapFText": "http://www.openlinksw.com/schemas/virtrdf#QuadMapFText",
    "巻子閲覧": "https://jpsearch.go.jp/term/nctype/OAR_arc#巻子閲覧",
    "PolicyCategory": "http://purl.org/net/ns/policy#PolicyCategory",
    "巻子画像": "https://jpsearch.go.jp/term/nctype/OAR_arc#巻子画像",
    "QuadStorage": "http://www.openlinksw.com/schemas/virtrdf#QuadStorage",
    "完成形4": "https://jpsearch.go.jp/term/nctype/OAR_arc#完成形4",
    "do": "https://jpsearch.go.jp/term/nctype/do",
    "巻全体": "https://jpsearch.go.jp/term/nctype/OAR_arc#巻全体",
    "10": "https://jpsearch.go.jp/term/nctype/10",
    "DivisionRank": "https://jpsearch.go.jp/term/nctype/DivisionRank",
    "完成形3": "https://jpsearch.go.jp/term/nctype/OAR_arc#完成形3",
    "関連資料": "https://jpsearch.go.jp/term/nctype/OAR_arc#関連資料",
    "array-of-QuadMap": "http://www.openlinksw.com/schemas/virtrdf#array-of-QuadMap",
    "ORG": "https://jpsearch.go.jp/term/nctype/OAR_arc#ORG",
    "完成図": "https://jpsearch.go.jp/term/nctype/OAR_arc#完成図",
    "絵画DB": "https://jpsearch.go.jp/term/nctype/OAR_arc#絵画DB",
    "TransitiveProperty": "http://www.w3.org/2002/07/owl#TransitiveProperty",
    "ORGimage": "https://jpsearch.go.jp/term/nctype/OAR_arc#ORGimage",
    "官公庁刊行物": "https://jpsearch.go.jp/term/type/官公庁刊行物",
    "QuadMap": "http://www.openlinksw.com/schemas/virtrdf#QuadMap",
    "掛軸画像": "https://jpsearch.go.jp/term/nctype/OAR_arc#掛軸画像",
    "KingdomRank": "https://jpsearch.go.jp/term/nctype/KingdomRank",
    "lzh": "https://jpsearch.go.jp/term/nctype/lzh",
    "ORG_site": "https://jpsearch.go.jp/term/nctype/OAR_arc#ORG_site",
    "ORG書誌": "https://jpsearch.go.jp/term/nctype/OAR_arc#ORG書誌",
    "Org縮小": "https://jpsearch.go.jp/term/nctype/OAR_arc#Org縮小",
    "array-of-QuadMapATable": "http://www.openlinksw.com/schemas/virtrdf#array-of-QuadMapATable",
    "DatatypeProperty": "http://www.w3.org/2002/07/owl#DatatypeProperty",
    "書籍装丁DB": "https://jpsearch.go.jp/term/nctype/OAR_arc#書籍装丁DB",
    "建物": "https://jpsearch.go.jp/term/type/建物",
    "接続画像": "https://jpsearch.go.jp/term/nctype/OAR_arc#接続画像",
    "SubDivisionRank": "https://jpsearch.go.jp/term/nctype/SubDivisionRank",
    "SubPhylumRank": "https://jpsearch.go.jp/term/nctype/SubPhylumRank",
    "Prohibition": "http://creativecommons.org/ns#Prohibition",
    "SuperClassRank": "https://jpsearch.go.jp/term/nctype/SuperClassRank",
    "絵本和漢誉": "https://jpsearch.go.jp/term/nctype/OAR_arc#絵本和漢誉",
    "銅板表示": "https://jpsearch.go.jp/term/nctype/OAR_arc#銅板表示",
    "書籍DB閲覧": "https://jpsearch.go.jp/term/nctype/OAR_arc#書籍DB閲覧",
    "全文翻刻": "https://jpsearch.go.jp/term/nctype/OAR_arc#全文翻刻",
    "Wikipedia": "https://jpsearch.go.jp/term/nctype/OAR_arc#Wikipedia",
    "書籍DB.": "https://jpsearch.go.jp/term/nctype/OAR_arc#書籍DB.",
    "浮世絵Portal": "https://jpsearch.go.jp/term/nctype/OAR_arc#浮世絵Portal",
    "絵本番付1": "https://jpsearch.go.jp/term/nctype/OAR_arc#絵本番付1",
    "北斎漫画3": "https://jpsearch.go.jp/term/nctype/OAR_arc#北斎漫画3",
    "狂言本挿絵": "https://jpsearch.go.jp/term/nctype/OAR_arc#狂言本挿絵",
    "板本表示": "https://jpsearch.go.jp/term/nctype/OAR_arc#板本表示",
    "movie": "https://jpsearch.go.jp/term/nctype/OAR_arc#movie",
    "array-of-string": "http://www.openlinksw.com/schemas/virtrdf#array-of-string",
    "掲載頁閲覧": "https://jpsearch.go.jp/term/nctype/OAR_arc#掲載頁閲覧",
    "11": "https://jpsearch.go.jp/term/nctype/11",
    "QuadMapATable": "http://www.openlinksw.com/schemas/virtrdf#QuadMapATable",
    "日経記事": "https://jpsearch.go.jp/term/nctype/OAR_arc#日経記事",
    "RSK_DB": "https://jpsearch.go.jp/term/nctype/OAR_arc#RSK_DB",
    "本間美術館": "https://jpsearch.go.jp/term/nctype/OAR_arc#本間美術館",
    "日本山海名産図会": "https://jpsearch.go.jp/term/nctype/OAR_arc#日本山海名産図会",
    "UCB_LS": "https://jpsearch.go.jp/term/nctype/OAR_arc#UCB_LS",
    "zoomify": "https://jpsearch.go.jp/term/nctype/OAR_arc#zoomify",
    "個別閲覧": "https://jpsearch.go.jp/term/nctype/OAR_arc#個別閲覧",
    "16": "https://jpsearch.go.jp/term/nctype/16",
    "jp": "https://jpsearch.go.jp/term/nctype/jp",
    "解説411-2": "https://jpsearch.go.jp/term/nctype/OAR_arc#解説411-2",
    "絵本漢楚軍談3": "https://jpsearch.go.jp/term/nctype/OAR_arc#絵本漢楚軍談3",
    "釈迦御一代記": "https://jpsearch.go.jp/term/nctype/OAR_arc#釈迦御一代記",
    "参照画像": "https://jpsearch.go.jp/term/nctype/OAR_arc#参照画像",
    "日文研検索": "https://jpsearch.go.jp/term/nctype/OAR_arc#日文研検索",
    "頁閲覧へ": "https://jpsearch.go.jp/term/nctype/OAR_arc#頁閲覧へ",
    "頁毎詳細": "https://jpsearch.go.jp/term/nctype/OAR_arc#頁毎詳細",
    "国文研書誌": "https://jpsearch.go.jp/term/nctype/OAR_arc#国文研書誌",
    "紹介": "https://jpsearch.go.jp/term/nctype/OAR_arc#紹介",
    "_番付DB.": "https://jpsearch.go.jp/term/nctype/OAR_arc#_番付DB.",
    "DVD": "https://jpsearch.go.jp/term/type/DVD",
    "List": "http://www.w3.org/1999/02/22-rdf-syntax-ns#List",
    "ConceptScheme": "http://www.w3.org/2004/02/skos/core#ConceptScheme",
    "ZIP": "https://jpsearch.go.jp/term/nctype/ZIP",
    "国土地理院本": "https://jpsearch.go.jp/term/nctype/OAR_arc#国土地理院本",
    "Z0188-032(03)": "https://jpsearch.go.jp/term/nctype/OAR_arc#Z0188-032(03)",
    "ORG検索Site": "https://jpsearch.go.jp/term/nctype/OAR_arc#ORG検索Site",
    "BM解説": "https://jpsearch.go.jp/term/nctype/OAR_arc#BM解説",
    "新画像": "https://jpsearch.go.jp/term/nctype/OAR_arc#新画像",
    "同伴表紙": "https://jpsearch.go.jp/term/nctype/OAR_arc#同伴表紙",
    "漫画十二NMS": "https://jpsearch.go.jp/term/nctype/OAR_arc#漫画十二NMS",
    "稿本": "https://jpsearch.go.jp/term/nctype/OAR_arc#稿本",
    "奈文研": "https://jpsearch.go.jp/term/nctype/OAR_arc#奈文研",
    "FunctionalProperty": "http://www.w3.org/2002/07/owl#FunctionalProperty",
    "辻番付1": "https://jpsearch.go.jp/term/nctype/OAR_arc#辻番付1",
    "Related": "https://jpsearch.go.jp/term/nctype/OAR_arc#Related",
    "図録解説": "https://jpsearch.go.jp/term/nctype/OAR_arc#図録解説",
    "詳細解説": "https://jpsearch.go.jp/term/nctype/OAR_arc#詳細解説",
    "考証": "https://jpsearch.go.jp/term/nctype/OAR_arc#考証",
    "写真DB": "https://jpsearch.go.jp/term/nctype/OAR_arc#写真DB",
    "参考資料": "https://jpsearch.go.jp/term/nctype/OAR_arc#参考資料",
    "漫画十二多色": "https://jpsearch.go.jp/term/nctype/OAR_arc#漫画十二多色",
    "部首一覧": "https://jpsearch.go.jp/term/nctype/OAR_arc#部首一覧",
    "通俗漢楚軍談1": "https://jpsearch.go.jp/term/nctype/OAR_arc#通俗漢楚軍談1",
    "参考": "https://jpsearch.go.jp/term/nctype/OAR_arc#参考",
    "書籍DB": "https://jpsearch.go.jp/term/nctype/OAR_arc#書籍DB",
    "MFA_Boston_": "https://jpsearch.go.jp/term/nctype/OAR_arc#MFA_Boston_",
    "ARC近代": "https://jpsearch.go.jp/term/nctype/OAR_arc#ARC近代",
    "影印複製": "https://jpsearch.go.jp/term/nctype/OAR_arc#影印複製",
    "作成中": "https://jpsearch.go.jp/term/nctype/OAR_arc#作成中",
    "版画DB.": "https://jpsearch.go.jp/term/nctype/OAR_arc#版画DB.",
    "口絵": "https://jpsearch.go.jp/term/nctype/OAR_arc#口絵",
    "明治初年後摺": "https://jpsearch.go.jp/term/nctype/OAR_arc#明治初年後摺",
    "15": "https://jpsearch.go.jp/term/nctype/15",
    "xlsm": "https://jpsearch.go.jp/term/nctype/xlsm",
    "解説3": "https://jpsearch.go.jp/term/nctype/OAR_arc#解説3",
    "Q3304751": "http://www.wikidata.org/entity/Q3304751",
    "Slide2": "https://jpsearch.go.jp/term/nctype/OAR_arc#Slide2",
    "全体図": "https://jpsearch.go.jp/term/nctype/OAR_arc#全体図",
    "北斎漫画": "https://jpsearch.go.jp/term/nctype/OAR_arc#北斎漫画",
    "論文": "https://jpsearch.go.jp/term/nctype/OAR_arc#論文",
    "影印翻刻": "https://jpsearch.go.jp/term/nctype/OAR_arc#影印翻刻",
    "刊行本": "https://jpsearch.go.jp/term/nctype/OAR_arc#刊行本",
    "図録閲覧": "https://jpsearch.go.jp/term/nctype/OAR_arc#図録閲覧",
    "17": "https://jpsearch.go.jp/term/nctype/17",
    "北斎漫画1": "https://jpsearch.go.jp/term/nctype/OAR_arc#北斎漫画1",
    "演博": "https://jpsearch.go.jp/term/nctype/OAR_arc#演博",
    "DOI": "https://jpsearch.go.jp/term/nctype/OAR_arc#DOI",
    "安永7.11絵本番付": "https://jpsearch.go.jp/term/nctype/OAR_arc#安永7.11絵本番付",
    "各図詳細情報": "https://jpsearch.go.jp/term/nctype/OAR_arc#各図詳細情報",
    "写本表示": "https://jpsearch.go.jp/term/nctype/OAR_arc#写本表示",
    "番付検索": "https://jpsearch.go.jp/term/nctype/OAR_arc#番付検索",
    "NDL書誌": "https://jpsearch.go.jp/term/nctype/OAR_arc#NDL書誌",
    "全巻翻刻": "https://jpsearch.go.jp/term/nctype/OAR_arc#全巻翻刻",
    "国文研": "https://jpsearch.go.jp/term/nctype/OAR_arc#国文研",
    "関連冊子": "https://jpsearch.go.jp/term/nctype/OAR_arc#関連冊子",
    "北斎漫画３": "https://jpsearch.go.jp/term/nctype/OAR_arc#北斎漫画３",
    "辻番付2": "https://jpsearch.go.jp/term/nctype/OAR_arc#辻番付2",
    "辻番付": "https://jpsearch.go.jp/term/nctype/OAR_arc#辻番付",
    "掲載書籍": "https://jpsearch.go.jp/term/nctype/OAR_arc#掲載書籍",
    "図録頁": "https://jpsearch.go.jp/term/nctype/OAR_arc#図録頁",
    "翻刻本文": "https://jpsearch.go.jp/term/nctype/OAR_arc#翻刻本文",
    "12": "https://jpsearch.go.jp/term/nctype/12",
    "銅板表紙": "https://jpsearch.go.jp/term/nctype/OAR_arc#銅板表紙",
    "スライド": "https://jpsearch.go.jp/term/type/スライド",
    "複製閲覧": "https://jpsearch.go.jp/term/nctype/OAR_arc#複製閲覧",
    "http://www.arc.ritsumei.ac.jp/": "https://jpsearch.go.jp/term/nctype/OAR_arc#http://www.arc.ritsumei.ac.jp/",
    "名所絵": "http://ja.dbpedia.org/resource/名所絵",
    "修復前画像": "https://jpsearch.go.jp/term/nctype/OAR_arc#修復前画像",
    "絵本番付2": "https://jpsearch.go.jp/term/nctype/OAR_arc#絵本番付2",
    "訓蒙図彙": "https://jpsearch.go.jp/term/nctype/OAR_arc#訓蒙図彙",
    "貼込頁": "https://jpsearch.go.jp/term/nctype/OAR_arc#貼込頁",
    "絵本番付①": "https://jpsearch.go.jp/term/nctype/OAR_arc#絵本番付①",
    "校合本": "https://jpsearch.go.jp/term/nctype/OAR_arc#校合本",
    "浮世DB.": "https://jpsearch.go.jp/term/nctype/OAR_arc#浮世DB.",
    "国会本": "https://jpsearch.go.jp/term/nctype/OAR_arc#国会本",
    "JPsearch": "https://jpsearch.go.jp/term/nctype/OAR_arc#JPsearch",
    "ORG_Search": "https://jpsearch.go.jp/term/nctype/OAR_arc#ORG_Search",
    "関連図": "https://jpsearch.go.jp/term/nctype/OAR_arc#関連図",
    "参考画像": "https://jpsearch.go.jp/term/nctype/OAR_arc#参考画像",
    "未指定": "https://jpsearch.go.jp/term/type/未指定",
    "旧ORG閲覧": "https://jpsearch.go.jp/term/nctype/OAR_arc#旧ORG閲覧",
    "活字本": "https://jpsearch.go.jp/term/nctype/OAR_arc#活字本",
    "解題翻刻": "https://jpsearch.go.jp/term/nctype/OAR_arc#解題翻刻",
    "ARC浮世絵": "https://jpsearch.go.jp/term/nctype/OAR_arc#ARC浮世絵",
    "13": "https://jpsearch.go.jp/term/nctype/13",
    "ARC画像": "https://jpsearch.go.jp/term/nctype/OAR_arc#ARC画像",
    "PDF(J)": "https://jpsearch.go.jp/term/nctype/OAR_arc#PDF(J)",
    "解説411": "https://jpsearch.go.jp/term/nctype/OAR_arc#解説411",
    "建築物": "https://jpsearch.go.jp/term/type/建築物",
    "Service": "http://www.w3.org/ns/sparql-service-description#Service",
    "博士論文": "https://jpsearch.go.jp/term/type/博士論文",
    "AgentClass": "http://purl.org/dc/terms/AgentClass",
    "広報リリース": "https://jpsearch.go.jp/term/nctype/OAR_arc#広報リリース",
    "原品": "https://jpsearch.go.jp/term/nctype/OAR_arc#原品",
    "浮世絵ポータル": "https://jpsearch.go.jp/term/nctype/OAR_arc#浮世絵ポータル",
    "十二編色々な": "https://jpsearch.go.jp/term/nctype/OAR_arc#十二編色々な",
    "立命館図書館": "https://jpsearch.go.jp/term/nctype/OAR_arc#立命館図書館",
    "番付閲覧": "https://jpsearch.go.jp/term/nctype/OAR_arc#番付閲覧",
    "pl": "https://jpsearch.go.jp/term/nctype/pl",
    "japan": "https://jpsearch.go.jp/term/nctype/japan",
    "縮緬本": "https://jpsearch.go.jp/term/nctype/OAR_arc#縮緬本",
    "14": "https://jpsearch.go.jp/term/nctype/14",
    "PDF(E)": "https://jpsearch.go.jp/term/nctype/OAR_arc#PDF(E)",
    "Legislation": "http://schema.org/Legislation",
}


def ndc_codes_to_labels(codes: list) -> list:
    """コードリスト (例: ['76', '77']) を表示ラベル表記のリスト (例: ['76:音楽・舞踊', ...]) に変換"""
    labels = []
    if not isinstance(codes, list):
        return labels
    for c in codes:
        raw_c = str(c).strip()
        code_str = raw_c.zfill(2) if raw_c.isdigit() and len(raw_c) <= 2 else raw_c
        if code_str in NDC_MASTER:
            labels.append(NDC_MASTER[code_str])
        elif raw_c:
            labels.append(raw_c)
    return labels


def ndc_labels_to_codes(labels: list) -> list:
    """表示ラベル表記のリストから 2桁の NDC コードリストを抽出"""
    codes = []
    if not isinstance(labels, list):
        return codes
    for label in labels:
        label_str = str(label).strip()
        if ":" in label_str:
            code_part = label_str.split(":")[0].strip()
            codes.append(code_part)
        elif label_str:
            codes.append(label_str)
    return codes


def optimize_ndc_codes_for_regex(codes: list) -> str:
    """
    NDCコードリスト（例: ['00', '01', ..., '09', '76', '15.4']）を
    上位大分類への集約とSPARQL用正規表現パターンに最適化する
    """
    if not codes:
        return ""
    
    cleaned = set()
    for code in codes:
        c = str(code).strip()
        if c:
            cleaned.add(c)
    
    digit_groups = defaultdict(set)
    other_codes = set()
    for c in cleaned:
        if c.isdigit() and len(c) == 2:
            digit_groups[c[0]].add(c[1])
        else:
            other_codes.add(c)
            
    final_patterns = []
    for d, sub_digits in sorted(digit_groups.items()):
        if len(sub_digits) == 10:  # 0-9 すべて揃っている場合は1桁に圧縮
            final_patterns.append(d)
        else:
            for sd in sorted(list(sub_digits)):
                final_patterns.append(f"{d}{sd}")
                
    final_patterns.extend(sorted(list(other_codes)))
    
    escaped_patterns = [re.escape(p) for p in final_patterns]
    return "|".join(escaped_patterns)


def _safe_json_loads(text_content: str) -> dict:
    """
    LLMが生成したJSON文字列から不要なマークダウン記法やコメントを除去し、
    生の改行・制御文字 (Invalid control character) を許容して安全にパースします。
    """
    if not text_content:
        raise ValueError("LLMからの応答テキストが空です")

    cleaned = re.sub(r"^```json\s*", "", text_content.strip(), flags=re.MULTILINE)
    cleaned = re.sub(r"^```\s*", "", cleaned, flags=re.MULTILINE)
    cleaned = re.sub(r"\s*```$", "", cleaned, flags=re.MULTILINE)
    cleaned = re.sub(r"//.*$", "", cleaned, flags=re.MULTILINE)

    json_match = re.search(r"\{.*\}", cleaned, re.DOTALL)
    if json_match:
        cleaned = json_match.group(0)

    try:
        return json.loads(cleaned, strict=False)
    except json.JSONDecodeError:
        cleaned_escaped = re.sub(
            r'[\x00-\x1f\x7f-\x9f]', 
            lambda m: '\\n' if m.group(0) == '\n' else ('\\t' if m.group(0) == '\t' else ''), 
            cleaned
        )
        return json.loads(cleaned_escaped, strict=False)


def expand_query_with_llm(
    theme_prompt: str, 
    provider: str = "local", 
    api_base: str = DEFAULT_LLM_URL, 
    api_key: str = "", 
    model: str = DEFAULT_MODEL
) -> dict:
    """
    ユーザーが指定したテーマに基づき、Japan Searchからの再現率（Recall）最大化を目的とした検索クエリ拡張パラメータをLLMを用いて自動生成します。
    対象ドメインに関連する異体字・旧字体・専門用語・周辺概念を体系的に抽出します。
    検索キーワード一覧 (keywords) を基盤に、正規表現パターン (title_regex, desc_regex) を自動生成します。
    """
    system_prompt = (
        "あなたは日本の文化資源・人文学データの専門ライブラリアンおよびデータアナリストです。\n"
        "ユーザーが指定したテーマ・関心領域に基づき、Japan Searchから対象となり得る資料を【漏れなく網羅的（Recall最大化）】に収集するための検索パラメータを生成してください。\n\n"
        "【最重要方針】:\n"
        "1. 後段のフィルタリング工程でノイズは除外するため、現段階ではノイズ（無関係な資料）の混入を全く気にする必要はありません。\n"
        "2. 対象テーマが含まれる可能性が少しでもある全ての【旧字体・異体字、派生語、専門用語、流派・楽器・形態名、関連周辺単語】を20〜40個以上徹底的に出力してください。\n"
        "3. キーワードは単一の長い文章ではなく、「譜」「楽譜」「樂譜」「音譜」「調子本」「謡本」「聲明譜」のように個別の単語リスト (keywords) として出力してください。\n"
        "4. title_regex および desc_regex には、keywords リストに含まれるすべてのキーワードを '|'（パイプ）で結合した REGEX パターンを出力してください。\n"
        "5. 対象テーマに関連するNDC（日本十進分類法）分類コードを、下記「NDC 二次区分一覧表」を参照して【2桁の分類記号（二次区分）】（例: [\"76\", \"77\", \"18\"]）で漏れなく特定し、ndc_codes リストに出力してください。\n"
        "6. 【最重要: 除外(Negative) NDCの特定】対象テーマの単語（例: 「譜」「音」「曲」等）に文字列として偶発的にヒットしやすいものの、明らかにドメイン外・異分野となるNDCコード（例: 教科書 \"375\", 医学 \"49\", 家政学 \"59\", 建築 \"51\", 家譜・系図 \"288\" 等）を特定し、exclude_ndc_codes リストに出力してください。\n\n"
        "【NDC (日本十進分類法) 二次区分一覧表】:\n"
        "00:総記, 01:図書館・図書館情報学, 02:図書・書誌学, 03:百科事典, 04:一般論文集, 05:逐次刊行物, 06:団体・博物館, 07:ジャーナリズム・新聞, 08:叢書・全集, 09:貴重書・郷土資料\n"
        "10:哲学, 11:哲学各論, 12:東洋哲学, 13:西洋哲学, 14:心理学, 15:倫理学・道徳, 16:宗教, 17:神道, 18:仏教, 19:キリスト教\n"
        "20:歴史・文化史, 21:日本史, 22:アジア史, 23:ヨーロッパ史, 24:アフリカ史, 25:北アメリカ史, 26:南アメリカ史, 27:オセアニア史, 28:伝記, 29:地理・地誌・紀行\n"
        "30:社会科学, 31:政治, 32:法律, 33:経済, 34:財政, 35:統計, 36:社会, 37:教育, 38:風俗習慣・民俗学, 39:国防・軍事\n"
        "40:自然科学, 41:数学, 42:物理学, 43:化学, 44:天文学, 45:地球科学, 46:生物科学, 47:植物学, 48:動物学, 49:医学・薬学\n"
        "50:技術・工学, 51:建設・土木, 52:建築学, 53:機械工学, 54:電気工学, 55:海洋・軍事工学, 56:金属・鉱山, 57:化学工業, 58:製造工業, 59:家政学\n"
        "60:産業, 61:農業, 62:園芸, 63:蚕糸業, 64:畜産業, 65:林業, 66:水産業, 67:商業, 68:運輸・交通・観光, 69:通信事業\n"
        "70:芸術・美術, 71:彫刻, 72:絵画・書道, 73:版画・印章・印譜, 74:写真・印刷, 75:工芸, 76:音楽・舞踊, 77:演劇・映画・大衆芸能, 78:スポーツ, 79:諸芸・娯楽\n"
        "80:言語, 81:日本語, 82:中国語・東洋諸語, 83:英語, 84:ドイツ語, 85:フランス語, 86:スペイン・ポルトガル語, 87:イタリア語, 88:ロシア語, 89:その他言語\n"
        "90:文学, 91:日本文学, 92:中国文学・東洋文学, 93:英米文学, 94:ドイツ文学, 95:フランス文学, 96:スペイン文学, 97:イタリア文学, 98:ロシア文学, 99:その他文学\n\n"
        "必ず以下の純粋で有効なJSONフォーマットのみを出力してください（コメントや説明文は不要です）：\n"
        "{\n"
        '  "theme": "テーマ名",\n'
        '  "domain_definition": "資料判定用ドメイン定義文",\n'
        '  "keywords": ["譜", "楽譜", "樂譜", "音譜", "譜面", "曲譜", "音律", "調子本", "謡本", "舞譜", "琴譜", "笛譜", "三味線譜", "聲明譜"],\n'
        '  "ndc_codes": ["76", "77", "18"],\n'
        '  "exclude_ndc_codes": ["375", "49", "59", "288", "51"],\n'
        '  "title_regex": "譜|楽譜|樂譜|音譜|譜面|曲譜|音律|調子本|謡本|舞譜|琴譜|笛譜|三味線譜|聲明譜",\n'
        '  "desc_regex": "譜|楽譜|樂譜|音譜|譜面|曲譜|音律|調子本|謡本|舞譜|琴譜|笛譜|三味線譜|聲明譜"\n'
        "}\n"
    )

    user_prompt = f"対象テーマ: {theme_prompt}"

    # --- 1. Google Gemini API 呼び出しロジック ---
    if provider.lower() == "gemini":
        gemini_key = api_key or os.environ.get("GEMINI_API_KEY", "")
        if not gemini_key:
            return _build_fallback_result(theme_prompt, "Gemini APIキーが設定されていません。")

        target_model = model if model and model != "local-model" else "gemini-3.6-flash"
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{target_model}:generateContent?key={gemini_key}"
        
        payload = {
            "contents": [
                {
                    "role": "user",
                    "parts": [{"text": f"{system_prompt}\n\n{user_prompt}"}]
                }
            ],
            "generationConfig": {
                "temperature": 0.3,
                "responseMimeType": "application/json"
            }
        }

        try:
            res = requests.post(url, json=payload, timeout=30)
            if res.status_code == 200:
                resp_json = json.loads(res.text, strict=False)
                text_content = resp_json["candidates"][0]["content"]["parts"][0]["text"]
                parsed = _safe_json_loads(text_content)
                parsed["is_fallback"] = False
                parsed["fallback_reason"] = None
                return _sanitize_and_sync_result(parsed)
            else:
                return _build_fallback_result(theme_prompt, f"Gemini API エラー (Status {res.status_code}): {res.text[:200]}")
        except Exception as e:
            return _build_fallback_result(theme_prompt, f"Gemini API 接続例外: {e}")

    # --- 2. Local LLM / OpenAI 互換 API 呼び出しロジック ---
    else:
        req_headers = {"Content-Type": "application/json"}
        if api_key:
            req_headers["Authorization"] = f"Bearer {api_key}"

        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": f"/no_think\n思考は行わず直ちにJSONのみ出力してください。\n{system_prompt}"},
                {"role": "user", "content": user_prompt}
            ],
            "temperature": 0.2,
            "max_tokens": 4000
        }

        try:
            url = f"{api_base.rstrip('/')}/chat/completions"
            res = requests.post(url, json=payload, headers=req_headers, timeout=6000)
            if res.status_code == 200:
                resp_json = json.loads(res.text, strict=False)
                choice_msg = resp_json["choices"][0]["message"]
                content = choice_msg.get("content") or ""
                
                if not content.strip() and "reasoning_content" in choice_msg:
                    content = choice_msg.get("reasoning_content") or ""

                parsed = _safe_json_loads(content)
                parsed["is_fallback"] = False
                parsed["fallback_reason"] = None
                return _sanitize_and_sync_result(parsed)
            else:
                return _build_fallback_result(theme_prompt, f"APIエラー Status {res.status_code}: {res.text[:200]}")
        except Exception as e:
            return _build_fallback_result(theme_prompt, f"API接続エラー: {e}")


def optimize_keywords_for_regex(keywords: list[str]) -> list[str]:
    """
    部分文字列として包含される冗長なキーワードを除外して正規表現用キーワードリストを最適化
    例: ['譜', '楽譜', '音譜', '調子本'] -> ['譜', '調子本']
    """
    cleaned = [str(k).strip() for k in keywords if str(k).strip()]
    sorted_kws = sorted(list(set(cleaned)), key=len)
    optimized = []
    for kw in sorted_kws:
        if not any(short_kw in kw for short_kw in optimized):
            optimized.append(kw)
    return optimized


def optimize_regex_str(regex_str: str) -> str:
    """
    パイプ区切りの正規表現文字列を受け取り、包含関係にある冗長キーワードを除去して最適化
    丸かっこ () や角かっこ [] などの余分な包み込み記号を除去します
    """
    if not regex_str or not isinstance(regex_str, str):
        return ""
    # 文字列全体から丸かっこ・角かっこ・波かっこ・クォートを除去
    cleaned_str = re.sub(r"[\(\)\[\]\{\}\"']", "", regex_str)
    
    kws = [k.strip() for k in cleaned_str.split("|") if k.strip()]
    optimized = optimize_keywords_for_regex(kws)
    return "|".join(optimized)


def chunk_regex_str(regex_str: str, chunk_size: int = 12) -> list[str]:
    """
    パイプ区切りの REGEX 文字列を受け取り、指定サイズ (デフォルト12語) ごとの安全な REGEX 文字列リストに分割する
    Japan Search SPARQL サーバーでの 504 Gateway Timeout を物理的に回避します
    """
    if not regex_str or not isinstance(regex_str, str):
        return []
    cleaned_str = re.sub(r"[\(\)\[\]\{\}\"']", "", regex_str)
    kws = [k.strip() for k in cleaned_str.split("|") if k.strip()]
    opt_kws = optimize_keywords_for_regex(kws)
    if not opt_kws:
        return []

    chunked = []
    for i in range(0, len(opt_kws), chunk_size):
        sub_group = opt_kws[i:i + chunk_size]
        chunked.append("|".join(sub_group))
    return chunked


def regex_to_bif_contains(regex_str: str) -> str:
    """パイプ区切りの正規表現文字列を、Virtuosoの bif:contains 用のクエリ文字列に変換します (例: 'A' OR 'B')"""
    if not regex_str:
        return ""
    kws = [k.strip().replace("'", "") for k in regex_str.split("|") if k.strip()]
    return " OR ".join([f"'{k}'" for k in kws])


def _sanitize_and_sync_result(result: dict) -> dict:
    """keywords から title_regex および desc_regex を自動連動・確認・補正（包含関係の最適化含む）"""
    if "keywords" in result and isinstance(result["keywords"], list):
        kws = [str(k).strip() for k in result["keywords"] if str(k).strip()]
        result["keywords"] = kws
        
        # keywords から包含関係を除外した最適化済み REGEX パターンを作成
        optimized_kws = optimize_keywords_for_regex(kws)
        auto_regex = "|".join(optimized_kws)
        
        if not result.get("title_regex"):
            result["title_regex"] = auto_regex
        else:
            result["title_regex"] = optimize_regex_str(result["title_regex"])

        if not result.get("desc_regex"):
            result["desc_regex"] = auto_regex
        else:
            result["desc_regex"] = optimize_regex_str(result["desc_regex"])
    else:
        if result.get("title_regex"):
            result["title_regex"] = optimize_regex_str(result["title_regex"])
        if result.get("desc_regex"):
            result["desc_regex"] = optimize_regex_str(result["desc_regex"])

    return result


def _build_fallback_result(theme_prompt: str, reason: str) -> dict:
    """フォールバックルールベース結果の構築（ドメイン固定コードを排除し汎用化）"""
    logger.info(f"[LLM Expander] フォールバック適用: {reason}")
    print(f"[LLM Expander] フォールバック適用: {reason}")
    words = [w.strip() for w in re.split(r"[\s,・/／におけるについて等の文献資料]+", theme_prompt) if len(w.strip()) >= 2]
    keywords = words if words else [theme_prompt]
    ndc_codes = []
    exclude_ndc_codes = ["375", "49", "59", "288", "51"]

    opt_kws = optimize_keywords_for_regex(keywords)
    title_regex = "|".join(opt_kws)
    desc_regex = title_regex

    return {
        "theme": theme_prompt,
        "domain_definition": f"「{theme_prompt}」に関連する文化資源・文献・資料",
        "keywords": keywords,
        "ndc_codes": ndc_codes,
        "exclude_ndc_codes": exclude_ndc_codes,
        "title_regex": title_regex,
        "desc_regex": desc_regex,
        "is_fallback": True,
        "fallback_reason": reason
    }


def generate_sparql_queries(expansion_result: dict) -> list:
    """
    SPARQLクエリ一覧の自動生成 (Recall 最大化 ＆ 504 Timeout 回避チャンク分割 ＆ NDC除外フィルタ対応仕様)
    - rdf:type 絞り込みを排除し全RDFリソースを検索。
    - rdfs:label, schema:name, schema:about, schema:keywords, dct:subject, schema:description を網羅化。
    - 除外(Negative) NDCコードが指定されている場合、FILTER NOT EXISTS でタイトル・主題・説明文検索から確実・安全にブロック。
    - REGEXパターン長を12語ごとに自動分割し、Virtuosoサーバーの504 Timeoutを完全に回避。
    """
    raw_title_regex = expansion_result.get("title_regex", "")
    if not raw_title_regex and expansion_result.get("keywords"):
        kws = expansion_result.get("keywords")
        if isinstance(kws, list):
            raw_title_regex = "|".join(optimize_keywords_for_regex(kws))
        elif isinstance(kws, str):
            parsed_k = [w.strip() for w in re.split(r"[\n,・/／]+", kws) if w.strip()]
            raw_title_regex = "|".join(optimize_keywords_for_regex(parsed_k))

    raw_desc_regex = expansion_result.get("desc_regex", raw_title_regex)
    if not raw_desc_regex:
        raw_desc_regex = raw_title_regex
    
    rdf_types = expansion_result.get("blacklist_rdf_types", expansion_result.get("rdf_types", []))
    
    # システムメタデータノード（実態のないノード）を強制的に除外リストに追加
    system_excludes = [
        "https://jpsearch.go.jp/term/type/アクセス情報",
        "https://jpsearch.go.jp/term/type/ソース情報"
    ]
    rdf_types = list(set(rdf_types + system_excludes))
    
    type_filter_str = ""
    if rdf_types:
        uris = " ".join([f"<{uri}>" for uri in rdf_types])
        type_filter_str = f"FILTER NOT EXISTS {{\n                    VALUES ?excluded_type {{ {uris} }}\n                    ?s rdf:type ?excluded_type .\n                  }}"
    
    # --- 除外(Negative) NDC フィルターの構築 ---
    raw_exclude_ndc = expansion_result.get("exclude_ndc_codes", [])
    if isinstance(raw_exclude_ndc, str):
        raw_exclude_ndc = [c.strip() for c in re.split(r"[\n,・/／\s]+", raw_exclude_ndc) if c.strip()]
    
    # リスト内の各要素にスラッシュやカンマが含まれる場合も再分割して平坦化
    flattened_ex_codes = []
    for item in raw_exclude_ndc:
        if isinstance(item, str):
            for sub in re.split(r"[\n,・/／\s]+", item):
                if sub.strip():
                    flattened_ex_codes.append(sub.strip())
    
    exclude_ndc_filter_str = ""
    if flattened_ex_codes:
        ndc_pattern = optimize_ndc_codes_for_regex(flattened_ex_codes)
        if ndc_pattern:
            exclude_ndc_filter_str = f"""FILTER NOT EXISTS {{
                    {{ ?s schema:genre ?_ex_g . }} UNION {{ ?s schema:about ?_ex_g . }} UNION {{ ?s <http://purl.org/dc/terms/subject> ?_ex_g . }}
                    FILTER (
                      REGEX(STR(?_ex_g), "(ndc[0-9]*[#/]|/ndc/|^)({ndc_pattern})")
                    )
                  }}"""
    
    # 共通フィルタ文字列の結合
    filter_elements = [f for f in [type_filter_str, exclude_ndc_filter_str] if f]
    combined_filter_str = "\n                  ".join(filter_elements) if filter_elements else ""

    queries = []
    
    # 1. タイトル・名称 (rdfs:label / schema:name) 検索
    parsed_title_kws = [w.strip() for w in re.split(r"\|", raw_title_regex) if w.strip()]
    multi_char_kws = [w for w in parsed_title_kws if len(w) >= 2]
    single_char_kws = [w for w in parsed_title_kws if len(w) == 1]
    
    multi_regex = "|".join(multi_char_kws) if multi_char_kws else ""
    title_chunks = chunk_regex_str(multi_regex, chunk_size=12) if multi_regex else []
    
    for kw in single_char_kws:
        title_chunks.append(kw)
        
    for c_idx, t_pattern in enumerate(title_chunks):
        bif_str = regex_to_bif_contains(t_pattern)
        p_name = f"1-{c_idx+1}. タイトル・名称 網羅検索 (Part {c_idx+1})" if len(title_chunks) > 1 else "1. タイトル・名称 (label / name) 網羅検索"
        def make_q_title(pat):
            def q_title(lim, offset=0):
                return f"""
                PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
                PREFIX schema: <http://schema.org/>
                
                SELECT DISTINCT ?s WHERE {{
                  {combined_filter_str}
                  {{
                    ?s rdfs:label ?title .
                    ?title bif:contains "{pat}" .
                  }} UNION {{
                    ?s schema:name ?title .
                    ?title bif:contains "{pat}" .
                  }}
                }}
                OFFSET {offset}
                LIMIT {lim}
                """
            return q_title
        queries.append((p_name, make_q_title(bif_str)))

    # 2-A. 主題エンティティ (schema:about) 網羅検索
    for c_idx, t_pattern in enumerate(title_chunks):
        bif_str = regex_to_bif_contains(t_pattern)
        p_name = f"2A-{c_idx+1}. 主題エンティティ (schema:about) 網羅検索 (Part {c_idx+1})" if len(title_chunks) > 1 else "2A. 主題エンティティ (schema:about) 網羅検索"
        def make_q_about(pat):
            def q_about(lim, offset=0):
                return f"""
                PREFIX schema: <http://schema.org/>
                PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
                
                SELECT DISTINCT ?s WHERE {{
                  {combined_filter_str}
                  ?s schema:about ?about .
                  {{
                    ?about rdfs:label ?aboutLabel .
                    ?aboutLabel bif:contains "{pat}" .
                  }} UNION {{
                    ?about schema:name ?aboutLabel .
                    ?aboutLabel bif:contains "{pat}" .
                  }}
                }}
                OFFSET {offset}
                LIMIT {lim}
                """
            return q_about
        queries.append((p_name, make_q_about(bif_str)))

    # 2-B. 主題・件名・キーワード (schema:keywords / dct:subject) 検索
    for c_idx, t_pattern in enumerate(title_chunks):
        bif_str = regex_to_bif_contains(t_pattern)
        p_name = f"2B-{c_idx+1}. キーワード・件名 (keywords / subject) 網羅検索 (Part {c_idx+1})" if len(title_chunks) > 1 else "2B. キーワード・件名 (keywords / subject) 網羅検索"
        def make_q_subject(pat):
            def q_subject(lim, offset=0):
                return f"""
                PREFIX schema: <http://schema.org/>
                PREFIX dct: <http://purl.org/dc/terms/>
                
                SELECT DISTINCT ?s WHERE {{
                  {combined_filter_str}
                  {{
                    ?s schema:keywords ?kw .
                    ?kw bif:contains "{pat}" .
                  }} UNION {{
                    ?s dct:subject ?subj .
                    ?subj bif:contains "{pat}" .
                  }}
                }}
                OFFSET {offset}
                LIMIT {lim}
                """
            return q_subject
        queries.append((p_name, make_q_subject(bif_str)))

    # 3. 説明文・内容記述 (schema:description) 検索
    desc_kws = [w for w in re.split(r"\|", raw_desc_regex) if len(w.strip()) >= 2]
    safe_desc_regex = "|".join(desc_kws) if desc_kws else raw_desc_regex
    desc_chunks = chunk_regex_str(safe_desc_regex, chunk_size=8)[:5]

    for c_idx, d_pattern in enumerate(desc_chunks):
        bif_str = regex_to_bif_contains(d_pattern)
        p_name = f"3-{c_idx+1}. 説明文 網羅検索 (Part {c_idx+1})" if len(desc_chunks) > 1 else "3. 説明文 (description) 網羅検索"
        def make_q_desc(pat):
            def q_desc(lim, offset=0):
                return f"""
                PREFIX schema: <http://schema.org/>
                PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
                
                SELECT DISTINCT ?s WHERE {{
                  {combined_filter_str}
                  ?s rdfs:label ?label .
                  ?s schema:description ?desc .
                  ?desc bif:contains "{pat}" .
                }}
                OFFSET {offset}
                LIMIT {lim}
                """
            return q_desc
        queries.append((p_name, make_q_desc(bif_str)))

    # 4. NDC 二次区分・細分類 (schema:genre / schema:about) 網羅検索
    ndc_codes = expansion_result.get("ndc_codes", [])
    if isinstance(ndc_codes, str):
        ndc_codes = [c.strip() for c in re.split(r"[\n,・/／]+", ndc_codes) if c.strip()]

    if ndc_codes:
        inc_ndc_pattern = optimize_ndc_codes_for_regex(ndc_codes)
        if inc_ndc_pattern:
            def q_ndc(lim, offset=0):
                return f"""
                PREFIX schema: <http://schema.org/>
                
                SELECT DISTINCT ?s WHERE {{
                  {type_filter_str}
                  {{ ?s schema:genre ?genre . }} UNION {{ ?s schema:about ?genre . }}
                  FILTER (
                    REGEX(STR(?genre), "(ndc[0-9]*[#/]|/ndc/|^)({inc_ndc_pattern})")
                  )
                }}
                OFFSET {offset}
                LIMIT {lim}
                """
            queries.append(("4. NDC分類 (schema:genre / about) 網羅検索", q_ndc))

    # 5. ホワイトリスト (強制全件取得) 検索
    whitelist_rdf_types = expansion_result.get("whitelist_rdf_types", [])
    for uri in whitelist_rdf_types:
        uri_str = str(uri).strip()
        if not uri_str:
            continue
        type_name = uri_str.split("/")[-1]
        if "#" in type_name:
            type_name = type_name.split("#")[-1]
            
        p_name = f"5. ホワイトリスト強制全件検索 ({type_name})"
        def make_q_whitelist(tgt_uri):
            def q_whitelist(lim, offset=0):
                return f"""
                PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
                
                SELECT DISTINCT ?s WHERE {{
                  ?s rdf:type <{tgt_uri}> .
                }}
                OFFSET {offset}
                LIMIT {lim}
                """
            return q_whitelist
        queries.append((p_name, make_q_whitelist(uri_str)))

    return queries

