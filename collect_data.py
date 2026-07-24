# ============================================================
# collect_data.py  (v2 — 주도섹터 점수제 + 관제지수)
# ------------------------------------------------------------
# 하는 일:
#   ① DART 공시 수집 + 별점
#   ② 코스피/코스닥 지수 + 투자자별 수급
#   ③ 주도 섹터 6개  ← 2단계 선별 (강도40 + 거래대금35 + 확산도25)
#   ④ 관제지수(0~100) ← 요소별 가중합산 + 요소별 근거
#   → 전부 모아서 data_YYYYMMDD.json 으로 저장
# ============================================================

import requests
import pandas as pd
from bs4 import BeautifulSoup
import re
import json
import os
import io
import math
import yfinance as yf
from datetime import datetime

DART_KEY = os.environ.get("DART_API_KEY", "")
DATE = datetime.now().strftime("%Y%m%d")
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}


# ============================================================
# 공통 도구
# ============================================================
def clean_name(name):
    """종목명 옆의 표시기호(*)와 공백 제거."""
    return str(name).strip().rstrip("*").strip()


def to_num(x):
    """'+3.66%', '−1.38', '1,234' 같은 문자열을 숫자로. 실패하면 None."""
    if x is None:
        return None
    s = str(x).replace(",", "").replace("%", "").replace("+", "")
    s = s.replace("−", "-")  # 유니코드 마이너스 → 일반 마이너스
    try:
        return float(s)
    except ValueError:
        return None


def read_html_safe(html_text):
    """HTML 텍스트에서 표를 읽는다.
    최신 pandas는 문자열을 파일 경로로 오해하므로 io.StringIO로 감싼다.
    (구/신 pandas 양쪽에서 동작)"""
    if isinstance(html_text, bytes):
        html_text = html_text.decode("euc-kr", errors="replace")
    return pd.read_html(io.StringIO(html_text))


# ============================================================
# ① DART 공시
# ============================================================
def collect_dart():
    if not DART_KEY:
        print("⚠️ DART_API_KEY 없음 → 공시 수집 건너뜀")
        return []

    url = "https://opendart.fss.or.kr/api/list.json"
    params = {"crtfc_key": DART_KEY, "bgn_de": DATE, "end_de": DATE,
              "page_no": "1", "page_count": "100"}
    data = requests.get(url, params=params).json()

    별점룰북 = [
        (5, ["무상증자", "자기주식소각"]),
        (4, ["유상증자결정"]),
        (3, ["전환사채", "신주인수권부사채"]),
        (2, ["대량보유상황보고서", "자기주식취득", "자기주식처분"]),
        (1, ["기재정정"]),
    ]

    def 별점(공시명):
        for 점수, 키워드들 in 별점룰북:
            if any(k in 공시명 for k in 키워드들):
                return 점수
        return 2

    관심유형 = ["대량보유", "유상증자", "무상증자", "공급계약", "자기주식", "전환사채"]
    결과 = []
    for item in data.get("list", []):
        nm = item.get("report_nm", "")
        if any(k in nm for k in 관심유형):
            결과.append({
                "회사명": item.get("corp_name"),
                "공시명": nm,
                "별점": 별점(nm),
                "링크": f"https://dart.fss.or.kr/dsaf001/main.do?rcpNo={item.get('rcept_no')}",
            })
    결과.sort(key=lambda x: x["별점"], reverse=True)
    print(f"✅ 공시 {len(결과)}건")
    return 결과


