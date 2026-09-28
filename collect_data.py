import random
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
import statistics
import time      # ⚠️ 매집 스캔 sleep — 차단 방지
import yfinance as yf
from datetime import datetime

SCRIPT_VERSION = "v2026.09.17-v19"   # ⬅ 버전 표시 (로그·리포트에서 확인용)
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
    """오늘의 공시 목록.

    🆕 2026-08-25(실전 사고) — 이 함수 하나가 **리포트 전체를 끌고 내려갔다.**
       원인 둘:
         ① timeout이 없어 DART가 느리면 무한정 기다렸다
            (실측: 2분 18초 만에 겨우 ConnectTimeout으로 실패)
         ② 이 함수가 __main__ 맨 **첫 줄**에서 호출되는데 try/except가 없어서,
            공시(리포트 20개 코너 중 하나일 뿐) 하나가 막히면 지수·섹터·강세·
            매집·기업분석까지 **나머지 전부가 통째로 실패**했다.
       ⚠️ 원칙: 없어도 되는 코너 때문에 있어야 하는 코너까지 죽으면 안 된다.
       [고침] timeout 추가 + 실패하면 빈 목록으로 **조용히 넘어간다.**
              (다른 DART 함수들이 이미 쓰는 것과 같은 패턴)
    """
    if not DART_KEY:
        print("⚠️ DART_API_KEY 없음 → 공시 수집 건너뜀")
        return []

    url = "https://opendart.fss.or.kr/api/list.json"
    params = {"crtfc_key": DART_KEY, "bgn_de": DATE, "end_de": DATE,
              "page_no": "1", "page_count": "100"}
    try:
        data = requests.get(url, params=params, timeout=15).json()
    except Exception as e:
        print(f"   ⚠️ 공시 수집 실패({type(e).__name__}) — 공시 없이 리포트를 계속 만듭니다")
        return []

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


# ══════════════════════════════════════════════════════════════
# 📅 공시 날짜 파서 — 1단계: **로그에만 찍는다** (2026-08-25 신설)
# ══════════════════════════════════════════════════════════════
#  목표 — 유상증자·권리락·배당·사업보고서처럼 **날짜가 정해진 공시**에서
#         그 날짜를 뽑아 D-day 카운트다운을 만든다.
#
#  ⚠️ 왜 1단계는 화면에 안 띄우나 (HO 승인 2026-08-25)
#     샌드박스에서 DART 실측 호출이 안 된다(네이버·KRX와 같은 차단).
#     실제 응답을 한 번도 못 본 파서를 화면에 바로 켜면,
#     **없는 "D-3"을 지어내는 사고**가 난다. 날짜는 오파싱이 최악이다.
#     인수인계 §3-⑥ "검증 못 한 파서는 배포하지 않는다"에 정확히 걸린다.
#     → 1단계: 뽑아서 **로그에만** 남기고 archive에 조용히 저장한다.
#       HO가 Actions 로그에서 날짜가 맞는지 확인 → 2단계에서 화면 ON.
#
#  ⚠️ 실패해도 아무 일도 일어나지 않는다. 공시 목록은 그대로 나간다.
DART_날짜_ON = True        # 🔴 2026-09-07 — 실측 검증 후 화면 ON (아래 근거)
# 🔴 2026-09-07 — 1단계(로그만) → 2단계(화면 표시)로 전환한다.
#   [검증] archive에 조용히 쌓인 25건을 전수 확인했다. 20건 중 19건이
#     정확했다(유상증자 납입일·상장예정일·권리락일 모두 원문과 일치).
#     «검증 못 한 파서는 배포하지 않는다»(원칙8)의 조건이 이제 충족됐다.
#   [발견한 오류 1건] 애드바이오텍 전환사채가 «납입일 2031-09-03(D+1826)»
#     로 파싱됐다. 전환사채 공시에는 **만기일**(5년 뒤)이 같이 적혀 있는데
#     그걸 납입일로 끌어온 것이다. → 아래 DART_날짜_최대D로 막는다.
DART_날짜_최대D = 400      # 이보다 먼 미래 날짜는 버린다.
#   ⚠️ 왜 400일인가: 유상증자·배당·주총 일정은 아무리 멀어도 1년 안이다.
#      그보다 먼 날짜가 나왔다면 만기일·소멸시효 같은 **다른 날짜를
#      잘못 집은 것**이다. 틀린 D-day를 보여주느니 안 보여주는 게 낫다.
DART_날짜_최대 = 8         # 하루에 원문을 열어볼 공시 수(요청 수 제한)

# 뽑을 항목 — 라벨: 원문에서 찾을 키워드들
DART_날짜_항목 = [
    ("신주배정기준일", ["신주배정기준일", "신주배정 기준일"]),
    ("권리락일", ["권리락", "권리락일"]),
    ("배당기준일", ["배당기준일", "배당금지급 기준일", "결산기준일"]),
    ("납입일", ["납입일", "주금납입일"]),
    ("상장예정일", ["상장예정일", "신주의 상장 예정일", "신주상장예정일"]),
    ("주주총회일", ["주주총회", "주주총회일"]),
]
# 이 유형의 공시만 원문을 연다(전부 열면 요청이 폭증한다)
DART_날짜_대상 = ["유상증자", "무상증자", "배당", "주주총회", "사업보고서",
                "분기보고서", "반기보고서", "자기주식", "전환사채"]


def _dart_dates_from_text(본문):
    """원문 텍스트에서 항목별 날짜를 찾는다.

    ⚠️ 날짜 표기가 제각각이다: 2026년 09월 10일 / 2026-09-10 / 2026.09.10
       세 가지를 모두 받되, **키워드 뒤 120자 안**에 있는 것만 채택한다.
       멀리 떨어진 날짜를 끌어오면 엉뚱한 날이 붙는다.
    """
    날짜패턴 = (r"(20\d{2})\s*[년.\-/]\s*(\d{1,2})\s*[월.\-/]\s*(\d{1,2})")
    모든키워드 = [k for _, ks in DART_날짜_항목 for k in ks]
    out = {}
    for 라벨, 키워드들 in DART_날짜_항목:
        for kw in 키워드들:
            i = 본문.find(kw)
            if i < 0:
                continue
            # ⚠️ 범위를 좁게 잡는다(50자). 넓히면 표의 다른 칸 날짜를 끌어온다.
            창 = 본문[i + len(kw):i + len(kw) + 50]
            # ⚠️ 그리고 **다음 항목 키워드가 나오면 거기서 자른다.**
            #    "신주배정기준일 (아래 참조) … 주주총회 2026년 3월 1일" 같은 경우
            #    자르지 않으면 주주총회 날짜가 신주배정기준일로 붙는다.
            컷 = len(창)
            for k2 in 모든키워드:
                if k2 == kw or k2 in kw or kw in k2:
                    continue
                j = 창.find(k2)
                if 0 <= j < 컷:
                    컷 = j
            m = re.search(날짜패턴, 창[:컷])
            if not m:
                continue
            y, mo, d = m.groups()
            if not (1 <= int(mo) <= 12 and 1 <= int(d) <= 31):
                continue
            out[라벨] = f"{int(y):04d}{int(mo):02d}{int(d):02d}"
            break
    return out


def collect_disclosure_dates(공시목록):
    """★ 공시 원문을 열어 날짜를 뽑는다. 1단계는 로그 + 저장만.

    반환: [{회사명, 공시명, 링크, 날짜들:{라벨:YYYYMMDD}, D데이:{라벨:일수}}]
    """
    if not DART_KEY or not 공시목록:
        return []
    대상 = [g for g in 공시목록
           if any(k in (g.get("공시명") or "") for k in DART_날짜_대상)][:DART_날짜_최대]
    if not 대상:
        print("   📅 공시 날짜 파서 — 대상 공시 없음")
        return []
    결과 = []
    for g in 대상:
        rcp = ""
        m = re.search(r"rcpNo=(\d+)", g.get("링크") or "")
        if m:
            rcp = m.group(1)
        if not rcp:
            continue
        try:
            r = requests.get("https://opendart.fss.or.kr/api/document.xml",
                             params={"crtfc_key": DART_KEY, "rcept_no": rcp},
                             timeout=15)
            if r.status_code != 200 or len(r.content) < 200:
                print(f"   ⚠️ 원문 실패 {g.get('회사명')} — HTTP {r.status_code}")
                continue
            본문 = _dart_unzip_text(r.content)
        except Exception as e:
            print(f"   ⚠️ 원문 예외 {g.get('회사명')} — {type(e).__name__}")
            continue
        if not 본문:
            continue
        날짜들 = _dart_dates_from_text(본문)
        if not 날짜들:
            print(f"   📅 {g.get('회사명')} · {g.get('공시명')} → 날짜 못 찾음")
            continue
        디데이 = {}
        # 🔴 2026-09-07 — 너무 먼 미래 날짜는 **오파싱**으로 보고 버린다.
        #    실측: 애드바이오텍 전환사채가 만기일(2031년)을 «납입일»로
        #    끌어와 D+1826이 나왔다. 유상증자·배당·주총 일정은 아무리
        #    멀어도 1년 안이라, 400일을 넘으면 다른 날짜를 잘못 집은 것이다.
        #    ⚠️ 틀린 D-day는 «없는 것»보다 나쁘다. 조용히 지운다(원칙14).
        _버림 = []
        for 라벨, ymd in list(날짜들.items()):
            try:
                d0 = datetime.strptime(DATE, "%Y%m%d")
                d1 = datetime.strptime(ymd, "%Y%m%d")
                _dd = (d1 - d0).days
                if _dd > DART_날짜_최대D:
                    _버림.append(f"{라벨}({ymd}, D+{_dd})")
                    날짜들.pop(라벨, None)
                    continue
                디데이[라벨] = _dd
            except Exception:
                pass
        if _버림:
            print(f"   ⚠️ {g.get('회사명')} — 너무 먼 날짜 제외: {', '.join(_버림)}")
        if not 날짜들:
            continue
        결과.append({"회사명": g.get("회사명"), "공시명": g.get("공시명"),
                     "링크": g.get("링크"), "날짜들": 날짜들, "D데이": 디데이})
        표기 = " · ".join(f"{k} {v[:4]}-{v[4:6]}-{v[6:]}"
                        f"(D{디데이.get(k):+d})" if k in 디데이 else f"{k} {v}"
                        for k, v in 날짜들.items())
        print(f"   📅 {g.get('회사명')} · {g.get('공시명')}")
        print(f"      → {표기}")
    print(f"   📅 공시 날짜 파서 — {len(결과)}/{len(대상)}건에서 날짜 추출 "
          f"(화면 표시: {'ON' if DART_날짜_ON else 'OFF — 로그 확인용 1단계'})")
    return 결과


def _dart_unzip_text(content):
    """DART document.xml은 **ZIP으로 내려온다.** 풀어서 텍스트만 뽑는다.

    ⚠️ 이 사실을 모르고 r.text를 그대로 쓰면 깨진 바이너리를 뒤지게 된다.
       ZIP이 아니면 그냥 디코드해 본다(형식이 바뀔 수도 있으니 방어).
    """
    try:
        import zipfile
        zf = zipfile.ZipFile(io.BytesIO(content))
        조각 = []
        for nm in zf.namelist():
            try:
                raw = zf.read(nm)
            except Exception:
                continue
            # 🔴 2026-08-27 사고 수정 — 인코딩 선택이 **항상 euc-kr로 고정**됐다.
            #    errors="ignore"를 주면 어떤 인코딩도 예외를 안 내므로 첫 번째
            #    후보(euc-kr)에서 무조건 break 했다. DART 사업보고서는 UTF-8이라
            #    본문이 통째로 깨졌다(실측: 「사업의 내용」 위치 -1, 단서 {} 8종목 전부).
            #    → 예외가 아니라 **한글이 얼마나 나왔는지**로 고른다.
            _best, _score = "", -1
            for enc in ("utf-8", "euc-kr", "cp949"):
                try:
                    _t = raw.decode(enc, errors="ignore")
                except Exception:
                    continue
                # 한글 음절 비율이 가장 높은 해독을 채택한다.
                _h = sum(1 for _c in _t[:20000] if "가" <= _c <= "힣")
                if _h > _score:
                    _best, _score = _t, _h
            if _best:
                조각.append(_best)
        본문 = " ".join(조각)
    except Exception:
        try:
            본문 = content.decode("euc-kr", errors="ignore")
        except Exception:
            return ""
    본문 = re.sub(r"<[^>]+>", " ", 본문)
    return re.sub(r"\s+", " ", 본문)


