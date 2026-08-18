# ============================================================
# build_html.py  (v2)
#  data_YYYYMMDD.json (+ report_YYYYMMDD.json 있으면) → report_YYYYMMDD.html
#  포함: 관제지수 게이지(산정기준 토글) · 주도섹터6(짙은분홍) · 예측셀프체크
# ============================================================

import json
import os
import re
import html
from datetime import datetime

SCRIPT_VERSION = "v2026.08.18-n5"   # ⬅ 버전 표시
                             #    5개 파일(build_html/generate_report/collect_data/
                             #    make_thumb/notify_telegram)이 **항상 같은 번호**여야 한다.
                             #    번호가 다르면 일부 파일만 올라간 것이다.

# ── 거래일 계산 (v-k5 신규) ──────────────────────────────
#  왜 필요한가: 금요일 리포트가 "내일 확인하세요"라고 쓰면 틀린 안내가 된다.
#  실제로 2026-08-14(금) 리포트의 다음 거래일은 8/17(월)이 아니라 **8/18(화)**였다.
#  (8/15 광복절이 토요일 → 8/17 월요일이 대체공휴일 → 증시 휴장)
#  주말은 코드가 확실히 알 수 있지만 공휴일은 표가 필요하다.
#
#  ⚠️ 연 1회 갱신 필요: 아래 표에 새해 휴장일을 추가하지 않으면
#     주말만 반영되고 공휴일은 놓친다(로그에 경고가 뜬다).
KRX_HOLIDAYS = {
    2026: {
        "20260101",                                     # 신정
        "20260216", "20260217", "20260218",             # 설날 연휴
        "20260302",                                     # 삼일절 대체(3/1 일요일)
        "20260501",                                     # 근로자의 날
        "20260505",                                     # 어린이날
        "20260525",                                     # 부처님오신날 대체(5/24 일요일)
        "20260603",                                     # 지방선거
        "20260717",                                     # 제헌절(2026년 재지정)
        "20260817",                                     # 광복절 대체(8/15 토요일)
        "20260924", "20260925",                         # 추석 연휴(9/26은 토요일)
        "20261005",                                     # 개천절 대체(10/3 토요일)
        "20261009",                                     # 한글날
        "20261225",                                     # 성탄절
        "20261231",                                     # 연말 폐장(KRX 관행)
    },
}

_요일한글 = ("월", "화", "수", "목", "금", "토", "일")

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


def _fold(제목, 내용HTML, key):
    """긴 설명을 '더보기'로 접는다.

    ⚠️ <details>를 쓰는 이유: JS 없이 동작하고, 접힌 상태에서도
       내용이 DOM에 있어 검색·복사가 된다. 화면만 짧아진다.
       (설명이 길면 정작 봐야 할 표가 밀려나 안 읽힌다)
    """
    return (f'<details style="margin:9px 0 0"><summary style="cursor:pointer;'
            f'list-style:none;font-size:11.5px;color:#e0c060;font-weight:700;'
            f'padding:7px 10px;background:#0f131a;border:1px solid #1e2531;'
            f'border-radius:8px;-webkit-tap-highlight-color:transparent">'
            f'{제목} <span style="color:#6f7784;font-weight:600">· 눌러서 펼치기</span>'
            f'</summary>'
            f'<div style="margin-top:6px;padding:10px;background:#0f131a;'
            f'border-radius:8px;border:1px solid #1e2531">{내용HTML}</div></details>')


def grid_slot_of(테마명):
    """주도섹터(그날의 네이버 테마명) → 계좌 구역(고정 슬롯) 이름.

    ⚠️ collect_data.py와 **반드시 같은 내용**이어야 한다(GRID_슬롯 포함).
       두 지도를 잇는 유일한 다리라, 한쪽만 고치면 배지가 어긋난다.
    """
    if not 테마명:
        return None
    t = str(테마명).lower()
    for 슬롯명, 키워드들 in GRID_슬롯:
        if any(k.lower() in t for k in 키워드들):
            return 슬롯명
    return None




def is_trading_day(d):
    """datetime.date → 장이 열리는 날인가."""
    if d.weekday() >= 5:                 # 토·일
        return False
    표 = KRX_HOLIDAYS.get(d.year)
    if 표 is None:
        return True                      # 표가 없으면 주말만 반영 (아래에서 경고)
    return d.strftime("%Y%m%d") not in 표


def next_trading_day(base):
    """base(datetime.date) 다음의 첫 거래일. 최대 20일까지만 찾는다."""
    from datetime import timedelta
    d = base
    for _ in range(20):
        d = d + timedelta(days=1)
        if is_trading_day(d):
            return d
    return base


def trading_day_context(today):
    """프롬프트·화면에 넣을 날짜 표현을 한 번에 만든다.

    반환 예)
      {"오늘": "2026-08-14(금)", "다음거래일": "2026-08-18(화)",
       "다음거래일표현": "화요일(8/18)", "휴장안내": "8/17(월)은 광복절 대체공휴일로 휴장입니다",
       "오늘휴장": False}
    """
    from datetime import timedelta
    nxt = next_trading_day(today)
    간격 = (nxt - today).days
    if 간격 == 1:
        표현 = "내일"
    else:
        표현 = f"{_요일한글[nxt.weekday()]}요일({nxt.month}/{nxt.day})"

    # 중간에 낀 '평일인데 쉬는 날'만 안내한다(주말은 굳이 설명할 필요 없음).
    쉬는평일 = []
    d = today + timedelta(days=1)
    while d < nxt:
        if d.weekday() < 5:
            쉬는평일.append(f"{d.month}/{d.day}({_요일한글[d.weekday()]})")
        d += timedelta(days=1)
    휴장안내 = (f"{', '.join(쉬는평일)}은(는) 공휴일로 증시가 열리지 않습니다"
              if 쉬는평일 else "")

    표없음 = KRX_HOLIDAYS.get(today.year) is None
    return {
        "오늘": f"{today:%Y-%m-%d}({_요일한글[today.weekday()]})",
        "오늘요일": f"{_요일한글[today.weekday()]}요일",
        "다음거래일": f"{nxt:%Y-%m-%d}({_요일한글[nxt.weekday()]})",
        "다음거래일표현": 표현,
        "휴장안내": 휴장안내,
        "오늘휴장": not is_trading_day(today),
        "휴장표없음": 표없음,
    }

# ⚙️ 개발용 조건 표시 — 배포 시 False로 바꾸면 모든 조건 설명이 사라진다
SHOW_CRITERIA = True

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


DATA_PATH = apath(f"data_{DATE}.json")
REPORT_PATH = apath(f"report_{DATE}.json")
OUT_PATH = f"report_{DATE}.html"

# collect_data.py 와 동일한 사전(설명 붙이기용). 여기서도 참조.
THEME_DICT = {
    "S7": "반도체 소부장 그룹", "자원개발": "해외 광물·에너지 자원", "LNG": "액화천연가스",
    "MLCC": "적층세라믹콘덴서(전자부품)", "OLED": "유기발광 디스플레이", "면역항암제": "암 치료 신약",
    "CXL": "차세대 메모리 연결기술", "HBM": "고대역폭 메모리", "전력설비": "송배전·전력 인프라",
    "마이크로 LED": "차세대 디스플레이", "PCB": "인쇄회로기판", "리튬": "2차전지 핵심 원료",
    "희토류": "첨단산업 필수 광물", "탄소나노튜브": "차세대 소재",
}
THEME_SUFFIX = {"로봇": "(산업용/협동로봇)", "지능형로봇/인공지능(AI)": "(산업용/협동로봇)"}


def load_json(path):
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)



def dev_note(text):
    """개발용 조건 표시. SHOW_CRITERIA=False면 아무것도 출력하지 않는다."""
    if not SHOW_CRITERIA:
        return ""
    return f'<p class="devnote">⚙️ <b>적용 조건</b> · {text}</p>'


def esc_url(u):
    """URL을 href에 넣기 전에 &를 &amp;로 바꾼다.
    ⚠️ 이걸 안 하면 '&section_id'의 '&sect'를 브라우저가 § 기호로 해석해
    링크가 깨진다(실제로 겪었던 버그)."""
    if not u:
        return "#"
    return html.escape(str(u), quote=True)


def idx_dir_class(지수):
    """지수 카드 등락 색상 — 국내 HTS 문법(상승=빨강, 하락=파랑).

    ⚠️ 예전 코드는 '등락방향'에 '-'가 들어있는지 봤는데, 이 값은 '상승'/'하락'
       한글이라 마이너스 기호가 없다. 그래서 하락한 날도 빨강으로 나왔다.
       이제 등락률의 부호를 먼저 보고, 없으면 방향 글자로 판단한다.
    """
    률 = str(지수.get("등락률", "")).strip()
    if 률.startswith("-") or 률.startswith("−"):
        return "ic-chg-dn"
    방향 = str(지수.get("등락방향", ""))
    if "하락" in 방향 or "▼" in 방향:
        return "ic-chg-dn"
    try:
        if float(률.replace(",", "")) < 0:
            return "ic-chg-dn"
    except ValueError:
        pass
    return "ic-chg-up"


def money_class(text):
    """수급 값의 부호로 색상 클래스 결정. +는 up(빨강), -는 dn(파랑)."""
    v = _to_float(text)
    if v is None:
        # 숫자 변환 실패 시 문자열 기호로 폴백
        t = str(text)
        if "-" in t or "−" in t:
            return "dn"
        if "+" in t:
            return "up"
        return "smut"
    if v > 0:
        return "up"
    if v < 0:
        return "dn"
    return "smut"


def _to_float(x):
    if x is None:
        return None
    s = str(x).replace(",", "").replace("%", "").replace("+", "").replace("−", "-").strip()
    try:
        return float(s)
    except ValueError:
        return None


def fmt_flow(억값):
    """네이버 수급(억원 단위 숫자) → '+3.66조' 또는 '+1,565억' 로 표시."""
    v = _to_float(억값)
    if v is None:
        return "—"
    sign = "+" if v > 0 else ("−" if v < 0 else "")
    a = abs(v)
    if a >= 10000:  # 1조 이상
        return f"{sign}{a/10000:.2f}조"
    return f"{sign}{a:,.0f}억"


def fmt_price(값):
    """현재가 → 콤마 표시. '259500' → '259,500'."""
    v = _to_float(값)
    if v is None:
        return str(값) if 값 not in (None, "") else "—"
    return f"{v:,.0f}"


def fmt_trade(값):
    """거래대금(네이버 테마상세는 '백만원' 단위) → 조/억 표시.
    예: 2801739(백만) → 2.80조 / 25005(백만) → 250억."""
    v = _to_float(값)
    if v is None:
        return "—"
    억 = v / 100  # 100백만 = 1억
    if 억 >= 10000:
        return f"{억/10000:.2f}조"
    if 억 >= 1:
        return f"{억:,.0f}억"
    return f"{v:,.0f}백만"


def stars_html(score):
    score = score or 2
    return "★" * score + '<span class="off">' + "★" * (5 - score) + "</span>"


def theme_label(테마명):
    """테마명 + (설명/부가). 사전에 있으면 설명, 없으면 원본만."""
    suffix = THEME_SUFFIX.get(테마명, "")
    desc = THEME_DICT.get(테마명, "")
    label = f'<span class="sc-name">{테마명}</span>'
    if suffix:
        label += f'<span class="sc-sfx">{suffix}</span>'
    elif desc:
        label += f'<span class="sc-sfx">({desc})</span>'
    return label


# ── 게이지 ──────────────────────────────────────────────
def build_gauge(gauge, 오늘한줄평):
    if not gauge:
        return '<div class="gauge-box"><p style="color:#9aa0a8">⏳ 관제지수 데이터 없음</p></div>'
    점수 = gauge["점수"]
    구간 = gauge["구간"]
    이모지 = gauge["이모지"]

    # 산정기준 표
    행들 = []
    for d in gauge.get("상세", []):
        행들.append(f'''
      <div class="gz-row">
        <span class="gz-el">{d['요소']}</span>
        <span class="gz-sc">{d['점수']}점</span>
        <span class="gz-w">가중 {d['가중치']}%</span>
        <span class="gz-ev">{d['근거']}</span>
      </div>''')
    기준표 = "".join(행들)

    # 눈금 위 바늘 위치 (%)
    needle = max(0, min(100, 점수))

    # 한줄평 근거 배지
    배지들 = gauge.get("배지", [])
    배지HTML = ""
    if 배지들:
        배지HTML = '<div class="gz-badges">' + "".join(
            f'<span class="gz-badge">{b}</span>' for b in 배지들) + '</div>'

    return f'''
  <div class="gauge-box">
    <div class="gz-top">
      <div class="gz-numwrap"><p class="gz-num">{점수}</p><p class="gz-lab">{구간} {이모지}</p></div>
      <div class="gz-bodywrap">
        <p class="gz-title">📡 관제지수 (0~100) — 오늘 시장의 온도</p>
        <div class="gz-track">
          <div class="gz z1"></div><div class="gz z2"></div><div class="gz z3"></div><div class="gz z4"></div><div class="gz z5"></div>
          <div class="gz-needle" style="left:{needle}%"></div>
        </div>
        <div class="gz-scale"><span>혹한</span><span>한파</span><span>보통</span><span>온기</span><span>과열</span></div>
      </div>
    </div>
    <p class="gz-oneline">📝 <b>한줄평:</b> {오늘한줄평}</p>
    {배지HTML}
    <button class="gz-toggle" onclick="toggleMore('gzDetail',this,'▾ 산정 기준 보기')">▾ 산정 기준 보기</button>
    <div class="hidden-block" id="gzDetail">
      <div class="gz-detail">{기준표}
        <p class="gz-note">※ 각 요소를 0~100으로 환산해 가중 합산한 자체 참고 지표입니다. 거래대금(평소 대비)·극단 심리 지표는 데이터가 쌓이는 대로 추가됩니다.</p>
      </div>
    </div>
  </div>'''


# ── 주도 섹터 6개 ────────────────────────────────────────
# 주도 섹터의 '최근 20일 강도' — 오늘 테마가 지난 한 달간 얼마나 자주 상위권에 있었나.
#   반짝 테마(오늘 처음)와 꾸준한 대장(며칠째 상위)을 구분해준다. 전부 규칙 기반.
_SECTOR_HIST_CACHE = None


def _sector_history(days=20):
    """archive/data_*.json에서 최근 days일의 [ (날짜, [테마명 순위대로]) ] 를 읽는다.
    한 번 읽으면 캐시(같은 리포트 빌드 중 여러 섹터가 재사용)."""
    global _SECTOR_HIST_CACHE
    if _SECTOR_HIST_CACHE is not None:
        return _SECTOR_HIST_CACHE
    hist = []
    try:
        import glob
        files = sorted(glob.glob(os.path.join(ARCHIVE, "data_*.json")))
        # 루트에도 있을 수 있어 합침(하위호환)
        files += sorted(glob.glob("data_*.json"))
        files = sorted(set(files))[-days:]
        for f in files:
            try:
                with open(f, encoding="utf-8") as fp:
                    주도 = (json.load(fp).get("주도섹터") or [])
                hist.append([s.get("테마명") for s in 주도])
            except Exception:
                continue
    except Exception:
        pass
    _SECTOR_HIST_CACHE = hist
    return hist


def sector_strength_badge(테마명):
    """테마 하나의 20일 강도 배지 HTML. 이력이 얇으면 빈 문자열."""
    hist = _sector_history()
    N = len(hist)
    if N < 3 or not 테마명:
        return ""     # 최소 3일은 쌓여야 의미 있음
    순위들 = [day.index(테마명) + 1 for day in hist if 테마명 in day]
    등장 = len(순위들)
    if 등장 <= 1:
        # 오늘 처음(또는 오늘만) — 신규 대장
        return ('<span class="sc-str new">🆕 신규 주도 · '
                f'최근 {N}일 중 처음</span>')
    평균 = sum(순위들) / 등장
    최고 = min(순위들)
    # 꾸준함 강도로 라벨을 나눈다
    if 등장 >= max(3, N // 3) and 평균 <= 3:
        급 = "🔥 대장 지속"
    elif 등장 >= 2:
        급 = "📈 재등장"
    else:
        급 = "📈 재등장"
    return (f'<span class="sc-str">{급} · '
            f'{N}일 중 <b>{등장}일</b> 상위 · 평균 <b>{평균:.1f}위</b></span>')


def one_sector_card(a):
    rows = []
    for s in a.get("종목", [])[:4]:
        rate = str(s.get("등락률", "—"))
        cls = "dn" if ("-" in rate or "−" in rate) else "up"
        rows.append(f'''
        <div class="sc-row"><span class="sc-stock">{s.get('종목명','—')}</span>
          <span class="sc-price">{fmt_price(s.get('현재가'))}</span>
          <span class="sc-rate {cls}">{rate}</span>
          <span class="sc-vol">{fmt_trade(s.get('거래대금'))}</span></div>''')
    et = a.get("테마등락")
    et_s = f"{et:+.2f}%" if isinstance(et, (int, float)) else "—"
    badge_cls = "pos" if (isinstance(et, (int, float)) and et >= 0) else ""
    head_cls = "pos" if (isinstance(et, (int, float)) and et >= 0) else ""
    점수 = a.get("주도력점수", "—")
    강도배지 = sector_strength_badge(a.get('테마명'))
    # 이 현장이 '내 종목 구역'의 어느 줄인지 이어준다(두 지도를 잇는 다리).
    _구역 = a.get("계좌구역") or grid_slot_of(a.get("테마명"))
    구역배지 = (f'<p style="margin:2px 0 0;font-size:10px;color:#22d3ee">'
              f'↳ {_구역} 구역</p>') if _구역 else ''
    return f'''
    <div class="sector-card">
      <div class="sc-head {head_cls}">
        <div class="sc-name-row">{theme_label(a['테마명'])}
          <span class="sc-chg {badge_cls}">{et_s}</span></div>
        <p class="sc-score">주도력 {점수}점</p>
        {f'<p class="sc-strline">{강도배지}</p>' if 강도배지 else ''}
        {구역배지}
      </div>
      <div class="sc-list">
        <div class="sc-cols"><span>종목명</span><span>현재가</span><span>등락률</span><span>거래대금</span></div>
        {"".join(rows)}
      </div>
    </div>'''


# ── 섹터 지형도 (0선 기준 세로 막대, 데이터에 맞춰 자동 스케일) ──
def build_terrain(주도섹터):
    """주도섹터 6개의 테마 등락률로 막대 차트를 그린다.

    ⚠️ 예전 방식의 두 가지 문제를 고쳤다.
      ① 0선을 항상 한가운데(50%)에 고정 → 오늘처럼 6개가 전부 상승이면
         아래 절반이 통째로 빈 공간이 됐다.
      ② 막대 높이를 '등락률 × 8px'로 고정 → 등락률이 크면 막대가 영역을
         뚫고 올라가 숫자가 제목과 겹쳤다.

    새 방식: 0선 위치와 막대 높이를 **오늘 데이터에 맞춰 비율로 계산**한다.
      · 전부 상승이면 0선을 바닥으로 내려 위쪽을 다 쓴다 (빈 공간 없음)
      · 전부 하락이면 0선을 천장으로 올린다
      · 섞여 있으면 양수·음수 최대치 비율대로 0선을 배치한다
      · 가장 큰 막대가 그리는 영역을 꽉 채우되, 숫자가 앉을 자리(라벨 밴드)를
        위아래에 미리 비워둬서 절대 겹치지 않는다
      · 모든 값이 %라서 모바일에서 영역 높이가 줄어도 그대로 맞는다
    """
    if not 주도섹터:
        return ""
    항목 = []
    for a in 주도섹터[:6]:
        et = a.get("테마등락")
        v = float(et) if isinstance(et, (int, float)) else 0.0
        항목.append((a.get("테마명", ""), v))
    if not 항목:
        return ""

    최대양 = max([v for _, v in 항목 if v > 0], default=0.0)
    최대음 = max([-v for _, v in 항목 if v < 0], default=0.0)
    합 = 최대양 + 최대음
    if 합 <= 0:                      # 전부 0인 예외 상황
        최대양, 합 = 1.0, 1.0

    # 숫자가 앉을 자리를 위아래에 확보 (해당 방향에 막대가 있을 때만)
    위여백 = 15.0 if 최대양 > 0 else 3.0
    아래여백 = 15.0 if 최대음 > 0 else 3.0
    그림영역 = 100.0 - 위여백 - 아래여백
    영점 = 위여백 + (최대양 / 합) * 그림영역      # 위에서부터 % — 0선 위치

    cols = []
    for name, v in 항목:
        h = max(1.5, abs(v) / 합 * 그림영역)      # 막대 높이(%)
        if v >= 0:
            바닥 = 100.0 - 영점
            bar = f'<div class="bar pos" style="bottom:{바닥:.1f}%;height:{h:.1f}%"></div>'
            val = (f'<span class="bar-val pos" '
                   f'style="bottom:calc({바닥 + h:.1f}% + 2px)">{v:+.1f}%</span>')
        else:
            bar = f'<div class="bar neg" style="top:{영점:.1f}%;height:{h:.1f}%"></div>'
            val = (f'<span class="bar-val neg" '
                   f'style="top:calc({영점 + h:.1f}% + 2px)">{v:+.1f}%</span>')
        disp = name if len(name) <= 6 else name[:5] + "…"
        cols.append(f'''
      <div class="bar-col">
        <div class="bar-zone" style="--zero:{영점:.1f}%">{val}{bar}</div>
        <p class="bar-name">{disp}</p>
      </div>''')
    return f'''
  <div class="terrain-box">
    <p class="terrain-title">📊 오늘의 섹터 지형도 — 주도 6개 업종 등락률</p>
    <div class="bar-chart">{"".join(cols)}</div>
  </div>'''


def build_sectors(주도섹터, 설정=None):
    if not 주도섹터:
        return '<p class="smut">오늘 수집된 데이터가 없습니다.</p>'
    앞2 = 주도섹터[:2]
    뒤4 = 주도섹터[2:6]
    앞 = "".join(one_sector_card(a) for a in 앞2)
    뒤 = "".join(one_sector_card(a) for a in 뒤4)
    더보기 = ""
    if 뒤4:
        더보기 = f'''
  <div class="hidden-block" id="moreSectors"><div class="sector-grid">{뒤}</div></div>
  <button class="more-btn" onclick="toggleMore('moreSectors',this,'▾ 나머지 {len(뒤4)}개 더보기')">▾ 나머지 {len(뒤4)}개 더보기</button>'''
    return f'<div class="sector-grid">{앞}</div>{더보기}'


# ── 공시 ─────────────────────────────────────────────────
def build_disclosures(disc, 공시해설=None):
    공시해설 = 공시해설 or {}
    if not disc:
        return '<p class="disc-note" style="color:#8a909a">오늘 수집된 관심 유형 공시가 없습니다.</p>'

    def 한줄(item):
        회사 = item['회사명']
        해설 = 공시해설.get(회사, "")
        해설HTML = f'<p class="disc-why">💡 {해설}</p>' if 해설 else ''
        return f'''
    <a class="disc-row" href="{esc_url(item['링크'])}" target="_blank">
      <div class="disc-head"><span class="disc-name">{회사}</span>
        <span class="stars">{stars_html(item['별점'])}</span></div>
      <p class="disc-note">{item['공시명']} <span class="disc-lnk">↗ 상세보기</span></p>
      {해설HTML}
    </a>'''

    앞3 = "".join(한줄(i) for i in disc[:3])
    뒤 = disc[3:8]
    if not 뒤:
        return 앞3
    뒤HTML = "".join(한줄(i) for i in 뒤)
    return f'''{앞3}
    <div class="hidden-block" id="moreDisc">{뒤HTML}</div>
    <button class="more-btn dark" onclick="toggleMore('moreDisc',this,'▾ 공시 {len(뒤)}개 더보기')">▾ 공시 {len(뒤)}개 더보기</button>'''


# ── 오늘의 공부 (단계별) ──
def build_study(공부):
    if not 공부:
        return '<div class="pending">⏳ 오늘의 공부 — 생성 실패</div>'
    if isinstance(공부, str):  # 예전 형식(문자열)도 안전하게 처리
        return f'<div class="study-box">📚 {공부}</div>'
    단계 = [("개념", 공부.get("개념", "")), ("원리", 공부.get("원리", "")),
            ("오늘 연결", 공부.get("오늘연결", ""))]
    행들 = "".join(
        f'<div class="study-step"><span class="study-k">{k}</span><span>{v}</span></div>'
        for k, v in 단계 if v)
    암기 = 공부.get("한줄암기", "")
    근거 = 공부.get("출제근거", "")
    심화단계 = [("역사에서", 공부.get("역사에서", "")),
              ("투자 적용", 공부.get("투자적용", "")),
              ("더 깊이", 공부.get("더깊이", ""))]
    심화행 = "".join(
        f'<div class="study-step"><span class="study-k">{k}</span><span>{v}</span></div>'
        for k, v in 심화단계 if v)
    심화HTML = ""
    if 심화행:
        심화HTML = f'''
    <div class="hidden-block" id="moreStudy" style="margin-top:.6rem">{심화행}</div>
    <button class="more-btn" onclick="toggleMore('moreStudy',this,'▾ 심화 학습 더보기 (역사·투자 적용)')">▾ 심화 학습 더보기 (역사·투자 적용)</button>'''

    return f'''
  <div class="study-box">
    <p class="study-no">📚 오늘 리포트에서 출제 · {공부.get("주제","")}</p>
    {f'<p class="study-src">📍 출처: {근거}</p>' if 근거 else ''}
    <p class="study-term">{공부.get("질문","")}</p>
    {행들}
    {f'<div class="study-memo">✏️ 한 줄 암기: {암기}</div>' if 암기 else ''}
  </div>{심화HTML}'''


# ── 지난 리포트 아카이브 (report_YYYYMMDD.html 자동 스캔) ──
ARCHIVE_MAX = 14          # 최근 몇 개까지 보여줄지
ARCHIVE_FOLD = 7          # 이 개수까지만 펼쳐 두고 나머지는 '더보기'
_WD = ["월", "화", "수", "목", "금", "토", "일"]


def find_past_reports():
    """같은 폴더의 report_YYYYMMDD.html 을 모아 최신순으로 돌려준다."""
    목록 = []
    try:
        파일들 = os.listdir(".")
    except Exception:
        return 목록
    for f in 파일들:
        if not (f.startswith("report_") and f.endswith(".html")):
            continue
        ymd = f[7:-5]
        if len(ymd) != 8 or not ymd.isdigit():
            continue
        if ymd == DATE:          # 오늘 리포트는 목록에서 제외
            continue
        try:
            d = datetime.strptime(ymd, "%Y%m%d")
        except ValueError:
            continue
        목록.append((ymd, d, f))
    목록.sort(key=lambda x: x[0], reverse=True)
    return 목록[:ARCHIVE_MAX]


def build_archive():
    목록 = find_past_reports()
    if not 목록:
        return ('<div class="arch-wrap"><p class="arch-head">🗂️ 지난 리포트</p>'
                '<p class="arch-empty">아직 쌓인 리포트가 없습니다. 내일부터 이 자리에 목록이 쌓입니다.</p></div>')

    def 칩(item):
        ymd, d, f = item
        return f'<a class="arch-link" href="{f}">{d.month}/{d.day}({_WD[d.weekday()]})</a>'

    앞 = "".join(칩(x) for x in 목록[:ARCHIVE_FOLD])
    뒤목록 = 목록[ARCHIVE_FOLD:]
    뒤HTML = ""
    if 뒤목록:
        뒤칩 = "".join(칩(x) for x in 뒤목록)
        뒤HTML = (f'<div class="hidden-block" id="moreArch" style="margin-top:6px">'
                  f'<div class="arch-grid">{뒤칩}</div></div>'
                  f'<button class="more-btn" style="margin-top:8px;margin-bottom:0" '
                  f'onclick="toggleMore(\'moreArch\',this,\'▾ 이전 리포트 {len(뒤목록)}개 더보기\')">'
                  f'▾ 이전 리포트 {len(뒤목록)}개 더보기</button>')
    return (f'<div class="arch-wrap"><p class="arch-head">🗂️ 지난 리포트 — 날짜를 누르면 그날 브리핑으로 이동합니다</p>'
            f'<div class="arch-grid">{앞}</div>{뒤HTML}</div>')


# ── 핵심 이슈 ──
def build_issues(핵심이슈):
    if not 핵심이슈:
        return '<div class="pending">⏳ 오늘 시장을 만든 이슈 3~4개 — 뉴스/공시 기반 자동 추출 준비중</div>'
    rows = []
    for it in 핵심이슈:
        칩들 = "".join(
            f'<a class="iss-link" href="{esc_url(l.get("링크",""))}" target="_blank">📎 {l.get("제목","기사")[:26]}…</a>'
            for l in (it.get("관련링크") or [])[:2] if l.get("링크"))
        rows.append(f'''
    <div class="iss"><span class="itag">{it.get('태그','')}</span>
      <span class="iss-text">{it.get('상세') or it.get('내용','')}{f'<span class="iss-links">{칩들}</span>' if 칩들 else ''}</span></div>''')
    return f'<div class="issue-box">{"".join(rows)}</div>'


# ── 핵심 뉴스 TOP10 (3개 노출 + 더보기) ──
NEWS_TAG_CLASS = {"시황": "nt-market", "정책": "nt-policy", "특징주": "nt-stock", "글로벌": "nt-global"}


def one_news_item(idx, item):
    tag = item.get("태그", "시황")
    cls = NEWS_TAG_CLASS.get(tag, "nt-market")
    링크 = item.get("링크", "")
    제목 = item.get("제목", "")
    요약 = item.get("요약", "")
    본문 = f'''
      <span class="news-tag {cls}">{tag}</span>{제목}<span class="news-go">↗</span>'''
    if 링크:
        title_html = f'<a class="news-a" href="{esc_url(링크)}" target="_blank">{본문}</a>'
    else:
        title_html = 본문
    return f'''
    <div class="news-item">
      <span class="news-rank">{idx}</span>
      <div class="news-body">
        <p class="news-title">{title_html}</p>
        <p class="news-insight">{요약}</p>
      </div>
    </div>'''


def news_title(핵심뉴스):
    """섹션 제목. 개수가 매일 5~8개로 달라지므로 제목도 따라 움직인다."""
    n = len(핵심뉴스 or [])
    return f"놓치기 쉬운 것들 {n}건" if n else "놓치기 쉬운 것들"



def build_news(핵심뉴스):
    """인기 뉴스 — 3개만 펼치고 나머지는 더보기.
    개수는 generate 단계에서 매일 5~8개 사이로 정해져 넘어온다.
    리포트 본문에서 이미 다룬 사안은 제외하고 고른 것들이다."""
    if not 핵심뉴스:
        return '<div class="pending">⏳ 네이버 증권 인기뉴스 수집 준비중</div>'
    앞3 = 핵심뉴스[:3]
    뒤 = 핵심뉴스[3:]
    앞HTML = "".join(one_news_item(i + 1, it) for i, it in enumerate(앞3))
    더보기 = ""
    if 뒤:
        뒤HTML = "".join(one_news_item(i + 4, it) for i, it in enumerate(뒤))
        더보기 = (f'<div class="hidden-block" id="moreNews">'
                f'<div class="news-wrap" style="border:none;box-shadow:none;margin:0">{뒤HTML}</div></div>'
                f'<button class="more-btn" onclick="toggleMore(\'moreNews\',this,\'▾ 뉴스 {len(뒤)}개 더보기\')">'
                f'▾ 뉴스 {len(뒤)}개 더보기</button>')
    return (f'<div class="news-wrap">{앞HTML}</div>{더보기}'
            '<p class="news-foot">※ 제목을 누르면 해당 기사 원문으로 이동합니다. '
            '위 코너에서 이미 다룬 사안은 제외하고 골랐습니다.</p>')


# ── 환율·유가·금리 카드 ──
# ── 프로의 시선 (3개 렌즈) ──
def build_insight(프로의시선):
    if not 프로의시선:
        return '<div class="pending">⏳ 조용한 강세 · 짖지 않은 개 · 다음 시나리오 — Claude 해석 연동 후 자동 생성</div>'
    렌즈들 = [
        ("조용한 강세", 프로의시선.get("조용한_강세", "")),
        ("짖지 않은 개", 프로의시선.get("짖지_않은_개", "")),
        ("다음 시나리오", 프로의시선.get("다음_시나리오", "")),
    ]
    rows = []
    for 이름, 내용 in 렌즈들:
        if not 내용:
            continue
        rows.append(f'''
    <div class="si-item"><span class="si-lens">{이름}</span><span>{내용}</span></div>''')
    if not rows:
        return '<div class="pending">⏳ 프로의 시선 — 데이터 부족</div>'
    return f'''
  <div class="silent-wrap">
    <p class="silent-head">🔍 모두가 지수를 볼 때, 저는 이 3가지를 봅니다</p>
    {"".join(rows)}
  </div>'''


# ── 마감 브리핑 (방송사별) ──
# ── 실제 강세 레이더 (오늘 신규 포착만 표시) ──
def build_radar(강세레이더, 설정=None):
    if not 강세레이더:
        return '<div class="pending">⏳ 실제 강세 레이더 — 데이터 수집 준비중</div>'
    설정 = (설정 or {}).get("강세", {})
    조건 = dev_note(
        f"시총 ≥ {설정.get('최소시총','?'):,}억 · 거래대금 ≥ {설정.get('최소거래대금','?'):,}억 · "
        f"상승 종목만 · 전일 대비 거래량 ≥ {설정.get('거래량배수','?')}배 │ "
        f"점수 = 회전율×{설정.get('회전비중','?')} + 상승률×{설정.get('상승비중','?')} "
        f"(각각 0~100 정규화) + 거래량 {설정.get('가점배수','?')}배↑ 시 +{설정.get('가점','?')}점 │ "
        f"추적 {설정.get('추적일','?')}거래일"
    ) if 설정 else ""
    신규 = 강세레이더.get("신규") or {}
    추적 = 강세레이더.get("추적") or []

    # ── 1단: 오늘 새로 포착 ──
    def 시장블록(시장, 목록):
        if not 목록:
            return f'<p class="rd-empty">{시장} — 오늘 새로 포착된 종목이 없습니다.</p>'

        def 행(rank, s):
            등락 = s.get("등락률") or 0
            폭발 = '<span class="rd-tag rd-boom">🔥 거래량 폭발</span>' if s.get("폭발") else ''
            재 = s.get("재점화")
            재HTML = f'<span class="rd-tag rd-re">🔄 {재}차 포착</span>' if 재 else ''
            return f"""
      <div class="rd-row">
        <span class="rd-rank">{rank}</span>
        <div class="rd-info">
          <p class="rd-name">{s['종목명']}{재HTML}{폭발}</p>
          <p class="rd-meta">회전율 {s.get('회전율','—')}% · 거래량 전일 <b>{s.get('배수','—')}배</b>
            · 거래대금 {_fmt_eok(s.get('거래대금'))} · 시총 {_fmt_eok(s.get('시총'))}</p>
        </div>
        <div class="rd-nums">
          <span class="rd-score">{s.get('강세점수','—')}</span>
          <span class="rd-chg up">+{등락:.2f}%</span>
        </div>
      </div>"""

        앞5 = "".join(행(i+1, s) for i, s in enumerate(목록[:5]))
        뒤 = 목록[5:10]
        더보기 = ""
        if 뒤:
            gid = f"radar{시장}"
            뒤HTML = "".join(행(i+6, s) for i, s in enumerate(뒤))
            더보기 = f"""
    <div class="hidden-block" id="{gid}">{뒤HTML}</div>
    <button class="more-btn" onclick="toggleMore('{gid}',this,'▾ {시장} 6~{5+len(뒤)}위 더보기')">▾ {시장} 6~{5+len(뒤)}위 더보기</button>"""
        return f"""
    <div class="rd-market">
      <p class="rd-mkt-name">📡 {시장}</p>
      {앞5}{더보기}
    </div>"""

    신규HTML = 시장블록("코스피", 신규.get("코스피", [])) + 시장블록("코스닥", 신규.get("코스닥", []))

    # ── (2단 '포착 이후 추적'은 화면에서 제거했다) ──
    #   collect_data.py는 계속 추적 데이터를 쌓는다. 화면에 안 보일 뿐,
    #   '🔄 N차 포착' 재점화 뱃지가 그 기록 위에서 돌아가기 때문이다.

    return f"""
  <div class="rd-box">
    <p class="rd-lead">💰 <b>돈도 몰리고 실제로 오른 곳</b>만 추립니다.
      시총 5,000억 이상 · 거래대금 500억 이상 · <b>전일 대비 거래량 2배 이상</b> 종목 중에서,
      회전율(거래대금÷시총)과 상승률을 <b>5:5</b>로 반영해 점수를 냈습니다.</p>
    {조건}
    {신규HTML}
    <p class="rd-foot">🔥 폭발 = 전일 대비 거래량 3배 이상 · 🔄 N차 포착 = 추적 중이던 종목의 재점화.
      점수는 관찰 참고용이며 매수 신호가 아닙니다.</p>
  </div>"""




# ── 5일 매집 레이더 (시총대비 + 아직 안 오른 매집) ──
def _acc_star_names(매집):
    """매집 레이더에서 '5일 TOP5 ∩ 20일 TOP5' 종목명만 뽑는다.

    ⚠️ 반드시 '화면에 실제로 뜨는 TOP5'끼리 비교해야 한다.
       조건을 통과한 후보 전체(수십 종목)끼리 비교하면 겹침이 부풀려진다
       (실측: 후보 70개 vs 50개를 그대로 비교하면 겹침 34개라는 과장된
       숫자가 나온 적이 있다 — 화면엔 각 5개씩만 보이는데도).
    """
    매집 = 매집 or {}
    def top5(리스트, 시장):
        후보 = [x for x in (리스트 or []) if x.get("시장") == 시장]
        후보 = sorted(후보, key=lambda x: x.get("시총대비") or 0, reverse=True)[:5]
        return {x["종목명"] for x in 후보}
    단기 = 매집.get("종목") or []
    중기 = 매집.get("중기종목") or []
    단기TOP = top5(단기, "코스피") | top5(단기, "코스닥")
    중기TOP = top5(중기, "코스피") | top5(중기, "코스닥")
    return 단기TOP & 중기TOP


def build_accumulation(매집, 설정=None):
    if not 매집:
        return '<div class="pending">⏳ 매집 레이더 — 데이터 수집 준비중</div>'
    종목 = 매집.get("종목") or []
    if not 종목:
        return '<div class="pending">오늘은 조건을 만족한 매집 종목이 없습니다.</div>'
    기간 = 매집.get("기간", 5)
    쌍최소 = 매집.get("쌍끌이최소", 3)
    단최소 = 매집.get("단독최소", 4)
    쌍수 = 매집.get("쌍끌이수", 0)

    cfg = (설정 or {}).get("매집", {})
    스캔 = cfg.get("스캔범위") or {}
    조건 = dev_note(
        f"스캔 = 시총 상위 코스피 {스캔.get('코스피','?')} + 코스닥 {스캔.get('코스닥','?')}종목 · "
        f"관찰 {cfg.get('기간','?')}거래일 │ "
        f"🤝쌍끌이 = 외국인·기관 <b>둘 다</b> {cfg.get('쌍끌이일수','?')}일↑ 순매수 & 각자 누적 + · "
        f"💼단독 = 한쪽만 {cfg.get('단독일수','?')}일↑<br>"
        f"조건 통과 종목 전부를 후보 풀에 담은 뒤 <b>코스피·코스닥으로 나눠</b> 각 시장에서 TOP5<br>"
        f"<b>시총대비</b> = 5일 누적 순매수 ÷ 시가총액 × 100 (내림차순 정렬)"
    ) if cfg else ""

    def 유형뱃지(t):
        if t == "쌍끌이":
            return '<span class="ac-tag ac-both">🤝 쌍끌이</span>'
        return f'<span class="ac-tag ac-solo">💼 {t}</span>'

    def 행(i, s, 값HTML, 부가=""):
        return f"""
        <div class="ac-row">
          <span class="ac-rank">{i}</span>
          <div class="ac-info">
            <p class="ac-name">{s['종목명']}{유형뱃지(s.get('유형',''))}</p>
            <p class="ac-meta">외 {s.get('외인일수',0)}일 · 기 {s.get('기관일수',0)}일
              · 시총 {_fmt_eok(s.get('시총'))}{부가}</p>
          </div>
          {값HTML}
        </div>"""

    # ── 시장별 시총 대비 TOP5 ──
    #   예전엔 '시총대비 / 매집갭' 두 랭킹이었는데, 매집갭은 해석 부담이 커서 뺐다.
    #   대신 같은 기준(시총대비)을 코스피·코스닥으로 나눠 비교 가능성을 높였다.
    def 시장랭킹(시장):
        목록 = [x for x in 종목 if x.get("시장") == 시장]
        목록 = sorted(목록, key=lambda x: x.get("시총대비", 0) or 0, reverse=True)[:5]
        if not 목록:
            return 0, f'<p class="rd-empty">{시장} — 오늘 조건을 만족한 종목이 없습니다.</p>'
        전체 = len([x for x in 종목 if x.get("시장") == 시장])
        행들 = "".join(
            행(i, s, f'<span class="ac-val">{s.get("시총대비","—")}%</span>',
              f' · 누적 +{_fmt_eok(s.get("합산"))}')
            for i, s in enumerate(목록, 1))
        return 전체, 행들

    코스피수, 코스피행 = 시장랭킹("코스피")
    코스닥수, 코스닥행 = 시장랭킹("코스닥")

    # ── 중기(20일) 매집 — 같은 데이터 응답에서 나온 긴 호흡 랭킹 ──
    중기 = 매집.get("중기종목") or []
    중기블록 = ""
    별명단 = _acc_star_names(매집)   # 5일 TOP5 ∩ 20일 TOP5 (화면 기준. 후보 전체 기준 아님)
    if 중기:
        중기간 = 매집.get("중기기간", 20)
        def 중기랭킹(시장):
            목록 = [x for x in 중기 if x.get("시장") == 시장]
            목록 = sorted(목록, key=lambda x: x.get("시총대비") or 0, reverse=True)[:5]
            if not 목록:
                return f'<p class="rd-empty">{시장} — 조건 만족 종목 없음</p>'
            return "".join(
                행(i, s, f'<span class="ac-val">{s.get("시총대비","—")}%</span>',
                  f' · 누적 +{_fmt_eok(s.get("합산"))}'
                  + ('<span class="ac-star2">⭐ 5일 랭킹에도 동시 등재</span>' if s["종목명"] in 별명단 else ""))
                for i, s in enumerate(목록, 1))
        중기블록 = f'''
    <div class="ac-long">
      <p class="ac-long-t">🏗️ 중기 매집 — 최근 {중기간}거래일, 더 긴 호흡의 돈</p>
      <p class="ac-long-s">5일이 "이번 주 신호"라면, {중기간}일은 "한 달째 이어지는 의지"입니다.
        🤝쌍끌이 = 둘 다 {매집.get("중기쌍끌이",12)}일↑ · 💼단독 = 한쪽 {매집.get("중기단독",14)}일↑ ·
        ⭐ = 5일 랭킹에도 동시 등재 (가장 강한 신호)</p>
      <div class="ac-two">
        <div class="ac-col"><p class="ac-col-t">📊 코스피 · {중기간}일</p>{중기랭킹("코스피")}</div>
        <div class="ac-col"><p class="ac-col-t">📊 코스닥 · {중기간}일</p>{중기랭킹("코스닥")}</div>
      </div>
    </div>'''

    보충 = (f'<p class="ac-note">※ 오늘 후보 풀 {len(종목)}종목 '
          f'(🤝쌍끌이 {쌍수} + 💼단독 {max(0,len(종목)-쌍수)}) — '
          f'코스피 {코스피수} · 코스닥 {코스닥수}. 각 시장에서 시총 대비 상위 5개입니다.</p>')

    return f"""
  <div class="rd-box">
    <p class="rd-lead">🐢 <b>하루 순매수는 우연이지만, 며칠 연속은 의지입니다.</b>
      조용히 돈이 쌓이는 종목을 코스피·코스닥에서 각각 찾습니다.
      (강세 레이더가 '터진 것'을 본다면, 여기는 '쌓이는 것'을 봅니다)<br>
      🤝 쌍끌이 = 외국인·기관이 <b>둘 다</b> {기간}일 중 {쌍최소}일 이상 순매수 ·
      💼 단독 = 한쪽만 {단최소}일 이상</p>
    {조건}
    <p class="ac-long-t" style="margin-top:.6rem">🔥 단기 매집 — 최근 {기간}거래일</p>
    <div class="ac-two">
      <div class="ac-col">
        <p class="ac-col-t">📊 코스피 · 시총 대비</p>
        <p class="ac-col-s">그 회사엔 얼마나 큰 돈인가</p>
        {코스피행}
      </div>
      <div class="ac-col">
        <p class="ac-col-t">📊 코스닥 · 시총 대비</p>
        <p class="ac-col-s">그 회사엔 얼마나 큰 돈인가</p>
        {코스닥행}
      </div>
    </div>
    {보충}
    {중기블록}
    <p class="rd-foot">💡 <b>순위가 높다고 "곧 오른다"는 뜻이 아닙니다.</b> 그 회사 규모에 비해 들어온 돈이
      컸다는 사실만 보여줄 뿐이며, 이유는 개별 확인이 필요합니다.
      시장을 나눈 이유는 시총 규모가 다른 코스피·코스닥을 한 줄로 세우면 늘 소형주만 올라오기 때문입니다.<br>
      ※ '기관'은 <b>기관계 합산</b>입니다. 증권사 자기매매(선물·ELS 헤지 등 방향성이 아닌 물량)가
      포함될 수 있습니다. 관찰 참고용이며 매수 신호가 아닙니다.</p>
  </div>"""


def _fmt_eok(억):
    """억원 숫자를 조/억으로 표기."""
    v = _to_float(억)
    if v is None:
        return "—"
    if abs(v) >= 10000:
        return f"{v/10000:.1f}조"
    return f"{v:,.0f}억"


def build_briefings(마감브리핑):
    if not 마감브리핑:
        return '<div class="pending">⏳ 오늘 마감 브리핑 영상을 찾지 못했습니다</div>'

    # 요약이 있는 것을 대표로 우선 선택
    요약있음 = [b for b in 마감브리핑 if b.get("summary")]
    대표 = 요약있음[0] if 요약있음 else 마감브리핑[0]
    나머지 = [b for b in 마감브리핑 if b is not 대표]

    대표HTML = f'''
    <div class="tv-lead">
      <span class="tv-lead-badge">⭐ 오늘의 대표 · {대표.get('채널','')}</span>
      <p class="tv-lead-ch"><span class="tv-dot"></span>{대표.get('채널','')}
        {f"· {대표.get('angle')}" if 대표.get('angle') else ''}</p>
      <p class="tv-title">{대표.get('제목','')}</p>
      <p class="tv-lead-body">{대표.get('summary','') or '요약 없음 — 원본 영상에서 확인하세요'}</p>
      <a class="tv-see" href="{esc_url(대표.get('링크'))}" target="_blank">영상 보기 ↗</a>
    </div>'''

    행들 = []
    for i, b in enumerate(나머지):
        요약 = b.get("summary", "") or "요약 없음 — 원본 영상에서 확인하세요"
        행들.append(f'''
      <div class="tv-row-wrap">
        <div class="tv-row tv-clickable" onclick="toggleTV('tvbody{i}',this)">
          <span class="tv-ch">{b.get('채널','')}</span>
          {f'<span class="tv-angle">{b.get("angle")}</span>' if b.get('angle') else ''}
          <span class="tv-see-sm">보기 ▾</span>
        </div>
        <div class="tv-body-hidden" id="tvbody{i}">
          <p class="tv-title">{b.get('제목','')}</p>
          <p class="tv-sum">{요약}</p>
          <a class="tv-link-sm" href="{esc_url(b.get('링크'))}" target="_blank">영상 보기 ↗</a>
        </div>
      </div>''')

    나머지HTML = f'<div class="tv-others">{"".join(행들)}</div>' if 행들 else ''

    return f'''
  <div class="tv-wrap">{대표HTML}{나머지HTML}
    <p class="tv-note">📡 각 채널의 관점을 요약한 것으로, 원문을 그대로 옮기지 않았습니다. 자세한 내용은 각 영상 링크에서 확인하세요.</p>
  </div>'''


def build_story_bridge():
    """'지금까지의 줄거리' — 오늘을 최근 며칠 흐름과 잇는 한 줄 서사(연속극).

    채점표·프로의판단과 정보가 겹치지 않게, 여기서는 '흐름의 연속성'만 짧게 짚는다.
    기준: 어제(1일) + 최대 5일. 20/60일은 '이야기'가 아니라 통계라 여기선 안 쓴다.
    전부 규칙 기반(코드) — flow_history를 읽어 가장 강한 서사 한 줄을 만든다.
    """
    try:
        h = load_json("flow_history.json") or []
        h = [r for r in h if isinstance(r, dict) and r.get("실탄") is not None]
    except Exception:
        return ""
    if len(h) < 3:
        return ""
    오늘, 어제 = h[-1], h[-2]

    def 연속(key):
        n, sign = 0, None
        for r in reversed(h):
            v = r.get(key)
            if v is None or v == 0:
                break
            s = v >= 0
            if sign is None:
                sign = s
            if s != sign:
                break
            n += 1
        return n, ("매수" if sign else "매도")

    # 각 조각은 '연결형'(~며)으로 쓰고, 마지막에 종결한다.
    조각 = []

    # ① 어제→오늘 방향 전환 (가장 극적)
    실오, 실어 = 오늘.get("실탄", 0), 어제.get("실탄", 0)
    전환 = (실어 >= 0) != (실오 >= 0)
    if 전환:
        조각.append(f'어제 <b>{_flow_amt(실어)}</b>였던 실탄이 오늘 <b>{_flow_amt(실오)}</b>로 '
                    f'<b class="st-turn">하루 만에 방향을 틀었으며</b>')
    else:
        # ② 연속 흐름 (며칠째)
        외n, 외방 = 연속("외현")
        기n, 기방 = 연속("기관")
        best = max((외n, "외국인", 외방), (기n, "기관", 기방))
        if best[0] >= 3:
            조각.append(f'<b>{best[1]}</b>이 <b>{best[0]}일째</b> {best[2]}를 이어가며')

    # ③ 5일 내 바닥 반등 (희망 서사)
    누적, acc = [], 0
    for r in h:
        acc += r.get("실탄", 0)
        누적.append(acc)
    저점i = 누적.index(min(누적))
    흐른 = len(h) - 1 - 저점i
    바닥조각 = None
    if 0 < 흐른 <= 8 and 누적[저점i] < 0 <= 누적[-1]:
        from datetime import datetime
        try:
            d = datetime.strptime(h[저점i]["날짜"], "%Y%m%d")
            바닥조각 = f'{d.month}/{d.day} 바닥을 찍은 실탄이 <b>{흐른}일째 쌓이는 중</b>'
        except Exception:
            pass

    # 조립: 연결형 조각(들) + 종결형(바닥조각 우선, 없으면 연결형을 종결로)
    앞 = " ".join(조각)
    if 바닥조각:
        본문 = (앞 + " " if 앞 else "") + 바닥조각 + "입니다"
    elif 앞:
        # 연결형 어미(~며/~으며)를 종결로 교체
        본문 = 앞.rstrip()
        for 연결, 종결 in (("이어가며", "이어가고 있습니다"),
                          ("틀었으며", "틀었습니다")):
            if 본문.endswith(연결):
                본문 = 본문[:-len(연결)] + 종결
                break
        else:
            본문 += "입니다"
    else:
        return ""
    return (f'<div class="story-bridge"><span class="st-ic">🎬</span>'
            f'<span class="st-txt"><b>지금까지의 줄거리</b> — {본문}.</span></div>')


# ── 어제의 채점표 ──
def build_scorecard(채점표, 어제날짜=""):
    if not 채점표:
        return ""  # 첫 발행이면 아예 섹션을 숨긴다
    rows = []
    for it in 채점표:
        결과 = it.get("결과", "△")
        cls = {"○": "sc-o", "×": "sc-x"}.get(결과, "sc-t")
        rows.append(f'''
    <div class="score-row">
      <span class="score-mark {cls}">{결과}</span>
      <div class="score-body">
        <p class="score-item">{it.get('항목','')}</p>
        <p class="score-why">{it.get('근거','')}</p>
      </div>
    </div>''')
    맞은수 = sum(1 for it in 채점표 if it.get("결과") == "○")
    return f'''
  <div class="score-box">
    <p class="score-head">📋 어제 예고한 관전포인트를 오늘 결과로 채점했습니다
      <span class="score-tally">{맞은수} / {len(채점표)} 적중</span></p>
    {"".join(rows)}
    <p class="score-foot">※ 예보 → 채점 → 새 예보. 매일 이어집니다. 채점은 사실 확인이지 수익률 평가가 아닙니다.</p>
  </div>'''


def _flow_highlight(key, days_max=20):
    """수급 한 주체의 '가장 눈에 띄는 특징'을 최대 20일 범위에서 자동으로 고른다.

    항상 20일 고정이 아니라, 최근 5/10/20일 관점을 모두 계산해 가장 강한 신호 하나만
    문장으로 돌려준다. 우선순위: 방향 전환(3) > 기간 내 최대(2) > 연속·순위(1).
    전부 규칙 기반(코드) — flow_history.json의 외현/기관 컬럼을 읽는다.
    """
    try:
        h = load_json("flow_history.json") or []
        h = [r for r in h if isinstance(r, dict) and r.get(key) is not None][-days_max:]
    except Exception:
        return None
    N = len(h)
    if N < 2:
        return None
    오늘 = h[-1].get(key)
    if 오늘 is None:
        return None
    방향 = "매수" if 오늘 >= 0 else "매도"
    후보 = []

    # ① 최근 5일 vs 이전 5일 방향 전환 (가장 중요)
    if N >= 10:
        최근5 = sum((r.get(key) or 0) for r in h[-5:])
        이전5 = sum((r.get(key) or 0) for r in h[-10:-5])
        if 이전5 <= 0 < 최근5:
            후보.append((3, '최근 5일 매도 <span class="nw">→매수 전환</span>'))
        elif 최근5 <= 0 < 이전5:
            후보.append((3, '최근 5일 매수 <span class="nw">→매도 전환</span>'))

    # ② 최근 5/10/20일 중 최대 규모 (짧은 기간 우선)
    for days in (5, 10, 20):
        if N >= days:
            창 = [r.get(key) for r in h[-days:] if r.get(key) is not None]
            같은방향 = [v for v in 창 if (v >= 0) == (오늘 >= 0)]
            if 같은방향 and 오늘 == max(같은방향, key=abs):
                후보.append((2, f"{days}일 중 최대 {방향}"))
                break

    # ③ 연속 일수
    n, sign = 0, None
    for r in reversed(h):
        v = r.get(key)
        if v is None or v == 0:
            break
        s = v >= 0
        if sign is None:
            sign = s
        if s != sign:
            break
        n += 1
    if n >= 3:
        후보.append((1, f"{n}일 연속 {'매수' if sign else '매도'}"))

    # ④ 순위 (상위 3위)
    같은방향전체 = sorted(
        [r.get(key) for r in h if r.get(key) is not None and (r.get(key) >= 0) == (오늘 >= 0)],
        key=abs, reverse=True)
    if 오늘 in 같은방향전체:
        순 = 같은방향전체.index(오늘) + 1
        if 순 <= 3:
            후보.append((1, f"{N}일 중 {방향} {순}위"))

    if not 후보:
        return "순매수" if 오늘 >= 0 else "순매도"
    후보.sort(key=lambda x: x[0], reverse=True)
    return 후보[0][1]


def _load_market_history():
    try:
        with open("market_history.json", encoding="utf-8") as f:
            rows = (json.load(f).get("일별") or [])
        return [r for r in rows if r.get("코스피") is not None]
    except Exception:
        return []


def _mh_rank(rows, key, val):
    """오늘이 최근 20행 안에서 '같은 방향으로' 몇 번째로 큰가.
    매수일이면 매수 규모 순위, 매도일이면 매도 규모 순위 — 그래야 문장이 자연스럽다.
    ("11일 중 8위로 판 날" 같은 어색함 방지). 6행 미만이면 None."""
    vals = [r.get(key) for r in rows[-20:] if r.get(key) is not None]
    if val is None or len(vals) < 6:
        return None
    if val >= 0:
        동방향 = sorted([v for v in vals if v >= 0], reverse=True)
    else:
        동방향 = sorted([v for v in vals if v < 0])
    # ⚠️ val이 rows에 없을 수 있다(오늘 행이 아직 안 쌓였거나 다른 소스에서 온 값).
    #    그대로 index()를 부르면 ValueError로 리포트 전체가 죽는다 → 순위로 계산한다.
    if val not in 동방향:
        순 = sum(1 for v in 동방향 if (v > val if val >= 0 else v < val)) + 1
    else:
        순 = 동방향.index(val) + 1
    if 순 <= 3:
        return f"{len(vals)}일 중 {'매수' if val >= 0 else '매도'} {순}위"
    return None      # 상위 3위 안일 때만 배지로 보여줄 가치가 있다


def _mh_streak(rows, key):
    n, sign = 0, None
    for r in reversed(rows):
        v = r.get(key)
        if v is None or v == 0:
            break
        s = v > 0
        if sign is None:
            sign = s
        if s != sign:
            break
        n += 1
    if n < 2:
        return None
    return f"{n}일 연속 {'매수' if sign else '매도'}"


# 구형 기기·카톡에서 □(두부)로 깨지는 최신 이모지 → 널리 지원되는 것으로 치환.
# 프롬프트로 막아도 이미 생성된 옛 리포트엔 남아 있으므로, 화면 그리는 마지막 단계에서
# 코드가 한 번 더 강제한다(숫자를 규칙으로 막는 것과 같은 원리 — 표현도 규칙으로 방어).
# 매핑 대상: Emoji 13.1~15.x 계열 중 감정 코너에 쓰일 법한 것들.
_EMOJI_SAFE = {
    "🫠": "😮\u200d💨",  # melting face → 한숨
    "🫥": "😶",          # dotted line face
    "🫡": "🫡",          # (경례 — 유지하되 필요시 😐)
    "🫨": "😳",          # shaking face
    "🫤": "😕",          # diagonal mouth
    "🥹": "🥲",          # holding back tears
    "🫢": "😮",          # face with peeking eye
    "🫣": "🙈",          # face with peeking eye variant
}
# 경례는 지원 폭이 애매해서 감정 코너에선 중립으로 낮춘다
_EMOJI_SAFE["🫡"] = "😐"


def safe_emoji(s):
    """문자열 안의 '깨질 수 있는 최신 이모지'를 안전한 것으로 바꾼다."""
    if not s:
        return s
    for bad, good in _EMOJI_SAFE.items():
        if bad in s:
            s = s.replace(bad, good)
    return s


# ── 지수 헤더 스타일 선택 ──
#   핵심편 맨 위 헤더의 시각 스타일. 아래 하나만 바꾸면 전체가 바뀐다.
#   "BC"=막대+성격 · "F"=도넛 게이지 · "G"=카드 분할 · "H"=타임라인 · "I"=히트 스트립
HEADER_STYLE = "BC"


# ── 맨 앞 아이콘 스타일 ──
#   "ring"=링+화살표 · "gauge"=반원 게이지 · "light"=신호등 3점 · "shield"=방패
#   "arrow"=큰 화살표 · "badge"=각진 배지(관제지수) · "candle"=미니 캔들
#   "bar"=세로바 · "round"=라운드 사각 이모지
ICON_STYLE = "light"


def _head_icon(코등, 링색, 이모, 관제점수=None, 관제구간=None, 태그색=None):
    """핵심편 맨 앞 성격 아이콘 — ICON_STYLE 상수로 9종 중 하나."""
    st = ICON_STYLE
    화살표 = "↗" if (코등 or 0) > 0 else "↘" if (코등 or 0) < 0 else "→"

    if st == "ring":
        return (f'<div class="hi-ring" style="border-color:{링색};color:{링색}">{화살표}</div>')

    if st == "gauge":
        frac = min(abs(코등 or 0) / 4.0, 1.0)
        dash = 55 * frac
        return (f'<div class="hi-gauge"><svg width="46" height="46" style="transform:rotate(135deg)">'
                f'<circle cx="23" cy="23" r="18" fill="none" stroke="rgba(255,255,255,.1)" stroke-width="5" stroke-dasharray="85 200"/>'
                f'<circle cx="23" cy="23" r="18" fill="none" stroke="{링색}" stroke-width="5" stroke-linecap="round" stroke-dasharray="{dash:.0f} 200"/></svg>'
                f'<span class="hi-gauge-c">{이모}</span></div>')

    if st == "light":
        # 신호등 본능: 초록=좋음/안전 · 노랑=주의 · 빨강=위험/멈춤
        #   조합태그 기준 — 지수형매수(good)=초록불 / 종목장세·지수만방어(warn)=노란불
        #   / 지수형매도(info)=빨간불. 태그 없으면 지수 방향으로 폴백.
        GRN, YEL, RED = "#4ade80", "#e0c060", "#ff5a4a"
        if 태그색 == "good":
            켜 = "green"
        elif 태그색 == "info":
            켜 = "red"
        elif 태그색 == "warn":
            켜 = "yellow"
        else:
            켜 = ("green" if (코등 or 0) > 0.3 else "red" if (코등 or 0) < -0.3 else "yellow")
        def dot(pos, color):
            on = (켜 == pos)
            bg = color if on else "#333"
            cls = "hi-dot on" if on else "hi-dot"
            style = f'background:{bg};--gc:{color}' if on else f'background:{bg}'
            return f'<div class="{cls}" style="{style}"></div>'
        # 위→아래: 초록 · 황색 · 적색
        return ('<div class="hi-light">'
                + dot("green", GRN) + dot("yellow", YEL) + dot("red", RED)
                + '</div>')

    if st == "shield":
        return (f'<div class="hi-shield"><svg width="42" height="42" viewBox="0 0 24 24" fill="none">'
                f'<path d="M12 2 L20 5 V11 C20 16 16 20 12 22 C8 20 4 16 4 11 V5 Z" '
                f'fill="{링색}22" stroke="{링색}" stroke-width="1.6"/>'
                f'<text x="12" y="15" font-size="9" fill="{링색}" text-anchor="middle" font-weight="900">관</text></svg></div>')

    if st == "arrow":
        return (f'<div class="hi-arrow" style="color:{링색}">{화살표}</div>')

    if st == "badge":
        점 = 관제점수 if 관제점수 is not None else "—"
        구 = 관제구간 or ""
        return (f'<div class="hi-badge" style="background:linear-gradient(135deg,{링색},{링색}cc)">'
                f'<span class="hi-badge-n">{점}</span><span class="hi-badge-s">{구}</span></div>')

    if st == "candle":
        return ('<div class="hi-candle">'
                '<div style="height:22px;background:#ff6b4a"></div>'
                '<div style="height:36px;background:#e0c060"></div>'
                '<div style="height:16px;background:#5b9bff"></div></div>')

    if st == "bar":
        return (f'<div class="hi-bar" style="background:linear-gradient(180deg,{링색},{링색}bb)"></div>')

    if st == "round":
        return (f'<div class="hi-round" style="background:{링색}26;border-color:{링색}66">{이모}</div>')

    # 기본: 링
    return (f'<div class="hi-ring" style="border-color:{링색};color:{링색}">{화살표}</div>')



def _header_data(지수수급, 파생, 코수):
    """헤더 5종이 공통으로 쓰는 값을 한 번에 계산한다(코드 계산 · 항상 최신)."""
    지 = (지수수급 or {}).get("지수") or {}
    파생 = 파생 or {}
    코수 = 코수 or {}

    def f0(v):
        try: return float(str(v).replace(",", ""))
        except (TypeError, ValueError): return None

    def one(key):
        o = 지.get(key) or {}
        등 = f0(o.get("등락률"))
        cls = "flat" if 등 is None else ("up" if 등 >= 0 else "down")
        부호 = "+" if (등 or 0) >= 0 and 등 is not None else ""
        등문 = "—" if 등 is None else f"{부호}{등:.2f}%"
        return {"종가": o.get("종가") or "—", "등": 등, "cls": cls, "등문": 등문}

    코 = one("코스피"); 닥 = one("코스닥")

    외 = f0(코수.get("외국인")); 기 = f0(코수.get("기관계"))
    실탄 = (외 + 기) if (외 is not None and 기 is not None) else None
    비차익 = f0((파생.get("프로그램") or {}).get("비차익")) or f0(파생.get("비차익"))
    태그 = combo_tag(실탄, 비차익) if (실탄 is not None and 비차익 is not None) else None

    if 태그:
        이모 = 태그[1].split()[0] if 태그[1][0] in "🔴🟠🟡🔵" else "🟡"
        이름 = 태그[1].split(maxsplit=1)[-1] if " " in 태그[1] else 태그[1]
        성격부제 = 태그[2]
    else:
        코등 = 코["등"] or 0
        이름 = ("함께 오른 하루" if 코등 > 0 else "함께 내린 하루" if 코등 < 0 else "숨 고른 하루")
        이모 = ("🔴" if 코등 > 0 else "🔵" if 코등 < 0 else "⚪")
        성격부제 = "코스피·코스닥 지수 흐름 요약"

    # 수급 특징 — 최대 20일 범위에서 '가장 눈에 띄는 신호' 자동 선택(코드 계산).
    #   flow_history의 외현/기관을 읽어, 전환/최대/연속/순위 중 강한 것 하나를 문장으로.
    외배지 = _flow_highlight("외현") if 외 is not None else "&nbsp;"
    기배지 = _flow_highlight("기관") if 기 is not None else "&nbsp;"

    return {"코": 코, "닥": 닥, "실탄": 실탄, "외인": 외, "기관": 기,
            "외배지": 외배지, "기배지": 기배지,
            "이모": 이모, "성격이름": 이름, "성격부제": 성격부제, "태그색": (태그[0] if 태그 else None)}


def _flow_line(실탄):
    if 실탄 is None:
        return "", "flat"
    cls = "up" if 실탄 >= 0 else "down"
    word = "순매수" if 실탄 >= 0 else "순매도"
    return f"{_flow_amt(실탄)} {word}", cls


def build_index_header(지수수급, 파생, 코수, style=None, 관제=None):
    """핵심편 최상단 지수 헤더 — style 상수로 5가지 레이아웃 중 하나를 그린다."""
    style = style or HEADER_STYLE
    d = _header_data(지수수급, 파생, 코수)
    코, 닥 = d["코"], d["닥"]
    실탄문, 실탄cls = _flow_line(d["실탄"])

    def barfill(cls, 등):
        w = 0.0 if 등 is None else min(abs(등) / 4.0, 1.0) * 50.0
        색 = ("linear-gradient(90deg,#ff6b4a,#ff9a80)" if cls == "up"
              else "linear-gradient(270deg,#5b9bff,#2E6BD6)" if cls == "down"
              else "rgba(255,255,255,.2)")
        side = "left" if (등 or 0) >= 0 else "right"
        return f'{side}:50%;width:{w:.1f}%;background:{색}'

    # ── BC · 막대 + 성격 (지수 2줄 + 수급 2줄) ──
    #   색 규칙 (2026-08-18 개정):
    #     지수 = 진한 빨강/파랑(#c1432b / #2e6bd6)
    #     수급 = 밝은 빨강/파랑(#ff6b4a / #5b9bff)
    #   ⚠️ 예전엔 수급을 초록/보라로 갈랐는데, 그러면 같은 리포트 안에서
    #      "초록=샀다"와 "빨강=올랐다"가 동시에 돌아 뜻이 두 개가 됐다.
    #      이제 **빨강 계열=올랐다/샀다**로 뜻을 하나로 통일하고,
    #      진하기(지수) vs 밝기(수급)로 "무엇에 대한 얘기인가"를 구분한다.
    #   맨 앞 성격은 '링+화살표'(지수 방향까지 표현).
    #   수급 밑 작은 글씨엔 '연속·순위' 배지, 그 아래 60일 누적을 붙인다.
    #   스케일: 지수 ±4% / 수급 ±3조. 단위가 다르므로 각자 기준(정직).
    if style == "BC":
        def row(nm, o):
            return (f'<div class="ix-bar-row"><span class="ix-bn">{nm}</span>'
                    f'<div class="ix-bt"><span class="ix-bz"></span>'
                    f'<div class="ix-bf" style="{barfill(o["cls"],o["등"])}"></div></div>'
                    f'<span class="ix-bv {o["cls"]}">{o["등문"]}<small>{o["종가"]}</small></span></div>')

        def flow_row(nm, v, 배지):
            # v: 억원. 매수(+)=밝은 빨강, 매도(-)=밝은 파랑. ±3조(30,000억)를 최대폭으로.
            if v is None:
                return (f'<div class="ix-bar-row"><span class="ix-bn">{nm}</span>'
                        f'<div class="ix-bt"><span class="ix-bz"></span></div>'
                        f'<span class="ix-bv flat">—<small>&nbsp;</small></span></div>')
            매수 = v >= 0
            w = min(abs(v) / 30000.0, 1.0) * 50.0
            색 = ("linear-gradient(90deg,#ff6b4a,#c1432b)" if 매수
                  else "linear-gradient(270deg,#5b9bff,#2e6bd6)")
            side = "left" if 매수 else "right"
            vcls = "buy" if 매수 else "sellv"
            return (f'<div class="ix-bar-row"><span class="ix-bn">{nm}</span>'
                    f'<div class="ix-bt"><span class="ix-bz"></span>'
                    f'<div class="ix-bf" style="{side}:50%;width:{w:.1f}%;background:{색}"></div></div>'
                    f'<span class="ix-bv {vcls}">{_flow_amt(v)}<small>{배지}</small></span></div>')

        수급블록 = (f'<div class="ix-div"></div><p class="ix-grouplbl">수급 (±3조 · 매수 빨강 / 매도 파랑)</p>'
                  f'{flow_row("외국인", d["외인"], d["외배지"])}{flow_row("기관", d["기관"], d["기배지"])}'
                  f'<div class="ix-scale"><span>-3조</span><span>0</span><span>+3조</span></div>'
                  ) if (d["외인"] is not None or d["기관"] is not None) else ""

        # 맨 앞 '링 + 화살표' — 코스피 방향으로 상승↗/하락↘, 색은 성격/지수 기준
        코등 = 코["등"] or 0
        링색 = {"good": "#ff6b4a", "warn": "#e0c060", "info": "#5b9bff"}.get(d.get("태그색"),
                "#ff6b4a" if 코등 > 0 else "#5b9bff" if 코등 < 0 else "#9aa0a8")
        _관 = 관제 or {}
        아이콘HTML = _head_icon(코등, 링색, d["이모"],
                             관제점수=_관.get("점수"), 관제구간=_관.get("구간"),
                             태그색=d.get("태그색"))

        return (f'<div class="ix-head"><div class="ix-mood">{아이콘HTML}'
                f'<div class="ix-mood-txt"><p class="ix-mood-t">오늘은 <span class="yl">{d["성격이름"]}</span></p>'
                f'<p class="ix-mood-s">{d["성격부제"]}</p></div></div>'
                f'<div class="ix-bars"><p class="ix-grouplbl">지수 (±4%)</p>'
                f'{row("코스피",코)}{row("코스닥",닥)}'
                f'<div class="ix-scale"><span>-4%</span><span>0</span><span>+4%</span></div>'
                f'{수급블록}</div></div>')

    # ── F · 도넛 게이지 ──
    if style == "F":
        def ring(nm, o):
            등 = o["등"] or 0
            frac = min(abs(등) / 4.0, 1.0)
            circ = 239.0
            off = circ * (1 - frac)
            stroke = "#ff6b4a" if o["cls"] == "up" else "#5b9bff" if o["cls"] == "down" else "#888"
            return (f'<div class="f-gauge"><div class="f-ring">'
                    f'<svg width="88" height="88"><circle cx="44" cy="44" r="38" fill="none" stroke="rgba(255,255,255,.08)" stroke-width="8"/>'
                    f'<circle cx="44" cy="44" r="38" fill="none" stroke="{stroke}" stroke-width="8" stroke-linecap="round" '
                    f'stroke-dasharray="{circ:.0f}" stroke-dashoffset="{off:.0f}"/></svg>'
                    f'<div class="f-ring-txt"><span class="f-pct {o["cls"]}">{o["등문"]}</span></div></div>'
                    f'<div class="f-nm">{nm}</div><div class="f-close">{o["종가"]}</div></div>')
        moodline = f'{d["이모"]} {d["성격이름"]}' + (f' · 외인+기관 {실탄문}' if 실탄문 else '')
        return (f'<div class="ix-head"><div class="f-wrap">{ring("코스피",코)}{ring("코스닥",닥)}</div>'
                f'<div class="f-mood yl">{moodline}</div></div>')

    # ── G · 카드 분할 ──
    if style == "G":
        return (f'<div class="ix-head"><div class="g-grid">'
                f'<div class="g-main"><span class="k">KOSPI</span>'
                f'<span class="v {코["cls"]}">{코["종가"]}</span>'
                f'<span class="c {코["cls"]}">▲ {코["등문"]}</span>'
                f'<span class="g-tag">오늘의 주인공</span></div>'
                f'<div class="g-sub"><p class="k">KOSDAQ</p><p class="v {닥["cls"]}">{닥["종가"]} '
                f'<span style="font-size:11px">{닥["등문"]}</span></p></div>'
                f'<div class="g-sub"><p class="k">외인+기관</p><p class="v {실탄cls}">{실탄문 or "—"}</p></div>'
                f'</div><p class="g-mood">{d["이모"]} <b class="yl">{d["성격이름"]}</b> — {d["성격부제"]}</p></div>')

    # ── H · 타임라인 내러티브 ──
    if style == "H":
        점색 = "#ff6b4a" if 코["cls"] == "up" else "#5b9bff" if 코["cls"] == "down" else "#888"
        flowdot = ('<div class="h-item"><span class="h-dot" style="background:#ff6b4a"></span>'
                   f'<div><p class="h-txt"><b>외국인·기관 {실탄문}</b></p>'
                   f'<p class="h-sub">큰손이 어느 쪽에 섰는지 보여주는 신호입니다</p></div></div>') if 실탄문 else ""
        return (f'<div class="ix-head">'
                f'<div class="h-item"><span class="h-dot" style="background:{점색}"></span>'
                f'<div><p class="h-txt"><b class="{코["cls"]}">코스피 {코["등문"]}</b> · 코스닥 {닥["등문"]}</p>'
                f'<p class="h-sub">코스피 {코["종가"]} · 코스닥 {닥["종가"]}</p></div></div>'
                f'{flowdot}'
                f'<div class="h-item"><span class="h-dot" style="background:#e0c060"></span>'
                f'<div><p class="h-txt"><b class="yl">{d["이모"]} {d["성격이름"]}</b></p>'
                f'<p class="h-sub">{d["성격부제"]}</p></div></div></div>')

    # ── I · 히트 스트립 ──
    if style == "I":
        def seg(nm, val, sub, grad):
            return (f'<div class="i-seg" style="background:{grad}">'
                    f'<span class="k">{nm}</span><span class="v">{val}</span><span class="c">{sub}</span></div>')
        코grad = "linear-gradient(135deg,#c1432b,#ff6b4a)" if 코["cls"]=="up" else "linear-gradient(135deg,#2E6BD6,#5b9bff)"
        닥grad = "linear-gradient(135deg,#8a5a2b,#c99a4a)"
        segs = seg("코스피", 코["종가"], 코["등문"], 코grad) + seg("코스닥", 닥["종가"], 닥["등문"], 닥grad)
        if 실탄문:
            segs += seg("외인+기관", 실탄문.split()[0], 실탄문.split()[-1], "linear-gradient(135deg,#2a6b4a,#3aa06a)")
        return (f'<div class="ix-head"><p class="i-head">{d["이모"]} 오늘은 '
                f'<span class="hl">{d["성격이름"]}</span></p>'
                f'<div class="i-strip">{segs}</div></div>')

    return ""   # 알 수 없는 스타일


# ============================================================
# 계좌 좌표 격자 · 사건명 · 오늘 딱 N개     [v-k 신규]
# ============================================================

GRID_최소종목 = 3


#  등락 강도 5단계 색 램프 (v-k5)
#  ⚠️ 예전 방식(같은 빨강의 투명도만 조절)은 "전부 오른 날"에 거의 구분이 안 됐다.
#     같은 색을 흐리게/진하게만 하면 사람 눈은 인접 두 단계를 못 가른다.
#     그래서 밝기와 채도를 함께 움직이는 **실색 5단계**로 바꿨다.
#     배경(#161a22)에 미리 섞어둔 값이라 겹침·투명도 문제가 없다.
#  ⚠️ v-k9: 색상(Hue)까지 돌리니 너무 요란했다 → 붉은 계열로 복귀.
#     대신 명도 폭을 최대로 벌린다: 거의 검정에 가까운 자주부터
#     프로젝트 표준 상승색(#ff6b4a)까지 5단계.
#     같은 계열이라도 단계 간 밝기 차를 크게 두면 구분이 된다.
#     하락도 같은 원리로 남색 → 표준 하락색(#5b9bff).
#  ⚠️ v-l4: "색이 제각각이라 혼란스럽다"는 지적을 받고 다시 정리했다.
#     원인은 두 가지였다.
#       ① 글자색이 칸마다 달랐다(밝은 칸은 검정, 어두운 칸은 흰색) → 표가 얼룩덜룩
#       ② 램프 끝이 너무 밝아 '순한 상승'과 '강한 상승'이 다른 색처럼 보였다
#     그래서 **한 계열 안에서 밝기만 단조 증가**하도록 다시 잡고,
#     글자는 전 칸 흰색으로 통일했다(밝기 대비는 배경이 담당).
GRID_RAMP_UP = ["#2b2f37", "#4d2529", "#7a2d2c", "#ad3730", "#e04a35"]   # 0→강
GRID_RAMP_DN = ["#2b2f37", "#22344a", "#2a4f78", "#3568a8", "#4a8fe0"]
GRID_STEPS = (0.5, 1.0, 2.0, 3.0)     # 이 값들을 경계로 5칸


def _grid_step(v):
    """등락률 → 0~4 강도 단계."""
    a = abs(v)
    for i, t in enumerate(GRID_STEPS):
        if a < t:
            return i
    return 4


def _grid_cell_color(v):
    """등락률 → 배경색. 지수 관례(빨강=상승/파랑=하락)를 따른다.
    색만으로 구분하지 않도록 숫자를 항상 함께 쓰고, 강한 칸일수록 글자도 밝아진다."""
    if v is None:
        return "transparent"
    return (GRID_RAMP_UP if v >= 0 else GRID_RAMP_DN)[_grid_step(v)]


def _grid_text_style(v):
    """강도에 따라 글자색을 바꾼다.

    ⚠️ 글자색은 **전 칸 동일**하게 둔다. 칸마다 글자색이 바뀌면
       표 전체가 얼룩덜룩해져서 "어디가 강한가"가 오히려 안 보인다.
       강약은 배경 밝기 하나로만 말하게 한다(정보 채널을 하나로).
    """
    if v is None:
        return "color:#6b7280;font-weight:500"
    return "color:#ffffff;font-weight:800"


def _load_strata_history(days=20):
    """strata_history.json에서 최근 N일치를 읽는다(스파크라인 원료)."""
    try:
        with open(apath("strata_history.json"), encoding="utf-8") as f:
            rows = json.load(f) or []
    except Exception:
        return []
    rows = [r for r in rows if isinstance(r, dict) and r.get("날짜")]
    rows.sort(key=lambda r: r.get("날짜", ""))
    return rows[-days:]


def _spark_svg(vals, w=120, h=22):
    """숫자 목록 → 아주 작은 꺾은선 SVG. 값이 3개 미만이면 빈 문자열."""
    vs = [v for v in vals if isinstance(v, (int, float))]
    if len(vs) < 3:
        return ""
    lo, hi = min(vs), max(vs)
    rng = (hi - lo) or 1.0
    step = w / max(1, len(vs) - 1)
    pts = " ".join(f"{i*step:.1f},{h - 3 - (v-lo)/rng*(h-6):.1f}" for i, v in enumerate(vs))
    끝색 = "#e24b4a" if vs[-1] >= 0 else "#378add"
    return (f'<svg width="{w}" height="{h}" viewBox="0 0 {w} {h}" style="vertical-align:middle">'
            f'<polyline points="{pts}" fill="none" stroke="{끝색}" stroke-width="1.6" '
            f'stroke-linejoin="round" opacity=".85"/></svg>')


_GRID_SEQ = [0]   # 같은 표가 여러 번 그려질 때 id가 겹치지 않게 하는 일련번호


def build_account_grid(격자, 주도섹터=None):
    # 다리 ② — 오늘 '뜨는 현장'이 속한 구역 줄에 불을 붙인다.
    #   격자만 보고도 "내 구역에 오늘 불이 났나"를 알 수 있게 한다.
    _GRID_SEQ[0] += 1
    _pfx = f"g{_GRID_SEQ[0]}"      # 이 표 전용 id 접두어
    불난구역 = {}
    for s in (주도섹터 or []):
        슬 = s.get("계좌구역") or grid_slot_of(s.get("테마명"))
        if 슬:
            불난구역.setdefault(슬, []).append(
                re.sub(r"[（(].*", "", str(s.get("테마명") or "")).strip())
    """계좌 좌표 격자 — 테마(세로) × 시총 3단계(가로).

    "코스피는 올랐는데 내 종목은 왜 안 올랐나"의 답을 5초에 준다.
    가로로 읽으면 같은 테마 안의 대형·소형 격차, 세로로 읽으면 오늘의 주인공.
    """
    if not 격자 or not 격자.get("행"):
        return ""

    기준 = 격자.get("기준") or {}
    행들 = 격자.get("행") or []
    크기 = 격자.get("크기전체") or {}
    프리미엄 = 격자.get("크기프리미엄")

    # 열 폭 고정 — 테마 칸을 넉넉히 주고 나머지를 균등 분배해야 모바일에서 안 깨진다.
    콜 = ('<colgroup><col style="width:33%"><col style="width:16.75%">'
          '<col style="width:16.75%"><col style="width:16.75%"><col style="width:16.75%"></colgroup>')

    def _짧은기준(층):
        """'301위 이하' 같은 긴 라벨은 좁은 칸에서 옆 칸과 겹친다 → 숫자만 남긴다."""
        t = str(기준.get(층, "")).strip()
        t = t.replace("위 이하", "~").replace("위 이상", "~").replace("위", "")
        return t.replace(" ", "")

    def _시총기준(층):
        """순위만으로는 독자가 자기 종목을 대입 못 한다 → 시총도 같이 보여준다."""
        v = 기준.get({"대형": "대형시총", "중형": "중형시총", "소형": "소형시총"}[층])
        return str(v) if v else ""
    머리 = ('<tr><th style="text-align:left;padding:6px 3px 6px 2px;font-size:12px;'
            'color:#9aa0aa;font-weight:600">테마</th>'
            + "".join(f'<th style="padding:6px 1px;font-size:11.5px;color:#9aa0aa;font-weight:600;text-align:center">'
                      f'{층}<br><span style="font-size:9px;opacity:.65;white-space:nowrap">'
                      f'{_짧은기준(층)}</span>'
                      f'<br><span style="display:block;font-size:8.5px;color:#e0c060;'
                      f'line-height:1.2;overflow:hidden;text-overflow:ellipsis">'
                      f'{_시총기준(층)}</span></th>'
                      for 층 in ("대형", "중형", "소형"))
            + '<th style="padding:6px 1px;font-size:12px;color:#e8eaee;font-weight:700;text-align:center">전체</th></tr>')

    몸 = []
    for r in 행들:
        칸들 = []
        for 층 in ("대형", "중형", "소형"):
            c = (r.get("칸") or {}).get(층) or {}
            v = c.get("등락률")
            if v is None:
                칸들.append(f'<td class="ag-cell" data-cell="{r.get("테마")}|{층}" '
                            'style="padding:7px 2px;text-align:center;font-size:12px;'
                            'color:#6b7280;background:#ffffff08;border-radius:4px">—</td>')
            else:
                # ⚠️ 표 안의 테두리는 '내 관심종목 칸(금색)' 하나만 쓴다.
                #    오늘 최강 칸 강조는 없앴다 — 테두리가 두 종류면 서로 헷갈린다.
                _링 = ''
                칸들.append(f'<td class="ag-cell" data-cell="{r.get("테마")}|{층}" '
                            f'style="padding:7px 2px;text-align:center;font-size:12.5px;'
                            f'background:{_grid_cell_color(v)};border-radius:4px;{_링}'
                            f'{_grid_text_style(v)}">{v:+.1f}</td>')
        전 = r.get("전체")
        if isinstance(전, (int, float)):
            # '전체'는 이미 내림차순 정렬돼 있어 색 농담이 순서와 같은 말을 반복한다.
            #   → 배경 채움을 빼고 숫자 부호 색(빨강/파랑)만 남긴다.
            #     금색 왼쪽 선으로 "여기부터는 요약"임만 표시.
            부호색 = "#e04a36" if 전 >= 0 else "#337ad6"
            전칸 = (f'<td style="padding:7px 2px;text-align:center;font-size:13px;'
                   f'font-weight:800;color:{부호색};'
                   f'border-left:2px solid rgba(240,198,90,.5)">{전:+.1f}</td>')
        else:
            전칸 = ('<td style="padding:7px 2px;text-align:center;font-size:12px;color:#6b7280;'
                   'border-left:2px solid rgba(240,198,90,.3)">—</td>')
        # 모바일(가로 360px)에서 표가 잘리지 않게: 테마명은 '·' 뒤에서 줄바꿈을 허용한다.
        #   예) '인터넷·게임·엔터' → '인터넷·' / '게임·' / '엔터' 로 접힘
        #   nowrap을 유지하면 이 한 칸이 표 전체 폭을 밀어내 가로 스크롤이 생긴다.
        rid = f"{_pfx}r{len(몸)}"
        # ⚠️ 화살표가 혼자 다음 줄로 떨어지던 문제:
        #    테마명을 '·'에서 접히게 해뒀는데 화살표를 그냥 뒤에 붙이면
        #    마지막 조각과 분리될 수 있다. 마지막 조각과 화살표를 한 덩어리로 묶는다.
        # ⚠️ 긴 테마명이 두 줄로 접히면 그 행만 두꺼워져 표가 들쭉날쭉해진다.
        #    → 한 줄 고정(넘치면 …로 자름). 전체 이름은 눌렀을 때 헤더에서 볼 수 있다.
        _풀 = str(r.get("테마", ""))
        _불 = 불난구역.get(_풀)
        불배지 = (f'<span style="color:#ff9a3c;font-size:9px;flex:none" '
                f'title="오늘 뜨는 현장: {", ".join(_불)}">&nbsp;🔥</span>') if _불 else ''
        테마명 = (f'<span style="flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;'
                 f'white-space:nowrap">{_풀}</span>{불배지}'
                 f'<span style="color:#e0c060;font-size:9px;flex:none">&nbsp;▾</span>')
        테마명_평 = (f'<span style="flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;'
                   f'white-space:nowrap">{_풀}</span>{불배지}')

        펼칠것 = []
        for 층 in ("대형", "중형", "소형"):
            칸 = (r.get("칸") or {}).get(층) or {}
            목록 = 칸.get("종목") or []
            if not 목록:
                continue
            # 칩은 격자 램프를 쓰지 않는다.
            #   칸 색은 '평균의 강도'를 보여주는 용도라 개별 종목까지 같은 색으로 칠하면
            #   전부 붉은 덩어리가 되어 종목명이 안 읽힌다.
            #   → 배경은 읽기 좋은 어두운 회색 고정, 등락률 숫자에만 색을 준다.
            칩 = "".join(
                f'<span style="display:inline-block;font-size:11.5px;padding:4px 8px;'
                f'margin:2px 4px 2px 0;border-radius:6px;background:#1b2230;'
                f'border:1px solid #2a3446;color:#dfe3e9;font-weight:600">'
                f'{x.get("명","")} '
                f'<b style="color:{"#ff6b4a" if (x.get("등") or 0) >= 0 else "#5b9bff"}">'
                f'{(x.get("등") or 0):+.1f}%</b></span>' for x in 목록)
            # ⚠️ "1종목 중 상위"처럼 말이 안 되는 문구가 나오던 문제:
            #    전체 종목수와 화면에 보이는 개수가 같으면 '중 상위'가 아니라 전부다.
            #    표본이 GRID_최소종목 미만이라 격자에 —로 나온 칸도 따로 알려준다.
            총 = 칸.get("종목수") or len(목록)
            if 총 < GRID_최소종목:
                꼬리 = f'{총}종목 (표본이 적어 격자에는 —로 표시)'
            elif 총 > len(목록):
                꼬리 = f'{총}종목 중 상위 {len(목록)}개'
            else:
                꼬리 = f'{총}종목 전부'
            펼칠것.append(
                f'<div style="margin:6px 0 0"><span style="font-size:10.5px;color:#8b93a0;'
                f'font-weight:700">{층}</span> '
                f'<span style="font-size:10px;color:#6f7784">{꼬리}</span>'
                f'<div style="margin-top:4px">{칩}</div></div>')
        접힘 = ""
        if 펼칠것:
            # 닫기 버튼은 없앤다 — 테마명을 다시 누르면 닫히므로 중복이고,
            # 버튼이 있으면 "눌러야 닫힌다"고 오해하게 된다.
            접힘 = (f'<tr id="{rid}" style="display:none"><td colspan="5" '
                    f'style="padding:9px 8px 12px;background:#0f131a;border-radius:6px">'
                    f'<p style="margin:0;font-size:11.5px;color:#e0c060;font-weight:700">'
                    f'{r.get("테마","")} 구성 종목 '
                    f'<span style="color:#6f7784;font-weight:600">· 다시 누르면 닫힙니다</span></p>'
                    f'{"".join(펼칠것)}</td></tr>')
            테마셀 = (f'<td onclick="gtog(\'{rid}\')" title="{_풀}" '
                    f'style="padding:7px 3px 7px 2px;font-size:11.5px;color:#d5d9e0;'
                    f'cursor:pointer;-webkit-tap-highlight-color:transparent">'
                    f'<span style="display:flex;align-items:center">{테마명}</span></td>')
        else:
            테마셀 = (f'<td title="{_풀}" style="padding:7px 3px 7px 2px;font-size:11.5px;'
                    f'color:#d5d9e0"><span style="display:flex;align-items:center">'
                    f'{테마명_평}</span></td>')
        몸.append(f'<tr class="ag-row" data-zone="{_풀}">'
                 + 테마셀 + "".join(칸들) + 전칸 + '</tr>' + 접힘)


    # ── 색 강도 범례 (색만으로 못 읽는 사람을 위해 숫자 경계를 같이 보여준다) ──
    def _칩(색, 라벨):
        return (f'<span style="display:inline-flex;align-items:center;gap:3px;font-size:9.5px;'
                f'color:#7d848f"><span style="width:11px;height:11px;border-radius:2px;'
                f'background:{색};display:inline-block"></span>{라벨}</span>')
    범례 = ('<div style="display:flex;flex-wrap:wrap;gap:7px;margin:9px 0 0;'
            'padding-top:8px;border-top:1px solid #1e2531">'
            + _칩(GRID_RAMP_DN[4], "−3%↓") + _칩(GRID_RAMP_DN[2], "−1%") 
            + _칩(GRID_RAMP_UP[0], "0%") + _칩(GRID_RAMP_UP[2], "+1%")
            + _칩(GRID_RAMP_UP[4], "+3%↑")
            + '<span style="font-size:9.5px;color:#7d848f">· '
              '맨 오른쪽 <b style="color:#9aa0aa">전체</b>는 높은 순으로 정렬돼 있습니다</span></div>')

    프리 = ""
    if isinstance(프리미엄, (int, float)):
        # 크기 프리미엄의 최근 평균 비교용(20일 추이 행은 없앴지만 이 숫자는 유지한다).
        이력 = _load_strata_history()
        추이 = [r.get("크기프리미엄") for r in 이력 if isinstance(r.get("크기프리미엄"), (int, float))]
        평균 = (sum(추이) / len(추이)) if len(추이) >= 5 else None
        비교 = (f' · 최근 {len(추이)}일 평균 {평균:+.1f}%p' if 평균 is not None else " · 추이 축적 중")
        방향 = "대형 쏠림" if 프리미엄 > 0 else "소형 우위"
        프리 = (f'<p style="margin:10px 0 0;font-size:12.5px;color:#c9ced6">'
                f'크기 프리미엄 <b style="color:#f0c65a">{프리미엄:+.2f}%p</b> '
                f'({방향}){비교}</p>')

    return ('<div style="background:#161a22;border:1px solid #232a36;border-radius:14px;'
            'padding:14px 14px 12px;margin:0 0 14px">'
            '<p style="margin:0 0 2px;font-size:12px;color:#8b93a0;letter-spacing:.02em">내 종목 구역</p>'
            '<p style="margin:0 0 10px;font-size:17.5px;font-weight:800;color:#f2f4f7">'
            '오늘 내 종목은 어디에 있었나</p>'
            # min-width를 없애 화면 폭에 맞춘다 — 모바일에서 한눈에 다 보이게.
            f'<table style="width:100%;border-collapse:separate;border-spacing:2px;'
            f'table-layout:fixed">{콜}{머리}{"".join(몸)}</table>'
            '<script>function gtog(id){var e=document.getElementById(id);'
            'if(e)e.style.display=(e.style.display==="none"?"table-row":"none");}'
            '(function(){function paint(){var mc=(window.cpMyCells?cpMyCells():{});'
            'document.querySelectorAll(".ag-cell").forEach(function(c){'
            'if(!mc[c.dataset.cell]){c.style.outline="none";return;}'
            'c.style.outline="2px solid #f0c65a"; c.style.outlineOffset="-2px";});}'
            'window.CP_PAINT=window.CP_PAINT||[];window.CP_PAINT.push(paint);'
            'if(document.readyState!=="loading"){paint()}else{'
            'document.addEventListener("DOMContentLoaded",paint)}})();</script>'
            '<p style="margin:7px 0 0;font-size:11px;color:#e0c060">'
            '👆 섹터 이름을 누르면 그 줄의 종목이 펼쳐집니다<br>'
            '<span style="color:#ff9a3c">🔥</span>는 오늘 그 섹터에서 불이 난 줄입니다<br>'
            '<span style="display:inline-block;width:11px;height:11px;border-radius:2px;'
            'border:1.5px solid #f0c65a;vertical-align:-2px"></span> '
            '<b>금색 테두리</b>는 <b>내가 등록한 관심종목이 있는 칸</b>입니다<br>'
            '위 <b>내 관심종목 등록</b>에 종목을 넣으면 자동으로 표시됩니다</p>'
            + 범례 + 프리
            + '<details style="margin:10px 0 0;padding:9px 10px;background:#0f131a;'
              'border-radius:8px;border:1px solid #1e2531">'
              '<summary style="font-size:11.5px;color:#e0c060;font-weight:700;'
              'cursor:pointer;list-style:none">📖 내 종목 구역 보는 방법 '
              '<span style="color:#6f7784;font-weight:600">(눌러서 펼치기)</span></summary>'
              '<div style="height:6px"></div>'
              '<p style="margin:0;font-size:11px;color:#7d848f;line-height:1.65">'
              '<b style="color:#9aa0aa">가로로 읽으면</b> — 같은 테마라도 대형·중형·소형 중 '
              '어디가 올랐는지 보입니다. 내 종목 크기 칸이 <b style="color:#ff6b4a">밝은 빨강</b>이면 '
              '그 흐름을 세게 탄 것입니다.<br>'
              '<b style="color:#9aa0aa">세로로 읽으면</b> — 오늘 어느 테마가 주인공이었는지 보입니다. '
              '맨 오른쪽 <b style="color:#9aa0aa">전체</b>는 그 테마의 평균이고, '
              '<b style="color:#9aa0aa">위에서부터 높은 순</b>으로 줄 세워져 있습니다.<br>'
              '<b style="color:#9aa0aa">색</b> — 빨강이 <b style="color:#ff6b4a">밝고 선명할수록</b> '
              '많이 오른 칸, 파랑이 <b style="color:#5b9bff">밝을수록</b> 많이 내린 칸입니다. '
              '회색은 거의 안 움직인 칸입니다.<br>'
              '<b style="color:#9aa0aa">맨 아래 줄</b> — 그 크기(대형·중형·소형)의 시장 전체 평균과 '
              '최근 20거래일 추이선입니다. 위 표와 열이 맞춰져 있습니다.'
              '</p></details>'
            + '<p style="margin:8px 0 0;font-size:11px;color:#6f7784;line-height:1.5">'
            f'한 칸에 종목이 {GRID_최소종목}개 미만이면 —로 둡니다 · '
            '한 종목이 여러 테마에 들어갈 수 있습니다</p>'
            '</div>')


def build_headline(해석):
    """오늘의 사건명 — 리포트 최상단 제목.

    이름이 붙으면 그날 시장이 기억되고, 아카이브가 목차가 된다.
    근거가 없으면 조용히 생략한다(제목만 그럴듯한 것을 막기 위해).
    """
    제목 = (해석.get("사건명") or "").strip()
    if not 제목:
        return ""
    제목 = 제목.strip("〈〉<>").strip()
    if not 제목:
        return ""
    return ('<div style="margin:0 0 12px">'
            '<p style="margin:0 0 4px;font-size:11.5px;color:#8b93a0;letter-spacing:.08em;font-weight:700">'
            'TODAY</p>'
            f'<p style="margin:0;font-size:21px;font-weight:800;color:#20242c;line-height:1.35">'
            f'〈{제목}〉</p></div>')


def build_top_picks(해석):
    """오늘 딱 N개 — 핵심편 최상단.

    개수는 고정이 아니다. 그날 실제로 중요한 것만 담기 때문에 2~4개로 달라진다.
    마지막 항목은 반드시 '내일 볼 것'이라 리포트가 닫히지 않고 열린다.
    """
    항목 = 해석.get("오늘딱N") or []
    항목 = [str(x).strip() for x in 항목 if str(x).strip()][:4]
    if len(항목) < 2:
        return ""
    한글수 = {2: "두", 3: "세", 4: "네"}.get(len(항목), "세")
    줄 = "".join(
        f'<li style="margin:0 0 7px;padding-left:24px;position:relative;font-size:14.5px;'
        f'line-height:1.55;color:#e8eaee">'
        f'<span style="position:absolute;left:0;top:1px;width:17px;height:17px;border-radius:5px;'
        f'background:#2a3140;color:#f0c65a;font-size:11px;font-weight:700;display:inline-flex;'
        f'align-items:center;justify-content:center">{i}</span>{t}</li>'
        for i, t in enumerate(항목, start=1))
    return ('<div style="background:#12161d;border:1px solid #f0c65a33;border-left:3px solid #f0c65a;'
            'border-radius:0 12px 12px 0;padding:13px 14px;margin:0 0 14px">'
            f'<p style="margin:0 0 9px;font-size:16.5px;font-weight:800;color:#f0c65a">'
            f'오늘 시장에서 딱 {한글수} 가지만 보십시오</p>'
            f'<ul style="margin:0;padding:0;list-style:none">{줄}</ul></div>')


# ============================================================
# 수급 변속기 · 관제 레이더 · 경사선 · 포착 항로     [v-k2 신규]
# ============================================================

RADAR_R = 130          # 레이더 반지름(px)
RADAR_슬롯 = 12        # 각도 슬롯 수 (30도 간격)


# ── 1. 수급 변속기 ───────────────────────────────────────────
def build_flow_gearbox():
    """수급의 '속도 변화'를 6단계로 판정한다.

    방향(사느냐 파느냐)은 누구나 안다. 힘이 세지는지 약해지는지는 아무도 안 알려준다.
    꼭지와 바닥은 방향보다 속도가 먼저 꺾인다 — 그래서 1차 차분을 본다.
    """
    try:
        with open(apath("flow_history.json"), encoding="utf-8") as f:
            rows = json.load(f) or []
    except Exception:
        return ""
    vals = [r.get("실탄") for r in rows if isinstance(r.get("실탄"), (int, float))]
    # 5거래일 = 한 주. 4일이면 주 단위 흐름이 잘려 "이번 주 어땠나"가 안 읽힌다.
    #   (이력이 5일에 못 미치면 있는 만큼 쓰되, 최소 4일은 있어야 속도 변화를 판정한다)
    if len(vals) < 4:
        return ""
    최근 = vals[-5:]
    오늘 = 최근[-1]
    차분 = [최근[i + 1] - 최근[i] for i in range(len(최근) - 1)]
    오름 = sum(1 for d in 차분 if d > 0)
    내림 = sum(1 for d in 차분 if d < 0)
    어제 = 최근[-2]

    if 오늘 > 0 and 어제 <= 0:
        상태, 색, 설명 = "매수 전환", "#ff6b4a", "팔던 흐름이 사는 쪽으로 돌아섰습니다"
    elif 오늘 < 0 and 어제 >= 0:
        상태, 색, 설명 = "매도 전환", "#5b9bff", "사던 흐름이 파는 쪽으로 돌아섰습니다"
    elif 오늘 > 0 and 오름 >= 2:
        상태, 색, 설명 = "매수 가속", "#ff6b4a", "사는 힘이 점점 세지고 있습니다"
    elif 오늘 > 0 and 내림 >= 2:
        상태, 색, 설명 = "매수 감속", "#86efac", "여전히 사지만 힘은 빠지는 중입니다"
    elif 오늘 < 0 and 내림 >= 2:
        상태, 색, 설명 = "매도 가속", "#5b9bff", "파는 힘이 점점 세지고 있습니다"
    elif 오늘 < 0 and 오름 >= 2:
        상태, 색, 설명 = "매도 감속", "#c4b5fd", "여전히 팔지만 힘은 빠지는 중입니다"
    else:
        상태, 색, 설명 = "속도 유지", "#9aa0aa", "흐름의 세기에 큰 변화가 없습니다"

    막대 = []
    최대 = max(abs(v) for v in 최근) or 1
    for v in 최근:
        h = max(4, int(abs(v) / 최대 * 34))
        c = "#ff6b4a" if v >= 0 else "#5b9bff"
        막대.append(f'<div style="width:26px;display:flex;flex-direction:column;'
                    f'align-items:center;justify-content:flex-end;height:40px">'
                    f'<div style="width:16px;height:{h}px;background:{c};border-radius:3px"></div></div>')

    수치 = " → ".join(f'{v/10000:+.1f}조' if abs(v) >= 10000 else f'{int(v):+,}억' for v in 최근)
    return ('<div style="background:#141922;border:1px solid #232a36;border-radius:12px;'
            'padding:12px 14px;margin:10px 0 0">'
            '<p style="margin:0 0 2px;font-size:11.5px;color:#8b93a0">수급 변속기</p>'
            f'<p style="margin:0 0 8px;font-size:16px;font-weight:800;color:{색}">{상태}</p>'
            f'<div style="display:flex;gap:6px;align-items:flex-end;margin-bottom:7px">{"".join(막대)}</div>'
            f'<p style="margin:0;font-size:12.5px;color:#c9ced6">{설명}</p>'
            f'<p style="margin:4px 0 0;font-size:11.5px;color:#6f7784">'
            f'최근 {len(최근)}거래일 실탄 {수치}</p>'
            '<p style="margin:5px 0 0;font-size:11px;color:#6f7784;line-height:1.5">'
            '💡 <b style="color:#8b93a0">실탄</b>이란 코스피에서 '
            '<b style="color:#8b93a0">외국인 + 기관</b>이 순매수한 금액의 합계입니다. '
            '개인은 이 둘의 거울(반대편)이라 더하면 정보가 지워져 제외했고, '
            '선물·비차익은 단위가 달라 합치지 않습니다.</p>'
            '</div>')


# ── 2. 섹터 주도력 이력 (레이더 원료) ─────────────────────────
def _sector_scores(days=6):
    """archive/data_*.json에서 날짜별 {테마명: 주도력점수}를 읽는다.

    ⚠️ 한계: 저장된 것은 그날 TOP6뿐이다. TOP6 밖 섹터는 점수가 없어
       '권외'로 처리한다. 전 테마 저장이 시작되면 정확도가 올라간다.
    """
    out = []
    for f in sorted(alist(r"data_\d{8}\.json"))[-days:]:
        try:
            with open(apath(f), encoding="utf-8") as fp:
                d = json.load(fp)
            m = {}
            for s in (d.get("주도섹터") or []):
                nm, sc = s.get("테마명"), s.get("주도력점수")
                if nm and isinstance(sc, (int, float)):
                    m[nm] = float(sc)
            if m:
                out.append((d.get("날짜", f[5:13]), m))
        except Exception:
            continue
    return out


def _radar_slots(이름들):
    """테마명을 12개 고정 각도 슬롯에 배정한다.

    이름 해시로 정하므로 같은 섹터는 매일 같은 자리에 온다
    (매일 자리가 바뀌면 '내 섹터 찾기'가 안 된다).
    """
    쓴슬롯, 배정 = set(), {}
    for nm in 이름들:
        s = sum(ord(c) for c in nm) % RADAR_슬롯
        for k in range(RADAR_슬롯):
            c = (s + k) % RADAR_슬롯
            if c not in 쓴슬롯:
                쓴슬롯.add(c); 배정[nm] = c; break
    return 배정


def _polar(cx, cy, score, slot):
    """주도력 점수 → 좌표. 점수가 높을수록 중심(관제탑)에 가깝다."""
    import math as _m
    r = (100 - max(0.0, min(100.0, score))) / 100 * RADAR_R
    a = _m.radians(slot * (360 / RADAR_슬롯) - 90)
    return cx + r * _m.cos(a), cy + r * _m.sin(a)


# ── 📊 구역 성적표 — 시장 대비 누적 성과 (v-l6 신규) ──────────
#  무엇: 각 계좌 구역이 코스피를 얼마나 이겼는지 5/20/60일 창으로 집계한다.
#
#  ⚠️ 왜 '초과수익(%p)'을 주인공으로 두나:
#     누적 수익률만 그리면 지수가 흔들 때 모든 구역이 같이 흔들려
#     "어느 구역이 잘했나"가 곡선 모양에서 안 읽힌다.
#     시장을 빼면 그 공통 소음이 사라지고 순수 실력만 남는다.
#
#  ⚠️ 재료: archive/data_*.json의 계좌격자(행별 '전체') + market_history의 코스피등락.
#     계좌격자는 최근에 생긴 코너라 이력이 짧다 → 5일치도 못 채우면 통째로 생략한다.
# ── 섹터 고정 색 (v-l9) ──────────────────────────────────
#  왜: 그날 순위에 따라 색이 바뀌면 "어제 빨간 선이 오늘은 파란 선"이 되어
#      며칠 이어 보는 사람이 선을 눈으로 못 쫓는다.
#      섹터마다 색을 **못 박아** 두면 색 자체가 이름표가 된다.
#  ⚠️ 금색(#f0c65a)은 '내 관심종목의 섹터' 전용이라 팔레트에서 뺀다.
SECTOR_COLORS = {
    "반도체":           "#ff6b4a",
    "AI·소프트웨어":     "#22d3ee",
    "2차전지·소재":      "#5b9bff",
    "조선·기계·방산":    "#4ade80",
    "전력·신재생·원전":  "#a78bfa",
    "바이오·제약":       "#f472b6",
    "자동차·부품":       "#fb923c",
    "인터넷·게임·엔터":  "#818cf8",
    "금융·지주":         "#34d399",
    "에너지·정유·화학":  "#e879f9",
    "통신·유틸리티":     "#7dd3fc",
    "소비·유통·식품":    "#fbbf24",
    "건설·부동산":       "#94a3b8",
    "운송·물류":         "#2dd4bf",
    "전기전자·부품":     "#c084fc",
    "신규 주도":         "#ef4444",
    "기타":             "#6b7280",
}
_SECTOR_FALLBACK = ["#ff8a65", "#80cbc4", "#9fa8da", "#ce93d8", "#a5d6a7", "#ffab91"]


def sector_color(nm):
    """섹터명 → 항상 같은 색. 표에 없는 이름은 이름 해시로 고정 배정한다."""
    if nm in SECTOR_COLORS:
        return SECTOR_COLORS[nm]
    h = 0
    for ch in str(nm):
        h = (h * 31 + ord(ch)) % 9973
    return _SECTOR_FALLBACK[h % len(_SECTOR_FALLBACK)]


ZONE_WINDOWS = [(5, "이번 주", "5일"), (20, "한 달", "20일"), (60, "분기", "60일")]
ZONE_TOP_N = 5          # 처음에 펼쳐 보여줄 줄 수 (나머지는 '더보기')
#  창별 최소 관측일 — 이만큼 없으면 그 탭은 "축적 중"으로 둔다.
#  ⚠️ 2일치로 "이번 주 성적"이라고 쓰면 거짓말이 된다. 없는 비교는 만들지 않는다.
ZONE_MIN = {5: 5, 20: 10, 60: 30}


def _zone_series():
    """{구역명: {날짜: 등락률}} 과 {날짜: 시장등락률}을 만든다."""
    구역 = {}
    for f in sorted(alist(r"data_\d{8}\.json")):
        try:
            with open(apath(f), encoding="utf-8") as fp:
                d = json.load(fp)
        except Exception:
            continue
        날짜 = d.get("날짜")
        for r in ((d.get("계좌격자") or {}).get("행") or []):
            v, nm = r.get("전체"), r.get("테마")
            if nm and isinstance(v, (int, float)):
                구역.setdefault(nm, {})[날짜] = v
    시장 = {}
    try:
        with open("market_history.json", encoding="utf-8") as f:
            for r in ((json.load(f) or {}).get("일별") or []):
                v = r.get("코스피등락")
                if isinstance(v, (int, float)):
                    시장[str(r.get("날짜", "")).replace("-", "")] = v
    except Exception:
        pass
    return 구역, 시장


def _zone_stat(일별, 시장, n):
    """최근 n거래일 성적. 반환 (초과%p, 수익률%, 승, 총, 곡선[(날짜,초과누적)])"""
    날짜들 = sorted(set(일별) & set(시장))[-n:]
    if len(날짜들) < ZONE_MIN.get(n, 5):
        return None
    tc = mc = 1.0
    곡선 = []
    승 = 0
    for d in 날짜들:
        t, m = 일별[d], 시장[d]
        tc *= (1 + t / 100); mc *= (1 + m / 100)
        if t > m:
            승 += 1
        곡선.append((d, round((tc - mc) * 100, 2)))
    return (round((tc - mc) * 100, 2), round((tc - 1) * 100, 2),
            승, len(날짜들), 곡선)


# ── 📋 내 종목 (v-l7 신규) ────────────────────────────────
#  회원이 보유 종목을 입력하면
#    ① 그 종목이 어느 구역인지
#    ② 시장 대비 5/20/60일 성적이 어떤지
#    ③ 오늘 그 종목의 뉴스·공시가 있는지
#  를 한 자리에서 보여준다.
#
#  ⚠️ 설계 원칙: 입력값은 **브라우저에만** 저장한다(서버로 안 보낸다).
#     계산도 전부 브라우저에서 한다 → 회원이 몇 명이든 서버 부담이 0이다.
#     그래서 오늘 리포트 안에 '종목사전 20일치'를 미리 실어 보낸다.
MYSTOCK_MAX = 10        # 입력 상한. 넘으면 화면이 길어져 오히려 안 읽힌다.
MYSTOCK_DAYS = 60       # 페이지에 실어 보낼 최대 거래일 수


def _mystock_payload():
    """브라우저 계산용 데이터 묶음.

    {"days":[날짜...], "mkt":[코스피등락...],
     "stocks":{종목명:[구역들, 순위, 층, 시장]},
     "ret":{종목명:[일별 등락률...]}}   ← ret는 days와 같은 길이(없는 날 null)
    """
    파일들 = sorted(alist(r"data_\d{8}\.json"))[-MYSTOCK_DAYS:]
    days, per = [], {}
    meta = {}
    for f in 파일들:
        try:
            with open(apath(f), encoding="utf-8") as fp:
                d = json.load(fp)
        except Exception:
            continue
        사전 = (d.get("계좌격자") or {}).get("종목사전") or {}
        if not 사전:
            continue
        날짜 = d.get("날짜")
        days.append(날짜)
        for nm, v in 사전.items():
            per.setdefault(nm, {})[날짜] = v[3] if len(v) > 3 else None
            meta[nm] = [v[0] if v else [], v[1] if len(v) > 1 else None,
                        v[2] if len(v) > 2 else None, v[4] if len(v) > 4 else None]
    if not days:
        return None
    시장 = {}
    try:
        with open("market_history.json", encoding="utf-8") as f:
            for r in ((json.load(f) or {}).get("일별") or []):
                시장[str(r.get("날짜", "")).replace("-", "")] = r.get("코스피등락")
    except Exception:
        pass
    return {
        "days": days,
        "mkt": [시장.get(d) for d in days],
        "stocks": meta,
        "ret": {nm: [per[nm].get(d) for d in days] for nm in per},
    }


def build_my_stocks(data):
    payload = _mystock_payload()
    if not payload:
        return ""
    이름들 = sorted(payload["stocks"])
    보유일 = len(payload["days"])

    # 오늘의 뉴스·공시 (브라우저가 종목명으로 매칭한다)
    뉴스 = [{"t": n.get("제목", ""), "u": n.get("링크", "")}
           for n in (data.get("뉴스원본") or []) if n.get("제목")]
    공시원 = data.get("공시")
    공시목록 = 공시원.get("목록") if isinstance(공시원, dict) else (공시원 or [])
    공시 = [{"c": g.get("회사명", ""), "t": (g.get("공시명") or "").strip(),
            "s": g.get("별점"), "u": g.get("링크", "")}
           for g in (공시목록 or []) if g.get("회사명")]

    옵션 = "".join(f'<option value="{n}">' for n in 이름들)
    PAY = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    NEWS = json.dumps(뉴스, ensure_ascii=False, separators=(",", ":"))
    DISC = json.dumps(공시, ensure_ascii=False, separators=(",", ":"))

    JS = ("""<script>
(function(){
 window.CP_PAINT=window.CP_PAINT||[];
 var K='chartpro_mystocks', MAX=""" + str(MYSTOCK_MAX) + """;
 var P=""" + PAY + """, NEWS=""" + NEWS + """, DISC=""" + DISC + """;
 var WINDOWS=[[5,'이번 주'],[20,'한 달'],[60,'분기']], curW=5;
 function get(){try{return JSON.parse(localStorage.getItem(K))||[]}catch(e){return []}}
 function set(v){try{localStorage.setItem(K,JSON.stringify(v))}catch(e){}}
 // 내 관심종목이 속한 섹터 집합 — 계좌 구역·섹터 성적표·시총별 섹터가 함께 쓴다.
 window.cpMyZones=function(){var s={};
  get().forEach(function(nm){((P.stocks[nm]||[[]])[0]||[]).forEach(function(z){s[z]=1;});});
  return s;};
 // 내 종목이 '어느 섹터의 어느 크기 칸'에 있는지 — 칸 단위 표시에 쓴다.
 //   예: 삼성SDI면 '2차전지·소재 × 대형' 칸 하나만 금색이 되어야 한다.
 window.cpMyCells=function(){var s={};
  get().forEach(function(nm){var m=P.stocks[nm]||[[],null,null,null];
   var tier=m[2]; if(!tier) return;
   (m[0]||[]).forEach(function(z){s[z+'|'+tier]=1;});});
  return s;};
 window.cpFire=function(){(window.CP_PAINT||[]).forEach(function(f){try{f()}catch(e){}});};
 function fmt(v){return (v>=0?'+':'')+v.toFixed(1);}
 function calc(nm,n){
  var r=P.ret[nm]; if(!r) return null;
  var idx=[]; for(var i=0;i<P.days.length;i++){if(r[i]!=null&&P.mkt[i]!=null)idx.push(i);}
  idx=idx.slice(-n); if(idx.length<2) return {short:true,have:idx.length};
  var tc=1,mc=1,w=0;
  idx.forEach(function(i){tc*=(1+r[i]/100); mc*=(1+P.mkt[i]/100); if(r[i]>P.mkt[i])w++;});
  return {ex:(tc-mc)*100, ret:(tc-1)*100, win:w, tot:idx.length};
 }
 function render(){
  var my=get(), box=document.getElementById('ms-list');
  if(!my.length){box.innerHTML='<p style="margin:14px 0;font-size:12px;color:#7d848f;'+
   'text-align:center">위에 종목을 입력하면 구역과 시장 대비 성적을 보여드립니다</p>';
   document.getElementById('ms-sum').innerHTML=''; return;}
  var html='', exs=[];
  my.forEach(function(nm){
   var m=P.stocks[nm]||[[],null,null,null], c=calc(nm,curW);
   var zones=(m[0]||[]).map(function(z){return '<span style="display:inline-block;'+
     'font-size:10px;padding:2px 7px;margin-right:4px;border-radius:99px;'+
     'background:#22303f;color:#8fd0e8">'+z+'</span>';}).join('')||
     '<span style="font-size:10px;color:#6f7784">구역 미분류</span>';
   var right='';
   if(c&&!c.short){exs.push(c.ex);
    var col=c.ex>=0?'#ff6b4a':'#5b9bff';
    right='<div style="text-align:right;flex:none;width:60px">'+
     '<div style="font-size:12.5px;font-weight:800;color:'+col+'">'+fmt(c.ex)+'%p</div>'+
     '<div style="font-size:9.5px;color:#7d848f">'+fmt(c.ret)+'%</div>'+
     '<div style="font-size:9px;color:#6f7784">'+c.win+'/'+c.tot+'승</div></div>';
   }else{right='<div style="text-align:right;flex:none;width:60px;font-size:10px;'+
     'color:#6f7784">축적 중</div>';}
   var tags='';
   NEWS.forEach(function(n){if(n.t.indexOf(nm)>=0)tags+='<a href="'+n.u+'" target="_blank" '+
    'style="display:block;font-size:10.5px;color:#8fb4ee;margin-top:3px;text-decoration:none">'+
    '📰 '+n.t+'</a>';});
   DISC.forEach(function(g){if(g.c===nm)tags+='<a href="'+g.u+'" target="_blank" '+
    'style="display:block;font-size:10.5px;color:#e0c060;margin-top:3px;text-decoration:none">'+
    '📄 '+g.t+(g.s?' ('+'★'.repeat(g.s)+')':'')+'</a>';});
   html+='<div style="padding:9px 8px;border-bottom:1px solid #1b212c">'+
    '<div style="display:flex;align-items:flex-start;gap:8px">'+
    '<div style="flex:1;min-width:0">'+
    '<div style="font-size:13px;font-weight:800;color:#e8eaee">'+nm+
    '<span onclick="msDel(\\''+nm+'\\')" style="color:#6f7784;font-size:11px;'+
    'margin-left:6px;cursor:pointer">✕</span></div>'+
    '<div style="margin-top:4px">'+zones+'</div>'+
    (m[1]?'<div style="font-size:9.5px;color:#6f7784;margin-top:3px">'+
      (m[3]||'')+' · 시총 '+m[1]+'위 ('+(m[2]||'')+')</div>':'')+
    tags+'</div>'+right+'</div></div>';
  });
  box.innerHTML=html; drawChart(my); drawBrief(my); if(window.cpFire)cpFire();
  var s=document.getElementById('ms-sum');
  if(exs.length){var avg=exs.reduce(function(a,b){return a+b;},0)/exs.length;
   var col=avg>=0?'#ff6b4a':'#5b9bff';
   s.innerHTML='<div style="margin-top:9px;padding:9px 10px;background:#0f131a;'+
    'border-radius:8px;display:flex;justify-content:space-between;align-items:center">'+
    '<span style="font-size:11.5px;color:#c9ced6">내 종목 평균 (동일 비중)</span>'+
    '<span style="font-size:14px;font-weight:800;color:'+col+'">'+fmt(avg)+'%p</span></div>';
  }else{s.innerHTML='';}
 }
 // ── 📰 내 종목 브리핑 (심층편) ──
 //  오늘의 뉴스·공시·수급 중 **특이점만** 짚는다. 없으면 짧게 끝낸다.
 //  ⚠️ '오늘 분석' 문장은 지금은 숫자에서 뽑은 요약이다.
 //     Claude가 쓰는 해석으로 교체하는 것이 다음 단계.
 function drawBrief(my){
  var host=document.getElementById('ms-brief'); if(!host) return;
  if(!my.length){host.innerHTML='<p style="margin:14px 0;font-size:12px;color:#7d848f;'+
   'text-align:center">위 <b>내 관심종목 등록</b>에 종목을 넣으면 여기에 브리핑이 쌓입니다</p>';
   return;}
  var out='';
  my.forEach(function(nm){
   var m=P.stocks[nm]||[[],null,null,null], c=calc(nm,20);
   var zones=(m[0]||[]).map(function(z){return '<span style="display:inline-block;'+
     'font-size:10px;padding:2px 7px;margin-right:4px;border-radius:99px;'+
     'background:#22303f;color:#8fd0e8">'+z+'</span>';}).join('');
   var items='', n1=0, n2=0;
   NEWS.forEach(function(n){if(n.t.indexOf(nm)>=0){n1++;
    items+='<div style="display:flex;gap:6px;margin-top:4px"><span style="flex:none">📰</span>'+
     '<a href="'+n.u+'" target="_blank" style="font-size:11px;color:#8fb4ee;'+
     'line-height:1.5;text-decoration:none">'+n.t+'</a></div>';}});
   DISC.forEach(function(g){if(g.c===nm){n2++;
    items+='<div style="display:flex;gap:6px;margin-top:4px"><span style="flex:none">📄</span>'+
     '<a href="'+g.u+'" target="_blank" style="font-size:11px;color:#e0c060;'+
     'line-height:1.5;text-decoration:none">'+g.t+(g.s?' '+'★'.repeat(g.s):'')+'</a></div>';}});
   if(!items) items='<p style="margin:4px 0 0;font-size:11px;color:#6f7784">'+
     '오늘은 뉴스도 공시도 없었습니다</p>';
   var 분석='';
   if(c&&!c.short){
    var 승률=c.win/c.tot*100;
    분석='최근 20일 '+c.win+'승 '+(c.tot-c.win)+'패('+승률.toFixed(0)+'%), 시장 대비 '+
     fmt(c.ex)+'%p입니다. ';
    분석+= (c.ex>=0
      ? (승률>=60?'꾸준히 시장을 이기고 있습니다.':'며칠에 몰아서 번 구간이라 변동이 큽니다.')
      : (승률<=30?'자리 자체가 불리했습니다 — 종목 선택 문제로 보기 어렵습니다.'
                 :'시장에 조금 뒤처지는 흐름입니다.'));
    if(n2) 분석+=' 오늘 공시가 있으니 내용을 확인해 보세요.';
    else if(n1) 분석+=' 오늘 뉴스가 있어 단기 변동이 커질 수 있습니다.';
   }else{분석='성적을 말하기엔 아직 이력이 부족합니다.';}
   out+='<div style="padding:11px 0;border-bottom:1px solid #1b212c">'+
    '<div style="font-size:13.5px;font-weight:800;color:#e8eaee">'+nm+'</div>'+
    '<div style="margin-top:4px">'+zones+'</div>'+items+
    '<div style="margin-top:7px;padding:8px 10px;background:#0f131a;border-radius:8px;'+
    'border-left:2.5px solid #e0c060">'+
    '<p style="margin:0;font-size:11.5px;color:#c9ced6;line-height:1.7">'+
    '<b style="color:#e0c060">오늘 분석</b> — '+분석+'</p></div></div>';
  });
  host.innerHTML=out;
 }
 // 내 종목들의 '시장 대비 초과수익' 곡선 — 등록 종목이 있을 때만 그린다.
 function drawChart(my){
  var host=document.getElementById('ms-chart'); if(!host) return;
  var W=360,H=150,L=30,R=10,T=12,B=20;
  var idx=[]; for(var i=0;i<P.days.length;i++){if(P.mkt[i]!=null)idx.push(i);}
  idx=idx.slice(-curW);
  if(!my.length||idx.length<3){host.innerHTML=''; return;}
  var series=[],all=[];
  my.forEach(function(nm){var r=P.ret[nm]; if(!r) return;
   var tc=1,mc=1,pts=[];
   idx.forEach(function(i){if(r[i]==null)return;
    tc*=(1+r[i]/100); mc*=(1+P.mkt[i]/100);
    var v=(tc-mc)*100; pts.push(v); all.push(v);});
   if(pts.length>=3) series.push({nm:nm,pts:pts});});
  if(!series.length){host.innerHTML=''; return;}
  all.push(0);
  var hi=Math.max.apply(null,all), lo=Math.min.apply(null,all), rng=Math.max(0.01,hi-lo);
  var n=Math.max.apply(null,series.map(function(s){return s.pts.length;}));
  function PX(i){return L+i*(W-L-R)/Math.max(1,n-1);}
  function PY(v){return T+(hi-v)/rng*(H-T-B);}
  var COL=['#f0c65a','#ff6b4a','#22d3ee','#4ade80','#a78bfa',
           '#fb923c','#f472b6','#5b9bff','#34d399','#e879f9'];
  var g='<rect x="'+L+'" y="'+T+'" width="'+(W-L-R)+'" height="'+(PY(0)-T)+
        '" fill="#ff6b4a" opacity=".05"/>'+
        '<rect x="'+L+'" y="'+PY(0)+'" width="'+(W-L-R)+'" height="'+(H-B-PY(0))+
        '" fill="#5b9bff" opacity=".05"/>'+
        '<line x1="'+L+'" y1="'+PY(0)+'" x2="'+(W-R)+'" y2="'+PY(0)+
        '" stroke="#8b93a0" stroke-width="1.3"/>';
  var leg='';
  series.forEach(function(s,k){
   var c=COL[k%COL.length];
   g+='<polyline points="'+s.pts.map(function(v,i){return PX(i)+','+PY(v);}).join(' ')+
      '" fill="none" stroke="'+c+'" stroke-width="1.6"/>';
   leg+='<span style="font-size:10px;color:'+c+'">— '+s.nm+'</span>';});
  [hi,0,lo].forEach(function(t){
   g+='<text x="'+(L-3)+'" y="'+(PY(t)+3)+'" text-anchor="end" font-size="8" fill="#6f7784">'+
      (t>=0?'+':'')+t.toFixed(0)+'</text>';});
  host.innerHTML='<p style="margin:9px 0 3px;font-size:10.5px;color:#8b93a0">'+
   '시장 대비 초과수익 추이</p>'+
   '<svg viewBox="0 0 '+W+' '+H+'" style="width:100%;height:auto;display:block">'+g+'</svg>'+
   '<div style="display:flex;flex-wrap:wrap;gap:7px;margin-top:4px">'+leg+'</div>';
 }
 window.msAdd=function(){
  var el=document.getElementById('ms-in'), nm=(el.value||'').trim();
  if(!nm) return;
  if(!P.stocks[nm]){alert('목록에 없는 종목입니다. 자동완성에서 골라주세요.'); return;}
  var my=get();
  if(my.indexOf(nm)>=0){el.value=''; return;}
  if(my.length>=MAX){alert('최대 '+MAX+'종목까지 담을 수 있습니다.'); return;}
  my.push(nm); set(my); el.value=''; render();
 };
 window.msDel=function(nm){var my=get(),i=my.indexOf(nm);
  if(i>=0){my.splice(i,1); set(my); render();}};
 window.msWin=function(n){curW=n;
  document.querySelectorAll('.ms-tab').forEach(function(t){
   var on=+t.dataset.n===n;
   t.style.background=on?'#2a3446':'#171c25';
   t.style.color=on?'#f0c65a':'#7d848f'; t.style.fontWeight=on?800:600;});
  render();};
 if(document.readyState!=='loading'){render()}else{
  document.addEventListener('DOMContentLoaded',render)}
})();
</script>""")

    탭 = "".join(
        f'<span class="ms-tab" data-n="{n}" onclick="msWin({n})" '
        f'style="flex:1;text-align:center;font-size:11px;padding:6px 0;border-radius:7px;'
        f'cursor:pointer;font-weight:{800 if n==5 else 600};'
        f'background:{"#2a3446" if n==5 else "#171c25"};'
        f'color:{"#f0c65a" if n==5 else "#7d848f"};'
        f'-webkit-tap-highlight-color:transparent">{이름}</span>'
        for n, 이름 in [(5, "이번 주 (5일)"), (20, "한 달 (20일)"), (60, "분기 (60일)")])

    return ('<div style="background:#141922;border:1px solid #232a36;border-radius:12px;'
            'padding:13px 14px;margin:10px 0 0">'
            '<p style="margin:0 0 2px;font-size:11.5px;color:#8b93a0">내 관심종목 등록</p>'
            '<p style="margin:0 0 5px;font-size:17px;font-weight:800;color:#f2f4f7">'
            '내 종목은 시장을 이기고 있나</p>'
            '<p style="margin:0 0 8px;font-size:11.5px;color:#c9ced6;line-height:1.6">'
            '한 번 등록해두면 <b style="color:#e8eaee">매일 자동으로 추적</b>합니다 — '
            '시장 대비 성적(5·20·60일), 그날의 뉴스와 공시, 소속 섹터 변화까지 '
            '이 자리에서 계속 보여드립니다.</p>'
            '<p style="margin:0 0 10px;font-size:11px;color:#e0c060">'
            f'최대 {MYSTOCK_MAX}종목 · 이 기기에만 저장되고 서버로 보내지 않습니다</p>'
            f'<datalist id="ms-names">{옵션}</datalist>'
            '<div style="display:flex;gap:6px;margin-bottom:10px">'
            '<input id="ms-in" list="ms-names" placeholder="종목명 입력 (예: 삼성전자)" '
            'style="flex:1;min-width:0;background:#0f131a;border:1px solid #2a3446;'
            'border-radius:8px;padding:9px 10px;font-size:12.5px;color:#e8eaee;outline:none">'
            '<button onclick="msAdd()" style="flex:none;background:#2a3446;border:none;'
            'color:#f0c65a;font-size:12.5px;font-weight:800;border-radius:8px;'
            'padding:9px 14px;cursor:pointer">추가</button></div>'
            f'<div style="display:flex;gap:6px;margin-bottom:9px">{탭}</div>'
            '<div id="ms-list"></div><div id="ms-sum"></div><div id="ms-chart"></div>'
            '<details style="margin:10px 0 0;padding:9px 10px;background:#0f131a;'
            'border-radius:8px;border:1px solid #1e2531">'
            '<summary style="font-size:11.5px;color:#e0c060;font-weight:700;'
            'cursor:pointer;list-style:none">📖 내 종목 보는 방법 '
            '<span style="color:#6f7784;font-weight:600">(눌러서 펼치기)</span></summary>'
            '<p style="margin:6px 0 0;font-size:11px;color:#7d848f;line-height:1.65">'
            '<b style="color:#9aa0aa">%p</b>는 코스피보다 얼마나 더 벌었나입니다. '
            '아래 작은 숫자는 실제 수익률, 그 아래는 그 기간 코스피를 이긴 날의 수입니다.<br>'
            '<b style="color:#8fd0e8">파란 태그</b>가 그 종목이 속한 구역입니다. '
            '한 종목이 두 구역에 걸치면 <b style="color:#9aa0aa">오늘 더 세게 움직인 구역</b>이 앞에 옵니다.<br>'
            '<b style="color:#9aa0aa">내 종목 평균</b>은 모든 종목을 같은 금액씩 샀다고 가정한 값입니다. '
            '실제 보유 비중은 받지 않으므로 참고용입니다.<br>'
            f'📰 뉴스와 📄 공시는 <b style="color:#9aa0aa">오늘</b> 그 종목이 언급된 것만 붙습니다.'
            '</p></details></div>' + JS)


def build_stock_brief():
    """📰 내 종목 브리핑 — 오늘의 뉴스·공시·수급 특이점.

    ⚠️ 내용은 브라우저가 그린다(관심종목이 기기에만 저장되므로).
       여기서는 자리만 만들고, build_my_stocks의 JS가 채운다.
    """
    return ('<div style="background:#141922;border:1px solid #232a36;border-radius:12px;'
            'padding:13px 14px;margin:10px 0 0">'
            '<p style="margin:0 0 2px;font-size:11.5px;color:#8b93a0">내 종목 브리핑</p>'
            '<p style="margin:0 0 10px;font-size:17px;font-weight:800;color:#f2f4f7">'
            '오늘 내 종목에 무슨 일이 있었나</p>'
            '<div id="ms-brief"></div>'
            '<p style="margin:9px 0 0;font-size:11px;color:#7d848f;line-height:1.6">'
            '📰 뉴스 · 📄 공시 중 <b>오늘 그 종목이 언급된 것만</b> 붙습니다. '
            '별일 없는 날은 짧게 끝납니다.</p></div>')


def build_sector_scoreboard():
    """📊 섹터 성적표 — 순위 막대 + 선 그래프를 한 카드로.

    v-l8에서 '구역 성적표'와 '구역 추이'를 합쳤다.
    둘은 같은 숫자의 두 표현(결론/과정)이라 떨어져 있으면 오히려 헷갈렸다.

    구성: 탭(5·20·60일) → 상승3+하락3 막대 → 더보기 → 선 그래프 → 보는 방법
    선 그래프에는 막대 줄의 체크박스로 원하는 섹터를 넣고 뺄 수 있다.
    """
    구역, 시장 = _zone_series()
    if not 구역 or not 시장:
        return ""
    보유일 = len(set().union(*[set(v) for v in 구역.values()]) & set(시장))

    탭, 패널 = "", ""
    기본idx = 0   # 기본 탭은 5일 — 가장 최근 흐름부터 본다

    for idx, (n, 이름, 부제) in enumerate(ZONE_WINDOWS):
        통계 = []
        for nm, 일별 in 구역.items():
            st = _zone_stat(일별, 시장, n)
            if st:
                통계.append((nm,) + st)          # (nm, 초과, 수익, 승, 총, 곡선)
        통계.sort(key=lambda x: -x[1])

        if not 통계:
            필요 = ZONE_MIN.get(n, 5)
            비율 = min(100, 보유일 / 필요 * 100)
            패널 += (f'<div class="sb-panel" data-idx="{idx}" '
                    f'style="display:{"block" if idx == 기본idx else "none"}">'
                    '<div style="padding:16px 6px;text-align:center">'
                    f'<p style="margin:0 0 8px;font-size:12.5px;color:#c9ced6">'
                    f'{이름} 성적은 <b style="color:#f0c65a">{필요}거래일</b>이 쌓이면 열립니다</p>'
                    f'<div style="height:8px;background:#1b2230;border-radius:4px;overflow:hidden">'
                    f'<div style="width:{비율:.0f}%;height:100%;background:#f0c65a"></div></div>'
                    f'<p style="margin:7px 0 0;font-size:11.5px;color:#8b93a0">'
                    f'지금 <b style="color:#e8eaee">{보유일}일</b> 모았습니다 · '
                    f'{max(0, 필요-보유일)}거래일 남음</p></div></div>')
        else:
            # 순위와 무관하게 섹터마다 색이 고정된다(색이 곧 이름표).
            색맵 = {t[0]: sector_color(t[0]) for t in 통계}
            기본선 = set([t[0] for t in 통계[:3]] + [t[0] for t in 통계[-3:]])
            mx = max(abs(t[1]) for t in 통계) or 1

            줄 = []
            for i, (nm, 초, 수, 승, 총, _) in enumerate(통계):
                상위3, 하위3 = i < 3, i >= len(통계) - 3
                보임 = 상위3 or 하위3
                c = "#ff6b4a" if 초 >= 0 else "#5b9bff"
                wd = abs(초) / mx * 46
                바 = (f'<div style="position:absolute;left:50%;width:{wd:.1f}%;height:100%;'
                     f'background:{c};border-radius:0 3px 3px 0"></div>' if 초 >= 0 else
                     f'<div style="position:absolute;right:50%;width:{wd:.1f}%;height:100%;'
                     f'background:{c};border-radius:3px 0 0 3px"></div>')
                체크 = "checked" if nm in 기본선 else ""
                줄.append(
                    f'<div class="sb-row{"" if 보임 else " sb-more"}" data-zone="{nm}" '
                    f'style="display:{"flex" if 보임 else "none"};align-items:center;gap:6px;'
                    f'padding:5px 4px;border-bottom:1px solid #1b212c;border-radius:6px">'
                    f'<input type="checkbox" class="sb-ck" data-idx="{idx}" data-zone="{nm}" '
                    f'{체크} onchange="sbTog({idx})" '
                    f'style="flex:none;width:14px;height:14px;accent-color:{색맵[nm]};cursor:pointer">'
                    f'<div style="width:78px;flex:none;min-width:0">'
                    f'<div class="sb-name" style="font-size:11px;color:#e8eaee;font-weight:700;'
                    f'overflow:hidden;text-overflow:ellipsis;white-space:nowrap;'
                    f'border-radius:4px;padding:1px 3px">{nm}</div>'
                    f'<div style="font-size:9px;color:#7d848f">{승}승 {총-승}패 · {승/총*100:.0f}%</div></div>'
                    f'<div style="flex:1;position:relative;height:17px;background:#161b24;'
                    f'border-radius:3px;min-width:40px">'
                    f'<div style="position:absolute;left:50%;top:-2px;width:1px;height:21px;'
                    f'background:#3a4150"></div>{바}</div>'
                    f'<div style="width:48px;flex:none;text-align:right">'
                    f'<div style="font-size:11.5px;font-weight:800;color:{c}">{초:+.1f}%p</div>'
                    f'<div style="font-size:9px;color:#7d848f">{수:+.1f}%</div></div></div>')

            더보기 = ""
            숨김수 = len(통계) - len(기본선 & set(t[0] for t in 통계))
            숨김수 = max(0, len(통계) - 6)
            if 숨김수 > 0:
                더보기 = (f'<p onclick="sbMore(this)" style="margin:7px 0 0;font-size:11.5px;'
                        f'color:#e0c060;text-align:center;cursor:pointer;font-weight:700;'
                        f'-webkit-tap-highlight-color:transparent">'
                        f'▾ 나머지 {숨김수}개 더보기</p>')

            # ── 선 그래프 ──
            날짜 = [d for d, _ in 통계[0][5]]
            vals = [v for t in 통계 for _, v in t[5]]
            lo, hi = min(vals + [0]), max(vals + [0])
            # 오른쪽에 섹터명을 적을 자리를 남긴다(R을 크게).
            W, H, L, R, T, B = 420, 170, 30, 92, 14, 22
            def PX(i): return L + i * (W - L - R) / max(1, len(날짜) - 1)
            def PY(v): return T + (hi - v) / max(0.01, hi - lo) * (H - T - B)
            g = (f'<rect x="{L}" y="{T}" width="{W-L-R}" height="{PY(0)-T:.0f}" '
                 f'fill="#ff6b4a" opacity=".05"/>'
                 f'<rect x="{L}" y="{PY(0):.0f}" width="{W-L-R}" height="{H-B-PY(0):.0f}" '
                 f'fill="#5b9bff" opacity=".05"/>'
                 # 기준선이라 눈에 띄어야 한다 — 회색은 곡선에 묻힌다.
                 f'<line x1="{L}" y1="{PY(0):.0f}" x2="{W-R}" y2="{PY(0):.0f}" '
                 f'stroke="#ffffff" stroke-width="1.8" opacity=".85"/>'
                 # 0선 이름은 그림 안이 아니라 **오른쪽 라벨 열**에 둔다.
                 #   선 위에 겹쳐 쓰면 곡선과 부딪혀 읽히지 않는다.
                 f'<text class="sb-lab" data-idx="{idx}" data-zone="__mkt" '
                 f'data-y0="{PY(0):.1f}" x="{W-R+7}" y="{PY(0)+3:.1f}" font-size="8" '
                 f'fill="#ffffff" font-weight="700">시장 평균</text>'
                 f'<line class="sb-leader" data-idx="{idx}" data-zone="__mkt" '
                 f'x1="{W-R}" y1="{PY(0):.1f}" x2="{W-R+5}" y2="{PY(0):.1f}" '
                 f'stroke="#ffffff" stroke-width="0.7" opacity=".6" style="display:none"/>')
            for nm, 초, 수, 승, 총, 곡선 in 통계:
                pts = " ".join(f"{PX(i):.0f},{PY(v):.0f}" for i, (_, v) in enumerate(곡선))
                켬 = nm in 기본선
                _ey = PY(곡선[-1][1])   # 라벨 자리는 브라우저가 겹칠 때만 조정한다
                g += (f'<polyline class="sb-line" data-idx="{idx}" data-zone="{nm}" '
                      f'points="{pts}" fill="none" stroke="{색맵[nm]}" stroke-width="1.5" '
                      f'style="display:{"block" if 켬 else "none"}"/>'
                      f'<text class="sb-lab" data-idx="{idx}" data-zone="{nm}" '
                      f'data-y0="{_ey:.1f}" x="{W-R+7}" y="{_ey+3:.1f}" font-size="8.5" '
                      f'fill="{색맵[nm]}" style="display:{"block" if 켬 else "none"}">'
                      f'{nm[:8]}</text>'
                      f'<line class="sb-leader" data-idx="{idx}" data-zone="{nm}" '
                      f'x1="{W-R}" y1="{_ey:.1f}" x2="{W-R+5}" y2="{_ey:.1f}" '
                      f'stroke="{색맵[nm]}" stroke-width="0.7" opacity=".5" '
                      f'style="display:none"/>')
            for t in (hi, 0, lo):
                g += (f'<text x="{L-3}" y="{PY(t)+3:.0f}" text-anchor="end" font-size="8" '
                      f'fill="#6f7784">{t:+.0f}</text>')
            g += (f'<text x="{L}" y="{H-5}" font-size="8.5" fill="#6f7784">'
                  f'{날짜[0][4:6]}/{날짜[0][6:]}</text>'
                  f'<text x="{W-R}" y="{H-5}" text-anchor="end" font-size="8.5" fill="#6f7784">'
                  f'{날짜[-1][4:6]}/{날짜[-1][6:]}</text>')

            패널 += (f'<div class="sb-panel" data-idx="{idx}" '
                    f'data-lo="{T}" data-hi="{H-B+2}" '
                    f'style="display:{"block" if idx == 기본idx else "none"}">'
                    + "".join(줄) + 더보기
                    + '<p style="margin:11px 0 4px;font-size:10.5px;color:#8b93a0">'
                      '체크한 섹터가 아래 그래프에 들어갑니다</p>'
                    + f'<svg viewBox="0 0 {W} {H}" preserveAspectRatio="xMidYMid meet" '
                      f'style="width:100%;height:auto;display:block">{g}</svg>'
                    + '<p style="margin:5px 0 0;font-size:10px;color:#6f7784">'
                      '<b style="color:#8b93a0">점선</b> = 내 관심종목이 속한 섹터입니다</p>'
                    + '</div>')

        켬 = idx == 기본idx
        탭 += (f'<span class="sb-tab" data-idx="{idx}" onclick="sbTab({idx})" '
              f'style="flex:1;text-align:center;font-size:11px;padding:6px 0;border-radius:7px;'
              f'cursor:pointer;font-weight:{800 if 켬 else 600};'
              f'background:{"#2a3446" if 켬 else "#171c25"};'
              f'color:{"#f0c65a" if 켬 else "#7d848f"};'
              f'-webkit-tap-highlight-color:transparent">{부제}</span>')

    JS = """<script>
(function(){
 // ── 선택 섹터는 5·20·60일과 '시총별 섹터'까지 하나로 공유한다 ──
 //   기간 탭을 옮길 때마다 다시 체크하게 만들면 아무도 안 쓴다.
 window.CP_SECT = window.CP_SECT || null;
 function seed(){
  if(window.CP_SECT) return;
  // ⚠️ 초기 체크는 HTML의 checked 속성으로 판단해야 한다.
  //    .checked(프로퍼티)는 다른 패널의 같은 섹터를 훑는 도중 덮여
  //    전부 false가 될 수 있다(실제로 선이 하나도 안 보였다).
  var s={};
  document.querySelectorAll('.sb-ck').forEach(function(c){
   if(c.hasAttribute('checked')) s[c.dataset.zone]=1; });
  window.CP_SECT=s;
 }
 // 보이는 라벨만 모아 겹칠 때만 밀어낸다. 안 겹치면 선 옆에 그대로 둔다.
 function relayout(){
  document.querySelectorAll('.sb-panel').forEach(function(pnl){
   if(pnl.style.display==='none') return;
   var lo=parseFloat(pnl.dataset.lo||'0'), hi=parseFloat(pnl.dataset.hi||'0');
   var labs=[].filter.call(pnl.querySelectorAll('.sb-lab'),
     function(t){return t.style.display!=='none';});
   labs.sort(function(a,b){return parseFloat(a.dataset.y0)-parseFloat(b.dataset.y0);});
   // 겹치는 쌍만 **양쪽으로 반씩** 밀어낸다(한쪽으로만 밀면 위쪽에 뭉친다).
   var GAP=9.5;
   var ys=labs.map(function(t){return parseFloat(t.dataset.y0);});
   for(var it=0; it<40; it++){
    var moved=false;
    for(var k=0;k<ys.length-1;k++){
     var d=ys[k+1]-ys[k];
     if(d<GAP){var push=(GAP-d)/2; ys[k]-=push; ys[k+1]+=push; moved=true;}
    }
    // 경계를 넘으면 안쪽으로 되민다
    if(ys.length){
     if(ys[0]<lo+4){var sft=(lo+4)-ys[0]; ys=ys.map(function(y){return y+sft;}); moved=true;}
     if(ys[ys.length-1]>hi){var s2=ys[ys.length-1]-hi;
      ys=ys.map(function(y){return y-s2;}); moved=true;}
    }
    if(!moved) break;
   }
   // ⚠️ 라벨 수 × 간격이 차트 높이보다 크면 위 루프가 위·아래로 서로 밀며
   //    제자리로 돌아온다(실제로 반도체 라벨이 차트 밖 -6px에 남았다).
   //    그럴 때는 남는 공간에 균등 배치해서라도 전부 화면 안에 넣는다.
   var top=lo+5, bot=hi-2;
   if(ys.length){
    var need=(ys.length-1)*GAP;
    if(need > bot-top){
     var step=(bot-top)/Math.max(1,ys.length-1);
     for(var q=0;q<ys.length;q++) ys[q]=top+step*q;
    }else{
     if(ys[0]<top){var s3=top-ys[0]; ys=ys.map(function(y){return y+s3;});}
     if(ys[ys.length-1]>bot){var s4=ys[ys.length-1]-bot;
      ys=ys.map(function(y){return y-s4;});}
     for(var q2=0;q2<ys.length;q2++) ys[q2]=Math.min(bot,Math.max(top,ys[q2]));
    }
   }
   labs.forEach(function(t,i){
    var y=ys[i], y0=parseFloat(t.dataset.y0);
    t.setAttribute('y',(y+3).toFixed(1));
    var ld=pnl.querySelector('.sb-leader[data-zone="'+t.dataset.zone+'"]');
    if(ld){
     if(Math.abs(y-y0)>3){ld.setAttribute('y1',y0.toFixed(1));
      ld.setAttribute('y2',y.toFixed(1)); ld.style.display='block';}
     else{ld.style.display='none';}}});
  });
 }
 function apply(){
  var s=window.CP_SECT||{}, mz=(window.cpMyZones?cpMyZones():{});
  document.querySelectorAll('.sb-ck').forEach(function(c){ c.checked=!!s[c.dataset.zone]; });
  document.querySelectorAll('.sb-line').forEach(function(l){
   var on=!!s[l.dataset.zone];
   l.style.display=on?'block':'none';
   l.setAttribute('stroke-dasharray', mz[l.dataset.zone]?'6 3':'');
   l.setAttribute('stroke-width', mz[l.dataset.zone]?'2.4':'1.5');});
  document.querySelectorAll('.sb-lab').forEach(function(t){
   var z=t.dataset.zone;
   // '__'로 시작하는 것은 기준선 라벨 — 체크와 무관하게 항상 보인다.
   t.style.display=(z.indexOf('__')===0 || s[z])?'block':'none';
   t.setAttribute('font-weight', mz[z]?'800':'400');});
  relayout();
  document.querySelectorAll('.sb-row').forEach(function(r){
   var on=!!mz[r.dataset.zone], n=r.querySelector('.sb-name');
   // 줄 전체가 아니라 섹터 이름에만 테두리 — 표가 덜 요란해진다.
   r.style.background='transparent'; r.style.boxShadow='none';
   if(n){n.style.boxShadow=on?'inset 0 0 0 1.5px #f0c65a':'none';
         n.style.color='#e8eaee';}});
  var all=document.getElementById('sb-all');
  if(all){
   var names={}; document.querySelectorAll('.sb-ck').forEach(function(c){names[c.dataset.zone]=1;});
   all.checked = Object.keys(s).length>0 && Object.keys(s).length>=Object.keys(names).length;}
  if(window.slSync) slSync();
 }
 window.cpSectApply=apply;
 window.CP_PAINT=window.CP_PAINT||[]; window.CP_PAINT.push(apply);
 window.sbTab=function(i){
  document.querySelectorAll('.sb-panel').forEach(function(p){
   p.style.display=(p.dataset.idx==i)?'block':'none';});
  document.querySelectorAll('.sb-tab').forEach(function(t){
   var on=t.dataset.idx==i;
   t.style.background=on?'#2a3446':'#171c25';
   t.style.color=on?'#f0c65a':'#7d848f'; t.style.fontWeight=on?800:600;});
  apply();};
 window.sbTog=function(i){
  seed();
  document.querySelectorAll('.sb-ck[data-idx="'+i+'"]').forEach(function(c){
   if(c.checked){window.CP_SECT[c.dataset.zone]=1;} else {delete window.CP_SECT[c.dataset.zone];}});
  apply();};
 window.sbAll=function(el){
  seed(); var s={};
  if(el.checked){document.querySelectorAll('.sb-ck').forEach(function(c){s[c.dataset.zone]=1;});}
  window.CP_SECT=s; apply();};
 window.sbMore=function(el){
  var p=el.closest('.sb-panel'), h=p.querySelectorAll('.sb-more');
  var open=h.length&&h[0].style.display!=='none';
  h.forEach(function(r){r.style.display=open?'none':'flex';});
  el.textContent=open?('▾ 나머지 '+h.length+'개 더보기'):'▴ 접기';
  apply();};
 function boot(){seed(); apply();}
 if(document.readyState!=='loading'){boot()}else{
  document.addEventListener('DOMContentLoaded',boot)}
})();
</script>"""

    return ('<div style="background:#141922;border:1px solid #232a36;border-radius:12px;'
            'padding:13px 14px;margin:10px 0 0">'
            '<p style="margin:0 0 2px;font-size:11.5px;color:#8b93a0">섹터 성적표</p>'
            '<p style="margin:0 0 3px;font-size:17px;font-weight:800;color:#f2f4f7">'
            '어느 섹터가 시장을 이겼나 '
            '<span style="font-size:11.5px;font-weight:600;color:#8b93a0">'
            '· 시장 대비 초과수익률</span></p>'
            f'<div style="display:flex;gap:6px;margin:10px 0 8px">{탭}</div>'
            '<label style="display:flex;align-items:center;gap:6px;margin-bottom:6px;'
            'font-size:11px;color:#8b93a0;cursor:pointer">'
            '<input type="checkbox" id="sb-all" onchange="sbAll(this)" '
            'style="width:14px;height:14px;accent-color:#f0c65a;cursor:pointer">'
            '전체 선택 / 해제</label>'
            + 패널 +
            '<details style="margin:10px 0 0;padding:9px 10px;background:#0f131a;'
            'border-radius:8px;border:1px solid #1e2531">'
            '<summary style="font-size:11.5px;color:#e0c060;font-weight:700;'
            'cursor:pointer;list-style:none">📖 섹터 성적표 보는 방법 '
            '<span style="color:#6f7784;font-weight:600">(눌러서 펼치기)</span></summary>'
            '<p style="margin:6px 0 0;font-size:11px;color:#7d848f;line-height:1.65">'
            '<b style="color:#9aa0aa">%p(퍼센트포인트)</b>는 코스피보다 얼마나 더 벌었나입니다. '
            '가운데 세로선이 코스피(0), 오른쪽으로 뻗을수록 시장을 크게 이긴 섹터입니다.<br>'
            '<b style="color:#9aa0aa">승패</b>는 그 기간 하루하루 코스피를 이긴 날의 수입니다. '
            '초과수익이 커도 승률이 낮으면 <b style="color:#9aa0aa">며칠에 몰아서 번 것</b>이라 '
            '들고 있는 대부분의 날이 괴로웠다는 뜻입니다.<br>'
            '<b style="color:#9aa0aa">작은 회색 숫자</b>는 실제 수익률입니다. '
            '시장이 함께 내린 날은 이 값이 마이너스여도 시장을 이겼을 수 있습니다.<br>'
            '<b style="color:#9aa0aa">체크박스</b>를 켜고 끄면 아래 선 그래프에 넣고 뺄 수 있습니다. '
            '기본은 상위 3개와 하위 3개입니다.<br>'
            '<b style="color:#f0c65a">내 섹터가 아래쪽에 있다면</b> — 종목 선택이 아니라 '
            '<b style="color:#9aa0aa">자리</b>가 불리했다는 뜻입니다. '
            '그 섹터 안에서는 무엇을 골랐어도 시장을 이기기 어려웠습니다.'
            '</p></details></div>' + JS)


def build_crowd_compass(_구=None):
    """🧭 군중 나침반 — 개인이 사고 있나, 팔고 있나.

    ⚠️ v-l8에서 재설계했다.
      예전: 레버리지·인버스 ETF 개인 순매수(네이버 크롤링, 검증 불가)
      지금: **코스피+코스닥 개인 순매수**(market_history에 매일 저장 중, 검증됨)

    왜 바꿨나:
      · 레버리지 ETF는 개인 자금의 일부일 뿐이다. 개인 전체 수급이 훨씬 큰 그림이다.
      · 이미 매일 쌓고 있는 데이터라 새 크롤링도, 실패 위험도 없다.
      · 실탄(외국인+기관)과 정확히 반대편이라 "큰돈 vs 군중" 대비가 선명해진다.
    """
    try:
        with open("market_history.json", encoding="utf-8") as f:
            rows = (json.load(f) or {}).get("일별") or []
    except Exception:
        return ""
    seq = []
    for r in rows:
        a, b = r.get("개인_코스피"), r.get("개인_코스닥")
        if isinstance(a, (int, float)) or isinstance(b, (int, float)):
            seq.append((a or 0) + (b or 0))
    if len(seq) < 2:
        return ""
    오늘 = seq[-1]
    누적5 = sum(seq[-5:])
    누적20 = sum(seq[-20:])
    연속 = 1
    for v in reversed(seq[:-1]):
        if (v > 0) == (오늘 > 0):
            연속 += 1
        else:
            break

    def _억(v):
        return f"{v/10000:+.2f}조" if abs(v) >= 10000 else f"{v:+,.0f}억"

    사 = 오늘 > 0
    색 = "#ff6b4a" if 사 else "#5b9bff"
    if abs(오늘) < 1000:
        판정, 설명 = "관망하고 있습니다", "개인 자금이 어느 쪽으로도 크게 움직이지 않았습니다."
    elif 사:
        판정 = f"{연속}일 연속 사고 있습니다" if 연속 >= 2 else "오늘 샀습니다"
        설명 = ("개인이 받아내는 중입니다. 외국인·기관이 파는 물량을 개인이 받는 구도라면, "
              "쏠림이 커질수록 되돌림도 커집니다.")
    else:
        판정 = f"{연속}일 연속 팔고 있습니다" if 연속 >= 2 else "오늘 팔았습니다"
        설명 = ("개인이 내놓는 중입니다. 큰돈이 그 물량을 받고 있다면 바닥 다지기일 수 있고, "
              "같이 팔고 있다면 수급 공백입니다.")

    # 최근 20일 미니 막대 (컴팩트 — 큰 게이지 대신 흐름만)
    최근 = seq[-20:]
    mx = max(abs(v) for v in 최근) or 1
    막대 = ""
    for i, v in enumerate(최근):
        h = max(2, abs(v) / mx * 18)
        c = "#ff6b4a" if v >= 0 else "#5b9bff"
        # 0선을 가운데 두고 매수는 위, 매도는 아래로 뻗게 한다.
        #   (예전엔 flex 정렬만 바꿔 색과 방향이 어긋나 보였다)
        # ⚠️ flex 중첩으로 위/아래를 나누면 자식 높이가 0으로 눌린다(실제로 막대가 사라졌다).
        #    위·아래 칸 높이를 20px로 **고정**하고 그 안에서 정렬한다.
        불 = 0.95 if i == len(최근) - 1 else 0.55
        위 = (f'<div style="height:20px;display:flex;align-items:flex-end">'
             f'<div style="width:100%;height:{h:.0f}px;background:{c};'
             f'border-radius:1.5px 1.5px 0 0;opacity:{불}"></div></div>') if v >= 0 else \
            '<div style="height:20px"></div>'
        아래 = (f'<div style="height:20px;display:flex;align-items:flex-start">'
              f'<div style="width:100%;height:{h:.0f}px;background:{c};'
              f'border-radius:0 0 1.5px 1.5px;opacity:{불}"></div></div>') if v < 0 else \
             '<div style="height:20px"></div>'
        막대 += (f'<div style="flex:1;min-width:0">{위}'
               f'<div style="height:1px;background:#3a4150"></div>{아래}</div>')

    # ── 신용융자 잔고 (있으면 표시) ──
    #  ⚠️ 아직 수집원이 없다. data["신용잔고"]에 {"잔고": 억원, "증감": 억원}이 들어오면
    #     자동으로 켜진다. 없으면 이 블록은 통째로 빠진다(없는 걸 지어내지 않는다).
    신용HTML = ""
    신 = (_구 or {}) if isinstance(_구, dict) else {}
    잔고, 증감 = 신.get("잔고"), 신.get("증감")
    # 잔고 추이 — archive에서 과거 신용잔고를 모아 선으로 그린다.
    #   "지금 21.9조"보다 "3주째 늘고 있다"가 훨씬 중요한 정보다.
    _hist = []
    for _f in sorted(alist(r"data_\d{8}\.json"))[-40:]:
        try:
            with open(apath(_f), encoding="utf-8") as _fp:
                _v = (json.load(_fp).get("신용잔고") or {}).get("잔고")
            if isinstance(_v, (int, float)):
                _hist.append(_v)
        except Exception:
            continue
    추이HTML = ""
    if len(_hist) >= 3:
        _hi, _lo = max(_hist), min(_hist)
        _rng = max(1.0, _hi - _lo)
        _W, _H = 300, 42
        _pts = " ".join(f"{i*_W/(len(_hist)-1):.0f},{_H-4-(v-_lo)/_rng*(_H-10):.0f}"
                        for i, v in enumerate(_hist))
        _c = "#ff6b4a" if _hist[-1] >= _hist[0] else "#5b9bff"
        추이HTML = (f'<svg viewBox="0 0 {_W} {_H}" preserveAspectRatio="none" '
                  f'style="width:100%;height:42px;display:block;margin-top:7px">'
                  f'<polyline points="{_pts}" fill="none" stroke="{_c}" stroke-width="2"/>'
                  f'<circle cx="{_W}" cy="{_H-4-(_hist[-1]-_lo)/_rng*(_H-10):.0f}" r="3" '
                  f'fill="{_c}"/></svg>'
                  f'<p style="margin:2px 0 0;font-size:9.5px;color:#6f7784">'
                  f'최근 {len(_hist)}거래일 신용융자 잔고 추이 '
                  f'({_lo/10000:.1f}조 ~ {_hi/10000:.1f}조)</p>')
    if isinstance(잔고, (int, float)):
        c = "#ff6b4a" if (증감 or 0) >= 0 else "#5b9bff"
        증문 = f"{증감/10000:+.2f}조" if isinstance(증감, (int, float)) and abs(증감) >= 10000 \
              else (f"{증감:+,.0f}억" if isinstance(증감, (int, float)) else "—")
        해석 = ("빚내서 사는 돈이 늘고 있습니다. 상승에 대한 기대가 커진 만큼 "
              "되돌림이 오면 반대매매로 낙폭이 커질 수 있습니다."
              if (증감 or 0) >= 0 else
              "빚내서 산 돈이 줄고 있습니다. 부담이 덜어지는 중이지만, "
              "급격히 줄면 반대매매가 진행 중일 수도 있습니다.")
        신용HTML = ('<div style="margin-top:9px;padding:9px 10px;background:#191d26;'
                   'border-radius:8px">'
                   '<div style="display:flex;justify-content:space-between;align-items:center">'
                   '<span style="font-size:11.5px;color:#8b93a0">신용융자 잔고</span>'
                   f'<span style="font-size:13px;font-weight:800;color:#e8eaee">'
                   f'{잔고/10000:,.1f}조 <span style="color:{c};font-size:11.5px">'
                   f'{증문}</span></span></div>'
                   f'<p style="margin:5px 0 0;font-size:11px;color:#7d848f;line-height:1.6">'
                   f'{해석}</p>' + 추이HTML + '</div>')

    def _칸(라벨, v):
        c = "#ff6b4a" if v >= 0 else "#5b9bff"
        return (f'<div style="flex:1;background:#191d26;border-radius:8px;padding:7px 9px">'
                f'<p style="margin:0;font-size:10px;color:#8b93a0">{라벨}</p>'
                f'<p style="margin:2px 0 0;font-size:12.5px;font-weight:800;color:{c}">'
                f'{_억(v)}</p></div>')

    return ('<div style="background:#141922;border:1px solid #232a36;border-radius:12px;'
            'padding:13px 14px;margin:10px 0 0">'
            '<p style="margin:0 0 2px;font-size:11.5px;color:#8b93a0">군중 나침반</p>'
            '<p style="margin:0 0 8px;font-size:17px;font-weight:800;color:#f2f4f7">'
            '개인은 사고 있나, 팔고 있나</p>'
            f'<p style="margin:0 0 3px;font-size:15px;font-weight:800;color:{색}">{판정}</p>'
            f'<p style="margin:0 0 9px;font-size:11.5px;color:#c9ced6;line-height:1.6">{설명}</p>'
            '<div style="display:flex;gap:6px;margin-bottom:8px">'
            + _칸("오늘", 오늘) + _칸("최근 5일", 누적5) + _칸("최근 20일", 누적20) +
            '</div>'
            f'<div style="display:flex;gap:1.5px">{막대}</div>'
            '<p style="margin:4px 0 0;font-size:9.5px;color:#6f7784">'
            '최근 20거래일 개인 순매수 (위=매수 · 아래=매도)</p>'
            + 신용HTML +
            '<details style="margin:9px 0 0;padding:9px 10px;background:#0f131a;'
            'border-radius:8px;border:1px solid #1e2531">'
            '<summary style="font-size:11.5px;color:#e0c060;font-weight:700;'
            'cursor:pointer;list-style:none">📖 군중 나침반 보는 방법 '
            '<span style="color:#6f7784;font-weight:600">(눌러서 펼치기)</span></summary>'
            '<p style="margin:6px 0 0;font-size:11px;color:#7d848f;line-height:1.65">'
            '코스피와 코스닥에서 <b style="color:#9aa0aa">개인이 순매수한 금액</b>의 합계입니다.<br>'
            '<b style="color:#9aa0aa">실탄과 정확히 반대편</b>입니다 — 실탄은 외국인+기관(큰돈), '
            '나침반은 개인(군중)이라, 현물시장이 제로섬이라는 성질상 둘은 대체로 거울처럼 움직입니다.<br>'
            '<b style="color:#9aa0aa">개인이 연속으로 사는 구간</b>은 큰돈이 내놓는 물량을 '
            '개인이 받고 있다는 뜻입니다. 그 자체로 좋고 나쁨은 아니지만, '
            '길어질수록 되돌림 여지가 커진다고 읽는 편이 안전합니다.<br>'
            '<b style="color:#9aa0aa">신용융자 잔고</b>는 개인이 증권사에서 빌려 산 금액입니다. '
            '늘어나면 기대가 커진 것이고, 그만큼 하락 시 반대매매 압력도 커집니다.'
            '</p></details></div>')


def build_sector_radar():
    """관제 레이더(일간) — 중심에 가까울수록 주도력이 강하다. 화살표는 전날 대비 이동."""
    이력 = _sector_scores(2)
    if not 이력:
        return ""
    오늘날, 오늘맵 = 이력[-1]
    어제맵 = 이력[-2][1] if len(이력) >= 2 else {}
    이름들 = list(오늘맵.keys()) + [n for n in 어제맵 if n not in 오늘맵]
    if not 이름들:
        return ""
    배정 = _radar_slots(이름들)
    cx, cy = 175, 175
    권외 = 25.0                      # TOP6 밖이면 점수 미상 → 바깥쪽으로 둔다

    링 = "".join(f'<circle cx="{cx}" cy="{cy}" r="{RADAR_R*k/4:.0f}" fill="none" '
                 f'stroke="#2a3140" stroke-width="1"/>' for k in (1, 2, 3, 4))
    축 = ""
    for s in range(RADAR_슬롯):
        x, y = _polar(cx, cy, 0, s)
        축 += f'<line x1="{cx}" y1="{cy}" x2="{x:.0f}" y2="{y:.0f}" stroke="#232a36" stroke-width="1"/>'

    # ⚠️ 색 규칙(v-k4): 회색 점은 어두운 배경에서 거의 안 보였다.
    #    "제자리"도 오늘 주도권을 쥐고 있으면 봐야 하므로, 무채색 대신
    #    금색(유지)을 주고 접근=초록 / 이탈=보라로 대비를 키운다.
    #    (수급 색 규칙과 동일 계열: 좋아짐=초록, 빠짐=보라)
    점, 라벨, 자취 = "", "", ""
    최대접근 = (None, -999)
    최대이탈 = (None, -999)
    for _di, nm in enumerate(이름들):
        s = 배정[nm]
        오 = 오늘맵.get(nm, 권외)
        어 = 어제맵.get(nm, 권외)
        nx, ny = _polar(cx, cy, 오, s)
        ox, oy = _polar(cx, cy, 어, s)
        변화 = 오 - 어
        if 변화 > 2:
            색, 표식 = "#4ade80", "▲"      # 관제탑에 가까워짐
        elif 변화 < -2:
            색, 표식 = "#a78bfa", "▼"      # 멀어짐
        else:
            색, 표식 = "#f0c65a", "="      # 제자리 — 금색으로 또렷하게
        # 어제 자리는 속 빈 점으로, 오늘까지의 이동은 화살표 선으로 남긴다.
        if abs(변화) > 2:
            자취 += (f'<circle cx="{ox:.0f}" cy="{oy:.0f}" r="3.2" fill="none" '
                     f'stroke="{색}" stroke-width="1.4" opacity=".55"/>')
            자취 += (f'<line x1="{ox:.0f}" y1="{oy:.0f}" x2="{nx:.0f}" y2="{ny:.0f}" '
                     f'stroke="{색}" stroke-width="2.4" opacity=".8"/>')
        # 점을 키우고 어두운 테두리를 둘러 배경과 확실히 분리한다.
        # 레이더처럼 천천히 명멸시킨다. 섹터마다 시작 시점을 어긋나게 해
        # 한꺼번에 깜빡이지 않도록(=요란하지 않도록) 지연을 준다.
        _dly = f"{(_di * 0.37) % 3.2:.2f}s"
        점 += (f'<circle cx="{nx:.0f}" cy="{ny:.0f}" r="7" fill="{색}" '
               f'class="rdr-dot" style="animation-delay:{_dly}" '
               f'stroke="#0f131a" stroke-width="1.6"/>')
        lx, ly = _polar(cx, cy, -8, s)
        anc = "middle" if abs(lx - cx) < 20 else ("start" if lx > cx else "end")
        # 라벨이 그림 밖으로 잘리지 않게: 이름을 줄이고 x를 안쪽으로 붙든다.
        #   (긴 이름은 아래 '어제 대비 움직임' 표에서 전체를 볼 수 있다)
        짧 = re.sub(r"[\(（].*", "", nm).strip() or nm
        짧 = re.sub(r"\s*대표주$", "", 짧).strip() or 짧
        짧 = 짧[:5]
        lx = min(max(lx, 30), 320)
        라벨 += (f'<text x="{lx:.0f}" y="{ly+4:.0f}" text-anchor="{anc}" font-size="11" '
                 f'fill="#c9ced6" font-weight="600">{짧}'
                 f'<tspan fill="{색}" font-size="10.5"> {표식}</tspan></text>')
        if 변화 > 최대접근[1]:
            최대접근 = (f"{nm} {어:.0f} → {오:.0f}", 변화)
        if -변화 > 최대이탈[1]:
            최대이탈 = (f"{nm} {어:.0f} → {오:.0f}", -변화)

    # ── 어제 대비 움직임 표 (숫자로도 확인 가능하게) ──
    변동행 = []
    for nm in sorted(이름들, key=lambda n: -(오늘맵.get(n, 권외) - 어제맵.get(n, 권외))):
        오 = 오늘맵.get(nm, 권외)
        어 = 어제맵.get(nm, 권외)
        변화 = 오 - 어
        if abs(변화) < 0.5:
            c, 화 = "#f0c65a", "= 제자리"
        elif 변화 > 0:
            c, 화 = "#4ade80", f"▲ {변화:.0f} 가까워짐"
        else:
            c, 화 = "#a78bfa", f"▼ {abs(변화):.0f} 멀어짐"
        신규 = " 🆕" if (nm not in 어제맵 and nm in 오늘맵) else ""
        # 다리 ① — 이 현장이 '내 계좌 구역' 어느 줄인지 붙여준다.
        #   독자가 "소캠(SOCAMM)이 격자 어디지?"를 스스로 추측하지 않아도 되게.
        구역 = grid_slot_of(nm)
        구역HTML = (f'<div style="font-size:9.5px;color:#22d3ee;margin-top:1px">'
                  f'↳ {구역} 구역</div>') if 구역 else ''
        변동행.append(
            f'<div style="display:flex;justify-content:space-between;gap:8px;'
            f'padding:5px 0;border-bottom:1px solid #1b212c">'
            f'<div style="min-width:0"><span style="font-size:11.5px;color:#c9ced6">'
            f'{re.sub(r"[（(].*", "", nm).strip()[:11]}{신규}</span>{구역HTML}</div>'
            f'<span style="font-size:11.5px;font-weight:700;color:{c};white-space:nowrap">{화}</span></div>')
    변동표 = ('<div style="margin:10px 0 0;padding-top:8px;border-top:1px solid #232a36">'
              '<p style="margin:0 0 4px;font-size:11.5px;color:#8b93a0;font-weight:700">'
              '📊 어제 대비 움직임</p>' + "".join(변동행) + '</div>') if 변동행 else ""

    # 접근/이탈은 짝을 이루는 정보라 나란히 두는 편이 비교가 쉽다.
    #   좁은 화면에서 세로로 쌓이면 두 줄을 눈으로 왕복해야 해서 대비가 안 잡힌다.
    def _칸(제목, 값, 색):
        return (f'<div style="flex:1;min-width:0;background:#141922;border-radius:8px;'
                f'padding:8px 9px">'
                f'<p style="margin:0;font-size:10.5px;color:#8b93a0">{제목}</p>'
                f'<p style="margin:3px 0 0;font-size:12.5px;font-weight:700;color:{색};'
                f'word-break:keep-all;line-height:1.35">{값}</p></div>')
    접근값, 접근색 = ((최대접근[0], "#4ade80") if 최대접근[1] > 0.5 else ("오늘은 없음", "#6f7784"))
    이탈값, 이탈색 = ((최대이탈[0], "#a78bfa") if 최대이탈[1] > 0.5 else ("오늘은 없음", "#6f7784"))
    패널 = ('<div style="display:flex;gap:7px">'
            + _칸("가장 빠르게 접근", 접근값, 접근색)
            + _칸("가장 빠르게 이탈", 이탈값, 이탈색) + '</div>')

    return ('<div style="background:#141922;border:1px solid #232a36;border-radius:12px;'
            'padding:12px 14px;margin:10px 0 0">'
            '<p style="margin:0 0 2px;font-size:11.5px;color:#8b93a0">뜨는 현장</p>'
            '<p style="margin:0 0 8px;font-size:17px;font-weight:800;color:#f2f4f7">'
            '오늘 관제탑에 가까워진 섹터</p>'
            '<div style="display:flex;flex-wrap:wrap;gap:10px;align-items:center">'
            f'<svg width="350" height="300" viewBox="0 25 350 300" style="flex:none;max-width:100%">'
            f'{링}{축}'
            # 중심(관제탑)은 섹터 점과 절대 헷갈리면 안 된다.
            #   섹터 점이 쓰는 색(금색=제자리 / 초록=접근 / 보라=이탈)과 겹치지 않는
            #   청록(#22d3ee)을 중심 전용으로 배정하고, 모양도 조준 마커로 다르게 한다.
            f'<circle cx="{cx}" cy="{cy}" r="13" fill="none" stroke="#22d3ee" '
            f'stroke-width="1.3" opacity=".5"/>'
            f'<line x1="{cx-17}" y1="{cy}" x2="{cx+17}" y2="{cy}" stroke="#22d3ee" '
            f'stroke-width="1.1" opacity=".45"/>'
            f'<line x1="{cx}" y1="{cy-17}" x2="{cx}" y2="{cy+17}" stroke="#22d3ee" '
            f'stroke-width="1.1" opacity=".45"/>'
            f'<circle cx="{cx}" cy="{cy}" r="5.5" fill="#22d3ee" '
            f'stroke="#0f131a" stroke-width="1.5"/>'
            f'<text x="{cx}" y="{cy+26}" text-anchor="middle" font-size="9.5" '
            f'fill="#22d3ee" font-weight="700" opacity=".9">관제탑</text>'
            f'{자취}{점}{라벨}</svg>'
            f'<div style="flex:1;min-width:150px">{패널}</div></div>'
            + 변동표
            + '<details style="margin:10px 0 0;padding:9px 10px;background:#0f131a;'
              'border-radius:8px;border:1px solid #1e2531">'
              '<summary style="font-size:11.5px;color:#e0c060;font-weight:700;'
              'cursor:pointer;list-style:none">📖 뜨는 현장 보는 방법 '
              '<span style="color:#6f7784;font-weight:600">(눌러서 펼치기)</span></summary>'
              '<div style="height:6px"></div>'
              '<p style="margin:0;font-size:11px;color:#7d848f;line-height:1.65">'
              '<b style="color:#22d3ee">가운데 청록색 조준점이 관제탑</b>입니다. 섹터 점이 여기에 '
              '<b style="color:#9aa0aa">가까울수록 오늘 시장을 세게 끌고 갔다</b>는 뜻이고, '
              '바깥에 있을수록 뒤로 밀렸다는 뜻입니다.<br>'
              '<b style="color:#4ade80">초록 ▲</b> 어제보다 안쪽으로 들어옴 (달아오르는 중) · '
              '<b style="color:#a78bfa">보라 ▼</b> 바깥으로 밀림 (식는 중) · '
              '<b style="color:#f0c65a">금색 =</b> 어제와 비슷한 자리<br>'
              '<b style="color:#9aa0aa">속 빈 점 → 꽉 찬 점</b>으로 이어진 선이 '
              '어제 자리에서 오늘 자리까지 움직인 거리입니다. 선이 길수록 하루 사이 변화가 큽니다.'
              '</p></details>'
            + '<details style="margin:8px 0 0;padding:9px 10px;background:#141c1e;'
              'border-radius:8px;border:1px solid #1e3238">'
              '<summary style="font-size:11.5px;color:#22d3ee;font-weight:700;'
              'cursor:pointer;list-style:none">🔗 내 종목 구역과 함께 보는 법 '
              '<span style="color:#6f7784;font-weight:600">(눌러서 펼치기)</span></summary>'
              '<div style="height:6px"></div>'
              '<p style="margin:0;font-size:11px;color:#7d848f;line-height:1.65">'
              '두 그림은 <b style="color:#9aa0aa">축척이 다른 같은 지도</b>입니다. '
              '<b style="color:#9aa0aa">계좌 구역</b>은 안 바뀌는 <b style="color:#9aa0aa">주소</b>(내 종목이 사는 동네), '
              '<b style="color:#22d3ee">뜨는 현장</b>은 매일 바뀌는 '
              '<b style="color:#9aa0aa">사건 현장</b>(오늘 어디서 불이 났나)입니다. '
              '그래서 현장 이름 밑에 <b style="color:#22d3ee">↳ 어느 구역</b>인지를 적어뒀고, '
              '격자에서 불난 줄에는 🔥를 달았습니다.<br>'
              '<b style="color:#9aa0aa">계좌 구역</b>은 "얼마나 올랐나"(등락률)를, '
              '<b style="color:#9aa0aa">뜨는 현장</b>은 "얼마나 시장을 끌었나"(거래대금·확산도까지 합친 주도력)를 봅니다.<br>'
              '그래서 <b style="color:#ff6b4a">구역은 빨간데 현장에서는 바깥</b>이면 — '
              '올랐지만 <b style="color:#9aa0aa">돈이 붙지 않은 상승</b>이라 오래가기 어렵습니다.<br>'
              '반대로 <b style="color:#22d3ee">현장은 안쪽인데 구역은 옅다</b>면 — '
              '아직 덜 올랐는데 <b style="color:#9aa0aa">돈이 먼저 들어오는</b> 자리일 수 있습니다.<br>'
              '<b style="color:#9aa0aa">둘 다 강하면</b> 오늘의 진짜 주인공, '
              '<b style="color:#9aa0aa">둘 다 약하면</b> 굳이 쫓을 이유가 없는 자리입니다.'
              '</p></details>'
            + '<p style="margin:8px 0 0;font-size:11px;color:#6f7784;line-height:1.5">'
            '어제 주도 6위 밖이던 섹터는 바깥에서 출발한 것으로 표시됩니다</p></div>')


# ── 3. 경사선 (테마별 대형→중형→소형) ────────────────────────
def _tier_series():
    """archive에서 {섹터: {날짜: {대형·중형·소형 등락률}}} 을 만든다."""
    out = {}
    for f in sorted(alist(r"data_\d{8}\.json")):
        try:
            with open(apath(f), encoding="utf-8") as fp:
                d = json.load(fp)
        except Exception:
            continue
        날짜 = d.get("날짜")
        for r in ((d.get("계좌격자") or {}).get("행") or []):
            nm, 칸 = r.get("테마"), (r.get("칸") or {})
            vals = {t: (칸.get(t) or {}).get("등락률") for t in ("대형", "중형", "소형")}
            if nm and all(isinstance(v, (int, float)) for v in vals.values()):
                out.setdefault(nm, {})[날짜] = vals
    return out


def _tier_cum(일별, n):
    """최근 n거래일 누적 등락(대·중·소). 관측일이 모자라면 None."""
    날짜들 = sorted(일별)[-n:]
    if len(날짜들) < min(n, 3):
        return None
    acc = {}
    for t in ("대형", "중형", "소형"):
        c = 1.0
        for d in 날짜들:
            c *= (1 + 일별[d][t] / 100)
        acc[t] = round((c - 1) * 100, 2)
    return acc


# ── 🗺️ 순위 섹터맵 · 🔮 돌아올 섹터 (v-m1 신규) ──────────────
#  섹터별 '일별 순위'에서 체류·주기를 계산해 다음 순번을 가늠한다.
#  ⚠️ 예측이 아니라 순서 관찰이다. 주기는 자주 깨진다.
CYC_TOP = 5           # 상위 N위를 '주도권 안'으로 본다
CYC_WINS = [(20, "20일"), (60, "60일"), (120, "120일")]


def _cyc_rank():
    """{섹터: [일별 순위]} 와 날짜 목록. 초과수익 순으로 매일 순위를 매긴다."""
    구역, 시장 = _zone_series()
    if not 구역 or not 시장:
        return None, None, None
    날짜 = sorted(set().union(*[set(v) for v in 구역.values()]) & set(시장))
    if len(날짜) < 5:
        return None, None, None
    이름 = sorted(구역)
    순위 = {n: [] for n in 이름}
    초과 = {n: [] for n in 이름}
    for d in 날짜:
        오늘 = [(n, 구역[n][d] - 시장[d]) for n in 이름 if d in 구역[n]]
        오늘.sort(key=lambda x: -x[1])
        있는 = {n: i + 1 for i, (n, _) in enumerate(오늘)}
        for n in 이름:
            순위[n].append(있는.get(n))
            초과[n].append(dict(오늘).get(n))
    return 날짜, 순위, 초과


def _cyc_stat(rk):
    """상위권 체류·등판 주기·이탈 후 경과."""
    구간, cur = [], None
    for i, r in enumerate(rk):
        if r is not None and r <= CYC_TOP:
            cur = i if cur is None else cur
        elif cur is not None:
            구간.append((cur, i - 1)); cur = None
    if cur is not None:
        구간.append((cur, len(rk) - 1))
    체류 = [b - a + 1 for a, b in 구간]
    간격 = [구간[k + 1][0] - 구간[k][0] for k in range(len(구간) - 1)]
    return {"회수": len(구간),
            "평균체류": (sum(체류) / len(체류)) if 체류 else 0,
            "평균주기": (sum(간격) / len(간격)) if 간격 else None,
            "경과": (len(rk) - 1 - 구간[-1][1]) if 구간 else len(rk),
            "현재": rk[-1]}


def build_sector_map():
    """🗺️ 순위 섹터맵 — 주도권이 어떻게 돌았나."""
    날짜, 순위, 초과 = _cyc_rank()
    if not 날짜:
        return ""
    이름 = sorted(순위)
    탭, 패널 = "", ""
    for idx, (n, lab) in enumerate(CYC_WINS):
        켬 = idx == 0
        if len(날짜) < 5:
            continue
        # ⚠️ 이력이 창 길이에 못 미치면 60일 탭과 120일 탭이 똑같은 그림이 된다.
        #    같은 걸 두 번 보여주면 "대충 만들었네"로 읽힌다 → 솔직히 남은 일수를 알린다.
        if len(날짜) < n * 0.9:
            패널 += (f'<div class="sm-panel" data-idx="{idx}" '
                    f'style="display:{"block" if 켬 else "none"};padding:18px 6px;'
                    f'text-align:center">'
                    f'<p style="margin:0 0 8px;font-size:12.5px;color:#c9ced6">'
                    f'{lab} 섹터맵은 <b style="color:#f0c65a">{n}거래일</b>이 쌓이면 열립니다</p>'
                    f'<div style="height:8px;background:#1b2230;border-radius:4px;overflow:hidden">'
                    f'<div style="width:{min(100, len(날짜)/n*100):.0f}%;height:100%;'
                    f'background:#f0c65a"></div></div>'
                    f'<p style="margin:7px 0 0;font-size:11.5px;color:#8b93a0">'
                    f'지금 <b style="color:#e8eaee">{len(날짜)}일</b> 모았습니다 · '
                    f'{n-len(날짜)}거래일 남음</p></div>')
            탭 += (f'<span class="sm-tab" data-idx="{idx}" onclick="smTab({idx})" '
                  f'style="flex:1;text-align:center;font-size:11px;padding:6px 0;'
                  f'border-radius:7px;cursor:pointer;font-weight:{800 if 켬 else 600};'
                  f'background:{"#2a3446" if 켬 else "#171c25"};'
                  f'color:{"#f0c65a" if 켬 else "#7d848f"}">{lab}</span>')
            continue
        take = min(n, len(날짜))
        def 누적(nm):
            c = 1.0
            for v in 초과[nm][-take:]:
                if v is not None:
                    c *= (1 + v / 100)
            return (c - 1) * 100
        순 = sorted(이름, key=lambda x: -누적(x))
        rows = ""
        for nm in 순:
            rk = 순위[nm][-take:]
            cells = ""
            for i, r in enumerate(rk):
                if r is None:      c, o = "#242a34", 1.0
                elif r <= 3:       c, o = sector_color(nm), 1.0
                elif r <= 6:       c, o = sector_color(nm), 0.4
                else:              c, o = "#242a34", 1.0
                gap = ";margin-right:2px" if (i + 1) % 5 == 0 and i < len(rk) - 1 else ""
                cells += (f'<div style="flex:1;height:13px;background:{c};opacity:{o};'
                          f'border-radius:1px{gap}"></div>')
            rows += (f'<div class="sm-row" data-zone="{nm}" '
                     f'style="display:flex;align-items:center;gap:6px;margin-bottom:3px">'
                     f'<span class="sm-name" style="width:78px;flex:none;min-width:0;font-size:10px;'
                     f'text-align:right;font-weight:600;color:#e8eaee;padding:1px 3px;'
                     f'border-radius:4px;overflow:hidden;text-overflow:ellipsis;'
                     f'white-space:nowrap">{nm}</span>'
                     f'<div style="flex:1;min-width:0;display:flex;gap:1px">{cells}</div>'
                     f'<span style="width:38px;flex:none;text-align:right;font-size:10px;'
                     f'font-weight:800;color:{"#ff6b4a" if 누적(nm)>=0 else "#5b9bff"}">'
                     f'{누적(nm):+.1f}</span></div>')
        주 = max(1, take // 5)
        눈금 = "".join(f'<span style="flex:1;text-align:center">{주-k}주</span>'
                      for k in range(0, 주, max(1, 주 // 5)))
        패널 += (f'<div class="sm-panel" data-idx="{idx}" '
                f'style="display:{"block" if 켬 else "none"}">{rows}'
                f'<div style="display:flex;gap:6px;margin-top:5px">'
                f'<span style="width:78px;flex:none"></span>'
                f'<div style="flex:1;display:flex;font-size:8.5px;color:#6f7784">{눈금}</div>'
                f'<span style="width:38px;flex:none;text-align:right;font-size:8.5px;'
                f'color:#6f7784">누적%p</span></div></div>')
        탭 += (f'<span class="sm-tab" data-idx="{idx}" onclick="smTab({idx})" '
              f'style="flex:1;text-align:center;font-size:11px;padding:6px 0;border-radius:7px;'
              f'cursor:pointer;font-weight:{800 if 켬 else 600};'
              f'background:{"#2a3446" if 켬 else "#171c25"};'
              f'color:{"#f0c65a" if 켬 else "#7d848f"}">{lab}</span>')

    JS = """<script>
(function(){
 function paint(){var mz=(window.cpMyZones?cpMyZones():{});
  document.querySelectorAll('.sm-row').forEach(function(r){
   var n=r.querySelector('.sm-name'), on=!!mz[r.dataset.zone];
   if(n){n.style.boxShadow=on?'inset 0 0 0 1.3px #f0c65a':'none';
         n.style.fontWeight=on?800:600;}});}
 window.CP_PAINT=window.CP_PAINT||[]; window.CP_PAINT.push(paint);
 window.smTab=function(i){
  document.querySelectorAll('.sm-panel').forEach(function(p){
   p.style.display=(p.dataset.idx==i)?'block':'none';});
  document.querySelectorAll('.sm-tab').forEach(function(t){
   var on=t.dataset.idx==i;
   t.style.background=on?'#2a3446':'#171c25';
   t.style.color=on?'#f0c65a':'#7d848f'; t.style.fontWeight=on?800:600;});
  paint();};
 if(document.readyState!=='loading'){paint()}else{
  document.addEventListener('DOMContentLoaded',paint)}
})();
</script>"""
    return ('<div style="background:#141922;border:1px solid #232a36;border-radius:12px;'
            'padding:13px 14px;margin:10px 0 0">'
            '<p style="margin:0 0 2px;font-size:11.5px;color:#8b93a0">순위 섹터맵</p>'
            '<p style="margin:0 0 10px;font-size:17px;font-weight:800;color:#f2f4f7">'
            '주도권이 어떻게 돌았나</p>'
            f'<div style="display:flex;gap:6px;margin-bottom:9px">{탭}</div>' + 패널 +
            '<p style="margin:9px 0 0;font-size:11px;color:#7d848f;line-height:1.6">'
            '<b style="color:#c9ced6">진한 색 = 상위 3위</b> · 연한 색 = 4~6위 · 회색 = 하위권<br>'
            '섹터는 <b>그 기간 누적 초과수익이 높은 순</b>으로 정렬 · 가로 눈금은 <b>주 단위</b><br>'
            '<b style="color:#f0c65a">금색 테두리</b> = 내 관심종목이 속한 섹터</p>'
            '</div>' + JS)


def build_return_sector():
    """🔮 돌아올 섹터 — 주기로 본 다음 순번."""
    날짜, 순위, _ = _cyc_rank()
    if not 날짜:
        return ""
    ST = {n: _cyc_stat(순위[n]) for n in 순위}

    def 위상(n):
        s = ST[n]
        return None if not s["평균주기"] else min(1.25, s["경과"] / s["평균주기"])

    def dday(n):
        s = ST[n]
        if not s["평균주기"]:
            return None
        if s["현재"] is not None and s["현재"] <= CYC_TOP:
            return 0
        return max(0, round(s["평균주기"] - s["경과"]))

    def 그룹(n):
        s = ST[n]
        if s["현재"] is not None and s["현재"] <= CYC_TOP:
            return "지금"
        d = dday(n)
        return "임박" if d == 0 else "대기"

    # 순서: 임박(곧 온다) → 대기(언제 오나) → 지금(이미 와 있다)
    GRP = [("임박", "임박 섹터", "#ff6b4a", "평균 주기를 이미 넘겼습니다"),
           ("대기", "대기 섹터", "#5b9bff", "아직 순번이 오지 않았습니다"),
           ("지금", "지금 섹터", "#4ade80", "이미 상위권 안에 있습니다")]
    본문 = ""
    for key, 라벨, 색, 설명 in GRP:
        멤버 = [n for n in 순위 if 그룹(n) == key]
        if not 멤버:
            continue
        if key == "대기":
            멤버.sort(key=lambda n: (dday(n) if dday(n) is not None else 999))
        else:
            멤버.sort(key=lambda n: -(위상(n) or 0))
        rows = ""
        for nm in 멤버:
            c = sector_color(nm); p = min(1.25, (위상(nm) or 0)); pos = p / 1.25 * 100
            d = dday(nm)
            뱃 = "지금" if key == "지금" else ("임박" if key == "임박" else
                                          (f"D-{d}" if d else "—"))
            _s = ST[nm]
            if _s["평균주기"]:
                _차 = _s["경과"] - _s["평균주기"]
                _차문 = (f'<b style="color:#ff6b4a">+{_차:.0f}일 초과</b>' if _차 >= 0
                       else f'<b style="color:#5b9bff">{-_차:.0f}일 남음</b>')
                주기문 = (f'평균 주기 <b style="color:#c9ced6">{_s["평균주기"]:.0f}일</b> · '
                       f'이탈 후 {_s["경과"]}일 · {_차문}')
            else:
                주기문 = f'등판 {_s["회수"]}회 — 주기를 말하기엔 표본이 적습니다'
            rows += (f'<div class="rs-row" data-zone="{nm}" '
                     f'style="display:flex;align-items:center;gap:7px;margin-bottom:5px">'
                     f'<span class="rs-name" style="width:88px;flex:none;min-width:0;'
                     f'font-size:10.5px;font-weight:600;color:#e8eaee;text-align:right;'
                     f'padding:1px 3px;border-radius:4px;overflow:hidden;'
                     f'text-overflow:ellipsis;white-space:nowrap">{nm}</span>'
                     f'<div style="flex:1;min-width:0;position:relative;height:14px;'
                     f'background:#0f131a;border-radius:7px;overflow:hidden">'
                     f'<div style="position:absolute;left:80%;right:0;top:0;bottom:0;'
                     f'background:#f0c65a;opacity:.13"></div>'
                     f'<div style="position:absolute;left:0;width:{pos:.0f}%;top:0;bottom:0;'
                     f'background:{c};opacity:.55"></div>'
                     f'<div style="position:absolute;left:calc({pos:.0f}% - 6px);top:1px;'
                     f'width:12px;height:12px;border-radius:6px;background:{c};'
                     f'box-shadow:0 0 0 1.5px #141922"></div></div>'
                     f'<span style="width:34px;flex:none;text-align:right;font-size:10.5px;'
                     f'font-weight:800;color:{색};white-space:nowrap">{뱃}</span></div>'
                     f'<p style="margin:-2px 0 6px 95px;font-size:9.5px;color:#7d848f">'
                     f'{주기문}</p>')
        본문 += (f'<div style="margin-bottom:12px">'
                f'<div style="display:flex;align-items:baseline;gap:7px;margin-bottom:6px">'
                f'<span style="font-size:12.5px;font-weight:800;color:{색}">{라벨}</span>'
                f'<span style="font-size:10px;color:#6f7784">{len(멤버)}개 · {설명}</span></div>'
                f'{rows}</div>')
    if not 본문:
        return ""

    # 도달 지점(80%)을 전 섹터에 걸쳐 세로 점선 한 줄로 잇는다 —
    #   막대마다 따로 있으면 "공통 기준선"이라는 게 안 읽힌다.
    JS = """<script>
(function(){
 function line(){
  var host=document.getElementById('rs-body'); if(!host) return;
  var old=document.getElementById('rs-line'); if(old) old.remove();
  var ol=document.getElementById('rs-lab'); if(ol) ol.remove();
  var rows=host.querySelectorAll('.rs-row'); if(!rows.length) return;
  var track=rows[0].children[1];
  var hb=host.getBoundingClientRect(), tb=track.getBoundingClientRect();
  var x=tb.left-hb.left+tb.width*0.8;
  var first=rows[0].getBoundingClientRect(), last=rows[rows.length-1].getBoundingClientRect();
  var top=first.top-hb.top, bot=last.bottom-hb.top;
  var el=document.createElement('div'); el.id='rs-line';
  el.style.cssText='position:absolute;left:'+x+'px;top:'+top+'px;height:'+(bot-top)+
   'px;width:0;border-left:1.5px dashed #f0c65a;opacity:.75;pointer-events:none';
  host.appendChild(el);
  // 라벨은 선(el)이 아니라 host에 붙인다 — 폭 0인 선에 붙이면 밖으로 삐져나간다.
  var lab=document.createElement('div'); lab.id='rs-lab';
  // 마지막 행 설명글과 겹치지 않게 선 '위쪽'에 붙인다.
  lab.style.cssText='position:absolute;left:'+Math.max(0,x-28)+'px;top:'+Math.max(0,top-13)+
   'px;font-size:8.5px;color:#f0c65a;pointer-events:none;white-space:nowrap';
  lab.textContent='도달 지점'; host.appendChild(lab);
 }
 function paint(){var mz=(window.cpMyZones?cpMyZones():{});
  document.querySelectorAll('.rs-row').forEach(function(r){
   var n=r.querySelector('.rs-name'), on=!!mz[r.dataset.zone];
   if(n){n.style.boxShadow=on?'inset 0 0 0 1.3px #f0c65a':'none';
         n.style.fontWeight=on?800:600;}});
  line();}
 window.CP_PAINT=window.CP_PAINT||[]; window.CP_PAINT.push(paint);
 window.addEventListener('resize',line);
 if(document.readyState!=='loading'){paint()}else{
  document.addEventListener('DOMContentLoaded',paint)}
})();
</script>"""
    return ('<div style="background:#141922;border:1px solid #232a36;border-radius:12px;'
            'padding:13px 14px;margin:10px 0 0">'
            '<p style="margin:0 0 2px;font-size:11.5px;color:#8b93a0">돌아올 섹터</p>'
            '<p style="margin:0 0 11px;font-size:17px;font-weight:800;color:#f2f4f7">'
            '다음 순번은 어디인가</p>'
            f'<div id="rs-body" style="position:relative;padding-top:14px">{본문}</div>'
            '<p style="margin:14px 0 0;font-size:11px;color:#7d848f;line-height:1.6">'
            '막대는 <b style="color:#c9ced6">주기 트랙</b>입니다 — 왼쪽 끝이 상위권에서 빠진 날, '
            '<b style="color:#f0c65a">노란 세로 점선</b>이 평균 주기에 도달하는 지점입니다.<br>'
            '표식이 점선을 넘으면 <b style="color:#ff6b4a">임박</b>입니다.<br>'
            '⚠️ <b style="color:#9aa0aa">예측이 아니라 순서 관찰</b>입니다. 주기는 자주 깨집니다.</p>'
            '</div>' + JS)


# ── 🛬 포착 항로 (v-m2 재설계) ────────────────────────────
#  구조: 기간 탭(20·60·120일) × 시장 카드(코스피·코스닥)
#        각 카드에 [강세 레이더 평균] [매집 레이더 평균] [해당 지수] 세 곡선을 겹친다.
#  ⚠️ 코스피 종목은 코스피와, 코스닥 종목은 코스닥과 비교해야 한다.
#     지수를 섞으면 변동폭이 큰 코스닥이 불리하게 보인다.
CAP_WINS = [(20, "20일"), (60, "60일"), (120, "120일")]
CAP_KINDS = [("강세", "강세레이더", "#ff6b4a"), ("매집", "매집레이더", "#4ade80")]


def _cap_curves(일수, 시장):
    """{종류: {경과: 평균등락}} 과 지수 벤치마크 {경과: 평균등락}."""
    파일들 = sorted(alist(r"data_\d{8}\.json"))[-일수:]
    종가 = _index_close_map()
    날짜들 = sorted(종가)
    _idx = 1 if 시장 == "코스닥" else 0
    곡선 = {k: {} for k, _, _ in CAP_KINDS}
    벤치 = {}
    쌍 = {k: {} for k, _, _ in CAP_KINDS}
    for f in 파일들:
        try:
            with open(apath(f), encoding="utf-8") as fp:
                d = json.load(fp)
        except Exception:
            continue
        for 라벨, 키, _c in CAP_KINDS:
            for t in ((d.get(키) or {}).get("추적") or []):
                g, r = t.get("경과"), t.get("이후등락")
                if not (isinstance(g, int) and isinstance(r, (int, float))):
                    continue
                if t.get("시장") != 시장:
                    continue
                쌍[라벨][(t.get("종목명"), t.get("포착일"))] = (g, r, t.get("포착일"))
    for 라벨 in 곡선:
        for g, r, 포착일 in 쌍[라벨].values():
            곡선[라벨].setdefault(g, []).append(r)
            if 포착일 in 종가:
                try:
                    i0 = 날짜들.index(포착일)
                except ValueError:
                    continue
                i1 = i0 + g
                if i1 < len(날짜들):
                    a, b = 종가[날짜들[i0]][_idx], 종가[날짜들[i1]][_idx]
                    if isinstance(a, (int, float)) and isinstance(b, (int, float)) and a:
                        벤치.setdefault(g, []).append((b - a) / a * 100)
    평 = {k: {g: sum(v) / len(v) for g, v in 곡선[k].items()} for k in 곡선}
    벤평 = {g: sum(v) / len(v) for g, v in 벤치.items()}
    수 = {k: len(쌍[k]) for k in 쌍}
    return 평, 벤평, 수


def _cap_card(일수, 시장):
    평, 벤, 수 = _cap_curves(일수, 시장)
    Ds = sorted(set().union(*[set(평[k]) for k in 평]) | set(벤)) if any(평.values()) else []
    Ds = [d for d in Ds if d <= 20]
    if len(Ds) < 3:
        return (f'<div style="padding:14px 6px;text-align:center;font-size:11.5px;color:#7d848f">'
                f'{시장} — 추적 이력이 아직 부족합니다 · 축적 중</div>')
    vals = [v for k in 평 for g, v in 평[k].items() if g in Ds] + [벤[g] for g in Ds if g in 벤]
    hi, lo = max(vals + [0]), min(vals + [0])
    rng = max(0.5, hi - lo)
    W, H, L, R, T, B = 380, 165, 30, 60, 12, 22
    def PX(i): return L + i * (W - L - R) / max(1, len(Ds) - 1)
    def PY(v): return T + (hi - v) / rng * (H - T - B)
    g = (f'<line x1="{L}" y1="{PY(0):.0f}" x2="{W-R}" y2="{PY(0):.0f}" stroke="#3a4150" '
         f'stroke-dasharray="4 3"/>'
         f'<text x="{L+2}" y="{PY(0)-4:.0f}" font-size="8" fill="#6f7784">0%</text>')
    if len([d for d in Ds if d in 벤]) >= 3:
        pts = " ".join(f"{PX(i):.0f},{PY(벤[d]):.0f}" for i, d in enumerate(Ds) if d in 벤)
        g += (f'<polyline points="{pts}" fill="none" stroke="#8b93a0" stroke-width="2" '
              f'stroke-dasharray="6 4"/>')
        _lv = [벤[d] for d in Ds if d in 벤][-1]
        라벨y = {"__idx": (PY(_lv), "#8b93a0", None)}
    else:
        라벨y = {}
    for 라벨, _키, c in CAP_KINDS:
        pt = [(i, d) for i, d in enumerate(Ds) if d in 평[라벨]]
        if len(pt) < 3:
            continue
        pts = " ".join(f"{PX(i):.0f},{PY(평[라벨][d]):.0f}" for i, d in pt)
        g += f'<polyline points="{pts}" fill="none" stroke="{c}" stroke-width="2.4"/>'
        라벨y[라벨] = (PY(평[라벨][pt[-1][1]]), c, 평[라벨][pt[-1][1]])
    # 오른쪽 끝 라벨(강세·매집·지수)이 포개지지 않게 최소 11px 간격을 강제한다.
    ys = sorted(라벨y.items(), key=lambda x: x[1][0])
    prev = None
    for 라벨, (y, c, v) in ys:
        y2 = y if prev is None else max(y, prev + 11)
        prev = y2
        글 = 시장 if 라벨 == "__idx" else f'{라벨} {v:+.1f}%'
        굵 = "400" if 라벨 == "__idx" else "700"
        g += (f'<text x="{W-R+5}" y="{y2+3:.0f}" font-size="8.5" fill="{c}" '
              f'font-weight="{굵}">{글}</text>')
    for i, d in enumerate(Ds):
        if i % max(1, len(Ds) // 5) == 0:
            g += (f'<text x="{PX(i):.0f}" y="{H-6}" text-anchor="middle" font-size="8.5" '
                  f'fill="#6f7784">D+{d}</text>')
    요약 = ""
    for 라벨, _키, c in CAP_KINDS:
        if not 평[라벨]:
            continue
        마지막 = 평[라벨][max(평[라벨])]
        벤끝 = 벤.get(max(평[라벨]))
        초 = (마지막 - 벤끝) if isinstance(벤끝, (int, float)) else None
        요약 += (f'<div style="flex:1;background:#161b24;border-radius:8px;padding:7px 8px">'
               f'<p style="margin:0;font-size:10px;color:{c};font-weight:800">{라벨} 레이더</p>'
               f'<p style="margin:2px 0 0;font-size:12px;font-weight:800;color:#e8eaee">'
               f'{마지막:+.1f}%</p>'
               f'<p style="margin:1px 0 0;font-size:9px;color:#7d848f">'
               f'{수[라벨]}건'
               + (f' · 초과 <b style="color:{"#4ade80" if 초>=0 else "#a78bfa"}">{초:+.1f}%p</b>'
                  if 초 is not None else '') + '</p></div>')
    return (f'<p style="margin:10px 0 5px;font-size:12px;font-weight:800;color:#c9ced6">'
            f'{시장}</p>'
            f'<svg viewBox="0 0 {W} {H}" preserveAspectRatio="xMidYMid meet" '
            f'style="width:100%;height:auto;display:block">{g}</svg>'
            f'<div style="display:flex;gap:6px;margin-top:5px">{요약}</div>')


def build_capture_paths():
    """포착 항로 — 기간 탭 × 코스피/코스닥 카드."""
    탭, 패널 = "", ""
    있음 = False
    for idx, (n, lab) in enumerate(CAP_WINS):
        켬 = idx == 0
        본문 = _cap_card(n, "코스피") + _cap_card(n, "코스닥")
        if "축적 중" not in 본문:
            있음 = True
        패널 += (f'<div class="cp-panel" data-idx="{idx}" '
                f'style="display:{"block" if 켬 else "none"}">{본문}</div>')
        탭 += (f'<span class="cp-tab" data-idx="{idx}" onclick="cpTab({idx})" '
              f'style="flex:1;text-align:center;font-size:11px;padding:6px 0;border-radius:7px;'
              f'cursor:pointer;font-weight:{800 if 켬 else 600};'
              f'background:{"#2a3446" if 켬 else "#171c25"};'
              f'color:{"#f0c65a" if 켬 else "#7d848f"}">{lab}</span>')
    JS = """<script>
window.cpTab=function(i){
 document.querySelectorAll('.cp-panel').forEach(function(p){
  p.style.display=(p.dataset.idx==i)?'block':'none';});
 document.querySelectorAll('.cp-tab').forEach(function(t){
  var on=t.dataset.idx==i;
  t.style.background=on?'#2a3446':'#171c25';
  t.style.color=on?'#f0c65a':'#7d848f'; t.style.fontWeight=on?800:600;});};
</script>"""
    return ('<div style="background:#141922;border:1px solid #232a36;border-radius:12px;'
            'padding:13px 14px;margin:10px 0 0">'
            '<p style="margin:0 0 2px;font-size:11.5px;color:#8b93a0">포착 항로</p>'
            '<p style="margin:0 0 10px;font-size:17px;font-weight:800;color:#f2f4f7">'
            '레이더가 잡은 종목들, 그 뒤</p>'
            f'<div style="display:flex;gap:6px;margin-bottom:4px">{탭}</div>' + 패널 +
            '<p style="margin:10px 0 0;font-size:11px;color:#7d848f;line-height:1.6">'
            '가로축은 <b style="color:#c9ced6">포착 후 며칠(D+N)</b>, 세로축은 '
            '<b style="color:#c9ced6">포착가 대비 등락률</b>입니다. '
            '가로 점선(0%) 위면 오른 것입니다. '
            '탭은 <b>얼마나 과거까지의 포착을 모을지</b>를 정합니다.<br>'
            '<span style="color:#ff6b4a">━</span> 강세 레이더 · '
            '<span style="color:#4ade80">━</span> 매집 레이더 · '
            '<span style="color:#8b93a0">┅</span> 같은 기간 지수<br>'
            '코스피 종목은 코스피와, 코스닥 종목은 코스닥과 비교합니다 — '
            '변동폭이 다른 두 시장을 섞으면 비교가 왜곡됩니다.<br>'
            '⚠️ 포착은 추천이 아니라 <b style="color:#9aa0aa">지표 성능 공시</b>입니다. '
            '틀린 사례도 지우지 않습니다.</p></div>' + JS)


def build_slope_chart(격자):
    """📐 시총별 섹터 — 같은 섹터라도 대형·중형·소형 중 어디가 끌었나.

    v-l9 변경:
      · 5/20/60일 탭 (섹터 성적표와 같은 창 구성)
      · 섹터마다 색 고정, 내 관심종목 섹터는 금색 점선
      · 시장 평균선은 흰 점선(금색은 '내 섹터' 전용이라 양보)
    """
    이력 = _tier_series()
    if not 이력:
        return ""

    # 오른쪽에 섹터명을 적으므로 소형 지점을 왼쪽으로 당기고 폭을 넓힌다.
    # 왼쪽 여백을 없앤다 — 예전엔 라벨을 왼쪽에 뒀던 흔적으로 96px이 비어 있었다.
    #   지금은 이름을 오른쪽 끝에 적으므로 왼쪽은 축부터 바로 시작해도 된다.
    W, H, T, B = 440, 250, 34, 30
    X = {"대형": 38, "중형": 189, "소형": 340}
    탭, 패널 = "", ""
    기본idx = 0   # 기본 탭은 5일 — 가장 최근 흐름부터 본다

    for idx, (n, 이름, 부제) in enumerate(ZONE_WINDOWS):
        누적 = {}
        for nm, 일별 in 이력.items():
            c = _tier_cum(일별, n)
            if c:
                누적[nm] = c
        켬 = idx == 기본idx
        if len(누적) < 2:
            필요 = min(n, 3)
            패널 += (f'<div class="sl-panel" data-idx="{idx}" '
                    f'style="display:{"block" if 켬 else "none"};padding:18px 6px;'
                    f'text-align:center"><p style="margin:0;font-size:12.5px;color:#7d848f">'
                    f'{이름} 추이는 {필요}거래일이 쌓이면 열립니다 · 축적 중</p></div>')
        else:
            순 = sorted(누적, key=lambda k: -sum(누적[k].values()) / 3)
            보일 = 순[:3] + 순[-3:]
            vs = [v for nm in 누적 for v in 누적[nm].values()]
            시장 = None
            _t = 이력  # 시장 평균 = 전 섹터의 층별 평균
            시장 = {t: round(sum(누적[nm][t] for nm in 누적) / len(누적), 2)
                   for t in ("대형", "중형", "소형")}
            vs += list(시장.values())
            hi, lo = max(vs), min(vs)
            rng = max(0.01, hi - lo)
            def Y(v): return T + (hi - v) / rng * (H - T - B)

            # 전 섹터를 그려두고 기본은 숨긴다 → 섹터 성적표의 체크와 연동해 켠다.
            # 끝 라벨이 겹치지 않게 y를 벌린다(소형 값이 비슷한 섹터끼리 포개졌다).
            _ly = {}
            _이전 = None
            for nm in sorted(순, key=lambda k: Y(누적[k]["소형"])):
                y0 = Y(누적[nm]["소형"])
                _ly[nm] = y0 if _이전 is None else max(y0, _이전 + 11)
                _이전 = _ly[nm]
            _넘 = max(_ly.values()) - (H - B + 4) if _ly else 0
            if _넘 > 0:
                for k in _ly:
                    _ly[k] -= _넘

            선 = ""
            for nm in 순:
                c = sector_color(nm)
                켬2 = nm in 보일
                p = " ".join(f'{X[t]},{Y(누적[nm][t]):.0f}' for t in ("대형", "중형", "소형"))
                점 = "".join(f'<circle cx="{X[t]}" cy="{Y(누적[nm][t]):.0f}" r="3" fill="{c}"/>'
                            for t in ("대형", "중형", "소형"))
                y1, y2 = Y(누적[nm]["소형"]), _ly[nm]
                잇 = (f'<line x1="{X["소형"]+3}" y1="{y1:.0f}" x2="{X["소형"]+8}" y2="{y2:.0f}" '
                     f'stroke="{c}" stroke-width="0.7" opacity=".5"/>') if abs(y2-y1) > 3 else ""
                선 += (f'<g class="sl-line" data-idx="{idx}" data-zone="{nm}" '
                       f'style="display:{"block" if 켬2 else "none"}">'
                       f'<polyline class="sl-path" points="{p}" fill="none" stroke="{c}" '
                       f'stroke-width="2" stroke-linejoin="round"/>{점}{잇}'
                       f'<text x="{X["소형"]+10}" y="{y2+3:.0f}" font-size="9" '
                       f'fill="{c}">{nm[:8]}</text></g>')
            # 시장 평균 — 금색은 '내 섹터' 전용이므로 흰 점선으로.
            # ⚠️ 점선은 '내 관심종목 섹터' 전용이라, 시장 평균은 굵은 흰 실선으로 구분한다.
            mp = " ".join(f'{X[t]},{Y(시장[t]):.0f}' for t in ("대형", "중형", "소형"))
            선 += (f'<polyline points="{mp}" fill="none" stroke="#ffffff" stroke-width="3.4" '
                   f'stroke-linejoin="round" opacity=".9"/>')
            for t in ("대형", "중형", "소형"):
                선 += (f'<circle cx="{X[t]}" cy="{Y(시장[t]):.0f}" r="4" fill="#ffffff" '
                       f'stroke="#141922" stroke-width="1.2"/>')
            선 += (f'<text x="{X["소형"]+10}" y="{Y(시장["소형"])+3:.0f}" font-size="9" '
                   f'fill="#ffffff" font-weight="700">시장 평균</text>')

            축 = "".join(
                f'<line x1="{X[t]}" y1="{T-8}" x2="{X[t]}" y2="{H-B+8}" stroke="#232a36" '
                f'stroke-width="1"/><text x="{X[t]}" y="{T-14}" text-anchor="middle" '
                f'font-size="11" fill="#9aa0aa">{t}</text>' for t in X)
            영 = (f'<line x1="34" y1="{Y(0):.0f}" x2="344" y2="{Y(0):.0f}" stroke="#3a4150" '
                 f'stroke-dasharray="4 4"/>') if lo < 0 < hi else ""

            우하 = sum(1 for nm in 누적 if 누적[nm]["대형"] > 누적[nm]["소형"])
            결론 = (f'{len(누적)}개 섹터 중 <b style="color:#f0c65a">{우하}개</b>가 우하향 — '
                   + ("대형이 끌었습니다" if 우하 > len(누적) / 2 else "소형이 더 갔습니다"))
            패널 += (f'<div class="sl-panel" data-idx="{idx}" '
                    f'style="display:{"block" if 켬 else "none"}">'
                    f'<svg viewBox="0 0 {W} {H}" preserveAspectRatio="xMidYMid meet" '
                    f'style="width:100%;height:auto;display:block">'
                    f'{축}{영}{선}</svg>'
                    f'<p style="margin:6px 0 0;font-size:12.5px;color:#c9ced6">{결론}</p></div>')

        탭 += (f'<span class="sl-tab" data-idx="{idx}" onclick="slTab({idx})" '
              f'style="flex:1;text-align:center;font-size:11px;padding:6px 0;border-radius:7px;'
              f'cursor:pointer;font-weight:{800 if 켬 else 600};'
              f'background:{"#2a3446" if 켬 else "#171c25"};'
              f'color:{"#f0c65a" if 켬 else "#7d848f"};'
              f'-webkit-tap-highlight-color:transparent">{부제}</span>')

    JS = """<script>
(function(){
 // 섹터 성적표에서 체크한 섹터를 그대로 따라간다(선택 상태는 하나만 존재).
 function apply(){
  var sel=window.CP_SECT, mz=(window.cpMyZones?cpMyZones():{});
  document.querySelectorAll('.sl-line').forEach(function(g){
   var z=g.dataset.zone;
   if(sel) g.style.display = sel[z] ? 'block' : 'none';
   var pa=g.querySelector('.sl-path');
   if(pa){
    // 내 관심종목 섹터는 같은 색 점선 — 색은 섹터 고유색을 유지한다.
    pa.setAttribute('stroke-dasharray', mz[z]?'7 4':'');
    pa.setAttribute('stroke-width', mz[z]?'3':'2');}
  });
 }
 window.slSync=apply;
 window.CP_PAINT=window.CP_PAINT||[]; window.CP_PAINT.push(apply);
 window.slTab=function(i){
  document.querySelectorAll('.sl-panel').forEach(function(p){
   p.style.display=(p.dataset.idx==i)?'block':'none';});
  document.querySelectorAll('.sl-tab').forEach(function(t){
   var on=t.dataset.idx==i;
   t.style.background=on?'#2a3446':'#171c25';
   t.style.color=on?'#f0c65a':'#7d848f'; t.style.fontWeight=on?800:600;});
  apply();};
 if(document.readyState!=='loading'){apply()}else{
  document.addEventListener('DOMContentLoaded',apply)}
})();
</script>"""

    return ('<div style="background:#141922;border:1px solid #232a36;border-radius:12px;'
            'padding:13px 14px;margin:10px 0 0">'
            '<p style="margin:0 0 2px;font-size:11.5px;color:#8b93a0">섹터 크기별</p>'
            '<p style="margin:0 0 3px;font-size:17px;font-weight:800;color:#f2f4f7">'
            '대형에서 소형으로 갈 때 무슨 일이</p>'
            f'<div style="display:flex;gap:6px;margin:10px 0 9px">{탭}</div>'
            + 패널 +
            '<p style="margin:8px 0 0;font-size:10.5px;color:#6f7784;line-height:1.6">'
            '<span style="color:#ffffff">━</span> <b style="color:#c9ced6">굵은 흰 실선 = 시장 평균</b><br>'
            '<b style="color:#c9ced6">점선 = 내 관심종목이 속한 섹터</b> · 색은 섹터마다 고정입니다<br>'
            '위 <b>섹터 성적표</b>에서 체크한 섹터가 여기에도 그대로 나옵니다</p>'
            '<details style="margin:10px 0 0;padding:9px 10px;background:#0f131a;'
            'border-radius:8px;border:1px solid #1e2531">'
            '<summary style="font-size:11.5px;color:#e0c060;font-weight:700;'
            'cursor:pointer;list-style:none">📖 섹터 크기별 보는 방법 '
            '<span style="color:#6f7784;font-weight:600">(눌러서 펼치기)</span></summary>'
            '<p style="margin:6px 0 0;font-size:11px;color:#7d848f;line-height:1.65">'
            '같은 섹터라도 <b style="color:#9aa0aa">대형주와 소형주의 성적은 다릅니다.</b> '
            '이 그림은 그 차이를 한눈에 보여줍니다.<br>'
            '<b style="color:#9aa0aa">선이 우하향</b>(왼쪽이 높음)이면 그 섹터는 '
            '<b style="color:#9aa0aa">대형주가 끌었다</b>는 뜻입니다. 같은 섹터를 골랐어도 '
            '소형주를 들고 있었으면 못 벌었습니다.<br>'
            '<b style="color:#9aa0aa">선이 우상향</b>이면 반대로 소형주가 더 갔습니다. '
            '시장에 온기가 퍼질 때 자주 나오는 모습입니다.<br>'
            '<b style="color:#9aa0aa">굵은 흰 선(시장 평균)보다 위</b>에 있으면 '
            '그 크기에서 시장을 이긴 것입니다. 내 섹터 점선이 흰 선 아래로 계속 간다면 '
            '<b style="color:#9aa0aa">자리 자체가 불리했다</b>는 뜻입니다.<br>'
            '기간 탭(5·20·60일)을 바꾸면 <b style="color:#9aa0aa">최근 흐름과 큰 흐름</b>이 '
            '다른지 확인할 수 있습니다.'
            '</p></details></div>' + JS)


def _index_close_map():
    """market_history에서 {날짜: (코스피종가, 코스닥종가)} — 벤치마크 계산용."""
    try:
        with open("market_history.json", encoding="utf-8") as f:
            일별 = (json.load(f) or {}).get("일별") or []
    except Exception:
        return {}
    out = {}
    for r in 일별:
        d = str(r.get("날짜", "")).replace("-", "")
        if d:
            out[d] = (r.get("코스피"), r.get("코스닥"))
    return out


def build_capture_path(개월=1, 시장=None, 종류="강세"):
    """강세 레이더가 포착한 종목들이 그 뒤 실제로 걸어간 길.

    ⚠️ 성과 표시가 아니라 **지표 성능 공시**다. 최저 사례도 반드시 함께 낸다.
    """
    일수 = 22 if 개월 == 1 else 66
    파일들 = sorted(alist(r"data_\d{8}\.json"))[-일수:]
    if len(파일들) < 3:
        return ""
    # ⚠️ 3개월판은 이력이 충분할 때만 낸다.
    #    지금처럼 19일치뿐이면 66일을 요구해도 결국 같은 19일을 쓰게 되어
    #    1개월판과 **글자 하나 다르지 않은 그림**이 두 번 나온다.
    #    같은 걸 두 번 보여주면 구독자는 "대충 만들었네"로 읽는다. 차라리 숨긴다.
    if 개월 == 3 and len(파일들) < 33:
        return ""
    쌍 = {}          # (종목,포착일) → (경과, 이후등락) 최신값
    for f in 파일들:
        try:
            with open(apath(f), encoding="utf-8") as fp:
                _d = json.load(fp)
                _키 = "강세레이더" if 종류 == "강세" else "매집레이더"
                tr = ((_d.get(_키) or {}).get("추적")) or []
        except Exception:
            continue
        for t in tr:
            g, r = t.get("경과"), t.get("이후등락")
            if not (isinstance(g, int) and isinstance(r, (int, float))):
                continue
            # 시장을 나눠 보는 이유: 코스닥은 변동폭이 구조적으로 커서
            # 코스피와 한 줄로 섞으면 평균이 코스닥에 끌려간다.
            if 시장 and t.get("시장") != 시장:
                continue
            쌍[(t.get("종목명"), t.get("포착일"))] = (g, r, t.get("종목명"),
                                                 t.get("포착일"), t.get("시장"))
    if len(쌍) < 5:
        return ""

    별 = {}
    for v in 쌍.values():
        별.setdefault(v[0], []).append(v[1])
    최종 = [(v[1], v[2]) for v in 쌍.values()]

    # ── 벤치마크: 같은 기간 지수는 얼마나 움직였나 ──
    #   "우리 레이더가 잘한 건가, 그냥 시장이 좋았던 건가"를 가르는 유일한 기준.
    종가맵 = _index_close_map()
    날짜들 = sorted(종가맵)
    _idx = 1 if (시장 == "코스닥") else 0
    벤치 = {}
    for v in 쌍.values():
        g, 포착일 = v[0], v[3]
        if 포착일 not in 종가맵:
            continue
        try:
            i0 = 날짜들.index(포착일)
        except ValueError:
            continue
        i1 = i0 + g
        if i1 >= len(날짜들):
            continue
        a = 종가맵[날짜들[i0]][_idx]
        b = 종가맵[날짜들[i1]][_idx]
        if isinstance(a, (int, float)) and isinstance(b, (int, float)) and a:
            벤치.setdefault(g, []).append((b - a) / a * 100)
    평균 = sum(r for r, _ in 최종) / len(최종)
    승률 = sum(1 for r, _ in 최종 if r > 0) / len(최종) * 100
    중앙 = sorted(r for r, _ in 최종)[len(최종) // 2]
    최고 = max(최종, key=lambda x: x[0])
    최저 = min(최종, key=lambda x: x[0])

    Ds = sorted(d for d in 별 if d >= 0)
    if len(Ds) < 3:
        return ""
    곡선 = [(d, sum(별[d]) / len(별[d])) for d in Ds]
    벤곡선 = [(d, sum(벤치[d]) / len(벤치[d])) for d in Ds if 벤치.get(d)]
    vs = [v for _, v in 곡선] + [v for _, v in 벤곡선]
    lo, hi = min(vs + [0]), max(vs + [0])
    rng = (hi - lo) or 1.0
    # 경사선과 같은 이유로 340폭 좌표계 — 모바일에서 가로 스크롤 없이 한눈에.
    W, H = 340, 175
    def PX(d): return 40 + (d - Ds[0]) / max(1, (Ds[-1] - Ds[0])) * 280
    def PY(v): return 26 + (hi - v) / rng * 112

    선 = " ".join(f"{PX(d):.0f},{PY(v):.0f}" for d, v in 곡선)
    벤선 = " ".join(f"{PX(d):.0f},{PY(v):.0f}" for d, v in 벤곡선)
    벤HTML = (f'<polyline points="{벤선}" fill="none" stroke="#8b93a0" stroke-width="1.8" '
             f'stroke-dasharray="5 4" stroke-linejoin="round"/>') if len(벤곡선) >= 3 else ""
    # 초과수익 = 우리 곡선 끝점 − 지수 곡선 끝점. 이게 진짜 성적표다.
    초과 = (곡선[-1][1] - 벤곡선[-1][1]) if 벤곡선 else None
    영 = (f'<line x1="36" y1="{PY(0):.0f}" x2="324" y2="{PY(0):.0f}" stroke="#3a4150" '
         f'stroke-dasharray="4 4"/>')
    눈 = "".join(f'<text x="{PX(d):.0f}" y="162" text-anchor="middle" font-size="10" '
                 f'fill="#6f7784">D+{d}</text>' for d in Ds[::max(1, len(Ds)//5)])

    라벨 = "1개월" if 개월 == 1 else "3개월"
    시장명 = 시장 or "전체"
    종류명 = "강세" if 종류 == "강세" else "매집"
    지수명 = "코스닥" if 시장 == "코스닥" else ("코스피" if 시장 == "코스피" else "지수")
    초과HTML = ""
    if 초과 is not None:
        초색 = "#4ade80" if 초과 >= 0 else "#a78bfa"
        초과HTML = (f'<p style="margin:5px 0 0;font-size:13px;color:#e8eaee">'
                   f'같은 기간 {지수명} <b>{벤곡선[-1][1]:+.1f}%</b> → '
                   f'초과수익 <b style="color:{초색}">{초과:+.1f}%p</b></p>')
    return ('<div style="background:#141922;border:1px solid #232a36;border-radius:12px;'
            'padding:12px 14px;margin:10px 0 0">'
            f'<p style="margin:0 0 2px;font-size:11.5px;color:#8b93a0">'
            f'포착 항로 · {종류명}편 · {시장명}</p>'
            f'<p style="margin:0 0 8px;font-size:17px;font-weight:800;color:#f2f4f7">'
            f'{시장명} {종류명} 레이더가 잡은 종목들, 그 뒤 {라벨}</p>'
            f'<svg viewBox="0 0 {W} {H}" preserveAspectRatio="xMidYMid meet" '
            f'style="width:100%;max-width:520px;height:auto;display:block">{영}{벤HTML}'
            f'<polyline points="{선}" fill="none" stroke="#d85a30" stroke-width="2.6" '
            f'stroke-linejoin="round"/>{눈}</svg>'
            '<div style="display:flex;gap:12px;margin-top:5px">'
            '<span style="font-size:10.5px;color:#d85a30">— 포착 종목 평균</span>'
            f'<span style="font-size:10.5px;color:#8b93a0">--- {지수명} (같은 기간)</span></div>'
            f'<p style="margin:6px 0 0;font-size:13px;color:#e8eaee">'
            f'포착 {len(최종)}종목 · 평균 <b>{평균:+.1f}%</b> · 중앙값 {중앙:+.1f}% · 승률 {승률:.0f}%</p>'
            + 초과HTML +
            f'<p style="margin:4px 0 0;font-size:12.5px;color:#c9ced6">'
            f'최고 {최고[1]} {최고[0]:+.1f}% · 최저 {최저[1]} {최저[0]:+.1f}%</p>'
            '<p style="margin:6px 0 0;font-size:11.5px;color:#6f7784;line-height:1.5">'
            '포착은 추천이 아니라 <b>지표 성능 공시</b>입니다 · 틀린 사례도 지우지 않습니다 · '
            f'표본 {len(최종)}종목{"(30 미만이라 승률이 크게 흔들릴 수 있습니다)" if len(최종) < 30 else ""}<br>'
            '⚠️ 곡선의 각 지점은 <b>서로 다른 종목 묶음</b>의 평균입니다 — '
            '한 무리를 20일 따라간 곡선이 아니라, 그날그날 D+N을 지나던 종목들의 평균입니다</p>'
            '</div>')


def build_core(핵심편, data, 해석):
    """핵심편 '90초 브리핑' — 리포트 최상단.

    글(정의·공감·왜·특징·뒤집어보기)은 Claude가, 숫자 타일·티저는 코드가 만든다.
    핵심편 JSON이 없으면(과거 리포트 재빌드) 빈 문자열 — 하위 호환.
    """
    if not 핵심편:
        return ""
    # 금요일·연휴 직전에는 "내일"이 틀린 말이 된다 → 실제 다음 거래일로 표기.
    try:
        _NEXT_LABEL = trading_day_context(
            datetime.strptime(data.get("날짜") or DATE, "%Y%m%d").date())["다음거래일표현"]
    except Exception:
        _NEXT_LABEL = "내일"
    지수수급 = data.get("지수수급") or {}
    코수 = 지수수급.get("코스피_수급") or {}
    rows = _load_market_history()

    # ── 지수 헤더 (스타일은 HEADER_STYLE 상수로 전환) ──
    지수스트립 = build_index_header(지수수급, data.get("파생"), 코수, 관제=data.get("관제지수"))

    def _f(v):
        try:
            return float(str(v).replace(",", ""))
        except (TypeError, ValueError):
            return None

    # ── 수급 타일 3장 (기계) ──
    타일들 = []
    for 라벨, 키, mh키 in (("외국인", "외국인", "외국인_코스피"), ("기관", "기관계", "기관_코스피"), ("개인", "개인", "개인_코스피")):
        v = _f(코수.get(키))
        부제 = None
        if mh키 and rows:
            부제 = _mh_rank(rows, mh키, v) or _mh_streak(rows, mh키)
            if 부제 is None and v is not None:
                과값 = [abs(r[mh키]) for r in rows[-21:-1] if r.get(mh키) is not None]
                if len(과값) >= 5 and sum(과값):
                    부제 = f"평소의 {abs(v)/(sum(과값)/len(과값)):.1f}배"
        cls = "b" if (v or 0) >= 0 else "s"
        타일들.append(
            f'<div class="tile"><p class="tile-k">{라벨}</p>'
            f'<p class="tile-v {cls}">{_flow_amt(v)}</p>'
            f'<p class="tile-s">{부제 or "&nbsp;"}</p></div>')
    타일HTML = "".join(타일들)

    삼줄 = "".join(
        f'<div class="q3"><span class="q3-n">{i}</span><span>{줄}</span></div>'
        for i, 줄 in enumerate((핵심편.get("세줄요약") or [])[:3], 1))

    태그색 = {"반도체": "tg-semi", "글로벌": "tg-glo", "정책": "tg-pol",
            "수급": "tg-sup", "실적": "tg-semi", "산업": "tg-glo"}
    이슈들 = "".join(
        f'<div class="i9"><span class="i9-t {태그색.get(it.get("태그"), "tg-sup")}">{it.get("태그","")}</span>'
        f'<span>{it.get("내용","")}</span></div>'
        for it in (해석.get("핵심이슈") or [])[:4])
    이슈블록 = (f'<div class="iss90"><p class="iss90-h">📰 오늘 시장을 움직인 것들</p>'
              f'<p class="iss90-s">뉴스에서 오늘 실제로 주가에 영향을 준 것만 추렸습니다</p>{이슈들}</div>'
              ) if 이슈들 else ""

    특징 = "".join(
        f'<p class="mf"><span class="mf-i">{i}</span><span>{t}</span></p>'
        for i, t in enumerate((핵심편.get("수급특징") or [])[:3], 1))
    왜 = 핵심편.get("수급왜") or ""
    왜블록 = (f'<div class="mny-why"><p class="mw-h">🧭 왜 이렇게 움직였을까요</p>'
             f'<p class="mw-b">{왜}</p></div>') if 왜 else ""

    # ── 내 마음 코너 (매일 다른 제목·본문 — Claude 생성) ──
    마음 = 핵심편.get("내마음") or {}
    if isinstance(마음, str):          # 구버전 호환
        마음 = {"본문": 마음}
    본문 = 마음.get("본문") or 핵심편.get("내종목위로") or ""
    제목 = safe_emoji(마음.get("제목") or "😮‍💨 오늘 내 종목이 내렸다면")
    한줄 = safe_emoji(마음.get("한줄") or "")
    내종목 = ""
    if 본문:
        내종목 = ('<div class="mine">'
                + f'<p class="mine-h">{제목}</p>'
                + f'<p class="mine-b">{본문}</p>'
                + (f'<p class="mine-f2">{한줄}</p>' if 한줄 else '')
                + '</div>')
    # 핵심편 디버전스 콜아웃 — 가장 중요한 신호 1개만(경계>안심>관찰 순 우선)
    _divs = detect_divergences(data)
    핵심디버전스 = ""
    if _divs:
        _order = {"warn": 0, "good": 1, "watch": 2}
        _top = sorted(_divs, key=lambda x: _order.get(x[0], 9))[0]
        _g, _ic, _t, _dd = _top
        핵심디버전스 = (f'<div class="q90-dv dv-{_g}"><span class="q90-dv-ic">{_ic}</span>'
                     f'<span class="q90-dv-t"><b>{_t}</b> — 심층편 &lt;오늘 프로의 판단&gt;에서 자세히</span></div>')

    뒤집 = 핵심편.get("뒤집어보기") or ""
    뒤집블록 = (f'<div class="q90-flip"><p class="qf-h">🔄 오늘의 뒤집어보기</p>'
              f'<p class="qf-b">{뒤집}</p></div>') if 뒤집 else ""

    # ── 티저 (기계) ──
    #   ⚠️ 개수 자랑은 희소성을 죽인다. "34종목 확인하세요"는 아무도 안 본다.
    #      그래서 **가장 강한 신호 하나**만 골라 그 이유를 말한다.
    #   ⚠️ 매집 티저의 "N종목" 버그: ⭐표시가 화면에 실제로 뜨는 TOP5가 아니라
    #      조건만 통과한 후보 전체(수십 종목)를 비교해서 "34종목" 같은 부풀려진
    #      숫자가 나왔었다. _acc_star_names()로 화면 기준(TOP5×TOP5)만 쓰도록 고쳤고,
    #      숫자를 자랑하는 대신 "왜 봐야 하는지"로 문구를 다시 썼다.
    강세 = data.get("강세레이더") or {}
    신규 = 강세.get("신규") or {}
    전체신규 = [s for v in (신규.values() if isinstance(신규, dict) else []) for s in (v or [])]
    매집 = data.get("매집레이더") or {}
    단기 = 매집.get("종목") or []
    중기 = 매집.get("중기종목") or []
    별명단 = _acc_star_names(매집)
    별종목 = [s for s in 중기 if s.get("종목명") in 별명단]

    # ⚠️ 티저에는 '로직 용어'(거래량 N배·시총·가중치)를 절대 노출하지 않는다.
    #    구독자에게 보이는 건 "무엇이 얼마나 셌나(등락률·일수)"와 "왜 봐야 하나"뿐.
    #    로직 수치는 운영자만 아는 내부 재료다.
    티저들 = []
    선도섹터 = ((data.get("주도섹터") or [{}])[0].get("테마명") or "").strip()
    # 1) 강세 — 가장 센 1종목의 '등락률'만. 배수(로직) 대신 상승률로 말한다.
    if 전체신규:
        top = max(전체신규, key=lambda s: s.get("강세점수") or 0)
        등락 = top.get("등락률")
        섹터문 = f'{선도섹터} 중심으로 ' if 선도섹터 else ''
        티저들.append(('#radar', '레이더',
                     f'{섹터문}오늘 <span class="u">+{등락:.1f}%</span> 급등하며 새로 불붙은 곳이 있습니다'
                     if isinstance(등락,(int,float)) else '오늘 새로 불붙은 곳이 있습니다'))
    # 2) 매집 — ⭐(5일+20일 동시) → 20일 최장연속 → 5일 연속 순.
    #    "N일 동안 외국인/기관이 사들인 종목" 식으로, 왜 봐야 하는지를 말한다.
    if 별종목:
        기간 = 매집.get("중기기간", 20)
        티저들.append(('#acc', '매집',
                     f'최근 5일과 {기간}일, <b>양쪽 모두</b> 꾸준히 사들인 종목이 있습니다 — 꼭 확인하세요'))
    elif 중기:
        top = max(중기, key=lambda s: max(s.get("외인일수") or 0, s.get("기관일수") or 0))
        주체 = "외국인" if (top.get("외인일수") or 0) >= (top.get("기관일수") or 0) else "기관"
        일수 = max(top.get("외인일수") or 0, top.get("기관일수") or 0)
        기간 = 매집.get("중기기간", 20)
        티저들.append(('#acc', '매집',
                     f'{기간}일 중 <span class="u">{일수}일</span>을 {주체}이 조용히 사들인 종목이 있습니다 — 꼭 확인하세요'
                     if 일수 else '조용히 오래 쌓이는 곳이 있습니다 — 꼭 확인하세요'))
    elif 단기:
        top = max(단기, key=lambda s: max(s.get("외인일수") or 0, s.get("기관일수") or 0))
        주체 = "외국인" if (top.get("외인일수") or 0) >= (top.get("기관일수") or 0) else "기관"
        일수 = max(top.get("외인일수") or 0, top.get("기관일수") or 0)
        티저들.append(('#acc', '매집',
                     f'최근 5일 중 <span class="u">{일수}일</span>을 {주체}이 사들인 종목이 있습니다 — 꼭 확인하세요'
                     if 일수 else '조용히 돈이 쌓이는 곳이 있습니다 — 꼭 확인하세요'))
    티저HTML = "".join(
        f'<a class="qt" href="{h}"><span class="qt-tag">{t}</span><span>{txt}</span>'
        f'<span class="qt-go">확인 ↓</span></a>' for h, t, txt in 티저들[:3])

    # 내일장 대응 — 핵심편만 읽는 사람을 위해 '내일 관찰 포인트'를 맨 끝에.
    #   ⚠️ 항상 지수만 보여주면 지루하다. 관전포인트 3개(지수/선물/프로그램)를
    #      날짜 기준으로 순환시키고, 섹터·매집 관찰 포인트도 후보에 섞어
    #      발행마다 다른 각도가 나오게 한다.
    관전 = [str(p).lstrip("①②③④⑤1234567890. ").strip()
          for p in (해석.get("관전포인트") or []) if str(p).strip()]
    후보들 = list(관전)   # 지수·수급 / 선물 / 프로그램

    # 섹터 관찰 포인트 (오늘 1위 주도섹터가 내일도 이어지는지)
    _주도 = data.get("주도섹터") or []
    if _주도:
        _s = _주도[0]
        _nm = (_s.get("테마명") or "").strip()
        _등 = _s.get("테마등락")
        if _nm and isinstance(_등,(int,float)):
            후보들.append(f'오늘 시장을 이끈 <b>{_nm}</b>(+{_등:.1f}%)가 내일도 힘을 이어가는지, '
                        f'아니면 하루 만에 식는지 — 주도 섹터의 <b>이틀째</b>를 보세요.')

    # 매집 관찰 포인트 (⭐ 동시 매집 종목이 있으면)
    _매집 = data.get("매집레이더") or {}
    _별 = _acc_star_names(_매집)
    if _별:
        후보들.append(f'외국인·기관이 <b>5일·20일 모두</b> 사들인 매집 종목들이 내일도 매수세를 '
                    f'유지하는지 확인하세요 — 조용한 매집이 진짜인지 갈리는 날입니다.')

    내일대응 = ""
    if 후보들:
        # 날짜 숫자로 순환 — 같은 날은 항상 같은 포인트, 발행마다 달라짐
        try:
            _seed = int(DATE)      # 발행일(YYYYMMDD) 기준 순환 — 매일 다른 각도
        except Exception:
            _seed = 0
        pick = 후보들[_seed % len(후보들)]
        내일대응 = (f'<div class="tmr"><p class="tmr-h">🌅 {_NEXT_LABEL}장, 이것만 기억하세요</p>'
                   f'<p class="tmr-b">{pick}</p></div>')

    # ⚠️ 장 마감 전(09:00~15:30) 또는 개장 전에 돌면 지수·섹터가 전부 0%로 잡힌다.
    #    데이터가 아니라 실행 시각의 문제이므로, 조용히 넘기지 말고 명시한다.
    지 = ((data.get("지수수급") or {}).get("지수") or {})
    _r = lambda k: str((지.get(k) or {}).get("등락률") or "").replace("%", "")
    장전 = _r("코스피") in ("0.00", "0", "") and _r("코스닥") in ("0.00", "0", "")
    장전경고 = ('<p class="q90-stale">⚠️ 이 리포트는 <b>장 마감 전</b>에 만들어졌습니다 — '
              '지수·섹터·레이더 수치가 아직 반영되지 않았습니다. '
              '정식 리포트는 장 마감 후 발행분을 확인해 주세요.</p>') if 장전 else ''

    공감 = 핵심편.get("공감문구") or ""
    왜그런가 = 핵심편.get("왜그런가") or ""
    사건명블록 = build_headline(해석)
    딱N블록 = build_top_picks(해석)
    # ⚠️ 배치 원칙(v-k4): 핵심편은 "오늘은 어떤 하루였나(헤더)" → "왜 그랬나(정의·공감·왜)"
    #    → "수급으로 확인" → "그래서 내 계좌는 어디에(좌표·레이더)" 순서로 읽힌다.
    #    · 수급 변속기는 수급 타일 바로 밑(같은 맥락)으로 이동
    #    · 경사선·포착 항로는 분석 성격이 짙어 심층편으로 이동
    # 순서 의도: 💰수급(외국인·기관=큰돈) → 🧭나침반(개인=군중) → 격자·레이더
    #   같은 하루를 '큰돈'과 '군중' 두 시선으로 잇따라 보여준다.
    # 순서 의도: 내 종목(가장 개인적) → 내 구역 → 구역 성적 → 시장 전체
    # 핵심편은 '내 자리'까지만 — 시장 전체 분석은 심층편으로 내린다.
    # ⚠️ 내 관심종목 '등록' UI는 심층편으로 내렸다(2026-08-18).
    #    핵심편은 90초 브리핑이라 '입력하는 화면'이 흐름을 끊는다.
    #    등록은 심층편에서 하고, 핵심편은 그 결과(격자·성적표)만 보여준다.
    격자블록 = (build_account_grid(data.get("계좌격자"), data.get("주도섹터"))
              + build_sector_scoreboard())
    변속기블록 = build_flow_gearbox()

    return (장전경고 + 사건명블록 + '<div class="q90"><div class="q90-top">'
            '<span class="q90-badge">⏱️ 90초 브리핑</span>'
            '<span class="q90-sub">바쁘신 분들을 위한 핵심 요약편입니다</span></div>'
            + 지수스트립
            + f'<p class="q90-def">{핵심편.get("오늘의정의","")}</p>'
            + (f'<p class="q90-gloss">{핵심편.get("정의풀이")}</p>' if 핵심편.get("정의풀이") else '')
            + (f'<p class="q90-feel">{공감}</p>' if 공감 else '')
            + (f'<p class="q90-why">{왜그런가}</p>' if 왜그런가 else '')
            + f'<div class="q90-3">{삼줄}</div>'
            + 이슈블록
            + '<div class="mny"><p class="mny-h">💰 오늘 수급, 평소와 뭐가 달랐나</p>'
            + '<p class="mny-sub">최근 20거래일과 비교했습니다</p>'
            + core_flow_gauge()
            + f'<div class="mny-tiles">{타일HTML}</div>'
            + 변속기블록
            + f'<div class="mny-feat">{특징}</div>' + 왜블록 + '</div>'
            + 격자블록
            + 내종목 + 뒤집블록 + 딱N블록 + 핵심디버전스
            + f'<div class="q90-tease"><p class="qt-h">🚨 시간 되실 때, 이것만은 꼭 확인하세요</p>{티저HTML}</div>'
            + 내일대응
            + '</div>'
            + ('<div class="deep-cut" id="deep">'
               '<span class="deep-arrow">⌄</span>'
               '<div class="deep-txt"><p class="deep-t1">여기까지가 핵심편입니다</p>'
               '<p class="deep-t2">지금부터는 근거와 상세를 담은 <b>심층편</b></p></div>'
               '<span class="deep-arrow">⌄</span></div>'))


def temp_inline():
    """수급 온도 — 수급 관제신호 카드 **맨 위**에 놓이는 주체별 비교.

    3체크(실탄 합계 기준)보다 먼저 "누가 얼마나 움직였나"를 보여줘야
    아래 판정이 자연스럽게 읽힌다.
    한 행에 담는 것: 주체 · 오늘 금액 · 평소 평균과 배수 · 배지(순위/연속).
    이력 6일 미만이면 비교를 생략한다 — 없는 비교는 만들지 않는다.
    """
    rows = _load_market_history()
    if len(rows) < 2:
        return ""
    비교가능 = len(rows) >= 6

    def 평소(key):
        vals = [abs(r[key]) for r in rows[-21:-1] if r.get(key) is not None]
        return round(sum(vals) / len(vals)) if len(vals) >= 5 else None

    행들 = []
    for 라벨, key in (("외국인", "외국인_코스피"), ("기관", "기관_코스피"), ("개인", "개인_코스피")):
        오늘 = rows[-1].get(key)
        if 오늘 is None:
            continue
        평 = 평소(key) if 비교가능 else None
        비교문 = f"평소 {평:,.0f}억 · {abs(오늘)/평:.1f}배" if 평 else "—"
        배지 = (_mh_rank(rows, key, 오늘) or _mh_streak(rows, key)) if 비교가능 else None
        cls = "b" if 오늘 >= 0 else "s"
        행들.append(
            f'<div class="ft-row"><span class="ft-who">{라벨}</span>'
            f'<span class="ft-val {cls}">{_flow_amt(오늘)}</span>'
            f'<span class="ft-avg">{비교문}</span>'
            f'<span class="ft-bad">{f"<i>{배지}</i>" if 배지 else "&nbsp;"}</span></div>')
    if not 행들:
        return ""
    꼬리 = ("" if 비교가능 else
           f' · <span style="color:#7d838c">비교는 6일부터 (현재 {len(rows)}일)</span>')
    return (f'<div class="fs-temp"><p class="fs-temp-t">🌡️ 오늘 수급 온도 '
            f'<span>최근 {min(len(rows),20)}거래일과 비교{꼬리}</span></p>'
            f'{"".join(행들)}'
            f'<p class="ft-note">배지는 같은 방향(매수는 매수끼리) 상위 3위이거나 '
            f'연속 흐름일 때만 붙습니다 — 붙은 날이 특별한 날입니다.</p></div>')


# ── 수급 관제신호 (실탄·3질문·누적 그래프) ──
FLOW_강한배수 = 1.4      # 평소 대비 이 배수 이상이면 "강한"
FLOW_바스켓선 = 0.45     # 바스켓 비중 이 이상이면 "폭넓은 매수"
FLOW_선물유의 = 0.5      # 선물이 평소의 이 배수 이상일 때만 반대 신호로 인정
FLOW_실탄최소 = 2000     # 실탄이 이보다 작으면(억) 바스켓 비중이 튀어 판정 보류
FLOW_평소일수 = 20       # '평소'를 계산할 기간(거래일). 오늘은 제외하고 이 일수만큼 본다


def expiry_note(ymd=None):
    """만기·지수변경 주간인지 판정한다.

    한국 파생 만기 규칙:
      · 옵션 만기      = 매월 **두 번째 목요일**
      · 선물+옵션 동시 = 3·6·9·12월 두 번째 목요일 ("네 마녀의 날")
      · 코스피200 정기변경 = 6월·12월 만기일에 맞춰 연 2회 적용
    이 주간의 비차익은 방향성 베팅이 아니라 **기계적 조정**이라 해석을 달리해야 한다.
    반환: (배지문구, 설명) 또는 (None, None)
    """
    d = datetime.strptime(ymd or DATE, "%Y%m%d")
    # 그 달의 두 번째 목요일 구하기
    첫날 = d.replace(day=1)
    첫목 = 1 + (3 - 첫날.weekday()) % 7      # 목요일 = 3
    만기일 = d.replace(day=첫목 + 7)
    차이 = (d - 만기일).days                  # 음수면 만기 전
    if not (-3 <= 차이 <= 1):
        return None, None
    분기 = d.month in (3, 6, 9, 12)
    정기변경 = d.month in (6, 12)
    이름 = "네 마녀의 날 주간" if 분기 else "옵션 만기 주간"
    언제 = ("오늘이 만기일입니다" if 차이 == 0 else
           (f"만기일이 {-차이}거래일 앞입니다" if 차이 < 0 else "어제가 만기일이었습니다"))
    설명 = (f"{언제}. 이 시기의 비차익은 <b>방향성 베팅이 아니라 만기 청산·롤오버에 따른 "
           f"기계적 조정</b>일 수 있습니다. 다음 날 반대로 나올 수 있으니 폭 판정을 그대로 믿지 마십시오.")
    if 정기변경:
        설명 += " 이번 달은 <b>코스피200 정기변경</b>도 겹칩니다 — 편입·편출 종목 매매가 비차익에 섞입니다."
    return f"📅 {이름}", 설명


def combo_tag(실탄, 비차익):
    """실탄 부호 × 비차익 부호 → 4가지 장세 이름.

    색은 국내 HTS 문법을 따른다.
      빨강 = 돈이 들어옴 · 파랑 = 돈이 나감 · 노랑 = 지수와 종목이 엇갈림
    """
    if 실탄 is None or 비차익 is None or 실탄 == 0:
        return None
    실 = 실탄 >= 0
    비 = 비차익 >= 0
    if 실 and 비:
        return ("good", "🔴 지수형 매수", "지수도 종목도 함께 오른 폭넓은 매수")
    if 실 and not 비:
        return ("warn", "🟠 종목 장세", "개별은 사고 지수 바스켓은 판 날 — 종목별 편차가 큼")
    if (not 실) and 비:
        return ("warn", "🟡 지수만 방어", "개별은 파는데 인덱스 자금이 지수를 떠받친 날")
    return ("info", "🔵 지수형 매도", "지수도 종목도 함께 빠진 전면 이탈")


# ── 🧺 비차익(바스켓) 해석·통계 ─────────────────────────
#  비차익 = "종목을 고르지 않고 코스피200을 한 바구니에 담아 통째로 사고판 돈".
#  이 코너가 답하는 것은 **지수가 오를까 내릴까가 아니다.**
#  "그 방향이 내 계좌까지 오는 구조인가" — 즉 **폭(넓이)** 하나다.
#
#  ⚠️ 판정 기준은 위쪽 수급 관제신호와 **같은 상수를 쓴다.**
#     (FLOW_바스켓선 / FLOW_실탄최소). 여기서 따로 45%·2000억을 다시 쓰면
#     같은 날이 두 자리에서 다르게 판정돼 리포트가 자기모순에 빠진다.
BASKET_HIGH = FLOW_바스켓선 * 100      # 이 이상이면 '지수형'
BASKET_LOW = 20.0                      # 이 미만이면 '종목형'
BASKET_MIN_SAMPLE = 5                  # 표본 5회 룰 — 미만이면 빈도 문장을 내지 않는다


def basket_ratio(비차익, 실탄):
    """비차익 ÷ 실탄 × 100. 판정 불가면 None.

    ⚠️ 100%를 넘거나 음수가 나올 수 있다. 오류가 아니다.
       분모(실탄=외국인+기관 상계 후)와 분자(비차익=시장 전체 프로그램)의
       집계 범위가 달라서, 한쪽이 지수를 통째로 사고 다른 쪽이 개별 종목을
       반대로 팔면 이런 값이 나온다.
    """
    if 비차익 is None or 실탄 is None:
        return None
    if abs(실탄) < FLOW_실탄최소:
        return None
    return 비차익 / 실탄 * 100.0


def basket_band(r):
    """비중 → ('high'|'mid'|'low'|'odd'|None, 표시명)"""
    if r is None:
        return None, "판정 보류"
    if r < 0 or r > 100:
        return "odd", "상계"
    if r >= BASKET_HIGH:
        return "high", "지수형"
    if r >= BASKET_LOW:
        return "mid", "혼재"
    return "low", "종목형"


def basket_read(실탄, 비차익, 만기=False):
    """오늘 비차익을 초보 눈높이로 풀어쓴 한 문단 (규칙 기반 — Claude 미개입).

    방향(실탄 부호) × 폭(비중 구간)의 4분면으로 갈라 쓴다.
    '오를 것이다 / 내릴 것이다'는 절대 쓰지 않는다.
    """
    r = basket_ratio(비차익, 실탄)
    band, _ = basket_band(r)

    if 만기:
        return ("오늘은 만기일이라 비차익이 기계적으로 크게 잡힙니다. "
                "폭 판정은 오늘 하루 건너뜁니다.")
    if band is None:
        return ("오늘은 실탄이 작아 비율로 나누면 값이 크게 튑니다. "
                "폭 판정은 보류합니다.")

    pct = f"{r:.0f}%"
    산다 = 실탄 >= 0

    if band == "odd":
        return (f"비중이 <b>{pct}</b>로 나왔습니다. 오류가 아니라 "
                f"<b>한쪽은 지수를 통째로 사고 다른 쪽은 개별 종목을 반대로 판</b> 날입니다. "
                f"이런 날은 지수와 개별 종목의 방향이 크게 엇갈리기 쉬우니, "
                f"<b>지수만 보고 내 종목을 판단하면 어긋납니다.</b>")
    if 산다 and band == "low":
        return (f"실탄은 들어왔지만 <b>{pct}만 바스켓</b>입니다. "
                f"지수 상승을 <b>소수 종목이 만들었다</b>는 뜻이라, "
                f"대부분의 계좌는 지수만큼 못 올랐을 겁니다. "
                f"이런 날은 지수 방향보다 <b>어느 섹터에 있느냐</b>가 수익을 가릅니다.")
    if 산다 and band == "mid":
        return (f"바스켓 비중 <b>{pct}</b> — 지수 전체와 개별 종목이 <b>절반씩 섞인</b> 매수입니다. "
                f"지수도 오르고 종목별 편차도 남는 구간이라, "
                f"<b>지수를 따라가되 섹터가 성과를 가른다</b>고 보면 됩니다.")
    if 산다 and band == "high":
        return (f"실탄의 <b>{pct}</b>가 바스켓 매수입니다. 종목을 고른 게 아니라 "
                f"<b>한국 시장 자체를 담은</b> 날이라, 대형주·지수를 따라가는 자리가 유리합니다. "
                f"넓게 들어온 돈은 좁게 들어온 돈보다 <b>흐름이 오래 이어지는 편</b>이지만, "
                f"소형 테마는 상대적으로 소외될 수 있습니다.")
    if (not 산다) and band == "low":
        return (f"실탄은 빠졌지만 바스켓은 <b>{pct}</b>뿐입니다. "
                f"지수를 통째로 던진 게 아니라 <b>오른 종목에서 차익을 실현한</b> 쪽에 가깝습니다. "
                f"지수는 버텨도 <b>많이 오른 종목이 먼저 밀릴 수 있는</b> 자리입니다.")
    if (not 산다) and band == "mid":
        return (f"바스켓 비중 <b>{pct}</b> — 지수 이탈과 종목 정리가 <b>같이 일어난</b> 매도입니다. "
                f"한쪽으로 단정하기 어려운 구간이라 다음 이틀의 방향을 확인하는 편이 낫습니다.")
    return (f"실탄의 <b>{pct}</b>가 바스켓 매도입니다. 종목을 고른 게 아니라 "
            f"<b>한국 시장 자체에서 나간</b> 날이라, 개별 호재가 잘 먹히지 않습니다. "
            f"종목 고르기로 이기기 어려운 국면입니다.")


def basket_followup(이력, 앞으로=5, 최소표본=BASKET_MIN_SAMPLE, 만기제외=True):
    """비차익 비중 구간별로 'N거래일 뒤 코스피가 올랐나'를 센다.

    이력 : flow_history.json 리스트 (날짜·실탄·비차익·코스피등락 필요.
           선택 필드 '만기'가 True면 표본에서 뺀다)
    반환 : {'매수': {band: {n, up, down, avg, ready}}, '매도': {...}, 'days': N}

    ⚠️ 만기일은 비차익이 기계적으로 튀므로 반드시 뺀다. 안 빼면 통계가 오염된다.
    """
    rows = [x for x in (이력 or []) if x.get("실탄") is not None]
    n = len(rows)
    out = {"매수": {}, "매도": {}, "days": 앞으로, "min_sample": 최소표본}
    buckets = {}
    for i in range(n - 앞으로):
        x = rows[i]
        if 만기제외 and x.get("만기"):
            continue
        band, _ = basket_band(basket_ratio(x.get("비차익"), x.get("실탄")))
        if band is None or band == "odd":
            continue
        방향 = "매수" if x["실탄"] >= 0 else "매도"
        acc, ok = 1.0, True
        for j in range(i + 1, i + 1 + 앞으로):
            v = rows[j].get("코스피등락")
            if v is None:
                ok = False
                break
            acc *= (1 + v / 100.0)
        if not ok:
            continue
        buckets.setdefault((방향, band), []).append((acc - 1) * 100.0)
    for (방향, band), vals in buckets.items():
        up = sum(1 for v in vals if v > 0)
        out[방향][band] = {"n": len(vals), "up": up, "down": len(vals) - up,
                          "avg": sum(vals) / len(vals), "ready": len(vals) >= 최소표본}
    return out


_BASKET_NAME = {"high": "비중 {:.0f}% 넘은".format(BASKET_HIGH),
                "mid": "비중 {:.0f}~{:.0f}%".format(BASKET_LOW, BASKET_HIGH),
                "low": "비중 {:.0f}% 미만".format(BASKET_LOW)}


def basket_followup_sentence(stat, 방향="매수"):
    """basket_followup 결과 → 사람이 읽는 문장.

    ⚠️ 표본이 최소치에 못 미치는 구간은 **아예 말하지 않는다.**
       (없는 비교는 만들지 않는다 — 절대 원칙 2)
    """
    d = (stat or {}).get(방향, {})
    N = (stat or {}).get("days", 5)
    최소 = (stat or {}).get("min_sample", BASKET_MIN_SAMPLE)
    ready = [(b, v) for b, v in d.items() if v["ready"]]
    if not ready:
        가진것 = sum(v["n"] for v in d.values())
        return (f"⏳ {방향}일의 비중 구간별 통계는 아직 표본이 부족합니다 "
                f"(현재 {가진것}건 · 구간당 {최소}건부터 공개).")
    parts = []
    for b in ("high", "mid", "low"):
        v = d.get(b)
        if not v or not v["ready"]:
            continue
        parts.append(f"{_BASKET_NAME[b]} {방향}일이 기록상 {v['n']}번 있었고, "
                     f"그중 {N}거래일 뒤 코스피가 오른 건 {v['up']}번이었습니다")
    미달 = [b for b in ("high", "mid", "low") if b in d and not d[b]["ready"]]
    꼬리 = ""
    if 미달:
        꼬리 = " (" + " · ".join(f"{_BASKET_NAME[b]} {d[b]['n']}건은 표본 부족" for b in 미달) + ")"
    return ". ".join(parts) + "." + 꼬리 + " 과거 빈도이며 확률 예측이 아닙니다."


def _flow_amt(v):
    """억원 → '+1.17조' / '−2,672억' 표기"""
    if v is None:
        return "—"
    a, s = abs(v), ("+" if v > 0 else "−")
    if a >= 10000:
        t = f"{a/10000:.2f}".rstrip("0").rstrip(".")
        return f"{s}{t}조"
    return f"{s}{a:,.0f}억"


def detect_divergences(data):
    """지수·수급의 '엇갈림(디버전스)'을 규칙 기반으로 포착한다.

    엇갈림은 반전의 씨앗이다. 각 신호를 ⚠️경계 / 👀관찰 / ✅안심 3단계로 분류해
    '단정'이 아니라 '지금 이걸 주목하라'는 판단 힌트로 준다.
    최대 60일 범위에서 기간은 신호마다 자동 선택(5·20일 등).
    """
    지 = ((data.get("지수수급") or {}).get("지수")) or {}
    코수 = ((data.get("지수수급") or {}).get("코스피_수급")) or {}

    def f(v):
        try: return float(str(v).replace(",", "").replace("%", ""))
        except (TypeError, ValueError): return None

    코등 = f((지.get("코스피") or {}).get("등락률"))
    닥등 = f((지.get("코스닥") or {}).get("등락률"))
    외 = f(코수.get("외국인")); 기 = f(코수.get("기관계"))
    실탄오늘 = (외 + 기) if (외 is not None and 기 is not None) else None

    h = load_json("flow_history.json") or []
    h = [x for x in h if isinstance(x, dict) and x.get("실탄") is not None]
    h20 = h[-20:]
    실탄20 = sum(x.get("실탄") or 0 for x in h20) if h20 else None
    외20 = sum(x.get("외현") or 0 for x in h20) if h20 else None

    signals = []   # (등급, 아이콘, 제목, 설명)

    # ① 지수 상승 vs 20일 실탄 유출 (고점 경계)
    if 코등 is not None and 코등 > 0.3 and 실탄20 is not None and 실탄20 < 0 and len(h20) >= 8:
        signals.append((
            "warn", "⚠️",
            "지수는 오르는데, 큰돈은 빠지는 중",
            f"코스피가 <b>{코등:+.1f}%</b> 올랐지만 최근 {len(h20)}일 실탄은 "
            f"<b>{_flow_amt(실탄20)}</b> 빠져나갔습니다. 외국인·기관이 아니라 개인이 밀어올린 "
            f"상승일 수 있어, <b>지속력은 지켜봐야</b> 합니다."))

    # ② 오늘 외국인 매수 vs 20일 누적 매도 (바닥 전환 초기)
    if 외 is not None and 외 > 0 and 외20 is not None and 외20 < 0 and len(h20) >= 8:
        signals.append((
            "good", "✅",
            "외국인이 이제 막 돌아서는 신호",
            f"오늘 외국인은 <b>{_flow_amt(외)}</b> 샀지만 최근 {len(h20)}일 누적은 아직 "
            f"<b>{_flow_amt(외20)}</b> 매도입니다. <b>추세가 바뀌기 시작하는 초입</b>일 수 있어, "
            f"매수가 며칠 더 이어지는지가 관건입니다."))

    # ③ 코스피 vs 코스닥 격차 (쏠림/양극화)
    if 코등 is not None and 닥등 is not None:
        갭 = 코등 - 닥등
        if 코등 > 0.5 and 닥등 < 0:
            signals.append((
                "warn", "⚠️",
                "대형주만 웃고 중소형주는 소외",
                f"코스피는 <b>{코등:+.1f}%</b>인데 코스닥은 <b>{닥등:+.1f}%</b>입니다. "
                f"돈이 일부 대형주에만 몰린 <b>쏠림 장세</b>라, 지수만 보고 '좋았다'고 "
                f"느끼면 실제 체감과 어긋납니다."))
        elif abs(갭) >= 1.5:
            signals.append((
                "watch", "👀",
                "코스피와 코스닥이 서로 다른 방향",
                f"두 지수 격차가 <b>{abs(갭):.1f}%p</b>로 큽니다. 시장 안에서 "
                f"자금이 한쪽으로 이동 중일 수 있으니 어느 쪽이 이기는지 지켜보십시오."))

    # ④ 실탄 20일 유출인데 5일은 유입 (흐름 반전 조짐)
    실탄5 = sum(x.get("실탄") or 0 for x in h[-5:]) if len(h) >= 5 else None
    if (실탄20 is not None and 실탄5 is not None and len(h) >= 10
            and 실탄20 < 0 < 실탄5 and abs(실탄5) > abs(실탄20) * 0.3):
        signals.append((
            "good", "✅",
            "한 달 흐름은 유출, 이번 주는 유입",
            f"최근 {len(h20)}일 실탄은 <b>{_flow_amt(실탄20)}</b> 빠졌지만 최근 5일은 "
            f"<b>{_flow_amt(실탄5)}</b> 들어왔습니다. <b>큰 흐름이 바뀌는 변곡</b>일 수 있습니다."))

    return signals


def _alignment_verdict(data):
    """엇갈림이 없을 때 — 지수·수급이 '정렬'됐는지 판정해 안심 판단을 준다.

    엇갈림 없음 = 정보 없음이 아니라 '방향이 선명하다'는 판단 재료.
    (등급, 아이콘, 제목, 설명) 하나를 돌려준다. 전부 규칙 기반(코드).
    """
    def f(v):
        try: return float(str(v).replace(",", "").replace("%", ""))
        except (TypeError, ValueError): return None
    지 = ((data.get("지수수급") or {}).get("지수")) or {}
    코수 = ((data.get("지수수급") or {}).get("코스피_수급")) or {}
    코등 = f((지.get("코스피") or {}).get("등락률"))
    외 = f(코수.get("외국인")); 기 = f(코수.get("기관계"))
    실탄 = (외 + 기) if (외 is not None and 기 is not None) else None
    if 코등 is None or 실탄 is None:
        return None

    지수양 = 코등 > 0.2
    지수음 = 코등 < -0.2
    수급양 = 실탄 > 0
    수급음 = 실탄 < 0

    if 지수양 and 수급양:
        return ("good", "✅", "지수도 수급도 매수로 정렬",
                f"코스피 <b>{코등:+.1f}%</b> 상승에 실탄도 <b>{_flow_amt(실탄)}</b> 순매수 — "
                f"방향이 <b>한 곳으로 정렬</b>됐습니다. 엇갈림 없는 <b>선명한 상승</b>이라, "
                f"이런 날은 추세를 믿고 따라가되 과열만 경계하면 됩니다.")
    if 지수음 and 수급음:
        return ("warn", "🔻", "지수도 수급도 매도로 정렬",
                f"코스피 <b>{코등:+.1f}%</b> 하락에 실탄도 <b>{_flow_amt(실탄)}</b> 순매도 — "
                f"되돌림 신호 없이 <b>방향이 아래로 일치</b>했습니다. 반등 근거가 약한 날이라 "
                f"무리한 저점매수는 신중히, 흐름이 꺾이는 신호를 먼저 확인하는 편이 낫습니다.")
    # 지수와 실탄이 애매(보합권)하거나 부분 정렬 — 중립 안심
    return ("watch", "🌤️", "큰 엇갈림 없이 방향이 정리된 하루",
            f"코스피 <b>{코등:+.1f}%</b>, 실탄 <b>{_flow_amt(실탄)}</b> — 오늘은 지수와 수급이 "
            f"크게 어긋나지 않았습니다. <b>급한 판단이 필요 없는 날</b>이니, 다음 신호가 나올 때까지 "
            f"기존 관점을 유지하며 지켜봐도 좋습니다.")


def build_divergence_block(data, 해석=None, 제목="⚡ 오늘 프로의 판단"):
    """오늘 프로의 판단 — 감지는 코드, 전망·대응 서술은 Claude(있으면).

    · 엇갈림 감지(detect_divergences)는 항상 코드가 한다 → 재사용 모드에서도 최신.
    · Claude가 생성한 '오늘의판단'(전망·대응)이 있으면 각 신호에 붙여 심도를 더한다.
      없으면(재사용 등) 코드가 만든 현황 설명만으로도 성립한다.
    """
    sigs = detect_divergences(data)
    판단 = ((해석 or {}).get("오늘의판단")) or []

    # 엇갈림이 없는 조용한 날 — 숨기지 않고 '정렬됨 = 선명한 추세'로 안심 판단을 준다.
    if not sigs:
        v = _alignment_verdict(data)
        if not v:
            return ""
        등급, 아이콘, 제, 설 = v
        # 조용한 날에도 Claude 판단이 있으면(드묾) 첫 항목의 전망·대응을 얹는다.
        전망대응 = ""
        j = 판단[0] if 판단 and isinstance(판단[0], dict) else None
        if j:
            for k, cls in (("맥락", "dv-ctx"), ("전망", "dv-fc"), ("대응", "dv-fc dv-act")):
                val = (j.get(k) or "").strip()
                if val:
                    키 = f'<span class="dv-fc-k">{k}</span>' if k != "맥락" else ""
                    전망대응 += f'<p class="{cls}">{키}{val}</p>'
        foot = ('엇갈림이 없다는 것도 하나의 신호입니다 — 방향이 선명한 날입니다. '
                '단정이나 매매 신호가 아닙니다.')
        return (f'<div class="dv-wrap"><p class="dv-h">{제목}</p>'
                f'<div class="dv-row dv-{등급}"><div class="dv-ic">{아이콘}</div>'
                f'<div class="dv-body"><p class="dv-t">{제}</p><p class="dv-d">{설}</p>'
                f'{전망대응}</div></div>'
                f'<p class="dv-foot">{foot}</p></div>')

    rows = []
    for idx, (등급, 아이콘, 제, 설) in enumerate(sigs):
        전망대응 = ""
        j = 판단[idx] if idx < len(판단) and isinstance(판단[idx], dict) else None
        if j:
            제 = j.get("제목") or 제
            맥락 = (j.get("맥락") or "").strip()
            전망 = (j.get("전망") or "").strip()
            대응 = (j.get("대응") or "").strip()
            부분 = ""
            if 맥락:
                부분 += f'<p class="dv-ctx">{맥락}</p>'
            if 전망:
                부분 += f'<p class="dv-fc"><span class="dv-fc-k">전망</span>{전망}</p>'
            if 대응:
                부분 += f'<p class="dv-fc dv-act"><span class="dv-fc-k">대응</span>{대응}</p>'
            전망대응 = 부분
        rows.append(
            f'<div class="dv-row dv-{등급}"><div class="dv-ic">{아이콘}</div>'
            f'<div class="dv-body"><p class="dv-t">{제}</p><p class="dv-d">{설}</p>'
            f'{전망대응}</div></div>')

    foot = ('프로가 지금 시장을 어떻게 읽고 무엇을 지켜보는지 짚어드립니다. '
            '전망은 조건부 관찰이며, 단정이나 매매 신호가 아닙니다.')
    return (f'<div class="dv-wrap"><p class="dv-h">{제목}</p>'
            + "".join(rows)
            + f'<p class="dv-foot">{foot}</p></div>')


def flow_pattern_analysis():
    """수급 과거 패턴 분석 — 전부 규칙 기반(코드 계산). Claude 미개입.

    두 가지를 본다:
      ① 오늘 조합태그가 과거에 나왔을 때 '다음날' 코스피가 어땠나 (빈도)
         → 표본 5일 미만이면 통계 대신 "축적 중"으로 정직하게 표시.
      ② 외국인·기관의 '최근 5일 vs 그 이전 5일' 흐름 변화
         → 순매도→순매수 전환 같은 방향 전환을 잡아낸다.

    원칙: 없는 비교는 만들지 않는다. 표본이 얇으면 말을 아낀다.
    """
    h = load_json("flow_history.json") or []
    if not isinstance(h, list):
        h = []
    h = [r for r in h if r.get("실탄") is not None]
    if len(h) < 6:
        return ""   # 6일 미만이면 아예 분석하지 않음

    블록 = []

    # ── ① 조합태그 다음날 빈도 ──
    조합오늘 = h[-1].get("조합")
    if 조합오늘:
        같은 = []
        for i in range(len(h) - 1):
            if h[i].get("조합") == 조합오늘:
                nxt = h[i + 1].get("코스피등락")
                if nxt is not None:
                    같은.append(nxt)
        태그이름 = {"지수형매수": "🔴 지수형 매수", "종목장세": "🟠 종목 장세",
                  "지수만방어": "🟡 지수만 방어", "지수형매도": "🔵 지수형 매도"}.get(조합오늘, 조합오늘)
        if len(같은) >= 5:
            상승 = sum(1 for r in 같은 if r > 0)
            평균 = sum(같은) / len(같은)
            블록.append(
                f'<p class="fp-line"><b>{태그이름}</b> 조합은 기록상 이번이 <b>{len(같은)+1}번째</b>입니다. '
                f'과거 {len(같은)}번의 <b>다음날</b> 코스피는 상승 {상승} · 하락 {len(같은)-상승}, '
                f'평균 <b>{평균:+.2f}%</b>였습니다.</p>')
        else:
            블록.append(
                f'<p class="fp-line"><b>{태그이름}</b> 조합은 기록상 {len(같은)+1}번째입니다 — '
                f'다음날 통계는 사례가 5번 이상 쌓인 뒤 제공합니다 <span class="fp-acc">(축적 중)</span>.</p>')

    # ── ② 외국인·기관 20일 분석 (헤더와 동일 로직 · 여기선 더 상세하게) ──
    #    각 주체마다: 오늘 규모 + 20일 자동선택 특징 + 5일 흐름 + 매수일수를 한 줄로.
    def _합(rows, key):
        return sum((r.get(key) or 0) for r in rows)
    def _매수일(rows, key, days=5):
        return sum(1 for r in rows[-days:] if (r.get(key) or 0) > 0)

    상세문 = []
    for 라벨, key in (("외국인", "외현"), ("기관", "기관")):
        오늘값 = h[-1].get(key)
        if 오늘값 is None:
            continue
        특징 = _flow_highlight(key)          # 20일 자동선택 (전환/최대/연속/순위)
        매수일 = _매수일(h, key)
        방향 = "매수" if 오늘값 >= 0 else "매도"
        # 5일 흐름(추세 방향)
        추세 = ""
        if len(h) >= 10:
            최근합 = _합(h[-5:], key); 이전합 = _합(h[-10:-5], key)
            if 이전합 <= 0 < 최근합 or 최근합 <= 0 < 이전합:
                추세 = f' · 5일 흐름 {_flow_amt(이전합)}→<b>{_flow_amt(최근합)}</b>'
            else:
                추세 = f' · 최근 5일 <b>{_flow_amt(최근합)}</b>'
        turn = ' fp-turn' if (특징 and "전환" in 특징) else ''
        상세문.append(
            f'<div class="fp-sub"><span class="fp-who">{라벨}</span>'
            f'<span class="fp-body">오늘 <b>{_flow_amt(오늘값)}</b> 순{방향} — '
            f'<b class="fp-hl{turn}">{특징}</b>{추세} · 최근 5일 중 {매수일}일 매수</span></div>')
    if 상세문:
        블록.append('<div class="fp-detail">' + "".join(상세문) + '</div>')

    if not 블록:
        return ""

    return (f'<div class="fs-pattern"><p class="fp-h">🧠 오늘 수급, 과거엔 어땠나 · 최근 무엇이 달라졌나</p>'
            + "".join(블록)
            + f'<p class="fp-foot">기록({len(h)}일치)에 근거한 사실 정리이며, 미래 예측이나 매매 신호가 아닙니다. '
            f'데이터가 쌓일수록 정확해집니다.</p></div>')



# ── 🕒 수급 상단 v5 — 계기·막대·통합 타임라인 ────────────
#  설계 원칙
#   · 숫자 하나(오늘 얼마)보다 **흐름**(며칠째·유별난가·누가 끌었나)이 중심이다.
#   · 매수=빨강 / 매도=파랑. 주체 구분은 색이 아니라 **선 색상 대비**로 한다
#     (외국인=자홍 / 기관=민트) — 매수·매도 색과 겹치면 뜻이 두 개가 된다.
#   · 데이터가 없는 구간은 0으로 채우지 않는다. **비우고 그 사실을 적는다.**
# ⚠️ 색 규칙 (2026-08-18 확정)
#   지수와 수급이 둘 다 빨강/파랑을 쓰므로 **명도로 층을 나눈다.**
#   같은 계열이라 뜻(빨강=올랐다·샀다)은 하나로 통하고,
#   진하기 차이로 "지수 얘긴가 수급 얘긴가"가 구분된다.
FS_BUY, FS_SELL = "#ff6b4a", "#5b9bff"       # 수급 — 밝은 톤
IDX_UP, IDX_DN = "#c1432b", "#2e6bd6"        # 지수 — 진한 톤
FS_FOR, FS_INS = "#f472e6", "#74f0d4"        # 외국인 / 기관
FS_FUT = "#e0c060"                            # 선물
FS_TL_MIN = {5: 5, 20: 10, 60: 30}            # 이만큼 없으면 그림 대신 진행 막대
_FS_TL_SEQ = [0]



# ══════════════════════════════════════════════════════
# 🙈 리포트에서 가린 챕터
# ══════════════════════════════════════════════════════
#  운영 규칙 (2026-08-18 확정)
#    · 챕터를 "빼달라"는 요청은 **삭제가 아니라 가림**이다.
#      코드·CSS·함수는 전부 그대로 두고, 발행되는 HTML에서만 감춘다.
#    · 다시 보고 싶으면 아래 목록에서 그 줄만 지우면 즉시 되살아난다.
#      ("가린 거 다 보여줘" → HIDDEN_CHAPTERS = set() 로 비우면 전부 복귀)
#    · 왜 이렇게 하나: 지웠다가 몇 주 뒤 되살리려면 코드를 다시 쓰게 된다.
#      가려두면 되돌리는 비용이 0이고, 그때까지 유지보수도 따라간다.
HIDDEN_CHAPTERS = {
    "지수와수급나란히",     # 2026-08-18 가림 — 통합 타임라인과 역할이 겹침
}


def hide(key, html):
    """HIDDEN_CHAPTERS에 있으면 빈 문자열, 없으면 그대로."""
    return "" if key in HIDDEN_CHAPTERS else html


def hidden_note():
    """가려둔 챕터가 있으면 개발자 메모로만 남긴다(운영자 확인용)."""
    if not HIDDEN_CHAPTERS:
        return ""
    return ("<!-- 가려둔 챕터: " + ", ".join(sorted(HIDDEN_CHAPTERS)) +
            " (build_html.py의 HIDDEN_CHAPTERS에서 해제) -->")


def _fs_stat(arr, 평소일수=20):
    """주체 하나의 오늘 성적 — 방향별 순위·상위%·N일 만의 최대·연속일수·평소 배수.

    ⚠️ 매도인 날에 '매수 기준 15위'라고 쓰면 정반대로 읽힌다.
       매수면 큰 순, 매도면 작은 순으로 세어 **그 방향에서 몇 번째인가**를 말한다.
    """
    arr = [v for v in arr if v is not None]
    n = len(arr)
    if n == 0:
        return None
    v = arr[-1]
    rk = (sorted(arr, reverse=True) if v >= 0 else sorted(arr)).index(v) + 1
    back = 1
    for j in range(2, n + 1):
        ok = (v == max(arr[-j:])) if v >= 0 else (v == min(arr[-j:]))
        if ok:
            back = j
        else:
            break
    기준 = arr[-(평소일수 + 1):-1] if n >= 6 else arr[:-1]
    평소 = (sum(abs(x) for x in 기준) / len(기준)) if 기준 else 0
    연속 = 1
    for i in range(n - 1, 0, -1):
        if (arr[i] >= 0) == (arr[i - 1] >= 0):
            연속 += 1
        else:
            break
    return {"v": v, "n": n, "rk": rk, "top": max(1, round(rk / n * 100)),
            "back": back, "평소": 평소, "배수": (abs(v) / 평소) if 평소 else 0,
            "연속": 연속, "dir": "매수" if v >= 0 else "매도"}


def _fs_gauge(st, W=118):
    """실탄 계기 — 바늘이 가리키는 건 금액이 아니라 **평소 대비 배수**다.

    금액을 바늘로 그리면 '3조가 얼마나 큰지'를 여전히 모른다.
    배수로 그리면 바늘 위치 자체가 '오늘이 유별났나'에 대한 답이 된다.
    """
    배수, 양 = st["배수"], st["v"] >= 0
    deg = max(-86, min(86, 배수 / 2 * 90)) * (1 if 양 else -1)
    c = FS_BUY if 양 else FS_SELL
    return (f'<svg class="fs-g" viewBox="0 0 132 86" style="width:{W}px">'
            f'<path d="M16 66 A50 50 0 0 1 116 66" fill="none" stroke="#161c26" stroke-width="12"/>'
            f'<path d="M66 16 A50 50 0 0 1 116 66" fill="none" stroke="{c}" stroke-width="12" stroke-opacity=".26"/>'
            f'<g stroke="#12161d" stroke-width="2">'
            f'<line x1="66" y1="10" x2="66" y2="22"/>'
            f'<line x1="30.6" y1="30.6" x2="39.1" y2="39.1"/>'
            f'<line x1="101.4" y1="30.6" x2="92.9" y2="39.1"/></g>'
            f'<text x="66" y="7" font-size="7" fill="#5b6472" font-weight="700" text-anchor="middle">평소 0</text>'
            f'<text x="16" y="80" font-size="8" fill="{FS_SELL}" font-weight="800">← 매도</text>'
            f'<text x="116" y="80" font-size="8" fill="{FS_BUY}" font-weight="800" text-anchor="end">매수 →</text>'
            f'<g transform="rotate({deg:.1f} 66 66)"><path d="M62.8 42 L66 18 L69.2 42 Z" fill="{c}"/></g>'
            f'<circle cx="66" cy="66" r="4" fill="{c}"/></svg>')


def _fs_hbar(st, MX, W=200, H=16):
    """가로 막대 — 뒤 회색 띠는 그 주체의 '평소 하루 폭'.

    ⚠️ 전 기간 최대값을 기준으로 잡으면 오늘 막대가 전부 뭉개진다.
       오늘값과 평소 범위를 담을 만큼만 잡는다(MX는 호출부에서 계산).
    """
    v, 평소 = st["v"], st["평소"]
    z, px = W / 2, (W / 2 - 4) / (MX or 1)
    bw, band = abs(v) * px, 평소 * px
    c = FS_BUY if v >= 0 else FS_SELL
    x = z if v >= 0 else z - bw
    return (f'<svg viewBox="0 0 {W} {H}" preserveAspectRatio="none" style="height:{H}px">'
            f'<rect x="{z-band:.1f}" y="1" width="{band*2:.1f}" height="{H-2}" fill="#7d848f" '
            f'fill-opacity=".16" rx="2"/>'
            f'<rect x="{x:.1f}" y="3" width="{max(2,bw):.1f}" height="{H-6}" rx="2" fill="{c}"/>'
            f'<line x1="{z}" y1="0" x2="{z}" y2="{H}" stroke="#fff" stroke-opacity=".35" '
            f'stroke-width="1.3"/></svg>')


def _fs_keyfact(st):
    """오늘 가장 말할 가치가 있는 사실 **하나만** 고른다.

    배지를 다섯 개 늘어놓으면 전부 같은 무게라 눈이 뭘 볼지 못 고른다.
    하나만 띄우고 나머지는 얇은 회색 줄로 내린다.
    """
    if st["back"] >= 3:
        return ("🔥" if st["v"] >= 0 else "🧊"), f'{st["back"]}일 만의 최대 {st["dir"]}'
    if st["연속"] >= 3:
        return "🔁", f'{st["연속"]}일 연속 {st["dir"]}'
    if st["배수"] >= 1.5:
        return "⚡", f'평소의 {st["배수"]:.1f}배'
    if st["배수"] and st["배수"] < 0.6:
        return "💤", "평소보다 조용한 하루"
    return "·", "평범한 규모"


def _fs_subrow(name, st, col, MX):
    ico, key = _fs_keyfact(st)
    c = FS_BUY if st["v"] >= 0 else FS_SELL
    return f'''
      <div class="fs-sub">
        <div class="fs-sub-h">
          <p class="fs-sub-n" style="color:{col}">{name}</p>
          {_fs_hbar(st, MX)}
          <p class="fs-sub-v" style="color:{c}">{_flow_amt(st["v"])}</p>
        </div>
        <p class="fs-sub-x"><span class="fs-key" style="border-color:{c}55;color:{c}">{ico} {key}</span>
          {st["dir"]} <b>{st["rk"]}위</b>/{st["n"]}일 · 평소 하루치의 <b>{st["배수"]:.1f}배</b></p>
      </div>'''


def _fs_timeline_svg(이력, p, W=380):
    """기간 p의 통합 타임라인 — 외국인/기관 누적 · 선물 누적 · 비차익 비중.

    세 칸이 **같은 날짜축**을 쓴다. 어느 날의 세로줄을 따라 내려가면
    그날 네 가지가 각각 무엇을 했는지 한 번에 읽힌다.
    이력이 최소 기준에 못 미치면 None(→ 진행 막대).
    """
    N = len(이력)
    if N < FS_TL_MIN[p]:
        return None
    q = min(p, N)
    sl = 이력[-q:]
    날 = [f"{x['날짜'][4:6]}/{x['날짜'][6:]}" for x in sl]
    외 = [x.get("외현") or 0 for x in sl]
    기 = [x.get("기관") or 0 for x in sl]
    코 = [x.get("코스피등락") or 0 for x in sl]
    선 = [x.get("외선") for x in sl]
    비 = [x.get("비차익") for x in sl]
    실 = [x.get("실탄") or 0 for x in sl]

    def cum(a):
        t, o = 0, []
        for v in a:
            t += v
            o.append(t)
        return o
    C외, C기, C코 = cum(외), cum(기), cum(코)
    C선 = cum([v if v is not None else 0 for v in 선])

    # ⚠️ viewBox 폭은 실제 표시 폭과 맞춰야 한다. 700으로 잡으면 390px 화면에서
    #    0.54배로 축소돼 11px 글자가 6px가 된다(안 읽힘).
    H = 300
    # ⚠️ 오른쪽 여백(PR)은 선 이름표가 앉을 자리다. 0에 가깝게 잡으면
    #    선이 화면 끝까지 꽉 차서 '어느 선이 외국인인지'를 못 읽는다.
    PL, PR = 7, 46
    X = lambda k: PL + (W - PR - PL) * (k + 0.5) / q
    g = []

    # ── 레인 A: 외국인·기관 누적 ──
    AT, AB = 14, 140
    vals = C외 + C기 + [0]
    lo, hi = min(vals), max(vals)
    sp = (hi - lo) or 1
    YA = lambda v: AB - (AB - AT) * (v - lo) / sp
    zA = YA(0)
    g.append(f'<rect x="{PL}" y="{AT}" width="{W-PR-PL}" height="{max(0,zA-AT):.1f}" fill="{FS_BUY}" opacity=".05" rx="4"/>')
    g.append(f'<rect x="{PL}" y="{zA:.1f}" width="{W-PR-PL}" height="{max(0,AB-zA):.1f}" fill="{FS_SELL}" opacity=".05" rx="4"/>')
    g.append(f'<text x="{PL+6}" y="{AT+13:.1f}" font-size="7.5" fill="{FS_BUY}" font-weight="800" opacity=".85">누적 매수</text>')
    g.append(f'<text x="{PL+6}" y="{AB-5:.1f}" font-size="7.5" fill="{FS_SELL}" font-weight="800" opacity=".85">누적 매도</text>')
    g.append(f'<line x1="{PL}" y1="{zA:.1f}" x2="{W-PR}" y2="{zA:.1f}" stroke="#fff" stroke-opacity=".22" stroke-width="1.2"/>')
    klo, khi = min(C코 + [0]), max(C코 + [0])
    YK = lambda v: AB - (AB - AT) * (v - klo) / ((khi - klo) or 1)
    g.append('<polyline points="' + " ".join(f"{X(k):.1f},{YK(v):.1f}" for k, v in enumerate(C코)) +
             '" fill="none" stroke="#6f7784" stroke-width="1.1" stroke-dasharray="3 3" opacity=".6"/>')
    # 오른쪽 이름표는 서로 최소 11px 떨어뜨린다. 안 그러면 값이 비슷한 날
    # '코스피'와 '기관'이 겹쳐 둘 다 못 읽는다.
    _lbl_used = []
    def _lbl_y(want):
        y = min(max(want, AT + 9), AB - 3)
        for _ in range(24):
            if all(abs(y - u) >= 11 for u in _lbl_used):
                break
            y += 11
            if y > AB - 3:
                y = AT + 9
        _lbl_used.append(y)
        return y
    _kty = _lbl_y(YK(C코[-1]) + 3)
    g.append(f'<text x="{W-PR+4}" y="{_kty:.1f}" font-size="8.5" fill="#8b93a0" font-weight="800">코스피</text>')
    for ser, col, nm, wd in ((C기, FS_INS, "기관", 2.4), (C외, FS_FOR, "외국인", 2.8)):
        g.append('<polyline points="' + " ".join(f"{X(k):.1f},{YA(v):.1f}" for k, v in enumerate(ser)) +
                 f'" fill="none" stroke="{col}" stroke-width="{wd}" stroke-linejoin="round"/>')
        g.append(f'<circle cx="{X(q-1):.1f}" cy="{YA(ser[-1]):.1f}" r="3.3" fill="{col}"/>')
        ty = _lbl_y(YA(ser[-1]) + 3)
        g.append(f'<text x="{W-PR+4}" y="{ty:.1f}" font-size="8.5" fill="{col}" font-weight="800">{nm}</text>')

    # ── 레인 B: 선물 누적 (확신) ──
    BT, BB = 152, 206
    blo, bhi = min(C선 + [0]), max(C선 + [0])
    YB = lambda v: BB - (BB - BT) * (v - blo) / ((bhi - blo) or 1)
    g.append(f'<rect x="{PL}" y="{BT}" width="{W-PR-PL}" height="{BB-BT}" fill="#0a0e14" rx="4"/>')
    g.append(f'<line x1="{PL}" y1="{YB(0):.1f}" x2="{W-PR}" y2="{YB(0):.1f}" stroke="#fff" stroke-opacity=".18"/>')
    if q >= 6:
        i0 = q - 6
        sl5 = (C선[q-1] - C선[i0]) / 5
        sc = FS_BUY if sl5 >= 0 else FS_SELL
        g.append(f'<line x1="{X(i0):.1f}" y1="{YB(C선[i0]):.1f}" x2="{X(q-1):.1f}" y2="{YB(C선[q-1]):.1f}" '
                 f'stroke="{sc}" stroke-width="3" stroke-linecap="round" opacity=".9"/>')
        ar = "↗" if sl5 >= 0 else "↘"
        g.append(f'<text x="{W-PR-6}" y="{BT+10:.1f}" font-size="8" fill="{sc}" font-weight="800" '
                 f'text-anchor="end">5일 기울기 {ar} 하루 {sl5:,.0f}억</text>')
    g.append('<polyline points="' + " ".join(f"{X(k):.1f},{YB(v):.1f}" for k, v in enumerate(C선)) +
             f'" fill="none" stroke="{FS_FUT}" stroke-width="2" stroke-linejoin="round" opacity=".9"/>')
    g.append(f'<circle cx="{X(q-1):.1f}" cy="{YB(C선[-1]):.1f}" r="3" fill="{FS_FUT}"/>')
    g.append(f'<text x="{W-PR+4}" y="{min(max(YB(C선[-1])+3, BT+10), BB-3):.1f}" font-size="8.5" '
             f'fill="{FS_FUT}" font-weight="800">선물</text>')
    g.append(f'<rect x="{PL+1}" y="{BT+1}" width="62" height="12" rx="3" fill="#0a0e14" opacity=".92"/>')
    g.append(f'<text x="{PL+4}" y="{BT+10:.1f}" font-size="7.5" fill="#8b93a0" font-weight="800">🛩️ 선물 누적</text>')

    # ── 레인 C: 비차익 비중(%) — 세로축이 곧 비중이라 숫자를 매일 안 적어도 읽힌다 ──
    CT, CB = 216, 284
    rs = []
    for k in range(q):
        rs.append(basket_ratio(비[k], 실[k]))
    have = [k for k, r in enumerate(rs) if r is not None]
    g.append(f'<rect x="{PL}" y="{CT}" width="{W-PR-PL}" height="{CB-CT}" fill="#0a0e14" rx="4"/>')
    if have:
        first = have[0]
        if first > 0:
            g.append(f'<rect x="{PL}" y="{CT}" width="{max(0,X(first)-PL-4):.1f}" height="{CB-CT}" fill="#12171f" rx="4"/>')
            g.append(f'<text x="{max(PL+4,(PL+X(first))/2):.1f}" y="{CB-9:.1f}" font-size="7.5" '
                     f'fill="#4a5462" text-anchor="middle" font-weight="700">미수집</text>')
        vv = [rs[k] for k in have]
        lo2 = min(-25, min(vv) - 8)
        hi2 = max(115, max(vv) + 8)
        YC = lambda r: CB - 8 - (CB - CT - 22) * (r - lo2) / ((hi2 - lo2) or 1)
        for gy, gc, gt, dash in ((0, "#ffffff", "0%", ""),
                                 (BASKET_HIGH, FS_FUT, f"{BASKET_HIGH:.0f}% 지수형", ' stroke-dasharray="4 4"'),
                                 (100, "#e0a83c", "100%", ' stroke-dasharray="3 4"')):
            if lo2 <= gy <= hi2:
                g.append(f'<line x1="{PL}" y1="{YC(gy):.1f}" x2="{W-PR}" y2="{YC(gy):.1f}" '
                         f'stroke="{gc}" stroke-opacity=".28" stroke-width="1"{dash}/>')
                g.append(f'<text x="{PL+3}" y="{YC(gy)-2:.1f}" font-size="6.5" fill="{gc}" '
                         f'opacity=".75" font-weight="700">{gt}</text>')
        # ── 선을 잇는 방식 ──
        #  측정된 날끼리는 실선, **측정 못 한 날을 건너뛴 구간은 점선**으로 잇는다.
        #  (실탄이 너무 작아 비율이 튀는 날 = 판정 보류. 값이 없는 것이지
        #   0인 것이 아니므로, 실선으로 그으면 없는 값을 지어낸 셈이 된다.
        #   그렇다고 끊어두면 그림이 조각나 흐름이 안 읽힌다 → 점선이 절충안.)
        측정 = [(k, rs[k]) for k in have]
        for a, bq in zip(측정, 측정[1:]):
            (k1, r1), (k2, r2) = a, bq
            건너뜀 = (k2 - k1) > 1
            g.append(f'<line x1="{X(k1):.1f}" y1="{YC(r1):.1f}" x2="{X(k2):.1f}" y2="{YC(r2):.1f}" '
                     f'stroke="#c8ced6" stroke-width="1.9" stroke-linecap="round"'
                     + (' stroke-dasharray="3 3" opacity=".55"' if 건너뜀 else '') + '/>')
        for k, r in enumerate(rs):
            if r is None:
                continue
            이상 = (r < 0 or r > 100)
            c = "#e0a83c" if 이상 else (FS_BUY if r >= BASKET_HIGH else "#8b93a0")
            g.append(f'<circle cx="{X(k):.1f}" cy="{YC(r):.1f}" r="{3.2 if k==q-1 else 2.2}" fill="{c}"/>')
        if rs[-1] is not None:
            ty = min(max(YC(rs[-1]) - 7, CT + 24), CB - 4)
            g.append(f'<text x="{X(q-1)-5:.1f}" y="{ty:.1f}" font-size="9" fill="{FS_BUY}" '
                     f'font-weight="900" text-anchor="end">{rs[-1]:.0f}%</text>')
    else:
        g.append(f'<text x="{W/2:.1f}" y="{(CT+CB)/2+4:.1f}" font-size="8" fill="#4a5462" '
                 f'text-anchor="middle" font-weight="700">이 구간에는 비차익 데이터가 없습니다</text>')
    g.append(f'<rect x="{W-PR-136}" y="{CT+1}" width="132" height="12" rx="3" fill="#0a0e14" opacity=".92"/>')
    g.append(f'<text x="{W-PR-133}" y="{CT+10:.1f}" font-size="7.5" fill="#8b93a0" font-weight="800">🧺 비차익 — 실탄 대비 비중(%)</text>')

    # ── 공통 날짜축 ──
    step = max(1, q // 4)
    for k in range(0, q, step):
        g.insert(0, f'<line x1="{X(k):.1f}" y1="{AT}" x2="{X(k):.1f}" y2="{CB}" stroke="#1a2029" stroke-width="1"/>')
        g.append(f'<text x="{X(k):.1f}" y="{H-6}" font-size="7" fill="#5b6472" '
                 f'text-anchor="middle" font-weight="700">{날[k]}</text>')
    g.append(f'<text x="{X(q-1):.1f}" y="{H-6}" font-size="7" fill="#c9d0d9" '
             f'text-anchor="middle" font-weight="800">{날[-1]}</text>')
    return f'<svg viewBox="0 0 {W} {H}">{"".join(g)}</svg>'


def core_flow_gauge():
    """핵심편 수급 머리 — 심층편과 **같은 계기**를 작게 얹는다.

    ⚠️ 핵심편은 90초 브리핑이라 통합 타임라인·비차익 판독까지는 내리지 않는다.
       두 편이 **같은 언어**(같은 계기·같은 색)를 쓰되 **깊이만 다르게** 한다.
       (인수인계 §5 '두 지도' 원칙과 같은 구조)
    """
    이력 = load_json("flow_history.json") or []
    이력 = [x for x in 이력 if isinstance(x, dict) and x.get("실탄") is not None]
    if not 이력:
        return ""
    st = _fs_stat([x["실탄"] for x in 이력])
    if not st:
        return ""
    c = FS_BUY if st["v"] >= 0 else FS_SELL
    ico, key = _fs_keyfact(st)
    return (f'<div class="core-g">'
            f'<div class="core-g-l">{_fs_gauge(st, 96)}'
            f'<p class="core-g-x" style="color:{c}">평소의 {st["배수"]:.1f}배</p></div>'
            f'<div class="core-g-r">'
            f'<p class="core-g-v" style="color:{c}">{_flow_amt(st["v"])}</p>'
            f'<p class="core-g-s">실탄 · {st["dir"]} <b>{st["rk"]}위</b>/{st["n"]}일</p>'
            f'<p class="core-g-k" style="border-color:{c}55;color:{c}">{ico} {key}</p>'
            f'</div></div>')


def build_flow_timeline(이력):
    """기간 탭(5·20·60) + 통합 타임라인. 이력 부족 탭은 진행 막대."""
    N = len(이력)
    _FS_TL_SEQ[0] += 1
    gid = f"fstl{_FS_TL_SEQ[0]}"
    탭 = "".join(f'<div class="fs-ptab{" on" if p==20 else ""}" data-g="{gid}" data-p="{p}">{p}일</div>'
                for p in (5, 20, 60))
    몸 = ""
    for p in (5, 20, 60):
        svg = _fs_timeline_svg(이력, p)
        if svg is None:
            r = min(1, N / FS_TL_MIN[p])
            몸체 = (f'<div class="fs-pend"><p class="fs-pend-t">⏳ {p}거래일 이력을 쌓는 중입니다</p>'
                   f'<div class="fs-pend-bar"><div style="width:{r*100:.0f}%"></div></div>'
                   f'<p class="fs-pend-s">{N} / 최소 {FS_TL_MIN[p]}일 · '
                   f'약 {max(0, FS_TL_MIN[p]-N)}거래일 뒤 열립니다</p></div>')
        else:
            몸체 = svg
            if N < p:
                몸체 += (f'<p class="fs-tnote">※ 이력이 {N}거래일이라 {N}일치로 그렸습니다 '
                        f'({p}일까지 {p-N}일 남음)</p>')
        몸 += f'<div class="fs-pbody{" on" if p==20 else ""}" data-g="{gid}" data-p="{p}">{몸체}</div>'
    return f'''
    <div class="fs-tl">
      <div class="fs-ptabs">{탭}</div>
      {몸}
      <div class="fs-lg">
        <span><i style="background:{FS_FOR}"></i>외국인 누적</span>
        <span><i style="background:{FS_INS}"></i>기관 누적</span>
        <span><i style="background:{FS_FUT}"></i>선물 누적</span>
        <span><i style="background:#6f7784"></i>코스피</span>
        <span><i style="background:#c8ced6"></i>비차익 — 점 = 측정된 날 · 점선 = 판정 보류 구간</span>
      </div>
    </div>
    <script>(function(){{
      var root=document.currentScript.parentNode;
      root.addEventListener('click',function(e){{
        var t=e.target.closest('.fs-ptab'); if(!t) return;
        var g=t.getAttribute('data-g'), p=t.getAttribute('data-p');
        root.querySelectorAll('.fs-ptab[data-g="'+g+'"]').forEach(function(c){{c.classList.remove('on');}});
        t.classList.add('on');
        root.querySelectorAll('.fs-pbody[data-g="'+g+'"]').forEach(function(b){{
          b.classList.toggle('on', b.getAttribute('data-p')===p);
        }});
      }});
    }})();</script>'''


def build_flow_signal(파생, 지수수급):
    """수급 관제신호: 오늘 실탄 판정 + 3질문 체크 + 20거래일 누적 그래프.

    해석 문장까지 전부 규칙 기반(코드 생성)이다 — 숫자 코너에 AI 창작이 끼면
    할루시네이션 위험이 있어서, 이 코너만큼은 기계가 끝까지 책임진다.
    원료는 collect_data.py가 쌓는 flow_history.json.
    """
    이력 = load_json("flow_history.json") or []
    if not isinstance(이력, list):
        이력 = []
    이력 = [x for x in 이력 if x.get("실탄") is not None]
    if not 이력:
        return '<div class="pending">⏳ 수급 관제신호 — 내일 발행부터 데이터가 쌓입니다</div>'

    오늘 = 이력[-1]
    실탄 = 오늘["실탄"]
    외선 = 오늘.get("외선")
    비차익 = 오늘.get("비차익")
    N = len(이력)

    # ── 평소 규모(있는 만큼의 평균, 오늘 제외해 자기참조 완화) ──
    #   ⚠️ '평소'의 정의: **최근 20거래일 중 오늘을 뺀 날들의 |실탄| 평균**.
    #      이력 파일은 60일까지 쌓이지만, 60일 평균을 쓰면 두 달 전 장세가
    #      오늘 판정에 섞여 둔해진다. 화면 그래프도 20일이라 기준을 맞췄다.
    #      과거가 5일 미만이면 '평소'라 부를 수 없어 규모 판정을 하지 않는다.
    기준들 = 이력[-(FLOW_평소일수 + 1):-1] if N >= 6 else 이력
    평소실탄 = sum(abs(x["실탄"]) for x in 기준들) / max(1, len(기준들))
    평소선물 = None
    선물있는 = [abs(x["외선"]) for x in 기준들 if x.get("외선") is not None]
    if 선물있는:
        평소선물 = sum(선물있는) / len(선물있는)

    배수 = (abs(실탄) / 평소실탄) if 평소실탄 else None
    방향양 = 실탄 >= 0
    상태 = ("매수 우위" if 방향양 else "매도 우위")
    if 배수 and 배수 >= FLOW_강한배수:
        상태 = ("강한 매수" if 방향양 else "강한 매도")
    배수문 = f" · 평소의 {배수:.1f}배" if (배수 and N >= 6) else ""
    vc = "pos" if 방향양 else "neg"

    # ── 체크②: 선물 동의 ──
    선물동의 = None
    if 외선 is not None:
        선물동의 = (외선 >= 0) == 방향양
        선물유의 = (abs(외선) / 평소선물 >= FLOW_선물유의) if 평소선물 else (abs(외선) >= 1000)

    # ── 체크③: 바스켓 비중 ──
    #   ⚠️ 비중이 100%를 넘을 수 있다. 비차익은 '시장 전체' 프로그램 순매수이고
    #      실탄은 '외국인+기관'의 순매수 **합계(상계 후)** 라서 분모가 서로 다르다.
    #      한쪽이 바스켓으로 크게 팔고 다른 쪽이 개별 종목으로 사면 실탄만 작아진다.
    #      → 100% 초과는 오류가 아니라 '상계' 상태이므로 문구를 따로 준다.
    #      → 실탄이 너무 작으면 비율이 무한대로 튀므로 아예 판정을 보류한다.
    비중, 비중상태 = None, "없음"
    if 비차익 is not None and 실탄:
        if abs(실탄) < FLOW_실탄최소:
            비중상태 = "보류"
        elif 방향양 != (비차익 >= 0):
            비중상태 = "역방향"
            비중 = 비차익 / 실탄               # 음수가 된다
        else:
            비중 = 비차익 / 실탄
            비중상태 = "초과" if 비중 > 1.0 else "정상"

    # ── 칩 ──
    칩 = []
    if 비중상태 == "초과":
        칩.append(("warn", f"🔀 바스켓 {비중*100:.0f}% — 주체 간 상계"))
    elif 비중상태 == "역방향":
        칩.append(("warn", "🔀 바스켓은 반대 방향"))
    elif 비중 is not None and 비중 >= FLOW_바스켓선:
        칩.append(("good", f"🧺 폭넓은 {'매수' if 방향양 else '매도'} — 바스켓 {비중*100:.0f}%"))
    elif 비중 is not None:
        칩.append(("info", f"🎯 종목 선별형 — 바스켓 {비중*100:.0f}%"))
    선배수칩 = (abs(외선) / 평소선물) if (외선 is not None and 평소선물) else None
    if 선물동의 is False and 선물유의:
        if 선배수칩 is not None and 선배수칩 < 0.4:
            칩.append(("info", "🪶 선물은 반대 (가벼운 헤지)"))
        elif 선배수칩 is not None and 선배수칩 >= 2.0:
            칩.append(("warn", "⚠️ 선물이 크게 반대 (강한 헤지)"))
        else:
            칩.append(("warn", "⚠️ 선물은 반대 (헤지 동반)"))
    elif 선물동의 is True and 선물유의:
        칩.append(("good", "🤝 선물도 같은 방향" +
                  (" (강하게)" if (선배수칩 is not None and 선배수칩 >= 1.5) else "")))
    조합 = combo_tag(실탄, 비차익)
    if 조합:
        칩.insert(0, (조합[0], 조합[1]))
    만기배지, 만기설명 = expiry_note()
    if 만기배지:
        칩.append(("warn", 만기배지))
    칩HTML = "".join(f'<span class="fs-chip {c}">{t}</span>' for c, t in 칩)

    # ── 3단 체크 행 ──
    def 체크행(아이콘, 질문, 부제, 답, 값, 값클래스, 꼬리):
        return f'''
      <div class="fs-ck">
        <div class="fs-ck-ico {아이콘[0]}">{아이콘[1]}</div>
        <p class="fs-ck-q">{질문}<small>{부제}</small></p>
        <p class="fs-ck-a">{답}</p>
        <p class="fs-ck-v {값클래스}">{값}<small>{꼬리}</small></p>
      </div>'''

    행들 = []
    동사 = "들어왔습니다" if 방향양 else "빠져나갔습니다"
    if 배수 and N >= 6:
        if 배수 >= 2.5:
            크기말 = f"최근 {len(기준들)}거래일 하루 평균({평소실탄:,.0f}억)의 <b>{배수:.1f}배</b> — 눈에 띄게 큰 하루입니다."
        elif 배수 >= FLOW_강한배수:
            크기말 = f"최근 {len(기준들)}거래일 하루 평균({평소실탄:,.0f}억)의 <b>{배수:.1f}배</b>로 평소보다 큽니다."
        elif 배수 >= 0.6:
            크기말 = f"규모는 최근 {len(기준들)}거래일 하루 평균({평소실탄:,.0f}억)과 <b>비슷한 수준</b>({배수:.1f}배)입니다."
        else:
            크기말 = (f"다만 규모는 최근 {len(기준들)}거래일 하루 평균({평소실탄:,.0f}억)의 "
                    f"<b>{배수*100:.0f}%</b> 수준으로 조용한 편입니다.")
        답1 = f"{동사}. {크기말}"
    else:
        답1 = f"{동사}. (비교할 과거 데이터가 {N}일치뿐이라 규모 판정은 다음 발행부터입니다)"
    행들.append(체크행(("y" if 방향양 else "n", "✓" if 방향양 else "✗"),
                    "돈이 들어왔나?", "실탄 = 외국인+기관 현물", 답1,
                    _flow_amt(실탄), vc, "방향"))

    if 외선 is None:
        행들.append(체크행(("h", "—"), "선물도 동의하나?", "외국인 선물 방향",
                        "오늘은 선물 수급을 확보하지 못했습니다.", "—", "mid", "확신"))
    else:
        선배수 = (abs(외선) / 평소선물) if 평소선물 else None
        if 선배수 is None:
            세기말 = ""
        elif 선배수 >= 2.0:
            세기말 = "그것도 평소보다 훨씬 큰 규모로 "
        elif 선배수 >= 1.2:
            세기말 = "평소보다 큰 규모로 "
        elif 선배수 < 0.4:
            세기말 = "다만 규모가 작아 참고 수준으로 "
        else:
            세기말 = ""
        if 선물동의:
            if 선배수 is not None and 선배수 >= 1.2:
                답2 = (f"현물과 선물이 같은 방향입니다. 선물에서도 {세기말}"
                      f"{'사들였으니' if 방향양 else '내던졌으니'} <b>확신이 실린 수급</b>으로 봅니다.")
            elif 선배수 is not None and 선배수 < 0.4:
                답2 = ("방향은 현물과 같습니다. 다만 선물 규모가 작아 "
                      "<b>강한 확신까지는 아닌</b> 동의로 봅니다.")
            else:
                답2 = "현물과 선물이 같은 방향 — 확신이 실린 수급입니다."
            행들.append(체크행(("y", "✓"), "선물도 동의하나?", "외국인 선물 방향",
                            답2, _flow_amt(외선), vc, "확신"))
        else:
            반대 = "팔았습니다" if 방향양 else "샀습니다"
            if 선배수 is not None and 선배수 >= 2.0:
                답2 = (f"현물은 {'사면서' if 방향양 else '팔면서'} 선물은 {세기말}{반대}. "
                      f"현물보다 선물 쪽 움직임이 커서, <b>{'상승' if 방향양 else '하락'}에 베팅했다기보다 "
                      f"반대쪽을 대비한 포지션</b>일 수 있습니다.")
            elif 선배수 is not None and 선배수 < 0.4:
                답2 = (f"선물은 반대 방향이지만 규모가 작습니다. "
                      f"<b>가벼운 헤지</b> 정도로 보고, 확신을 크게 깎지는 않습니다.")
            else:
                답2 = (f"현물은 {'사면서' if 방향양 else '팔면서'} 선물은 {세기말}{반대}. "
                      f"<b>보험(헤지)을 든 {'매수' if 방향양 else '매도'}</b>라 확신은 한 단계 낮춰 봅니다.")
            행들.append(체크행(("h", "△"), "선물도 동의하나?", "외국인 선물 방향",
                            답2, _flow_amt(외선), "mid", "확신"))

    # ── v5 상단: 주체별 성적 + 계기 + 가로 막대 ──
    S실 = _fs_stat([x["실탄"] for x in 이력])
    S외 = _fs_stat([x.get("외현") for x in 이력 if x.get("외현") is not None])
    S기 = _fs_stat([x.get("기관") for x in 이력 if x.get("기관") is not None])
    _MX = max([abs(t["v"]) for t in (S실, S외, S기) if t] +
              [t["평소"] for t in (S실, S외, S기) if t] + [1]) * 1.12
    계기HTML = _fs_gauge(S실) if S실 else ""
    주체HTML = ""
    if S외:
        주체HTML += _fs_subrow("외국인", S외, FS_FOR, _MX)
    if S기:
        주체HTML += _fs_subrow("기관", S기, FS_INS, _MX)

    # ── 비차익 판독 + 구간별 사후 통계 ──
    _만기배지2, _ = expiry_note()
    바스켓읽기 = basket_read(실탄, 비차익, 만기=bool(_만기배지2))
    _st5 = basket_followup(이력, 앞으로=5)
    바스켓통계 = basket_followup_sentence(_st5, "매수" if 방향양 else "매도")

    # ── 누적 그래프 (서버에서 SVG 생성) ──
    그래프HTML = 판독HTML = 배지HTML = ""
    if N >= 2:
        표시 = 이력[-20:]
        n = len(표시)
        누적, acc = [], 0
        for x in 표시:
            acc += x["실탄"]
            누적.append(acc)
        누5 = sum(x["실탄"] for x in 이력[-5:])
        누20 = 누적[-1]
        W0, H0, PL, PR, PT, PB = 700, 240, 8, 8, 16, 8
        PW, PH = W0-PL-PR, H0-PT-PB
        X = lambda i: PL + PW*(i+0.5)/n
        BW = PW/n*0.58
        BMAX = max(abs(x["실탄"]) for x in 표시) or 1
        B0 = PT + PH*0.78
        BY = lambda v: B0 - (v/BMAX)*PH*0.40*0.55
        CMIN, CMAX = min(0, min(누적)), max(누적)
        span = (CMAX-CMIN) or 1
        CY = lambda v: PT + (PH*0.66)*(1-(v-CMIN)/span)
        g = []
        # 밴드는 '5일 전 기준점'에서 시작해야 5일간의 움직임이 통째로 안에 들어온다.
        # (예전엔 마지막 5개 막대에만 맞춰서, 정작 상승분이 밴드 왼쪽 밖에 그려졌다)
        bx = PL
        if n >= 6:
            bx = X(n-6)
            g.append(f'<rect x="{bx:.1f}" y="{PT}" width="{W0-PR-bx:.1f}" height="{PH}" fill="#e0c060" opacity=".07" rx="4"/>')
            g.append(f'<text x="{bx+6:.1f}" y="{PT+PH-4:.1f}" font-size="8.5" fill="#e0c060" font-weight="700" opacity=".8">최근 5일</text>')
        g.append(f'<line x1="{PL}" y1="{B0}" x2="{W0-PR}" y2="{B0}" stroke="#fff" stroke-opacity=".14"/>')
        for i, x in enumerate(표시):
            v = x["실탄"]; y1 = BY(v)
            g.append(f'<rect x="{X(i)-BW/2:.1f}" y="{min(B0,y1):.1f}" width="{BW:.1f}" '
                     f'height="{max(1.5,abs(y1-B0)):.1f}" rx="1.5" '
                     f'fill="{"#C1432B" if v>=0 else "#2E6BD6"}" opacity="{1 if i==n-1 else .75}"/>')
        선 = " ".join(f'{"L" if i else "M"}{X(i):.1f} {CY(v):.1f}' for i, v in enumerate(누적))
        g.append(f'<path d="{선} L{X(n-1):.1f} {CY(CMIN):.1f} L{X(0):.1f} {CY(CMIN):.1f} Z" fill="url(#fsgr)" opacity=".5"/>')
        g.append('<defs><linearGradient id="fsgr" x1="0" y1="0" x2="0" y2="1">'
                 '<stop offset="0%" stop-color="#ff8a6e" stop-opacity=".45"/>'
                 '<stop offset="100%" stop-color="#ff8a6e" stop-opacity="0"/></linearGradient></defs>')
        # ── 외국인 선물 누적 (흐릿한 점선, 방향 참고용) ──
        #   현물과 규모 단위가 달라 크기 비교는 무의미하다. 0선만 공유하고
        #   각자 자기 폭으로 스케일해 **방향과 기울기**만 겹쳐 본다.
        선물있는 = [x for x in 표시 if x.get("외선") is not None]
        if len(선물있는) >= 2:
            f누적, facc = [], 0
            for x in 표시:
                facc += (x.get("외선") or 0)
                f누적.append(facc)
            FMAX = max(abs(v) for v in f누적) or 1
            여유 = min(CY(0) - PT, (PT + PH*0.66) - CY(0))
            여유 = max(여유, 8)
            FY = lambda v: CY(0) - (v / FMAX) * 여유
            f선 = " ".join(f'{"L" if i else "M"}{X(i):.1f} {FY(v):.1f}' for i, v in enumerate(f누적))
            g.append(f'<path d="{f선}" fill="none" stroke="#7fa8e8" stroke-width="1.8" '
                     f'stroke-dasharray="4 4" opacity=".45" stroke-linejoin="round"/>')
            g.append(f'<circle cx="{X(n-1):.1f}" cy="{FY(f누적[-1]):.1f}" r="2.6" fill="#7fa8e8" opacity=".6"/>')
            g.append(f'<text x="{X(n-1)-7:.1f}" y="{FY(f누적[-1])+11:.1f}" text-anchor="end" '
                     f'font-size="8.5" fill="#7fa8e8" font-weight="700" opacity=".75">선물 {_flow_amt(f누적[-1])}</text>')

        g.append(f'<path d="{선}" fill="none" stroke="#f0f0ee" stroke-width="2.6" stroke-linejoin="round"/>')
        # ── 5일 전 기준선 ──
        #   밴드 구간의 '겉모습'(고점에서 흘러내림)과 배지 숫자(+4,595억)가
        #   반대로 보이는 착시가 있었다. 5일 누적은 '5일 전 누적과 오늘 누적의 차'인데,
        #   밴드 왼쪽 끝의 상승 구간이 이미 그 안에 포함돼 있기 때문이다.
        #   그래서 기준점(5일 전 누적)에 가로선을 그어 눈으로 차이를 확인하게 한다.
        if n >= 6:
            기준y = CY(누적[n-6])
            # ① 기준선 대비 위/아래를 색으로 칠한다 — 위(빨강)면 5일간 순유입
            for i in range(n-6, n-1):
                y0, y1 = CY(누적[i]), CY(누적[i+1])
                위쪽 = (누적[i] + 누적[i+1]) / 2 >= 누적[n-6]
                g.append(f'<polygon points="{X(i):.1f},{y0:.1f} {X(i+1):.1f},{y1:.1f} '
                         f'{X(i+1):.1f},{기준y:.1f} {X(i):.1f},{기준y:.1f}" '
                         f'fill="{"#C1432B" if 위쪽 else "#2E6BD6"}" opacity=".30"/>')
            # ② 기준선
            g.append(f'<line x1="{bx:.1f}" y1="{기준y:.1f}" x2="{W0-PR}" y2="{기준y:.1f}" '
                     f'stroke="#e0c060" stroke-opacity=".7" stroke-width="1.3" stroke-dasharray="4 3"/>')
            g.append(f'<circle cx="{X(n-6):.1f}" cy="{기준y:.1f}" r="2.6" fill="#e0c060" opacity=".8"/>')
            g.append(f'<text x="{bx+7:.1f}" y="{기준y-6:.1f}" font-size="8.5" fill="#e0c060" '
                     f'font-weight="700" opacity=".9">5일 전</text>')
            # ③ 기준선 → 오늘 끝점의 화살표 = 5일 누적 그 자체
            끝y = CY(누적[-1]); ax = X(n-1) - 26
            위로 = 끝y < 기준y
            색 = "#ff8a6e" if 위로 else "#7fa8e8"
            if abs(끝y - 기준y) >= 10:      # 간격이 넉넉할 때만 화살표
                머리 = f"{ax:.1f},{끝y:.1f} {ax-4.5:.1f},{끝y + (7 if 위로 else -7):.1f} {ax+4.5:.1f},{끝y + (7 if 위로 else -7):.1f}"
                g.append(f'<line x1="{ax:.1f}" y1="{기준y:.1f}" x2="{ax:.1f}" y2="{끝y + (6 if 위로 else -6):.1f}" '
                         f'stroke="{색}" stroke-width="1.8"/>')
                g.append(f'<polygon points="{머리}" fill="{색}"/>')
                라벨y = (기준y + 끝y) / 2 + 3
            else:                            # 좁으면 기준선 바로 아래에 글자만
                라벨y = 기준y + (16 if 위로 else -9)
            g.append(f'<text x="{ax-7:.1f}" y="{라벨y:.1f}" text-anchor="end" font-size="9.5" '
                     f'fill="{색}" font-weight="800">5일 {"▲" if 위로 else "▼"} {_flow_amt(누5)}</text>')
        if CMIN < 0 < CMAX:
            g.append(f'<line x1="{PL}" y1="{CY(0):.1f}" x2="{W0-PR}" y2="{CY(0):.1f}" stroke="#fff" stroke-opacity=".10" stroke-dasharray="3 4"/>')
            g.append(f'<text x="{PL+4}" y="{CY(0)-4:.1f}" font-size="8.5" fill="#767c86" font-weight="600">누적 0</text>')
        g.append(f'<circle cx="{X(n-1):.1f}" cy="{CY(누적[-1]):.1f}" r="8" fill="#f0f0ee" opacity=".16"/>')
        g.append(f'<circle cx="{X(n-1):.1f}" cy="{CY(누적[-1]):.1f}" r="3.4" fill="#fff"/>')
        g.append(f'<text x="{X(n-1)-8:.1f}" y="{CY(누적[-1])-9:.1f}" text-anchor="end" '
                 f'font-size="10.5" fill="#fff" font-weight="800">{_flow_amt(누20)}</text>')
        저점i = 누적.index(min(누적))
        반등함 = 0 < 저점i < n-1 and 누적[저점i] < 0 <= 누적[-1]
        if 반등함:
            d = datetime.strptime(표시[저점i]["날짜"], "%Y%m%d")
            g.append(f'<circle cx="{X(저점i):.1f}" cy="{CY(누적[저점i]):.1f}" r="2.8" fill="#7fa8e8"/>')
            g.append(f'<text x="{X(저점i):.1f}" y="{CY(누적[저점i])+14:.1f}" text-anchor="middle" '
                     f'font-size="8.5" fill="#7fa8e8" font-weight="700">{d.month}/{d.day} 바닥</text>')
        눈금 = sorted(set([0, n//3, 2*n//3, n-1]))
        축 = "".join(f'<span>{datetime.strptime(표시[i]["날짜"], "%Y%m%d").strftime("%m/%d")}</span>' for i in 눈금)
        배지HTML = (f'<div class="fs-badges">'
                   f'<span class="fs-cb {"b5" if 누5 >= 0 else "b5n"}">최근 {min(5, N)}일 {_flow_amt(누5)}</span>'
                   f'<span class="fs-cb b20">{n}일 누적 {_flow_amt(누20)}</span></div>')
        범례 = ('<div class="fs-leg"><span><i class="l-sp"></i>현물 누적(실탄)</span>'
              '<span><i class="l-fu"></i>외국인 선물 누적 · 방향 참고</span>'
              '<span><i class="l-rf"></i>5일 전 기준선</span></div>') if len(선물있는) >= 2 else ""
        # ── 코스피 미니 캔들 (실탄 차트 위, 같은 날짜축 공유) ──
        #   ⚠️ flow_history의 '코스피등락'은 최근 며칠만 백필돼 있어(2일치) 차트가 짧게 나온다.
        #      그래서 market_history.json의 '코스피 종가'(17일 온전)를 날짜로 매칭해 쓴다.
        #   실탄 차트와 X좌표(X(i))를 그대로 공유해 날짜가 정확히 맞물린다.
        코스피HTML = ""
        종가맵 = {}
        try:
            _mh = load_json("market_history.json") or {}
            for r in (_mh.get("일별") or []):
                날 = str(r.get("날짜", "")).replace("-", "")   # 2026-08-13 → 20260813
                if 날 and r.get("코스피") is not None:
                    종가맵[날] = float(r.get("코스피"))
        except Exception:
            pass
        종가들 = [종가맵.get(str(x.get("날짜"))) for x in 표시]
        유효 = [v for v in 종가들 if v is not None]
        # 캔들 데이터(시·고·저·종): 표시(flow_history)에 있으면 수집.
        #   20일 이상 온전히 쌓이면 흐름선(A) → 진짜 캔들(B)로 자동 전환한다.
        ohlc = []
        for x in 표시:
            시, 고, 저, 종 = x.get("시가"), x.get("고가"), x.get("저가"), x.get("종가")
            if None not in (시, 고, 저, 종):
                try:
                    ohlc.append((float(시), float(고), float(저), float(종)))
                except (TypeError, ValueError):
                    ohlc.append(None)
            else:
                ohlc.append(None)
        캔들가능 = sum(1 for o in ohlc if o is not None) >= 20
        if len(유효) >= 2:
            KW, KH = W0, 96
            KPT, KPB = 10, 6
            KPH = KH - KPT - KPB
            # 스케일: 캔들이면 고가·저가까지 포함해 잡는다
            if 캔들가능:
                _vals = [o[j] for o in ohlc if o for j in (1, 2)]
                KMIN, KMAX = min(_vals), max(_vals)
            else:
                KMIN, KMAX = min(유효), max(유효)
            kspan = (KMAX - KMIN) or 1
            KY = lambda val: KPT + KPH * (1 - (val - KMIN) / kspan)
            kg = []
            if 캔들가능:
                # ── 진짜 캔들 (B) : 몸통=시가~종가, 꼬리=고가~저가 ──
                for i, o in enumerate(ohlc):
                    if o is None:
                        continue
                    시, 고, 저, 종 = o
                    상승 = 종 >= 시
                    색 = "#C1432B" if 상승 else "#2E6BD6"
                    op = 1 if i == n-1 else .82
                    # 꼬리(고가~저가)
                    kg.append(f'<line x1="{X(i):.1f}" y1="{KY(고):.1f}" x2="{X(i):.1f}" y2="{KY(저):.1f}" '
                              f'stroke="{색}" stroke-width="1" opacity="{op}"/>')
                    # 몸통(시가~종가)
                    상, 하 = (종, 시) if 상승 else (시, 종)
                    kg.append(f'<rect x="{X(i)-BW*0.4:.1f}" y="{KY(상):.1f}" width="{BW*0.8:.1f}" '
                              f'height="{max(1.2, abs(KY(시)-KY(종))):.1f}" fill="{색}" opacity="{op}"/>')
            else:
                # ── 흐름선 (A) : 시고저 부족 → 종가 봉 + 종가선 ──
                prev = None
                for i, v in enumerate(종가들):
                    if v is None:
                        prev = None
                        continue
                    y_now = KY(v)
                    if prev is not None:
                        y_prev = KY(prev)
                        top, bot = min(y_now, y_prev), max(y_now, y_prev)
                        색 = "#C1432B" if v >= prev else "#2E6BD6"
                        kg.append(f'<rect x="{X(i)-BW*0.35:.1f}" y="{top:.1f}" width="{BW*0.7:.1f}" '
                                  f'height="{max(1.5, bot-top):.1f}" rx="1" fill="{색}" opacity="{1 if i==n-1 else .7}"/>')
                    prev = v
                seg, segs = [], []
                for i, v in enumerate(종가들):
                    if v is None:
                        if seg: segs.append(seg); seg = []
                    else:
                        seg.append((i, v))
                if seg: segs.append(seg)
                for s in segs:
                    k선 = " ".join(f'{"L" if j else "M"}{X(i):.1f} {KY(v):.1f}' for j, (i, v) in enumerate(s))
                    kg.append(f'<path d="{k선}" fill="none" stroke="#f0c65a" stroke-width="2" stroke-linejoin="round" opacity=".95"/>')
            # 오늘 끝점 + 종가 라벨
            마지막 = [(i, v) for i, v in enumerate(종가들) if v is not None][-1]
            kg.append(f'<circle cx="{X(마지막[0]):.1f}" cy="{KY(마지막[1]):.1f}" r="3.2" fill="#f0c65a"/>')
            kg.append(f'<text x="{X(마지막[0])-7:.1f}" y="{KY(마지막[1])-7:.1f}" text-anchor="end" '
                      f'font-size="9.5" fill="#f0c65a" font-weight="800">{마지막[1]:,.0f}</text>')
            첫값 = 유효[0]
            누계등락 = (유효[-1] / 첫값 - 1) * 100
            kg.append(f'<text x="{X(마지막[0]):.1f}" y="{KH-1:.1f}" text-anchor="end" font-size="8.5" fill="#9aa0a8" font-weight="700">{누계등락:+.1f}%</text>')
            코스피HTML = (f'<p class="fs-chart-t">📈 코스피 지수 {"캔들" if 캔들가능 else "흐름"} — 최근 {len(유효)}일</p>'
                        + f'<svg viewBox="0 0 {KW} {KH}" preserveAspectRatio="none" style="width:100%;display:block">'
                        + "".join(kg) + '</svg>'
                        + '<div class="fs-chart-div"></div>'
                        + f'<p class="fs-chart-t">📊 실탄이 쌓이는 흐름 — 최근 {min(n,20)}일</p>')

        그래프HTML = (코스피HTML
                     + f'<svg viewBox="0 0 {W0} {H0}" preserveAspectRatio="none" style="width:100%;display:block">'
                     + "".join(g) + f'</svg><div class="fs-x">{축}</div>{범례}')

        # ── 판독문 (규칙 기반) ──
        문장 = []
        if 반등함:
            d = datetime.strptime(표시[저점i]["날짜"], "%Y%m%d")
            흐른일 = n - 1 - 저점i
            문장.append(f"<b>{d.month}/{d.day}</b>까지 빠져나가던 실탄이 그날을 바닥으로 방향을 바꿔, "
                       f"이후 <b>{흐른일}거래일째 쌓이는 중</b>입니다.")
        elif 누적[-1] > 0:
            문장.append(f"최근 {n}거래일간 실탄이 <b>{_flow_amt(누20)}</b> 쌓였습니다.")
        else:
            문장.append(f"최근 {n}거래일간 실탄이 <b>{_flow_amt(누20)}</b> — 빠져나가는 흐름입니다.")
        if n >= 10 and 누20 != 0 and 누5/누20 > 0.55 and (누5 > 0) == (누20 > 0):
            문장.append(f"특히 최근 5일에만 <b>{_flow_amt(누5)}</b> — 누적의 "
                       f"<b>{abs(누5/누20)*100:.0f}%가 이번 주에</b> 움직였습니다. "
                       f"돈이 {'들어오는' if 누20>0 else '빠져나가는'} 속도가 빨라지고 있다는 뜻입니다.")
        elif n >= 10 and (누5 > 0) != (누20 > 0):
            문장.append(f"다만 최근 5일은 <b>{_flow_amt(누5)}</b>로 방향이 반대입니다 — "
                       f"한 달 흐름과 이번 주 흐름이 엇갈리는 구간입니다.")
        판독HTML = f'<p class="fs-read">{" ".join(문장)}</p>'
    else:
        그래프HTML = (f'<div class="fs-building">📈 누적 그래프는 데이터가 쌓이는 대로 여기 그려집니다 '
                     f'(현재 {N}/20거래일)</div>')

    쌓임안내 = f' <span class="fs-n">({N}일치 기준)</span>' if N < 20 else ""

    # ── 가림 처리 (⚠️ f-string 중첩 금지) ──
    #   f-string 안에 같은 따옴표의 f-string을 넣는 문법(PEP 701)은
    #   **Python 3.12부터만** 된다. GitHub Actions는 3.11이라 그대로 두면
    #   발행이 SyntaxError로 죽는다 (2026-08-18 실제 사고).
    #   → 블록을 **먼저 변수로 만들고** 본문에서는 이름만 끼운다.
    나란히블록 = hide("지수와수급나란히", f'''
    <div class="fs-splittitle">📊 지수와 수급, 나란히 보기 <span>— 최근 {min(N,20)}거래일</span></div>
    <div class="fs-cum">
      <div class="fs-cum-head">{배지HTML}</div>
      {그래프HTML}
      {판독HTML}
    </div>''')
    읽는법블록 = hide("지수와수급나란히", f'''<p class="fs-foot">읽는 법: 아래 막대는 <b>그날그날의 실탄</b>(빨강 = 들어옴 · 파랑 = 빠짐), 흰 선은 그것이 <b>차곡차곡 쌓인 누적</b>입니다.
      선이 우상향이면 큰돈이 시장에 쌓이는 중입니다. 흐린 파란 점선은 <b>외국인 선물 누적</b>으로, 현물과 단위가 달라 <b>크기가 아니라 방향만</b> 견주는 참고선입니다. ※ 오늘까지의 수급 사실 정리이며 내일의 예측이나 매매 신호가 아닙니다.</p>''')

    return f'''
  <div class="fs-box">
    <div class="fs-v5">
      <div class="fs-v5-g">{계기HTML}
        <p class="fs-v5-gl" style="color:{FS_BUY if 방향양 else FS_SELL}">평소의 {S실["배수"]:.1f}배</p></div>
      <div class="fs-v5-m">
        <p class="fs-k">오늘의 실탄 <span>외국인+기관이 실제 주식에 넣은 현금</span>{쌓임안내}</p>
        <p class="fs-v5-num" style="color:{FS_BUY if 방향양 else FS_SELL}">{_flow_amt(실탄)}</p>
        <p class="fs-v5-x">{S실["dir"]} <b>{S실["rk"]}위</b> / 최근 {S실["n"]}일 ·
          <b>{S실["연속"]}일 연속 {S실["dir"]}</b></p>
        <div class="fs-chips">{칩HTML}</div>
      </div>
    </div>
    {주체HTML}
    <p class="fs-bandnote">회색 = 그 주체의 <b>평소 하루 폭</b> · 막대가 더 길면 오늘이 그만큼 컸다는 뜻</p>
    <div class="fs-checks">
      <p class="fs-checks-t">🔍 두 가지만 확인하면 됩니다</p>
      {"".join(행들)}
    </div>
    <div class="fs-splittitle">🕒 하나의 타임라인 <span>— 지수 + 수급 + 선물 + 비차익</span></div>
    {build_flow_timeline(이력)}
    <div class="fs-read">
      <p class="fs-read-t">🧺 오늘의 비차익 판독</p>
      <p class="fs-read-b">{바스켓읽기}</p>
    </div>
    <div class="fs-read stat">
      <p class="fs-read-t">📊 비중 구간별 사후 통계 <span>(5거래일 뒤)</span></p>
      <p class="fs-read-b dim">{바스켓통계}</p>
    </div>
    {f'<p class="fs-combo"><b>{조합[1]}</b> — {조합[2]}</p>' if 조합 else ''}
    {f'<p class="fs-warn">{만기배지} — {만기설명}</p>' if 만기배지 else ''}
    {나란히블록}{hidden_note()}
    {flow_pattern_analysis()}
    {읽는법블록}
  </div>'''


def build_macro_card(item, 해설=""):
    if not item:
        return '<div class="mr-card"><p class="mr-label">—</p><p class="mr-val">— (준비중)</p></div>'
    cls = "dn" if item["등락률"] < 0 else "up"
    단위 = item.get("단위", "")
    값표시 = f"{단위}{item['값']:,.2f}" if 단위 == "$" else f"{item['값']:,.2f}{단위}"
    해설HTML = f'<p class="mr-comment">{해설}</p>' if 해설 else ''
    return f'''
    <div class="mr-card">
      <p class="mr-label">{item['표시명']}</p>
      <p class="mr-val">{값표시}</p>
      <span class="{cls}" style="font-size:11px;font-weight:700">{item['등락률']:+.2f}%</span>
      {해설HTML}
    </div>'''


def build_html(data, report):
    지수 = (data.get("지수수급") or {}).get("지수") or {}
    코 = 지수.get("코스피", {})
    닥 = 지수.get("코스닥", {})
    코수 = (data.get("지수수급") or {}).get("코스피_수급") or {}
    닥수 = (data.get("지수수급") or {}).get("코스닥_수급") or {}
    해석 = (report or {}).get("해석글", {})
    오늘의시장 = 해석.get("오늘의_시장", "— (Claude API 해석글 미생성: 충전 후 generate_report.py 재실행 필요)")
    오늘한줄평 = 해석.get("한줄평", "— (충전 후 자동 생성: 오늘 시장을 한 문장으로 압축)")
    오늘의문장 = 해석.get("오늘의_한문장", "오늘 시장이 준 교훈이 이 자리에 담깁니다. (Claude 해석 연동 후 자동 생성)")
    프로의시선 = 해석.get("프로의시선") or {}
    오늘의공부 = 해석.get("오늘의_공부", "")
    # 3개월 항로 — 이력이 충분할 때만 별도 섹션으로 붙는다(부족하면 빈 문자열).
    # 시장을 나눠 두 장으로 — 코스닥은 변동폭이 구조적으로 커서 섞으면 평균이 끌려간다.
    # 구역 추이는 v-l8에서 '섹터 성적표'(핵심편)로 흡수됐다 — 심층편에서는 뺀다.
    _zone_trend_block = ""
    # 포착 항로는 v-m2에서 '기간 탭 × 시장 카드' 하나로 통합됐다.

    날짜 = f"{data['날짜'][:4]}.{data['날짜'][4:6]}.{data['날짜'][6:]}"

    # ── 다음 거래일 라벨 ──
    #   금요일·연휴 직전에는 "내일"이 틀린 말이 된다. 화면 제목도 데이터에 맞춘다.
    #   (예: 금요일 리포트 → "🌅 화요일(8/18)장, 이것만 기억하세요")
    try:
        _tc = trading_day_context(datetime.strptime(data["날짜"], "%Y%m%d").date())
        _NEXT_LABEL = _tc["다음거래일표현"]
        _휴장안내 = _tc["휴장안내"]
        _오늘휴장 = _tc["오늘휴장"]
    except Exception:
        _NEXT_LABEL, _휴장안내, _오늘휴장 = "내일", "", False

    # 휴장일에 돌리면 수집값이 직전 거래일과 같다 — 조용히 넘기지 않고 명시한다.
    휴장배너 = ('<div style="margin:0 0 12px;padding:10px 12px;background:#2a2118;'
              'border:1px solid #5a4520;border-radius:10px">'
              '<p style="margin:0;font-size:12.5px;color:#f0c65a;font-weight:700">'
              '📅 오늘은 증시 휴장일입니다</p>'
              '<p style="margin:4px 0 0;font-size:11.5px;color:#c9ced6;line-height:1.6">'
              '장이 열리지 않아 아래 수치는 <b>직전 거래일과 동일</b>합니다. '
              f'다음 거래일은 <b style="color:#f0c65a">{_NEXT_LABEL}</b>입니다.</p></div>'
              ) if _오늘휴장 else ''

    # ── 공유 카드(OG) — 같은 문장이 세 번 겹치던 문제를 역할 분담으로 해결 ──
    #   ⚠️ 중복 제거(v-l5): 예전엔 og:title도 한줄평이라, 썸네일 그림 속 한줄평과
    #      카톡 말풍선 한줄평까지 **같은 문장이 세 번** 나와 지저분했다.
    #      자리마다 서로 다른 것만 담는다.
    #        썸네일 그림 = 한줄평 + 공감문구   (make_thumb.py)
    #        og:title    = 오늘의 정의        (여기 — 그림에 없는 문장)
    #        og:desc     = 관제지수 + 날짜     (여기)
    #        텔레그램 캡션 = 브랜드 + 날짜 + 링크 (notify_telegram.py)
    관제 = data.get("관제지수") or {}
    _정의 = ((해석.get("핵심편") or {}).get("오늘의정의") or "").strip()
    if _정의:
        og_title = _정의
    elif isinstance(오늘한줄평, str) and not 오늘한줄평.startswith("—"):
        og_title = 오늘한줄평
    else:
        og_title = f"차트프로 관제탑 {날짜}"
    _d = data["날짜"]
    _요일 = "월화수목금토일"[datetime.strptime(_d, "%Y%m%d").weekday()]
    _점수 = 관제.get("점수")
    _구간 = 관제.get("구간") or ""
    _앞 = (f"관제지수 {_점수}" + (f" · {_구간}" if _구간 else "")) if _점수 is not None else "차트프로 관제탑"
    og_desc = f"{_앞} · {int(_d[4:6])}월 {int(_d[6:])}일({_요일}) 마감"
    # ⚠️ 캐시 대응: 텔레그램·카톡은 링크를 처음 열어본 순간의 미리보기를 저장해두고
    #    한동안 다시 안 가져온다. 같은 날 다시 발행하면 이미지 파일은 바뀌었는데
    #    미리보기는 옛 그림 그대로다. 이미지 주소 뒤에 빌드 시각을 붙여
    #    "다른 파일"로 보이게 하면 다시 가져올 확률이 올라간다.
    _ver = datetime.now().strftime("%H%M")
    og_img = f"https://sixline86-ship-it.github.io/chartpro/thumb/{_d}.png?v={_d}{_ver}"
    og_url = f"https://sixline86-ship-it.github.io/chartpro/report_{_d}.html"

    return f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>차트프로 관제탑 · {날짜}</title>
<meta property="og:title" content="{og_title}">
<meta property="og:description" content="{og_desc}">
<meta property="og:type" content="article">
<meta property="og:image" content="{og_img}">
<meta property="og:image:width" content="1200">
<meta property="og:image:height" content="630">
<meta property="og:url" content="{og_url}">
<meta name="twitter:card" content="summary_large_image">
<style>
:root{{
  --font-sans:'Pretendard','Apple SD Gothic Neo','Malgun Gothic',system-ui,sans-serif;
  --ink:#1a1a1a; --sub:#6b6b6b; --bg:#fff; --bg2:#f6f5f3; --line:#e2e0dc;
  --up:#C1432B; --dn:#2E6BD6; --rmd:8px; --rlg:12px;
  --pink:#7a2b4d; --pink2:#9c3862; --pink-line:#c86a92;
}}
*{{box-sizing:border-box;margin:0;padding:0}}
body{{background:#f0efec;padding:24px 12px;display:flex;justify-content:center;font-family:var(--font-sans)}}
.rp{{padding:1.5rem 1.75rem 2rem;background:var(--bg);max-width:780px;width:100%;border-radius:16px;box-shadow:0 2px 24px rgba(0,0,0,.06)}}
.deep-wrap{{background:#e4e7ec;background:linear-gradient(180deg,#e6e9ef,#dfe3ea);margin:.2rem -1.75rem 0;padding:1.4rem 1.75rem 1.5rem;border-top:3px solid #c0c6d0}}
.deep-wrap .sec-label{{color:#2b3038}}
.deep-wrap .sec-label small{{color:#7a828d}}
a{{color:inherit;text-decoration:none}}
.top-bar{{display:flex;justify-content:space-between;padding-bottom:1rem;border-bottom:.5px solid var(--line);margin-bottom:.9rem}}
.rp-title{{font-size:17px;font-weight:800}}
.badge{{font-size:11px;color:var(--sub);background:var(--bg2);padding:3px 9px;border-radius:var(--rmd);border:.5px solid var(--line);height:fit-content}}
.sec-label{{display:block;font-size:17.5px;font-weight:800;color:var(--ink);letter-spacing:-.01em;text-transform:none;margin:1.6rem 0 .7rem;line-height:1.35}}
.sec-label small{{display:block;font-size:10px;font-weight:700;color:var(--sub);letter-spacing:.1em;margin-bottom:2px}}
.sec-label i{{font-style:normal;font-weight:500;color:#a8aeb6;letter-spacing:0}}
.sec-label::after{{content:'';display:block;height:.5px;background:var(--line);margin-top:.5rem}}
.up{{color:var(--up);font-weight:600}} .dn{{color:var(--dn);font-weight:600}} .smut{{color:var(--sub)}}

/* ── 게이지 ── */
.gauge-box{{background:linear-gradient(180deg,#23262b,#2c3038);border-radius:var(--rlg);padding:1.15rem 1.25rem;color:#e8e6e2;margin-bottom:1rem}}
.gz-top{{display:flex;gap:18px;align-items:center;flex-wrap:wrap}}
.gz-numwrap{{text-align:center;flex-shrink:0}}
.gz-num{{font-size:40px;font-weight:800;color:#7fa8e8;line-height:1}}
.gz-lab{{font-size:12px;font-weight:700;color:#7fa8e8;margin-top:3px}}
.gz-bodywrap{{flex:1;min-width:230px}}
.gz-title{{font-size:12px;font-weight:700;color:#c8ccd2;margin-bottom:9px}}
.gz-track{{position:relative;height:12px;border-radius:6px;display:flex;overflow:visible}}
.gz{{height:100%;width:20%}}
.z1{{background:#2E6BD6;border-radius:6px 0 0 6px}} .z2{{background:#6b93d8}} .z3{{background:#8a8f98}} .z4{{background:#d08a6a}} .z5{{background:#C1432B;border-radius:0 6px 6px 0}}
.gz-needle{{position:absolute;top:-5px;width:3px;height:22px;background:#fff;border-radius:2px;box-shadow:0 0 8px rgba(255,255,255,.8);transform:translateX(-50%)}}
.gz-scale{{display:flex;margin-top:7px}}
.gz-scale span{{width:20%;text-align:center;font-size:9.5px;color:#8a909a;font-weight:600}}
.gz-toggle{{margin-top:.9rem;width:100%;font-size:11px;font-weight:600;color:#c8ccd2;background:rgba(255,255,255,.06);border:.5px solid rgba(255,255,255,.14);border-radius:99px;padding:6px 0;cursor:pointer;font-family:var(--font-sans)}}
.gz-detail{{margin-top:.7rem;background:rgba(0,0,0,.22);border-radius:var(--rmd);padding:.7rem .9rem}}
.gz-row{{display:grid;grid-template-columns:96px 42px 62px 1fr;gap:6px;align-items:center;padding:6px 0;border-bottom:.5px solid rgba(255,255,255,.08);font-size:11px}}
.gz-row:last-of-type{{border-bottom:none}}
.gz-el{{font-weight:700;color:#e8e6e2}}
.gz-sc{{font-weight:800;color:#7fa8e8;text-align:right}}
.gz-w{{color:#9aa0a8;font-size:10px}}
.gz-ev{{color:#c3c8ce;font-size:10.5px}}
.gz-note{{font-size:9.5px;color:#8a909a;line-height:1.6;margin-top:.6rem}}
.gz-oneline{{font-size:12px;color:#e8e6e2;line-height:1.7;margin-top:.9rem;padding-top:.85rem;border-top:.5px solid rgba(255,255,255,.1)}}
.gz-oneline b{{color:#7fa8e8}}
.gz-badges{{display:flex;gap:6px;flex-wrap:wrap;margin-top:.7rem}}
.gz-badge{{font-size:10.5px;font-weight:600;background:rgba(255,255,255,.08);border:.5px solid rgba(255,255,255,.14);color:#dfe3e8;padding:3px 10px;border-radius:99px}}

/* ── 지수+수급 ── */
.idx-grid{{display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-bottom:1rem}}
.idx-card2{{background:#23262b;color:#eee;border-radius:var(--rmd);padding:.8rem .9rem}}
.ic-mkt{{font-size:10px;color:#9aa0a8}}
.ic-num{{font-size:21px;font-weight:800}}
.ic-chg-up{{color:#ff6b4a;font-weight:700}} .ic-chg-dn{{color:#5b9bff;font-weight:700}}
.sup-grid{{display:grid;grid-template-columns:repeat(3,1fr);gap:4px;margin-top:9px}}
.sup{{background:rgba(0,0,0,.22);border-radius:6px;padding:5px 4px;text-align:center}}
.sup-who{{font-size:9px;color:#9aa0a8}}
.sup-amt{{font-size:11.5px;font-weight:800}}
.sup-amt.up{{color:#ff6b4a}} .sup-amt.dn{{color:#5b9bff}} .sup-amt.smut{{color:#c3c8ce}}

.today-market{{background:#EAF3DE;border-radius:var(--rlg);padding:.85rem 1.05rem;font-size:12.5px;color:#3B6D11;line-height:1.75;margin-bottom:1rem}}

/* ── 섹터 지형도 (v8 스타일) ── */
.terrain-box{{background:linear-gradient(180deg,#23262b,#2c3038);border-radius:var(--rlg);padding:1rem 1.15rem 1.1rem;margin-bottom:1rem}}
.terrain-title{{font-size:10.5px;font-weight:700;color:#c8ccd2;margin-bottom:.55rem;letter-spacing:.04em}}
.bar-chart{{display:grid;grid-template-columns:repeat(6,1fr);gap:6px}}
.bar-col{{display:flex;flex-direction:column;align-items:center}}
.bar-zone{{position:relative;width:100%;height:132px}}
.bar-zone::after{{content:'';position:absolute;left:6%;right:6%;top:var(--zero,50%);height:1px;background:rgba(255,255,255,.25)}}
.bar{{position:absolute;left:50%;transform:translateX(-50%);width:55%;max-width:24px;border-radius:4px;z-index:1}}
.bar.pos{{background:linear-gradient(180deg,#ff8a6e,#C1432B)}}
.bar.neg{{background:linear-gradient(180deg,#2E6BD6,#7fa8e8)}}
.bar-val{{position:absolute;left:50%;transform:translateX(-50%);font-size:10px;font-weight:800;white-space:nowrap;z-index:2}}
.bar-val.pos{{color:#ef8a72}} .bar-val.neg{{color:#7fa8e8}}
.bar-name{{font-size:10px;font-weight:600;color:#c8ccd2;margin-top:6px;white-space:nowrap}}

/* ── 주도섹터 (v8 라이트 카드) ── */
.sector-grid{{display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-bottom:.7rem}}
.sector-card{{background:var(--bg);border:.5px solid var(--line);border-radius:var(--rlg);overflow:hidden;box-shadow:0 1px 3px rgba(0,0,0,.03)}}
.sc-head{{padding:.7rem .9rem .55rem;border-bottom:.5px solid var(--line);background:linear-gradient(135deg,#FBFAF8,#F4F1EB);position:relative}}
.sc-head::before{{content:'';position:absolute;left:0;top:0;bottom:0;width:3px;background:var(--dn)}}
.sc-head.pos::before{{background:var(--up)}}
.sc-name-row{{display:flex;align-items:baseline;gap:6px}}
.sc-name{{font-size:14px;font-weight:800;color:var(--ink)}}
.sc-sfx{{font-size:10px;color:var(--sub);font-weight:600}}
.sc-chg{{font-size:12px;font-weight:800;padding:2px 8px;border-radius:6px;margin-left:auto;background:rgba(46,107,214,.1);color:var(--dn)}}
.sc-chg.pos{{background:rgba(193,67,43,.1);color:var(--up)}}
.sc-score{{font-size:10px;color:var(--sub);margin-top:5px;font-weight:600}}
.sc-strline{{margin-top:4px}}
.sc-str{{display:inline-block;font-size:9.5px;font-weight:700;color:#b98a1a;background:rgba(224,192,96,.14);border:.5px solid rgba(224,192,96,.3);border-radius:5px;padding:2px 7px;line-height:1.4;word-break:keep-all}}
.sc-str b{{color:#8a6a10;font-weight:800}}
.sc-str.new{{color:#2a7d5a;background:rgba(74,222,128,.12);border-color:rgba(74,222,128,.3)}}
.sc-str.new b{{color:#1a6a44}}
.sc-list{{padding:.15rem .9rem .5rem}}
.sc-cols{{display:grid;grid-template-columns:1.1fr 72px 58px 64px;font-size:9.5px;color:#a8a49c;font-weight:600;padding:6px 0 3px;border-bottom:.5px solid var(--line)}}
.sc-cols span:not(:first-child){{text-align:right}}
.sc-row{{display:grid;grid-template-columns:1.1fr 72px 58px 64px;align-items:center;padding:6px 0;border-bottom:.5px solid var(--line);font-size:12px}}
.sc-row:last-child{{border-bottom:none}}
.sc-stock{{font-weight:700;color:var(--ink);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}}
.sc-price{{text-align:right;color:var(--sub);font-variant-numeric:tabular-nums}}
.sc-rate{{text-align:right;font-weight:800;font-variant-numeric:tabular-nums}}
.sc-rate.up{{color:var(--up)}} .sc-rate.dn{{color:var(--dn)}}
.sc-vol{{text-align:right;color:#8a6d3b;font-weight:700;font-size:11px;font-variant-numeric:tabular-nums}}

/* ── 공시 ── */
.disc-box{{background:#23262b;border-radius:var(--rlg);padding:1rem 1.15rem;margin-bottom:.6rem}}
.disc-row{{display:block;padding:.85rem 0;border-bottom:.5px solid rgba(255,255,255,.08)}}
.disc-row:last-child{{border-bottom:none}}
.disc-head{{display:flex;align-items:center;gap:8px}}
.disc-name{{font-size:13.5px;font-weight:800;color:#fff}}
.stars{{font-size:12px;color:#E0A100;margin-left:auto}}
.stars .off{{color:#565b64}}
.disc-note{{font-size:11.5px;color:#c3c8ce;line-height:1.6}}
.disc-lnk{{color:#8a909a;font-size:10px}}

/* ── 공용 ── */
.pending{{background:var(--bg2);border:.5px dashed var(--line);border-radius:var(--rmd);padding:.9rem 1rem;font-size:11.5px;color:var(--sub);margin-bottom:1rem;line-height:1.7;text-align:center}}

/* 핵심 이슈 */
.issue-box{{background:linear-gradient(180deg,#23262b,#2c3038);border-radius:var(--rlg);padding:.9rem 1.1rem;margin-bottom:1rem}}
.iss{{display:flex;align-items:flex-start;gap:8px;padding:7px 0;border-bottom:.5px solid rgba(255,255,255,.08);line-height:1.65}}
.iss:last-child{{border-bottom:none;padding-bottom:0}}
.iss-links{{display:block;margin-top:3px}}
.iss-link{{font-size:9.5px;color:#9fb4e0;text-decoration:none;font-weight:600;margin-right:8px}}
.iss-link:hover{{text-decoration:underline}}
.itag{{font-size:10px;font-weight:600;padding:2px 7px;border-radius:4px;white-space:nowrap;flex-shrink:0;margin-top:2px;background:#E6F1FB;color:#0C447C}}
.iss-text{{font-size:12.5px;color:#dfe3e8}}

/* 핵심 뉴스 */
.news-wrap{{background:var(--bg);border:.5px solid var(--line);border-radius:var(--rlg);overflow:hidden;margin-bottom:.6rem}}
.news-item{{display:flex;gap:11px;padding:.75rem 1.15rem;border-bottom:.5px solid var(--line);align-items:flex-start}}
.news-item:last-child{{border-bottom:none}}
.news-rank{{font-size:13px;font-weight:800;color:#c9c1b0;font-style:italic;flex-shrink:0;width:20px;line-height:1.5}}
.news-body{{flex:1}}
.news-title{{font-size:12.5px;font-weight:700;color:var(--ink);line-height:1.55;margin-bottom:3px}}
.news-tag{{display:inline-block;font-size:9.5px;font-weight:700;padding:1px 6px;border-radius:4px;margin-right:5px;vertical-align:middle}}
.nt-market{{background:#E6F1FB;color:#0C447C}} .nt-stock{{background:#FAECE7;color:#993C1D}}
.nt-policy{{background:#FAEEDA;color:#854F0B}} .nt-global{{background:#EEEDFE;color:#3C3489}}
.news-insight{{font-size:11.5px;color:var(--sub);line-height:1.6}}
.news-a{{text-decoration:none;color:inherit}}
.news-a:hover .news-tag{{filter:brightness(.94)}}
.news-item:hover{{background:#FBFAF8}}
.news-go{{font-size:10px;color:#b0aca6;margin-left:4px;vertical-align:middle}}
.news-a:hover{{text-decoration:underline;text-underline-offset:3px}}
.mf-sub-x{{font-size:9.5px;font-weight:600;color:#8a909a}}
.news-foot{{font-size:10px;color:var(--sub);line-height:1.6;margin:-.2rem 0 1rem;padding:0 .2rem}}
/* 지난 리포트 아카이브 */
.arch-wrap{{background:var(--bg2);border:.5px solid var(--line);border-radius:var(--rlg);padding:.85rem 1rem;margin:1.4rem 0 .4rem}}
.arch-head{{font-size:11.5px;font-weight:800;color:var(--ink);margin-bottom:.6rem;letter-spacing:-.01em}}
.arch-grid{{display:flex;flex-wrap:wrap;gap:6px}}
.arch-link{{font-size:11.5px;font-weight:600;color:var(--ink);background:var(--bg);border:.5px solid var(--line);border-radius:99px;padding:5px 12px;text-decoration:none;font-variant-numeric:tabular-nums;white-space:nowrap}}
.arch-link:hover{{background:#23262b;color:#fff;border-color:#23262b}}
.arch-empty{{font-size:11px;color:var(--sub)}}
.silent-wrap{{background:linear-gradient(180deg,#23262b,#2c3038);border-radius:var(--rlg);padding:.95rem 1.05rem;margin-bottom:1rem}}
.silent-head{{font-size:12.5px;font-weight:800;color:#c9c4f0;margin-bottom:.6rem}}
.si-item{{display:flex;gap:9px;padding:7px 0;border-bottom:.5px solid rgba(255,255,255,.08);font-size:12.5px;line-height:1.75;color:#dfe3e8}}
.si-item:last-child{{border-bottom:none;padding-bottom:0}}
.si-lens{{font-size:10px;font-weight:700;background:rgba(255,255,255,.12);color:#c9c4f0;padding:2px 8px;border-radius:4px;white-space:nowrap;flex-shrink:0;margin-top:3px;height:fit-content}}
.study-src{{font-size:10.5px;font-weight:600;color:#5b8a2a;background:#dcebc8;display:inline-block;padding:2px 9px;border-radius:99px;margin:2px 0 6px}}
.study-box{{background:linear-gradient(135deg,#EAF3DE,#f2f7e8);border-radius:var(--rlg);padding:.95rem 1.1rem;margin-bottom:1rem;font-size:12.5px;color:#3B6D11;line-height:1.8}}
.hidden-block{{display:none}} .hidden-block.open{{display:block}}
.more-btn{{display:block;width:100%;text-align:center;font-size:11.5px;font-weight:600;color:var(--sub);background:var(--bg2);border:.5px solid var(--line);border-radius:99px;padding:7px 0;cursor:pointer;font-family:var(--font-sans);margin-bottom:1rem}}
.macro-row{{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:8px;margin-bottom:1rem}}
.mr-card{{background:var(--bg2);border-radius:var(--rmd);padding:.7rem .9rem}}
.mr-label{{font-size:11px;color:var(--sub);margin-bottom:3px}}
.mr-val{{font-size:15px;font-weight:700;color:var(--sub)}}
.mr-comment{{font-size:10.5px;color:var(--sub);margin-top:6px;line-height:1.6}}
.watch-item{{background:#23262b;color:#e8e6e2;border-radius:var(--rmd);padding:.75rem .95rem;font-size:12.5px;line-height:1.7;margin-bottom:8px}}
.tv-wrap{{background:var(--bg);border:.5px solid var(--line);border-radius:var(--rlg);overflow:hidden;margin-bottom:1rem}}
.tv-row-wrap{{padding:.8rem 1.1rem;border-bottom:.5px solid var(--line)}}
.tv-row{{display:flex;align-items:center;gap:8px;margin-bottom:5px;flex-wrap:wrap}}
.tv-ch{{font-size:12.5px;font-weight:800;color:var(--ink)}}
.tv-angle{{font-size:10px;color:var(--sub);background:var(--bg2);padding:2px 7px;border-radius:4px;white-space:nowrap}}
.tv-see{{margin-left:auto;font-size:10.5px;font-weight:700;color:#fff;background:#23262b;padding:3px 11px;border-radius:99px;white-space:nowrap}}
.tv-title{{font-size:11.5px;color:var(--sub);line-height:1.5;margin-bottom:4px}}
.tv-sum{{font-size:12.5px;color:var(--ink);line-height:1.75}}
.tv-note{{font-size:10px;color:var(--sub);line-height:1.6;padding:.7rem 1.1rem;background:var(--bg2)}}
.tv-lead{{padding:1rem 1.15rem .95rem;background:linear-gradient(135deg,#F7F3EC,#FBF9F5);border-bottom:.5px solid var(--line)}}
.tv-lead-badge{{display:inline-block;font-size:10.5px;font-weight:800;color:#8a5a1f;background:#F3E4C8;padding:3px 10px;border-radius:99px;margin-bottom:.55rem}}
.tv-lead-ch{{font-size:14px;font-weight:800;color:var(--ink);margin-bottom:.45rem;display:flex;align-items:center;gap:7px}}
.tv-dot{{width:7px;height:7px;border-radius:50%;background:var(--up);flex-shrink:0}}
.tv-lead-body{{font-size:12.5px;color:var(--ink);line-height:1.85;margin-bottom:.6rem}}
.tv-others{{padding:.15rem 1.15rem}}
.tv-clickable{{cursor:pointer}}
.tv-see-sm{{margin-left:auto;font-size:10.5px;font-weight:700;color:#fff;background:#23262b;padding:3px 12px;border-radius:99px;white-space:nowrap}}
.tv-body-hidden{{max-height:0;overflow:hidden;transition:max-height .28s ease}}
.tv-body-hidden.open{{max-height:500px;padding-bottom:11px}}
.tv-link-sm{{display:inline-block;font-size:10.5px;font-weight:700;color:var(--dn);margin-top:5px}}
.disc-why{{font-size:11px;color:#9fb4cc;line-height:1.6;margin-top:6px;padding-left:2px}}
.study-no{{font-size:10px;font-weight:700;color:#3B6D11;letter-spacing:.06em}}
.study-term{{font-size:15px;font-weight:800;color:#2c520c;margin:4px 0 10px;line-height:1.4}}
.study-step{{display:flex;gap:9px;padding:7px 0;border-bottom:.5px solid #d5e3c2;font-size:12.5px;line-height:1.75;color:#3B6D11}}
.study-step:last-of-type{{border-bottom:none}}
.study-k{{font-size:10px;font-weight:800;background:#d9e8c4;color:#2c520c;padding:2px 8px;border-radius:4px;white-space:nowrap;flex-shrink:0;margin-top:3px;height:fit-content}}
.study-memo{{background:#2c520c;color:#eef5e2;border-radius:var(--rmd);padding:.6rem .9rem;font-size:12px;font-weight:600;margin-top:.7rem;line-height:1.6}}

/* ── 회전율 레이더 ── */
.rd-box{{background:var(--bg);border:.5px solid var(--line);border-radius:var(--rlg);padding:1rem 1.1rem;margin-bottom:1rem}}
.devnote{{background:#FFF8E6;border:.5px dashed #E0C060;border-radius:var(--rmd);padding:.55rem .8rem;font-size:10px;color:#7a5a10;line-height:1.7;margin-bottom:.8rem}}
.devnote b{{color:#5a4208}}
.rd-lead{{font-size:11.5px;color:var(--sub);line-height:1.7;margin-bottom:.9rem;background:var(--bg2);padding:.7rem .85rem;border-radius:var(--rmd)}}
.rd-market{{margin-bottom:.8rem}}
.rd-mkt-name{{font-size:12px;font-weight:800;color:var(--ink);margin-bottom:.5rem}}
.rd-row{{display:flex;align-items:center;gap:10px;padding:8px 0;border-bottom:.5px solid var(--line)}}
.rd-row:last-child{{border-bottom:none}}
.rd-rank{{font-size:13px;font-weight:800;color:#c9c1b0;font-style:italic;width:20px;flex-shrink:0;text-align:center}}
.rd-info{{flex:1;min-width:0}}
.rd-name{{font-size:12.5px;font-weight:700;color:var(--ink);display:flex;align-items:center;gap:6px;flex-wrap:wrap}}
.rd-tag{{font-size:9px;font-weight:700;padding:1px 6px;border-radius:4px;white-space:nowrap}}
.rd-new{{background:#FAECE7;color:#993C1D}} .rd-stay{{background:#FAEEDA;color:#854F0B}}
.rd-meta{{font-size:10.5px;color:var(--sub);margin-top:2px}}
.rd-nums{{text-align:right;flex-shrink:0}}
.rd-score{{display:block;font-size:15px;font-weight:800;color:#8a5a1f}}\n.rd-boom{{background:#FAECE7;color:#C1432B}}
.rd-chg{{font-size:11px;font-weight:700}}
.ac-gap{{text-align:right;flex-shrink:0}}
.ac-gap b{{display:block;font-size:14px;font-weight:800;color:#8a5a1f}}
.ac-char{{display:block;font-size:9px;color:var(--sub);white-space:nowrap}}
.ac-two{{display:grid;grid-template-columns:1fr 1fr;gap:10px}}
.ac-col{{background:var(--bg2);border-radius:var(--rmd);padding:.7rem .8rem}}
.ac-col-t{{font-size:12px;font-weight:800;color:var(--ink)}}
.ac-col-s{{font-size:9.5px;color:var(--sub);margin:2px 0 .5rem}}
.ac-rank{{font-size:11px;font-weight:800;color:#c9c1b0;font-style:italic;width:14px;flex-shrink:0}}
.ac-info{{flex:1;min-width:0}}
.ac-name{{font-size:11.5px;font-weight:700;color:var(--ink);display:flex;align-items:center;gap:4px;flex-wrap:wrap}}
.ac-meta{{font-size:9.5px;color:var(--sub);margin-top:1px}}
.ac-val{{font-size:11.5px;font-weight:800;color:var(--up);flex-shrink:0;text-align:right}}
.ac-solo{{background:var(--bg);color:var(--sub);border:.5px solid var(--line)}}
.ac-note{{font-size:10px;color:var(--sub);margin-top:.6rem}}
@media (max-width:600px){{ .ac-gap{{text-align:right;flex-shrink:0}}
.ac-gap b{{display:block;font-size:14px;font-weight:800;color:#8a5a1f}}
.ac-char{{display:block;font-size:9px;color:var(--sub);white-space:nowrap}}
.ac-two{{grid-template-columns:1fr}} }}
.ac-group{{margin-bottom:.8rem}}
.ac-row{{display:flex;align-items:center;gap:10px;padding:8px 0;border-bottom:.5px solid var(--line)}}
.ac-row:last-child{{border-bottom:none}}
.ac-tag{{font-size:9px;font-weight:700;padding:1px 6px;border-radius:4px;white-space:nowrap}}
.ac-days{{background:var(--bg2);color:var(--sub)}}
.ac-both{{background:#FAECE7;color:#C1432B}}
.ac-money{{display:block;font-size:14px;font-weight:800}}
.ac-ratio{{font-size:10px;color:var(--sub)}}
.sort-tabs{{display:flex;border:.5px solid var(--line);border-radius:99px;overflow:hidden;width:fit-content;margin-bottom:.8rem}}
.sort-tab{{font-size:11px;font-weight:600;padding:5px 16px;background:var(--bg);color:var(--sub);border:none;cursor:pointer;font-family:var(--font-sans)}}
.sort-tab.active{{background:#23262b;color:#fff}}
.rd-re{{background:#EEEDFE;color:#3C3489}}
.rd-empty{{font-size:11.5px;color:var(--sub);padding:.5rem 0}}
.ac-long{{margin-top:1rem;border-top:.5px solid var(--line);padding-top:.85rem}}
.ac-long-t{{font-size:12px;font-weight:800;color:var(--ink);margin-bottom:.2rem}}
.ac-long-s{{font-size:10.5px;color:var(--sub);line-height:1.65;margin-bottom:.6rem}}
.ac-star2{{display:block;margin-top:4px;font-size:9.5px;font-weight:800;color:#b8860b;background:#fdf3d8;border-radius:99px;padding:2px 9px;width:fit-content}}
.ac-star{{font-size:9px;font-weight:800;color:#b8860b;background:#fdf3d8;border-radius:99px;padding:1px 7px;margin-left:4px}}
.rd-foot{{font-size:9.5px;color:var(--sub);line-height:1.6;margin-top:.5rem;padding-top:.7rem;border-top:.5px solid var(--line)}}

.story-bridge{{display:flex;gap:9px;align-items:flex-start;margin:1rem 0;padding:.85rem 1rem;background:linear-gradient(90deg,rgba(91,155,255,.1),rgba(91,155,255,.03));border-left:3px solid #5b9bff;border-radius:9px}}
.story-bridge .st-ic{{font-size:16px;flex-shrink:0;line-height:1.4}}
.story-bridge .st-txt{{font-size:12.5px;color:var(--ink);line-height:1.7;word-break:keep-all}}
.story-bridge .st-txt b{{color:var(--ink);font-weight:800}}
.story-bridge .st-turn{{color:#e0813a!important}}
/* ── 어제의 채점표 ── */
.score-box{{background:#FBFAF8;border:.5px solid var(--line);border-radius:var(--rlg);padding:.95rem 1.1rem;margin-bottom:1rem}}
.score-head{{font-size:12px;font-weight:800;color:var(--ink);margin-bottom:.7rem;display:flex;align-items:center;gap:8px;flex-wrap:wrap}}
.score-tally{{font-size:10.5px;font-weight:700;color:#8a5a1f;background:#F3E4C8;padding:2px 9px;border-radius:99px}}
.score-row{{display:flex;gap:10px;padding:8px 0;border-bottom:.5px solid var(--line)}}
.score-row:last-of-type{{border-bottom:none}}
.score-mark{{font-size:15px;font-weight:800;width:22px;text-align:center;flex-shrink:0;line-height:1.5}}
.sc-o{{color:var(--up)}} .sc-x{{color:var(--dn)}} .sc-t{{color:#a8a49c}}
.score-item{{font-size:12px;color:var(--ink);line-height:1.6;font-weight:600}}
.score-why{{font-size:11px;color:var(--sub);line-height:1.6;margin-top:3px}}
.score-foot{{font-size:9.5px;color:var(--sub);margin-top:.6rem;line-height:1.5}}

/* ── 돈의 이동경로 ── */
.mf-box{{background:linear-gradient(180deg,#23262b,#2c3038);border-radius:var(--rlg);padding:1.05rem 1.15rem;color:#e8e6e2;margin-bottom:1rem}}
.mf-summary{{font-size:13px;font-weight:700;color:#fff;line-height:1.7;margin-bottom:.9rem}}
.mf-move{{display:flex;align-items:center;gap:10px;background:rgba(0,0,0,.22);border-radius:var(--rmd);padding:.75rem .85rem}}
.mf-side{{flex:1;min-width:0}}
.mf-side-t{{font-size:10px;font-weight:700;margin-bottom:6px}}
.mf-side-t.out{{color:#7fa8e8}} .mf-side-t.in{{color:#ff8a6e}}
.mf-chips{{display:flex;flex-wrap:wrap;gap:4px}}
.mf-chip{{font-size:10.5px;font-weight:700;padding:3px 9px;border-radius:99px;white-space:nowrap}}
.mf-chip.out{{background:rgba(46,107,214,.25);color:#bcd2f5}}
.mf-chip.in{{background:rgba(193,67,43,.28);color:#ffd0c0}}
.mf-none{{font-size:10.5px;color:#8a909a}}
.mf-arrow{{font-size:18px;color:#8a909a;flex-shrink:0}}
/* ══ 핵심편·수급온도 — 시안 v5 (화이트리스트 이식) ══ */

.top-bar{{display:flex;align-items:flex-start;justify-content:space-between;padding-bottom:1rem;border-bottom:.5px solid var(--line);margin-bottom:1rem;gap:10px}}

.part-line{{display:flex;align-items:center;gap:10px;margin:2.2rem 0 1.1rem}}

.part-line span{{font-size:12px;font-weight:800;color:#fff;background:#23262b;padding:5px 14px;border-radius:99px;white-space:nowrap}}

.part-line::after{{content:'';flex:1;height:1.5px;background:#23262b}}

.q90{{background:linear-gradient(180deg,#1e2127,#282c34);border-radius:var(--rlg);padding:1.3rem 1.35rem 1.2rem;color:#e8e6e2}}

.q90-top{{display:flex;align-items:center;gap:8px;margin-bottom:.9rem;flex-wrap:wrap}}

.q90-badge{{font-size:11.5px;font-weight:800;color:#20242b;background:#e0c060;padding:3px 12px;border-radius:99px}}

.q90-sub{{font-size:12px;color:#9aa0a8}}

.q90-def{{font-size:21px;font-weight:800;color:#fff;line-height:1.45;letter-spacing:-.02em;margin-bottom:.5rem}}
.ix-head{{margin-bottom:1rem;padding-bottom:1rem;border-bottom:1px solid rgba(255,255,255,.1)}}
.ix-head .up{{color:#ff6b4a}} .ix-head .down{{color:#5b9bff}} .ix-head .yl{{color:#e0c060}}
.ix-mood{{display:flex;align-items:center;gap:12px;margin-bottom:14px}}
.ix-mood-emoji{{font-size:32px;line-height:1;flex-shrink:0}}
.ix-mood-txt{{flex:1}}
.ix-mood-t{{font-size:18px;font-weight:900;letter-spacing:-.02em;line-height:1.15;color:#f0efec}}
.ix-mood-s{{font-size:11px;color:#9aa0a8;margin-top:3px;line-height:1.4}}
.ix-bars{{background:rgba(255,255,255,.03);border-radius:12px;padding:.95rem .9rem .75rem}}
.ix-bar-row{{display:flex;align-items:center;gap:9px;margin-bottom:11px}}
.ix-bn{{width:48px;font-size:12px;font-weight:800;color:#dfe3e8;flex-shrink:0}}
.ix-bt{{flex:1;height:18px;background:rgba(255,255,255,.05);border-radius:5px;position:relative;overflow:hidden}}
.ix-bz{{position:absolute;left:50%;top:0;bottom:0;width:1px;background:rgba(255,255,255,.18)}}
.ix-bf{{position:absolute;top:0;bottom:0;border-radius:4px}}
.ix-bv{{width:100px;text-align:right;font-size:13.5px;font-weight:900;flex-shrink:0;line-height:1.05}}
.ix-bv small{{font-size:10px;color:#9aa0a8;font-weight:600;display:block;margin-top:5px;word-break:keep-all;line-height:1.4}}
.ix-scale{{display:flex;justify-content:space-between;font-size:8.5px;color:#6b7078;padding-left:57px;padding-right:109px}}
.ix-flow{{display:flex;justify-content:space-between;align-items:center;margin-top:11px;padding-top:10px;border-top:1px solid rgba(255,255,255,.08)}}
.ix-flow-k{{font-size:11px;color:#9aa0a8;font-weight:700}}
.ix-flow-v{{font-size:14.5px;font-weight:900}}
.ix-head .buy{{color:#4ade80}} .ix-head .sell{{color:#ff6b4a}} .ix-head .flat{{color:#8a909a}}
.ix-head .sellv{{color:#a78bfa}}
.ix-ring{{width:42px;height:42px;border-radius:50%;border:3px solid #ff6b4a;display:flex;align-items:center;justify-content:center;font-size:20px;font-weight:900;flex-shrink:0}}
.hi-ring{{width:42px;height:42px;border-radius:50%;border:3px solid #ff6b4a;display:flex;align-items:center;justify-content:center;font-size:20px;font-weight:900;flex-shrink:0}}
.hi-gauge{{width:46px;height:46px;position:relative;flex-shrink:0}}
.hi-gauge-c{{position:absolute;inset:0;display:flex;align-items:center;justify-content:center;font-size:14px}}
.hi-light{{display:flex;flex-direction:column;gap:5px;flex-shrink:0;padding:6px 5px;background:rgba(0,0,0,.25);border:1px solid rgba(255,255,255,.12);border-radius:10px}}
.hi-light .hi-dot{{width:12px;height:12px;border-radius:50%;border:1.5px solid rgba(255,255,255,.25)}}
.hi-light .hi-dot.on{{background:var(--gc);animation:hiblink 1.5s ease-in-out infinite}}
@keyframes hiblink{{0%,100%{{box-shadow:0 0 18px var(--gc),0 0 6px var(--gc);opacity:1;transform:scale(1.12)}}50%{{box-shadow:0 0 2px var(--gc);opacity:.32;transform:scale(1)}}}}
.hi-shield{{width:44px;height:44px;flex-shrink:0;display:flex;align-items:center;justify-content:center}}
.hi-arrow{{font-size:38px;font-weight:900;flex-shrink:0;line-height:1;width:44px;text-align:center}}
.hi-badge{{width:46px;height:46px;border-radius:11px;flex-shrink:0;display:flex;flex-direction:column;align-items:center;justify-content:center;color:#20242b}}
.hi-badge-n{{font-size:17px;font-weight:900;line-height:1}}
.hi-badge-s{{font-size:8px;font-weight:800;margin-top:1px}}
.hi-candle{{width:44px;height:44px;flex-shrink:0;display:flex;align-items:flex-end;justify-content:center;gap:3px}}
.hi-candle>div{{width:7px;border-radius:2px}}
.hi-bar{{width:5px;height:44px;border-radius:3px;flex-shrink:0}}
.hi-round{{width:46px;height:46px;border-radius:13px;border:1.5px solid;flex-shrink:0;display:flex;align-items:center;justify-content:center;font-size:22px}}
.ix-cum{{font-size:10.5px;color:#9aa0a8;margin-top:9px;padding-top:8px;border-top:1px dashed rgba(255,255,255,.1);line-height:1.5}}
.ix-cum b{{font-weight:800}}
.ix-cum .buy{{color:#4ade80}} .ix-cum .sellv{{color:#a78bfa}}
.ix-grouplbl{{font-size:9px;color:#7d838c;font-weight:700;letter-spacing:.04em;margin-bottom:6px;padding-left:2px}}
.ix-div{{height:1px;background:rgba(255,255,255,.08);margin:9px 0 8px}}
.ix-bv small{{font-size:9px}}
/* F 도넛 */
.f-wrap{{display:flex;gap:10px}}
.f-gauge{{flex:1;background:rgba(255,255,255,.04);border-radius:12px;padding:1rem .6rem;text-align:center}}
.f-ring{{width:88px;height:88px;margin:0 auto 6px;position:relative}}
.f-ring svg{{transform:rotate(-90deg)}}
.f-ring-txt{{position:absolute;inset:0;display:flex;justify-content:center;align-items:center}}
.f-pct{{font-size:17px;font-weight:900}}
.f-nm{{font-size:11px;color:#9aa0a8;font-weight:700}}
.f-close{{font-size:11px;color:#c3c8ce;font-weight:700;margin-top:2px}}
.f-mood{{text-align:center;margin-top:12px;padding-top:12px;border-top:1px solid rgba(255,255,255,.08);font-size:13px;font-weight:800}}
/* G 카드분할 */
.g-grid{{display:grid;grid-template-columns:1.4fr 1fr;grid-template-rows:auto auto;gap:8px}}
.g-main{{grid-row:span 2;background:linear-gradient(135deg,#2a1f1a,#3a2620);border-radius:12px;padding:1rem;display:flex;flex-direction:column;justify-content:center}}
.g-main .k{{font-size:11px;color:#ffb4a0;font-weight:700}}
.g-main .v{{font-size:29px;font-weight:900;line-height:1;margin:6px 0}}
.g-main .c{{font-size:15px;font-weight:900}}
.g-tag{{font-size:10px;color:#9aa0a8;margin-top:8px}}
.g-sub{{background:rgba(255,255,255,.04);border-radius:12px;padding:.75rem .85rem}}
.g-sub .k{{font-size:10px;color:#9aa0a8;font-weight:700}}
.g-sub .v{{font-size:16px;font-weight:900;margin-top:3px}}
.g-mood{{font-size:12px;color:#9aa0a8;margin-top:10px;line-height:1.5}}
/* H 타임라인 */
.h-item{{display:flex;gap:11px;padding-bottom:12px;position:relative}}
.h-item:not(:last-child)::before{{content:'';position:absolute;left:5px;top:16px;bottom:-2px;width:2px;background:rgba(255,255,255,.1)}}
.h-dot{{width:12px;height:12px;border-radius:50%;flex-shrink:0;margin-top:3px}}
.h-txt{{font-size:13px;line-height:1.5}}
.h-txt b{{font-weight:900}}
.h-sub{{font-size:11px;color:#9aa0a8;margin-top:2px}}
/* I 히트스트립 */
.i-head{{font-size:15px;font-weight:900;margin-bottom:12px;line-height:1.4}}
.i-head .hl{{background:linear-gradient(transparent 60%,rgba(255,107,74,.4) 60%);padding:0 2px}}
.i-strip{{display:flex;height:52px;border-radius:10px;overflow:hidden;gap:2px}}
.i-seg{{flex:1;display:flex;flex-direction:column;justify-content:center;align-items:center;color:#fff}}
.i-seg .k{{font-size:9.5px;opacity:.85;font-weight:700}}
.i-seg .v{{font-size:15px;font-weight:900;margin-top:2px}}
.i-seg .c{{font-size:10px;font-weight:700;opacity:.9}}
.ix-head .up{{color:#ff6b4a}} .ix-head .dn,.ix-head .down{{color:#5b9bff}} .ix-head .yl{{color:#e0c060}}

.q90-def .hi{{color:var(--up-soft)}}

.q90-feel{{font-size:13.5px;color:#e0c060;font-weight:700;line-height:1.6;padding-left:11px;border-left:2.5px solid #e0c060;margin-bottom:.75rem}}

.q90-why{{font-size:13.5px;color:#b9bfc7;line-height:1.75;padding-bottom:1rem;border-bottom:.5px solid rgba(255,255,255,.1)}}

.q90-why b{{color:#fff;font-weight:800}}

.q90-3{{padding:.9rem 0 .2rem}}

.q3{{display:flex;gap:10px;padding:8px 0;font-size:13.5px;line-height:1.75;color:#dfe3e8}}

.q3-n{{font-size:12px;font-weight:800;color:#20242b;background:#9aa0a8;width:20px;height:20px;border-radius:50%;display:flex;align-items:center;justify-content:center;flex-shrink:0;margin-top:3px}}

.q3 b{{color:#fff;font-weight:800}}

.q3 .u{{color:var(--up-soft);font-weight:800}}
.q3 .d{{color:var(--dn-soft);font-weight:800}}

.iss90{{background:rgba(255,255,255,.045);border-radius:var(--rmd);padding:.9rem 1rem;margin-top:.8rem}}

.iss90-h{{font-size:17px;font-weight:800;color:#e0c060;margin-bottom:.15rem}}

.iss90-s{{font-size:11px;color:#8a909a;margin-bottom:.7rem}}

.i9{{display:flex;align-items:flex-start;gap:9px;padding:7px 0;border-bottom:.5px solid rgba(255,255,255,.07);font-size:13px;line-height:1.7;color:#dfe3e8}}

.i9:last-child{{border-bottom:none;padding-bottom:0}}

.i9-t{{font-size:10.5px;font-weight:800;padding:2px 8px;border-radius:4px;white-space:nowrap;flex-shrink:0;margin-top:3px}}

.tg-semi{{background:rgba(120,180,255,.16);color:#9fc6f5}}

.tg-pol{{background:rgba(224,192,96,.16);color:#e0c060}}

.tg-glo{{background:rgba(200,150,255,.14);color:#c3a7ee}}

.tg-sup{{background:rgba(255,154,128,.16);color:var(--up-soft)}}

.i9 b{{color:#fff;font-weight:800}}

.i9 .u{{color:var(--up-soft);font-weight:800}}
.i9 .d{{color:var(--dn-soft);font-weight:800}}

.mny{{background:rgba(0,0,0,.25);border-radius:var(--rmd);padding:.95rem 1rem 1rem;margin-top:.8rem}}

.mny-h{{font-size:17px;font-weight:800;color:#e0c060;margin-bottom:.15rem}}

.mny-sub{{font-size:11px;color:#8a909a;margin-bottom:.8rem}}

.mny-tiles{{display:grid;grid-template-columns:repeat(3,1fr);gap:7px}}

.tile{{background:rgba(255,255,255,.05);border-radius:7px;padding:.62rem .55rem;text-align:center}}

.tile-k{{font-size:10.5px;color:#9aa0a8;font-weight:600;margin-bottom:3px}}

.tile-v{{font-size:17px;font-weight:800;line-height:1.15;font-variant-numeric:tabular-nums}}

.tile-v.b{{color:var(--up-soft)}}
.tile-v.s{{color:var(--dn-soft)}}

.tile-s{{font-size:10px;font-weight:700;margin-top:3px;color:#9aa0a8}}

.mny-feat{{margin-top:.9rem;display:flex;flex-direction:column;gap:8px}}

.mf{{display:flex;align-items:flex-start;gap:9px;font-size:12.5px;color:#c3c8ce;line-height:1.7}}

.mf-i{{font-size:11px;font-weight:800;color:#20242b;background:#e0c060;width:17px;height:17px;border-radius:4px;display:flex;align-items:center;justify-content:center;flex-shrink:0;margin-top:2px}}

.mf b{{color:#fff;font-weight:800}}

.mf .u{{color:var(--up-soft);font-weight:800}}
.mf .d{{color:var(--dn-soft);font-weight:800}}

.mny-why{{margin-top:.9rem;background:rgba(224,192,96,.1);border-radius:6px;padding:.75rem .85rem}}

.mw-h{{font-size:16.5px;font-weight:800;color:#e0c060;margin-bottom:.35rem}}

.mw-b{{font-size:13px;color:#fff;line-height:1.75;font-weight:600}}

.mw-b b{{color:#e0c060;font-weight:800}}

.mine{{background:rgba(143,180,238,.09);border:.5px solid rgba(143,180,238,.22);border-radius:var(--rmd);padding:.9rem 1rem;margin-top:.8rem}}

.mine-h{{font-size:17px;font-weight:800;color:var(--dn-soft);margin-bottom:.5rem}}

.mine-b{{font-size:13px;color:#dfe3e8;line-height:1.8}}

.mine-b b{{color:#fff;font-weight:800}}

.mine-split{{margin-top:.7rem;display:grid;grid-template-columns:1fr 1fr;gap:7px}}

.ms{{background:rgba(0,0,0,.2);border-radius:6px;padding:.6rem .7rem}}

.ms-k{{font-size:11px;font-weight:800;color:#e0c060;margin-bottom:3px}}

.ms-v{{font-size:12px;color:#c3c8ce;line-height:1.6}}

.mine-f{{font-size:11.5px;color:#8a909a;margin-top:.65rem;line-height:1.6}}


.q90-flip{{background:rgba(224,192,96,.07);border-left:3px solid #e0c060;padding:.9rem 1rem;margin-top:.8rem}}

.qf-h{{font-size:17px;font-weight:800;color:#e0c060;margin-bottom:.45rem}}

.qf-b{{font-size:13.5px;color:#dfe3e8;line-height:1.8}}

.qf-b b{{color:#fff;font-weight:800}}

.q90-tease{{margin-top:1rem;padding-top:.9rem;border-top:.5px solid rgba(255,255,255,.1)}}

.qt-h{{font-size:17px;font-weight:800;color:var(--up-soft);margin-bottom:.6rem}}

.qt{{display:flex;align-items:center;gap:10px;padding:10px 0;border-bottom:.5px solid rgba(255,255,255,.07);font-size:13.5px;color:#fff;line-height:1.6;font-weight:700}}

.qt:last-child{{border-bottom:none;padding-bottom:0}}

.qt-tag{{font-size:10px;font-weight:800;padding:3px 8px;border-radius:4px;white-space:nowrap;flex-shrink:0;background:rgba(255,255,255,.1);color:#c8ccd2}}

.qt-go{{margin-left:auto;font-size:11.5px;font-weight:800;color:#e0c060;white-space:nowrap;flex-shrink:0}}

.qt .u{{color:var(--up-soft)}}

.q90-stale{{font-size:11.5px;line-height:1.7;color:#8a6d3b;background:#fcf6e3;border:.5px solid #e6d7a8;border-radius:var(--rmd);padding:.7rem .85rem;margin-bottom:.8rem}}
.q90-gloss{{font-size:12px;color:#9aa0a8;line-height:1.7;margin:-.2rem 0 .6rem}}
.mine-f2{{font-size:13px;font-weight:800;color:#fff;margin-top:.5rem}}
.q90-cut{{text-align:center;font-size:12px;color:var(--sub);background:var(--bg2);border:.5px solid var(--line);border-radius:99px;padding:9px 0;margin:.6rem 0 0}}
.deep-cut{{display:flex;align-items:center;justify-content:center;gap:16px;margin:1.2rem 0 .2rem;padding:1rem 1rem;background:linear-gradient(180deg,#2a2e36,#20242b);border-radius:14px;border:1px solid rgba(224,192,96,.25)}}
.deep-arrow{{font-size:38px;font-weight:900;color:#e0c060;line-height:.6;animation:deepbob 1.4s ease-in-out infinite}}
@keyframes deepbob{{0%,100%{{transform:translateY(-2px)}}50%{{transform:translateY(3px)}}}}
.deep-txt{{text-align:center}}
.deep-t1{{font-size:12px;color:#9aa0a8;font-weight:700}}
.deep-t2{{font-size:14px;color:#e8e6e2;font-weight:800;margin-top:2px}}
.deep-t2 b{{color:#e0c060}}
.tmr{{margin-top:1rem;padding:.9rem 1rem;background:linear-gradient(180deg,#2b2f37,#242830);border-radius:12px;border-left:4px solid #e0c060}}
.tmr-h{{font-size:17px;font-weight:800;color:#e0c060;margin-bottom:6px}}
.tmr-b{{font-size:13px;color:#e8e6e2;line-height:1.7}}



















@media (max-width:600px){{
  body{{padding:8px 0}}
  .rp{{padding:1.1rem 1rem 1.5rem;border-radius:0;max-width:100%}}
  .deep-wrap{{margin-left:-1rem;margin-right:-1rem;padding-left:1rem;padding-right:1rem}}
  .top-bar{{flex-direction:column;gap:6px}}
  .q90{{padding:1.05rem .95rem}}
  .q90-def{{font-size:18.5px}}
  .mny-tiles{{grid-template-columns:1fr;gap:6px}}
  .tile{{display:flex;align-items:center;justify-content:space-between;text-align:left;padding:.55rem .7rem}}
  .tile-k{{margin-bottom:0}}.tile-v{{font-size:15px}}.tile-s{{margin-top:0}}
  .mine-split{{grid-template-columns:1fr}}
  .tower-dash{{padding:1rem .9rem}}
  .idx-grid{{grid-template-columns:1fr}}
  .bar-chart{{gap:3px}}.bar-zone{{height:112px}}.bar-val{{font-size:9px}}.bar-name{{font-size:9px}}
  .sector-grid{{grid-template-columns:1fr}}
  .sc-cols,.sc-row{{grid-template-columns:1.3fr 74px 58px 52px;font-size:12.5px}}
  .macro-row{{grid-template-columns:1fr}}
  table.tt{{font-size:11.5px}}
  table.tt th,table.tt td{{padding:7px 4px}}
}}
.tp-who{{grid-area:who}} .tp-val{{grid-area:val}} .tp-val.up{{color:var(--up)}} /* 핵심편 색 고정 — 시안 v5 값 강제 */
.q90 .u,.mny .u,.tile-v.b{{color:#ff9a80!important;font-weight:800}}
.q90 .d,.mny .d,.tile-v.s{{color:#8fb4ee!important;font-weight:800}}
.mf b,.i9 b,.mine-b b,.qf-b b{{color:#fff}}
.mw-b b{{color:#e0c060;font-weight:800}}
/* ══ 폰트 일괄 확대 (v-12-a) ══ */
.rp{{font-size:13.5px}}
.rp p{{line-height:1.75}}
.ic-num{{font-size:21px}}
.rd-foot,.fs-foot,.ac-note,.mf-sub-x{{font-size:11px}}
.iss-text,.news-insight,.mr-comment,.fs-read{{font-size:12.5px}}
.fs-ck-a{{font-size:12px}}
/* 수급 관제신호 */
.fs-box{{background:linear-gradient(180deg,#141e2b,#1c2a3a);border:.5px solid rgba(120,160,220,.14);border-radius:var(--rlg);padding:1.1rem 1.1rem .95rem;color:#e8e6e2;margin-bottom:1rem}}
.fs-verdict{{display:flex;align-items:center;gap:14px;padding-bottom:.95rem;border-bottom:.5px solid rgba(255,255,255,.1);flex-wrap:wrap}}
.fs-ico{{flex-shrink:0;width:50px;height:50px;border-radius:50%;display:flex;align-items:center;justify-content:center}}
.fs-ico.pos{{background:rgba(255,138,110,.13)}}
.fs-ico.neg{{background:rgba(127,168,232,.13)}}
.fs-main{{flex:1;min-width:200px}}
.fs-k{{font-size:10px;font-weight:700;color:#9aa0a8;letter-spacing:.05em}}
.fs-n{{color:#767c86;font-weight:600}}
.fs-row{{display:flex;align-items:baseline;gap:9px;flex-wrap:wrap}}
.fs-num{{font-size:30px;font-weight:800;line-height:1.1;font-variant-numeric:tabular-nums;letter-spacing:-.02em}}
.fs-num.pos{{color:var(--up-soft)}} .fs-num.neg{{color:var(--dn-soft)}}
.fs-state{{font-size:12.5px;font-weight:800}}
.fs-state.pos{{color:var(--up-soft)}} .fs-state.neg{{color:var(--dn-soft)}}
.fs-chips{{display:flex;gap:6px;flex-wrap:wrap;margin-top:6px}}
.fs-chip{{font-size:10.5px;font-weight:700;padding:3px 10px;border-radius:99px;border:.5px solid}}
.fs-chip.good{{background:rgba(255,138,110,.12);border-color:rgba(255,138,110,.3);color:var(--up-soft)}}
.fs-chip.warn{{background:rgba(224,192,96,.1);border-color:rgba(224,192,96,.32);color:#e0c060}}
.fs-chip.info{{background:rgba(255,255,255,.06);border-color:rgba(255,255,255,.14);color:#c8ccd2}}
.fs-checks{{padding:.85rem 0 .9rem;border-bottom:.5px solid rgba(255,255,255,.1)}}
.fs-checks-t{{font-size:10.5px;font-weight:700;color:#c8ccd2;letter-spacing:.04em;margin-bottom:.5rem}}
.fs-ck{{display:grid;grid-template-columns:30px 110px 1fr auto;gap:9px;align-items:center;padding:7px 0}}
.fs-ck-ico{{width:26px;height:26px;border-radius:50%;display:flex;align-items:center;justify-content:center;font-size:13px;font-weight:800}}
.fs-ck-ico.y{{background:rgba(255,138,110,.15);color:var(--up-soft)}}
.fs-ck-ico.n{{background:rgba(127,168,232,.15);color:var(--dn-soft)}}
.fs-ck-ico.h{{background:rgba(224,192,96,.13);color:#e0c060}}
.fs-ck-q{{font-size:11.5px;font-weight:800;color:#e8e6e2;line-height:1.4}}
.fs-ck-q small{{display:block;font-size:9px;font-weight:600;color:#767c86}}
.fs-ck-a{{font-size:11px;color:#a8aeb6;line-height:1.6}}
.fs-ck-a b{{color:#dfe3e8}}
.fs-ck-v{{font-size:12.5px;font-weight:800;font-variant-numeric:tabular-nums;white-space:nowrap;text-align:right}}
.fs-ck-v.pos{{color:var(--up-soft)}} .fs-ck-v.neg{{color:var(--dn-soft)}} .fs-ck-v.mid{{color:#e0c060}}
.fs-ck-v small{{display:block;font-size:8.5px;font-weight:700;color:#767c86;white-space:nowrap}}
.fs-combo{{font-size:11px;color:#c3c8ce;line-height:1.7;margin-top:.7rem;background:rgba(255,255,255,.04);border-radius:var(--rmd);padding:.5rem .75rem}}
.fs-combo b{{color:#fff}}
.fs-warn{{font-size:11px;color:#e8d9a8;line-height:1.7;margin-top:.5rem;background:rgba(224,192,96,.09);border:.5px solid rgba(224,192,96,.25);border-radius:var(--rmd);padding:.5rem .75rem}}
.fs-warn b{{color:#f0e2b8}}
/* 핵심편 수급 머리 — 심층편과 같은 계기 */
.core-g{{display:grid;grid-template-columns:auto minmax(0,1fr);gap:.7rem;align-items:center;margin:.5rem 0 .7rem;padding:.6rem .2rem;border-bottom:.5px solid rgba(255,255,255,.08)}}
.core-g-l{{text-align:center}}
.core-g-l svg{{max-width:96px}}
.core-g-x{{font-size:11px;font-weight:900;margin:.1rem 0 0}}
.core-g-v{{font-size:23px;font-weight:900;margin:0;letter-spacing:-.04em;font-variant-numeric:tabular-nums;line-height:1.1}}
.core-g-s{{font-size:10.5px;color:#8b93a0;margin:.2rem 0 0}}
.core-g-s b{{color:#c9d0d9}}
.core-g-k{{display:inline-block;font-size:10px;font-weight:800;padding:.15rem .5rem;border-radius:20px;border:1px solid #2a3342;background:#0d1118;margin:.35rem 0 0}}
/* 뜨는 현장 레이더 — 섹터 점이 천천히 명멸한다 */
/*   ⚠️ 빠르게 깜빡이면 요란하고 눈이 아프다. 3.2초 주기 ease-in-out으로
       숨 쉬듯 느리게, 투명도만 오간다(크기는 안 건드려 위치가 안 흔들린다).
       섹터마다 시작 시점을 어긋나게 해 한꺼번에 켜지지 않게 한다. */
@keyframes rdrpulse{{0%,100%{{opacity:1}}50%{{opacity:.42}}}}
.rdr-dot{{animation:rdrpulse 3.2s ease-in-out infinite}}
@media (prefers-reduced-motion:reduce){{.rdr-dot{{animation:none}}}}
/* ── 수급 관제신호 v5 ── */
.fs-v5{{display:grid;grid-template-columns:auto minmax(0,1fr);gap:.7rem;align-items:center;padding:0 0 .7rem;border-bottom:.5px solid rgba(255,255,255,.1)}}
.fs-v5-g{{text-align:center;flex:0 0 auto}}
.fs-v5 .fs-g{{max-width:118px}}
.fs-v5-gl{{font-size:12px;font-weight:900;margin:.15rem 0 0;letter-spacing:-.02em}}
.fs-v5-m{{min-width:0}}
.fs-v5-m .fs-k span{{font-weight:600;color:#78808c}}
.fs-v5-num{{font-size:25px;font-weight:900;margin:.1rem 0 0;letter-spacing:-.045em;font-variant-numeric:tabular-nums;line-height:1.1}}
.fs-v5-x{{font-size:11px;color:#8b93a0;margin:.25rem 0 0;line-height:1.5}}
.fs-v5-x b{{color:#c9d0d9}}
.fs-sub{{padding:.6rem 0;border-bottom:.5px solid rgba(255,255,255,.06)}}
.fs-sub-h{{display:grid;grid-template-columns:52px minmax(0,1fr) 74px;gap:.5rem;align-items:center}}
.fs-sub-n{{font-size:12.5px;font-weight:900;margin:0;letter-spacing:-.02em}}
.fs-sub-v{{font-size:13px;font-weight:900;margin:0;text-align:right;letter-spacing:-.03em;font-variant-numeric:tabular-nums}}
.fs-sub-x{{font-size:10px;color:#6f7784;margin:.35rem 0 0;line-height:1.6}}
.fs-sub-x b{{color:#9aa0aa}}
.fs-key{{display:inline-block;font-size:10px;font-weight:800;padding:.12rem .45rem;border-radius:20px;border:1px solid #2a3342;background:#0d1118;margin-right:.3rem}}
.fs-bandnote{{font-size:9.5px;color:#4a5462;margin:.55rem 0 .2rem;text-align:center}}
.fs-tl{{margin:.2rem 0 0}}
.fs-ptabs{{display:flex;gap:.3rem;margin:0 0 .55rem}}
.fs-ptab{{flex:1;text-align:center;font-size:11px;font-weight:800;padding:.35rem 0;border-radius:7px;background:#0d1118;border:1px solid #1e2531;color:#7d848f;cursor:pointer}}
.fs-ptab.on{{background:#1b2432;border-color:#3a465c;color:#fff}}
.fs-pbody{{display:none}}
.fs-pbody.on{{display:block}}
.fs-pend{{background:#0d1118;border:1px solid #1e2531;border-radius:10px;padding:1.3rem .9rem;text-align:center}}
.fs-pend-t{{margin:0;font-size:12px;color:#8b93a0;font-weight:700}}
.fs-pend-bar{{height:7px;background:#161c26;border-radius:4px;margin:.55rem 0 .35rem;overflow:hidden}}
.fs-pend-bar div{{height:100%;background:#e0c060}}
.fs-pend-s{{margin:0;font-size:10px;color:#6f7784}}
.fs-tnote{{margin:.3rem 0 0;font-size:10px;color:#e0c060;font-weight:700;text-align:center}}
.fs-lg{{display:flex;gap:.6rem;flex-wrap:wrap;justify-content:center;margin:.5rem 0 0}}
.fs-lg span{{font-size:9.5px;color:#7d848f;font-weight:700}}
.fs-lg i{{display:inline-block;width:14px;height:3px;border-radius:2px;vertical-align:middle;margin-right:.18rem}}
.fs-read{{background:#14100d;border:1px solid #3a2a20;border-radius:10px;padding:.65rem .75rem;margin:.7rem 0 0}}
.fs-read.stat{{background:#0d1118;border-color:#1e2531}}
.fs-read-t{{font-size:11.5px;font-weight:800;color:#c9d0d9;margin:0 0 .3rem}}
.fs-read-t span{{font-weight:600;color:#78808c}}
.fs-read-b{{font-size:11px;color:#c9d0d9;line-height:1.75;margin:0}}
.fs-read-b.dim{{color:#8b93a0}}
.fs-read-b b{{color:#fff}}
.fs-temp{{padding:.2rem 0 .75rem;border-bottom:.5px solid rgba(255,255,255,.1)}}
.fs-temp-t{{font-size:10.5px;font-weight:700;color:#c8ccd2;letter-spacing:.04em;margin-bottom:.45rem}}
.fs-temp-t span{{font-weight:600;color:#8a909a;letter-spacing:0}}
.ft-row{{display:grid;grid-template-columns:minmax(38px,48px) minmax(64px,92px) 1fr auto;gap:9px;align-items:baseline;padding:5px 0}}
.ft-who{{font-size:11.5px;font-weight:700;color:#9aa0a8}}
.ft-val{{font-size:14.5px;font-weight:800;font-variant-numeric:tabular-nums}}
.ft-val.b{{color:#ff9a80}} .ft-val.s{{color:#8fb4ee}}
.ft-avg{{font-size:10px;color:#7d838c;font-weight:600;white-space:nowrap}}
.ft-bad i{{font-style:normal;font-size:9.5px;font-weight:800;color:#d8dce2;background:rgba(255,255,255,.07);border:.5px solid rgba(255,255,255,.13);border-radius:99px;padding:2px 8px;display:inline-block;word-break:keep-all;line-height:1.45}}
.ft-bad{{min-width:0;text-align:right}}
.ft-note{{font-size:9.5px;color:#7d838c;line-height:1.6;margin-top:.45rem}}
.fs-cum{{padding-top:.95rem}}
.fs-splittitle{{margin:1.1rem -1.1rem .6rem;padding:.7rem 1.1rem;background:linear-gradient(90deg,rgba(224,192,96,.16),rgba(224,192,96,.04));color:#f0dfa8;font-size:13px;font-weight:800;letter-spacing:-.01em;border-top:1px solid rgba(224,192,96,.25);border-bottom:1px solid rgba(224,192,96,.25)}}
.fs-splittitle span{{color:#b0a880;font-weight:600;font-size:11px}}
.fs-cum-head{{display:flex;align-items:baseline;justify-content:flex-start;gap:8px;flex-wrap:wrap;margin-bottom:.4rem}}
.fs-cum-t{{font-size:10.5px;font-weight:700;color:#c8ccd2;letter-spacing:.04em}}
.fs-badges{{display:flex;gap:6px;flex-wrap:wrap}}
.fs-cb{{font-size:10px;font-weight:800;padding:3px 10px;border-radius:99px;font-variant-numeric:tabular-nums}}
.fs-cb.b5{{background:rgba(255,138,110,.14);color:var(--up-soft);border:.5px solid rgba(255,138,110,.3)}}
.fs-cb.b5n{{background:rgba(127,168,232,.14);color:var(--dn-soft);border:.5px solid rgba(127,168,232,.3)}}
.fs-cb.b20{{background:rgba(255,255,255,.06);color:#dfe3e8;border:.5px solid rgba(255,255,255,.14)}}
.fs-leg{{display:flex;gap:13px;flex-wrap:wrap;margin-top:5px}}
.fs-leg span{{font-size:9.5px;color:#8a909a;font-weight:600;display:flex;align-items:center;gap:5px}}
.fs-leg i{{width:15px;height:0;border-top-width:2.2px;display:inline-block}}
.fs-leg i.l-sp{{border-top-style:solid;border-color:#f0f0ee}}
.fs-leg i.l-fu{{border-top-style:dashed;border-color:#7fa8e8;opacity:.6}}
.fs-leg i.l-rf{{border-top-style:dashed;border-color:#e0c060;opacity:.8}}
.fs-x{{display:flex;justify-content:space-between;font-size:9px;color:#767c86;font-weight:600;margin-top:3px;padding:0 2px}}
.fs-read{{font-size:11.5px;color:#c3c8ce;line-height:1.75;margin-top:.65rem}}
.fs-read b{{color:#fff}}
.fs-building{{background:rgba(255,255,255,.04);border:.5px dashed rgba(255,255,255,.16);border-radius:var(--rmd);padding:1.1rem;text-align:center;font-size:11px;color:#9aa0a8;margin-top:.4rem}}
.fs-foot{{font-size:9.5px;color:#8a909a;line-height:1.7;margin-top:.8rem;border-top:.5px solid rgba(255,255,255,.08);padding-top:.6rem}}
.fs-pattern{{margin-top:.9rem;padding:.9rem 1rem;background:rgba(224,192,96,.06);border:1px solid rgba(224,192,96,.2);border-radius:10px}}
.fp-h{{font-size:15.5px;font-weight:800;color:#e0c060;margin-bottom:.6rem}}
.fs-chart-div{{height:1px;background:rgba(255,255,255,.1);margin:3px 0 5px}}
.fs-chart-t{{font-size:10.5px;font-weight:700;color:#c8ccd2;margin:2px 0 4px;letter-spacing:.02em}}
.dv-wrap{{margin-top:1rem;padding:1rem 1.05rem;background:linear-gradient(180deg,#24262e,#2c2f38);border-radius:12px;border:1px solid rgba(255,255,255,.08)}}
.dv-h{{font-size:16px;font-weight:800;color:#f0efec;margin-bottom:.7rem}}
.dv-row{{display:flex;gap:10px;padding:9px 0;border-bottom:.5px solid rgba(255,255,255,.07)}}
.dv-row:last-of-type{{border-bottom:0}}
.dv-ic{{flex-shrink:0;font-size:16px;width:24px;text-align:center;line-height:1.4}}
.dv-body{{flex:1}}
.dv-t{{font-size:12.5px;font-weight:800;color:#fff;margin-bottom:2px;word-break:keep-all}}
.dv-d{{font-size:11.5px;color:#c3c8ce;line-height:1.65;word-break:keep-all}}
.dv-d b{{color:#fff;font-weight:700}}
.dv-ctx{{font-size:11.5px;color:#aeb4bd;line-height:1.65;margin-top:5px;font-style:italic;word-break:keep-all}}
.dv-warn .dv-t{{color:#ffcf8a}} .dv-warn{{border-left:3px solid #e0a020;padding-left:8px;margin-left:-11px}}
.dv-good .dv-t{{color:#8ee6a8}} .dv-good{{border-left:3px solid #4ade80;padding-left:8px;margin-left:-11px}}
.dv-watch .dv-t{{color:#a8c8f0}} .dv-watch{{border-left:3px solid #5b9bff;padding-left:8px;margin-left:-11px}}
.dv-foot{{font-size:9.5px;color:#8a909a;line-height:1.6;margin-top:.6rem}}
.dv-fc{{font-size:11.5px;line-height:1.65;margin-top:6px;padding-left:10px;border-left:2px solid rgba(255,255,255,.12);color:#c3c8ce;word-break:keep-all}}
.dv-fc-k{{display:inline-block;font-size:9.5px;font-weight:800;color:#20242b;background:#c8ccd2;border-radius:4px;padding:1px 6px;margin-right:6px;vertical-align:1px}}
.dv-fc b{{color:#fff;font-weight:700}}
.dv-act{{border-left-color:rgba(224,192,96,.5)}}
.dv-act .dv-fc-k{{background:#e0c060}}
.q90-dv{{display:flex;align-items:center;gap:8px;margin-top:.7rem;padding:9px 11px;border-radius:9px;background:rgba(255,255,255,.05)}}
.q90-dv-ic{{font-size:15px;flex-shrink:0}}
.q90-dv-t{{font-size:12px;color:#dfe3e8;line-height:1.5;word-break:keep-all}}
.q90-dv-t b{{color:#fff}}
.q90-dv.dv-warn{{background:rgba(224,160,32,.12);border:1px solid rgba(224,160,32,.3)}}
.q90-dv.dv-good{{background:rgba(74,222,128,.1);border:1px solid rgba(74,222,128,.3)}}
.q90-dv.dv-watch{{background:rgba(91,155,255,.1);border:1px solid rgba(91,155,255,.3)}}
.fp-line{{font-size:12px;color:#dfe3e8;line-height:1.75;margin-bottom:.5rem}}
.fp-line b{{color:#fff;font-weight:800}}
.fp-turn{{color:#ff8a6e!important}}
.fp-detail{{margin:.5rem 0}}
.fp-sub{{display:flex;gap:9px;padding:7px 0;border-bottom:.5px solid rgba(255,255,255,.06)}}
.fp-sub:last-child{{border-bottom:0}}
.fp-who{{flex-shrink:0;width:48px;font-size:11.5px;font-weight:800;color:#e0c060}}
.fp-body{{flex:1;font-size:12px;color:#dfe3e8;line-height:1.7;word-break:keep-all}}
.fp-body b{{color:#fff;font-weight:800}}
.fp-hl{{color:#e0c060!important}}
.fp-hl.fp-turn{{color:#ff8a6e!important}}
.nw{{white-space:nowrap}}
.fp-acc{{color:#9aa0a8;font-weight:600}}
.fp-foot{{font-size:9.5px;color:#8a909a;line-height:1.6;margin-top:.5rem}}
.fs-foot b{{color:#b6bcc4}}
.mf-sub{{font-size:10.5px;font-weight:700;color:#c8ccd2;margin:.9rem 0 .45rem}}
.mf-bar{{display:flex;height:22px;border-radius:6px;overflow:hidden}}
.mf-seg{{display:flex;align-items:center;justify-content:center;font-size:10px;font-weight:800;color:#fff}}
.mf-kospi{{background:#4a6fa5}} .mf-kosdaq{{background:#b5652f}}
.mf-hint{{font-size:9.5px;color:#8a909a;margin-top:5px;line-height:1.5}}
.mf-flow-row{{display:flex;align-items:center;gap:8px;margin-bottom:6px}}
.mf-who{{font-size:11px;color:#c8ccd2;width:42px;flex-shrink:0}}
.mf-track{{flex:1;height:9px;background:rgba(255,255,255,.08);border-radius:5px;overflow:hidden}}
.mf-fill{{height:100%;border-radius:5px}}
.mf-fill.up{{background:linear-gradient(90deg,#ff8a6e,#C1432B)}}
.mf-fill.dn{{background:linear-gradient(90deg,#7fa8e8,#2E6BD6)}}
.mf-amt{{font-size:11px;font-weight:800;width:64px;text-align:right;flex-shrink:0}}
.mf-amt.up{{color:#ff8a6e}} .mf-amt.dn{{color:#7fa8e8}}
.mf-read{{font-size:12px;color:#dfe3e8;line-height:1.75;margin-top:.9rem;padding-top:.8rem;border-top:.5px solid rgba(255,255,255,.1)}}
.fx-wrap{{margin-top:.8rem}}
.fx-chart{{display:flex;flex-direction:column;gap:7px}}
.fx-row{{display:flex;align-items:center;gap:8px}}
.fx-lb{{font-size:11px;color:#c8ccd2;width:34px;flex-shrink:0;font-weight:600}}
.fx-zone{{flex:1;position:relative;height:16px;background:rgba(255,255,255,.06);border-radius:4px}}
.fx-zone::after{{content:'';position:absolute;left:50%;top:0;bottom:0;width:1px;background:rgba(255,255,255,.3)}}
.fx-bar{{position:absolute;top:2px;bottom:2px;border-radius:3px}}
.fx-bar.pos{{left:50%;background:linear-gradient(90deg,#ff8a6e,#C1432B)}}
.fx-bar.neg{{right:50%;background:linear-gradient(270deg,#7fa8e8,#2E6BD6)}}
.fx-lb2{{font-size:11px;color:#c8ccd2;width:44px;flex-shrink:0;font-weight:600}}
.fx-desc{{font-size:9.5px;color:#8a909a;margin:1px 0 6px 52px;line-height:1.5}}
.fx-amt{{font-size:11px;font-weight:800;width:66px;text-align:right;flex-shrink:0}}
.fx-amt.up{{color:#ff8a6e}} .fx-amt.dn{{color:#7fa8e8}} .fx-amt.smut{{color:#8a909a}}
.fx-na{{position:absolute;left:50%;top:50%;transform:translate(-50%,-50%);font-size:9.5px;color:#8a909a}}
.more-btn.dark{{background:rgba(255,255,255,.07);border-color:rgba(255,255,255,.14);color:#c8ccd2;margin-top:.6rem}}
.mf-badge{{display:inline-block;font-size:10.5px;font-weight:800;color:#ffd9c9;background:rgba(193,67,43,.3);padding:3px 11px;border-radius:99px;margin-bottom:.6rem}}
.mf-blk{{background:rgba(0,0,0,.22);border-radius:var(--rmd);padding:.7rem .85rem;margin-top:.65rem}}
.mf-blk-t{{font-size:10.5px;font-weight:800;color:#c8ccd2}}
.mf-blk-b{{font-size:12px;color:#dfe3e8;line-height:1.75;margin-top:5px}}
.mf-check{{font-size:12px;color:#ffd9c9;line-height:1.7;margin-top:.8rem;padding-top:.75rem;border-top:.5px solid rgba(255,255,255,.1)}}
.mf-na{{font-size:11px;color:#8a909a;line-height:1.6;margin:.7rem 0}}
.q-wrap{{margin-top:.8rem}}
.q-grid{{display:grid;grid-template-columns:1fr 1fr;gap:5px}}
.q-cell{{background:rgba(255,255,255,.05);border:.5px solid rgba(255,255,255,.1);border-radius:6px;padding:.55rem .4rem;text-align:center;display:flex;flex-direction:column;gap:2px}}
.q-cell.on{{background:rgba(193,67,43,.32);border-color:#ff8a6e}}
.q-t{{font-size:10px;color:#c8ccd2;font-weight:600}}
.q-cell.on .q-t{{color:#fff;font-weight:800}}
.q-nums{{display:flex;gap:14px;justify-content:center;margin-top:8px;font-size:11px;color:#c8ccd2}}
.q-nums .up{{color:#ff8a6e}} .q-nums .dn{{color:#7fa8e8}}
.mf-todo{{font-size:9.5px;color:#8a909a;margin-top:.6rem;line-height:1.5}}

/* ── 오늘의 한 문장 (필사 코너) ── */
.quote-box{{background:linear-gradient(135deg,#1c1f24,#2c3038);border-radius:var(--rlg);padding:1.6rem 1.4rem;color:#e8e6e2;margin-bottom:1rem;text-align:center;position:relative;overflow:hidden}}
.quote-mark{{font-size:52px;font-weight:800;color:rgba(127,168,232,.25);line-height:.5;height:24px}}
.quote-text{{font-size:16px;font-weight:700;color:#fff;line-height:1.75;letter-spacing:-.01em;margin:.4rem 0 .8rem;word-break:keep-all}}
.quote-sub{{font-size:11px;color:#9aa0a8}}

.foot{{font-size:10px;color:#b0aca6;line-height:1.6;border-top:.5px solid var(--line);padding-top:.8rem;margin-top:1.2rem}}

/* ── 모바일 ── */
@media (max-width:600px){{
  .fs-box{{padding:.95rem .8rem .85rem}}
  .fs-num{{font-size:25px}}
  .fs-ck{{grid-template-columns:26px 92px 1fr;gap:7px}}
  .fs-ck-v{{grid-column:2/4;text-align:left;margin-left:33px}}
  .fs-ck-q{{font-size:10.5px}}
  body{{padding:8px 0}}
  .rp{{padding:1.1rem 1rem 1.5rem;border-radius:0;max-width:100%}}
  .top-bar{{flex-direction:column;gap:6px}}
  .badge{{align-self:flex-start}}
  .rp-title{{font-size:16px}}
  .gz-num{{font-size:34px}}
  .gz-bodywrap{{min-width:100%}}
  .gz-row{{grid-template-columns:84px 38px 1fr;row-gap:2px}}
  .gz-ev{{grid-column:1/-1;color:#9aa0a8}}
  .idx-grid{{grid-template-columns:1fr;gap:8px}}
  .bar-chart{{gap:3px}} .bar-zone{{height:112px}} .bar-val{{font-size:8.5px}} .bar-name{{font-size:8.5px}}
  .sector-grid{{grid-template-columns:1fr}}
  .sc-cols,.sc-row{{grid-template-columns:1.3fr 76px 58px 60px;font-size:11.5px}}
  .macro-row{{grid-template-columns:1fr}}
}}
@media (max-width:380px){{
  .sc-cols,.sc-row{{grid-template-columns:1.2fr 62px 50px 52px;font-size:10.5px}}
  .bar-name{{font-size:8px}}
}}
/* 340px 이하 (iPhone SE 1세대 등 초소형) — 배지를 한 줄 아래로 내려 넘침을 없앤다 */
@media (max-width:340px){{
  .ft-row{{grid-template-columns:minmax(34px,44px) minmax(58px,80px) 1fr;gap:6px}}
  .ft-bad{{grid-column:1 / -1;text-align:left;margin-top:2px}}
  .ft-avg{{white-space:normal}}
}}
</style>
</head>
<body>
<div class="rp">
  <div class="top-bar">
    <p class="rp-title">🗼 차트프로 관제탑</p>
    <span class="badge">{날짜} 마감</span>
  </div>

  {휴장배너}
  {build_core(해석.get('핵심편'), data, 해석)}

  <div class="deep-wrap">
  {build_gauge(data.get('관제지수'), 오늘한줄평)}

  <p class="sec-label"><small>지수 + 수급</small>📊 오늘의 성적표</p>
  <div class="idx-grid">
    <div class="idx-card2">
      <p class="ic-mkt">KOSPI</p>
      <p class="ic-num">{코.get('종가','—')}</p>
      <p class="{idx_dir_class(코)}">{코.get('등락방향','—')} {코.get('등락률','—')}%</p>
      <div class="sup-grid">
        <div class="sup"><p class="sup-who">외국인</p><p class="sup-amt {money_class(코수.get('외국인'))}">{fmt_flow(코수.get('외국인'))}</p></div>
        <div class="sup"><p class="sup-who">기관</p><p class="sup-amt {money_class(코수.get('기관계'))}">{fmt_flow(코수.get('기관계'))}</p></div>
        <div class="sup"><p class="sup-who">개인</p><p class="sup-amt {money_class(코수.get('개인'))}">{fmt_flow(코수.get('개인'))}</p></div>
      </div>
    </div>
    <div class="idx-card2">
      <p class="ic-mkt">KOSDAQ</p>
      <p class="ic-num">{닥.get('종가','—')}</p>
      <p class="{idx_dir_class(닥)}">{닥.get('등락방향','—')} {닥.get('등락률','—')}%</p>
      <div class="sup-grid">
        <div class="sup"><p class="sup-who">외국인</p><p class="sup-amt {money_class(닥수.get('외국인'))}">{fmt_flow(닥수.get('외국인'))}</p></div>
        <div class="sup"><p class="sup-who">기관</p><p class="sup-amt {money_class(닥수.get('기관계'))}">{fmt_flow(닥수.get('기관계'))}</p></div>
        <div class="sup"><p class="sup-who">개인</p><p class="sup-amt {money_class(닥수.get('개인'))}">{fmt_flow(닥수.get('개인'))}</p></div>
      </div>
    </div>
  </div>

  <div class="today-market">💡 <b>오늘의 시장:</b> {오늘의시장}</div>

  <p class="sec-label"><small>핵심 이슈</small>🔬 이슈 해부 — 왜, 어디로, 무엇을 볼까</p>
  {build_issues(해석.get('핵심이슈'))}

  <p class="sec-label"><small>환율 · 유가 · 금리 · 금</small>🌏 바깥 날씨</p>
  <div class="macro-row">
    {build_macro_card((data.get('매크로') or {}).get('원달러환율'), (해석.get('매크로해설') or {}).get('환율',''))}
    {build_macro_card((data.get('매크로') or {}).get('WTI유가'), (해석.get('매크로해설') or {}).get('유가',''))}
    {build_macro_card((data.get('매크로') or {}).get('미국채10년'), (해석.get('매크로해설') or {}).get('금리',''))}
    {build_macro_card((data.get('매크로') or {}).get('국제금'), (해석.get('매크로해설') or {}).get('금',''))}
  </div>

  <p class="sec-label"><small>내 자리</small>📋 내 관심종목 등록 — 먼저 내 종목부터</p>
  {build_my_stocks(data)}

  <p class="sec-label"><small>오늘의 주인공</small>🏆 오늘의 주인공
    <span style="font-size:11px;font-weight:600;color:#8b93a0">· 상승률 + 거래대금 + 확산도 기준</span></p>
  {dev_note(f"전체 테마 중 등락률 상위 {(data.get('설정') or {}).get('주도섹터',{}).get('1차후보','?')}개를 1차 후보로 추림 → "
            f"{(data.get('설정') or {}).get('주도섹터',{}).get('가중치','?')} 점수로 재정렬 → "
            f"상위 {(data.get('설정') or {}).get('주도섹터',{}).get('선정수','?')}개. "
            f"단, 앞 카드와 종목이 {(data.get('설정') or {}).get('주도섹터',{}).get('중복제외기준','?')}개 이상 겹치면 제외")}
  {build_sectors(data.get('주도섹터'))}
  <details style="margin:12px 0 0;padding:9px 10px;background:#0f131a;border-radius:8px;
    border:1px solid #1e2531">
    <summary style="font-size:11.5px;color:#e0c060;font-weight:700;cursor:pointer;
      list-style:none">📖 오늘의 주인공과 섹터 성적표는 뭐가 다른가요?
      <span style="color:#6f7784;font-weight:600">(눌러서 펼치기)</span></summary>
    <p style="margin:6px 0 0;font-size:11px;color:#7d848f;line-height:1.65">
      <b style="color:#9aa0aa">오늘의 주인공</b>은 매일 바뀌는 <b>사건 현장</b>입니다.
      거래대금까지 보기 때문에 <b>돈이 몰린 곳</b>을 잡습니다.<br>
      <b style="color:#9aa0aa">섹터 성적표</b>는 안 바뀌는 <b>주소</b>입니다. 항상 같은 칸이라
      어제·지난달과 비교됩니다.<br>
      그래서 <b style="color:#9aa0aa">두 곳의 순위가 다를 수 있습니다.</b>
      성적표에선 강한데 여기 없다면 — <b style="color:#f0c65a">올랐지만 돈은 안 붙은 상승</b>입니다.
    </p></details>

  {_zone_trend_block}

  <p class="sec-label"><small>뜨는 현장</small>📡 관제 레이더 — 오늘 관제탑에 가까워진 섹터</p>
  {hide("관제레이더", build_sector_radar())}

  <p class="sec-label"><small>내 자리</small>📊 내 종목 구역 다시 보기</p>
  {build_account_grid(data.get('계좌격자'), data.get('주도섹터'))}

  <p class="sec-label"><small>섹터 성적</small>📈 섹터 성적표 다시 보기</p>
  {build_sector_scoreboard()}

  <p class="sec-label"><small>섹터 성적</small>📐 섹터 크기별 — 대형이 끌었나</p>
  {build_slope_chart(data.get('계좌격자'))}

  <p class="sec-label"><small>순환 분석</small>🗺️ 순위 섹터맵 — 주도권이 어떻게 돌았나</p>
  {build_sector_map()}

  <p class="sec-label"><small>순환 분석</small>🔮 돌아올 섹터 — 다음 순번은</p>
  {build_return_sector()}

  <p class="sec-label"><small>내 자리</small>📰 내 종목 브리핑 — 오늘 무슨 일이</p>
  {build_stock_brief()}

  <p class="sec-label"><small>프로의 시선</small>🔍 남들이 놓친 자리</p>
  {build_insight(프로의시선)}
  {build_divergence_block(data, 해석)}

  <p class="sec-label"><small>수급 관제신호</small>💰 큰돈은 어디로 갔나</p>
  {build_flow_signal(data.get('파생'), data.get('지수수급'))}

  <p class="sec-label"><small>시장 심리</small>🧭 군중 나침반</p>
  {build_crowd_compass(data.get('신용잔고'))}

  <p class="sec-label" id="radar"><small>실제 강세 레이더</small>🔥 오늘 불 붙은 곳</p>
  {build_radar(data.get('강세레이더'), data.get('설정'))}

  <p class="sec-label" id="acc"><small>매집 레이더</small>🐢 조용히 모으는 손</p>
  {build_accumulation(data.get('매집레이더'), data.get('설정'))}

  <p class="sec-label"><small>포착 종목 성적</small>🛬 레이더는 잘 잡았나</p>
  {build_capture_paths()}

  <p class="sec-label"><small>마감 브리핑</small>📺 그들은 뭐라 했나</p>
  {build_briefings(해석.get('마감브리핑'))}

  <p class="sec-label"><small>오늘의 중요 공시</small>📋 놓치면 아까운 공시</p>
  <div class="disc-box">
    {build_disclosures(data.get('공시'), 해석.get('공시해설'))}
    <p class="disc-note" style="margin-top:.6rem;font-size:9.5px">별점은 다음 거래일 변동 가능성 참고용이며 방향 예측이 아닙니다.</p>
  </div>

  <p class="sec-label"><small>이슈 밖 뉴스</small>🔥 {news_title(해석.get('핵심뉴스'))}</p>
  {build_news(해석.get('핵심뉴스'))}

  {f'<p class="sec-label"><small>어제의 채점표</small>✅ 어제 예고, 오늘 결과는</p>{build_scorecard(해석.get("채점표"))}' if 해석.get('채점표') else ''}

  {build_story_bridge()}

  <p class="sec-label" id="watch"><small>{_NEXT_LABEL}의 관전 포인트</small>🗼 {_NEXT_LABEL} 이것만 보세요</p>
  {(''.join(f'<div class="watch-item"><span>{pt}</span></div>' for pt in 해석.get('관전포인트'))) if 해석.get('관전포인트') else '<div class="pending">⏳ ①②③ 관전포인트 — Claude 해석 연동 후 자동 생성</div>'}

  <p class="sec-label"><small>오늘의 공부</small>📚 오늘 하나만 배운다면</p>
  {build_study(오늘의공부)}

  <!-- 오늘의 한 문장 (필사 코너) -->
  <p class="sec-label"><small>오늘의 한 문장</small>✍️ 오늘을 한 문장으로</p>
  <div class="quote-box">
    <div class="quote-mark">“</div>
    <p class="quote-text">{오늘의문장}</p>
    <p class="quote-sub">— 차트프로 관제탑, {날짜}</p>
  </div>

  </div><!-- /deep-wrap -->

  {build_archive()}

  <p class="foot">데이터: {날짜} 기준, 한국거래소·DART·네이버 증권 종합 · 관제지수는 등락률·수급·시장폭을 근거로 한 자체 참고 지표입니다 · 별점·예측은 참고용이며 매수·매도 신호가 아닙니다 · 본 브리핑은 정보 제공 목적으로, 투자 권유가 아니며 투자 판단과 책임은 투자자 본인에게 있습니다. <span style="opacity:.5">[{SCRIPT_VERSION}]</span></p>
</div>
<script>
function toggleMore(id,btn,label){{
  var el=document.getElementById(id);
  var open=el.classList.toggle('open');
  btn.textContent=open?'▴ 접기':label;
}}
function sortAcc(key,btn){{
  document.querySelectorAll('.sort-tab').forEach(function(t){{t.classList.remove('active')}});
  btn.classList.add('active');
  var attr = (key==='money') ? 'money' : 'ratio';
  document.querySelectorAll('[data-acclist]').forEach(function(list){{
    var rows = Array.prototype.slice.call(list.querySelectorAll('.ac-row'));
    rows.sort(function(a,b){{
      return (parseFloat(b.dataset[attr])||0) - (parseFloat(a.dataset[attr])||0);
    }});
    rows.forEach(function(r,i){{
      var n = r.querySelector('.rd-rank');
      if(n) n.textContent = i+1;
      list.appendChild(r);
    }});
  }});
}}
function toggleTV(id,el){{
  var body=document.getElementById(id);
  var open=body.classList.toggle('open');
  var see=el.querySelector('.tv-see-sm');
  if(see) see.textContent = open ? '접기 ▴' : '보기 ▾';
}}
</script>
</body>
</html>"""


if __name__ == "__main__":
    data = load_json(DATA_PATH)
    if data is None:
        print(f"❌ {DATA_PATH} 없음. collect_data.py 먼저 실행.")
        exit(1)
    report = load_json(REPORT_PATH)
    if report is None:
        print(f"⚠️ {REPORT_PATH} 없음 (해석글 미생성) — '오늘의 시장'은 안내문으로 채움.")
    html = build_html(data, report)
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"🎉 완료! → {OUT_PATH}  (build_html {SCRIPT_VERSION})")