# ============================================================
# ② 지수 + 수급
# ============================================================
def collect_index_and_flow():
    def 지수():
        url = "https://polling.finance.naver.com/api/realtime/domestic/index/KOSPI,KOSDAQ"
        res = requests.get(url, headers=HEADERS).json()
        out = {}
        for i, item in enumerate(res["datas"]):
            # 거래대금 관련 필드를 폭넓게 탐색 (API 필드명이 버전마다 다름)
            대금 = None
            for k in ("accumulatedTradingValue", "tradingValue", "accTradeValue",
                      "accumulatedTradingVolume"):
                if item.get(k) not in (None, ""):
                    대금 = item.get(k)
                    break
            out[item["stockName"]] = {
                "종가": item["closePrice"],
                "등락방향": item["compareToPreviousPrice"]["text"],
                "등락률": item["fluctuationsRatio"],
                "거래대금": 대금,
            }
            # ⚠️ 진단: 첫 항목의 사용 가능한 필드명을 한 번 찍어둔다.
            #    거래대금이 안 잡히면 이 로그를 보고 정확한 키를 연결할 수 있다.
            if i == 0 and 대금 is None:
                print(f"  ℹ️ 지수 API 필드 목록(거래대금 탐색용): {list(item.keys())}")
        return out

    def 수급(sosok):
        url = "https://finance.naver.com/sise/investorDealTrendDay.naver"
        res = requests.get(url, headers=HEADERS, params={"bizdate": DATE, "sosok": sosok, "page": "1"})
        res.encoding = "euc-kr"
        tables = read_html_safe(res.text)
        표 = tables[0]
        표.columns = ["날짜", "개인", "외국인", "기관계"] + list(표.columns[4:])
        오늘행 = 표[표["날짜"].astype(str).str.replace(".", "", regex=False) == DATE[2:]]
        if len(오늘행) == 0:
            실 = 표[표["날짜"].astype(str).str.contains(r"\d{2}\.\d{2}\.\d{2}", na=False, regex=True)]
            if len(실) == 0:
                return None
            오늘행 = 실.iloc[[0]]
        r = 오늘행.iloc[0]
        return {"개인": str(r["개인"]), "외국인": str(r["외국인"]), "기관계": str(r["기관계"])}

    out = {"지수": 지수(), "코스피_수급": 수급("01"), "코스닥_수급": 수급("02")}
    print("✅ 지수/수급")
    return out


# ============================================================
# 테마명 사전 (어려운 이름 → 쉬운 설명)
#   여기 없는 테마는 generate 단계에서 Claude가 보조 설명을 붙인다.
#   자주 나오는 애매한 테마명을 계속 여기에 추가하면 정확도가 올라감.
# ============================================================
THEME_DICT = {
    "S7": "반도체 소부장 그룹",
    "자원개발": "해외 광물·에너지 자원",
    "LNG": "액화천연가스",
    "MLCC": "적층세라믹콘덴서(전자부품)",
    "OLED": "유기발광 디스플레이",
    "면역항암제": "암 치료 신약",
    "CXL": "차세대 메모리 연결기술",
    "HBM": "고대역폭 메모리",
    "전력설비": "송배전·전력 인프라",
    "마이크로 LED": "차세대 디스플레이",
    "PCB": "인쇄회로기판",
    "리튬": "2차전지 핵심 원료",
    "희토류": "첨단산업 필수 광물",
    "탄소나노튜브": "차세대 소재",
}

# 이름 옆에 항상 붙일 부가설명 (요청: 로봇)
THEME_SUFFIX = {
    "로봇": "(산업용/협동로봇)",
    "지능형로봇/인공지능(AI)": "(산업용/협동로봇)",
}