# ============================================================
# ② 지수 + 수급
# ============================================================
# 🆕 2026-09-17 — 장 상태를 «네이버에게 직접 물어본다».
#
#   [왜 만드나] 지금까지 휴장 여부를 «거래대금이 작다» 같은 정황으로
#     «추론»했다. 정황은 수집이 깨지면 같이 깨진다 — 실제로 9/17에
#     수급 경로가 폐지되자 멀쩡한 거래일이 휴장으로 판정됐다.
#   [해법] HO가 F12로 찾아낸 공식 API가 «isTradingDay»를 그대로 준다.
#     추론할 필요가 없어진다.
#
#   GET https://stock.naver.com/api/stockSecurity/exchanges/market-status
#       ?exchanges=krx
#   응답: {"exchanges":[{"exchange":"krx","statuses":[
#           {"marketType":"KOSPI","stockType":"stock",
#            "today":{"date":"2026-09-17","isTradingDay":true,
#                     "isWeekdayHoliday":false,"holidayDescription":null}, ...}]}]}
#
#   ⚠️ statuses에는 KOSPI·KOSDAQ·KONEX가 있고 stockType도 stock·etf·etn으로
#      갈린다. 우리가 볼 것은 «KOSPI + stock» 하나다.
#   ⚠️ exchanges는 krx만 묻는다. NXT는 거래소가 달라 휴장일이 같다는 보장이
#      없고, 우리 데이터는 전부 KRX 기준이다.
#   ⚠️ 못 구하면 None을 준다 — 그러면 예전처럼 거래대금으로 «추론»한다.
#      이 API가 죽었다고 발행이 멈추면 안 된다(9/17 교훈).
# 🔴🔴 2026-09-28 — 휴장일에 «영구 이력»을 쓰지 않는다.
#   [사고] 9/24(추석 연휴)에도 예약 실행이 돌아, 네이버가 보여주는 «9/23 장»을
#     9/24라는 날짜로 theme_history · market_history · strata_history에 한 줄씩
#     더 적었다. 4일 누적 순위와 모든 테마의 «나이»가 하루씩 밀린다.
#   [막기] ① 쓰기 전에 거래소 공식 장상태(isTradingDay)를 묻는다(하루 한 번, 캐시).
#          주말이면 묻지도 않고 휴장. ② 이미 섞인 휴장일 줄은 시작할 때 걷어낸다.
_휴장캐시 = {}


def _휴장일():
    if "v" in _휴장캐시:
        return _휴장캐시["v"]
    v = False
    try:
        if datetime.strptime(DATE, "%Y%m%d").weekday() >= 5:
            v = True
        else:
            거래일, _정보 = collect_market_status()
            v = (거래일 is False)
    except Exception:
        v = False                      # 모르면 막지 않는다(평소처럼 기록)
    _휴장캐시["v"] = v
    if v:
        print(f"   🛑 {DATE}는 휴장일 — 영구 이력(theme/market/strata)에 쓰지 않습니다")
    return v


def _휴장줄_청소(휴장들):
    """이미 섞인 휴장일 줄을 걷어낸다. 휴장들 = {"YYYYMMDD", ...}"""
    if not 휴장들:
        return
    def _k(x):
        return str(x or "").replace("-", "")[:8]
    try:
        if os.path.exists(THEME_HISTORY_FILE):
            h = _load_json(THEME_HISTORY_FILE, {}) or {}
            일 = h.get("일별") or {}
            빼 = [d for d in 일 if d in 휴장들]
            if 빼:
                for d in 빼:
                    일.pop(d, None)
                h["날짜들"] = sorted(일)
                with io.open(THEME_HISTORY_FILE, "w", encoding="utf-8") as f:
                    json.dump(h, f, ensure_ascii=False, separators=(",", ":"))
                print(f"   🧹 theme_history 휴장일 줄 제거: {빼}")
    except Exception as e:
        print(f"   ⚠️ theme_history 청소 실패 — {type(e).__name__}")
    for 파일, 키 in (("market_history.json", "일별"), ("strata_history.json", None)):
        try:
            if not os.path.exists(파일):
                continue
            d = json.load(open(파일, encoding="utf-8"))
            rows = d.get(키) if (키 and isinstance(d, dict)) else d
            if not isinstance(rows, list):
                continue
            남 = [r for r in rows if _k((r or {}).get("날짜")) not in 휴장들]
            if len(남) != len(rows):
                if 키:
                    d[키] = 남
                else:
                    d = 남
                with open(파일, "w", encoding="utf-8") as f:
                    json.dump(d, f, ensure_ascii=False, indent=1)
                print(f"   🧹 {파일} 휴장일 줄 {len(rows) - len(남)}개 제거")
        except Exception as e:
            print(f"   ⚠️ {파일} 청소 실패 — {type(e).__name__}")


# 2026 휴장일(build_html의 KRX_HOLIDAYS와 같은 표 — 청소 대상 판별용)
_KRX_휴장_2026 = {"20260101", "20260216", "20260217", "20260218", "20260302", "20260501",
                 "20260505", "20260525", "20260603", "20260717", "20260817", "20260924",
                 "20260925", "20261005", "20261009", "20261225", "20261231"}


def collect_market_status():
    """오늘이 거래일인가? (True / False / None=모름)"""
    url = "https://stock.naver.com/api/stockSecurity/exchanges/market-status"
    try:
        res = requests.get(url, headers=HEADERS,
                           params={"exchanges": "krx"}, timeout=10)
        j = res.json()
    except Exception as e:
        print(f"  ⚠️ 장 상태 조회 실패 — {type(e).__name__}: {e} (거래대금으로 추론합니다)")
        return None, {}

    for ex in (j.get("exchanges") or []):
        if str(ex.get("exchange") or "").lower() != "krx":
            continue
        for st in (ex.get("statuses") or []):
            if st.get("marketType") != "KOSPI" or st.get("stockType") != "stock":
                continue
            t = st.get("today") or {}
            거래일 = t.get("isTradingDay")
            if not isinstance(거래일, bool):
                continue
            정보 = {"날짜": t.get("date"), "거래일": 거래일,
                   "평일휴장": t.get("isWeekdayHoliday"),
                   "휴장사유": t.get("holidayDescription"),
                   "세션": ((st.get("latest") or {}).get("session") or {})
                          .get("displayLabel")}
            # ⚠️ API가 말하는 날짜가 우리가 아는 오늘과 다르면 믿지 않는다.
            #    (예약이 밀려 새벽에 돌 때 날짜가 어긋난다 — 2026-08-27 사고)
            _api날짜 = str(정보["날짜"] or "").replace("-", "")
            if _api날짜 and _api날짜 != DATE:
                print(f"  ⚠️ 장 상태 API 날짜({_api날짜})가 오늘({DATE})과 다릅니다 "
                      f"— 판정에 쓰지 않습니다.")
                return None, 정보
            print(f"  📅 장 상태 — {정보['날짜']} 거래일={거래일}"
                  + (f" · {정보['휴장사유']}" if 정보.get("휴장사유") else "")
                  + (f" · {정보['세션']}" if 정보.get("세션") else ""))
            return 거래일, 정보
    print("  ⚠️ 장 상태 응답에서 KOSPI 항목을 못 찾았습니다 (거래대금으로 추론합니다)")
    return None, {}


def collect_index_and_flow():
    def 지수():
        url = "https://polling.finance.naver.com/api/realtime/domestic/index/KOSPI,KOSDAQ"
        # 🆕 2026-08-25 — timeout 추가(빠른 실패). DART 사고와 같은 이유.
        res = requests.get(url, headers=HEADERS, timeout=12).json()
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

    # 🔴🔴 2026-09-17 전면 교체 — 옛 경로가 «폐지»됐다.
    #
    #   [무슨 일] 네이버가 finance.naver.com/sise/investorDealTrendDay.naver 를
    #     없앴다. 화면에 "이 페이지는 더 이상 제공되지 않습니다"가 뜬다.
    #     표 머리글만 남고 데이터 행이 0개라 수급이 계속 None이 됐고,
    #     그 탓에 멀쩡한 거래일(9/17, 거래대금 23조)이 「휴장」으로 판정됐다.
    #
    #   [새 경로] HO가 F12로 잡아준 주소 (2026-09-17).
    #     GET https://stock.naver.com/api/domestic/market/trend/daily
    #         ?tradeType=KRX&marketType=KOSPI&bizdate=YYYYMMDD
    #         &startIdx=0&pageSize=N
    #
    #   ⚠️ tradeType은 «반드시 KRX». 넥스트레이드(NXT)가 생겨 거래가 둘로
    #      갈렸는데, 지금까지 쌓인 수급 이력은 전부 KRX 기준이다.
    #      여기서 NXT를 섞으면 어제까지의 기록과 비교가 통째로 깨진다.
    #   ⚠️ marketType은 KOSPI / KOSDAQ (옛 sosok=01 / 02 를 대신한다).
    #
    #   [응답 생김새]
    #     {"content":[{"bizdate":"20260917","netAmounts":[
    #        {"investorGubun":"8000","diffValue":"-1206134000000", ...}, ...]}, ...]}
    #     · 하루가 «한 덩어리», 그 안에 투자자 주체별 줄이 12개.
    #     · diffValue = 순매수 «원» 단위 (우리 저장 단위는 억원 → ÷1e8).
    #
    #   [투자자 코드 — 추측이 아니라 실측 교차검증]
    #     새 API의 9/16 값을 이미 저장해 둔 archive/data_20260916.json 과 맞춰본 결과
    #       개인   8000                              → -12,061.3억 (저장 -12,061.0)
    #       외국인 9000 + 9001(기타외국인)            → -16,725.8억 (저장 -16,726.0)
    #       기관계 1000·2000·3000·3100·4000·5000·6000 → +12,251.1억 (저장 +12,251.0)
    #     세 항목 모두 일치했고, 전체 순매수 합이 정확히 0이 나왔다
    #     (순매수 총합은 정의상 0이어야 한다 — 이게 매핑이 맞다는 가장 강한 증거다).
    #   ⚠️ 7000·7100은 기타법인 쪽이다. 우리가 안 쓰므로 합에 넣지 않는다.
    #      단, 모르는 코드가 새로 나오면 로그에 남겨 조용히 새지 않게 한다.
    _INV_개인 = {"8000"}
    _INV_외국인 = {"9000", "9001"}
    _INV_기관 = {"1000", "2000", "3000", "3100", "4000", "5000", "6000"}
    _INV_기타 = {"7000", "7100"}

    def 수급(marketType):
        url = "https://stock.naver.com/api/domestic/market/trend/daily"
        try:
            res = requests.get(
                url, headers=HEADERS,
                params={"tradeType": "KRX", "marketType": marketType,
                        "bizdate": DATE, "startIdx": "0", "pageSize": "5"},
                timeout=12)
            j = res.json()
        except Exception as e:
            print(f"  ⚠️ 수급({marketType}) 호출 실패 — {type(e).__name__}: {e}")
            return None

        # ⚠️ 오늘 날짜 덩어리만 고른다. 없으면 «없다»고 한다 —
        #    옛 코드가 첫 줄(직전 거래일)을 오늘로 둔갑시켰던 사고(2026-08-18)
        #    를 되풀이하지 않는다.
        오늘 = next((c for c in (j.get("content") or [])
                    if str(c.get("bizdate") or "") == DATE), None)
        if 오늘 is None:
            있는날 = [str(c.get("bizdate")) for c in (j.get("content") or [])][:3]
            print(f"  ⚠️ 수급({marketType}) — {DATE} 자료가 아직 없습니다 "
                  f"(응답의 날짜: {있는날 or '없음'}). 오늘 수급은 '미확보'로 둡니다.")
            return None

        합 = {"개인": 0.0, "외국인": 0.0, "기관계": 0.0}
        본코드, 모르는코드 = set(), set()
        for row in (오늘.get("netAmounts") or []):
            코드 = str(row.get("investorGubun") or "")
            try:
                v = float(row.get("diffValue"))
            except (TypeError, ValueError):
                continue
            본코드.add(코드)
            if 코드 in _INV_개인:
                합["개인"] += v
            elif 코드 in _INV_외국인:
                합["외국인"] += v
            elif 코드 in _INV_기관:
                합["기관계"] += v
            elif 코드 not in _INV_기타:
                모르는코드.add(코드)
        if not 본코드:
            print(f"  ⚠️ 수급({marketType}) — 투자자별 줄이 비어 있습니다.")
            return None
        if 모르는코드:
            # ⚠️ 네이버가 주체를 새로 쪼개면 «기관계»가 조용히 작아진다.
            #    에러가 안 나는 종류의 고장이라 반드시 눈에 띄게 찍는다.
            print(f"  ⚠️ 수급({marketType}) — 모르는 투자자 코드 {sorted(모르는코드)} "
                  f"(합산에서 빠졌습니다. 코드표를 갱신하세요)")
        # 원 → 억원. 저장 형식은 옛 경로와 똑같이 «문자열»로 맞춘다
        # (build_html·collect_data 여러 곳이 to_num()으로 읽는다).
        return {k: f"{v / 1e8:.1f}" for k, v in 합.items()}

    out = {"지수": 지수(), "코스피_수급": 수급("KOSPI"), "코스닥_수급": 수급("KOSDAQ")}
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
#
# 🔴 2026-09-14 — 네이버가 「네이버페이 증권」으로 개편했다.
#   옛 finance.naver.com/sise/theme.naver 는 서버가 HTML 표를 완성해 보냈지만,
#   새 화면은 빈 껍데기를 받은 뒤 JS가 데이터를 따로 불러와 그린다.
#   그래서 BeautifulSoup으로는 «영원히 0개»가 나온다 — 셀렉터 문제가 아니다.
#   (9/12·9/14 로그: 「1차 후보 0개」. 같은 날 프로그램매매는 정상이었으므로
#    IP 차단이 아니라 구조 변경이 맞다.)
#
#   👉 JS가 부르는 진짜 주소를 쓴다:
#      /api/stockSecurity/rankings/v2/domestic/themes
#        sortType=changeRate  등락률 순
#        size=100             한 번에 100개
#        period=daily         일간
#        cursor=<base64>      다음 페이지(우리는 상위 20만 쓰므로 불필요)
#
#   [이득] 목록에 «상승/보합/하락 종목수»가 이미 들어있다 = 확산도를
#   상세 페이지를 열지 않고 바로 계산할 수 있다. 요청 27회 → 1회.
#
#   ⚠️ 필드 이름을 실물로 확인하지 못했다(개발 환경에서 네이버 접속 차단).
#      그래서 «이름을 추측하지 않고 찾는다» — 후보 이름들을 순서대로 훑고,
#      첫 항목의 키 목록을 로그에 찍는다. 한 번만 돌려보면 확정된다.
THEME_API = "https://stock.naver.com/api/stockSecurity/rankings/v2/domestic/themes"
THEME_API_HEADERS = {
    "User-Agent": HEADERS["User-Agent"],
    "Accept": "application/json, text/plain, */*",
    "Referer": "https://stock.naver.com/domestic/industry-theme/theme",
    "Accept-Language": "ko-KR,ko;q=0.9",
}


