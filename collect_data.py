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
import math
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
        for item in res["datas"]:
            out[item["stockName"]] = {
                "종가": item["closePrice"],
                "등락방향": item["compareToPreviousPrice"]["text"],
                "등락률": item["fluctuationsRatio"],
            }
        return out

    def 수급(sosok):
        url = "https://finance.naver.com/sise/investorDealTrendDay.naver"
        res = requests.get(url, headers=HEADERS, params={"bizdate": DATE, "sosok": sosok, "page": "1"})
        res.encoding = "euc-kr"
        tables = pd.read_html(res.text.encode())
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
            tables = pd.read_html(res.text.encode())
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
            tables = pd.read_html(dres.text.encode())
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
    주도6 = 분석[:6]

    print("🏆 주도 섹터 6개 (주도력점수 순):")
    for a in 주도6:
        et = a["테마등락"]
        et_s = f"{et:+.2f}%" if et is not None else "—"
        print(f"   {a['테마명']} — 점수 {a['주도력점수']} (등락 {et_s}, 확산도 {a['확산도']:.0f}%)")

    시장확산 = sum(a["확산도"] for a in 분석) / len(분석)
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
# 메인
# ============================================================
if __name__ == "__main__":
    print(f"=== {DATE} 데이터 수집 시작 ===\n")

    공시 = collect_dart()
    지수수급 = collect_index_and_flow()
    테마결과 = collect_themes_and_gauge()
    게이지 = compute_gauge(지수수급, 테마결과.get("확산도_시장평균"))

    전체 = {
        "날짜": DATE,
        "공시": 공시,
        "지수수급": 지수수급,
        "주도섹터": 테마결과.get("주도섹터", []),
        "관제지수": 게이지,
    }

    경로 = f"data_{DATE}.json"
    with open(경로, "w", encoding="utf-8") as f:
        json.dump(전체, f, ensure_ascii=False, indent=2)
    print(f"\n🎉 완료! → {경로}")