# ============================================================
# ③+④ 테마 데이터 → 주도섹터 6개 선정 + 관제지수 재료(확산도)
# ============================================================
def collect_themes_and_gauge():
    """
    2단계 선별:
      1차) 테마 목록에서 '등락률' 상위 20개 후보 추림
      2차) 각 후보 상세를 열어 거래대금·확산도 계산
           → 강도40 + 거래대금35 + 확산도25 점수로 재정렬 → 상위 6개
    부산물: 주요 테마 평균 확산도(관제지수 ③ 재료)도 함께 수집
    """
    url_list = "https://finance.naver.com/sise/theme.naver"
    후보 = []       # (테마명, 번호, 테마등락률)
    중복 = set()

    for page in range(1, 8):
        res = requests.get(url_list, headers=HEADERS, params={"page": page})
        res.encoding = "euc-kr"
        soup = BeautifulSoup(res.text, "html.parser")
        links = soup.select("table.type_1 a[href*='sise_group_detail']")
        if not links:
            break

        링크들 = []
        for a in links:
            m = re.search(r"no=(\d+)", a.get("href", ""))
            링크들.append((a.get_text(strip=True), m.group(1) if m else None))

        try:
            tables = read_html_safe(res.text)
            테마표 = None
            for t in tables:
                if any("테마" in str(c) for c in t.columns):
                    테마표 = t
                    break
        except Exception:
            테마표 = None
        if 테마표 is None:
            continue

        이름컬 = next((c for c in 테마표.columns if "테마" in str(c)), 테마표.columns[0])
        등락컬 = next((c for c in 테마표.columns if "전일대비" in str(c) or "등락" in str(c)), None)

        for _, row in 테마표.iterrows():
            이름 = str(row[이름컬]).strip()
            if not 이름 or 이름 == "nan":
                continue
            등락 = to_num(row[등락컬]) if 등락컬 is not None else None
            번호 = next((no for nm, no in 링크들 if nm == 이름), None)
            if 이름 and 번호 and 번호 not in 중복:
                후보.append((이름, 번호, 등락))
                중복.add(번호)

    # ── 1차 필터: 등락률 상위 20개 ──
    유효 = [c for c in 후보 if c[2] is not None and not math.isnan(c[2])]
    유효.sort(key=lambda x: x[2], reverse=True)
    후보20 = 유효[:20]
    print(f"📊 1차 후보(등락률 상위) {len(후보20)}개 → 상세 분석 중...")

    # ── 2차: 각 후보 상세에서 거래대금·확산도 계산 ──
    분석 = []
    for 테마명, 번호, 테마등락 in 후보20:
        detail_url = "https://finance.naver.com/sise/sise_group_detail.naver"
        dres = requests.get(detail_url, headers=HEADERS, params={"type": "theme", "no": 번호})
        dres.encoding = "euc-kr"
        try:
            tables = read_html_safe(dres.text)
            종목표 = None
            for t in tables:
                if t.shape[1] >= 9 and t.shape[0] > 1:
                    종목표 = t
                    break
            if 종목표 is None:
                continue

            종목표 = 종목표.iloc[:, [0, 2, 4, 8]]
            종목표.columns = ["종목명", "현재가", "등락률", "거래대금"]
            종목표 = 종목표.dropna(subset=["종목명"])
            종목표 = 종목표[종목표["종목명"] != ""]
            종목표["종목명"] = 종목표["종목명"].apply(clean_name)
            종목표["등락_num"] = 종목표["등락률"].apply(to_num)
            종목표["대금_num"] = 종목표["거래대금"].apply(to_num)

            총 = len(종목표)
            오른 = int((종목표["등락_num"] > 0).sum())
            확산도 = (오른 / 총 * 100) if 총 else 0
            거래대금합 = float(종목표["대금_num"].fillna(0).sum())

            상위종목 = 종목표.sort_values("등락_num", ascending=False).head(4)
            분석.append({
                "테마명": 테마명,
                "테마등락": 테마등락,
                "거래대금합": 거래대금합,
                "확산도": float(확산도),
                "종목": 상위종목[["종목명", "현재가", "등락률", "거래대금"]].to_dict(orient="records"),
            })
        except Exception as e:
            print(f"  ⚠️ [{테마명}] 상세 실패: {e}")

    if not 분석:
        print("❌ 테마 상세를 하나도 못 가져옴")
        return {"주도섹터": [], "확산도_시장평균": None}

    # ── 점수화: 각 항목을 0~100 순위점수로 환산 후 가중합 ──
    def 순위점수(값리스트):
        vals = [v if v is not None else 0 for v in 값리스트]
        lo, hi = min(vals), max(vals)
        if hi == lo:
            return [50.0] * len(vals)
        return [(v - lo) / (hi - lo) * 100 for v in vals]

    강도 = 순위점수([a["테마등락"] for a in 분석])
    거래 = 순위점수([a["거래대금합"] for a in 분석])
    폭 = 순위점수([a["확산도"] for a in 분석])

    for i, a in enumerate(분석):
        a["주도력점수"] = round(강도[i] * 0.40 + 거래[i] * 0.35 + 폭[i] * 0.25, 1)

    분석.sort(key=lambda x: x["주도력점수"], reverse=True)

    # ── 종목 중복 제거: 이미 뽑힌 카드와 종목이 2개 이상 겹치면 건너뛴다 ──
    # (그렇지 않으면 "에너지 관련 테마 5개, 사실 종목은 같은 애들" 이 됨)
    주도6 = []
    이미쓴종목 = set()
    for a in 분석:
        이번종목 = {s["종목명"] for s in a.get("종목", [])}
        겹침 = len(이번종목 & 이미쓴종목)
        if 겹침 >= 2:
            print(f"  ⏭️  [{a['테마명']}] 건너뜀 — 이미 선택된 섹터와 종목 {겹침}개 중복")
            continue
        주도6.append(a)
        이미쓴종목 |= 이번종목
        if len(주도6) == 6:
            break

    print("🏆 주도 섹터 6개 (주도력점수 순, 중복 제거 적용):")
    for a in 주도6:
        et = a["테마등락"]
        et_s = f"{et:+.2f}%" if et is not None else "—"
        print(f"   {a['테마명']} — 점수 {a['주도력점수']} (등락 {et_s}, 확산도 {a['확산도']:.0f}%)")

    # ── 시장 전반 확산도: 상위 20개가 아니라 '전체 유효 테마' 기준으로 계산 ──
    #    (상위 20개만 보면 항상 90%대로 나와 매일 '과열'처럼 보이는 편향이 생김)
    상승테마 = sum(1 for c in 유효 if c[2] is not None and c[2] > 0)
    시장확산 = (상승테마 / len(유효) * 100) if 유효 else 50.0

    return {"주도섹터": 주도6, "확산도_시장평균": round(시장확산, 1)}