# 🆕 2026-09-23 HO 지시 — «오늘 뜬 테마에서 우선주는 빼줘.»
#   [왜] 우선주는 본주와 같은 회사다. S7 테마 목록 1번에 «삼성전자우»가 서면
#     같은 회사를 두 번 세는 셈이고, 거래대금합도 본주 몫이 겹친다.
#   [판별] 이름 끝이 우/우B/1우/2우B/우(전환) «그리고» 종목코드 끝자리가 0이 아니다.
#     (본주 코드는 0으로 끝난다 — 삼성전자 005930, 삼성전자우 005935)
#     이름만 보면 «~우»로 끝나는 보통주를 잘못 거를 수 있어 코드로 한 번 더 확인.
_PREF_RE = re.compile(r"(\d?우[A-Z]?|우\(전환\))$")


def _is_pref(name, code=None):
    nm = str(name or "").strip()
    if not _PREF_RE.search(nm):
        return False
    c = str(code or "").strip()
    return (not c) or (c[-1:] != "0")


def _pick(d, *cands):
    """딕셔너리에서 후보 키를 순서대로 찾는다. 대소문자·언더스코어 무시."""
    if not isinstance(d, dict):
        return None
    norm = {str(k).lower().replace("_", ""): v for k, v in d.items()}
    for c in cands:
        v = norm.get(c.lower().replace("_", ""))
        if v is not None:
            return v
    return None


def _dig_list(obj, depth=0):
    """응답 어디에 배열이 들어있든 찾아낸다 (result/items/data/list 등 감싸기 대응)."""
    if depth > 4:
        return None
    if isinstance(obj, list):
        return obj if obj and isinstance(obj[0], dict) else None
    if isinstance(obj, dict):
        for k in ("items", "list", "data", "result", "content", "ranks", "themes"):
            if k in obj:
                got = _dig_list(obj[k], depth + 1)
                if got:
                    return got
        for v in obj.values():
            got = _dig_list(v, depth + 1)
            if got:
                return got
    return None


# ── 테마 «안의 종목» 주소 자동 탐색 ────────────────────────────
#   [왜 이렇게 하나] 개편된 화면에서 종목 목록 API 주소를 사람이 개발자도구로
#   찾아 넘기는 건 품이 많이 든다. 주소 패턴은 목록 API에서 이미 드러났으므로
#   후보를 코드가 직접 두드려보고, 되는 것 하나를 기억해 계속 쓴다.
#   하루에 한 번, 첫 테마에서만 탐색한다(그 뒤 20번은 찾은 주소를 재사용).
#   ⚠️ 옛 HTML 상세는 «아직 살아 있을 수 있다» — 후보 맨 끝에 남겨둔다.
THEME_DETAIL_CANDIDATES = [
    # 🔴🔴 2026-09-22 — HO F12로 확보한 «진짜» 주소(테마 상세 화면의 종목 목록).
    #   테마 번호만 바꾸면 모든 테마에 쓰인다. pageSize=100 → 테마 종목 «전부».
    #   [전] 이 주소를 몰라 테마마다 목록에 딸려 오는 4종목만 봤다 —
    #     확산도·대장주가 4종목 안에서만 계산됐다.
    "https://stock.naver.com/api/domestic/market/theme/{code}/stocklist"
    "?marketType=ALL&orderType=priceTop&startIdx=0&pageSize=100",
    "https://stock.naver.com/api/stockSecurity/rankings/v2/domestic/themes/{code}/stocks",
    "https://stock.naver.com/api/stockSecurity/rankings/v2/domestic/themes/{code}/items",
    "https://stock.naver.com/api/stockSecurity/rankings/v2/domestic/themes/{code}",
    "https://stock.naver.com/api/stockSecurity/rankings/v2/domestic/theme/{code}/stocks",
    "https://stock.naver.com/api/stockSecurity/themes/{code}/stocks",
    "https://m.stock.naver.com/api/theme/{code}/stocks",
]
_DETAIL_WINNER = {"url": None, "tried": False}


# ── 🔴 2026-09-15 — 진짜 정답. 「종목 API」는 따로 없다.
#   HO가 개발자도구로 잡아준 흐름을 보면 종목코드 목록 요청이 REST API가
#   아니라 Next.js의 내부 프리페치(_rsc=...)였다 — 즉 이 사이트는
#   서버가 페이지를 «미리 완성해서» 보내는 SSR이다. 주소창에 주소만
#   쳐도 표가 바로 보였던 게 그 증거다(JS가 나중에 그린 게 아니다).
#   그래서 API를 더 찾을 필요가 없다 — 페이지를 그냥 받아서 그 안에
#   박힌 데이터를 읽으면 된다. 옛 finance.naver.com 상세 페이지를
#   읽던 것과 같은 기술을, 새 주소에 다시 쓰는 것뿐이다.
#
#   경로의 숫자(.../theme/20?no=566)는 실측상 «정렬에서 몇 번째인지»로
#   보인다(no=566 테마가 화면에서 20번째였을 때 주소가 .../theme/20).
#   우리 후보20도 등락률 내림차순이라 같은 순번을 쓸 수 있다.
#   ⚠️ 이 숫자가 틀려도 no=만 맞으면 될 가능성이 높지만 실측 전이라
#   단정하지 않는다 — 안 맞으면 로그에 남기고 다음 방법으로 넘어간다.
THEME_PAGE_HEADERS = {
    "User-Agent": HEADERS["User-Agent"],
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "ko-KR,ko;q=0.9",
}


def _theme_stocks_via_page(code, rank_hint=1):
    """테마 상세 페이지를 그대로 받아 안에 박힌 데이터를 읽는다.
    반환: (종목리스트 또는 None, 진단문구)"""
    url = f"https://stock.naver.com/market/stock/kr/theme/{rank_hint}"
    try:
        r = requests.get(url, headers=THEME_PAGE_HEADERS, params={"no": code}, timeout=12)
        if r.status_code != 200:
            return None, f"HTTP {r.status_code}"
    except Exception as e:
        return None, f"{type(e).__name__}"

    # 1차: __NEXT_DATA__ — Next.js가 서버에서 계산해둔 값을 그대로 담은 JSON.
    #   있으면 이게 제일 깨끗하다(표 파싱보다 구조가 안정적).
    m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', r.text, re.S)
    if m:
        try:
            rows = _dig_list(json.loads(m.group(1)))
            if rows and _pick(rows[0], "stockName", "itemName", "name", "hname") is not None:
                return _norm_stocks(rows), f"ok · __NEXT_DATA__ {len(rows)}건"
        except Exception:
            pass

    # 2차: 그래도 안 되면 서버가 그린 <table>을 그냥 읽는다(옛 방식과 동일 기술).
    try:
        tables = read_html_safe(r.text)
        for t in tables:
            cols = [str(c) for c in t.columns]
            if t.shape[0] < 2 or not any("종목" in c for c in cols):
                continue
            name_c = next((c for c in t.columns if "종목" in str(c)), None)
            price_c = next((c for c in t.columns if "현재가" in str(c)), None)
            chg_c = next((c for c in t.columns if "전일대비" in str(c) or "등락" in str(c)), None)
            amt_c = next((c for c in t.columns if "거래대금" in str(c)), None)
            out = []
            for _, row in t.iterrows():
                nm = clean_name(str(row[name_c]))
                if not nm or nm == "nan":
                    continue
                # 🔴 2026-09-15 — 「전일대비」 칸이 "+260(+1.43%)"처럼 금액과
                #   퍼센트가 한 칸에 같이 들어있는 경우가 실측에서 확인됐다
                #   (금액만 있고 %가 없는 옛 표와 다르다). to_num을 그냥
                #   쓰면 괄호 안 퍼센트를 못 읽고 None이 된다 — 괄호 안
                #   퍼센트를 먼저 찾고, 없으면 to_num으로 그대로 처리한다.
                _rawchg = str(row[chg_c]) if chg_c is not None else ""
                _pm = re.search(r"\(([+\-−]?[0-9.]+)%\)", _rawchg)
                등락률 = (to_num(_pm.group(1)) if _pm else to_num(_rawchg))
                out.append({"종목명": nm,
                            "현재가": to_num(row[price_c]) if price_c is not None else None,
                            "등락률": 등락률,
                            "거래대금": to_num(row[amt_c]) if amt_c is not None else None})
            if out:
                return out, f"ok · <table> {len(out)}건"
    except Exception as e:
        return None, f"table 파싱 실패 {type(e).__name__}"
    return None, "__NEXT_DATA__·table 둘 다 없음"


def _theme_stocks_via_api(code):
    """테마 구성종목을 새 API로 받는다. 실패하면 None(→ 옛 HTML 상세로 폴백)."""
    params = {"sortType": "changeRate", "size": 100, "period": "daily"}

    def _try(tpl):
        try:
            # ⚠️ 주소에 이미 질의(?…)가 박힌 후보는 옛 params를 덧붙이지 않는다.
            r = requests.get(tpl.format(code=code), headers=THEME_API_HEADERS,
                             params=(None if "?" in tpl else params), timeout=10)
            if r.status_code != 200:
                return None, f"HTTP {r.status_code}"
            rows = _dig_list(r.json())
            if not rows:
                return None, "배열 없음"
            if _pick(rows[0], "stockName", "itemName", "itemname", "name", "hname") is None:
                return None, f"종목명 없음 (키: {sorted(rows[0])[:8]})"
            return rows, "ok"
        except Exception as e:
            return None, f"{type(e).__name__}"

    if _DETAIL_WINNER["url"]:
        rows, _ = _try(_DETAIL_WINNER["url"])
        if rows:
            return _norm_stocks(rows)
        _DETAIL_WINNER["url"] = None          # 죽었으면 다시 탐색

    if _DETAIL_WINNER["tried"] and not _DETAIL_WINNER["url"]:
        return None                            # 오늘은 이미 다 두드려봤다

    # 🔴 2026-09-22 — 테마 «번호»를 같이 찍는다. 새 stocklist 주소가 이 번호를
    #   그대로 쓰기 때문에(theme/608/stocklist), 형식이 다르면 404가 난다.
    print(f"  🔎 [테마 종목 API] 주소 자동 탐색 시작... (이 테마 번호: {code!r})")
    for tpl in THEME_DETAIL_CANDIDATES:
        rows, why = _try(tpl)
        짧은 = tpl.replace("https://", "").split("?")[0]
        if rows:
            _DETAIL_WINNER["url"] = tpl
            _DETAIL_WINNER["tried"] = True
            print(f"     ✅ 찾음 → {짧은}")
            print(f"        첫 종목 키: {sorted(rows[0])}")
            return _norm_stocks(rows)
        print(f"     ✗ {짧은} — {why}")
    _DETAIL_WINNER["tried"] = True
    print("     ❌ 후보를 다 두드렸지만 못 찾음 → 옛 HTML 상세로 폴백합니다.")
    return None


