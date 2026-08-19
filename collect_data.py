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

SCRIPT_VERSION = "v2026.08.19-n12"   # ⬅ 버전 표시 (로그·리포트에서 확인용)
                             #    5개 파일(build_html/generate_report/collect_data/
                             #    make_thumb/notify_telegram)이 **항상 같은 번호**여야 한다.
                             #    번호가 다르면 일부 파일만 올라간 것이다.
DART_KEY = os.environ.get("DART_API_KEY", "")
DATE = datetime.now().strftime("%Y%m%d")

# ── 파일 보관 위치 ──
#   날짜별 원본(data_·report_ json)은 archive/ 폴더에 모은다.
#   저장소 첫 화면에 매일 3개씩 쌓이면 정작 중요한 .py 파일이 묻히기 때문이다.
#   ⚠️ report_*.html은 **루트에 그대로 둔다** — 이미 텔레그램·카톡으로 나간
#      https://.../report_YYYYMMDD.html 링크가 전부 깨지기 때문이다.
ARCHIVE = "archive"


def apath(name):
    """읽기용 경로 — archive/에 있으면 그것을, 없으면 루트를 쓴다(하위 호환)."""
    p = os.path.join(ARCHIVE, name)
    return p if os.path.exists(p) else name


def asave(name):
    """쓰기용 경로 — 항상 archive/ 아래. 폴더가 없으면 만든다."""
    os.makedirs(ARCHIVE, exist_ok=True)
    return os.path.join(ARCHIVE, name)


def alist(pattern):
    """archive/와 루트를 함께 훑어 파일명 목록을 준다(중복 제거)."""
    names = set()
    for d in (ARCHIVE, "."):
        try:
            names.update(f for f in os.listdir(d) if re.fullmatch(pattern, f))
        except FileNotFoundError:
            continue
    return sorted(names)

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
            def _pick(*keys):
                for k in keys:
                    if item.get(k) not in (None, ""):
                        return item.get(k)
                return None
            out[item["stockName"]] = {
                "종가": item["closePrice"],
                "등락방향": item["compareToPreviousPrice"]["text"],
                "등락률": item["fluctuationsRatio"],
                "거래대금": 대금,
                # 캔들용 시·고·저 (네이버 API 키가 버전마다 달라 후보를 폭넓게 탐색)
                "시가": _pick("openPrice", "openVal", "marketPrice"),
                "고가": _pick("highPrice", "highVal", "highPriceOfDay"),
                "저가": _pick("lowPrice", "lowVal", "lowPriceOfDay"),
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
            # ⚠️ 오늘 자료가 아직 안 올라온 경우 (2026-08-18 발견)
            #    예전에는 표의 첫 줄(= 직전 거래일)을 조용히 가져다 오늘 값으로 저장했다.
            #    그러면 **다른 날 수급이 오늘 숫자로 리포트에 실린다.**
            #    → 남의 날짜를 오늘로 둔갑시키지 않는다. 못 구했으면 못 구했다고 한다.
            실 = 표[표["날짜"].astype(str).str.contains(r"\d{2}\.\d{2}\.\d{2}", na=False, regex=True)]
            찾음 = str(실.iloc[0]["날짜"]) if len(실) else "없음"
            print(f"  ⚠️ 수급({sosok}) — {DATE} 자료가 아직 없습니다 "
                  f"(표의 최신 날짜: {찾음}). 오늘 수급은 '미확보'로 둡니다.")
            return None
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
                # 이 주도섹터가 '내 계좌 구역' 어느 줄에 속하는지 함께 저장한다.
                #   화면에서 "소캠(SOCAMM) · 반도체 구역"처럼 붙여 보여주기 위함.
                "계좌구역": grid_slot_of(테마명),
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

    return {"주도섹터": 주도6, "확산도_시장평균": round(시장확산, 1),
            "테마후보": 유효}   # 격자(collect_account_grid)가 재활용한다


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

    return 결과[:30]  # TOP5만 쓰지만, 리포트와 안 겹치는 걸 고를 수 있게 후보는 넉넉히


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
    "국제금": {"심볼": "GC=F", "표시명": "국제 금", "단위": "$"},   # 안전자산 심리 — 코스피와 자주 역상관
}


def _is_expiry_day(ymd):
    """그날이 파생 만기일인가 — 매월 두 번째 목요일.

    ⚠️ 왜 저장하나: 만기일엔 비차익이 기계적으로 크게 튄다.
       방향성 베팅이 아니라 지수 편입·교체에 따른 조정이라, 비중 통계에
       섞이면 결과가 오염된다. build_html의 basket_followup(만기제외=True)이
       이 필드를 보고 표본에서 뺀다. 지금 안 심으면 3개월 뒤 통계가
       오염된 채로 켜진다.
       (3·6·9·12월은 선물+옵션 동시 만기 = '네 마녀의 날'로 더 크게 튄다)
    """
    try:
        d = datetime.strptime(str(ymd), "%Y%m%d")
    except Exception:
        return False
    첫날 = d.replace(day=1)
    첫목 = 1 + ((3 - 첫날.weekday()) % 7)      # 그 달 첫 목요일
    return d.day == 첫목 + 7                   # 두 번째 목요일


def _flow_is_weekend(ymd):
    """YYYYMMDD가 토·일인가."""
    try:
        return datetime.strptime(str(ymd), "%Y%m%d").weekday() >= 5
    except Exception:
        return False


_FLOW_KEYS = ("외현", "기관", "외선", "비차익", "코스피등락")


def _flow_same(a, b):
    """두 줄의 수급 값이 완전히 같은가 = 데이터가 갱신되지 않았다는 뜻.

    서로 다른 두 거래일에 이 5개 실수가 전부 일치할 확률은 사실상 0이다.
    따라서 같다면 '휴장일에 직전 거래일 값을 그대로 받아온 것'으로 본다.
    """
    if not a or not b:
        return False
    if all(a.get(k) is None for k in _FLOW_KEYS):
        return False
    return all(a.get(k) == b.get(k) for k in _FLOW_KEYS)


def prune_flow_history(이력):
    """휴장일에 잘못 들어간 줄을 걷어낸다.

    ⚠️ 왜 필요한가 (2026-08-18 발견)
       워크플로가 8/15(토)·8/16(일)·8/17(대체공휴일)에도 돌았고,
       pykrx/네이버가 직전 거래일(8/14) 값을 그대로 돌려줘 같은 줄이 4개 쌓였다.
       그 결과 리포트가 '기관 4일 연속 매도'라고 표시했다 — 실제로는 1일이다.
       연속일수·평균·순위·차트가 전부 오염되므로 반드시 걷어내야 한다.

    거르는 기준 두 가지
      ① 토·일 (날짜만으로 확정 판정)
      ② 직전 줄과 수급 값이 완전히 동일 (공휴일·대체공휴일이 여기서 걸린다)

    ②를 쓰는 이유: 공휴일 표(KRX_HOLIDAYS)는 generate_report·build_html에
    이미 두 벌이 있어 세 번째 사본을 두면 매년 세 곳을 고쳐야 한다.
    값이 안 바뀐 날은 어차피 휴장이므로, 표 없이도 같은 결과가 나온다.
    """
    if not 이력:
        return 이력
    이력 = sorted([x for x in 이력 if x.get("날짜")], key=lambda x: x["날짜"])
    나온것, 버린주말, 버린중복 = [], 0, 0
    for row in 이력:
        if _flow_is_weekend(row["날짜"]):
            버린주말 += 1
            continue
        if 나온것 and _flow_same(row, 나온것[-1]):
            버린중복 += 1
            continue
        나온것.append(row)
    if 버린주말 or 버린중복:
        print(f"   🧹 휴장일 정리: 주말 {버린주말}일 · 직전과 동일 {버린중복}일 제거 "
              f"→ 거래일 {len(나온것)}일치")
    return 나온것


def backfill_flow_history(이력):
    """과거 data_YYYYMMDD.json 을 훑어 flow_history의 빈 날짜를 메운다.

    새 코너를 붙인 날 그래프가 한 점뿐이면 볼 게 없다. 그런데 지난 리포트의
    data 파일에는 이미 '지수수급'이 들어 있어서 실탄(외국인+기관)은 복원할 수 있다.
    (프로그램매매는 최근에야 수집되기 시작해 과거분은 비차익이 없다 —
     비차익은 '오늘의 바스켓 비중'에만 쓰이므로 그래프에는 지장이 없다)
    한 번 메워지면 그 뒤로는 매일 한 줄씩 정상 누적된다.
    """
    def _f(v):
        try:
            return float(str(v).replace(",", ""))
        except (TypeError, ValueError):
            return None

    기존 = {x.get("날짜"): x for x in 이력}
    추가 = 보강 = 0
    for f in alist(r"data_\d{8}\.json"):
        m = re.fullmatch(r"data_(\d{8})\.json", f)
        if not m:
            continue
        ymd = m.group(1)
        try:
            with open(apath(f), encoding="utf-8") as fp:
                d = json.load(fp)
        except Exception:
            continue

        코 = ((d.get("지수수급") or {}).get("지수") or {}).get("코스피", {})
        코등락 = _f(코.get("등락률"))
        # 캔들용 시·고·저·종 (data에 있으면 가져온다 — 없으면 None)
        ohlc = {k: _f(코.get(v)) for k, v in
                (("시가", "시가"), ("고가", "고가"), ("저가", "저가"), ("종가", "종가"))}

        # ── 이미 있는 날짜: 빈 필드만 보강 (코스피등락·시고저) ──
        if ymd in 기존:
            row = 기존[ymd]
            채움 = False
            if row.get("코스피등락") is None and 코등락 is not None:
                row["코스피등락"] = 코등락; 채움 = True
            for k, v in ohlc.items():
                if v is not None and row.get(k) is None:
                    row[k] = v; 채움 = True
            if 채움:
                보강 += 1
            continue

        # ── 없는 날짜: 새로 복원 ──
        코수 = ((d.get("지수수급") or {}).get("코스피_수급")) or {}
        외현, 기관 = _f(코수.get("외국인")), _f(코수.get("기관계"))
        if 외현 is None or 기관 is None:
            continue
        파생 = d.get("파생") or {}
        비차익p = _f((파생.get("프로그램매매") or {}).get("비차익거래_순매수"))
        실탄p = round(외현 + 기관)
        조합p = None
        if 비차익p is not None and 실탄p != 0:
            조합p = {(True, True): "지수형매수", (True, False): "종목장세",
                    (False, True): "지수만방어", (False, False): "지수형매도"}[
                    (실탄p > 0, 비차익p > 0)]
        새행 = {"날짜": ymd, "만기": _is_expiry_day(ymd), "외현": 외현, "기관": 기관,
               "외선": _f((파생.get("선물수급") or {}).get("외국인")),
               "비차익": 비차익p, "실탄": 실탄p,
               "코스피등락": 코등락, "조합": 조합p}
        새행.update({k: v for k, v in ohlc.items() if v is not None})
        이력.append(새행)
        추가 += 1
    if 추가 or 보강:
        print(f"   📦 과거 복원: 신규 {추가}일 · 빈 필드 보강 {보강}일")
    return 이력