# ============================================================
# ④ 관제지수 계산
# ============================================================
def compute_gauge(지수수급, 확산도_시장):
    요소 = []  # (이름, 점수0~100, 가중치, 근거문구)

    지수 = 지수수급.get("지수", {})
    코 = to_num(지수.get("코스피", {}).get("등락률"))
    닥 = to_num(지수.get("코스닥", {}).get("등락률"))

    # ① 지수 등락률: ±4% → 0~100, 0% → 50
    if 코 is not None and 닥 is not None:
        평균 = (코 + 닥) / 2
        점1 = max(0, min(100, 50 + 평균 * 12.5))
        요소.append(("지수 등락률", round(점1), 0.30, f"코스피 {코:+.2f}%, 코스닥 {닥:+.2f}%"))

    # ③ 등락 종목 비율(확산도)
    if 확산도_시장 is not None:
        점3 = max(0, min(100, 확산도_시장))
        요소.append(("등락 종목 비율", round(점3), 0.25, f"주요 테마 평균 상승종목 {확산도_시장:.0f}%"))

    # ④ 외국인+기관 수급: ±3조(30000억) → 0~100
    코수 = 지수수급.get("코스피_수급", {}) or {}
    외 = to_num(코수.get("외국인"))
    기 = to_num(코수.get("기관계"))
    if 외 is not None and 기 is not None:
        합 = 외 + 기
        점4 = max(0, min(100, 50 + 합 / 30000 * 50))
        방향 = "순매수" if 합 > 0 else "순매도"
        요소.append(("외국인+기관 수급", round(점4), 0.15, f"외인+기관 {합:+,.0f}억 {방향}"))

    # ② 거래대금 / ⑤ 극단심리 → 데이터 확보 전 정직하게 생략 (TODO)

    if not 요소:
        return None

    총가중 = sum(w for _, _, w, _ in 요소)
    최종 = 0
    상세 = []
    for 이름, 점, w, 근거 in 요소:
        재w = w / 총가중
        최종 += 점 * 재w
        상세.append({"요소": 이름, "점수": 점, "가중치": round(재w * 100), "근거": 근거})
    최종 = round(최종)

    def 구간(v):
        if v < 20: return ("혹한", "🥶")
        if v < 40: return ("한파", "❄️")
        if v < 60: return ("보통", "🌤️")
        if v < 80: return ("온기", "🔥")
        return ("과열", "🌋")

    이름, 이모지 = 구간(최종)

    # ── 근거 배지 자동 생성 (첨부 이미지 스타일: 아이콘 + 짧은 문구) ──
    배지 = []
    if 코 is not None and 닥 is not None:
        if 코 < 0 and 닥 < 0:
            배지.append("📉 코스피·코스닥 동반 하락")
        elif 코 > 0 and 닥 > 0:
            배지.append("📈 코스피·코스닥 동반 상승")
        else:
            배지.append("↔️ 코스피·코스닥 혼조")
    if 확산도_시장 is not None:
        if 확산도_시장 >= 55:
            배지.append(f"🟢 시장 전반 상승 우위 ({확산도_시장:.0f}%)")
        elif 확산도_시장 <= 45:
            배지.append(f"🔵 시장 전반 하락 우위 ({확산도_시장:.0f}%)")
        else:
            배지.append(f"⚪ 상승·하락 팽팽 ({확산도_시장:.0f}%)")
    외 = to_num((지수수급.get("코스피_수급", {}) or {}).get("외국인"))
    기 = to_num((지수수급.get("코스피_수급", {}) or {}).get("기관계"))
    if 외 is not None and 기 is not None:
        합 = 외 + 기
        조 = 합 / 10000
        방향 = "순매수" if 합 > 0 else "순매도"
        배지.append(f"💸 외인+기관 {조:+.2f}조 {방향}")

    print(f"📡 관제지수 = {최종} ({이름} {이모지})")
    return {"점수": 최종, "구간": 이름, "이모지": 이모지, "상세": 상세, "배지": 배지}