def _norm_stocks(rows):
    """API 종목 배열 → [{종목명, 현재가, 등락률, 거래대금}] 로 정규화."""
    out = []
    for it in rows:
        nm = _pick(it, "stockName", "itemName", "itemname", "name", "hname")
        if not nm:
            continue
        # 🔴 2026-09-22 — 새 stocklist는 거래대금을 «원»으로 줄 수 있다(시총 API가 그랬다).
        #   화면·주도점수는 «백만원» 기준이라, 원이면 백만원으로 맞춘다.
        # 🔴🔴 2026-09-23 — 단위가 «종목마다» 섞였다(9/22·9/23 두 번 발행).
        #   [전] «1e10(=100억 원) 이상이면 원으로 보고 ÷100만» — 크기로 단위를 추측했다.
        #     그래서 거래대금 100억 이상 종목만 백만원으로 바뀌고, 그 아래 종목은
        #     «원» 그대로 남았다. 한 테마 안에서 두 단위가 더해졌다.
        #     실측: 와이즈플래닛 1,068,419(백만원·변환됨) + 케이앤에스 7,855,875,000(원·그대로)
        #   [피해] ① 테마 거래대금 변화 «+650,128%» ② 주도력점수의 35%(거래대금 순위)가
        #     «작은 종목이 많은 테마»를 위로 끌어올림 → 순위표 자체가 비틀림.
        #   [고침] 새 stocklist의 tradeAmount는 «항상 원»이다(시총 API와 같은 개편 · 9/15 실측).
        #     크기로 추측하지 않고 «어떤 키에서 왔나»로 단위를 정한다.
        _amt_key, _amt = None, None
        for _k in ("accumulatedTradingValue", "tradingValue", "tradeAmount",
                   "accTradeValue", "amount"):
            _v = _pick(it, _k)                   # _pick = 대소문자 무시(기존 규칙 그대로)
            if _v not in (None, ""):
                _amt_key, _amt = _k, to_num(_v)
                break
        if _amt is not None:
            if _amt_key == "tradeAmount":
                _amt = _amt / 1e6                  # 원 → 백만원 (크기와 상관없이)
            elif _amt >= 1e10:
                _amt = _amt / 1e6                  # 출처 미확인 키 — 예전 추측 유지
        out.append({
            "종목명": clean_name(str(nm)),
            # 🔴 2026-09-21 — 9/15(새 테마 API 전환)부터 현재가가 전부 None이었다.
            #   같은 개편의 시총 API가 «nowPrice»를 쓰는 것을 실측했으므로 앞에 둔다.
            "현재가": to_num(_pick(it, "nowPrice", "closePrice", "currentPrice",
                                "tradePrice", "price", "nv")),
            "등락률": to_num(_pick(it, "fluctuationsRatio", "changeRate", "prevChangeRate",
                                "rate", "cr")),
            "거래대금": _amt,
            "코드": (str(_pick(it, "itemcode", "itemCode", "stockCode", "code"))
                   if _pick(it, "itemcode", "itemCode", "stockCode", "code") else None),
        })
    if out and all(x["현재가"] is None for x in out) and rows:
        print(f"  ⚠️ [테마 종목] 현재가 키 못 찾음 — 첫 항목 키: {sorted(rows[0])[:25]}")
    return out or None