def update_flow_history(지수수급, 파생):
    """수급 관제신호의 원료 — 실탄(외국인+기관 현물)·선물·비차익을 매일 쌓는다.

    flow_history.json 에 하루 한 줄씩 누적하며, 같은 날짜로 다시 실행되면
    그 줄을 덮어쓴다(재발행 안전). 60거래일까지만 보관한다.
    ⚠️ daily.yml 의 git add 목록에 flow_history.json 이 있어야 커밋된다.
    """
    파일 = "flow_history.json"
    이력 = []
    try:
        if os.path.exists(파일):
            with open(파일, encoding="utf-8") as f:
                이력 = json.load(f)
        if not isinstance(이력, list):
            이력 = []
    except Exception as e:
        print(f"⚠️ flow_history 읽기 실패({type(e).__name__}) — 새로 시작합니다.")
        이력 = []

    def _f(v):
        try:
            return float(str(v).replace(",", ""))
        except (TypeError, ValueError):
            return None

    코수 = (지수수급 or {}).get("코스피_수급") or {}
    외현 = _f(코수.get("외국인"))
    기관 = _f(코수.get("기관계"))
    외선 = _f(((파생 or {}).get("선물수급") or {}).get("외국인"))
    프로 = (파생 or {}).get("프로그램매매") or {}
    비차익 = _f(프로.get("비차익거래_순매수"))

    if 외현 is None or 기관 is None:
        print("⚠️ 현물 수급 미확보 — flow_history에 오늘을 기록하지 않습니다.")
        return 이력

    # ⚠️ 휴장일 방어 — 주말에는 아예 기록하지 않는다.
    #    (공휴일은 값이 직전과 같아서 아래 prune_flow_history가 걸러낸다)
    if _flow_is_weekend(DATE):
        print(f"🛑 {DATE}는 주말입니다 — flow_history에 기록하지 않습니다.")
        return prune_flow_history(이력)

    코 = ((지수수급 or {}).get("지수") or {}).get("코스피", {})
    코등락 = _f(코.get("등락률"))
    실탄값 = round(외현 + 기관)
    # 조합 태그: 나중에 "올해 🟠 종목 장세 며칠, 그때 지수는?" 통계의 원료.
    # 부호만으로 복원 가능하지만, 기준이 바뀌어도 그날의 판정이 보존되도록 저장해둔다.
    조합 = None
    if 비차익 is not None and 실탄값 != 0:
        조합 = {(True, True): "지수형매수", (True, False): "종목장세",
               (False, True): "지수만방어", (False, False): "지수형매도"}[
               (실탄값 > 0, 비차익 > 0)]
    만기 = _is_expiry_day(DATE)
    if 만기:
        print("   📅 오늘은 파생 만기일 — 비차익 통계 표본에서 제외되도록 표시합니다.")
    오늘 = {"날짜": DATE, "만기": 만기, "외현": 외현, "기관": 기관,
           "외선": 외선, "비차익": 비차익,
           "실탄": 실탄값, "코스피등락": 코등락, "조합": 조합,
           # 캔들용 시·고·저·종 (있을 때만 — 20일 쌓이면 build_html이 캔들로 전환)
           "시가": _f(코.get("시가")), "고가": _f(코.get("고가")),
           "저가": _f(코.get("저가")), "종가": _f(코.get("종가"))}
    이력 = [x for x in 이력 if x.get("날짜") != DATE]      # 재발행 시 덮어쓰기
    이력.append(오늘)
    이력 = backfill_flow_history(이력)                    # 빈 과거 날짜 메우기
    이력 = prune_flow_history(이력)                       # 휴장일에 들어온 줄 제거
    이력 = 이력[-60:]

    with open(파일, "w", encoding="utf-8") as f:
        json.dump(이력, f, ensure_ascii=False, indent=1)
    print(f"✅ flow_history 갱신: 오늘 실탄 {오늘['실탄']:+,}억 · 누적 {len(이력)}일치")
    return 이력


def collect_updown_counts():
    """코스피·코스닥의 상승/하락/보합 종목 수.

    네이버 국내증시 메인에 시장별로 "상승 N 상한 n 보합 N 하락 N"이 있다.
    이 숫자는 pykrx 등으로 **사후 복원이 불가능**해서 매일 그날 담아둬야 한다.
    실패하면 None — market_history에 null로 남기고 추정값을 넣지 않는다.
    """
    try:
        r = requests.get("https://finance.naver.com/sise/",
                         headers=HEADERS, timeout=12)
        r.encoding = "euc-kr"
        t = r.text
    except Exception:
        return None
    결과 = {}
    # 시장 블록별로 상승/보합/하락 수를 찾는다 (KOSPI 블록이 먼저, KOSDAQ이 다음)
    블록들 = re.split(r"(?i)kosdaq", t, maxsplit=1)
    이름들 = ["코스피", "코스닥"]
    for 이름, 블록 in zip(이름들, 블록들 if len(블록들) == 2 else [t, ""]):
        m = {}
        for k in ("상승", "보합", "하락"):
            mm = re.search(k + r"[^0-9]{0,40}?([\d,]+)", 블록)
            if mm:
                m[k] = int(mm.group(1).replace(",", ""))
        if len(m) == 3:
            결과[이름] = m
    if not 결과:
        print("⚠️ 상승/하락 종목 수를 찾지 못했습니다 (null로 기록)")
        return None
    for 이름, m in 결과.items():
        print(f"   {이름} 상승 {m['상승']} · 보합 {m['보합']} · 하락 {m['하락']}")
    return 결과


def update_market_history(지수수급, 파생, 게이지, 등락수):
    """market_history.json — 서비스가 존재하는 한 **영구 누적**하는 시장 일지.

    🔴 원칙: 절대 자르지 않는다 (60일 캡 없음). 같은 날짜 재실행 시에만 그 행 덮어쓰기.
       상승/하락 종목 수·레이더 이력 등은 사후 복원이 불가능한 데이터다.
       이 파일이 유료 챕터(국면 내비·확률 캘린더·수급 온도)의 원료가 된다.
    ⚠️ daily.yml 의 git add 목록에 market_history.json 이 있어야 커밋된다.
    """
    파일 = "market_history.json"
    본체 = {"meta": {"설명": "영구 누적. 절대 자르지 않음.",
                   "시작일": f"{DATE[:4]}-{DATE[4:6]}-{DATE[6:]}", "스키마버전": 1},
           "일별": []}
    try:
        if os.path.exists(파일):
            with open(파일, encoding="utf-8") as f:
                기존 = json.load(f)
            if isinstance(기존, dict) and isinstance(기존.get("일별"), list):
                본체 = 기존
    except Exception as e:
        print(f"⚠️ market_history 읽기 실패({type(e).__name__}) — 새로 시작")

    def _f(v):
        try:
            return float(str(v).replace(",", "").replace("%", ""))
        except (TypeError, ValueError):
            return None

    def _대금억(s):
        # "25,657,754백만" → 억원
        v = _f(str(s).replace("백만", ""))
        return round(v / 100) if v is not None else None

    지수 = (지수수급 or {}).get("지수") or {}
    코 = 지수.get("코스피") or {}
    닥 = 지수.get("코스닥") or {}
    코수 = (지수수급 or {}).get("코스피_수급") or {}
    닥수 = (지수수급 or {}).get("코스닥_수급") or {}
    외 = _f(코수.get("외국인")); 기 = _f(코수.get("기관계")); 개 = _f(코수.get("개인"))
    실탄 = round(외 + 기) if (외 is not None and 기 is not None) else None
    프로 = (파생 or {}).get("프로그램매매") or {}
    비차익 = _f(프로.get("비차익거래_순매수"))
    외선 = _f(((파생 or {}).get("선물수급") or {}).get("외국인"))
    바스켓 = None
    if 비차익 is not None and 실탄 and abs(실탄) >= 2000 and (실탄 > 0) == (비차익 > 0):
        바스켓 = round(비차익 / 실탄, 3)
    조합 = None
    if 비차익 is not None and 실탄:
        조합 = {(True, True): "지수형매수", (True, False): "종목장세",
               (False, True): "지수만방어", (False, False): "지수형매도"}[
               (실탄 > 0, 비차익 > 0)]
    등락수 = 등락수 or {}
    코등락수 = 등락수.get("코스피") or {}
    닥등락수 = 등락수.get("코스닥") or {}
    def _합(k):
        a, b = 코등락수.get(k), 닥등락수.get(k)
        return (a or 0) + (b or 0) if (a is not None or b is not None) else None

    요일 = "월화수목금토일"[datetime.strptime(DATE, "%Y%m%d").weekday()]
    행 = {"날짜": f"{DATE[:4]}-{DATE[4:6]}-{DATE[6:]}", "요일": 요일,
         "코스피": _f(코.get("종가")), "코스피등락": _f(코.get("등락률")),
         "코스닥": _f(닥.get("종가")), "코스닥등락": _f(닥.get("등락률")),
         "거래대금_코스피": _대금억(코.get("거래대금")),
         "거래대금_코스닥": _대금억(닥.get("거래대금")),
         "상승종목수": _합("상승"), "하락종목수": _합("하락"), "보합종목수": _합("보합"),
         "상승_코스피": 코등락수.get("상승"), "하락_코스피": 코등락수.get("하락"),
         "상승_코스닥": 닥등락수.get("상승"), "하락_코스닥": 닥등락수.get("하락"),
         "외국인_코스피": 외, "기관_코스피": 기, "개인_코스피": 개,
         "외국인_코스닥": _f(닥수.get("외국인")), "기관_코스닥": _f(닥수.get("기관계")),
         "개인_코스닥": _f(닥수.get("개인")),
         "실탄": 실탄, "외국인선물": 외선, "비차익": 비차익, "바스켓비중": 바스켓,
         "조합태그": 조합,
         "관제지수": (게이지 or {}).get("점수"), "관제구간": (게이지 or {}).get("구간"),
         "스키마버전": 1}

    오늘키 = 행["날짜"]
    본체["일별"] = [x for x in 본체["일별"] if x.get("날짜") != 오늘키]
    본체["일별"].append(행)
    본체["일별"].sort(key=lambda x: x.get("날짜", ""))
    # ⚠️ 자르지 않는다 — 영구 보관이 이 파일의 존재 이유

    # ── 최초 1회 백필: 과거 data_*.json에서 복원 가능한 필드만 ──
    있는날 = {x.get("날짜") for x in 본체["일별"]}
    추가 = 0
    for f in alist(r"data_\d{8}\.json"):
        m = re.fullmatch(r"data_(\d{8})\.json", f)
        if not m:
            continue
        ymd = m.group(1)
        키 = f"{ymd[:4]}-{ymd[4:6]}-{ymd[6:]}"
        if 키 in 있는날:
            continue
        try:
            with open(apath(f), encoding="utf-8") as fp:
                d = json.load(fp)
        except Exception:
            continue
        p지 = (d.get("지수수급") or {}).get("지수") or {}
        p코, p닥 = p지.get("코스피") or {}, p지.get("코스닥") or {}
        p코수 = (d.get("지수수급") or {}).get("코스피_수급") or {}
        p닥수 = (d.get("지수수급") or {}).get("코스닥_수급") or {}
        p외, p기 = _f(p코수.get("외국인")), _f(p코수.get("기관계"))
        p파 = d.get("파생") or {}
        p비 = _f((p파.get("프로그램매매") or {}).get("비차익거래_순매수"))
        p실 = round(p외 + p기) if (p외 is not None and p기 is not None) else None
        p조 = None
        if p비 is not None and p실:
            p조 = {(True, True): "지수형매수", (True, False): "종목장세",
                  (False, True): "지수만방어", (False, False): "지수형매도"}[(p실 > 0, p비 > 0)]
        본체["일별"].append({
            "날짜": 키, "요일": "월화수목금토일"[datetime.strptime(ymd, "%Y%m%d").weekday()],
            "코스피": _f(p코.get("종가")), "코스피등락": _f(p코.get("등락률")),
            "코스닥": _f(p닥.get("종가")), "코스닥등락": _f(p닥.get("등락률")),
            "거래대금_코스피": _대금억(p코.get("거래대금")),
            "거래대금_코스닥": _대금억(p닥.get("거래대금")),
            "상승종목수": None, "하락종목수": None, "보합종목수": None,   # 복원 불가 — 추정 금지
            "상승_코스피": None, "하락_코스피": None, "상승_코스닥": None, "하락_코스닥": None,
            "외국인_코스피": p외, "기관_코스피": p기, "개인_코스피": _f(p코수.get("개인")),
            "외국인_코스닥": _f(p닥수.get("외국인")), "기관_코스닥": _f(p닥수.get("기관계")),
            "개인_코스닥": _f(p닥수.get("개인")),
            "실탄": p실, "외국인선물": _f((p파.get("선물수급") or {}).get("외국인")),
            "비차익": p비, "바스켓비중": None, "조합태그": p조,
            "관제지수": (d.get("관제지수") or {}).get("점수"),
            "관제구간": (d.get("관제지수") or {}).get("구간"), "스키마버전": 1})
        추가 += 1
    if 추가:
        본체["일별"].sort(key=lambda x: x.get("날짜", ""))
        print(f"   📦 market_history 백필 {추가}일치 (복원 불가 필드는 null)")

    with open(파일, "w", encoding="utf-8") as f:
        json.dump(본체, f, ensure_ascii=False, indent=1)
    print(f"✅ market_history 갱신: 총 {len(본체['일별'])}일치 (영구 누적)")
    return 본체


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