# ============================================================
# ⑤ 핵심 뉴스 원본 수집 (네이버 증권 · 많이 본 뉴스)
# ------------------------------------------------------------
#   여기서는 "가공 없이 원본 제목+링크만" 가져온다.
#   합치기·요약·태그 붙이기는 Claude(generate_report.py)가 한다.
#   ⚠️ 이 URL 구조(mode=LSS2D)는 검증된 예시 자료를 근거로 했지만
#      네이버 페이지 구조는 종종 바뀐다. 첫 실행에서 0건이 나오면
#      diagnostic 출력을 보고 셀렉터를 조정해야 한다.
# ============================================================
def collect_news():
    url = "https://finance.naver.com/news/news_list.naver"
    # section_id=101(경제) / section_id2=258(증권) — "많이 본 뉴스"
    params = {"mode": "LSS2D", "section_id": "101", "section_id2": "258"}

    try:
        res = requests.get(url, headers=HEADERS, params=params, timeout=10)
        res.encoding = "euc-kr"
        soup = BeautifulSoup(res.text, "html.parser")
    except Exception as e:
        print(f"⚠️ 뉴스 페이지 요청 실패: {e}")
        return []

    결과 = []
    중복확인 = set()

    # 1차 시도: dl.newsList 안의 dd.articleSubject a 태그
    후보 = soup.select("dd.articleSubject a")
    if not 후보:
        # 2차 시도: 클래스명이 바뀌었을 경우 좀 더 느슨하게
        후보 = soup.select("a[href*='news_read']")

    for a in 후보:
        제목 = a.get("title") or a.get_text(strip=True)
        제목 = 제목.strip()
        href = a.get("href", "")
        if not 제목 or not href:
            continue
        if href.startswith("/"):
            링크 = "https://finance.naver.com" + href
        else:
            링크 = href
        if 제목 in 중복확인:
            continue
        중복확인.add(제목)
        결과.append({"제목": 제목, "링크": 링크})

    print(f"✅ 뉴스 원본 {len(결과)}건 수집")
    if len(결과) == 0:
        # 진단 정보: 페이지가 비었는지, 구조가 바뀐 건지 힌트를 남긴다
        print("  ⚠️ 0건 — 페이지 구조가 바뀌었을 수 있음. 응답 일부:")
        print("  " + res.text[:300].replace("\n", " "))
    else:
        print("  샘플:", 결과[0]["제목"][:40])

    return 결과[:15]  # Claude가 합치고 추릴 수 있게 넉넉히 15개까지


# ============================================================
# ⑥ 환율 · 유가 · 금리 (yfinance)
# ------------------------------------------------------------
#   숫자만 가져온다. 해석 문장은 build 단계나 Claude가 붙이지 않고
#   그냥 "숫자 그대로" 보여준다 (해석이 필요 없는 단순 시세이므로).
# ============================================================
MACRO_TICKERS = {
    "원달러환율": {"심볼": "KRW=X", "표시명": "원/달러 환율", "단위": ""},
    "WTI유가": {"심볼": "CL=F", "표시명": "WTI 유가", "단위": "$"},
    "미국채10년": {"심볼": "^TNX", "표시명": "미국채 10년물", "단위": "%"},
}