def _theme_list_via_api():
    """새 API로 테마 목록을 받는다. 실패하면 None(→ 옛 HTML 방식으로 폴백)."""
    try:
        res = requests.get(THEME_API, headers=THEME_API_HEADERS, timeout=15,
                           params={"sortType": "changeRate", "size": 100,
                                   "period": "daily"})
        if res.status_code != 200:
            print(f"  ❌ [테마 API] HTTP {res.status_code} · 본문 {len(res.text)}자")
            return None
        js = res.json()
    except Exception as e:
        print(f"  ❌ [테마 API] 요청 실패: {type(e).__name__} {e}")
        return None

    rows = _dig_list(js)
    if not rows:
        print(f"  ❌ [테마 API] 배열을 못 찾음 · 최상위 키: "
              f"{list(js)[:12] if isinstance(js, dict) else type(js).__name__}")
        return None

    # 🔍 첫 항목의 키를 통째로 찍는다 — 한 번만 돌면 스키마가 확정된다.
    print(f"  🔍 [테마 API] {len(rows)}개 수신 · 첫 항목 키: {sorted(rows[0])}")
    # 🔴 2026-09-15 — 「topByChangeRate」가 진짜 종목 객체라면(대장주 후보가
    #   목록 한 번에 딸려온다는 뜻), 종목상세 없이도 대장주 카드를 채울 수
    #   있다. 형태를 아직 실물로 못 봤으므로 원본 그대로 한 번 찍는다 —
    #   다음 실행 로그에서 dict인지 bool인지 바로 갈린다.
    print(f"  🔍 [테마 API] topByChangeRate 샘플: {rows[0].get('topByChangeRate')!r}")
    print(f"  🔍 [테마 API] topByTradingValue 샘플: {rows[0].get('topByTradingValue')!r}")

    out = []
    for it in rows:
        이름 = _pick(it, "themeName", "name", "groupName", "title", "itemName")
        번호 = _pick(it, "themeCode", "code", "groupCode", "no", "themeNo", "id")
        등락 = _pick(it, "changeRate", "fluctuationsRatio", "rate", "changeRatio")
        상승 = _pick(it, "riseCount", "upCount", "increaseCount", "risingCount")
        보합 = _pick(it, "flatCount", "steadyCount", "unchangedCount")
        하락 = _pick(it, "fallCount", "downCount", "decreaseCount", "fallingCount")
        # 🔴 2026-09-15 — 9/15 첫 실행 로그로 실제 필드명 확정.
        #   name / code / changeRate / risingCount / unchangedCount / fallingCount
        #   는 후보 목록 그대로 맞았다. 거래대금만 후보에 없어 못 찾고 있었다
        #   — 실제 키는 totalTradingValue (하나 더 있는 totalTradingVolume은
        #   거래량이지 거래대금이 아니므로 혼동하지 않는다).
        대금 = _pick(it, "totalTradingValue", "accumulatedTradingValue",
                    "tradingValue", "amount", "accTradeValue", "tradeValue")
        if 이름 is None or 번호 is None:
            continue
        # 🔴 2026-09-15 (2차 수정) — 9/15 밤 실측으로 두 가지가 드러났다.
        #   ① topByChangeRate는 dict 하나가 아니라 **배열**이었다
        #      [{'code','name','value','itemLogoUrl'}, ...] — 등락률 상위 3종목.
        #      topByTradingValue도 같은 모양으로 거래대금 상위 3종목을 준다.
        #      즉 종목 1개가 아니라 최대 6개(중복 제거하면 보통 4~5개)를
        #      새 요청 없이 이미 받고 있었다 — 「4종목 나열」에 더 가깝다.
        #   ② 'value' 필드가 배열마다 다른 걸 담는다 — topByChangeRate에서는
        #      «퍼센트»(예: '29.98'), topByTradingValue에서는 «원 단위 거래대금»
        #      (예: '203442345000' = 2,034억원)이다. 우리 fmt_trade()는
        #      «백만원» 단위를 가정하므로, 원 단위를 그대로 넣으면 표시가
        #      100만 배 부풀려진다. /1_000_000으로 맞춘다.
        def _norm_top(raw, is_pct):
            out2 = []
            if not isinstance(raw, list):
                return out2
            for x in raw:
                if not isinstance(x, dict):
                    continue
                nm2 = x.get("name")
                if not nm2:
                    continue
                val = to_num(x.get("value"))
                out2.append({
                    "종목명": clean_name(str(nm2)),
                    "코드": str(x.get("code")) if x.get("code") else None,
                    "등락률": val if is_pct else None,
                    "거래대금": None if is_pct else (val / 1_000_000 if val is not None else None),
                })
            return out2

        _merge = {}
        for r in _norm_top(it.get("topByChangeRate"), True) + _norm_top(it.get("topByTradingValue"), False):
            key = r["코드"] or r["종목명"]
            slot = _merge.setdefault(key, {"종목명": r["종목명"], "현재가": None,
                                          "등락률": None, "거래대금": None})
            if slot["등락률"] is None and r["등락률"] is not None:
                slot["등락률"] = r["등락률"]
            if slot["거래대금"] is None and r["거래대금"] is not None:
                slot["거래대금"] = r["거래대금"]
        대장후보목록 = list(_merge.values())[:4]

        # 🔴 같은 이유로 테마 전체 거래대금(totalTradingValue)도 원 단위로
        #   보인다 — 동일하게 백만원으로 환산한다.
        _대금원 = to_num(대금)
        out.append({
            "테마명": clean_name(str(이름)),
            "번호": str(번호),
            "등락": to_num(등락),
            "상승": to_num(상승), "보합": to_num(보합), "하락": to_num(하락),
            "거래대금": (_대금원 / 1_000_000) if _대금원 is not None else None,
            "대장후보목록": 대장후보목록,
        })
    if not out:
        print(f"  ❌ [테마 API] 이름·번호를 못 뽑음 — 위 «첫 항목 키»를 보고 "
              f"_pick 후보를 고쳐야 한다.")
        return None
    쓸만 = sum(1 for r in out if r["등락"] is not None)
    print(f"  ✅ [테마 API] 정규화 {len(out)}개 (등락률 확보 {쓸만}개) · "
          f"확산도 재료 {'있음' if out[0]['상승'] is not None else '없음 — 상세 필요'}")
    return out



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

    # 🔴 2026-09-14 — ① 새 API를 먼저 시도한다. 성공하면 HTML 루프는 건너뛴다.
    #    실패해도 옛 방식이 그대로 돌아가도록 남겨둔다(원칙 5 — 지우지 않는다).
    API목록 = _theme_list_via_api()
    if API목록:
        for r in API목록:
            if r["등락"] is not None and r["번호"] not in 중복:
                후보.append((r["테마명"], r["번호"], r["등락"]))
                중복.add(r["번호"])
        API맵 = {r["번호"]: r for r in API목록}
        print(f"📊 [테마 API] 후보 {len(후보)}개 확보 — HTML 목록 수집 건너뜀")
    else:
        API맵 = {}
        print("  ↩️ [테마] 옛 HTML 방식으로 폴백합니다.")

    for page in range(1, 8) if not API목록 else []:
        res = requests.get(url_list, headers=HEADERS, params={"page": page}, timeout=12)
        res.encoding = "euc-kr"
        soup = BeautifulSoup(res.text, "html.parser")
        links = soup.select("table.type_1 a[href*='sise_group_detail']")
        # 🔴 2026-09-14 — 셀렉터 폴백 + 진단 로그.
        #  [무슨 일이 있었나] 9/12·9/14 로그에 「1차 후보 0개」만 찍히고
        #   끝났다. res.status_code도, 본문 길이도, 왜 0인지도 남지 않아
        #   «차단인지 개편인지»를 로그만 보고는 가릴 수 없었다.
        #   (같은 날 programDealTrendDay는 정상 수집됐으므로 IP 차단은
        #    아닐 가능성이 높지만, 근거가 로그에 없었다.)
        #  [고친 것] ① table.type_1이 안 걸리면 넓은 셀렉터로 한 번 더 시도.
        #            ② 그래도 0이면 상태코드·본문길이·핵심 문자열 존재 여부를
        #               찍는다. 이 세 줄이면 다음 실패 때 원인이 바로 갈린다.
        if not links:
            links = soup.select("a[href*='sise_group_detail']")
            if links:
                print(f"  ⚠️ [테마목록 p{page}] table.type_1 셀렉터 실패 → "
                      f"넓은 셀렉터로 {len(links)}개 확보 (페이지 구조 변경 의심)")
        if not links:
            있나 = "sise_group_detail" in res.text
            print(f"  ❌ [테마목록 p{page}] 링크 0개 · HTTP {res.status_code} · "
                  f"본문 {len(res.text)}자 · 'sise_group_detail' 문자열 "
                  f"{'있음 → 셀렉터 문제(개편)' if 있나 else '없음 → 차단이거나 페이지 전면 교체'}")
            if page == 1:
                print(f"     본문 앞 200자: {res.text[:200]!r}")
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

    # ── 1차 필터: 등락률 상위 N개 ──
    # 🔴 2026-09-14 — 20 → 50 (HO 지시).
    #   [왜 지금 가능해졌나] 개편 전에는 상세 페이지를 테마 수만큼 열어야 해서
    #   50개면 요청이 50번이었다. 새 API는 목록 한 번에 «상승/보합/하락 수»를
    #   같이 주므로 확산도를 상세 없이 계산할 수 있다 — 목록 요청은 여전히 1회다.
    #   [무엇이 좋아지나] ① 「다가오는 테마」가 11~20위만 보던 걸 50위까지 본다.
    #   ② 테마 채점판의 «20위권 포착» 관문이 비로소 표본을 쌓을 수 있다.
    #   ③ 나이 계산의 체류 구간 표본이 늘어 기준선이 안정된다.
    #   [⚠️ 소급 불가] 고친 날부터 쌓인다. 그 이전 기록은 영원히 10~20개다.
    #   [폴백일 주의] 옛 HTML 방식으로 돌아가면 상세 요청이 50번이 된다.
    #   그래서 API가 아닐 때는 20으로 되돌린다.
    # 🔴 2026-09-19 HO 지시 — 50 → 80.
    #   [왜] 「거꾸로 보기」(순위 밖인데 돈이 붙는 테마)를 만들려면
    #     20위 밖 기록이 있어야 한다. 지금은 후보 자체가 50개라
    #     실제 저장은 30~34개뿐이고, 20위 밖은 사실상 비어 있었다.
    #   [진짜 이른 자리는 순위 밖이다] 돈이 순위보다 먼저 온다 —
    #     실측(9/18): HBM이 거래대금 +58%인데 순위는 3위로 이미 늦었다.
    #     순위에 나타나기 «전»을 보려면 넓게 담아야 한다.
    #   ⚠️⚠️ 소급 불가. 오늘 안 넓히면 한 달 뒤에도 20위 밖을 못 본다.
    #     지나간 날의 거래대금은 되돌려 받을 수 없다.
    #   [비용] 0에 가깝다 — 2차 상세는 이미 계산돼 있고 담기만 한다.
    THEME_CAND_MAX = int(os.getenv("THEME_CAND_MAX", "80")) if API목록 else 20
    유효 = [c for c in 후보 if c[2] is not None and not math.isnan(c[2])]
    # 🔴 HO 지시 2026-09-23 — «하반기 신규상장은 테마에서 빼. 의미없잖아.»
    #   [전] 화면(build_html)에서만 걸렀다(9/07). 그래서 수집 단계에선 살아 있어
    #     주도섹터·주도력점수 정규화·theme_history·AI 해석 입력에 전부 들어갔다.
    #     9/23: 해석글이 «신규상장 테마가 주도섹터 상위권»이라고 썼고,
    #     포착 탭 카드에 «신규상장 · 테마 1위»가 떴다.
    #   [후] 후보 단계에서 뺀다 → 뒤따르는 모든 곳에서 사라진다.
    #   ⚠️ 연도·반기가 바뀌어도 걸리게 «이름에 들어가면» 거른다.
    _비테마 = ("신규상장", "신규 상장")
    _빠짐 = [c[0] for c in 유효 if any(k in str(c[0]) for k in _비테마)]
    if _빠짐:
        print(f"  🚫 테마 아님(상장 시기로 묶인 자루) 제외: {' · '.join(_빠짐)}")
    유효 = [c for c in 유효 if not any(k in str(c[0]) for k in _비테마)]
    유효.sort(key=lambda x: x[2], reverse=True)
    후보20 = 유효[:THEME_CAND_MAX]
    print(f"📊 1차 후보(등락률 상위) {len(후보20)}개 → 상세 분석 중...")

    # ── 2차: 각 후보 상세에서 거래대금·확산도 계산 ──
    # 🔴 2026-09-15 — 9/15 첫 실행 결과: 종목 상세는 새 API 후보 6개
    #   (전부 404) · 옛 HTML(테이블 자체가 사라짐) 둘 다 실패했다. 그런데
    #   테마 «목록» API는 상승/보합/하락 종목수를 이미 준다 — 확산도는
    #   종목 하나하나를 안 열어도 계산된다. 예전 코드는 상세가 실패하면
    #   그 테마를 통째로 건너뛰어서(continue) 목록에 있던 이 재료까지
    #   같이 버렸다. 그 결과 종목 상세가 하나도 안 되던 9/15에는
    #   「테마 상세를 하나도 못 가져옴」으로 주도섹터가 통째로 0개였다.
    #   → 상세(종목 4개·대장주 후보)가 없어도 목록 재료만으로 «종목 없는»
    #   레코드를 만든다. 대장주·종목 펼침은 비지만, 순위·확산도·거래대금은
    #   살아서 테마 레이더·섹터×테마·채점판이 다시 채워진다.
    분석 = []
    _테마행 = {}          # 테마명 → 구성종목 전체(쏠림 계산용 · 2026-09-23)
    for _rank_i, (테마명, 번호, 테마등락) in enumerate(후보20, 1):
        _meta = (API맵.get(번호) or {}) if API목록 else {}
        _appended = False

        # 🔴 2026-09-15 — 1순위: SSR 페이지 직접 읽기(진짜 정답, 위 함수 설명 참고).
        _srows, _swhy = _theme_stocks_via_page(번호, rank_hint=_rank_i)
        if _srows:
            _srows = [x for x in _srows if not _is_pref(x.get("종목명"), x.get("코드"))]
            _테마행[테마명] = _srows
            _유효 = [x for x in _srows if x["등락률"] is not None]
            총 = len(_유효)
            오른 = sum(1 for x in _유효 if x["등락률"] > 0)
            _meta2 = _meta
            if _meta2.get("상승") is not None:
                _합 = (_meta2.get("상승") or 0) + (_meta2.get("보합") or 0) + (_meta2.get("하락") or 0)
                확산도 = (_meta2["상승"] / _합 * 100) if _합 else 0.0
            else:
                확산도 = (오른 / 총 * 100) if 총 else 0.0
            거래대금합 = float(sum(x["거래대금"] or 0 for x in _srows)) or \
                         float(_meta2.get("거래대금") or 0)
            상위 = sorted(_유효, key=lambda x: -x["등락률"])[:4]
            분석.append({
                "테마명": 테마명,
                "계좌구역": grid_slot_of(테마명),
                "테마등락": 테마등락,
                "거래대금합": 거래대금합,
                "확산도": float(확산도),
                "종목": [{"종목명": x["종목명"], "현재가": x["현재가"],
                         "등락률": x["등락률"], "거래대금": x["거래대금"]}
                        for x in 상위],
            })
            _appended = True
            if _rank_i == 1:
                print(f"  ✅ [테마 페이지] {_swhy} — SSR 직접 읽기 성공")
            continue
        elif _rank_i == 1:
            print(f"  ✗ [테마 페이지] {_swhy} — 다음 방법으로 폴백")

        # 🔴 2026-09-14 — 2순위: 예전에 추측했던 REST 후보 6종(대부분 404 확인됨).
        if API목록 and not _appended:
            _rows = _theme_stocks_via_api(번호)
            if _rows:
                _rows = [x for x in _rows if not _is_pref(x.get("종목명"), x.get("코드"))]
                _테마행[테마명] = _rows
                _유효 = [x for x in _rows if x["등락률"] is not None]
                총 = len(_유효)
                오른 = sum(1 for x in _유효 if x["등락률"] > 0)
                # 목록 API가 상승/하락 수를 이미 줬으면 그걸 우선한다(더 정확).
                _meta = API맵.get(번호) or {}
                if _meta.get("상승") is not None:
                    _합 = (_meta.get("상승") or 0) + (_meta.get("보합") or 0) + (_meta.get("하락") or 0)
                    확산도 = (_meta["상승"] / _합 * 100) if _합 else 0.0
                else:
                    확산도 = (오른 / 총 * 100) if 총 else 0.0
                거래대금합 = float(sum(x["거래대금"] or 0 for x in _rows)) or \
                             float(_meta.get("거래대금") or 0)
                상위 = sorted(_유효, key=lambda x: -x["등락률"])[:4]
                분석.append({
                    "테마명": 테마명,
                    "계좌구역": grid_slot_of(테마명),
                    "테마등락": 테마등락,
                    "거래대금합": 거래대금합,
                    "확산도": float(확산도),
                    "종목": [{"종목명": x["종목명"], "현재가": x["현재가"],
                             "등락률": x["등락률"], "거래대금": x["거래대금"]}
                            for x in 상위],
                })
                _appended = True
                continue

        detail_url = "https://finance.naver.com/sise/sise_group_detail.naver"
        # 🆕 2026-08-25 — 이 호출은 테마 수만큼(최대 수십 번) 반복된다.
        #    timeout이 없으면 한 번의 지연이 전체 수집 시간을 몇 분씩 늘릴 수 있다.
        dres = requests.get(detail_url, headers=HEADERS,
                             params={"type": "theme", "no": 번호}, timeout=10)
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
            _appended = True
        except Exception as e:
            print(f"  ⚠️ [{테마명}] 상세 실패: {e}")

        # 🔴 2026-09-15 — 상세(API·HTML) 둘 다 실패했을 때의 마지막 그물.
        #   목록 API가 상승/보합/하락 수를 줬으면 그걸로 확산도를 계산해
        #   «종목 없는» 레코드라도 남긴다. 종목=[]이면 대장주·종목 펼침은
        #   빈 채로 나가지만(화면 쪽에서 그 경우를 다뤄야 한다), 순위·
        #   등락률·확산도·거래대금은 살아서 주도섹터가 0개가 되지 않는다.
        if not _appended and _meta.get("상승") is not None:
            _합 = (_meta.get("상승") or 0) + (_meta.get("보합") or 0) + (_meta.get("하락") or 0)
            확산도 = (_meta["상승"] / _합 * 100) if _합 else 0.0
            # 🔴 2026-09-15 (2차) — topByChangeRate·topByTradingValue를 합쳐
            #   최대 4종목까지 채운다(9/15 밤 실측으로 단일 종목이 아니라
            #   배열임을 확인 — 위 _theme_list_via_api 주석 참고).
            _leaders = _meta.get("대장후보목록") or []
            분석.append({
                "테마명": 테마명,
                "계좌구역": grid_slot_of(테마명),
                "테마등락": 테마등락,
                "거래대금합": float(_meta.get("거래대금") or 0),
                "확산도": float(확산도),
                "종목": _leaders,
                "종목없음": len(_leaders) == 0,
                "종목부분": 0 < len(_leaders) < 4,  # 4개를 다 못 채웠다는 표시
            })
            if _leaders:
                print(f"  ✅ [{테마명}] 목록만으로 종목 {len(_leaders)}개 확보 → "
                      f"{', '.join(x['종목명'] for x in _leaders)} (확산도 {확산도:.0f}%)")
            else:
                print(f"  ↩️ [{테마명}] 종목 상세 없이 목록 재료만으로 채움 "
                      f"(확산도 {확산도:.0f}%)")

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
    폭 = 순위점수([a["확산도"] for a in 분석])

    # 🔴🔴 2026-09-23 HO 지시 — 거래대금을 «크기»가 아니라 «평소 대비 몇 배»로.
    #   [문제] 9/23 실측: S7·CXL·소캠·온디바이스 AI·전력반도체 다섯 테마의
    #     거래대금이 전부 약 11조. 다섯 모두 삼성전자(하루 5.45조)를 품고 있어서다.
    #     35% 몫이 «삼성전자가 들어 있는 테마인가»를 재고 있었다 — 테마의 열기가
    #     아니라 구성종목의 덩치를 잰 것. CXL 19위→6위에도 이 효과가 섞였다.
    #   [고침] 그 테마의 «평소 거래대금»(theme_history 최근 10번 기록의 중앙값)
    #     대비 오늘이 몇 배인가. 덩치가 달라도 «평소보다 뜨거운가»로 줄 세운다.
    #   [순위로 바꾸는 이유] 배수는 한 테마가 30배만 나와도 나머지가 0 근처로
    #     눌린다(최소·최대 정규화의 약점). 그래서 배수의 «백분위»를 점수로 쓴다.
    #   [기록 없는 테마] 평소를 모르면 판단하지 않는다 → 중간값 50점.
    #     (3번 미만 기록 = 평소를 말할 수 없음)
    #   ⚠️ 한계: theme_history는 그날 상위 50개만 저장한다. 그래서 «평소»는
    #      «순위권에 들었던 날들의 평소»라 실제 평소보다 높게 잡힌다 → 배수는
    #      보수적으로(작게) 나온다. 모든 테마가 같은 방향으로 치우치므로 순서는 유지된다.
    #   ⚠️ 5,000만 백만원(50조)을 넘는 값은 9/22 단위 섞임 사고 값이라 버린다.
    try:
        _hist = (_load_json(THEME_HISTORY_FILE, {}) or {}).get("일별") or {}
    except Exception:
        _hist = {}
    _과거 = {}
    for _d in sorted(k for k in _hist if k < DATE):
        for _x in (_hist[_d] or []):
            _v = _x.get("거래대금")
            if _v is not None and 0 < _v <= 5e7:
                _과거.setdefault(_x.get("테마명"), []).append(_v)
    for a in 분석:
        _p = _과거.get(a["테마명"], [])[-10:]
        a["평소거래대금"] = float(statistics.median(_p)) if len(_p) >= 3 else None
        a["거래배수"] = (round(a["거래대금합"] / a["평소거래대금"], 2)
                        if a["평소거래대금"] and a["거래대금합"] else None)
    _배수들 = sorted(a["거래배수"] for a in 분석 if a["거래배수"] is not None)
    def _백분위(v):
        if v is None or len(_배수들) < 2:
            return 50.0
        아래 = sum(1 for b in _배수들 if b < v)
        같음 = sum(1 for b in _배수들 if b == v)
        return (아래 + (같음 - 1) / 2) / (len(_배수들) - 1) * 100
    거래 = [_백분위(a["거래배수"]) for a in 분석]
    print(f"  📐 거래대금 = 평소 대비 배수 · 기준 있음 {len(_배수들)}/{len(분석)}개 테마"
          + (f" · 배수 중앙 {statistics.median(_배수들):.2f}배" if _배수들 else ""))

    # 🆕 2026-09-23 — 한 종목 쏠림. 테마 거래대금의 80% 이상이 한 종목이면
    #   «테마가 뜬 게 아니라 종목 하나가 뜬 것». 9/23 광고 테마: 1.1조 중
    #   1.09조(98%)가 상장 첫날 와이즈플래닛컴퍼니 한 종목이었다.
    #   → 점수 × 0.8 (감점) + 화면 표시용 «쏠림» 값 저장.
    #   ⚠️ 0.8은 판단값이다(실측 근거 아직 없음). 쏠림 테마의 다음 날 생존을
    #      기록해 두었다가 표본이 쌓이면 조정한다.
    for a in 분석:
        _r = _테마행.get(a["테마명"]) or []
        _am = [x.get("거래대금") or 0 for x in _r]
        _tot = sum(_am)
        if _tot > 0 and len(_am) >= 2:
            _i = max(range(len(_am)), key=lambda k: _am[k])
            a["쏠림"] = round(_am[_i] / _tot * 100, 1)
            a["쏠림종목"] = _r[_i].get("종목명")
        else:
            a["쏠림"], a["쏠림종목"] = None, None

    for i, a in enumerate(분석):
        a["주도력점수"] = round(강도[i] * 0.40 + 거래[i] * 0.35 + 폭[i] * 0.25, 1)
        if (a.get("쏠림") or 0) >= THEME_SOLO_PCT:
            a["주도력점수"] = round(a["주도력점수"] * THEME_SOLO_PENALTY, 1)
            print(f"  ⚠️ 쏠림 감점 [{a['테마명']}] {a['쏠림종목']} {a['쏠림']:.0f}% "
                  f"→ 점수 ×{THEME_SOLO_PENALTY}")

    분석.sort(key=lambda x: x["주도력점수"], reverse=True)

    # ── 종목 중복 제거: 이미 뽑힌 카드와 종목이 2개 이상 겹치면 건너뛴다 ──
    # (그렇지 않으면 "에너지 관련 테마 5개, 사실 종목은 같은 애들" 이 됨)
    # 🆕 2026-08-29 (2차) HO 지시 — 저장은 10개, 화면은 6개로 분리한다.
    #    [WHY] 20개 후보는 이미 다 계산돼 있다(강도·거래대금·확산도·점수).
    #    화면 카드는 원칙 13("나열하지 말고 하나만 짚는다")대로 6개를
    #    유지하지만, theme_history.json에는 10개까지 저장한다 — "88개 중
    #    48개가 1회성"이라는 실측 수치 자체가 6개짜리 좁은 창이 만든
    #    경계 노이즈일 수 있다는 판단 때문이다(진짜 순환 테마가 어떤
    #    날은 4위, 어떤 날은 8위로 밀리면 지금 구조는 8위인 날을 통째로
    #    놓친다). 비용은 0 — 이미 계산된 걸 몇 개 더 담는 것뿐이다.
    #    ⚠️ 종목 중복 제거 필터 때문에 10개를 못 채우는 날도 있다 —
    #       억지로 채우지 않는다(원칙 14와 같은 논리).
    # 🔴 2026-09-12 v17 — 저장 10 → 20.
    #    [왜] 11~20위 기록이 없으면 「어제 12위 → 오늘 3위」가
    #    «오늘 첫 등장»으로 오판된다. 실제로는 이미 데워지던 테마인데
    #    단타에게 정반대 신호를 준다. 「다가오는 테마」 코너의 재료이기도 하다.
    #    [비용] 0 — 20개는 이미 2차 상세에서 전부 계산돼 있다. 담기만 한다.
    #    [⚠️ 소급 불가] 고친 날부터 쌓인다. 그 이전 기록은 영원히 10개다.
    #       그래서 이 값은 하루라도 빨리 올리는 게 이득이다.
    # 🔴 2026-09-14 — 20 → 50 (HO 지시). 위 THEME_CAND_MAX와 짝이다.
    # 🔴 2026-09-19 — 50 → 80. 「거꾸로 보기」용. 위 THEME_CAND_MAX와 같은 값.
    #   ⚠️ 둘 중 하나만 올리면 소용없다 — 후보가 좁으면 담을 게 없고,
    #      저장이 좁으면 담아도 안 남는다. 항상 «짝»으로 움직인다.
    THEME_SAVE_MAX = int(os.getenv("THEME_SAVE_MAX", "80"))
    THEME_SHOW_MAX = 6
    주도N = []
    이미쓴종목 = set()
    for a in 분석:
        이번종목 = {s["종목명"] for s in a.get("종목", [])}
        겹침 = len(이번종목 & 이미쓴종목)
        if 겹침 >= 2:
            print(f"  ⏭️  [{a['테마명']}] 건너뜀 — 이미 선택된 섹터와 종목 {겹침}개 중복")
            continue
        주도N.append(a)
        이미쓴종목 |= 이번종목
        if len(주도N) == THEME_SAVE_MAX:
            break
    주도6 = 주도N[:THEME_SHOW_MAX]   # 화면(카드·사다리)은 그대로 6개까지만

    print(f"🏆 주도 섹터 화면 {len(주도6)}개 / 저장 {len(주도N)}개 (주도력점수 순, 중복 제거 적용):")
    for a in 주도6:
        et = a["테마등락"]
        et_s = f"{et:+.2f}%" if et is not None else "—"
        print(f"   {a['테마명']} — 점수 {a['주도력점수']} (등락 {et_s}, 확산도 {a['확산도']:.0f}%)")

    # ── 시장 전반 확산도: 상위 20개가 아니라 '전체 유효 테마' 기준으로 계산 ──
    #    (상위 20개만 보면 항상 90%대로 나와 매일 '과열'처럼 보이는 편향이 생김)
    상승테마 = sum(1 for c in 유효 if c[2] is not None and c[2] > 0)
    시장확산 = (상승테마 / len(유효) * 100) if 유효 else 50.0

    # 🆕 2026-08-29 HO 지시 — 테마 이력 영구 적재.
    #    [WHY] 31거래일 archive를 전수 조사해보니 등장 테마 88개 중 48개(55%)가
    #    딱 한 번만 등장했고, 최다 등장이 9회였다. 즉 지금은 "이 테마 평균
    #    재등장 주기" 같은 통계를 낼 표본이 없다. 그런데 매일 상위 6테마가
    #    나오고도 **파일로 남기지 않아 그대로 휘발**되고 있었다.
    #    → stock_flow_history를 8/24에 심어둔 덕에 지금 브리핑 💰 블록이
    #      사는 것과 같은 논리다. 오늘 심어야 3개월 뒤에 말할 수 있다.
    #    ⚠️ 새 수집 0회 — 이미 계산된 걸 저장만 한다.
    #    🆕 2026-08-29 (2차) — 화면(주도6)이 아니라 **주도N(최대 10개)**을
    #    저장한다. 화면 6개보다 넓게 담아 순환 통계의 경계 노이즈를 줄인다.
    _save_theme_history(주도N)

    return {"주도섹터": 주도6, "확산도_시장평균": round(시장확산, 1),
            "테마후보": 유효}   # 격자(collect_account_grid)가 재활용한다