def naver_get(url, referer=None):
    """네이버 페이지를 가져오되 **인코딩을 자동 판별**한다.

    네이버는 페이지마다 인코딩이 달라(euc-kr / utf-8) 한쪽으로 고정하면
    한글이 깨져서, 페이지가 정상적으로 열려도 '차익' 같은 단어를 찾지 못한다.
    세 가지로 디코딩해보고 한글이 가장 멀쩡한 것을 고른다.
    반환: (HTTP 상태코드, 본문 문자열, 사용한 인코딩)
    """
    h = dict(HEADERS)
    if referer:
        h["Referer"] = referer
    r = requests.get(url, headers=h, timeout=12)
    if r.status_code != 200:
        return r.status_code, "", None
    raw = r.content
    최고, 최고점, 최고이름 = "", -1, None
    for enc in ("euc-kr", "cp949", "utf-8"):
        try:
            t = raw.decode(enc, errors="replace")
        except Exception:
            continue
        한글 = sum(1 for ch in t if "\uac00" <= ch <= "\ud7a3")
        깨짐 = t.count("\ufffd")
        점수 = 한글 - 깨짐 * 3
        if 점수 > 최고점:
            최고, 최고점, 최고이름 = t, 점수, enc
    return 200, 최고, 최고이름


def _flatten_cols(t):
    """네이버 표는 헤더가 2단(MultiIndex)인 경우가 많다. '상위_하위'로 평탄화한다."""
    if isinstance(t.columns, pd.MultiIndex):
        t.columns = ["_".join(str(x) for x in col).strip() for col in t.columns]
    else:
        t.columns = [str(x) for x in t.columns]
    return t


def _num(v):
    """'-1,234' / '1,234억' 같은 문자열에서 숫자만 뽑는다."""
    if v is None:
        return None
    txt = str(v).replace(",", "").replace("+", "").strip()
    m = re.search(r"-?\d+(?:\.\d+)?", txt)
    if not m:
        return None
    try:
        return float(m.group(0))
    except ValueError:
        return None


def _pick_data_row(t, 날짜키=None):
    """네이버 표의 **첫 줄은 빈 줄(NaN)** 이다. 진짜 데이터가 있는 첫 행을 고른다.

    ⚠️ 이게 지난 실패의 원인이었다. iloc[0]을 읽었더니 전부 NaN이라
       숫자 추출이 매번 None으로 떨어졌다.
    날짜키가 주어지면(일별 표) 그 날짜 행을 우선 찾고, 없으면 첫 데이터 행을 쓴다.
    """
    t = _flatten_cols(t.copy()).dropna(how="all")
    if t.empty:
        return None, None
    첫컬 = t.columns[0]
    후보 = []
    for _, row in t.iterrows():
        라벨 = str(row[첫컬]).strip()
        if 라벨 in ("", "nan", "None"):
            continue
        후보.append((라벨, row))
    if not 후보:
        return None, None
    if 날짜키:
        for 라벨, row in 후보:
            if 날짜키 in 라벨:
                return 라벨, row
    return 후보[0]


def _unit_factor(html_text):
    """표의 '단위 : 백만원' 같은 표기를 읽어 **억원 기준 배율**을 돌려준다.

    단위를 잘못 읽으면 숫자가 100배 틀어진다. 유료 리포트에서 가장 위험한 종류의
    오류라, 표기를 못 찾으면 그 사실을 로그에 분명히 남긴다.
    """
    m = re.search(r"단위\s*[:：]\s*([^<,)\n]{1,12})", html_text)
    표기 = m.group(1).strip() if m else ""
    if "백만" in 표기:
        return 0.01, 표기            # 백만원 → 억원
    if "천원" in 표기:
        return 0.00001, 표기
    if "억" in 표기:
        return 1.0, 표기
    return 1.0, (표기 or "표기 없음(억원으로 가정)")


def _extract_program(t, html_text="", 날짜키=None):
    """프로그램매매 표에서 차익·비차익·전체 순매수를 뽑는다.

    실제 확인된 표 구조 (2026-08-05 로그):
      컬럼 = 시간 | 차익거래(매수·매도·순매수) | 비차익거래(…) | 전체(…)
      → 평탄화하면 '차익거래_순매수' 처럼 된다.
    '순매수' 칸이 비면 매수 − 매도로 직접 계산한다.
    """
    라벨, row = _pick_data_row(t, 날짜키)
    if row is None:
        return {}
    배율, 단위표기 = _unit_factor(html_text)
    t2 = _flatten_cols(t.copy())
    컬럼들 = list(t2.columns)

    def 뽑기(조건):
        순 = 매수 = 매도 = None
        for col in 컬럼들:
            if not 조건(col):
                continue
            v = _num(row.get(col))
            if "순매수" in col:
                순 = v
            elif "매수" in col:
                매수 = v
            elif "매도" in col:
                매도 = v
        if 순 is None and 매수 is not None and 매도 is not None:
            순 = 매수 - 매도
        return None if 순 is None else round(순 * 배율)

    결과 = {}
    차익 = 뽑기(lambda s: "차익" in s and "비차익" not in s)
    비차익 = 뽑기(lambda s: "비차익" in s)
    전체 = 뽑기(lambda s: "전체" in s)
    if 차익 is not None:
        결과["차익거래_순매수"] = 차익
    if 비차익 is not None:
        결과["비차익거래_순매수"] = 비차익
    if 전체 is not None:
        결과["전체_순매수"] = 전체
    if 결과:
        결과["기준"] = 라벨
        결과["단위"] = f"억원 (원문 단위: {단위표기})"
    return 결과


# ── 🧭 군중 나침반 (v-l3 신규) ────────────────────────────────
#  무엇: 레버리지 ETF(상승 베팅)와 인버스 ETF(하락 베팅)에 개인이
#        각각 얼마를 넣었는지 비교해 "군중이 어느 쪽을 보고 있나"를 잰다.
#
#  ⚠️ 왜 개인만 보나: 레버리지·인버스는 사실상 개인의 방향성 베팅 상품이다.
#     외국인·기관은 헤지·차익 목적이 섞여 방향 해석이 흐려진다.
#
#  ⚠️ 정직 고지: 이 수집은 네이버 페이지 구조에 의존한다.
#     실패해도 파이프라인을 멈추지 않고 None을 돌려주며, 화면에서는
#     나침반 코너 자체가 생략된다(없는 걸 지어내지 않는다).
CROWD_ETF = [
    ("122630", "KODEX 레버리지",            "레버리지"),
    ("233740", "KODEX 코스닥150레버리지",    "레버리지"),
    ("252670", "KODEX 200선물인버스2X",      "인버스"),
    ("251340", "KODEX 코스닥150선물인버스",  "인버스"),
]


def _crowd_one_mobile(code):
    """① 네이버 모바일 API — 개인 순매수가 직접 들어 있어 가장 정확하다."""
    r = requests.get(f"https://m.stock.naver.com/api/stock/{code}/trend",
                     headers={**HEADERS, "Referer": "https://m.stock.naver.com/"},
                     params={"pageSize": "5"}, timeout=10)
    r.raise_for_status()
    js = r.json()
    rows = js if isinstance(js, list) else (js.get("trends") or js.get("result") or [])
    if not rows:
        return None
    d = rows[0]
    개인 = None
    for k in ("individualPureBuyQuant", "individual", "individualQuant", "개인"):
        if isinstance(d.get(k), (int, float)):
            개인 = float(d[k]); break
    종가 = None
    for k in ("closePrice", "close", "종가"):
        v = d.get(k)
        if v is not None:
            try:
                종가 = float(str(v).replace(",", "")); break
            except Exception:
                pass
    if 개인 is None or not 종가:
        return None
    return 개인 * 종가 / 1e8          # 억원


def _crowd_one_html(code):
    """② HTML 표 폴백 — 개인이 없으므로 −(기관+외국인)으로 추정한다.

    ⚠️ 추정치다. 기타법인 몫이 빠져 있어 정확한 개인 순매수와는 다를 수 있다.
       그래서 화면에도 '추정'임을 표시한다.
    """
    r = requests.get("https://finance.naver.com/item/frgn.naver",
                     headers=HEADERS, params={"code": code}, timeout=10)
    r.encoding = "euc-kr"
    for t in read_html_safe(r.text):
        cols = [str(c) for c in _flatten_cols(t.copy()).columns]
        if not any("기관" in c for c in cols) or not any("외국인" in c for c in cols):
            continue
        t = _flatten_cols(t.copy()).dropna(how="all")
        기관열 = next((c for c in t.columns if "기관" in str(c)), None)
        외인열 = next((c for c in t.columns if "외국인" in str(c) and "보유" not in str(c)), None)
        종가열 = next((c for c in t.columns if "종가" in str(c)), None)
        if not (기관열 and 외인열 and 종가열):
            continue
        for _, row in t.iterrows():
            기 , 외, 종 = to_num(row[기관열]), to_num(row[외인열]), to_num(row[종가열])
            if 기 is None or 외 is None or not 종:
                continue
            return -(기 + 외) * 종 / 1e8      # 억원 (개인 추정)
    return None


def collect_crowd_compass():
    """레버리지 vs 인버스 개인 순매수를 모아 '군중 나침반' 원료를 만든다."""
    print("🧭 군중 나침반 — 레버리지·인버스 개인 순매수 수집")
    합 = {"레버리지": 0.0, "인버스": 0.0}
    상세, 추정여부, 성공 = [], False, 0
    for code, 이름, 방향 in CROWD_ETF:
        금액 = None
        try:
            금액 = _crowd_one_mobile(code)
        except Exception as e:
            print(f"   · {이름}: 모바일API 실패({type(e).__name__}) → HTML 시도")
        if 금액 is None:
            try:
                금액 = _crowd_one_html(code)
                if 금액 is not None:
                    추정여부 = True
            except Exception as e:
                print(f"   · {이름}: HTML도 실패({type(e).__name__})")
        if 금액 is None:
            print(f"   ⚠️ {이름} 수집 실패 — 건너뜁니다")
            continue
        성공 += 1
        합[방향] += 금액
        상세.append({"종목": 이름, "방향": 방향, "개인순매수": round(금액, 1)})
        print(f"   · {이름}({방향}) 개인 {금액:+,.0f}억")

    if 성공 == 0:
        print("   ❌ 전부 실패 — 군중 나침반은 이번 리포트에서 생략됩니다")
        return None

    L, I = 합["레버리지"], 합["인버스"]
    분모 = abs(L) + abs(I)
    기울기 = round((L - I) / 분모 * 100, 1) if 분모 else 0.0   # +100 상승베팅 / −100 하락베팅
    return {
        "레버리지_개인": round(L, 1),
        "인버스_개인": round(I, 1),
        "기울기": 기울기,
        "표본": 성공,
        "추정": 추정여부,      # True면 개인=−(기관+외국인) 추정치
        "상세": 상세,
    }