def collect_macro():
    결과 = {}
    for key, info in MACRO_TICKERS.items():
        try:
            t = yf.Ticker(info["심볼"])
            hist = t.history(period="5d")
            if hist.empty or len(hist) < 2:
                print(f"⚠️ {info['표시명']}: 데이터 부족")
                결과[key] = None
                continue
            마지막 = float(hist["Close"].iloc[-1])
            이전 = float(hist["Close"].iloc[-2])
            등락률 = (마지막 - 이전) / 이전 * 100
            결과[key] = {
                "값": round(마지막, 2),
                "등락률": round(등락률, 2),
                "표시명": info["표시명"],
                "단위": info["단위"],
            }
        except Exception as e:
            print(f"⚠️ {info['표시명']} 수집 실패: {e}")
            결과[key] = None

    성공 = sum(1 for v in 결과.values() if v is not None)
    print(f"✅ 환율/유가/금리 {성공}/{len(MACRO_TICKERS)}건 수집")
    return 결과


def collect_program_and_futures():
    """프로그램매매(차익/비차익)와 선물 수급을 수집한다.

    ⚠️ 네이버 페이지 구조를 이 환경에서 검증할 수 없어, 여러 후보 URL을 순서대로
       시도하고 실패하면 어떤 표가 있었는지 로그로 남긴다.
       첫 실행 로그를 보고 정확한 위치를 확정하면 된다.

    왜 중요한가:
      · 차익거래 = 선물-현물 가격차를 노린 기계적 매매 (방향성 아님)
      · 비차익거래 = 선물과 무관한 바스켓 매매 (실제 방향성 베팅)
      → 같은 '프로그램 매도 1조'라도 어느 쪽이냐에 따라 해석이 정반대다.
    """
    결과 = {"프로그램매매": None, "선물수급": None, "옵션수급": None}

    # ── 프로그램매매 ──
    후보 = [
        "https://finance.naver.com/sise/programDeal.naver",
        "https://finance.naver.com/sise/sise_program_deal.naver",
    ]
    for url in 후보:
        try:
            r = requests.get(url, headers=HEADERS, timeout=12)
            if r.status_code != 200:
                continue
            r.encoding = "euc-kr"
            tables = read_html_safe(r.text)
            찾음 = None
            for t in tables:
                cols = " ".join(str(c) for c in t.columns)
                if "차익" in cols or "비차익" in cols:
                    찾음 = t
                    break
            if 찾음 is not None:
                # 첫 데이터 행을 오늘치로 사용
                행 = 찾음.dropna(how="all").iloc[0].to_dict()
                결과["프로그램매매"] = {str(k): str(v) for k, v in 행.items()}
                print(f"✅ 프로그램매매 수집 ({url.split('/')[-1]})")
                break
            else:
                print(f"  ℹ️ 프로그램매매 표 못 찾음. 표 {len(tables)}개의 컬럼:")
                for i, t in enumerate(tables[:4]):
                    print(f"     표{i}: {list(t.columns)[:8]}")
        except Exception as e:
            print(f"  ⚠️ 프로그램매매 {url.split('/')[-1]} 실패: {type(e).__name__}")

    # ── 선물·옵션 투자자별 수급 ──
    #   sosok 코드가 문서화돼 있지 않아 여러 값을 시도하고,
    #   먼저 잡히는 것을 선물, 그다음을 옵션으로 본다. (첫 실행 로그로 확정 필요)
    파생후보 = [("선물수급", c) for c in ("03", "04")] + \
              [("옵션수급", c) for c in ("05", "06")]
    for 종류, sosok in 파생후보:
        if 결과[종류]:
            continue
        try:
            r = requests.get("https://finance.naver.com/sise/investorDealTrendDay.naver",
                             headers=HEADERS,
                             params={"bizdate": DATE, "sosok": sosok, "page": "1"}, timeout=12)
            if r.status_code != 200:
                continue
            r.encoding = "euc-kr"
            tables = read_html_safe(r.text)
            if not tables or tables[0].shape[0] < 2:
                continue
            표 = tables[0]
            표.columns = ["날짜", "개인", "외국인", "기관계"] + list(표.columns[4:])
            실 = 표[표["날짜"].astype(str).str.contains(r"\d{2}\.\d{2}\.\d{2}", na=False, regex=True)]
            if len(실) == 0:
                continue
            row = 실.iloc[0]
            결과[종류] = {"개인": str(row["개인"]), "외국인": str(row["외국인"]),
                       "기관계": str(row["기관계"]), "sosok": sosok}
            print(f"✅ {종류} 수집 (sosok={sosok})")
        except Exception as e:
            print(f"  ⚠️ {종류} sosok={sosok} 실패: {type(e).__name__}")

    미확보 = [k for k, v in 결과.items() if not v]
    if 미확보:
        print(f"⚠️ 미확보: {', '.join(미확보)} — 해당 부분은 '확인 불가'로 표시됩니다.")
    return 결과