THEME_HISTORY_FILE = "theme_history.json"
THEME_SOLO_PCT = 80        # 한 종목이 테마 거래대금의 이 % 이상 = 쏠림 (2026-09-23)
THEME_SOLO_PENALTY = 0.8   # 쏠림 테마 점수 배율 — 판단값, 표본 쌓이면 조정


def _save_theme_history(주도N):
    """🆕 2026-08-29 — 날짜별 상위 테마를 영구 누적한다.

    구조: {"날짜들": [...], "일별": {"YYYYMMDD": [{테마명, 등락, 확산도,
                                                  거래대금, 구역, 점수, 종목들}, ...]}}

    ⚠️ **절대 잘라내지 않는다.** market_history.json과 같은 등급의 영구
       파일이다. 이 파일의 값어치는 «시간이 만든 것»이라, 한 번 지우면
       그 몇 달을 다시 살 수 없다(원칙: 축적 데이터 삭제 금지).
    ⚠️ 같은 날 여러 번 실행돼도 그날 값을 덮어쓴다(중복 누적 방지).
    🆕 2026-08-29 (2차) — 파라미터명을 주도6→주도N으로 바꿨다. 화면에
       보여주는 6개보다 넓게(최대 10개) 저장해 순환 통계의 경계 노이즈를
       줄인다(HO 지시, 근거는 collect_themes_and_gauge 주석 참고).
       ⚠️ 종목 중복 제거로 10개를 못 채우는 날엔 그만큼만 들어간다 —
          억지로 채우지 않는다(원칙 14).
    🆕 「점수」(주도력점수) 필드를 추가했다. 저장 범위를 넓히면서 약한
       테마도 섞여 들어올 수 있는데, 점수를 같이 남겨두면 나중에
       "상위 6위 기준"과 "10위까지 기준" 통계를 나눠서 뽑을 수 있다.
    """
    if _휴장일():                      # 🔴 2026-09-28 — 휴장일엔 영구 이력에 안 쓴다
        return
    if not 주도N:
        return
    try:
        이력 = _load_json(THEME_HISTORY_FILE, {}) or {}
    except Exception:
        이력 = {}
    일별 = 이력.setdefault("일별", {})
    일별[DATE] = [{
        "테마명": t.get("테마명"),
        "등락": t.get("테마등락"),
        "확산도": t.get("확산도"),
        "거래대금": t.get("거래대금합"),
        "구역": t.get("계좌구역"),
        "점수": t.get("주도력점수"),
        "거래배수": t.get("거래배수"),        # 평소 대비 배수 (2026-09-23~)
        "쏠림": t.get("쏠림"),                # 한 종목 비중 % (2026-09-23~)
        "쏠림종목": t.get("쏠림종목"),
        # 상위 종목은 이름만 — 가격·등락은 archive에 이미 있어 중복 저장이다
        "종목들": [ (x.get("종목명") if isinstance(x, dict) else x)
                  for x in (t.get("종목") or []) ][:4],
    } for t in 주도N]
    이력["날짜들"] = sorted(일별.keys())
    try:
        with io.open(THEME_HISTORY_FILE, "w", encoding="utf-8") as _f:
            json.dump(이력, _f, ensure_ascii=False, separators=(",", ":"))
        print(f"   🗂️ 테마 이력 적재 — 오늘 {len(주도N)}개 · 누적 {len(이력['날짜들'])}거래일")
    except Exception as e:
        print(f"   ⚠️ 테마 이력 저장 실패 — {type(e).__name__}")


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
        # 🆕 2026-08-24 — 라벨 정정. 이 값은 **테마 단위** 비율이다.
        #    ⚠️ 계산식: 상승한 테마 수 ÷ 전체 유효 테마 수 (compute_sector_lead 참조)
        #    예전 이름이 "등락 종목 비율"/"평균 상승종목"이라 **종목 비율로 오해**됐고,
        #    실제로 코스피 -3.12%인 날 Claude가 "상승종목 비율 66%"라고 써 나갔다.
        #    숫자는 맞았지만 단위가 틀렸다. 이름을 단위 그대로 바꾼다.
        요소.append(("상승 테마 비율", round(점3), 0.25,
                   f"전체 테마 중 오른 테마 {확산도_시장:.0f}%"))

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
        # 🆕 2026-08-24 — "시장 전반"이라는 말을 뺀다. 테마 기준임을 문구에 박는다.
        if 확산도_시장 >= 55:
            배지.append(f"🟢 오른 테마가 더 많음 (테마 {확산도_시장:.0f}%)")
        elif 확산도_시장 <= 45:
            배지.append(f"🔵 내린 테마가 더 많음 (테마 {확산도_시장:.0f}%)")
        else:
            배지.append(f"⚪ 오른 테마·내린 테마 팽팽 (테마 {확산도_시장:.0f}%)")
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
# ── 📰 뉴스 수집원 ───────────────────────────────────────
#  ⚠️ HTML 셀렉터는 실전에서 0건이었다(2026-08-21).
#     한국경제 /finance는 404, 연합뉴스는 403(봇 차단).
#     → **RSS**로 바꿨다. 구조가 고정이라 안 깨지고 차단도 덜하다.
#  ⚠️ 새 매체를 넣기 전 반드시 실제로 열어보고 item 수를 확인할 것.
NEWS_RSS = [
    ("한국경제",   "https://www.hankyung.com/feed/finance"),
    ("한국경제",   "https://www.hankyung.com/feed/economy"),
    ("머니투데이", "https://rss.mt.co.kr/mt_news.xml"),
    ("아시아경제", "https://www.asiae.co.kr/rss/stock.htm"),
]

# 🆕 2026-08-24 HO 요청 — 연합뉴스 복귀 시도.
#  ⚠️ 과거 기록: 2026-08-21에 HTML 방식(yna.co.kr/economy/finance-industry)으로
#     넣었다가 **실전 403(봇 차단)**으로 0건이 나와 RSS 전환 때 빠졌다.
#     이번엔 RSS 주소로 다시 시도한다.
#  ⚠️ 정확한 주소를 확정하지 못했다(샌드박스는 연합뉴스가 403이라 실측 불가.
#     단, 이 샌드박스는 네이버·KRX도 전부 403이라 이 403은 판단 근거가 못 된다).
#     → **후보를 여러 개 두고 먼저 되는 것을 쓴다.** 다 실패하면 조용히 건너뛴다.
#  ⚠️ 다른 매체와 달리 한 곳만 채택한다 — 한국경제가 피드 2개라 물량이 배가 됐던
#     전례가 있어서다(NEWS_매체당상한으로도 막지만, 애초에 안 만드는 게 낫다).
#  📌 첫 실행 후 로그의 `· 연합뉴스: N건`을 확인할 것.
#     0건이면 이 블록을 지우거나 주소를 바꾼다.
NEWS_RSS_후보 = [
    ("연합뉴스", ["https://www.yna.co.kr/rss/economy.xml",
                "https://www.yna.co.kr/rss/market.xml",
                "https://www.yna.co.kr/rss/all.xml"]),
]
NEWS_NAVER = ("네이버금융", "https://finance.naver.com/news/news_list.naver",
              {"mode": "LSS2D", "section_id": "101", "section_id2": "258"})
NEWS_매체당상한 = 20   # 🆕 2026-08-22 — 한국경제가 피드 2개라 물량이 배로 쌓이는 것을
                       #    라운드로빈 전에 미리 잘라 원천 차단한다.


def _clean(t):
    return " ".join(str(t or "").split()).strip()


def _rss_items(xml):
    """RSS <item>에서 (제목, 링크, 요약) 뽑기. 라이브러리 없이 정규식으로."""
    out = []
    for it in re.findall(r"<item[^>]*>(.*?)</item>", xml, re.S):
        def _g(tag):
            m = re.search(rf"<{tag}[^>]*>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</{tag}>", it, re.S)
            return _clean(re.sub(r"<[^>]+>", "", m.group(1))) if m else ""
        t, l = _g("title"), _g("link")
        if t and l and len(t) >= 6:
            out.append((t, l, _g("description")[:300]))
    return out