# ── 매집 레이더 추적 (v-l4 신규) ─────────────────────────────
#  왜: 강세 레이더는 "그 뒤 어떻게 됐나"를 추적하는데 매집 레이더는 안 했다.
#      그래서 포착 항로에 '수급편'을 만들 재료가 아예 없었다.
#      강세와 똑같은 구조로 오늘부터 쌓는다. (시간이 만드는 데이터 — 오늘 안 심으면 영영 없다)
#  ⚠️ 과거분은 복원 불가. 의미 있는 곡선은 약 1개월 뒤부터.
ACC_TRACK_DAYS = 20


def _load_prev_acc_tracking():
    """어제 리포트의 매집 추적표를 읽어온다(없으면 빈 목록)."""
    파일들 = sorted(alist(r"data_\d{8}\.json"))
    for f in reversed(파일들):
        if f.endswith(f"{DATE}.json"):
            continue
        try:
            with open(apath(f), encoding="utf-8") as fp:
                d = json.load(fp)
            tr = ((d.get("매집레이더") or {}).get("추적")) or []
            if tr:
                return [dict(t) for t in tr]
        except Exception:
            continue
        break
    return []


def track_accumulation(매집결과, 가격맵):
    """매집 레이더가 잡은 종목의 이후 경로를 추적한다(강세 추적과 동일 규칙)."""
    추적 = _load_prev_acc_tracking()
    맵 = {t.get("종목명"): t for t in 추적}

    for t in 추적:
        t["경과"] = t.get("경과", 0) + 1
        현재 = 가격맵.get(t.get("종목명"))
        if 현재 and t.get("포착가"):
            t["현재가"] = 현재["현재가"]
            t["이후등락"] = round((현재["현재가"] - t["포착가"]) / t["포착가"] * 100, 2)

    오늘목록 = []
    for 키 in ("종목", "중기종목"):
        for s in (매집결과.get(키) or []):
            오늘목록.append(s)
    새로 = 0
    for s in 오늘목록:
        nm = s.get("종목명")
        if not nm or nm in 맵:
            continue
        현재 = 가격맵.get(nm)
        가 = (현재 or {}).get("현재가")
        if not 가:
            continue
        새 = {"종목명": nm, "시장": s.get("시장") or "코스피", "코드": s.get("코드"),
             "포착일": DATE, "포착가": 가, "현재가": 가,
             "이후등락": 0.0, "경과": 0, "유형": s.get("유형")}
        추적.append(새); 맵[nm] = 새; 새로 += 1

    남김 = [t for t in 추적 if t.get("경과", 0) <= ACC_TRACK_DAYS]
    남김.sort(key=lambda x: x.get("이후등락", 0), reverse=True)
    print(f"📋 매집 추적 {len(남김)}종목 (오늘 신규 {새로})")
    return 남김


def collect_program_trading():
    """프로그램매매(차익/비차익) 수집 — 확인된 주소를 직접 친다.

    2026-08-05 탐색으로 확정된 사실:
      · 실제 표는 sise_program.naver 가 아니라 그 안의 iframe에 있다
        → https://finance.naver.com/sise/programDealTrendDay.naver?bizdate=YYYYMMDD&sosok=
      · sosok 이 비어 있으면 코스피, sosok=02 면 코스닥
      · 표 첫 줄은 빈 줄이고, 둘째 줄부터 최신 거래일 순
      · 컬럼: 시간 | 차익거래(매수/매도/순매수) | 비차익거래(…) | 전체(…)
    """
    BASE = "https://finance.naver.com/sise/programDealTrendDay.naver"
    날짜키 = f"{DATE[2:4]}.{DATE[4:6]}.{DATE[6:8]}"      # 20260805 → 26.08.05
    시장들 = {"코스피": "", "코스닥": "02"}
    수집 = {}

    for 시장, sosok in 시장들.items():
        url = f"{BASE}?bizdate={DATE}&sosok={sosok}"
        try:
            code, 본문, enc = naver_get(url, referer="https://finance.naver.com/sise/sise_program.naver")
        except Exception as ex:
            print(f"  ⚠️ {시장} 프로그램매매 요청 실패: {type(ex).__name__}")
            continue
        if code != 200:
            print(f"  ⚠️ {시장} 프로그램매매 → HTTP {code}")
            continue
        찾음 = None
        for t in read_html_safe(본문):
            평 = " ".join(str(x) for x in t.columns)
            if "차익" in 평:
                찾음 = t
                break
        if 찾음 is None:
            print(f"  ⚠️ {시장} — '차익' 컬럼을 가진 표를 못 찾음 ({enc})")
            continue
        값 = _extract_program(찾음, 본문, 날짜키)
        if not 값:
            print(f"  ⚠️ {시장} — 표는 찾았으나 숫자 추출 실패. 컬럼: {list(_flatten_cols(찾음.copy()).columns)[:6]}")
            continue
        if 날짜키 not in str(값.get("기준", "")):
            print(f"  ⚠️ {시장} — 오늘({날짜키}) 행이 없어 최신행({값.get('기준')})을 씀. 장 마감 전 실행일 수 있음")
        수집[시장] = 값
        print(f"✅ {시장} 프로그램매매 [{값.get('기준')}] "
              f"차익 {값.get('차익거래_순매수')}억 · 비차익 {값.get('비차익거래_순매수')}억 "
              f"· 전체 {값.get('전체_순매수')}억 | {값.get('단위')}")

    if not 수집:
        print("⚠️ 프로그램매매 미확보 — 해당 코너는 리포트에서 숨겨집니다.")
        return None

    # 코스피를 기본값으로 펼치고(기존 렌더링 호환), 코스닥은 하위에 담는다
    기본 = dict(수집.get("코스피") or list(수집.values())[0])
    기본["시장"] = "코스피" if "코스피" in 수집 else list(수집.keys())[0]
    if "코스닥" in 수집:
        기본["코스닥"] = 수집["코스닥"]
    return 기본


def collect_program_and_futures():
    """프로그램매매 + 선물 수급.

    ⚠️ 옵션 수급은 뺐다. 네이버에서 투자자별 옵션 수급을 안정적으로 얻을 경로를
       확인하지 못했고, 리포트에 '확인 불가'만 고정으로 나가는 게 손해라고 판단했다.

    왜 프로그램매매가 중요한가:
      · 차익거래 = 선물-현물 가격차를 노린 기계적 매매 (방향성 아님)
      · 비차익거래 = 선물과 무관한 바스켓 매매 (실제 방향성 베팅)
      → 같은 '프로그램 매도 1조'라도 어느 쪽이냐에 따라 해석이 정반대다.
    """
    결과 = {"프로그램매매": None, "선물수급": None, "옵션수급": None}
    결과["프로그램매매"] = collect_program_trading()

    # ── 선물 투자자별 수급 ──
    for sosok in ("03", "04"):
        if 결과["선물수급"]:
            break
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
            결과["선물수급"] = {"개인": str(row["개인"]), "외국인": str(row["외국인"]),
                            "기관계": str(row["기관계"]), "sosok": sosok}
            print(f"✅ 선물수급 수집 (sosok={sosok})")
        except Exception as e:
            print(f"  ⚠️ 선물수급 sosok={sosok} 실패: {type(e).__name__}")

    미확보 = [k for k in ("프로그램매매", "선물수급") if not 결과[k]]
    if 미확보:
        print(f"⚠️ 미확보: {', '.join(미확보)} — 해당 부분은 리포트에서 숨겨집니다.")
    return 결과


def _fetch_prev_volume(code):
    """전일 거래량(주식 수)을 구한다.
    네이버 일별시세 표에 거래량이 그대로 있어 근사 없이 실측값을 쓸 수 있다.
    (거래대금은 이 표에 없어서 예전엔 '거래량×종가'로 추정해야 했다.)
    반환: 주식 수 float 또는 None
    """
    url = "https://finance.naver.com/item/sise_day.naver"
    try:
        r = requests.get(url, headers=HEADERS, params={"code": code, "page": "1"}, timeout=10)
        r.encoding = "euc-kr"
        tables = read_html_safe(r.text)
    except Exception:
        return None

    for t in tables:
        cols = " ".join(str(c) for c in t.columns)
        if "거래량" in cols and "날짜" in cols:
            df = t.dropna(subset=["날짜"])
            if len(df) < 2:
                return None
            # 0번째 = 최근일(오늘), 1번째 = 그 전날
            return to_num(df.iloc[1].get("거래량"))
    return None


TRACK_DAYS = 20         # 포착 후 추적 기간(거래일). 이 기간 안에 다시 조건을 만족하면 재점화(N차)

# ── 강세 레이더 설정 (여기 숫자만 바꾸면 리포트 설명도 자동으로 따라간다) ──
STR_MIN_시총 = 5000       # 억원
STR_MIN_거래대금 = 500    # 억원
STR_배수_하한 = 2.0       # 전일 대비 거래량 (하드 필터)
STR_배수_가점 = 3.0       # 이 이상이면 가점
STR_가점 = 15
STR_W_회전, STR_W_상승 = 0.5, 0.5

# ── 5일 매집 레이더 설정 ──
ACC_DAYS = 5            # 단기 관찰 기간(거래일)
ACC_LONG = 20           # 중기 관찰 기간(거래일) — 네이버 frgn 1페이지가 딱 20행이라 추가 요청 없음
ACC_L_BOTH = 12         # 중기 쌍끌이: 20일 중 12일(60%) 이상 — 5일 기준(3/5=60%)과 같은 비율
ACC_L_SOLO = 14         # 중기 단독: 14일(70%) — 5일 기준(4/5=80%)보다 살짝 완화. 20일 연속성은 훨씬 어렵다
ACC_BOTH_DAYS = 3       # 🤝쌍끌이 인정 최소 일수 (둘 다 사는 것 자체가 강한 조건이라 3일)
ACC_SOLO_DAYS = 4       # 💼단독 인정 최소 일수 (조건이 하나뿐이라 더 엄격하게)
ACC_DROP_LINE = -5.0    # 5일 등락률이 이 아래면 '하락 중 매집'(⚠️ 물타기 가능성)
ACC_FLAT_LINE = 5.0     # 이 이하면 '횡보 중 매집'(😴 전형적 매집 패턴)
ACC_POOL = None         # 후보 풀 상한. None = 상한 없음(조건 통과한 종목 전부)
                        #   화면엔 각 랭킹 TOP5만 나오지만, 뽑는 범위가 좁으면
                        #   두 랭킹이 같은 종목만 반복하게 된다(풀 5개면 겹침 100%).
                        #   그래서 상한을 두지 않고 통과 종목 전부를 풀에 담는다.
ACC_UNIVERSE = {"코스피": 100, "코스닥": 40}  # 시총 상위 몇 종목까지 스캔할지