# ============================================================
# ⑦ 마감 브리핑 — 방송사 유튜브 자막
# ------------------------------------------------------------
#   1단계) 유튜브 RSS(무료·키 불필요)로 각 채널의 '오늘 마감시황' 영상 찾기
#   2단계) Supadata API로 그 영상의 자막 가져오기
#
#   ⚠️ 저작권 주의: 여기서 수집한 자막은 '원문 그대로 싣기 위한 것이 아니라'
#      각 채널의 관점을 파악해 우리 문장으로 재구성하기 위한 재료다.
#      generate_report.py 프롬프트에서 직접 인용을 금지하고 있다.
#   ⚠️ 라이브 방송은 자막 API가 지원하지 않는다(완결된 영상만 가능).
# ============================================================
SUPADATA_KEY = os.environ.get("SUPADATA_API_KEY", "")

# 확인된 채널 ID (RSS로 채널명·오늘 영상 교차검증 완료)
BRIEF_CHANNELS = {
    "삼프로TV": "UChlv4GSd7OQl3js-jkLOnFA",
    "한국경제TV": "UCF8AeLlUbEpKju6v1H6p8Eg",
    "이데일리TV": "UC8Sv6O3Ux8ePVqorx8aOBMg",
}

# 마감시황 영상을 고를 때 우선순위 키워드 (앞쪽일수록 우선)
#   실제 채널들의 오늘 영상 제목을 보고 만든 목록이다.
BRIEF_KEYWORDS = [
    "마감시황", "마감 시황", "파이널포인트", "오늘장 마감", "장마감", "마감",
    "종목쇼", "넥스트시그널", "클로징",
    "코스피", "코스닥", "증시", "시황",
]

# 제외 키워드 — 마감 브리핑이 아닌 영상
BRIEF_EXCLUDE = ["#shorts", "shorts", "ETF골든타임", "광고"]

# 자막을 통째로 넣으면 비용이 커지므로 앞부분만 사용 (핵심 요약이 앞에 나옴)
TRANSCRIPT_LIMIT = 3500


def _find_today_video(channel_id):
    """RSS에서 오늘 올라온 영상 중 마감시황에 가장 가까운 것을 고른다."""
    url = f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"
    try:
        r = requests.get(url, headers=HEADERS, timeout=12)
        if r.status_code != 200:
            return None
    except Exception:
        return None

    entries = re.findall(r"<entry>(.*?)</entry>", r.text, re.S)
    오늘 = f"{DATE[:4]}-{DATE[4:6]}-{DATE[6:]}"
    후보 = []
    for e in entries:
        t = re.search(r"<title>(.*?)</title>", e)
        v = re.search(r"<yt:videoId>(.*?)</yt:videoId>", e)
        p = re.search(r"<published>(.*?)</published>", e)
        if not (t and v and p):
            continue
        if not p.group(1).startswith(오늘):
            continue  # 오늘 영상만
        제목 = t.group(1).replace("&quot;", '"').replace("&amp;", "&")
        # 마감 브리핑이 아닌 영상(쇼츠·정규 코너 등) 제외
        if any(x.lower() in 제목.lower() for x in BRIEF_EXCLUDE):
            continue
        후보.append({"제목": 제목, "videoId": v.group(1),
                    "링크": f"https://www.youtube.com/watch?v={v.group(1)}"})

    if not 후보:
        return None

    # 키워드 우선순위대로 탐색
    for kw in BRIEF_KEYWORDS:
        for c in 후보:
            if kw in c["제목"]:
                return c
    # ⚠️ 키워드가 하나도 안 맞으면 '마감 브리핑이 아니다'고 판단해 건너뛴다.
    #    아무 영상이나 가져오면 엉뚱한 콘텐츠가 리포트에 실린다.
    return None