def collect_credit_balance():
    """💳 신용융자 잔고 + 🏦 고객예탁금 — 네이버 새 API (2026-09-21).

    [사고] 옛 경로 finance.naver.com/sise/sise_deposit.naver 가 폐지돼
      2026-09-14부터 None이었다(수급·선물·프로그램과 같은 뿌리).
    [새 경로 — HO F12 확보]
      GET https://stock.naver.com/api/domestic/market/trendDeposit
          ?startIdx=0&pageSize=20
    ⚠️ 응답 «모양»은 아직 눈으로 확인 못 했다. 그래서 키 이름을 박지 않고
       «이름에 credit / deposit / date가 든 키»를 찾아 쓴다. 매 실행마다
       첫 행의 키 목록을 로그에 찍는다 — 첫 발행 로그로 반드시 확인할 것.
    ⚠️ 신용잔고는 금융투자협회가 «2거래일 늦게» 발표한다. 그래서 기준일을
       같이 돌려준다. 화면은 이 날짜를 반드시 붙여야 한다 — 안 그러면
       「오늘 신용이 늘었다」로 잘못 읽힌다.
    ⚠️ 20일치를 한 번에 주므로 «이력»도 같이 돌려준다. 폐지로 끊겼던
       구간을 소급해서 채울 수 있다.

    반환: {"잔고", "증감", "기준일", "예탁금", "예탁금증감", "이력":[...]} 또는 None
    """
    url = ("https://stock.naver.com/api/domestic/market/trendDeposit"
           "?startIdx=0&pageSize=20")
    try:
        _h = dict(HEADERS)
        _h["Referer"] = "https://stock.naver.com/market/stock/kr/deposit"
        res = requests.get(url, headers=_h, timeout=12)
        js = res.json()
    except Exception as e:
        print(f"  ⚠️ 신용잔고(새 API) 수집 실패: {type(e).__name__}: {e}")
        return None

    # ── 레코드 목록 찾기: 최상위 리스트이거나, 값이 «딕셔너리 리스트»인 첫 키
    rows = None
    if isinstance(js, list):
        rows = js
    elif isinstance(js, dict):
        for _k, _v in js.items():
            if isinstance(_v, list) and _v and isinstance(_v[0], dict):
                rows = _v
                break
        if rows is None:                      # 한 단계 더 안쪽
            for _v in js.values():
                if isinstance(_v, dict):
                    for _v2 in _v.values():
                        if isinstance(_v2, list) and _v2 and isinstance(_v2[0], dict):
                            rows = _v2
                            break
                if rows:
                    break
    if not rows:
        print(f"  ⚠️ 신용잔고 — 응답에서 목록을 못 찾음. 최상위 키: "
              f"{list(js)[:10] if isinstance(js, dict) else type(js).__name__}")
        return None

    keys = list(rows[0].keys())
    print(f"  🔎 신용잔고 API 첫 행 키: {keys}")          # ⚠️ 첫 발행 때 확인용
    print(f"  🔎 첫 행 값: {json.dumps(rows[0], ensure_ascii=False)[:300]}")

    _bad = ("change", "diff", "ratio", "rate", "percent", "increase",
            "compare", "fluct", "updown", "증감", "대비")

    def _pick(*words):
        c = [k for k in keys
             if any(w in k.lower() for w in words)
             and not any(b in k.lower() for b in _bad)]
        return c[0] if c else None

    def _pick_chg(*words):
        c = [k for k in keys
             if any(w in k.lower() for w in words)
             and any(b in k.lower() for b in _bad)]
        return c[0] if c else None

    k_date = _pick("date", "day", "일자", "날짜")
    k_cr = _pick("credit", "신용")
    k_dp = _pick("deposit", "예탁")
    if not (k_date and k_cr):
        print(f"  ⚠️ 신용잔고 — 날짜/신용 키를 못 찾음 (date={k_date}, credit={k_cr})")
        return None

    def _num(v):
        try:
            return float(str(v).replace(",", "").strip())
        except (TypeError, ValueError):
            return None

    def _eok(v):
        """단위를 «억원»으로. 신용잔고·예탁금은 수십~수백 조 = 1e5~5e6 억."""
        if v is None:
            return None
        a = abs(v)
        if a >= 1e11:   return v / 1e8     # 원
        if a >= 1e7:    return v / 100     # 백만원
        return v                            # 이미 억원

    def _ymd(v):
        t = re.sub(r"[^0-9]", "", str(v or ""))
        return t[:8] if len(t) >= 8 else None

    이력 = []
    for r in rows:
        d = _ymd(r.get(k_date))
        c = _eok(_num(r.get(k_cr)))
        p = _eok(_num(r.get(k_dp))) if k_dp else None
        if d and c:
            이력.append({"날짜": d, "잔고": round(c), "예탁금": (round(p) if p else None)})
    이력.sort(key=lambda x: x["날짜"])
    if len(이력) < 2:
        print(f"  ⚠️ 신용잔고 — 유효 행 {len(이력)}개뿐")
        return None

    last, prev = 이력[-1], 이력[-2]
    # ⚠️ 상식 검사 — 신용잔고는 대략 5조~100조(5만~100만 억). 벗어나면 단위 오판.
    if not (50_000 <= last["잔고"] <= 1_000_000):
        print(f"  ⚠️ 신용잔고 {last['잔고']:,}억 — 상식 범위 밖. 단위 확인 필요 "
              f"(키 {k_cr}, 원값 {rows[0].get(k_cr)})")
    out = {"잔고": last["잔고"], "증감": last["잔고"] - prev["잔고"],
           "기준일": last["날짜"], "이력": 이력}
    if last.get("예탁금") and prev.get("예탁금"):
        out["예탁금"] = last["예탁금"]
        out["예탁금증감"] = last["예탁금"] - prev["예탁금"]
    print(f"  ✅ 신용잔고 {out['잔고']:,}억 ({out['증감']:+,}억) · 기준 {out['기준일']}"
          + (f" · 예탁금 {out['예탁금']:,}억" if out.get("예탁금") else "")
          + f" · 이력 {len(이력)}일")
    return out


def collect_news():
    """뉴스 원본 — 여러 매체 RSS + 네이버 금융.

    ⚠️ 제목만 저장하면 본문에만 종목명이 나오는 기사를 못 찾는다.
       ('내 종목 브리핑에 뉴스가 없다'의 진짜 원인) → **요약문까지 저장**한다.
    ⚠️ 한 곳이 죽어도 나머지로 계속 간다. 로그에 매체별 건수를 반드시 찍는다.
    """
    결과, 중복 = [], set()

    for 이름, url in NEWS_RSS:
        n0 = len(결과)
        try:
            res = requests.get(url, headers=HEADERS, timeout=12)
            res.encoding = res.apparent_encoding or "utf-8"
            for t, l, d in _rss_items(res.text):
                if t in 중복:
                    continue
                중복.add(t)
                결과.append({"제목": t, "링크": l, "요약": d, "출처": 이름})
        except Exception as e:
            print(f"  ⚠️ 뉴스({이름}) 실패: {type(e).__name__}")
        print(f"  · {이름}: {len(결과)-n0}건")

    # ── 후보 주소가 여럿인 매체 — 먼저 되는 주소 하나만 채택 ──
    #  ⚠️ 실패해도 아무 일도 일어나지 않는다. 그냥 0건으로 넘어간다.
    for 이름, 후보들 in NEWS_RSS_후보:
        n0 = len(결과)
        for url in 후보들:
            try:
                res = requests.get(url, headers=HEADERS, timeout=12)
                res.encoding = res.apparent_encoding or "utf-8"
                항목 = _rss_items(res.text)
                if not 항목:
                    continue
                for t, l, d in 항목:
                    if t in 중복:
                        continue
                    중복.add(t)
                    결과.append({"제목": t, "링크": _fix_entity_url(l),
                                 "요약": d, "출처": 이름})
                print(f"  · {이름}: {len(결과)-n0}건 (채택 주소: {url})")
                break
            except Exception as e:
                print(f"  ⚠️ 뉴스({이름}) 후보 실패 {url} — {type(e).__name__}")
        else:
            print(f"  · {이름}: 0건 — 후보 {len(후보들)}개 모두 실패(무시하고 진행)")

    # 네이버 금융 — 국내 증시 뉴스라 종목명이 자주 나온다. 보조로 함께 쓴다.
    이름, url, params = NEWS_NAVER
    n0 = len(결과)
    try:
        res = requests.get(url, headers=HEADERS, params=params, timeout=12)
        res.encoding = "euc-kr"
        soup = BeautifulSoup(res.text, "html.parser")
        요약들 = [_clean(x.get_text(" ", strip=True)) for x in soup.select("dd.articleSummary")]
        for k, a in enumerate(soup.select("dd.articleSubject a") or
                              soup.select("a[href*='news_read']")):
            t = _clean(a.get("title") or a.get_text(" ", strip=True))
            href = a.get("href", "")
            if not t or len(t) < 6 or not href or t in 중복:
                continue
            중복.add(t)
            from urllib.parse import urljoin
            # 🆕 2026-08-24 — 링크가 기사로 안 가고 사이트 첫 화면으로 튀던 버그.
            #  ⚠️ 원인: HTML 파서가 주소 안의 `&sect`를 **기호 §로 해석**해버린다.
            #     `...&section_id=101` → `...§ion_id=101` 이 되어 주소가 깨졌다.
            #     (다른 매체는 RSS라 무사했고, 네이버금융만 HTML 파싱이라 당했다)
            #  ⚠️ &sect 말고도 같은 함정이 있다(&para, &copy, &reg, &times…).
            #     주소에서 실제로 나올 법한 것만 되돌린다.
            href = _fix_entity_url(href)
            결과.append({"제목": t, "링크": urljoin(url, href),
                         "요약": (요약들[k] if k < len(요약들) else "")[:300],
                         "출처": 이름})
    except Exception as e:
        print(f"  ⚠️ 뉴스({이름}) 실패: {type(e).__name__}")
    print(f"  · {이름}: {len(결과)-n0}건")

    print(f"✅ 뉴스 원본 {len(결과)}건 (제목+요약)")
    if not 결과:
        print("  ⚠️ 0건 — 수집원이 모두 실패했습니다. 구조 변경 의심.")
    # ⚠️ 앞에서부터 자르면 **첫 매체만 남는다**(한경 80건 → 나머지 0건).
    #    매체별로 번갈아 뽑아 골고루 섞는다. 그래야 이슈 해부 링크도 다양해진다.
    #
    # 🆕 2026-08-22 수정 — "라운드로빈으로 섞는데도 계속 한경 위주로 뽑힌다"는
    #    지적으로 원인 둘을 더 찾았다.
    #    ① 한국경제만 RSS 피드가 2개(economy·finance)라 출처가 합쳐지면 물량이
    #       다른 매체의 거의 2배였다. → 매체당 상한(NEWS_매체당상한)을 걸어
    #       라운드로빈 이전에 이미 물량 격차를 없앤다.
    #    ② 라운드마다 뽑는 순서가 항상 "한국경제→머니투데이→아시아경제→
    #       네이버금융"으로 고정이라, 한경이 '뉴스원본' 리스트 맨 앞을 계속
    #       차지했다. Claude가 앞쪽 항목을 더 많이 참조하는 경향과 만나면
    #       실질적으로 매일 한경 위주로 뽑히는 구조였다.
    #       → 라운드마다 매체 순서를 무작위로 섞어 특정 매체가 항상
    #         앞자리를 갖지 못하게 한다.
    from collections import defaultdict, Counter
    _버킷 = defaultdict(list)
    for _x in 결과:
        _버킷[_x["출처"]].append(_x)
    for _k in _버킷:
        _버킷[_k] = _버킷[_k][:NEWS_매체당상한]
    _섞, _i = [], 0
    while len(_섞) < 90 and any(len(v) > _i for v in _버킷.values()):
        _순서 = list(_버킷)
        random.shuffle(_순서)          # 🆕 매 라운드 순서를 섞어 특정 매체 고정 선두 방지
        for _k in _순서:
            if len(_버킷[_k]) > _i and len(_섞) < 90:
                _섞.append(_버킷[_k][_i])
        _i += 1
    print("   섞은 뒤: " + " · ".join(f"{k} {v}건" for k, v in Counter(x["출처"] for x in _섞).items()))
    return _섞


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
    # 🔴 2026-09-21 — 선물(외선) «소급 채우기».
    #   옛 경로 폐지로 2026-09-17부터 외선이 None이었다. 새 API가 30일치를
    #   한 번에 주므로, None인 과거 날짜만 채운다. 이미 값이 있는 날은
    #   건드리지 않는다(그날 그 시각에 본 값이 기록의 원본이다).
    _선이력 = ((파생 or {}).get("선물수급") or {}).get("이력") or {}
    _채움 = 0
    for x in 이력:
        # 🔴 2026-09-22 — 9/17 이후 «정확히 0.0»은 금액을 못 읽은 오염값이다.
        #   (선물 응답 diffValue=0을 그대로 소급해 넣었다) → 다시 채우거나 비운다.
        if x.get("날짜", "") >= "20260917" and x.get("외선") == 0.0:
            x["외선"] = None
        if x.get("외선") is None and x.get("날짜") in _선이력:
            x["외선"] = _선이력[x["날짜"]]
            _채움 += 1
    if _채움:
        print(f"  ♻️ 선물(외선) 소급 {_채움}일 채움")
    이력 = 이력[-60:]

    with open(파일, "w", encoding="utf-8") as f:
        json.dump(이력, f, ensure_ascii=False, indent=1)
    print(f"✅ flow_history 갱신: 오늘 실탄 {오늘['실탄']:+,}억 · 누적 {len(이력)}일치")
    return 이력