def _fetch_investor_flow(code, days=ACC_LONG):
    """종목별 외국인·기관 일별 순매매를 가져온다.
    네이버 '외국인·기관' 탭 표에는 순매매'량'(주식 수)이 있으므로
    종가를 곱해 금액(억원)으로 환산한다.
    반환: {"외국인": [일별 억원...], "기관": [...], "종가": 최근종가}
    """
    url = "https://finance.naver.com/item/frgn.naver"
    try:
        r = requests.get(url, headers=HEADERS,
                         params={"code": code, "page": "1"}, timeout=10)
        r.encoding = "euc-kr"
        tables = read_html_safe(r.text)
    except Exception:
        return None

    표 = None
    for t in tables:
        cols = " ".join(str(c) for c in t.columns)
        if "외국인" in cols and "기관" in cols and "날짜" in cols:
            표 = t
            break
    if 표 is None:
        return None

    # 2단 헤더면 평탄화
    if isinstance(표.columns, pd.MultiIndex):
        표.columns = ["_".join(str(x) for x in c).strip() for c in 표.columns]

    def 열찾기(*키워드):
        for c in 표.columns:
            s = str(c)
            if all(k in s for k in 키워드):
                return c
        return None

    날짜열 = 열찾기("날짜")
    종가열 = 열찾기("종가")
    기관열 = 열찾기("기관", "순매매")
    외인열 = 열찾기("외국인", "순매매")
    if not (날짜열 and 종가열 and 기관열 and 외인열):
        return None

    df = 표.dropna(subset=[날짜열]).head(days)
    if len(df) < ACC_DAYS:          # 최소 5일은 있어야 단기 판정이 가능
        return None

    외 , 기 = [], []
    종가들 = []
    for _, row in df.iterrows():
        종가 = to_num(row.get(종가열))
        외량 = to_num(row.get(외인열))
        기량 = to_num(row.get(기관열))
        if 종가 is None:
            continue
        종가들.append(종가)
        외.append((외량 or 0) * 종가 / 100_000_000)   # 원 → 억원
        기.append((기량 or 0) * 종가 / 100_000_000)
    if not 외 or len(종가들) < 2:
        return None

    # 5일 등락률 — 이미 받아온 종가로 계산하므로 추가 요청이 없다.
    # (표는 최신일이 0번째, 가장 오래된 날이 마지막)
    최근 = 종가들[0]
    시작5 = 종가들[min(ACC_DAYS, len(종가들)) - 1]
    시작N = 종가들[-1]
    등락5 = (최근 - 시작5) / 시작5 * 100 if 시작5 else None
    등락N = (최근 - 시작N) / 시작N * 100 if 시작N else None

    return {"외국인": 외, "기관": 기,          # 최신일이 0번째, 최대 20일치
            "종가": 최근,
            "5일등락률": round(등락5, 2) if 등락5 is not None else None,
            "장기등락률": round(등락N, 2) if 등락N is not None else None,
            "일수": len(외)}


def collect_accumulation_radar():
    """5일 매집 레이더 — 조용히 쌓이는 돈을 잡아낸다.

    강세 레이더가 '오늘 터진 것(폭발)'을 본다면, 여기는 '아직 안 터졌지만 쌓이는 것(매집)'.
    서로 반대편을 보므로 두 코너가 겹치지 않는다.

    ── 조건 설계 ──
      🤝 쌍끌이 : 외국인·기관이 **둘 다** 5일 중 3일 이상 순매수 + 각자 누적 플러스
                  → 둘이 동시에 사는 건 우연으로 잘 안 나온다. 그 자체가 강한 조건이라
                     일수는 3일로 두어도 신호가 충분하다.
      💼 단독   : 한쪽만 매집. 조건이 하나뿐이므로 **4일 이상**으로 엄격히 건다.
                  쌍끌이가 5종목 미만인 날에만 보충용으로 채운다.
                  (그래야 "오늘은 해당 종목이 없습니다"로 코너가 비는 일이 없다)

    ── 두 랭킹 ──
      금액 순위  : "큰돈이 어디로 갔나"      (대형주가 상위)
      시총대비   : "그 회사엔 얼마나 큰 돈인가" (중소형주가 상위)
      같은 종목 풀인데 순서가 완전히 달라진다 — 그 대비를 나란히 보여준다.
    """
    유니버스 = []
    for 시장, sosok in (("코스피", "0"), ("코스닥", "1")):
        상한 = ACC_UNIVERSE[시장]
        모은수 = 0
        for page in range(1, 4):
            if 모은수 >= 상한:
                break
            try:
                r = requests.get("https://finance.naver.com/sise/sise_market_sum.naver",
                                 headers=HEADERS,
                                 params={"sosok": sosok, "page": str(page)}, timeout=12)
                r.encoding = "euc-kr"
                soup = BeautifulSoup(r.text, "html.parser")
                tables = read_html_safe(r.text)
            except Exception:
                break
            코드맵 = {}
            for a in soup.select("a[href*='code=']"):
                m = re.search(r"code=(\d{6})", a.get("href", ""))
                if m:
                    코드맵[clean_name(a.get_text(strip=True))] = m.group(1)
            표 = None
            for t in tables:
                if "종목명" in " ".join(str(c) for c in t.columns):
                    표 = t
                    break
            if 표 is None:
                break
            for _, row in 표.dropna(subset=["종목명"]).iterrows():
                이름 = clean_name(row.get("종목명", ""))
                시총 = to_num(row.get("시가총액"))
                코드 = 코드맵.get(이름)
                if not 이름 or not 코드 or 시총 is None:
                    continue
                유니버스.append((이름, 코드, 시장, 시총))
                모은수 += 1
                if 모은수 >= 상한:
                    break

    print(f"📥 매집 레이더 스캔 대상 {len(유니버스)}종목 (시총 상위)")

    쌍끌이, 단독 = [], []
    중기목록 = []
    실패 = 0
    for 이름, 코드, 시장, 시총 in 유니버스:
        flow = _fetch_investor_flow(코드)
        if not flow:
            실패 += 1
            continue
        외전체, 기전체 = flow["외국인"], flow["기관"]
        외, 기 = 외전체[:ACC_DAYS], 기전체[:ACC_DAYS]        # 단기 = 최근 5일
        외일수 = sum(1 for v in 외 if v > 0)
        기일수 = sum(1 for v in 기 if v > 0)
        외누적, 기누적 = sum(외), sum(기)

        # ── 중기(20일) 판정 — 같은 응답에서 추가 요청 없이 ──
        if len(외전체) >= ACC_LONG:
            외20, 기20 = 외전체[:ACC_LONG], 기전체[:ACC_LONG]
            외일20 = sum(1 for v in 외20 if v > 0)
            기일20 = sum(1 for v in 기20 if v > 0)
            외누20, 기누20 = sum(외20), sum(기20)
            중기 = None
            if 외일20 >= ACC_L_BOTH and 기일20 >= ACC_L_BOTH and 외누20 > 0 and 기누20 > 0:
                중기 = ("쌍끌이", 외누20 + 기누20)
            elif 외일20 >= ACC_L_SOLO and 외누20 > 0:
                중기 = ("외국인 단독", 외누20)
            elif 기일20 >= ACC_L_SOLO and 기누20 > 0:
                중기 = ("기관 단독", 기누20)
            if 중기:
                중기목록.append({"종목명": 이름, "시장": 시장, "코드": 코드, "시총": 시총,
                              "외인일수": 외일20, "기관일수": 기일20,
                              "외국인": round(외누20, 1), "기관": round(기누20, 1),
                              "유형": 중기[0], "합산": round(중기[1], 1),
                              "시총대비": round(중기[1] / 시총 * 100, 3) if 시총 else None,
                              "장기등락률": flow.get("장기등락률")})

        기본 = {"종목명": 이름, "시장": 시장, "코드": 코드, "시총": 시총,
               "외인일수": 외일수, "기관일수": 기일수,
               "외국인": round(외누적, 1), "기관": round(기누적, 1),
               "5일등락률": flow.get("5일등락률")}

        # 🤝 쌍끌이 — 둘 다 3일 이상 & 각자 누적 플러스
        if (외일수 >= ACC_BOTH_DAYS and 기일수 >= ACC_BOTH_DAYS
                and 외누적 > 0 and 기누적 > 0):
            합산 = 외누적 + 기누적
            쌍끌이.append({**기본, "유형": "쌍끌이", "합산": round(합산, 1),
                         "시총대비": round(합산 / 시총 * 100, 3)})
            continue

        # 💼 단독 — 한쪽만, 4일 이상
        if 외일수 >= ACC_SOLO_DAYS and 외누적 > 0:
            단독.append({**기본, "유형": "외국인 단독", "합산": round(외누적, 1),
                       "시총대비": round(외누적 / 시총 * 100, 3)})
        elif 기일수 >= ACC_SOLO_DAYS and 기누적 > 0:
            단독.append({**기본, "유형": "기관 단독", "합산": round(기누적, 1),
                       "시총대비": round(기누적 / 시총 * 100, 3)})

    if 실패:
        print(f"  ℹ️ {실패}종목은 수급 데이터 미확보(신규상장·데이터 부족 등)")

    쌍끌이.sort(key=lambda x: x["합산"], reverse=True)
    단독.sort(key=lambda x: x["합산"], reverse=True)

    # 조건을 통과한 종목을 전부 풀에 담는다(쌍끌이 먼저, 그다음 단독).
    # ⚠️ 예전엔 여기서 5~10개로 잘라버려서 두 랭킹이 같은 종목만 반복됐다.
    #    두 랭킹 모두 이 전체 풀에서 각자 TOP5를 뽑는다.
    종목 = 쌍끌이 + 단독
    if ACC_POOL:
        종목 = 종목[:ACC_POOL]

    _score_accumulation(종목)

    쌍끌이수 = sum(1 for s in 종목 if s.get("유형") == "쌍끌이")
    print(f"✅ 매집 레이더 — 스캔 {len(유니버스)}종목 → 후보 풀 {len(종목)}종목 "
          f"(🤝쌍끌이 {쌍끌이수} + 💼단독 {len(종목)-쌍끌이수}) → 각 랭킹 TOP5 노출")
    for s in 종목[:3]:
        print(f"   [{s['유형']}] {s['종목명']} {s['합산']:,.0f}억 "
              f"(외{s['외인일수']}일/기{s['기관일수']}일, 시총대비 {s['시총대비']}%)")

    중기목록.sort(key=lambda x: x.get("시총대비") or 0, reverse=True)
    if 중기목록:
        상위 = 중기목록[0]
        print(f"🏗️ 중기(20일) 매집 {len(중기목록)}종목 — 1위 {상위['종목명']} "
              f"{상위['합산']:,.0f}억 (시총대비 {상위['시총대비']}%)")
    return {"종목": 종목, "중기종목": 중기목록, "중기기간": ACC_LONG,
            "중기쌍끌이": ACC_L_BOTH, "중기단독": ACC_L_SOLO,
            "기간": ACC_DAYS,
            "쌍끌이최소": ACC_BOTH_DAYS, "단독최소": ACC_SOLO_DAYS,
            "쌍끌이수": len(쌍끌이)}



def _score_accumulation(종목):
    """매집갭을 계산한다.

    ── 왜 '갭'인가 ──
      왼쪽 랭킹(시총 대비)은 "얼마나 큰 돈이 들어왔나"를 본다.
      오른쪽은 질문이 달라야 겹치지 않는다 → "그 돈이 아직 가격에 반영 안 된 곳".

    ── 계산 ──
      매집점수   = 시총대비 매집비율을 후보군 안에서 0~100으로 정규화
      반응점수   = 5일 등락률을 후보군 안에서 0~100으로 정규화
      매집갭     = 매집점수 − 반응점수     (범위 −100 ~ +100)

    ⚠️ 정규화하는 이유: 시총대비(0.04~1.6%)와 등락률(−10~+20%)은 단위가 달라
       그냥 빼면 숫자가 큰 등락률이 지배한다. 둘 다 0~100으로 맞춰야 공평하다.
    ⚠️ 나눗셈이 아니라 뺄셈인 이유: 등락률이 0에 가까우면 나눗셈은 값이 무한대로 튄다.
    """
    if not 종목:
        return
    유효 = [s for s in 종목 if s.get("5일등락률") is not None]
    if not 유효:
        return

    def 정규화(vals):
        lo, hi = min(vals), max(vals)
        if hi == lo:
            return [50.0] * len(vals)
        return [(v - lo) / (hi - lo) * 100 for v in vals]

    매집점수 = 정규화([s["시총대비"] for s in 유효])
    반응점수 = 정규화([s["5일등락률"] for s in 유효])

    for i, s in enumerate(유효):
        s["매집점수"] = round(매집점수[i])
        s["반응점수"] = round(반응점수[i])
        s["매집갭"] = round(매집점수[i] - 반응점수[i])
        # 성격 구분 — '안 올랐다'에는 횡보와 하락이 섞여 있어 반드시 나눠 표시한다
        등락 = s["5일등락률"]
        if 등락 < ACC_DROP_LINE:
            s["성격"] = "하락 중"
            s["성격아이콘"] = "⚠️"
        elif 등락 <= ACC_FLAT_LINE:
            s["성격"] = "횡보"
            s["성격아이콘"] = "😴"
        else:
            s["성격"] = "상승 중"
            s["성격아이콘"] = "🌱"