def _fetch_transcript(video_id):
    """Supadata로 자막 텍스트를 가져온다."""
    if not SUPADATA_KEY:
        return None
    url = "https://api.supadata.ai/v1/youtube/transcript"
    try:
        r = requests.get(url,
                         params={"videoId": video_id, "text": "true", "lang": "ko"},
                         headers={"x-api-key": SUPADATA_KEY}, timeout=45)
        if r.status_code != 200:
            # 왜 실패했는지 바로 알 수 있게 상세 출력
            이유 = {
                401: "API 키가 잘못됨",
                404: "영상 없음/비공개",
                403: "접근 제한 영상",
                429: "무료 크레딧 소진 또는 속도제한",
            }.get(r.status_code, "기타 오류")
            print(f"    ⚠️ 자막 실패 HTTP {r.status_code} ({이유}): {r.text[:150]}")
            return None
        data = r.json()
        content = data.get("content")
        if isinstance(content, list):  # 타임스탬프 형식으로 온 경우
            content = " ".join(seg.get("text", "") for seg in content)
        return (content or "").strip()
    except Exception as e:
        print(f"    ⚠️ 자막 요청 오류: {type(e).__name__}")
        return None


def collect_briefings():
    if not SUPADATA_KEY:
        print("⚠️ SUPADATA_API_KEY 없음 → 마감 브리핑 건너뜀")
        return []

    import time
    결과 = []
    for 이름, cid in BRIEF_CHANNELS.items():
        영상 = _find_today_video(cid)
        if not 영상:
            print(f"  · {이름}: 오늘 영상 없음")
            continue
        print(f"  · {이름}: {영상['제목'][:40]}")
        자막 = _fetch_transcript(영상["videoId"])
        if not 자막:
            # 자막이 없어도 제목·링크는 남긴다 (링크 안내용)
            결과.append({"채널": 이름, "제목": 영상["제목"], "링크": 영상["링크"], "자막": ""})
        else:
            결과.append({"채널": 이름, "제목": 영상["제목"], "링크": 영상["링크"],
                        "자막": 자막[:TRANSCRIPT_LIMIT]})
        time.sleep(2.5)  # API 속도제한(10초당 5건) 여유 있게 준수

    있음 = sum(1 for b in 결과 if b["자막"])
    print(f"✅ 마감 브리핑 {len(결과)}개 채널 (자막 확보 {있음}건)")
    return 결과


# ============================================================
# 메인
# ============================================================
if __name__ == "__main__":
    print(f"=== {DATE} 데이터 수집 시작 ===\n")

    공시 = collect_dart()
    지수수급 = collect_index_and_flow()
    테마결과 = collect_themes_and_gauge()
    게이지 = compute_gauge(지수수급, 테마결과.get("확산도_시장평균"))
    뉴스원본 = collect_news()
    매크로 = collect_macro()
    파생 = collect_program_and_futures()
    마감브리핑 = collect_briefings()

    전체 = {
        "날짜": DATE,
        "공시": 공시,
        "지수수급": 지수수급,
        "주도섹터": 테마결과.get("주도섹터", []),
        "관제지수": 게이지,
        "뉴스원본": 뉴스원본,
        "매크로": 매크로,
        "파생": 파생,
        "마감브리핑": 마감브리핑,
    }

    경로 = f"data_{DATE}.json"
    with open(경로, "w", encoding="utf-8") as f:
        json.dump(전체, f, ensure_ascii=False, indent=2)
    print(f"\n🎉 완료! → {경로}")