def _updown_sane(m):
    """상승/보합/하락 묶음이 '진짜 시장 숫자'인지 검사한다.

    🆕 2026-08-24 — 이 검사가 없어서 사고가 났다.
       파싱이 엉뚱한 숫자를 잡아 {상승 1, 보합 1, 하락 1}을 그대로 저장했고,
       휴장 판정과 리포트 문장이 그 쓰레기 값을 근거로 삼았다.
    ⚠️ 원칙: **못 구하는 것보다 틀리게 구하는 게 훨씬 나쁘다.**
       코스피는 약 950종목, 코스닥은 약 1,750종목이다.
       한 시장 합계가 500 미만이거나 3,500 초과면 파싱 실패로 본다.
    """
    if not isinstance(m, dict) or len(m) != 3:
        return False
    try:
        vals = [int(m[k]) for k in ("상승", "보합", "하락")]
    except (KeyError, TypeError, ValueError):
        return False
    if any(v < 0 for v in vals):
        return False
    return 500 <= sum(vals) <= 3500


def _updown_from_html(t):
    """HTML 한 덩어리에서 코스피·코스닥의 상승/보합/하락을 뽑는다.

    ⚠️ 네이버 서식이 바뀌면 여기가 제일 먼저 깨진다. 그래서
       ① 여러 패턴을 순서대로 시도하고
       ② 뽑은 값은 반드시 _updown_sane()을 통과해야 채택한다.
    """
    결과 = {}
    조각 = re.split(r"(?i)kosdaq|코스닥", t, maxsplit=1)
    쌍 = list(zip(["코스피", "코스닥"], 조각)) if len(조각) == 2 else [("코스피", t)]
    for 이름, 블록 in 쌍:
        for 패턴 in (
            # ① "상승</span> <span>523</span>" 처럼 태그가 끼어드는 형태
            r"{k}\s*</[^>]+>\s*(?:<[^>]+>\s*)*([\d,]{{2,5}})",
            # ② "상승 523" 처럼 바로 붙는 형태
            r"{k}[^0-9<]{{0,20}}([\d,]{{2,5}})",
            # ③ 사이에 태그가 여럿 끼는 느슨한 형태(마지막 수단)
            r"{k}(?:[^0-9]{{0,80}}?)([\d,]{{2,5}})",
        ):
            m = {}
            for k in ("상승", "보합", "하락"):
                mm = re.search(패턴.format(k=k), 블록)
                if mm:
                    try:
                        m[k] = int(mm.group(1).replace(",", ""))
                    except ValueError:
                        pass
            if _updown_sane(m):
                결과[이름] = m
                break
    return 결과


def _fix_entity_url(u):
    """HTML 파서가 주소 안에서 잘못 바꿔버린 기호를 원래대로 되돌린다.

    🆕 2026-08-24 — 실제로 겪은 버그.
       `&section_id=101` 의 앞부분 `&sect`가 HTML 엔티티로 인식돼 `§`가 됐다.
       세미콜론이 없어도 브라우저·파서는 관대하게 해석해버린다.
    ⚠️ 되돌릴 대상은 **주소 파라미터에 실제로 나올 법한 것만** 넣는다.
       무차별로 바꾸면 멀쩡한 주소를 망가뜨린다.
    """
    if not u or not isinstance(u, str):
        return u
    표 = {"§": "&sect", "¶": "&para", "©": "&copy", "®": "&reg",
         "×": "&times", "÷": "&divide", "±": "&plusmn", "¤": "&curren"}
    for 기호, 원본 in 표.items():
        if 기호 in u:
            u = u.replace(기호, 원본)
    return u


def collect_updown_counts():
    """코스피·코스닥의 상승/하락/보합 종목 수.

    이 숫자는 사후 복원이 사실상 불가능해서 **그날 담지 못하면 영영 없다.**
    (유료 챕터 「시장 국면 내비」의 원료이기도 하다.)

    🆕 2026-08-24 전면 재작성 — 기존 파서는 조용히 쓰레기 값을 만들었다.
       바뀐 점 세 가지:
         ① 출처를 2곳으로 늘렸다 (메인 → 시장별 페이지)
         ② 뽑은 값은 _updown_sane() 검사를 통과해야만 채택한다
         ③ 실패하면 None을 돌려주고, **원문 일부를 로그에 남긴다**
            (샌드박스에서 네이버가 403이라 서식을 직접 확인할 수 없다.
             다음에 정확히 고치려면 실제 응답 조각이 필요하다.)
    ⚠️ 절대 추정값을 넣지 않는다. 없으면 None이다.
    """
    def _get(url):
        try:
            r = requests.get(url, headers=HEADERS, timeout=12)
            r.encoding = "euc-kr"
            return r.text
        except Exception as e:
            print(f"   ⚠️ 등락종목수 요청 실패({url}): {e}")
            return ""

    결과 = {}
    # ── 1차: 국내증시 메인 (두 시장이 한 페이지에 있다) ──
    본문 = _get("https://finance.naver.com/sise/")
    결과.update(_updown_from_html(본문))

    # ── 2차: 1차에서 못 구한 시장만 시장별 페이지로 재시도 ──
    보조 = {"코스피": "https://finance.naver.com/sise/sise_index.naver?code=KOSPI",
           "코스닥": "https://finance.naver.com/sise/sise_index.naver?code=KOSDAQ"}
    for 이름, url in 보조.items():
        if 이름 in 결과:
            continue
        조각 = _updown_from_html(_get(url))
        # 시장별 페이지는 그 시장 값만 있으므로 이름을 가리지 않고 아무거나 채택
        for v in 조각.values():
            if _updown_sane(v):
                결과[이름] = v
                break

    if not 결과:
        print("   ⚠️ 상승/보합/하락 종목 수를 찾지 못했습니다 → null로 기록(추정값 금지)")
        # 다음에 정확히 고치기 위한 단서 — '상승' 주변 원문을 조금만 남긴다
        단서 = re.findall(r".{0,60}상승.{0,60}", 본문)[:2]
        for c in 단서:
            print("      단서:", re.sub(r"\s+", " ", c)[:120])
        return None

    for 이름, m in 결과.items():
        print(f"   {이름} 상승 {m['상승']} · 보합 {m['보합']} · 하락 {m['하락']}")
    for 이름 in ("코스피", "코스닥"):
        if 이름 not in 결과:
            print(f"   ⚠️ {이름}는 못 구했습니다 (한쪽만 기록됨)")
    return 결과


def update_market_history(지수수급, 파생, 게이지, 등락수, 시장조치=None):
    """market_history.json — 서비스가 존재하는 한 **영구 누적**하는 시장 일지.

    🔴 원칙: 절대 자르지 않는다 (60일 캡 없음). 같은 날짜 재실행 시에만 그 행 덮어쓰기.
       상승/하락 종목 수·레이더 이력 등은 사후 복원이 불가능한 데이터다.
       이 파일이 유료 챕터(국면 내비·확률 캘린더·수급 온도)의 원료가 된다.
    ⚠️ daily.yml 의 git add 목록에 market_history.json 이 있어야 커밋된다.
    """
    if _휴장일():                      # 🔴 2026-09-28 — 휴장일엔 영구 이력에 안 쓴다
        return
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
         # 🆕 2026-08-25 — 사이드카·서킷. 없는 날은 None(대부분의 날).
         #  ⚠️ 이 필드는 항로도 「특징」이 "올해 N번째 사이드카"를 세는 재료다.
         "시장조치": 시장조치,
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


MACRO_HIST_PATH = "macro_history.json"
MACRO_HIST_저장일수 = 20   # 화면엔 5일만 쓰지만, 넉넉히 저장해 나중 확장에 대비


def _macro_hist_load():
    """macro_history.json 읽기 — 없으면 빈 뼈대."""
    try:
        with open(MACRO_HIST_PATH, encoding="utf-8") as f:
            본체 = json.load(f)
        if isinstance(본체, dict) and isinstance(본체.get("일별"), dict):
            return 본체
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        pass
    return {"버전": SCRIPT_VERSION, "일별": {}}


def save_macro_history(수집):
    """매크로 시·고·저·종을 날짜별로 **영구 누적**한다.

    🆕 2026-09-07 HO 지시 — "환율·채권·유가·금도 캔들로."

    [왜 별도 파일인가]
      archive/data_*.json에 시고저를 넣으면 **오늘부터만** 쌓인다(코스피 캔들이
      정확히 그래서 20거래일을 기다려야 했다). 그런데 yfinance는 과거 OHLC를
      한 번에 내려주므로, 별도 이력 파일에 백필하면 **첫날부터 바로 캔들**이
      나온다. 기다릴 이유가 없는데 기다리는 건 손해다.

    [덮어쓰기 규칙]
      같은 날짜가 이미 있어도 **새 값으로 갱신한다.** 매크로는 24시간 시장이라
      장중에 수집하면 그날 봉이 미완성인데, 다음날 다시 받으면 완성된 값이
      온다. 지수(확정 종가)와 달리 여기선 최신값이 더 정확하다.
      ⚠️ 단, 과거 날짜를 **지우지는** 않는다(원칙3).
    """
    본체 = _macro_hist_load()
    본체["버전"] = SCRIPT_VERSION
    갱신 = 0
    for key, rows in (수집 or {}).items():
        if not rows:
            continue
        칸 = 본체["일별"].setdefault(key, {})
        for r in rows:
            날 = r.get("날짜")
            if not 날:
                continue
            칸[날] = {"시": r["시"], "고": r["고"], "저": r["저"], "종": r["종"],
                     "미확정": bool(r.get("미확정"))}
            갱신 += 1
        # 저장일수 초과분은 오래된 것부터 정리 — 이 파일은 «캔들용»이라
        # 영구 보관 대상이 아니다(영구 이력은 market_history.json 담당).
        if len(칸) > MACRO_HIST_저장일수:
            for 낡 in sorted(칸.keys())[:-MACRO_HIST_저장일수]:
                칸.pop(낡, None)
    try:
        with open(MACRO_HIST_PATH, "w", encoding="utf-8") as f:
            json.dump(본체, f, ensure_ascii=False, indent=1)
        일수 = {k: len(v) for k, v in 본체["일별"].items()}
        print(f"✅ macro_history 갱신: {갱신}건 반영 · 보유 {일수}")
    except OSError as e:
        print(f"⚠️ macro_history 저장 실패: {type(e).__name__}: {str(e)[:120]}")
    return 본체


def collect_macro():
    결과 = {}
    이력 = {}
    for key, info in MACRO_TICKERS.items():
        try:
            t = yf.Ticker(info["심볼"])
            # 🆕 2026-09-07 — 5d → 1mo. 캔들 백필용으로 과거분을 같이 받는다.
            #    요청 횟수는 그대로 1회다(기간만 늘림 — 추가 비용 0).
            hist = t.history(period="1mo")
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
            # ── 캔들용 OHLC 추출 ──
            # ⚠️ 지표마다 타임존이 다르다(실측: 환율=London, 미국채=Chicago,
            #    유가·금=New_York). 그래서 한국 날짜로 억지로 바꾸지 않고
            #    **그 지표 자신의 거래일**을 그대로 쓴다. 카드마다 독립된
            #    그래프라 서로 날짜를 맞출 필요가 없고, 억지 변환이 오히려
            #    하루씩 밀리는 오차를 만든다.
            try:
                _오늘그곳 = str(datetime.now(hist.index.tz).date()).replace("-", "")
            except Exception:
                _오늘그곳 = None
            줄 = []
            for _dt, _r in hist.tail(MACRO_HIST_저장일수).iterrows():
                try:
                    시, 고 = float(_r["Open"]), float(_r["High"])
                    저, 종 = float(_r["Low"]), float(_r["Close"])
                except (TypeError, ValueError, KeyError):
                    continue
                # nan 방어 — 자기 자신과 다르면 nan이다(실측: 8/29 유가).
                if any(v != v for v in (시, 고, 저, 종)):
                    continue
                _날 = str(_dt.date()).replace("-", "")
                줄.append({"날짜": _날,
                          "시": round(시, 4), "고": round(고, 4),
                          "저": round(저, 4), "종": round(종, 4),
                          # 그 시장의 «오늘» 봉이면 아직 장이 안 끝났을 수 있다.
                          # 24시간 시장이라 우리 발행(18시 KST) 시점엔 진행 중인
                          # 경우가 대부분 — 화면에서 «진행 중»으로 표시한다.
                          "미확정": (_오늘그곳 is not None and _날 == _오늘그곳)})
            if 줄:
                이력[key] = 줄
        except Exception as e:
            print(f"⚠️ {info['표시명']} 수집 실패: {type(e).__name__}: {str(e)[:120]}")
            결과[key] = None

    성공 = sum(1 for v in 결과.values() if v is not None)
    print(f"✅ 환율/유가/금리 {성공}/{len(MACRO_TICKERS)}건 수집")
    if 이력:
        save_macro_history(이력)
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
        h["Referer"] 