def collect_strength_radar():
    """실제 강세 레이더 — 2단 구조.

    ── 1단: 오늘 새로 포착 ──
      1차 필터 : 시총 ≥ 5,000억 AND 거래대금 ≥ 500억 AND 상승 종목만
      2차 필터 : 전일 대비 거래량 2배 이상  (평소와 다른 날만)
                 ※ 거래대금은 주가 상승분이 섞여 부풀려진다. 순수 손바뀜은 거래량이 정확.
      점수     : 회전율점수 × 0.5 + 상승률점수 × 0.5  (각각 0~100 정규화)
                 + 거래량 3배 이상이면 +15점
      ⚠️ 정규화 이유: 회전율(1~15%)과 상승률(0~30%)은 단위가 달라 그냥 더하면
         숫자가 큰 상승률이 늘 이긴다. 0~100으로 환산해야 비중이 뜻대로 작동한다.

    ── 2단: 포착 이후 추적 ──
      한 번 포착된 종목은 신규 목록에서 빠지고 추적표로 이동한다.
      "며칠째 같은 조건 충족"은 새 정보가 아니지만,
      "포착 후 실제로 올랐는가"는 지표가 맞는지 검증해주는 정보이기 때문.
      추적 중 다시 조건을 만족하면 '재점화'로 보고 신규에 다시 올리며 차수를 올린다.
    """
    MIN_시총 = STR_MIN_시총
    MIN_거래대금 = STR_MIN_거래대금
    배수_하한 = STR_배수_하한
    배수_가점 = STR_배수_가점
    가점 = STR_가점
    W_회전, W_상승 = STR_W_회전, STR_W_상승

    신규 = {"코스피": [], "코스닥": []}
    가격맵 = {}          # 종목명 → {"현재가": float, "등락률": float}  (추적 갱신용)
    시장맵 = {"코스피": "0", "코스닥": "1"}

    for 시장, sosok in 시장맵.items():
        종목들 = []
        for page in range(1, 6):
            url = "https://finance.naver.com/sise/sise_market_sum.naver"
            try:
                r = requests.get(url, headers=HEADERS,
                                 params={"sosok": sosok, "page": str(page)}, timeout=12)
                r.encoding = "euc-kr"
                soup = BeautifulSoup(r.text, "html.parser")
                tables = read_html_safe(r.text)
            except Exception as e:
                print(f"  ⚠️ {시장} p{page} 요청 실패: {type(e).__name__}")
                break

            코드맵 = {}
            for a in soup.select("a[href*='code=']"):
                m = re.search(r"code=(\d{6})", a.get("href", ""))
                if m:
                    코드맵[clean_name(a.get_text(strip=True))] = m.group(1)

            표 = None
            for t in tables:
                cols = " ".join(str(c) for c in t.columns)
                if "종목명" in cols and ("거래대금" in cols or "거래량" in cols):
                    표 = t
                    break
            if 표 is None:
                if page == 1:
                    print(f"  ℹ️ {시장} 시총 표 못 찾음. 표 컬럼들:")
                    for i, t in enumerate(tables[:5]):
                        print(f"     표{i} {t.shape}: {list(t.columns)[:9]}")
                break

            표 = 표.dropna(subset=["종목명"])
            for _, row in 표.iterrows():
                이름 = clean_name(row.get("종목명", ""))
                시총 = to_num(row.get("시가총액"))
                등락률 = to_num(row.get("등락률"))
                거래량 = to_num(row.get("거래량"))
                현재가num = to_num(row.get("현재가"))
                대금 = to_num(row.get("거래대금"))
                if 대금 is None and 거래량 is not None and 현재가num is not None:
                    대금 = 거래량 * 현재가num / 100_000_000
                if not 이름:
                    continue
                if 현재가num is not None:
                    가격맵[이름] = {"현재가": 현재가num, "등락률": 등락률}
                if 시총 is None or 대금 is None or 등락률 is None:
                    continue
                종목들.append({
                    "종목명": 이름, "코드": 코드맵.get(이름), "시장": 시장,
                    "시총": 시총, "거래대금": 대금, "거래량": 거래량,
                    "현재가": 현재가num, "등락률": 등락률,
                })

        후보 = [s for s in 종목들
                if s["시총"] >= MIN_시총 and s["거래대금"] >= MIN_거래대금 and s["등락률"] > 0]
        print(f"📡 {시장}: 수집 {len(종목들)} → 1차 필터 통과 {len(후보)}")

        통과 = []
        for s in 후보[:80]:
            if not s.get("코드") or not s.get("거래량"):
                continue
            전일량 = _fetch_prev_volume(s["코드"])
            if not 전일량 or 전일량 <= 0:
                continue
            배수 = s["거래량"] / 전일량
            if 배수 < 배수_하한:
                continue
            s["전일거래량"] = int(전일량)
            s["배수"] = round(배수, 1)
            통과.append(s)
        print(f"   2차 필터(전일 대비 거래량 {배수_하한}배↑) 통과 {len(통과)}")

        if not 통과:
            continue

        def 정규화(vals):
            lo, hi = min(vals), max(vals)
            if hi == lo:
                return [50.0] * len(vals)
            return [(v - lo) / (hi - lo) * 100 for v in vals]

        for s in 통과:
            s["회전율"] = round(s["거래대금"] / s["시총"] * 100, 1)
        회전점수 = 정규화([s["회전율"] for s in 통과])
        상승점수 = 정규화([s["등락률"] for s in 통과])
        for i, s in enumerate(통과):
            점수 = 회전점수[i] * W_회전 + 상승점수[i] * W_상승
            if s["배수"] >= 배수_가점:
                점수 += 가점
                s["폭발"] = True
            s["강세점수"] = round(min(100, 점수), 1)

        통과.sort(key=lambda x: x["강세점수"], reverse=True)
        신규[시장] = 통과[:10]
        if 신규[시장]:
            t = 신규[시장][0]
            print(f"   1위 {t['종목명']} 점수 {t['강세점수']} "
                  f"(회전율 {t['회전율']}%, {t['등락률']:+.2f}%, 거래량 {t['배수']}배)")

    추적 = _update_tracking(신규, 가격맵)
    # 가격맵을 함께 돌려준다 — 매집 추적이 같은 시세를 재사용해야 추가 요청이 0이다.
    return {"신규": 신규, "추적": 추적, "_가격맵": 가격맵}


def _load_prev_tracking():
    """직전 발행분에서 추적 목록을 불러온다."""
    import glob
    files = [apath(f) for f in alist(r"data_\d{8}\.json")]
    files = [f for f in files if DATE not in f]
    if not files:
        return []
    try:
        with open(files[-1], "r", encoding="utf-8") as f:
            prev = json.load(f)
        return (prev.get("강세레이더") or {}).get("추적") or []
    except Exception:
        return []


def _update_tracking(신규, 가격맵):
    """포착 이후 추적표를 갱신한다.

    · 기존 추적 종목: 경과일 +1, 현재가 갱신 → 포착 이후 등락률 계산
    · 오늘 새로 포착: 추적표에 추가 (차수 1)
    · 추적 중 재점화: 차수 +1, 포착일·포착가를 오늘로 리셋 → 신규에도 다시 노출
    · TRACK_DAYS 초과: 졸업 처리(목록에서 제외)
    """
    추적 = _load_prev_tracking()
    맵 = {t["종목명"]: t for t in 추적}

    # 1) 기존 추적 갱신
    for t in 추적:
        t["경과"] = t.get("경과", 0) + 1
        현재 = 가격맵.get(t["종목명"])
        if 현재 and t.get("포착가"):
            t["현재가"] = 현재["현재가"]
            t["이후등락"] = round((현재["현재가"] - t["포착가"]) / t["포착가"] * 100, 2)

    # 2) 오늘 포착 종목 반영
    for 시장, 목록 in 신규.items():
        for s in 목록:
            기존 = 맵.get(s["종목명"])
            if 기존:
                # 재점화 — 차수를 올리고 기준을 오늘로 리셋
                차수 = 기존.get("차수", 1) + 1
                기존.update({"차수": 차수, "경과": 0,
                            "포착일": DATE, "포착가": s["현재가"],
                            "현재가": s["현재가"], "이후등락": 0.0})
                s["재점화"] = 차수
                print(f"   🔄 {s['종목명']} 재점화 → {차수}차 포착")
            else:
                새 = {"종목명": s["종목명"], "시장": 시장, "코드": s.get("코드"),
                     "포착일": DATE, "포착가": s["현재가"], "현재가": s["현재가"],
                     "이후등락": 0.0, "경과": 0, "차수": 1}
                추적.append(새)
                맵[s["종목명"]] = 새

    # 3) 졸업 처리
    남김 = [t for t in 추적 if t.get("경과", 0) <= TRACK_DAYS]
    졸업 = len(추적) - len(남김)
    if 졸업:
        print(f"   🎓 추적 종료 {졸업}종목 (포착 후 {TRACK_DAYS}거래일 경과)")

    # 포착 후 등락률 높은 순 정렬 (실패도 그대로 노출 — 지표 검증이 목적)
    남김.sort(key=lambda x: x.get("이후등락", 0), reverse=True)
    print(f"📋 추적 중 {len(남김)}종목")
    return 남김

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

# 자막 분량. 앞부분만 보면 인사말·시황 나열에 그쳐 '차별적 관점'이 뒤에 묻힌다.
# 조금 넉넉히 가져와 Claude가 특징적인 대목을 찾을 수 있게 한다.
TRANSCRIPT_LIMIT = 7000


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
# 계좌 좌표 격자 (테마 10 + 기타) × (시총 3단계)     [v-k 신규]
# ------------------------------------------------------------
# 왜 만드나:
#   "코스피는 올랐는데 내 종목은 왜 안 올랐나"의 답을 그림 한 장으로 준다.
#   개인은 자기 종목의 시총 순위는 몰라도 '무슨 테마인지'는 안다.
#   그래서 세로=테마, 가로=크기 두 축을 함께 준다.
#
# 시총 구분을 '금액'이 아니라 '순위'로 하는 이유:
#   금액 기준(예: 10조 이상=대형)은 시장이 오르면 대형주 수가 저절로 늘어난다.
#   1년 뒤 오늘과 비교할 때 대형주의 정의 자체가 달라져 시계열 비교가 깨진다.
#   순위 기준이면 각 층의 종목 수가 항상 100/200/나머지로 고정된다.
# ============================================================

GRID_대형_끝 = 100        # 통합 시총 1~100위
GRID_중형_끝 = 300        # 101~300위 / 301위 이하는 소형
# ⚠️ v-l7: 12페이지(시장당 600종목)로는 코스닥 중소형주가 대거 빠졌다.
#    '내 종목'을 입력했는데 "찾을 수 없습니다"가 뜨면 그 회원은 기능을 다시 안 쓴다.
#    40페이지(시장당 2,000종목)면 사실상 전 종목을 덮는다.
#    빈 페이지가 나오면 즉시 멈추므로 실제 요청 수는 상장 종목 수만큼만 늘어난다.
GRID_시총페이지 = 40      # 시장별 크롤 페이지 수(50종목/페이지) → 사실상 전 종목
GRID_최소종목 = 3         # 한 칸에 이보다 적으면 '표본 부족'(—) 처리
GRID_테마상세 = 2         # 슬롯 하나당 상세를 열어볼 네이버 테마 개수
GRID_칸종목수 = 6         # 한 칸에서 화면에 펼쳐 보여줄 상위 종목 수

# 테마 슬롯 9개 — 네이버 테마명에 아래 키워드가 들어가면 그 슬롯으로 본다.
# ⚠️ 이 목록은 한 번 정하면 함부로 바꾸지 않는다. 바꾸면 과거 격자와 비교가 깨진다.
GRID_슬롯 = [
    # ⚠️ 순서가 중요하다 — 위에서부터 먼저 걸리는 슬롯으로 배정된다.
    #    그래서 구체적인 키워드('핵융합')를 넓은 키워드('에너지')보다 위에 둔다.
    #    예: '핵융합에너지'는 원전 줄로 가야지 정유 줄로 가면 안 된다.
    ("반도체",          ["반도체", "hbm", "파운드리", "메모리", "웨이퍼", "소부장",
                        "소캠", "socamm", "d램", "디램", "낸드", "s7", "온디바이스", "cxl"]),
    ("2차전지·소재",     ["2차전지", "이차전지", "전고체", "양극재", "음극재", "리튬", "폐배터리"]),
    ("조선·기계·방산",   ["조선", "방산", "우주", "항공기", "기계", "무기", "스페이스", "위성"]),
    ("전력·신재생·원전", ["원자력", "원전", "핵융합", "전력", "태양광", "풍력", "전선", "변압기",
                        "수소", "신재생", "smr"]),
    ("바이오·제약",      ["제약", "바이오", "의료", "백신", "임플란트", "비만", "치료제", "헬스케어"]),
    ("자동차·부품",      ["자동차", "타이어", "자율주행", "전기차"]),
    ("AI·소프트웨어",    ["인공지능", "ai", "클라우드", "데이터센터", "로봇", "소프트웨어",
                        "보안", "it 대표주", "it대표주", "sw"]),
    ("인터넷·게임·엔터", ["게임", "엔터", "미디어", "콘텐츠", "웹툰", "음원", "영화",
                        "인터넷", "여행", "야놀자", "플랫폼"]),
    ("금융·지주",        ["은행", "증권", "보험", "지주", "금융", "카드", "리츠", "reits",
                        "전자결제", "전자화폐", "종합상사", "환율"]),
    # ⚠️ v-l1 추가 — 기존 9칸이 성장주 쪽에 쏠려 있어 경기·배당 축이 통째로 비어 있었다.
    #    실제로 2026-08-14 주도섹터 1위가 '정유'였는데 격자에서는 '기타'로 들어가
    #    "오늘 시장 1등이 격자에 이름조차 없는" 상태가 됐다.
    ("에너지·정유·화학", ["정유", "석유", "화학", "가스", "에너지", "lng", "lpg", "석탄", "유가",
                        "귀금속", "비철", "철강", "광물", "플라스틱", "요소수", "연료전지"]),
    ("통신·유틸리티",    ["통신", "5g", "이동통신", "전기가스", "유틸리티", "광케이블", "광섬유"]),
    ("소비·유통·식품",   ["유통", "백화점", "편의점", "홈쇼핑", "음식료", "식품", "주류",
                        "화장품", "의류", "섬유", "면세", "카지노", "제습기", "공기청정기",
                        "가전", "마리화나", "대마"]),
    ("건설·부동산",      ["건설", "부동산", "시멘트", "레미콘", "모듈러", "주택", "인테리어"]),
    ("운송·물류",        ["해운", "항공", "lcc", "물류", "택배", "운송"]),
    ("전기전자·부품",    ["led", "디스플레이", "oled", "카메라", "cctv", "dvr", "기판",
                        "전자부품", "mlcc", "음성인식"]),
]
# ⚠️ '테마가 아닌 묶음' — 신규 슬롯 후보에서 뺀다.
#   네이버 테마 목록에는 산업/이슈가 아니라 **상장 시점·주식 종류**로 묶인 것이 섞여 있다.
#   예: "2026 하반기 신규상장"(8/18) → 바이오+패션+마케팅이 한 칸에 담겨
#       평균 +7.8%인데 개별은 +49.9% ~ −7.3%로 57%p 벌어졌다.
#   이런 묶음은 평균 등락률 자체가 거짓이 되므로 애초에 뽑지 않는다.
#   (정유·스마트카·남북경협처럼 진짜 테마는 그대로 통과시킨다)
NOT_A_THEME = ("신규상장", "신규 상장", "스팩", "SPAC", "우선주", "리츠",
               "ETN", "ETF", "인수합병", "상장폐지")

GRID_신규슬롯 = "신규 테마"   # 마지막 칸 — 15개 고정 슬롯 어디에도 안 걸린 테마 중 오늘 최강
#   ⚠️ 예전 이름 "신규 주도"는 "새로 주도하는 종목"으로 오해를 샀다(2026-08-18).
#      실제 뜻은 **아직 주소(슬롯)가 없는 새 테마**다. → "신규 테마"로 개명.
                              # ⚠️ 이모지를 쓰지 않는다 — 일부 환경에서 □로 깨진다


def grid_slot_of(테마명):
    """주도섹터(네이버 테마명) → 계좌 구역(고정 슬롯) 이름.

    ⚠️ 왜 필요한가:
      리포트에는 축척이 다른 두 지도가 있다.
        · 계좌 구역(고정 11~13칸) = 내 종목의 '주소'. 안 바뀌어야 비교가 된다.
        · 뜨는 현장(그날 주도섹터)  = 오늘의 '사건 현장'. 매일 바뀌어야 의미가 있다.
      둘 다 필요하지만 지금까지 연결 고리가 없어서, 독자가
      "레이더의 소캠(SOCAMM)이 격자의 어느 줄인가?"를 스스로 추측해야 했다.
      이 함수가 그 다리를 놓는다. (합치지 않고 잇는다 — 합치면 양쪽 기능이 죽는다)

    반환: 슬롯명 또는 None(어디에도 안 걸리면)
    """
    if not 테마명:
        return None
    t = str(테마명).lower()
    for 슬롯명, 키워드들 in GRID_슬롯:
        if any(k.lower() in t for k in 키워드들):
            return 슬롯명
    return None


def _grid_is_excluded(이름):
    """우선주·스팩·리츠·ETF성 종목은 격자에서 뺀다(평균을 왜곡한다)."""
    if not 이름:
        return True
    if re.search(r"(우|우B|1우|2우B|3우B)$", 이름):
        return True
    for k in ("스팩", "리츠", "홀딩스스팩", "기업인수목적"):
        if k in 이름:
            return True
    return False


def collect_marketcap_universe(pages=GRID_시총페이지):
    """코스피·코스닥 전 종목의 (종목명 → 시총·등락률)을 모아 시총 순위를 매긴다.

    반환: {종목명: {"시총": 억원, "등락률": %, "층": "대형"/"중형"/"소형", "순위": n}}
    """
    종목들 = []
    for 시장, sosok in (("코스피", "0"), ("코스닥", "1")):
        for page in range(1, pages + 1):
            try:
                r = requests.get("https://finance.naver.com/sise/sise_market_sum.naver",
                                 headers=HEADERS, params={"sosok": sosok, "page": str(page)},
                                 timeout=12)
                r.encoding = "euc-kr"
                tables = read_html_safe(r.text)
            except Exception as e:
                print(f"  ⚠️ 시총 {시장} p{page} 실패: {type(e).__name__}")
                break

            표 = None
            for t in tables:
                cols = " ".join(str(c) for c in t.columns)
                if "종목명" in cols and "시가총액" in cols:
                    표 = t
                    break
            if 표 is None:
                break

            표 = 표.dropna(subset=["종목명"])
            빈페이지 = True
            for _, row in 표.iterrows():
                이름 = clean_name(row.get("종목명", ""))
                시총 = to_num(row.get("시가총액"))
                등락 = to_num(row.get("등락률"))
                if not 이름 or 시총 is None or 등락 is None:
                    continue
                if _grid_is_excluded(이름):
                    continue
                빈페이지 = False
                종목들.append({"종목명": 이름, "시장": 시장, "시총": 시총, "등락률": 등락})
            if 빈페이지:
                break

    # 코스피·코스닥 통합 순위 (테마는 시장을 가리지 않으므로 합쳐서 줄 세운다)
    종목들.sort(key=lambda x: x["시총"], reverse=True)
    유니버스 = {}
    for i, s in enumerate(종목들, start=1):
        층 = "대형" if i <= GRID_대형_끝 else ("중형" if i <= GRID_중형_끝 else "소형")
        s["순위"] = i
        s["층"] = 층
        유니버스[s["종목명"]] = s
    print(f"📐 시총 유니버스 {len(유니버스)}종목 "
          f"(대형 {sum(1 for v in 유니버스.values() if v['층']=='대형')} / "
          f"중형 {sum(1 for v in 유니버스.values() if v['층']=='중형')} / "
          f"소형 {sum(1 for v in 유니버스.values() if v['층']=='소형')})")
    return 유니버스


def _grid_theme_members(번호):
    """네이버 테마 상세에서 구성 종목명만 뽑는다."""
    이름들 = []
    try:
        dres = requests.get("https://finance.naver.com/sise/sise_group_detail.naver",
                            headers=HEADERS, params={"type": "theme", "no": 번호}, timeout=12)
        dres.encoding = "euc-kr"
        soup = BeautifulSoup(dres.text, "html.parser")
        for a in soup.select("a[href*='code=']"):
            nm = clean_name(a.get_text(strip=True))
            if nm and not _grid_is_excluded(nm):
                이름들.append(nm)
    except Exception as e:
        print(f"  ⚠️ 테마 상세 {번호} 실패: {type(e).__name__}")
    return list(dict.fromkeys(이름들))


def collect_account_grid(테마후보):
    """테마 10칸(+기타) × 시총 3층 격자를 만든다.

    테마후보: collect_themes_and_gauge()가 모은 [(테마명, 번호, 등락률), ...] 전체 목록
    """
    유니버스 = collect_marketcap_universe()
    if not 유니버스:
        print("⚠️ 시총 유니버스 수집 실패 — 격자 생략")
        return {}

    유효 = [c for c in (테마후보 or []) if c[2] is not None and not math.isnan(c[2])]
    유효.sort(key=lambda x: x[2], reverse=True)

    슬롯멤버 = {}     # 슬롯명 → set(종목명)
    슬롯테마 = {}     # 슬롯명 → [쓰인 네이버 테마명]
    사용된번호 = set()

    for 슬롯명, 키워드들 in GRID_슬롯:
        매칭 = [c for c in 유효 if any(k.lower() in c[0].lower() for k in 키워드들)]
        멤버 = set()
        쓴테마 = []
        for 테마명, 번호, _ in 매칭[:GRID_테마상세]:
            멤버 |= set(_grid_theme_members(번호))
            쓴테마.append(테마명)
            사용된번호.add(번호)
        if 멤버:
            슬롯멤버[슬롯명] = 멤버
            슬롯테마[슬롯명] = 쓴테마

    # 🆕 신규 슬롯 — 위 9칸 어디에도 안 걸린 테마 중 오늘 가장 강한 것 1개
    for 테마명, 번호, _ in 유효:
        # 테마가 아닌 묶음(상장 시점·주식 종류)은 건너뛴다
        if any(k.lower() in str(테마명).lower() for k in NOT_A_THEME):
            print(f"   ⏭️ 신규 슬롯 후보 제외 — '{테마명}' (테마가 아니라 묶음)")
            continue
        if 번호 in 사용된번호:
            continue
        if any(any(k.lower() in 테마명.lower() for k in kws) for _, kws in GRID_슬롯):
            continue
        멤버 = set(_grid_theme_members(번호))
        if len(멤버) >= GRID_최소종목:
            슬롯멤버[GRID_신규슬롯] = 멤버
            슬롯테마[GRID_신규슬롯] = [테마명]
            break

    # ── 격자 계산 ──
    # ── 종목별 소속 구역(최대 2개) 사전 ──
    #   '내 종목' 코너에서 "이 종목이 어느 구역인가"를 즉시 보여주기 위함.
    #   테마 등락률이 높은 순으로 담아 '오늘 이 종목을 움직인 구역'이 먼저 오게 한다.
    종목구역 = {}
    for 슬롯명, 멤버 in 슬롯멤버.items():
        for n in 멤버:
            if n in 유니버스:
                종목구역.setdefault(n, [])
                if 슬롯명 not in 종목구역[n] and len(종목구역[n]) < 2:
                    종목구역[n].append(슬롯명)

    분류됨 = set()
    행들 = []
    for 슬롯명 in [s for s, _ in GRID_슬롯] + [GRID_신규슬롯]:
        멤버 = 슬롯멤버.get(슬롯명)
        if not 멤버:
            continue
        칸 = {}
        전체값 = []
        for 층 in ("대형", "중형", "소형"):
            항목 = [(n, 유니버스[n]["등락률"]) for n in 멤버
                   if n in 유니버스 and 유니버스[n]["층"] == 층]
            값들 = [v for _, v in 항목]
            # 등락률 높은 순 상위 몇 개의 '이름'까지 저장한다.
            #   화면에서 테마를 눌렀을 때 "그래서 어떤 종목이었나"를 바로 보여주기 위함.
            #   (예전엔 등락률·종목수만 저장해 숫자만 있고 실체가 없었다)
            상위 = sorted(항목, key=lambda x: x[1], reverse=True)[:GRID_칸종목수]
            칸[층] = ({"등락률": round(sum(값들) / len(값들), 2), "종목수": len(값들),
                     "종목": [{"명": n, "등": round(v, 2)} for n, v in 상위]}
                     if len(값들) >= GRID_최소종목 else
                     {"등락률": None, "종목수": len(값들),
                      "종목": [{"명": n, "등": round(v, 2)} for n, v in 상위]})
            전체값 += 값들
        if not 전체값:
            continue
        분류됨 |= {n for n in 멤버 if n in 유니버스}
        행들.append({
            "테마": 슬롯명,
            "네이버테마": 슬롯테마.get(슬롯명, []),
            "칸": 칸,
            "전체": round(sum(전체값) / len(전체값), 2),
            "종목수": len(전체값),
        })

    # ── 기타 — 어느 테마에도 안 걸린 종목 (빠지면 "내 종목이 없는데?"가 된다) ──
    나머지 = [v for n, v in 유니버스.items() if n not in 분류됨]
    if len(나머지) >= GRID_최소종목:
        칸 = {}
        for 층 in ("대형", "중형", "소형"):
            값들 = [v["등락률"] for v in 나머지 if v["층"] == 층]
            칸[층] = ({"등락률": round(sum(값들) / len(값들), 2), "종목수": len(값들)}
                     if len(값들) >= GRID_최소종목 else {"등락률": None, "종목수": len(값들)})
        행들.append({
            "테마": "기타",
            "네이버테마": [],
            "칸": 칸,
            "전체": round(sum(v["등락률"] for v in 나머지) / len(나머지), 2),
            "종목수": len(나머지),
        })

    행들.sort(key=lambda r: r["전체"], reverse=True)

    # ── 크기 전체 (스파크라인 원료) ──
    크기전체 = {}
    # ⚠️ 순위(1~100위)만 보여주면 독자가 "내 종목이 몇 위인지" 몰라 쓸모가 없다.
    #    그 경계에 실제로 걸린 종목의 시가총액을 함께 알려줘야 감이 온다.
    #    (예: 100위 종목 시총이 3.2조 → "3.2조 이상"이면 대형)
    def _시총경계(순위):
        후보 = [v.get("시총") for v in 유니버스.values()
               if v.get("순위") == 순위 and isinstance(v.get("시총"), (int, float))]
        if 후보:
            return 후보[0]
        # 그 순위 종목이 빠졌으면 근처 값으로 대체(제외 종목 때문에 구멍이 날 수 있다)
        가까운 = sorted((v for v in 유니버스.values()
                       if isinstance(v.get("시총"), (int, float)) and v.get("순위")),
                      key=lambda v: abs(v["순위"] - 순위))
        return 가까운[0]["시총"] if 가까운 else None

    def _조표기(억):
        """억원 → 사람이 읽는 말. 10,000억 = 1조 (절대 '만억'을 쓰지 않는다)"""
        if not isinstance(억, (int, float)) or 억 <= 0:
            return None
        # ⚠️ 세 칸(대형·중형·소형)의 단위를 반드시 '조'로 통일한다.
        #    하나만 '6,200억'으로 나오면 나란히 놓고 비교할 수 없다.
        # ⚠️ 격자 헤더는 칸이 좁다(모바일 한 칸 ≈ 60px).
        #    '0.62조~3.12조' 처럼 길면 옆 칸 글자와 겹친다 → 소수 1자리로 짧게.
        조 = 억 / 10000
        return f"{조:.0f}" if 조 >= 10 else f"{조:.1f}"

    대형선 = _조표기(_시총경계(GRID_대형_끝))
    중형선 = _조표기(_시총경계(GRID_중형_끝))

    for 층 in ("대형", "중형", "소형"):
        값들 = [v["등락률"] for v in 유니버스.values() if v["층"] == 층]
        크기전체[층] = round(sum(값들) / len(값들), 2) if 값들 else None

    격차 = None
    if 크기전체["대형"] is not None and 크기전체["소형"] is not None:
        격차 = round(크기전체["대형"] - 크기전체["소형"], 2)

    결과 = {
        "행": 행들,
        "크기전체": 크기전체,
        "크기프리미엄": 격차,          # 대형 − 소형. 양수면 대형 쏠림
        "기준": {"대형": f"1~{GRID_대형_끝}위", "중형": f"{GRID_대형_끝+1}~{GRID_중형_끝}위",
                "소형": f"{GRID_중형_끝+1}위 이하", "최소종목": GRID_최소종목,
                # 순위와 함께 '그 순위의 실제 시총'을 담는다 — 독자가 자기 종목을 대입할 수 있게.
                # 조 단위로 통일하고 기호로 줄인다 — 세 칸을 나란히 놓고 읽을 수 있게.
                "대형시총": f"{대형선}조↑" if 대형선 else None,
                "중형시총": f"{중형선}~{대형선}조" if (대형선 and 중형선) else None,
                "소형시총": f"{중형선}조↓" if 중형선 else None},
        "유니버스종목수": len(유니버스),
        # ── 종목 사전 (v-l7 신규) ──
        #  '내 종목' 코너의 재료. 이름 → [구역들, 시총순위, 층, 오늘 등락률].
        #  ⚠️ 매일 저장해야 archive에서 5/20/60일 누적을 계산할 수 있다.
        #     종목별 과거 주가를 따로 안 받아도 되는 이유가 이것이다.
        #     배열로 담아 용량을 줄인다(키 반복 제거).
        "종목사전": {
            n: [종목구역.get(n, []), v.get("순위"), v.get("층"),
                round(v.get("등락률", 0), 2), v.get("시장")]
            for n, v in 유니버스.items()
        },
    }
    print(f"🧭 계좌 좌표 격자 {len(행들)}행 · 크기 프리미엄 {격차}%p")
    update_strata_history(결과)
    return 결과


def update_strata_history(격자):
    """대형·중형·소형 일별 등락과 크기 프리미엄을 영구 누적한다.

    ⚠️ 오늘 저장하지 않으면 오늘 하루는 영영 복구할 수 없다.
       스파크라인 3줄과 크기 프리미엄 추이가 전부 여기서 나온다.
    """
    경로 = "strata_history.json"
    이력 = []
    try:
        if os.path.exists(경로):
            with open(경로, encoding="utf-8") as f:
                이력 = json.load(f) or []
    except Exception:
        이력 = []

    한줄 = {
        "날짜": DATE,
        "대형": 격자.get("크기전체", {}).get("대형"),
        "중형": 격자.get("크기전체", {}).get("중형"),
        "소형": 격자.get("크기전체", {}).get("소형"),
        "크기프리미엄": 격자.get("크기프리미엄"),
    }
    이력 = [r for r in 이력 if r.get("날짜") != DATE]   # 같은 날 재실행이면 덮어씀
    이력.append(한줄)
    이력.sort(key=lambda r: r.get("날짜", ""))

    with open(경로, "w", encoding="utf-8") as f:
        json.dump(이력, f, ensure_ascii=False, indent=2)
    print(f"💾 strata_history.json {len(이력)}일치 누적")


# ============================================================
# 메인
# ============================================================
if __name__ == "__main__":
    print(f"=== {DATE} 데이터 수집 시작 | collect_data {SCRIPT_VERSION} ===\n")

    # ⚠️ 장 마감(15:30) 전에 돌리면 지수·주도섹터·강세레이더가 전부 0%로 잡힌다.
    #    데이터 버그가 아니라 실행 시각 문제라서, 눈에 띄게 경고만 남기고 진행한다.
    _now = datetime.now()
    if _now.hour * 100 + _now.minute < 1540:
        print("=" * 62)
        print("⚠️  경고: 지금은 장 마감(15:30) 전입니다.")
        print("    지수·주도섹터·강세레이더가 0%/0종목으로 수집됩니다.")
        print("    정식 리포트는 15:40 이후에 실행하세요.")
        print("=" * 62 + "\n")

    공시 = collect_dart()
    지수수급 = collect_index_and_flow()
    테마결과 = collect_themes_and_gauge()
    게이지 = compute_gauge(지수수급, 테마결과.get("확산도_시장평균"))
    뉴스원본 = collect_news()
    매크로 = collect_macro()
    파생 = collect_program_and_futures()
    update_flow_history(지수수급, 파생)
    등락수 = collect_updown_counts()
    update_market_history(지수수급, 파생, 게이지, 등락수)
    강세레이더 = collect_strength_radar()
    _가격맵 = 강세레이더.pop("_가격맵", {}) or {}
    매집레이더 = collect_accumulation_radar()
    # 매집 종목도 강세와 똑같이 그 뒤 경로를 추적한다(포착 항로 수급편의 재료).
    try:
        매집레이더["추적"] = track_accumulation(매집레이더, _가격맵)
    except Exception as e:
        print(f"   ⚠️ 매집 추적 실패({type(e).__name__}: {e}) — 이번 회차는 건너뜁니다")
    계좌격자 = collect_account_grid(테마결과.get("테마후보"))
    # 🧭 군중 나침반 — 실패해도 None만 돌아오고 파이프라인은 계속된다.
    try:
        군중나침반 = collect_crowd_compass()
    except Exception as e:
        print(f"   ⚠️ 군중 나침반 수집 중 예외({type(e).__name__}: {e}) — 생략합니다")
        군중나침반 = None
    마감브리핑 = collect_briefings()

    전체 = {
        "날짜": DATE,
        "버전_collect": SCRIPT_VERSION,
        "공시": 공시,
        "지수수급": 지수수급,
        "주도섹터": 테마결과.get("주도섹터", []),
        "관제지수": 게이지,
        "뉴스원본": 뉴스원본,
        "매크로": 매크로,
        "파생": 파생,
        "강세레이더": 강세레이더,
        "매집레이더": 매집레이더,
        "등락종목수": 등락수,
        "계좌격자": 계좌격자,
        "군중나침반": 군중나침반,
        "설정": {
            "강세": {"최소시총": STR_MIN_시총, "최소거래대금": STR_MIN_거래대금,
                   "거래량배수": STR_배수_하한, "가점배수": STR_배수_가점,
                   "가점": STR_가점, "회전비중": STR_W_회전, "상승비중": STR_W_상승,
                   "추적일": TRACK_DAYS},
            "매집": {"기간": ACC_DAYS, "쌍끌이일수": ACC_BOTH_DAYS,
                   "단독일수": ACC_SOLO_DAYS, "스캔범위": ACC_UNIVERSE,
                   "하락선": ACC_DROP_LINE, "횡보선": ACC_FLAT_LINE,
                   "풀크기": ACC_POOL or "제한없음"},
            "주도섹터": {"1차후보": 20, "선정수": 6, "중복제외기준": 2,
                     "가중치": "강도40 + 거래대금35 + 확산도25"},
        },
        "마감브리핑": 마감브리핑,
    }

    경로 = asave(f"data_{DATE}.json")
    with open(경로, "w", encoding="utf-8") as f:
        json.dump(전체, f, ensure_ascii=False, indent=2)
    print(f"\n🎉 완료! → {경로}")
