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

SCRIPT_VERSION = "v2026.08.30-a1"   # ⬅ 버전 표시
# 발행할 때마다 달라지는 값. 캐시된 페이지인지 아닌지를 눈으로 구분하는 표식이자,
# 아래 자동 새로고침 스크립트가 "내가 보고 있는 게 최신인가"를 판별하는 기준이다.
BUILD_STAMP = datetime.now().strftime("%Y%m%d%H%M%S")


# ── 조사(助詞) 자동 선택 (2026-08-26 신설) ──────────────
#  왜 필요한가: 금액 표기가 "조"(받침 없음)와 "억"(받침 있음)을 오가는데
#  뒤 조사를 고정해 두면 «+848억를 담았어요», «기관 +156억가 들어왔습니다»
#  같은 문장이 그대로 발행된다. 실제 8/25 리포트에서 발견된 오류다.
#  유료 리포트에서 문장 오류는 숫자 오류만큼 신뢰를 깎으므로 코드로 막는다.
#
#  ⚠️ HTML 태그가 붙은 채로 넘어오므로 태그를 걷어내고 마지막 글자를 본다.
def _josa(word, pair):
    """pair = '이가' / '을를' / '은는' / '와과'"""
    import re as _re
    t = _re.sub(r"<[^>]*>", "", str(word)).strip()
    if not t:
        return pair[1]
    ch, code = t[-1], ord(t[-1])
    if 0xAC00 <= code <= 0xD7A3:               # 한글 음절
        받침 = (code - 0xAC00) % 28
    elif ch.isdigit():                          # 숫자는 읽는 소리로 판정
        받침 = 1 if ch in "0136780" else 0      # 영·일·삼·육·칠·팔
    else:
        return pair[1]                          # 알 수 없으면 받침 없는 쪽
    return pair[0] if 받침 else pair[1]
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

DATE = "20260831"   # 미리보기 전용
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

# ── 📊 오늘의 성적표 — SCORE B (2026-08-18) ────────────────
#  왼쪽 칸: 지수 → 태그 → 한 줄 설명 (세로로 쌓아 빈 공간을 없앤다)
#  오른쪽 칸: 수급 가로 막대 (작게 — 주인공은 지수와 설명이다)
def _pct_signed(v):
    """등락률에 부호를 붙인다. '2.42' → '+2.42%'

    ⚠️ 예전에는 '상승/하락' 글자가 방향을 말해줬는데 그 글자를 뺐더니
       부호가 없어 방향을 알 수 없게 됐다(2026-08-20 지적).
    """
    try:
        f = float(str(v).replace(",", "").replace("%", ""))
    except (TypeError, ValueError):
        return f"{v}%" if v not in (None, "") else "—"
    return f"{f:+.2f}%"


def _sc_flowbar(수급, W=205, H=23):
    """0선 좌우 발산 막대 3줄. 왼쪽은 이름, 오른쪽은 금액 자리로 비워둔다.
    ⚠️ 비워두지 않으면 막대 끝과 금액 글자가 겹친다."""
    def _n(v):
        try:
            return float(str(v).replace(",", ""))
        except (TypeError, ValueError):
            return None
    항목 = [("외국인", _n(수급.get("외국인"))),
            ("기관", _n(수급.get("기관계"))),
            ("개인", _n(수급.get("개인")))]
    항목 = [(n, v) for n, v in 항목 if v is not None]
    if not 항목:
        return ""
    mx = max(abs(v) for _, v in 항목) or 1
    L, R = 34, 54
    z = L + (W - L - R) / 2
    half = (W - L - R) / 2 - 3
    g = []
    for i, (nm, v) in enumerate(항목):
        y = 3 + i * H
        c = FS_BUY if v >= 0 else FS_SELL
        w = abs(v) / mx * half
        x = z if v >= 0 else z - w
        g.append(f'<text x="0" y="{y+11:.0f}" font-size="10.5" fill="#8b93a0" font-weight="700">{nm}</text>')
        g.append(f'<rect x="{x:.0f}" y="{y+1:.0f}" width="{max(2,w):.0f}" height="15" rx="3" fill="{c}"/>')
        g.append(f'<line x1="{z:.0f}" y1="{y-1:.0f}" x2="{z:.0f}" y2="{y+15:.0f}" '
                 f'stroke="#fff" stroke-opacity=".3"/>')
        g.append(f'<text x="{W}" y="{y+12:.0f}" font-size="10.5" fill="{c}" text-anchor="end" '
                 f'font-weight="800">{_flow_amt(v)}</text>')
    return f'<svg viewBox="0 0 {W} {len(항목)*H+4}">{"".join(g)}</svg>'


def _sc_read(수급):
    """수급 세 주체를 보고 '누가 끌었나'를 한 줄로 판정한다 (규칙 기반).

    ⚠️ '오를 것이다/내릴 것이다'는 쓰지 않는다.
       말하는 것은 **오늘의 상승·하락을 누가 만들었나**뿐이다.
    """
    def _n(v):
        try:
            return float(str(v).replace(",", ""))
        except (TypeError, ValueError):
            return None
    외, 기, 개 = _n(수급.get("외국인")), _n(수급.get("기관계")), _n(수급.get("개인"))
    if 외 is None or 기 is None:
        return None, None, None
    실 = 외 + 기
    큰쪽 = "외국인" if abs(외) >= abs(기) else "기관"
    큰값 = 외 if abs(외) >= abs(기) else 기

    if 외 > 0 and 기 > 0:
        return "🔥 두 큰손이 함께 샀다", FS_BUY, (
            f"외국인 <b>{_flow_amt(외)}</b>·기관 <b>{_flow_amt(기)}</b>"
            f"{_josa(_flow_amt(기), '이가')} 같이 들어왔습니다.")
    if 외 < 0 and 기 < 0:
        return "🧊 두 큰손이 함께 팔았다", FS_SELL, (
            f"외국인 <b>{_flow_amt(외)}</b>·기관 <b>{_flow_amt(기)}</b>"
            f"{_josa(_flow_amt(기), '이가')} 같이 빠졌습니다."
            + (f" 개인만 <b>{_flow_amt(개)}</b> 받았습니다." if 개 is not None and 개 > 0 else ""))
    if 실 >= 0:
        약 = "기관" if 큰쪽 == "외국인" else "외국인"
        return f"🔥 {큰쪽}이 끌었다", FS_BUY, (
            f"{큰쪽} <b>{_flow_amt(큰값)}</b>"
            f"{_josa(_flow_amt(큰값), '이가')} {약} 매도를 덮었습니다.")
    return f"🧊 {큰쪽}이 밀었다", FS_SELL, (
        f"{큰쪽} <b>{_flow_amt(큰값)}</b>"
        f"{_josa(_flow_amt(큰값), '이가')} 빠져 나갔습니다."
        + (f" 개인이 <b>{_flow_amt(개)}</b> 받았습니다." if 개 is not None and 개 > 0 else ""))


def _mkt_key(이름):
    """카드 표시 이름(KOSPI/KOSDAQ) → 데이터 키(코스피/코스닥)."""
    t = str(이름 or "").strip().upper()
    if t in ("KOSPI", "코스피"):
        return "코스피"
    if t in ("KOSDAQ", "코스닥"):
        return "코스닥"
    return None


def _mkt_ammo_series(시장="코스피", days=5):
    """시장별(코스피/코스닥) 실탄(외국인+기관) 최근 N거래일 [(날짜, 값)].

    ⚠️ flow_history.json에는 코스피 실탄만 있다(코스닥 없음). archive의
       「지수수급.{시장}_수급」에서 외국인+기관계를 직접 더한다.
    """
    def _n(v):
        try:
            return float(str(v).replace(",", ""))
        except (TypeError, ValueError):
            return None
    키 = _mkt_key(시장)
    if not 키:
        return []
    out = []
    try:
        for 날짜, d in archive_days(days + 6):
            수급 = ((d.get("지수수급") or {}).get(f"{키}_수급") or {})
            외, 기 = _n(수급.get("외국인")), _n(수급.get("기관계"))
            if 외 is None or 기 is None:
                continue
            out.append((str(날짜), 외 + 기))
    except Exception:
        return []
    return out[-days:]


def _mkt_ammo_spark(시장="코스피", W=118, H=52):
    """성적표 카드용 실탄 5일 세로 막대 (작게)."""
    시리즈 = _mkt_ammo_series(시장, 5)
    if len(시리즈) < 2:
        return ""
    vals = [v for _, v in 시리즈]
    날 = [f"{d[4:6]}/{d[6:]}" for d, _ in 시리즈]
    mx = max(abs(v) for v in vals) or 1
    z = H * 0.40
    n = len(vals)
    간격 = (W - 8) / max(1, n)
    bw = max(5, 간격 - 3.5)
    g = [f'<line x1="3" y1="{z:.1f}" x2="{W-3}" y2="{z:.1f}" '
         f'stroke="#fff" stroke-opacity=".16"/>']
    for i, v in enumerate(vals):
        x = 4 + i * 간격
        y = z - (v / mx) * ((z - 2) if v >= 0 else (H - 11 - z))
        c = FS_BUY if v >= 0 else FS_SELL
        g.append(f'<rect x="{x:.1f}" y="{min(z,y):.1f}" width="{bw:.1f}" '
                 f'height="{max(1.5,abs(y-z)):.1f}" rx="2" fill="{c}" '
                 f'opacity="{1 if i==n-1 else .45}"/>')
        if i == n - 1:
            g.append(f'<text x="{x+bw/2:.0f}" y="{H-1.5:.0f}" font-size="7" '
                     f'fill="#c9d0d9" text-anchor="middle" font-weight="800">{날[i]}</text>')
    return (f'<div class="sc2-spark"><p class="sc2-spark-t">최근 {n}일 실탄</p>'
            f'<svg viewBox="0 0 {W} {H}">{"".join(g)}</svg></div>')


def _mkt_mini_gauge(시장="코스피"):
    """성적표 카드용 미니 계기판 — 심층편과 같은 계기를 더 작게."""
    시리즈 = _mkt_ammo_series(시장, FLOW_창 + 4)
    if len(시리즈) < 3:
        return ""
    st = _fs_stat([v for _, v in 시리즈])
    if not st:
        return ""
    c = FS_BUY if st["v"] >= 0 else FS_SELL
    ico, key = _fs_keyfact(st)
    return (f'<div class="sc2-g">'
            f'<div class="sc2-g-l">{_fs_gauge(st, 92)}</div>'
            f'<div class="sc2-g-r">'
            f'<p class="sc2-g-v" style="color:{c}">{_flow_amt(st["v"])}</p>'
            f'<p class="sc2-g-s">실탄 · {st["dir"]} <b>{st["rk"]}위</b>/{st["n"]}일</p>'
            f'<p class="sc2-g-k" style="border-color:{c}55;color:{c}">{ico} {key}</p>'
            f'</div></div>')


def build_score_card(이름, 지수, 수급):
    """지수 카드 한 장 (SCORE B 배치). [수급막대→실탄5일→미니계기판→멘트]."""
    태그, 색, 글 = _sc_read(수급 or {})
    설명 = ""
    if 태그:
        설명 = (f'<div class="sc2-tagbox"><span class="sc2-tag" style="border-color:{색}55;'
                f'color:{색}">{태그}</span><p class="sc2-txt">{글}</p></div>')
    _spark = _mkt_ammo_spark(이름)
    _gauge = _mkt_mini_gauge(이름)
    _아래 = ""
    if _spark or _gauge:
        _아래 = f'<div class="sc2-bot">{_gauge}{_spark}</div>'
    # ⚠️ 설명글은 **카드 전체 폭**을 쓴다(2026-08-19).
    #    왼쪽 좁은 칸에 넣으면 두세 줄로 접혀 읽기가 힘들다.
    return f'''<div class="idx-card2 sc2wrap">
      <div class="sc2">
        <div class="sc2-l">
          <p class="ic-mkt">{이름}</p>
          <p class="ic-num">{지수.get('종가','—')}</p>
          <p class="{idx_dir_class(지수)}">{_pct_signed(지수.get('등락률'))}</p>
        </div>
        <div class="sc2-r">{_sc_flowbar(수급 or {})}</div>
      </div>
      {_아래}
      {설명}
    </div>'''


def build_gauge(gauge, 오늘한줄평, 지수=None):
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

    # 🆕 2026-08-22 HO 지시 — 심층편 「오늘의 성적표」를 핵심편으로 옮기면서
    #    심층편 첫머리에 지수가 사라졌다. 관제지수 카드 **오른쪽 빈 공간**에
    #    코스피·코스닥의 지수와 등락률만 간략히 넣는다. (스타일 A)
    #    ⚠️ 여기는 '요약'이다 — 수급·태그·설명은 넣지 않는다. 그건 핵심편 성적표 몫.
    지수칸 = ""
    if 지수:
        줄들 = []
        for 라벨, 키 in (("코스피", "코스피"), ("코스닥", "코스닥")):
            d = (지수 or {}).get(키) or {}
            종가, 등락 = d.get("종가"), d.get("등락률")
            if 종가 is None and 등락 is None:
                continue
            try:
                _v = float(str(등락).replace(",", ""))
            except (TypeError, ValueError):
                _v = None
            색 = "#8b93a0" if _v is None else (IDX_UP if _v >= 0 else IDX_DN)
            등락문 = "—" if _v is None else f"{_v:+.2f}%"
            종가문 = "—" if 종가 is None else f"{float(str(종가).replace(',', '')):,.2f}"
            줄들.append(
                f'<div class="gz-idx-row"><span class="gz-idx-n">{라벨}</span>'
                f'<span class="gz-idx-v">{종가문}</span>'
                f'<span class="gz-idx-p" style="color:{색}">{등락문}</span></div>')
        if 줄들:
            지수칸 = f'<div class="gz-idx">{"".join(줄들)}</div>'

    return f'''
  <div class="gauge-box">
    <div class="gz-top">
      <div class="gz-numwrap"><p class="gz-num">{점수}</p><p class="gz-lab">{구간} {이모지}</p></div>
      {지수칸}
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
    <!-- 🔴 2026-08-29 HO 지시 — 심층편 시황 정리.
         [WHY] «오늘 몇 점»이라는 결론은 핵심편 신호등이 이미 색으로 말한다
         (조합태그 기반 같은 판정). 즉 위 게이지는 핵심편과 중복이다.
         그런데 이 카드에는 신호등에 **없는** 것이 하나 있다 — 요소별
         점수와 근거(가중합산 상세). 그게 심층편만의 정보인데, 정작
         «▾ 산정 기준 보기» 버튼 뒤에 접혀 있어 아무도 안 봤다.
         → 접힘을 풀어 **근거표를 주인공으로** 올린다. 결론(게이지)은
         위에 그대로 두되, 이제 이 카드의 무게중심은 «왜 그 점수인가»다. -->
    <div class="gz-detail" style="margin-top:8px">
      <p style="margin:0 0 6px;font-size:11.5px;color:#e0c060;font-weight:800">
        이 점수가 나온 근거</p>
      {기준표}
      <p class="gz-note">※ 각 요소를 0~100으로 환산해 가중 합산한 자체 참고 지표입니다. 거래대금(평소 대비)·극단 심리 지표는 데이터가 쌓이는 대로 추가됩니다.</p>
    </div>
  </div>'''


# ── 주도 섹터 6개 ────────────────────────────────────────
# 주도 섹터의 '최근 20일 강도' — 오늘 테마가 지난 한 달간 얼마나 자주 상위권에 있었나.
#   반짝 테마(오늘 처음)와 꾸준한 대장(며칠째 상위)을 구분해준다. 전부 규칙 기반.
_SECTOR_HIST_CACHE = None



# ══════════════════════════════════════════════════════
# 📅 archive 거래일 로더 — archive를 읽는 모든 코너의 단일 창구
# ══════════════════════════════════════════════════════
#  ⚠️ 이걸 안 쓰고 archive를 직접 훑으면 **휴장일 데이터가 섞인다.**
#     워크플로가 토·일·공휴일에도 돌면 직전 거래일과 똑같은 파일이 쌓이는데,
#     그대로 세면 "20일"이 20거래일이 아니게 되고 연속·평균·승패가 전부 부풀려진다.
#     (2026-08-18 flow_history, 08-20 섹터 성적표·주인공 배지에서 연속 발견)
#
#  거르는 기준 두 가지 — collect_data.prune_flow_history()와 같은 논리다.
#     ① 토·일   : 날짜만으로 확정 판정
#     ② 직전 채택일과 **핵심 값이 완전히 동일** : 공휴일·대체공휴일이 여기서 걸린다
_ARCHIVE_DAYS_CACHE = None


def _day_fingerprint(d):
    """그날 데이터의 지문. 두 파일이 같은 값이면 같은 날로 본다.

    ⚠️ 여기서 예외가 나면 **리포트 발행이 통째로 실패한다.**
       archive_days()가 모든 코너의 입구라, 이 함수 하나가 죽으면 전부 죽는다.
       그래서 어떤 값이 비어 있어도(None·리스트·문자열) 절대 터지지 않게 짠다.
       (2026-08-21 실제 사고 — '코스피_수급'이 None인 날에 .items()를 호출해
        AttributeError로 발행이 실패했다. `or {}` 는 키가 없을 때만 막아주고,
        **값이 None이면 못 막는다.**)
    """
    def _safe(v, default):
        return v if isinstance(v, type(default)) else default

    try:
        g = _safe((d.get("계좌격자") or {}).get("행"), [])
        격자 = tuple(sorted(
            (str(r.get("테마")), r.get("전체"))
            for r in g if isinstance(r, dict) and r.get("테마")))
    except Exception:
        격자 = ()
    try:
        주도 = tuple(str(s.get("테마명"))
                   for s in _safe(d.get("주도섹터"), [])
                   if isinstance(s, dict))
    except Exception:
        주도 = ()
    try:
        _k = _safe(d.get("지수수급"), {}).get("코스피_수급")
        수급 = tuple(sorted((str(a), str(b)) for a, b in _safe(_k, {}).items()))
    except Exception:
        수급 = ()
    return (격자, 주도, 수급)


def archive_days(days=None):
    """archive의 **거래일만** 오래된 순으로 [(날짜, data dict)] 반환.

    days를 주면 최근 days거래일만. (파일 개수가 아니라 거래일 개수다)
    한 번 읽으면 캐시한다 — 한 리포트를 만드는 동안 여러 코너가 재사용한다.
    """
    global _ARCHIVE_DAYS_CACHE
    if _ARCHIVE_DAYS_CACHE is None:
        out, 직전 = [], None
        for f in sorted(alist(r"data_\d{8}\.json")):
            try:
                with open(apath(f), encoding="utf-8") as fp:
                    d = json.load(fp)
            except Exception:
                continue
            ymd = str(d.get("날짜") or "")
            try:
                _d0 = datetime.strptime(ymd, "%Y%m%d")
                if _d0.weekday() >= 5:
                    continue                       # ① 토·일
                # ①-b 공휴일 — 이 파일에 이미 있는 KRX_HOLIDAYS를 그대로 쓴다.
                #     지문 비교만으로는 '금→토→일→월(공휴일)' 사슬에서
                #     중간에 데이터가 보정되면 공휴일이 거래일로 통과한다.
                #     (2026-08-17 대체공휴일이 실제로 통과했다)
                _tb = KRX_HOLIDAYS.get(_d0.year)
                if _tb and ymd in _tb:
                    continue
            except Exception:
                pass
            fp_ = _day_fingerprint(d)
            if 직전 is not None and fp_ == 직전:
                continue                           # ② 직전과 완전 동일 = 휴장일
            직전 = fp_
            out.append((ymd, d))
        _ARCHIVE_DAYS_CACHE = out
    return _ARCHIVE_DAYS_CACHE[-days:] if days else _ARCHIVE_DAYS_CACHE


def _sector_history(days=20):
    """archive/data_*.json에서 최근 days일의 [ (날짜, [테마명 순위대로]) ] 를 읽는다.
    한 번 읽으면 캐시(같은 리포트 빌드 중 여러 섹터가 재사용)."""
    global _SECTOR_HIST_CACHE
    if _SECTOR_HIST_CACHE is not None:
        return _SECTOR_HIST_CACHE
    # ⚠️ 예전에는 '최근 20개 파일'을 읽었다. 휴장일 파일이 섞이면
    #    8/14 하루가 4번 세어져 "20일 중 8일"의 분모·분자가 모두 부풀려진다.
    #    → archive_days()로 **거래일 20일**만 가져온다.
    hist = [[s.get("테마명") for s in (d.get("주도섹터") or [])]
            for _ymd, d in archive_days(days)]
    _SECTOR_HIST_CACHE = hist
    return hist


_THEME_ALL_CACHE = None


def _theme_all_history():
    """🆕 2026-08-29 — **전 기간** 테마 등판 이력 [(날짜, [테마명…])].

    ⚠️ 위 _sector_history()는 20거래일 창이라 "이번이 9번째 등판" 같은
       누적 사실을 말할 수 없다. 순환매를 보는 사람에게는 «몇 번째인지»와
       «며칠 만에 돌아왔는지»가 등락률만큼 중요해서, 전 기간을 따로 읽는다.
    """
    global _THEME_ALL_CACHE
    if _THEME_ALL_CACHE is not None:
        return _THEME_ALL_CACHE
    _THEME_ALL_CACHE = [(_ymd, [s.get("테마명") for s in (d.get("주도섹터") or [])])
                        for _ymd, d in archive_days()]
    return _THEME_ALL_CACHE


def theme_return_badge(테마명):
    """🆕 2026-08-29 HO 지시 — 「반짝이냐 눌러앉았냐」.

    [WHY] 31거래일 실측: 등장 테마 88개 중 48개(55%)가 **딱 한 번만** 등장했고,
    반복 등판은 14개뿐이었다. 즉 "오늘 처음 뜬 테마"와 "계속 뜨는 테마"는
    성격이 완전히 다른데, 화면에서 구분이 안 됐다.
    매매하는 사람에게 이 구분은 등락률만큼 중요하다 — 그래서 등락률 옆에 붙인다.

    ⚠️ 통계가 아니라 **사실**만 말한다. "평균 주기 12일"은 표본이 찰 때까지
       (theme_history.json이 쌓인 뒤) 말하지 않는다. 지금은 셀 수 있는 것만:
       몇 번째 등판인지, 직전 등판이 며칠 전인지.
    """
    if not 테마명:
        return ""
    hist = _theme_all_history()          # 오래된 순
    나온날 = [ymd for ymd, names in hist if 테마명 in names]
    if not 나온날:
        return ""
    총등판 = len(나온날)
    if 총등판 <= 1:
        return ('<span class="sc-str new">🆕 첫 등판 · '
                f'기록 {len(hist)}일 중 처음</span>')
    # 직전 등판이 몇 거래일 전이었나 — 오늘(마지막)과 그 앞 등판 사이 거래일 수
    _날짜순 = [ymd for ymd, _ in hist]
    try:
        _간격 = _날짜순.index(나온날[-1]) - _날짜순.index(나온날[-2])
    except ValueError:
        _간격 = None
    _꼬리 = ""
    if _간격 == 1:
        _꼬리 = " · <b>어제 이어 오늘도</b>"
    elif _간격:
        _꼬리 = f" · <b>{_간격}거래일 만에</b> 복귀"
    return (f'<span class="sc-str">🔁 <b>{총등판}번째</b> 등판{_꼬리}</span>')


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
        return ('<span class="sc-str new">🆕 신규 테마 · '
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
            f'{N}일 중 <b>{등장}일</b> 주인공 · 평균 <b>{평균:.1f}위</b></span>')


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
    # 🆕 2026-08-29 — 「반짝이냐 눌러앉았냐」. 위 강도배지는 20일 창이라
    #    "이번이 9번째"를 못 말한다. 전 기간 등판 사실을 따로 붙인다.
    등판배지 = theme_return_badge(a.get('테마명'))
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
        {f'<p class="sc-strline">{등판배지}</p>' if 등판배지 else ''}
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
    # 🔴 2026-08-29 HO 지시 — 조건부 표시로 바꾼다.
    #    [WHY] 예전엔 내용이 없어도 "⏳ …해석 연동 후 자동 생성" 같은
    #    안내문이 자리를 차지했다. 이 코너의 값어치는 «남들이 못 본 것»인데,
    #    빈 껍데기가 매일 뜨면 "놓친 자리"가 아니라 그냥 «아무 말»이 된다.
    #    → 없으면 **코너 자체를 통째로 생략**한다(원칙 14 — 없으면 없다고
    #    짧게 끝낸다. 여기선 아예 말을 안 하는 게 가장 짧다).
    #    ⚠️ 운영자는 로그로 안다 — 화면에 «미생성» 안내를 띄울 이유가 없다.
    if not 프로의시선:
        return ""
    # 🆕 2026-08-22 — 프롬프트는 과거→현재→미래 1막/2막/3막으로 쓰라고 하는데
    #    화면엔 그 구조가 안 보여서, 글이 흔들려도 독자도 개발자도 못 알아챘다.
    #    라벨을 화면에도 노출해 구조를 눈으로 검증할 수 있게 한다.
    렌즈들 = [
        ("1막 · 과거", "조용한 강세", 프로의시선.get("조용한_강세", "")),
        ("2막 · 현재", "짖지 않은 개", 프로의시선.get("짖지_않은_개", "")),
        ("3막 · 미래", "다음 시나리오", 프로의시선.get("다음_시나리오", "")),
    ]
    rows = []
    for 막, 이름, 내용 in 렌즈들:
        if not 내용:
            continue
        rows.append(f'''
    <div class="si-item"><span class="si-lens"><b class="si-act">{막}</b>{이름}</span><span>{내용}</span></div>''')
    if not rows:
        return ""     # 🔴 2026-08-29 — 위와 같은 이유로 안내문 대신 생략
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
        # 🆕 2026-08-22 — "상승 종목만"으로 뭉뚱그려져 있어 핵심 조건인
        #    상승률 하한이 안 보였다(코스피 4% / 코스닥 5%).
        f"<b>전일 종가 대비 코스피 {(설정.get('최소상승') or {}).get('코스피', 4)}%↑ / "
        f"코스닥 {(설정.get('최소상승') or {}).get('코스닥', 5)}%↑</b> · "
        f"전일 대비 거래량 ≥ {설정.get('거래량배수','?')}배 │ "
        f"점수 = 회전율×{설정.get('회전비중','?')} + 상승률×{설정.get('상승비중','?')} "
        f"(각각 0~100 정규화) + 거래량 {설정.get('가점배수','?')}배↑ 시 +{설정.get('가점','?')}점 │ "
        f"추적 {설정.get('추적일','?')}거래일"
    ) if 설정 else ""
    # 🆕 2026-08-26 HO 지시 — 조건 설명 **바로 밑**에 두 기법이 뭔지 쉽게 쓴다.
    #  ⚠️ 구체적 수치(몇 배·몇 %)는 쓰지 않는다. 위 dev_note가 이미 다 말했고,
    #     여기는 "그래서 이게 무슨 종목인가"만 답하는 자리다.
    안내 = (
        '<div class="rd-guide">'
        '<p class="rd-guide-h">🎯 이 종목들이 왜 여기 떴냐면요</p>'
        '<p class="rd-guide-b">'
        '<b style="color:#f0c65a">💰 돈이 몰림</b> — 평소보다 훨씬 많은 돈과 거래가 '
        '한꺼번에 몰리면서 <b>높은 가격대에서 끝난</b> 종목이에요. '
        '살 사람이 끝까지 붙어 있었다는 뜻이에요.<br>'
        '<b style="color:#74f0d4">📈 V자 반등</b> — 장중에 크게 밀렸다가 '
        '<b>되돌려 올라온</b> 종목이에요. 떨어질 때 받아준 손이 있었다는 뜻이에요.'
        '</p>'
        '<p class="rd-guide-n">두 기법은 재는 기준이 서로 달라서 '
        '<b>한 종목이 둘 다</b> 걸리기도 해요. 추천이 아니라 '
        '<b>이 조건에 걸렸다</b>는 기록이에요.</p></div>')
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
            # 🆕 2026-08-22 — 어떤 기법으로 잡혔는지 배지로 표시.
            _배지명 = {"돈이 몰린 종목": "💰 돈이 몰림", "V자 반등 종목": "📈 V자 반등"}
            _색 = {"돈이 몰린 종목": "#f0c65a", "V자 반등 종목": "#74f0d4"}
            _유들 = s.get("유형들") or ([s["유형"]] if s.get("유형") else [])
            # 🆕 2026-08-26 HO 지시 — 배경을 빼고 **같은 색 테두리만 두껍게**.
            #    [WHY] 채운 배지가 종목명보다 먼저 눈에 들어와 시선을 뺏었다.
            #          선으로 바꾸면 윤곽은 남고 무게만 준다.
            유형HTML = "".join(
                f'<span class="rd-tag" style="background:none;'
                f'border:1px solid {_색.get(t,"#8b93a0")}66;'
                f'color:{_색.get(t,"#8b93a0")};font-weight:700">{_배지명.get(t, t)}</span>'
                for t in _유들)
            # ⚠️ V자 반등은 **전일 종가 대비로는 하락일 수 있다.**
            #    예전처럼 '+' 를 강제로 붙이면 "+-2.00%"가 되어 깨진다.
            _cls = "up" if 등락 >= 0 else "dn"
            # 시가 대비 장중 궤적 — V자 반등에서만 의미가 있다
            _저, _종 = s.get("시가대비저점"), s.get("시가대비종가")
            _궤적 = (f" · 시가 대비 <b>{_저:+.1f}% → {_종:+.1f}%</b>"
                    if (_저 is not None and _종 is not None
                        and "V자 반등 종목" in _유들) else "")
            # 🆕 2026-08-25 — 심층편 강세 레이더에도 기업분석을 붙인다.
            # 🆕 2026-08-26 HO 지시 — 이름 옆에도 등락률을 적는다.
            #  ⚠️ 오른쪽 «rd-chg»는 그대로 둔다 — 점수와 나란한 «성적 칸»이라
            #     역할이 다르다. 이름 옆은 «지금 몇 %인가»를 바로 읽는 자리다.
            _끼움 = (f'<span style="font-size:12.5px;font-weight:800;'
                   f'color:{"#c1432b" if 등락 >= 0 else "#2e6bd6"};'
                   f'margin:0 4px 0 6px">{등락:+.2f}%</span>')
            _이름, _칸 = sc_click(s['종목명'], None, 13, _끼움)
            # 🆕 2026-08-25 HO 지시 — 「돈이 몰림」·「V자 반등」이 둘 다 뜨면
            #    **한 줄에 같이** 나와야 한다.
            #    ⚠️ 원인: 이름+배지를 한 <p>에 다 넣고 flex-wrap만 걸었더니,
            #       폭이 되는 대로 끊겨서 배지 하나는 이름 줄에 붙고
            #       나머지는 다음 줄로 따로 밀렸다(줄바꿈이 배지 '그룹'을 안 지켰다).
            #    [고침] 이름 줄과 배지 줄을 **아예 분리한 두 개의 <p>**로 만든다.
            #       그러면 배지들은 항상 자기들끼리 한 줄(모자라면 자기들끼리만 줄바꿈)이라
            #       이름과 섞여 끊기는 일이 없다.
            _배지줄 = f'<p class="rd-badges">{유형HTML}{재HTML}{폭발}</p>' \
                if (유형HTML or 재HTML or 폭발) else ""
            return f"""
      <div class="rd-row">
        <span class="rd-rank">{rank}</span>
        <div class="rd-info">
          <p class="rd-name">{_이름}</p>
          {_배지줄}
          <p class="rd-meta">회전율 {s.get('회전율','—')}% · 거래량 전일 <b>{s.get('배수','—')}배</b>
            · 거래대금 {_fmt_eok(s.get('거래대금'))} · 시총 {_fmt_eok(s.get('시총'))}{_궤적}</p>
          {_칸}
        </div>
        <div class="rd-nums">
          <span class="rd-score">{s.get('강세점수','—')}</span>
          <span class="rd-chg {_cls}">{등락:+.2f}%</span>
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
    <p class="rd-lead">🔥 <b>서로 다른 두 기법</b>으로 잡습니다. 조건도 재는 기준도 완전히 다릅니다.</p>
    {조건}
    {안내}
    {신규HTML}
    <p class="rd-foot">🔄 N차 포착 = 추적 중이던 종목의 재점화 ·
      한 종목이 <b>두 기법에 동시에</b> 걸리면 배지가 둘 다 붙습니다.<br>
      ⚠️ 포착은 추천이 아닙니다. 두 기법의 성적을 5·20·60·120일로 추적해
      어느 쪽이 유효한지 공개할 예정입니다.</p>
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


_AC_SEQ = [0]


# ══════════════════════════════════════════════════════════════
# 🔁 매집 이력 — 차수 · 연속 등판 (2026-08-24 신설, HO 지시)
# ══════════════════════════════════════════════════════════════
#  HO 질문: "각 종목마다 최근 60일 안에 이런 매집이 있었는지 체크해서
#            1차 매집 / 2차 매집 라벨을 붙이면 분별이 되지 않을까?"
#  → 가능하다. 새 수집이 필요 없다. archive/data_*.json에 날짜별 매집 목록이
#    그대로 있어서, 종목별로 '언제 잡혔는지'를 되짚기만 하면 된다.
#
#  ⚠️ 왜 유용한가 — 같은 "매집 포착"도 성격이 전혀 다르다.
#     · 1차 = 처음 잡힌 자리. 신선하지만 검증 안 됨.
#     · 2차 이상 = 쉬었다가 다시 모으는 자리. 앞선 매집이 소화된 뒤라
#       "한 번 더 확신을 가진 손"이라는 뜻이 된다.
#     이걸 안 나누면 둘이 같은 줄에 섞여서 판단 재료가 안 된다.
#
#  ⚠️ 구간을 어떻게 끊나 — 하루 이틀 빠졌다고 새 매집이 아니다.
#     ACC_차수_공백 거래일 이상 안 잡히면 그때 '다음 차수'로 센다.
ACC_이력_창 = 60        # 며칠을 되돌아볼지(거래일)
ACC_차수_공백 = 5       # 이만큼 연속으로 안 잡히면 별개 매집으로 본다
_ACC_HIST_CACHE = {}


def _accum_history():
    """{종목명: [등장한 날짜(오래된순)]} — 최근 ACC_이력_창 거래일 기준."""
    if _ACC_HIST_CACHE:
        return _ACC_HIST_CACHE
    이력 = {}
    try:
        for 날, d in archive_days(ACC_이력_창):
            a = d.get("매집레이더")
            if not isinstance(a, dict):
                continue
            본 = set()
            for k in ("종목", "중기종목", "장기종목"):
                for x in (a.get(k) or []):
                    if isinstance(x, dict) and x.get("종목명"):
                        본.add(x["종목명"])
            for nm in 본:
                이력.setdefault(nm, []).append(str(날))
    except Exception as e:
        print(f"   ⚠️ 매집 이력 계산 실패 — {type(e).__name__} (배지 없이 진행)")
        return {}
    for nm in 이력:
        이력[nm] = sorted(set(이력[nm]))
    _ACC_HIST_CACHE.update(이력)
    return 이력


def accum_badge(종목명):
    """차수 + 연속 등판 배지 HTML. 재료가 없으면 빈 문자열."""
    이력 = _accum_history()
    날들 = 이력.get(종목명) or []
    if not 날들:
        return ""
    try:
        축 = [str(날) for 날, _ in archive_days(ACC_이력_창)]
    except Exception:
        return ""
    축 = sorted(set(축))
    위치 = {d: i for i, d in enumerate(축)}
    idx = sorted(위치[d] for d in 날들 if d in 위치)
    if not idx:
        return ""
    # ── 구간 나누기 ──
    구간 = [[idx[0]]]
    for a, b in zip(idx, idx[1:]):
        (구간.append([b]) if b - a > ACC_차수_공백 else 구간[-1].append(b))
    차수 = len(구간)
    연속 = 1
    끝 = 구간[-1]
    for a, b in zip(끝, 끝[1:]):
        연속 = 연속 + 1 if b - a == 1 else 1
    # 🆕 2026-08-24 (2차) — HO 질문 "22일 기준은 뭐야?"
    #  ⚠️ 그건 **되돌아본 거래일 수**였다(기록이 22일치뿐이라 22로 찍혔다).
    #     설명이 없어 독자는 알 길이 없었다. "최근 22일 안에서"로 바꾼다.
    #     60일이 다 차면 굳이 밝힐 필요가 없으므로 그때는 숨긴다.
    배지 = ""
    if 차수 >= 2:
        배지 += (f'<span class="ab ab2">{차수}차 매집</span>')
    else:
        배지 += (f'<span class="ab ab1">1차 매집</span>')
    if 연속 >= 2:
        배지 += f'<span class="ab abc">{연속}일 연속</span>'
    elif len(idx) == 1:
        배지 += '<span class="ab abn">오늘 처음</span>'
    if len(축) < ACC_이력_창:
        # 🆕 2026-08-25 HO 질문 — 기간 탭(5·20)을 눌러도 이 글자가 안 바뀐다.
        #  ⚠️ 이 배지는 **탭과 무관하다.** 탭은 '며칠간의 매집을 볼까'이고,
        #     이 배지는 '과거에도 잡힌 적 있나(차수)'다. 축이 다르다.
        #     말 자체를 바꿔 오해를 없앤다.
        배지 += f'<span class="ab abd">차수 판정 {len(축)}일치</span>'
    return 배지


NEWS_LOOKBACK = 10      # 🆕 종목 카드 뉴스를 며칠치까지 뒤질지(거래일)
BRIEF_NEWS_DAYS = 20    # 🆕 2026-08-29 HO 지시 — 5 → 20. 대신 최근 위주 정렬 +
                        #    종목별 중복(같은 사건 반복 보도) 제거를 같이 넣는다
                        #    (안 그러면 기간만 늘어난 만큼 옛날 기사·중복이 쌓여
                        #    더 정신없어진다).
# 🆕 2026-08-26 — 기업분석 카드의 「요즘 왜 주목받냐면요」는 **기간을 안 자른다.**
#  [WHY] HO 지시 — "10거래일만 보지 말고, 이 종목이 최근에 왜 올랐는지
#        이슈가 된 기사를 찾아라". 사흘 전 계약 공시가 오늘 주가를 만든다.
#  ⚠️ archive가 쌓인 만큼만 뒤진다. 지금은 2주치지만 매일 자동으로 길어진다.
#     상한을 크게 잡아도 없는 날은 그냥 건너뛰므로 비용이 늘지 않는다.
NEWS_ARCHIVE_ALL = 250  # 사실상 전 기간(1년치)
#  ⚠️ 카드(10일)와 브리핑(5일)이 다른 이유 —
#     카드는 "왜 매집이 들어왔나"를 찾는 자리라 길게 본다.
#     브리핑은 "지금 내 종목 상황"이라 **최근 것**이어야 한다.
#     오늘 하루만 보면 "재료 없음"이 대부분이라 5일이 균형점이다.


def _news_key(제목):
    """같은 사건을 다룬 기사를 하나로 묶기 위한 지문.

    ⚠️ 여러 매체가 같은 사안을 쓰면 제목이 «[특징주] 한전기술, 원전 기대에 20%↑»
       «한전기술 원전 기대감에 20% 급등» 처럼 미세하게 다르다. 글자만 비교하면
       중복이 그대로 남는다. 대괄호 머리말·기호·공백을 걷어내고 앞부분만 본다.
    """
    import re as _re
    s = _re.sub(r"\[[^\]]*\]", "", str(제목 or ""))       # [특징주] 같은 머리말
    s = _re.sub(r"[^0-9A-Za-z가-힣]", "", s)              # 기호·공백 제거
    return s[:24]                                        # 앞 24글자로 동일 사건 판정
_SC_SEQ = [0]


def sc_click(nm, 색=None, 크기=15, 끼움=""):
    """종목명을 '누르면 기업분석이 펼쳐지는' 형태로 만든다.

    🆕 2026-08-25 — id를 함수가 만들어 **이름표와 펼침칸이 어긋나지 않게** 한다.
       (각자 만들면 한쪽만 바뀌었을 때 조용히 안 열린다)
    반환: (이름HTML, 펼침칸HTML) — 펼침칸은 같은 카드 **맨 아래**에 넣는다.
    """
    _SC_SEQ[0] += 1
    sid = f"sc{_SC_SEQ[0]}"
    안전 = str(nm).replace("'", "")
    # 🆕 2026-08-25 (2차) — 색을 **강제하지 않는다.**
    #  🔴 사고: 심층편 레이더 카드는 **밝은 배경**(--ink #1a1a1a)인데
    #     내가 흰색을 박아 넣어 글자가 배경에 묻혔다. 핵심편은 어두운 배경이라
    #     같은 코드가 거기서는 잘 보여서 "심층편만 안 보인다"가 됐다.
    #  ⚠️ 원칙: 배경이 밝은지 어두운지는 **그 자리가 안다.** 카드는 물려받는다.
    _색 = f"color:{색};" if 색 else ""
    # 🆕 2026-08-26 HO 지시 — 이름 바로 뒤, «▾기업분석» 앞에 등락률을 끼운다.
    #    [WHY] 독자가 가장 먼저 찾는 숫자가 등락률인데 «기업분석» 배지에 밀려
    #          한 칸 뒤로 가 있었다. 순서: 종목명 → 등락률 → 기업분석.
    이름 = (f'<b style="font-size:{크기}px;{_색}" class="cp-sname" '
           f"onclick=\"scToggle('{안전}','{sid}')\">{nm}"
           f'{끼움}'
           f'<span class="sc-tap"><i>▾</i>기업분석</span></b>')
    칸 = f'<div id="{sid}" style="display:none"></div>'
    return 이름, 칸


def build_accumulation(매집, 설정=None):
    if not 매집:
        return '<div class="pending">⏳ 매집 레이더 — 데이터 수집 준비중</div>'
    종목 = 매집.get("종목") or []
    if not 종목:
        return '<div class="pending">오늘은 조건을 만족한 매집 종목이 없습니다.</div>'
    _AC_SEQ[0] += 1
    _AC_GID = f"ac{_AC_SEQ[0]}"   # 같은 표를 두 번 렌더해도 탭이 안 엉키게
    기간 = 매집.get("기간", 5)
    쌍최소 = 매집.get("쌍끌이최소", 3)
    단최소 = 매집.get("단독최소", 4)
    쌍수 = 매집.get("쌍끌이수", 0)

    cfg = (설정 or {}).get("매집", {})
    스캔 = cfg.get("스캔범위") or {}
    조건 = dev_note(
        f"스캔 = 시총 상위 코스피 {스캔.get('코스피','?')} + 코스닥 {스캔.get('코스닥','?')}종목 · "
        # ⚠️ 2026-08-22 수정 — 여기 "코스피 4%↑ / 코스닥 5%↑"가 적혀 있었는데
        #    그건 **강세 레이더(불난 자리)의 조건**이다. 매집 레이더는 상승률 필터가
        #    아예 없다(조용히 담기는 자리를 찾는 게 목적이라 오히려 반대다).
        #    설명이 틀리면 독자가 코너 성격을 정반대로 이해한다.
        f"<b>상승률 조건 없음</b>(조용히 담기는 자리를 찾는 코너라 오르지 않아도 됩니다) · "
        f"ETF·ETN·스팩·우선주 제외 · "
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

    def 행(i, s, 값HTML, 부가="", 일수=None):
        # 🆕 2026-08-25 — 심층편 매집 행에서도 종목명을 눌러 기업분석을 편다.
        # 🆕 2026-08-26 HO 지시 — 이름 옆에 등락률.
        #  ⚠️ 매집 레이더에는 «오늘 등락»이 없다. 저장된 건 그 매집이 일어난
        #     기간(5·20·60일) 동안의 등락률뿐이다.
        #  🔴 2026-08-26 (2차) — 처음엔 «기간»이라고만 적었는데 HO가 "이게 뭐냐"고
        #     물었다. 설명이 필요한 라벨은 실패한 라벨이다.
        #     → **실제 일수(«20일»)를 그대로 적는다.** 탭 이름과 같아 바로 읽힌다.
        _기등 = s.get("기간등락률")
        if _기등 is None:
            _기등 = s.get("5일등락률")
        _끼움 = ""
        if isinstance(_기등, (int, float)):
            _라벨 = f"{일수}일" if 일수 else "기간"
            _끼움 = (f'<span style="font-size:9.5px;color:#8b93a0;'
                   f'margin:0 2px 0 6px">{_라벨}</span>'
                   f'<span style="font-size:12px;font-weight:800;'
                   f'color:{"#c1432b" if _기등 >= 0 else "#2e6bd6"};'
                   f'margin-right:4px">{_기등:+.2f}%</span>')
        _이름, _칸 = sc_click(s['종목명'], None, 13, _끼움)
        return f"""
        <div class="ac-row">
          <span class="ac-rank">{i}</span>
          <div class="ac-info">
            <p class="ac-name">{_이름}{유형뱃지(s.get('유형',''))}</p>
            <p class="ac-meta">외 {s.get('외인일수',0)}일 · 기 {s.get('기관일수',0)}일
              · 시총 {_fmt_eok(s.get('시총'))}{부가}</p>
            <p class="ac-badge">{accum_badge(s.get('종목명'))}</p>
            {_칸}
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
              f' · 누적 +{_fmt_eok(s.get("합산"))}', 일수=기간)
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
                  + ('<span class="ac-star2">⭐ 5일 랭킹에도 동시 등재</span>' if s["종목명"] in 별명단 else ""),
                  일수=중기간)
                for i, s in enumerate(목록, 1))
        중기블록 = f'''
      <p class="ac-long-s">5일이 <b>"이번 주 신호"</b>라면, {중기간}일은 <b>"한 달째 이어지는 의지"</b>입니다.
        하루 이틀 산 게 아니라 <b>한 달 내내 같은 방향</b>이었다는 뜻이라, 단기보다 되돌림이 적습니다.<br>
        🤝쌍끌이 = 둘 다 {매집.get("중기쌍끌이",12)}일↑ · 💼단독 = 한쪽 {매집.get("중기단독",14)}일↑ ·
        <b>⭐ = 5일 랭킹에도 동시 등재</b>(가장 강한 신호)</p>
      <div class="ac-two">
        <div class="ac-col"><p class="ac-col-t">📊 코스피 · {중기간}일 매집</p>{중기랭킹("코스피")}</div>
        <div class="ac-col"><p class="ac-col-t">📊 코스닥 · {중기간}일 매집</p>{중기랭킹("코스닥")}</div>
      </div>'''

    # ── 🆕 2026-08-22 장기(60일) 매집 — 20일과 같은 규칙, 기간만 확장 ──
    #    ⚠️ 데이터가 없으면 블록이 비고, 아래 탭도 자동으로 꺼진다(off).
    장기 = 매집.get("장기종목") or []
    장기블록 = ""
    if 장기:
        장기간 = 매집.get("장기기간", 60)
        def 장기랭킹(시장):
            목록 = [x for x in 장기 if x.get("시장") == 시장]
            목록 = sorted(목록, key=lambda x: x.get("시총대비") or 0, reverse=True)[:5]
            if not 목록:
                return f'<p class="rd-empty">{시장} — 조건 만족 종목 없음</p>'
            return "".join(
                행(i, s, f'<span class="ac-val">{s.get("시총대비","—")}%</span>',
                  f' · 누적 +{_fmt_eok(s.get("합산"))}', 일수=장기간)
                for i, s in enumerate(목록, 1))
        장기블록 = f'''
      <p class="ac-long-s">{장기간}일은 <b>"분기 내내 이어진 방향"</b>입니다.
        세 달을 같은 쪽으로 담았다면 단기 이벤트가 아니라 <b>구조적인 판단</b>일 가능성이 큽니다.<br>
        🤝쌍끌이 = 둘 다 {매집.get("장기쌍끌이",36)}일↑ · 💼단독 = 한쪽 {매집.get("장기단독",42)}일↑ ·
        정렬은 <b>매집강도</b>(많이 담겼는데 덜 오른 순)</p>
      <div class="ac-two">
        <div class="ac-col"><p class="ac-col-t">📊 코스피 · {장기간}일 매집</p>{장기랭킹("코스피")}</div>
        <div class="ac-col"><p class="ac-col-t">📊 코스닥 · {장기간}일 매집</p>{장기랭킹("코스닥")}</div>
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
    <div class="ac-tabs" data-g="{_AC_GID}">
      <!-- 🆕 2026-08-22 HO 지시 — 탭 이름을 "N일 매집"으로 통일 + 60일 추가 -->
      <div class="ac-tab on" data-g="{_AC_GID}" data-p="s">🔥 {기간}일 매집</div>
      <div class="ac-tab{"" if 중기블록 else " off"}" data-g="{_AC_GID}" data-p="l">🏗️ {매집.get("중기기간",20)}일 매집</div>
      <div class="ac-tab{"" if 장기블록 else " off"}" data-g="{_AC_GID}" data-p="x">🗿 {매집.get("장기기간",60)}일 매집</div>
    </div>
    <div class="ac-body on" data-g="{_AC_GID}" data-p="s">
      <p class="ac-long-s">{기간}일은 <b>"이번 주에 막 들어온 돈"</b>입니다.
        아직 짧아 되돌릴 수도 있지만, <b>가장 빠른 신호</b>이기도 합니다.<br>
        🤝쌍끌이 = 둘 다 {쌍최소}일↑ · 💼단독 = 한쪽 {단최소}일↑</p>
      <div class="ac-two">
        <div class="ac-col">
          <p class="ac-col-t">📊 코스피 · {기간}일 매집</p>
          <p class="ac-col-s">그 회사엔 얼마나 큰 돈인가</p>
          {코스피행}
        </div>
        <div class="ac-col">
          <p class="ac-col-t">📊 코스닥 · {기간}일 매집</p>
          <p class="ac-col-s">그 회사엔 얼마나 큰 돈인가</p>
          {코스닥행}
        </div>
      </div>
      {보충}
    </div>
    <div class="ac-body" data-g="{_AC_GID}" data-p="l">
      {중기블록 or '<p class="rd-empty">20일 매집은 이력이 더 쌓이면 열립니다.</p>'}
    </div>
    <div class="ac-body" data-g="{_AC_GID}" data-p="x">
      {장기블록 or '<p class="rd-empty">60일 매집은 이력이 더 쌓이면 열립니다.</p>'}
    </div>
    <script>(function(){{
      var root=document.currentScript.parentNode;
      root.addEventListener('click',function(e){{
        var t=e.target.closest('.ac-tab'); if(!t||t.classList.contains('off')) return;
        var g=t.getAttribute('data-g'), p=t.getAttribute('data-p');
        root.querySelectorAll('.ac-tab[data-g="'+g+'"]').forEach(function(c){{c.classList.remove('on');}});
        t.classList.add('on');
        root.querySelectorAll('.ac-body[data-g="'+g+'"]').forEach(function(b){{
          b.classList.toggle('on', b.getAttribute('data-p')===p);
        }});
      }});
    }})();</script>
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


# ── 🔭 다음 거래일 예보 (구 관전포인트) ──
WATCH_COLORS = {
    "수급":   ("#85B7EB", "#0c447c"),
    "섹터":   ("#F0997B", "#4A1B0C"),
    "이벤트": ("#97C459", "#173404"),
}


def build_watchpoints(포인트들, 라벨=""):
    """다음 거래일 예보 — 기준선 + 어느 쪽인지 + 반증 조건.

    🆕 2026-08-22 전면 개편. 예전엔 "①외국인 수급을 지켜보세요" 같은
       문자열 배열을 그대로 찍었다. 그건 채점이 안 되고, 언제 써도 안 틀리고,
       매일 소재가 같았다. **틀릴 수 없는 예고는 맞춰도 가치가 없다.**
       → 영역(수급/섹터/이벤트) · 기준선(숫자) · 예보(어느 쪽) · 반증(틀렸다면)
         네 가지를 갖춘 카드로 바꾼다.
    ⚠️ 구버전 호환: 항목이 문자열이면 예전 형식이므로 그대로 한 줄로 보여준다
       (과거 archive를 다시 빌드해도 안 깨지게).
    """
    if not 포인트들:
        return ('<div class="pending">⏳ 다음 거래일 예보 — '
                'Claude 해석 연동 후 자동 생성</div>')
    카드 = []
    for pt in 포인트들:
        if isinstance(pt, str):
            카드.append(f'<div class="watch-item"><span>{pt}</span></div>')
            continue
        if not isinstance(pt, dict):
            continue
        영역 = str(pt.get("영역") or "").strip()
        배경, 글자 = WATCH_COLORS.get(영역, ("#B4B2A9", "#2C2C2A"))
        기준선 = str(pt.get("기준선") or "").strip()
        예보 = str(pt.get("예보") or "").strip()
        반증 = str(pt.get("반증") or "").strip()
        if not 예보:
            continue
        머리 = ""
        if 영역:
            머리 += (f'<span style="font-size:9.5px;font-weight:800;color:{글자};'
                    f'background:{배경};border-radius:4px;padding:2px 6px">{영역}</span>')
        if 기준선:
            머리 += f'<span style="font-size:11px;color:#8b93a0">기준선 {기준선}</span>'
        반증줄 = ""
        if 반증:
            반증줄 = (f'<p style="margin:0;font-size:11px;color:#7d848f;line-height:1.55">'
                    f'✗ {반증}</p>')
        카드.append(
            f'<div style="background:#0f131a;border-radius:8px;padding:10px 11px;'
            f'margin-bottom:8px">'
            f'<div style="display:flex;gap:6px;align-items:center;margin-bottom:5px">'
            f'{머리}</div>'
            f'<p style="margin:0 0 5px;font-size:12.5px;color:#e8eaee;line-height:1.65">'
            f'{예보}</p>{반증줄}</div>')
    if not 카드:
        return ('<div class="pending">⏳ 다음 거래일 예보 — 데이터 부족</div>')
    _제목 = f"{라벨}, 저는 이렇게 봅니다" if 라벨 else "다음 거래일, 저는 이렇게 봅니다"
    return (f'<div style="background:#141922;border:1px solid #232a36;border-radius:12px;'
            f'padding:13px 14px;margin:10px 0 0">'
            f'<p style="margin:0 0 2px;font-size:11.5px;color:#8b93a0">다음 거래일 예보</p>'
            f'<p style="margin:0 0 3px;font-size:17px;font-weight:800;color:#f2f4f7">'
            f'{_제목}</p>'
            f'<p style="margin:0 0 11px;font-size:10.5px;color:#e0c060">'
            f'다음 거래일에 ○×로 채점해 그대로 공개합니다</p>'
            f'{"".join(카드)}</div>')


# ── 어제의 채점표 ──
def build_scorecard(채점표, 어제날짜=""):
    if not 채점표:
        return ""  # 첫 발행이면 아예 섹션을 숨긴다
    rows = []
    for it in 채점표:
        결과 = it.get("결과", "×")
        # 🆕 2026-08-22 — △(부분 충족) 폐지. ○/× 둘 중 하나이고,
        #    데이터를 못 구해 판정 자체가 불가능한 것만 '측정불가'로 회색 처리한다.
        측정불가 = str(결과).replace(" ", "") in ("측정불가", "-", "—", "")
        기호 = "○" if 결과 == "○" else ("✕" if not 측정불가 else "—")
        cls = "sc-o" if 결과 == "○" else ("sc-t" if 측정불가 else "sc-x")
        rows.append(f'''
    <div class="score-row">
      <span class="score-mark {cls}">{기호}</span>
      <div class="score-body">
        <p class="score-item">{it.get('항목','')}</p>
        <p class="score-why">{it.get('근거','')}</p>
      </div>
    </div>''')
    유효 = [it for it in 채점표
            if str(it.get("결과", "")).replace(" ", "") not in ("측정불가", "-", "—", "")]
    맞은수 = sum(1 for it in 유효 if it.get("결과") == "○")
    틀린수 = len(유효) - 맞은수
    누적 = rs_watch_tally(맞은수, 틀린수)
    return f'''
  <div class="score-box">
    <p class="score-head">📋 어제 예보, {맞은수}승 {틀린수}패였습니다
      <span class="score-tally">{맞은수} / {len(유효)} 적중</span></p>
    {"".join(rows)}
    <p class="score-foot">{누적}※ 예보 → 채점 → 새 예보. 매일 이어집니다.
      <b style="color:#c9ced6">틀린 것도 지우지 않고 그대로 둡니다.</b></p>
  </div>'''


WATCH_TALLY_FILE = "watch_tally.json"


def rs_watch_tally(오늘맞음, 오늘틀림):
    """예보 누적 성적을 파일에 쌓고 한 줄로 돌려준다.

    🆕 2026-08-22 — "틀린 걸 지우지 않는다"를 숫자로 증명하는 자리.
    ⚠️ 같은 날짜를 두 번 세지 않도록 날짜를 키로 저장한다(재발행·재빌드 대비).
    ⚠️ daily.yml의 git add 목록에 watch_tally.json이 없으면 매일 초기화된다.
    """
    try:
        기록 = {}
        if os.path.exists(WATCH_TALLY_FILE):
            with open(WATCH_TALLY_FILE, encoding="utf-8") as f:
                기록 = json.load(f) or {}
        기록[str(DATE)] = {"맞음": 오늘맞음, "틀림": 오늘틀림}
        with open(WATCH_TALLY_FILE, "w", encoding="utf-8") as f:
            json.dump(기록, f, ensure_ascii=False, indent=1)
        누맞 = sum(v.get("맞음", 0) for v in 기록.values())
        누틀 = sum(v.get("틀림", 0) for v in 기록.values())
        총 = 누맞 + 누틀
        if 총 < 3:
            return (f'<b style="color:#c9ced6">누적 {누맞}승 {누틀}패</b> — '
                    f'적중률은 표본이 더 쌓이면 공개합니다<br>')
        return (f'<b style="color:#c9ced6">누적 {누맞}승 {누틀}패 · '
                f'적중률 {누맞/총*100:.0f}%</b><br>')
    except Exception as e:
        print(f"   ⚠️ 예보 누적 집계 실패 — {type(e).__name__}")
        return ""



def _hdr_flow_badge(key):
    """헤더 수급 막대 밑 배지 — 그 주체의 '오늘 성격' 한 줄.

    ⚠️ 예전에는 _flow_highlight()를 썼는데 외국인·기관이 같은 문구로 나오고
       매도인 날에 "매수 전환"이라 적히는 버그가 있었다(2026-08-19).
       _fs_stat()은 **방향별 순위**를 쓰므로 매도인 날은 매도 기준으로 센다.

    돌려주는 예: "20일 중 매도 2위 · 9일 만의 최대"
    """
    try:
        h = load_json("flow_history.json") or []
        arr = [r.get(key) for r in h if isinstance(r, dict) and r.get(key) is not None]
    except Exception:
        return "&nbsp;"
    st = _fs_stat(arr)
    if not st:
        return "&nbsp;"
    # ⚠️ 이 자리는 폭이 100px밖에 안 된다. 길면 두 줄로 접힌다(2026-08-19 지적).
    #    "20일 중 매수 6위"까지만 넣고 나머지는 **둘째 줄에 따로** 준다.
    #    (한 줄에 억지로 두 정보를 넣으면 반드시 접힌다)
    앞 = f'{st["n"]}일 중 {st["dir"]} {st["rk"]}위'
    뒤 = ""
    if st["back"] >= 3:
        뒤 = f'{st["back"]}일 만의 최대'
    elif st["연속"] >= 3:
        뒤 = f'{st["연속"]}일 연속 {st["dir"]}'
    elif st["배수"] >= 1.5:
        뒤 = f'평소 {_배수말(st["배수"])}'
    return (f'<span class="bdg1">{앞}</span>'
            + (f'<span class="bdg2">{뒤}</span>' if 뒤 else ""))


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



def _header_data(지수수급, 파생, 코수, 사건명=None):
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
        # ⚠️ "함께 오른 하루"는 매일 똑같아 아무 정보가 없다(2026-08-19 지적).
        #    오늘의 사건명(예: "6852 환호, 실탄은 마이너스")을 그대로 쓴다.
        #    사건명은 Claude가 매일 새로 짓는 제목이라 자동으로 매번 달라진다.
        _ev = (사건명 or "").strip().strip("〈〉<> ").strip()
        이름 = _ev or ("함께 오른 하루" if 코등 > 0 else
                       "함께 내린 하루" if 코등 < 0 else "숨 고른 하루")
        이모 = ("🔴" if 코등 > 0 else "🔵" if 코등 < 0 else "⚪")
        성격부제 = "코스피·코스닥 지수 흐름 요약"

    # 수급 특징 — 최대 20일 범위에서 '가장 눈에 띄는 신호' 자동 선택(코드 계산).
    #   flow_history의 외현/기관을 읽어, 전환/최대/연속/순위 중 강한 것 하나를 문장으로.
    외배지 = _hdr_flow_badge("외현") if 외 is not None else "&nbsp;"
    기배지 = _hdr_flow_badge("기관") if 기 is not None else "&nbsp;"

    return {"코": 코, "닥": 닥, "실탄": 실탄, "외인": 외, "기관": 기,
            "외배지": 외배지, "기배지": 기배지,
            "이모": 이모, "성격이름": 이름, "성격부제": 성격부제, "태그색": (태그[0] if 태그 else None)}


def _flow_line(실탄):
    if 실탄 is None:
        return "", "flat"
    cls = "up" if 실탄 >= 0 else "down"
    word = "순매수" if 실탄 >= 0 else "순매도"
    return f"{_flow_amt(실탄)} {word}", cls


CORE_ACC_FILE = "core_accum_log.json"


CORE_ACC_회피일 = 5   # 🆕 2026-08-24 HO 지시 — 최근 며칠치를 피할지


def _core_accum_recent(일수=None):
    """최근 N번의 발행에서 핵심편에 노출한 매집 종목 이름들.

    🆕 2026-08-24 HO 지시 — 예전에는 **어제 하루치만** 피했다.
       20일 매집은 같은 종목이 며칠씩 1위를 지키는 성격이라, 하루만 건너뛰면
       'A→B→A→B'로 두 종목이 번갈아 나오며 결국 늘 같은 얼굴이 됐다.
       그래서 최근 {CORE_ACC_회피일}번의 발행분을 모두 피한다.
    ⚠️ 그래도 **다 겹치면 그냥 1위를 쓴다**(코너가 비는 것보다 낫다).
       회피는 목표가 아니라 취향이다 — 강한 매집 종목을 영영 못 보게 하면 안 된다.
    ⚠️ daily.yml의 git add 목록에 core_accum_log.json이 없으면 매일 초기화되어
       중복 회피가 작동하지 않는다.
    """
    n = CORE_ACC_회피일 if 일수 is None else 일수
    try:
        if not os.path.exists(CORE_ACC_FILE):
            return set()
        with open(CORE_ACC_FILE, encoding="utf-8") as f:
            기록 = json.load(f) or {}
        과거 = sorted(k for k in 기록 if str(k) < str(DATE))[-n:]
        모음 = set()
        for k in 과거:
            모음 |= set(기록.get(k) or [])
        return 모음
    except Exception as e:
        print(f"   ⚠️ 매집 노출 이력 읽기 실패 — {type(e).__name__} (중복 회피 없이 진행)")
        return set()


def _core_accum_save(이름들):
    """오늘 노출한 종목을 기록한다(같은 날 재빌드해도 덮어쓰기라 안전)."""
    try:
        기록 = {}
        if os.path.exists(CORE_ACC_FILE):
            with open(CORE_ACC_FILE, encoding="utf-8") as f:
                기록 = json.load(f) or {}
        기록[str(DATE)] = sorted(이름들)
        for k in sorted(기록)[:-30]:      # 최근 30일치만 보관
            기록.pop(k, None)
        with open(CORE_ACC_FILE, "w", encoding="utf-8") as f:
            json.dump(기록, f, ensure_ascii=False, indent=1)
    except Exception as e:
        print(f"   ⚠️ 매집 노출 이력 저장 실패 — {type(e).__name__}")


def build_core_strong(강세레이더):
    """🔥 핵심편용 — 오늘 강세 포착 종목 2개만.

    🆕 2026-08-22 HO 지시. 심층편 강세 레이더는 표 전체를 보여주지만,
       핵심편에서는 **점수 상위 2종목**만 맛보기로 둔다.
    ⚠️ 정렬은 심층편과 동일하게 '강세점수'(회전율×0.5 + 상승률×0.5).
    ⚠️ 이 코너의 조건은 매집과 **정반대**다 — 매집은 상승률 조건이 없지만,
       강세는 코스피 4%↑ / 코스닥 5%↑ 상승이 필수다. 설명문을 섞지 말 것.
    ⚠️ 실측 성적이 D+1 −0.42%로 좋지 않다. 그래서 "추천"으로 읽히지 않게
       하단 고지를 반드시 붙인다.
    """
    신규 = (강세레이더 or {}).get("신규") or {}
    후보 = []
    for 시장 in ("코스피", "코스닥"):
        for s in (신규.get(시장) or []):
            if isinstance(s, dict) and s.get("종목명"):
                s = dict(s)
                s.setdefault("시장", 시장)
                후보.append(s)
    if not 후보:
        return ""
    # 🆕 2026-08-22 HO 지시 — 핵심편은 **최대 2종목**까지만.
    #    ⚠️ 무료 사용자는 핵심편만 본다. 전부 보여주면 유료로 갈 이유가 없어진다.
    #    규칙: 「돈이 몰린 종목」1개 + 「V자 반등 종목」1개.
    #          한쪽이 없으면 **다른 쪽에서 2개**를 채운다.
    후보.sort(key=lambda s: s.get("강세점수") or 0, reverse=True)

    def _유형(s):
        return s.get("유형들") or ([s["유형"]] if s.get("유형") else [])

    뽑기, 쓴이름 = [], set()
    for _t in ("돈이 몰린 종목", "V자 반등 종목"):
        for s in 후보:
            if s.get("종목명") in 쓴이름:
                continue
            if _t in _유형(s):
                뽑기.append(s)
                쓴이름.add(s["종목명"])
                break
    # 한쪽이 비었으면 남은 자리를 점수 순으로 채운다
    for s in 후보:
        if len(뽑기) >= 2:
            break
        if s.get("종목명") not in 쓴이름:
            뽑기.append(s)
            쓴이름.add(s["종목명"])
    뽑기 = 뽑기[:2]

    색맵 = {"코스피": "#f0c65a", "코스닥": "#74f0d4"}
    행들 = []
    for s in 뽑기:
        nm = s.get("종목명", "—")
        c = 색맵.get(s.get("시장"), "#c9ced6")
        등 = s.get("등락률")
        등문 = "—" if 등 is None else f"{등:+.1f}%"
        배수 = s.get("배수")
        배수문 = "—" if 배수 is None else f"{배수:.1f}배"
        재점화 = s.get("재점화")
        # 🆕 2026-08-29 HO 지적 — 「2차 재점화」가 옆 유형 배지보다 살짝 위로
        #    떠 보였다. [원인] 유형 배지는 padding+border가 있어 세로로 두꺼운데
        #    이 배지는 맨 글자라, 부모의 align-items:baseline 기준으로 글자
        #    밑선만 맞춰져 결과적으로 위로 밀려 보였다.
        #    [고침] 같은 inline-block + 같은 세로 padding(2px)을 주고
        #    vertical-align:middle로 가운데를 맞춘다. 테두리는 안 준다 —
        #    유형 배지가 주인공이고 이건 부가 정보라 덜 튀어야 한다.
        뱃지 = (f'<span style="display:inline-block;vertical-align:middle;'
              f'font-size:10.5px;color:#ff6b4a;padding:2px 0;'
              f'white-space:nowrap">🔁 {재점화}차 재점화</span>'
              if 재점화 and 재점화 > 1 else "")
        # 🆕 2026-08-22 — 어떤 기법으로 잡혔는지 배지로 보여준다.
        #    두 기법은 재는 기준부터 달라서(전일종가 vs 당일시가),
        #    안 보여주면 왜 잡혔는지 알 수 없다.
        #    ⚠️ 배지는 짧게 쓴다 — 카드 자체가 종목 목록이라 "종목"은 중복이고,
        #       320px에서 이름이 길면 줄바꿈으로 카드가 지저분해진다.
        _배지명 = {"돈이 몰린 종목": "💰 돈이 몰림", "V자 반등 종목": "📈 V자 반등"}
        # 🆕 2026-08-26 (2차) HO 지적 — 심층편 레이더는 **밝은 배경**이라
        #    금색(#f0c65a)·민트(#74f0d4)가 흰 바탕에 묻혀 글자가 안 읽혔다.
        #    ⚠️ 핵심편(어두운 배경)과 같은 색을 쓰면 한쪽이 반드시 죽는다 —
        #       이 파일에서 세 번 반복된 실수다. 심층편 전용으로 **더 짙은 색**을 쓴다.
        _유형색 = {"돈이 몰린 종목": "#a97400", "V자 반등 종목": "#0f8a76"}
        # ⚠️ 한 종목이 두 유형에 동시에 걸릴 수 있다(독립 판정). 배지를 모두 단다.
        _유들 = s.get("유형들") or ([s["유형"]] if s.get("유형") else [])
        if _유들:
            # 🆕 2026-08-26 HO 지시 — 배경 제거, 같은 색 테두리 2px.
            뱃지 = "".join(
                # 글자를 9 → 10.5px로 키우고 테두리 투명도도 조금 올린다(66→99).
                # 🆕 2026-08-29 — 옆 「N차 재점화」와 세로 기준을 맞춘다
                #    (inline-block + vertical-align:middle로 둘 다 통일).
                f'<span style="display:inline-block;vertical-align:middle;'
                f'font-size:10.5px;font-weight:800;'
                f'color:{_유형색.get(t,"#8b93a0")};background:none;'
                f'border:1px solid {_유형색.get(t,"#8b93a0")}99;border-radius:5px;'
                f'padding:2px 7px;margin-right:4px;white-space:nowrap">'
                f'{_배지명.get(t, t)}</span>' for t in _유들) + 뱃지
        # ⚠️ 등락률은 V자 반등에서 **음수일 수 있다.** 색을 나눈다.
        _등색 = "#ff6b4a" if (등 or 0) >= 0 else "#5b9bff"
        # ⚠️ 설명문도 기법마다 달라야 한다. V자 반등에 "돈이 몰렸어요"라고 쓰면
        #    그 기법의 핵심(장중에 되돌렸다)을 못 전한다.
        _저, _종 = s.get("시가대비저점"), s.get("시가대비종가")
        if "V자 반등 종목" in _유들 and _저 is not None and _종 is not None:
            _본문 = (f'장중 시가보다 <b style="color:#5b9bff">{_저:.1f}%</b>까지 밀렸다가 '
                   f'<b style="color:#ff6b4a">{_종:+.1f}%</b>로 되돌리며 마감했어요')
        else:
            # 🆕 2026-08-24 HO 질문 — "평소의 기준이 뭐냐".
            #  ⚠️ 실제 코드는 **전일(어제) 거래량 대비**다(STR_배수_하한 = 전일 대비).
            #     그런데 화면엔 '평소'라고만 써서 독자가 20일 평균쯤으로 오해한다.
            #     원칙 10(화면 설명문 = 실제 코드 조건)에 걸린다. 말을 바꾼다.
            _본문 = (f'거래량이 <b style="color:#e8eaee">어제보다 {배수문}</b>로 늘면서 '
                   f'거래대금 <b style="color:#e8eaee">{_flow_amt(s.get("거래대금"))}</b>'
                   f'{_josa(_flow_amt(s.get("거래대금")), "이가")} '
                   f'몰렸어요')
        # 🆕 2026-08-26 HO 지시 — 종목명 → 등락률 → 기업분석 순서.
        _끼움 = (f'<span style="font-size:13px;font-weight:800;color:{_등색};'
               f'margin:0 5px 0 6px">{등문}</span>')
        _이름, _칸 = sc_click(nm, c, 15, _끼움)
        행들.append(
            f'<div style="padding:10px 11px;margin-top:7px;'
            f'background:rgba(26,12,9,.55);'
            f'border-radius:9px;border-left:3px solid {c}">'
            f'<div style="display:flex;align-items:baseline;gap:7px;flex-wrap:wrap">'
            f'<span style="font-size:10.5px;color:#8b93a0">{s.get("시장","")}</span>'
            f'{_이름}</div>'
            # 🆕 2026-08-26 HO 지시 — 배지를 종목명과 같은 줄에 두면 폭이 되는
            #    대로 끊겨 흩어진다. **다음 줄에 나란히** 놓는다.
            + (f'<div style="display:flex;gap:5px;flex-wrap:wrap;margin-top:5px">'
               f'{뱃지}</div>' if 뱃지 else '')
            + (f'<p style="margin:4px 0 0;font-size:11.5px;color:#c9ced6;line-height:1.6">'
            f'{_본문}</p>{_칸}</div>'))

    return (f'<div style="background:linear-gradient(160deg,#2b1a16,#241713);'
            f'border:1.5px solid #5a3229;border-radius:14px;'
            f'padding:15px 15px 14px;margin:12px 0 0;'
            f'box-shadow:0 0 0 1px rgba(255,107,74,.07)">'
            f'<p style="margin:0 0 3px;font-size:11.5px;color:#ff6b4a;font-weight:700">'
            f'강세 레이더</p>'
            f'<p style="margin:0 0 4px;font-size:17.5px;font-weight:800;color:#f2f4f7">'
            f'<span class="cp-flame">🔥</span> 오늘 강한 종목</p>'
            # 🆕 2026-08-22 HO 지시 — "2종목만 보여드려요" 배지 제거.
            #    유료판에서는 심층편이 바로 아래 있어 굳이 안내할 이유가 없다.
            f'{"".join(행들)}'
            f'<p style="margin:9px 0 0;padding-top:8px;'
            f'border-top:.5px solid rgba(255,255,255,.08);'
            f'font-size:10.5px;color:#7d848f;line-height:1.6">'
            f'⚠️ 포착은 <b style="color:#c9ced6">추천이 아닙니다.</b> '
            f'오늘 이런 움직임이 있었다는 사실만 알려드려요.<br>'
            f'💰 <b>돈이 몰림</b>은 이미 크게 오른 자리라 다음 날 되밀리기도 하고, '
            f'📈 <b>V자 반등</b>은 되돌린 힘이 이어질지 하루짜리인지 아직 모릅니다 — '
            f'두 기법의 성적은 <b style="color:#c9ced6">5·20·60·120일로 추적해</b> '
            f'그대로 공개할게요.</p></div>')


def build_core_accum(매집):
    """🐢 핵심편용 — 매집 종목을 코스피·코스닥 1개씩만.

    🆕 2026-08-22 HO 지시. 심층편 매집 레이더는 표 전체를 보여주지만,
       핵심편에서는 **각 시장 대표 1개씩**만 뽑아 맛보기로 둔다.
    🆕 2026-08-29 HO 지시 — **20일 위주로 보여주되, 최근에 나온 종목이면
       5일(또는 60일)로 바꿔서 보여준다.**
       ⚠️ "랜덤"이라는 표현을 그대로 난수로 구현하지 않았다. 난수를 쓰면
          같은 날 새로고침할 때마다 종목이 바뀌어(리포트가 매번 달라져)
          "어제 뭘 봤는지"를 되짚을 수 없고, 원칙 7(매일 내용물이 바뀌는
          칸은 누적하지 않는다)과도 어긋난다. HO의 실제 의도는
          "매일 같은 종목만 나오지 않게 해달라"이므로, **기간을 바꿔가며
          새 얼굴을 찾는** 방식으로 구현한다. 결과적으로 날마다 다른
          종목이 나오면서도 그 날의 리포트는 몇 번을 열어도 똑같다.
       탐색 순서: 20일 → 5일 → 60일 (20일이 기본, 겹치면 다음 기간으로)
    ⚠️ 정렬 기준은 심층편과 동일하게 '매집강도'다.
       매집강도 = 시총대비 ÷ (1 + 기간등락률/100)
       → 같은 금액을 담았어도 **덜 올랐을수록** 위로 온다.
         "샀다"가 아니라 "조용히 모았다"를 찾는 게 이 코너의 목적이기 때문이다.
    ⚠️ 상승률 조건은 없다. (그건 강세 레이더 조건이다 — 혼동 주의)
    """
    매집 = 매집 or {}
    # (목록, 기간, 등락률필드) — 20일을 맨 앞에 둬 «기본»으로 삼는다.
    _풀 = [
        (매집.get("중기종목") or [], 매집.get("중기기간", 20), "장기등락률"),
        (매집.get("종목") or [], 매집.get("기간", 5), "등락률"),
        (매집.get("장기종목") or [], 매집.get("장기기간", 60), "장기등락률"),
    ]
    _풀 = [(lst, per, fld) for lst, per, fld in _풀 if lst]
    if not _풀:
        return ""

    # 🆕 2026-08-22 HO 지시 — **어제 노출한 종목은 건너뛰고 다음 순위로.**
    #    20일 매집은 성격상 며칠씩 같은 종목이 1위를 지킨다. 그대로 두면
    #    핵심편에 매일 같은 이름이 나와 "새 정보가 없는 코너"가 된다.
    #    ⚠️ 어제 것만 피한다(2일 전은 다시 나와도 된다) — 너무 오래 막으면
    #       정작 가장 강한 매집 종목이 영영 안 보인다.
    _최근 = _core_accum_recent()

    def _고르기(목록, 시장, 제외):
        """한 기간 목록 안에서 매집강도 1위부터 훑되, 제외 종목은 건너뛴다.
        찾으면 종목을, 전부 겹치면 None을 돌려준다(다음 기간에서 다시 찾게)."""
        후보 = sorted([s for s in 목록 if s.get("시장") == 시장
                     and s.get("매집강도") is not None],
                    key=lambda s: s["매집강도"], reverse=True)
        for s in 후보:
            if s.get("종목명") not in 제외:
                return s
        return None

    def _아무거나(시장):
        """모든 기간에서 다 겹쳤을 때의 최후 수단 — 20일 1위를 그냥 쓴다.
        (HO: "안 되면 그대로 보여주는 건 됨")"""
        for 목록, 기간, 필드 in _풀:
            후보 = sorted([s for s in 목록 if s.get("시장") == 시장
                         and s.get("매집강도") is not None],
                        key=lambda s: s["매집강도"], reverse=True)
            if 후보:
                return 후보[0], 기간, 필드
        return None, None, None

    _직전 = _core_accum_recent(1)      # 완화 단계에서 쓸 '어제만' 집합
    뽑기, _쓴이름 = [], set()
    for 시장 in ("코스피", "코스닥"):
        _찾음 = None
        # ① 최근 5회 노출분을 피해 20일 → 5일 → 60일 순으로 새 얼굴을 찾는다
        for 목록, 기간, 필드 in _풀:
            _s = _고르기(목록, 시장, _최근 | _쓴이름)
            if _s:
                _찾음 = (_s, 기간, 필드)
                break
        # ② 그래도 없으면 '어제만' 피해서 다시 한 바퀴
        if not _찾음:
            for 목록, 기간, 필드 in _풀:
                _s = _고르기(목록, 시장, _직전 | _쓴이름)
                if _s:
                    _찾음 = (_s, 기간, 필드)
                    break
        # ③ 전부 겹치면 20일 1위 그대로
        if not _찾음:
            _s, 기간, 필드 = _아무거나(시장)
            if _s:
                _찾음 = (_s, 기간, 필드)
        if _찾음:
            뽑기.append(_찾음)
            _쓴이름.add(_찾음[0].get("종목명"))
    _core_accum_save(_쓴이름)
    if not 뽑기:
        return ""

    색맵 = {"코스피": "#f0c65a", "코스닥": "#74f0d4"}
    행들 = []
    for s, 기간, 등락필드 in 뽑기:
        nm = s.get("종목명", "—")
        c = 색맵.get(s.get("시장"), "#c9ced6")
        # ⚠️ 5일 목록은 등락률 필드 이름이 다르다(«등락률») — 기간에 맞는
        #    필드를 써야 "그동안 주가는" 숫자가 그 기간의 것이 된다.
        등 = s.get(등락필드)
        if 등 is None:
            등 = s.get("장기등락률") if 등락필드 == "등락률" else s.get("등락률")
        등문 = "—" if 등 is None else f"{등:+.1f}%"
        등색 = "#8b93a0" if 등 is None else ("#ff6b4a" if 등 >= 0 else "#5b9bff")
        유형 = "🤝 쌍끌이" if s.get("유형") == "쌍끌이" else f"💼 {s.get('유형','단독')}"
        _이름, _칸 = sc_click(nm, c, 15)
        행들.append(
            f'<div style="padding:10px 11px;margin-top:7px;'
            f'background:rgba(9,14,19,.66);'
            f'border-radius:9px;border-left:3px solid {c}">'
            f'<div style="display:flex;align-items:baseline;gap:7px;flex-wrap:wrap">'
            f'<span style="font-size:10.5px;color:#8b93a0">{s.get("시장","")}</span>'
            f'{_이름}'
            f'<span style="font-size:10.5px;color:#8b93a0">{유형}</span></div>'
            f'<p style="margin:4px 0 0;font-size:11.5px;color:#c9ced6;line-height:1.6">'
            f'외국인·기관이 {기간}일간 <b style="color:#e8eaee">'
            f'{_flow_amt(s.get("합산"))}</b>'
            f'{_josa(_flow_amt(s.get("합산")), "을를")} 담았어요 '
            f'(시총의 {s.get("시총대비", 0):.2f}%) · 그동안 주가는 '
            f'<b style="color:{등색}">{등문}</b></p>{_칸}</div>')

    # 🆕 2026-08-22 HO 지시 — 이 코너가 핵심편의 **메인**이라 배경을 따로 준다.
    #    (다른 카드는 #141922 단색, 여기는 청록 그라데이션 + 굵은 테두리)
    #    조건 설명은 심층편 매집 레이더에 있으므로 여기선 뺀다.
    return (f'<div style="background:linear-gradient(160deg,#16232b,#131a24);'
            f'border:1.5px solid #2b4a52;border-radius:14px;'
            f'padding:15px 15px 14px;margin:12px 0 0;'
            f'box-shadow:0 0 0 1px rgba(116,240,212,.07)">'
            f'<p style="margin:0 0 3px;font-size:11.5px;color:#74f0d4;font-weight:700">'
            f'매집 레이더</p>'
            f'<p style="margin:0 0 4px;font-size:17.5px;font-weight:800;color:#f2f4f7">'
            f'<span class="cp-turtle">🐢</span> 외국인, 기관이 조용히 매집하는 종목</p>'
            # 🆕 2026-08-22 — 회색이라 묻혀 보인다는 지적. 눈에 띄는 배지로.
            # 🆕 2026-08-22 HO 지시 — "2종목만 보여드려요" 배지 제거.
            f'{"".join(행들)}'
            # 🆕 2026-08-24 HO 지시 — 선정 기준을 한 줄로 밝힌다.
            #  ⚠️ 왜 필요한가: "외인·기관이 샀다"는 흔한 얘기라 그것만 보면
            #     이 코너가 왜 특별한지 알 수 없다. 실제 기준은 두 가지가 더 있다 —
            #     ① **시총 대비** 얼마나 들어왔나(금액이 아니라 비율)
            #     ② 하루 몰빵이 아니라 **며칠에 걸쳐 연속으로** 샀나
            #     이 둘을 안 밝히면 독자가 코너의 값어치를 못 알아본다.
            f'<p style="margin:9px 0 0;padding:8px 10px;background:rgba(116,240,212,.06);'
            f'border-radius:8px;font-size:10.5px;color:#9aa4ae;line-height:1.65">'
            f'💡 외인·기관이 <b style="color:#74f0d4">샀다</b>는 것만으론 안 뽑아요. '
            f'금액이 아니라 <b style="color:#74f0d4">시가총액 대비 비율</b>이 크고, '
            f'하루 몰빵이 아니라 <b style="color:#74f0d4">며칠에 걸쳐 연속으로</b> '
            f'사들인 종목만 올라와요. 덜 오른 종목일수록 위로 옵니다.</p></div>')


def build_closing(해석, 날짜표기=""):
    """🗼 관제탑에서 내려다본 오늘 — 리포트를 닫는 마지막 교신.

    🆕 2026-08-22 — 예전 「✍️ 오늘을 한 문장으로」를 확장했다.
    ⚠️ 왜 바꿨나
       리포트는 신호등 → 무슨 일 → 왜 → 섹터 → 내 종목 → 내일 예보로 흐르는데,
       예보 다음에 격언 한 줄만 오면 감정이 한 번 식었다가 다시 뜨는 모양이 된다.
       마지막 자리는 **하루를 닫고 내일로 넘기는** 역할이어야 한다.
    구성 — ① 오늘을 한 문장으로  ② 이 하루가 흐름의 어디쯤인가  ③ 닫는 인사
       ②③이 비면 ①만 나온다(재사용 모드에서도 안 깨진다).
    """
    문장 = (해석.get("오늘의_한문장") or "").strip()
    위치 = (해석.get("오늘의_위치") or "").strip()
    인사 = (해석.get("닫는인사") or "").strip()
    if not 문장:
        문장 = "오늘 시장이 준 교훈이 이 자리에 담깁니다. (Claude 해석 연동 후 자동 생성)"

    위치줄 = ""
    if 위치:
        위치줄 = (f'<p style="margin:13px 0 0;padding-top:12px;'
                f'border-top:.5px solid rgba(255,255,255,.1);'
                f'font-size:12.5px;color:#c9ced6;line-height:1.75">'
                f'<b style="color:#22d3ee">📍 오늘 이 하루는</b> {위치}</p>')
    인사줄 = ""
    if 인사:
        인사줄 = (f'<p style="margin:11px 0 0;font-size:12.5px;color:#9aa3ae;'
                f'line-height:1.7;font-style:italic">{인사}</p>')

    return f'''
  <p class="sec-label"><small>마지막 교신</small>🗼 관제탑에서 내려다본 오늘</p>
  <div class="quote-box">
    <div class="quote-mark">“</div>
    <p class="quote-text">{문장}</p>
    {위치줄}{인사줄}
    <p class="quote-sub">— 차트프로 관제탑, {날짜표기}</p>
  </div>'''


def build_signal_head(지수수급, 파생, 코수, 관제=None, 사건명=None):
    """🚦 신호등 + 오늘의 사건명 — 핵심편 맨 위.

    ⚠️ 2026-08-22 사고 복구 — 핵심편 헤더를 「오늘의 성적표」 카드로 교체하면서
       build_index_header()를 통째로 걷어냈는데, **신호등이 그 안에 있어서**
       같이 사라졌다. 신호등은 지수 막대와 별개 자산이므로 함수로 떼어내
       성적표 위에 그대로 되살린다.
    """
    try:
        d = _header_data(지수수급, 파생, 코수, 사건명)
        코등 = (d["코"]["등"] if isinstance(d.get("코"), dict) else None) or 0
        링색 = {"good": "#ff6b4a", "warn": "#e0c060", "info": "#5b9bff"}.get(
            d.get("태그색"),
            "#ff6b4a" if 코등 > 0 else "#5b9bff" if 코등 < 0 else "#9aa0a8")
        _관 = 관제 or {}
        아이콘HTML = _head_icon(코등, 링색, d["이모"],
                             관제점수=_관.get("점수"), 관제구간=_관.get("구간"),
                             태그색=d.get("태그색"))
        return (f'<div class="ix-head" style="margin-bottom:.6rem">'
                f'<div class="ix-mood">{아이콘HTML}'
                f'<div class="ix-mood-txt"><p class="ix-mood-t">'
                f'<span class="yl">{d["성격이름"]}</span></p>'
                f'<p class="ix-mood-s">{d["성격부제"]}</p></div></div></div>')
    except Exception as e:
        print(f"   ⚠️ 신호등 렌더 실패 — {type(e).__name__} (나머지는 정상 발행)")
        return ""


def build_index_header(지수수급, 파생, 코수, style=None, 관제=None, 사건명=None):
    """핵심편 최상단 지수 헤더 — style 상수로 5가지 레이아웃 중 하나를 그린다."""
    style = style or HEADER_STYLE
    d = _header_data(지수수급, 파생, 코수, 사건명)
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

        수급블록 = (f'<div class="ix-div"></div><p class="ix-grouplbl">코스피 수급 (±3조)</p>'
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
                # ⚠️ 앞의 "오늘은"은 매일 똑같아 자리만 먹는다(2026-08-20 지시). 뺐다.
                f'<div class="ix-mood-txt"><p class="ix-mood-t"><span class="yl">{d["성격이름"]}</span></p>'
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



def build_new_theme(격자):
    """🆕 어디에도 안 걸린 새 테마 — '오늘의 주인공' 옆자리.

    ⚠️ 이 칸은 격자(주소 지도)에서 옮겨온 것이다.
       15개 고정 슬롯 어디에도 안 걸린 테마 중 **오늘 가장 센 것**이라
       담기는 종목이 매일 통째로 바뀐다. 그래서
         · 누적 통계에는 절대 넣지 않는다 (ZONE_EXCLUDE)
         · 어제와 비교하지 않는다 ("어제도 올랐다"는 말이 성립하지 않는다)
         · 편차가 크면 평균이 거짓이 되므로 그 사실을 화면에 적는다
    """
    행 = None
    for r in ((격자 or {}).get("행") or []):
        if r.get("테마") in ZONE_EXCLUDE:
            행 = r
            break
    if not 행:
        return ""
    테마 = (행.get("네이버테마") or [None])[0]
    if not 테마:
        return ""
    전체 = 행.get("전체")
    종목 = []
    for 층 in ("대형", "중형", "소형"):
        c = (행.get("칸") or {}).get(층) or {}
        for x in (c.get("종목") or []):
            if isinstance(x, dict) and x.get("명") is not None:
                종목.append((x["명"], x.get("등")))
    종목 = [t for t in 종목 if t[1] is not None]
    종목.sort(key=lambda t: -t[1])

    칩 = "".join(
        f'<span class="nt-chip" style="border-color:'
        f'{FS_BUY if v >= 0 else FS_SELL}55;color:{FS_BUY if v >= 0 else FS_SELL}">'
        f'{nm} {v:+.1f}%</span>' for nm, v in 종목[:8])

    경고 = ""
    if len(종목) >= 3:
        폭 = 종목[0][1] - 종목[-1][1]
        if 폭 >= 20:
            경고 = (f'<p class="nt-warn">⚠️ 같은 꾸러미인데 '
                    f'<b>{종목[0][0]} {종목[0][1]:+.1f}%</b> ~ '
                    f'<b>{종목[-1][0]} {종목[-1][1]:+.1f}%</b>로 '
                    f'<b>{폭:.0f}%p</b> 벌어졌습니다. '
                    f'<b>평균({전체:+.1f}%)만 보면 안 됩니다.</b></p>')

    색 = FS_BUY if (전체 or 0) >= 0 else FS_SELL
    return f'''
  <div class="nt-box">
    <p class="nt-k">🆕 어디에도 안 걸린 새 테마</p>
    <p class="nt-t">{테마} <span style="color:{색}">{전체:+.1f}%</span></p>
    <p class="nt-s">15개 고정 구역 어디에도 안 들어가는 테마 중, 오늘 가장 세게 움직인 곳입니다.</p>
    <div class="nt-chips">{칩}</div>
    {경고}
    <p class="nt-foot">⚠️ <b>이 칸은 매일 내용물이 통째로 바뀝니다.</b>
      어제의 새 테마와 오늘의 새 테마는 아무 관계가 없어, 누적 성적에는 넣지 않습니다.
      "새 테마가 계속 뜬다"로 읽으면 안 됩니다.</p>
  </div>'''


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
    # ⚠️ 「신규 테마」는 격자에서 뺀다(2026-08-18).
    #    격자는 "안 바뀌는 주소"인데 이 칸만 매일 내용물이 통째로 바뀐다.
    #    → build_new_theme()이 '오늘의 주인공' 옆에서 따로 보여준다.
    행들 = [r for r in (격자.get("행") or []) if r.get("테마") not in ZONE_EXCLUDE]
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
        # ⚠️ 「신규 테마」는 **매일 내용물이 통째로 바뀌는 칸**이다.
        #    (8/14 정유 → 8/16 스마트카 → 8/18 신규상장)
        #    이름만 고정이라 "같은 섹터가 계속 뜨고 있다"는 착시를 준다.
        #    → 오늘 실제로 무엇이 담겼는지를 이름 옆에 적어 매일 바뀜을 드러낸다.
        if _풀 in ZONE_EXCLUDE:
            _오늘테마 = (r.get("네이버테마") or [None])[0]
            if _오늘테마:
                _풀 = f"{_풀} · {_오늘테마}"
        _불 = 불난구역.get(str(r.get("테마", "")))
        불배지 = (f'<span style="color:#ff9a3c;font-size:9px;flex:none" '
                f'title="오늘 뜨는 현장: {", ".join(_불)}">&nbsp;🔥</span>') if _불 else ''
        테마명 = (f'<span style="flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;'
                 f'white-space:nowrap">{_풀}</span>{불배지}{ZONE_ARROW}')
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
            '<p style="margin:0 0 2px;font-size:12px;color:#8b93a0;letter-spacing:.02em">내 종목 지도</p>'
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
            '<span style="color:#ff9a3c">🔥</span>는 오늘 그 섹터에서 불이 난 구역입니다<br>'
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
            f'오늘 {한글수} 가지만 기억하세요</p>'
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
    # 📅 거래일만 — archive_days()가 휴장일 중복을 걸러준다
    for _ymd, d in archive_days(days):
        try:
            m = {}
            for s in (d.get("주도섹터") or []):
                nm, sc = s.get("테마명"), s.get("주도력점수")
                if nm and isinstance(sc, (int, float)):
                    m[nm] = float(sc)
            if m:
                # ⚠️ 예전 코드의 f[5:13](파일명 자르기)이 남아 있었다.
                #    archive_days로 바꾸면서 f가 사라져 **매번 NameError → continue**로
                #    통째로 버려졌고, 순위 섹터맵·돌아올 섹터·관제 레이더가 전부
                #    빈 화면이 됐다(2026-08-20). try/except가 오류를 삼켜 안 보였다.
                out.append((d.get("날짜") or _ymd, m))
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
    "신규 테마":         "#ef4444",   # 구 "신규 주도" — 2026-08-18 개명
    "신규 주도":         "#ef4444",   # ⚠️ 과거 archive 호환용(지우면 옛 리포트 색이 깨진다)
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


# ⚠️ '당일'(1일) 탭 — 오늘 하루만 놓고 본 섹터 성적.
#    5일 이상은 "흐름"이지만 1일은 "오늘 어디가 셌나"라 성격이 다르다.
#    누적곱이 하루뿐이라 승패(승/총)는 0승 또는 1승으로만 나오므로,
#    화면에서는 초과수익만 의미가 있다.
ZONE_WINDOWS = [(1, "당일", "오늘"), (5, "이번 주", "5일"),
                (20, "한 달", "20일"), (60, "분기", "60일")]
ZONE_TOP_N = 5          # 처음에 펼쳐 보여줄 줄 수 (나머지는 '더보기')
#  창별 최소 관측일 — 이만큼 없으면 그 탭은 "축적 중"으로 둔다.
#  ⚠️ 2일치로 "이번 주 성적"이라고 쓰면 거짓말이 된다. 없는 비교는 만들지 않는다.
ZONE_MIN = {1: 1, 5: 5, 20: 10, 60: 30}

#  ⚠️ 누적 통계에서 빼야 하는 칸
#     「신규 테마」는 "어디에도 안 걸린 테마 중 오늘 최강"이라 **매일 내용물이 바뀐다**.
#     (8/14 정유 → 8/16 스마트카 → 8/18 신규상장)
#     서로 다른 종목 묶음의 등락률을 누적하면 곡선·순위·주기가 전부 거짓이 된다.
#     하루 격자에는 남기되, 누적하는 코너에서는 제외한다.
ZONE_EXCLUDE = {"신규 테마", "신규 주도"}   # 구 이름도 함께(과거 archive 호환)


def _zone_series():
    """{구역명: {날짜: 등락률}} 과 {날짜: 시장등락률}을 만든다.

    ⚠️ 휴장일 오염 제거 (2026-08-20 발견)
       워크플로가 토·일·공휴일에도 돌면 archive에 **직전 거래일과 똑같은
       data_*.json** 이 쌓인다(8/15 토, 8/17 대체공휴일 등).
       그대로 누적하면 5일·20일 탭의 승패·초과수익이 같은 날을 여러 번 세어
       "오늘 장 것 같지 않은" 숫자가 나온다.
       flow_history는 prune_flow_history()가 청소하지만, 여기는 archive를
       직접 훑기 때문에 **같은 가드를 여기에도 걸어야 한다.**
         ① 토·일은 날짜만으로 제외
         ② 직전 채택일과 격자 값이 완전히 동일하면 제외(공휴일)
    """
    구역 = {}
    # 📅 자체 가드를 쓰지 않고 공용 로더로 통일했다(2026-08-20).
    #    같은 필터가 여러 벌 있으면 하나를 고칠 때 다른 데가 빠진다.
    for 날짜, d in archive_days():
        for r in ((d.get("계좌격자") or {}).get("행") or []):
            v, nm = r.get("전체"), r.get("테마")
            if nm in ZONE_EXCLUDE:      # 매일 내용물이 바뀌는 칸 — 누적 금지
                continue
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
     "stocks":{종목명:[구역들, 순위, 층, 시장, 종목코드]},
     "ret":{종목명:[일별 등락률...]}}   ← ret는 days와 같은 길이(없는 날 null)
    """
    days, per = [], {}
    meta = {}
    # 📅 거래일만 — archive_days()가 휴장일 중복을 걸러준다
    for _ymd, d in archive_days(MYSTOCK_DAYS):
        사전 = (d.get("계좌격자") or {}).get("종목사전") or {}
        if not 사전:
            continue
        날짜 = d.get("날짜")
        days.append(날짜)
        for nm, v in 사전.items():
            per.setdefault(nm, {})[날짜] = v[3] if len(v) > 3 else None
            # 🆕 2026-08-24 — 5번째 자리에 **종목코드**(토론방 링크용).
            #  ⚠️ 2026-08-24 이전 archive에는 코드가 없다 → None이 들어오고
            #     화면에서는 배지가 안 붙는다(죽은 링크를 놓지 않는다).
            _옛 = meta.get(nm) or []
            _코드 = (v[5] if len(v) > 5 else None) or (_옛[4] if len(_옛) > 4 else None)
            meta[nm] = [v[0] if v else [], v[1] if len(v) > 1 else None,
                        v[2] if len(v) > 2 else None, v[4] if len(v) > 4 else None,
                        _코드]
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
    # 자체 자동완성이 쓸 종목명 배열 (datalist 대체)
    이름배열JS = "window.CP_NAMES=" + json.dumps(이름들, ensure_ascii=False) + ";"
    # 브리핑이 "조용한 날"에 쓸 재료 — 구역별 오늘 등락률
    _오늘구역 = {}
    try:
        for _r in ((data.get("계좌격자") or {}).get("행") or []):
            _nm, _v = _r.get("테마"), _r.get("전체")
            if _nm and _v is not None:
                _오늘구역[_nm] = _v
    except Exception:
        _오늘구역 = {}
    이름배열JS += "window.CP_SECT_TODAY=" + json.dumps(_오늘구역, ensure_ascii=False) + ";"
    # 🆕 2026-08-29 HO 지시 — "무리에서 이탈" 알림의 재료. 오늘 하루만으론
    #    "계속" 뒤처지는지 알 수 없다 — 최근 5거래일 구역별 등락 시계열이
    #    필요하다. _zone_series()가 이미 계산해 사다리 그래프에 쓰고 있는
    #    걸 그대로 재사용한다(새 수집 0회).
    _구역시계열 = {}
    try:
        _구역들, _ = _zone_series()
        for _nm, _일별 in _구역들.items():
            _최근5 = sorted(_일별.items())[-5:]
            if _최근5:
                _구역시계열[_nm] = _최근5
    except Exception as e:
        print(f"   ⚠️ 구역 시계열(이탈 알림용) 읽기 실패 — {type(e).__name__}")
        _구역시계열 = {}
    이름배열JS += "window.CP_SECT_SERIES=" + json.dumps(_구역시계열, ensure_ascii=False) + ";"
    # 종목 → 오늘 주도 테마명 (구역이 비었을 때 대신 보여준다)
    _종목테마 = {}
    try:
        for _s in (data.get("주도섹터") or []):
            _tn = _s.get("테마명")
            for _x in (_s.get("종목") or []):
                # 키가 '종목명'인 경우와 '명'인 경우가 섞여 있다
                _n = (_x.get("종목명") or _x.get("명")) if isinstance(_x, dict) else _x
                if _n and _n not in _종목테마:
                    _종목테마[_n] = _tn
    except Exception:
        _종목테마 = {}
    이름배열JS += "window.CP_STOCK_THEME=" + json.dumps(_종목테마, ensure_ascii=False) + ";"
    # 🆕 2026-08-26 — 종목이 묶인 **테마 여러 개**. "뭐 하는 회사인가"의 재료다.
    #  ⚠️ 매출 비중(사업 포트폴리오)은 DART 주요계정에 없다. 사업보고서 원문을
    #     파싱해야 나오는데 검증 못 한 파서는 배포하지 않는다(§3-⑥).
    #     그래서 지금은 **테마·섹터로 성격만** 알려준다. 지어내지 않는다.
    _종목테마들 = {}
    try:
        for _s in (data.get("주도섹터") or []):
            _tn = _s.get("테마명")
            for _x in (_s.get("종목") or []):
                _n = (_x.get("종목명") or _x.get("명")) if isinstance(_x, dict) else _x
                if not _n or not _tn:
                    continue
                _lst = _종목테마들.setdefault(_n, [])
                if _tn not in _lst and len(_lst) < 3:
                    _lst.append(_tn)
    except Exception:
        _종목테마들 = {}
    이름배열JS += "window.CP_THEMES=" + json.dumps(_종목테마들, ensure_ascii=False) + ";"
    # 종목 → 오늘 잡힌 레이더 이름 ('왜 움직였나' 판정에 쓴다)
    _핫 = {}
    try:
        for _k, _lab in (("강세레이더", "강세 레이더"), ("매집레이더", "매집 레이더")):
            _blk = data.get(_k) or {}
            _all = []
            for _v in (_blk.get("신규") or {}).values():
                _all += _v or []
            _all += (_blk.get("종목") or [])
            for _t in _all:
                _n = _t.get("종목명") or _t.get("명")
                if _n and _n not in _핫:
                    _핫[_n] = _lab
    except Exception:
        _핫 = {}
    이름배열JS += "window.CP_HOT=" + json.dumps(_핫, ensure_ascii=False) + ";"

    # 🆕 2026-08-25 — 종목 카드 재료 4종.
    #  ⚠️ 카드는 **HTML 안에 미리 심어둔다.** 정적 페이지라 클릭 시점에
    #     서버에 물어볼 수 없다(API 키를 넣으면 소스 보기로 다 샌다).
    _프로필 = data.get("기업프로필") or {}
    # 🆕 2026-08-26 — 저장돼 있던 업종코드(KSIC)를 **한글 업종명**으로 풀어 넣는다.
    #  [WHY] "건설·부동산 쪽 회사예요"는 섹터 이름을 되풀이한 것뿐이라 정보가 없었다.
    #        DART가 주는 induty_code를 그동안 저장만 하고 안 썼다.
    #  ⚠️ 앞 2자리(중분류)만 본다. 5자리 전체를 담으면 표가 1,000줄이 되는데
    #     정작 독자에게는 그만큼의 정밀도가 필요 없다.
    try:
        for _nm, _p in _프로필.items():
            _o = (_p or {}).get("개요") or {}
            _cd = str(_o.get("업종") or "").strip()
            if _cd:
                _o["업종명"] = KSIC_중분류.get(_cd.zfill(5)[:2], "")
            _est = str(_o.get("설립") or "")
            if len(_est) >= 4 and _est[:4].isdigit():
                _o["설립연"] = _est[:4]
    except Exception as e:
        print(f"   ⚠️ 업종명 변환 실패 — {type(e).__name__}")
    이름배열JS += "window.CP_PROFILE=" + json.dumps(_프로필, ensure_ascii=False) + ";"

    # 한 줄 정의 — 뭐 하는 회사인지. 업종 + 소속 섹터로 만든다.
    _한줄 = {}
    try:
        _사전 = (data.get("계좌격자") or {}).get("종목사전") or {}
        for _n, _v in _사전.items():
            _zs = _v[0] if _v else []
            if _zs:
                _한줄[_n] = " · ".join(_zs[:2])
    except Exception:
        _한줄 = {}
    이름배열JS += "window.CP_ONELINE=" + json.dumps(_한줄, ensure_ascii=False) + ";"

    # 📊 사업 포트폴리오(매출 비중) — 2026-09-01 정식 연결.
    #  [WHY] 기업분석 카드가 그동안 "매출을 어느 사업에서 얼마나 버는지는
    #        준비 중"으로 비워두고 있었다. biz_portfolio_parser.py가
    #        DART 원문을 해석해 만든 biz_portfolio.json이 이제 99.7%
    #        커버리지라(2026-09-01 실측), 화면에 연결할 근거가 충분하다.
    #  ⚠️ build_html은 여기서 아무것도 해석하지 않는다. 조립만 한다
    #     (원칙 1 — 숫자는 기계가, 글은 Claude가. 해석은 이미 끝나 있다).
    #  ⚠️ "부문"이 빈 배열인 항목("없음" — 정직한 무응답)은 화면에
    #     보낼 이유가 없다. 여기서 미리 걸러서 JS로 보낼 용량을 줄인다
    #     (2,771개 중 실제 부문 있는 건 1,548개뿐 — 나머지는 애초에 안 보냄).
    _bizport = {}
    try:
        if os.path.exists("biz_portfolio.json"):
            with open("biz_portfolio.json", encoding="utf-8") as _f:
                _bp원본 = json.load(_f) or {}
            _bizport = {k: v for k, v in _bp원본.items() if v.get("부문")}
            print(f"   📊 사업 포트폴리오 {len(_bizport)}종목 적재 "
                  f"(전체 {len(_bp원본)}개 중 실제 부문 있는 것만)")
        else:
            print("   📊 biz_portfolio.json 없음 — 포트폴리오 칸은 건너뜁니다(정상)")
    except Exception as e:
        print(f"   ⚠️ 사업 포트폴리오 적재 실패 — {type(e).__name__}")
        _bizport = {}
    이름배열JS += "window.CP_BIZPORT=" + json.dumps(_bizport, ensure_ascii=False) + ";"

    # 매집 상세 — '왜 떴나' 칸의 핵심. 조건을 숫자 그대로 넘긴다.
    # ⚠️ 재료를 **아끼지 않는다.** 카드가 부실해 보이는 건 데이터가 없어서가
    #    아니라 있는 걸 안 쓰고 있어서였다(2026-08-25 HO 지적).
    #    · 외국인/기관을 **나눠서** 보여준다 — 누가 사는지가 성격을 가른다
    #    · 5·20·60일에 **동시에** 걸렸는지 — 이게 매집 신뢰도의 핵심이다
    #    · 매집갭(사들인 정도 vs 주가 반응) — "샀는데 안 올랐다"의 수치
    _accd = {}
    try:
        _acc = data.get("매집레이더") or {}
        for _k, _lab, _rk in (("종목", "5일", "5일등락률"),
                              ("중기종목", "20일", "장기등락률"),
                              ("장기종목", "60일", "최장기등락률")):
            _lst = sorted([x for x in (_acc.get(_k) or [])
                           if isinstance(x, dict) and x.get("시총대비") is not None],
                          key=lambda x: x["시총대비"], reverse=True)
            for _i, _x in enumerate(_lst, 1):
                _n = _x.get("종목명")
                if not _n:
                    continue
                if _n in _accd:                       # 이미 있으면 '기간 동시 포착'만 추가
                    _accd[_n].setdefault("기간들", []).append(_lab)
                    continue
                _accd[_n] = {
                    "유형": _x.get("유형") or "매집", "기간": _lab,
                    "기간들": [_lab],
                    "합산": _flow_amt(_x.get("합산")),
                    "시총대비": f"{_x.get('시총대비'):.2f}%",
                    "순위": _i, "전체": len(_lst), "등락": _x.get(_rk),
                    "외국인": _flow_amt(_x.get("외국인")),
                    "기관": _flow_amt(_x.get("기관")),
                    "외인일수": _x.get("외인일수"), "기관일수": _x.get("기관일수"),
                    "성격": _x.get("성격"), "성격아이콘": _x.get("성격아이콘"),
                    "매집갭": _x.get("매집갭"), "배지": accum_badge(_n)}
    except Exception:
        _accd = {}

    # 과거에도 잡혔나 + 그 뒤 성적 — **우리만 가진 이력**
    _track = {}
    try:
        for _key, _lab in (("매집레이더", "매집"), ("강세레이더", "강세")):
            for _t in ((data.get(_key) or {}).get("추적") or []):
                _n = _t.get("종목명")
                if not _n or _t.get("경과", 0) < 1:
                    continue
                _p = _t.get("포착일") or ""
                _track.setdefault(_n, []).append({
                    "종류": _lab, "날": f"{_p[4:6]}/{_p[6:]}" if len(_p) == 8 else _p,
                    "경과": _t.get("경과"), "등락": _t.get("이후등락")})
        for _n in _track:
            _track[_n] = sorted(_track[_n], key=lambda x: -(x["경과"] or 0))[:2]
    except Exception:
        _track = {}
    이름배열JS += "window.CP_TRACK=" + json.dumps(_track, ensure_ascii=False) + ";"

    # 종목 기본 — 오늘 등락·시총 순위·층
    _basic = {}
    try:
        for _n, _v in ((data.get("계좌격자") or {}).get("종목사전") or {}).items():
            _basic[_n] = {"등락": _v[3] if len(_v) > 3 else None,
                          "순위": _v[1] if len(_v) > 1 else None,
                          "층": _v[2] if len(_v) > 2 else None,
                          "시장": _v[4] if len(_v) > 4 else None}
    except Exception:
        _basic = {}
    이름배열JS += "window.CP_BASIC=" + json.dumps(_basic, ensure_ascii=False) + ";"
    이름배열JS += "window.CP_ACC_DETAIL=" + json.dumps(_accd, ensure_ascii=False) + ";"

    # 강세 상세
    _strd = {}
    try:
        for _mk, _lst in ((data.get("강세레이더") or {}).get("신규") or {}).items():
            for _x in (_lst or []):
                _n = _x.get("종목명")
                if not _n or _n in _strd:
                    continue
                _유 = _x.get("유형") or "강세"
                if "V자" in _유 and _x.get("시가대비저점") is not None:
                    _설 = (f"장중 시가보다 {_x['시가대비저점']:.1f}%까지 밀렸다가 "
                          f"{_x.get('시가대비종가', 0):+.1f}%로 되돌렸어요")
                else:
                    _설 = (f"거래량이 어제보다 {_x.get('배수', 0):.1f}배 · "
                          f"거래대금 {_flow_amt(_x.get('거래대금'))}")
                _strd[_n] = {"유형": _유, "설명": _설,
                             "종가위치": _x.get("종가위치"),
                             "회전율": _x.get("회전율")}
    except Exception:
        _strd = {}
    이름배열JS += "window.CP_STR_DETAIL=" + json.dumps(_strd, ensure_ascii=False) + ";"

    # 종목별 뉴스·공시 — 🆕 2026-08-26 **최근 10거래일**로 확대
    #  ⚠️ HO 지적: "오늘 뉴스만 보여주면 안 된다. 최근 어느 정도 기간을 뒤져서
    #     **왜 돈이 몰리는지**를 알려줘야 한다."
    #  ⚠️ 실제로 매집은 며칠~몇 주에 걸쳐 일어난다. 오늘 뉴스가 없다고
    #     "재료 없음"이라고 하면 사흘 전 계약 공시를 놓친다.
    #  ⚠️ archive에 날짜별 뉴스원본이 그대로 쌓여 있어 **새 수집이 필요 없다.**
    #     날짜를 붙여 보여줘 "언제 나온 얘기인지"를 숨기지 않는다.
    _snews = {}
    try:
        # 🔴 2026-09-01 실측 사고 발견 — 「내 종목 브리핑」의 «요즘 왜
        #    주목받냐면요»가 LG이노텍·SK 등 유명 종목에서도 "기사·공시가
        #    없었어요"만 떴다. 원인: _대상이 **오늘 레이더에 걸린 종목만**
        #    (_accd·_strd·_핫)이었다. 그런데 "내 종목"은 형이 브라우저
        #    localStorage에만 등록하는 거라 **build_html.py 실행 시점엔
        #    서버가 누가 무슨 종목을 등록할지 알 방법이 없다** — 오늘
        #    레이더에 안 걸린 종목이면 애초에 뉴스를 찾아본 적조차 없었다.
        #    → 기업프로필이 있는 종목(사실상 상장사 거의 전체, 3,956개)
        #      전부를 대상에 넣는다. 「내 종목」은 이 중 아무거나 될 수
        #      있으니, 미리 다 찾아둬야 나중에 등록해도 나온다.
        _대상 = set(list(_accd) + list(_strd) + list(_핫) + list(_프로필))
        _본제목 = {n: set() for n in _대상}
        # 🆕 2026-08-26 HO 지시 — "10거래일만 뒤지지 말고, 기간 상관없이
        #    이 종목이 최근에 왜 올랐는지 이슈가 된 기사를 찾아라".
        #  [1차] archive에 쌓인 **전 기간**을 뒤진다(NEWS_ARCHIVE_ALL).
        #        지금은 2주치뿐이지만 매일 자동으로 길어진다.
        #  ⚠️ 진짜 해법은 종목명으로 직접 검색하는 것이다. collect_data.py에
        #     네이버 종목뉴스 수집기를 1단계(로그만)로 붙여뒀다 — 로그 확인 후 켠다.
        for _ymd, _d in archive_days(NEWS_ARCHIVE_ALL):
            _라벨 = f"{str(_ymd)[4:6]}/{str(_ymd)[6:]}"
            for _x in (_d.get("뉴스원본") or []):
                _t = _x.get("제목") or ""
                if not _t:
                    continue
                for _n in _대상:
                    if _n in _t and _t not in _본제목[_n]:
                        _본제목[_n].add(_t)
                        _snews.setdefault(_n, []).append(
                            {"t": _t, "u": _x.get("링크", ""), "k": _라벨})
            for _g in (_d.get("공시") or []):
                _c = _g.get("회사명")
                if _c in _대상:
                    _t = _g.get("공시명", "")
                    if _t and _t not in _본제목[_c]:
                        _본제목[_c].add(_t)
                        _snews.setdefault(_c, []).insert(
                            0, {"t": _t, "u": _g.get("링크", ""), "k": _라벨 + " 공시"})
        # 🔴 2026-08-26 수정 — archive_days()는 **오래된 순**으로 준다.
        #    예전 주석은 "최신부터"라고 잘못 적혀 있었고, 그대로 [:5]를 해서
        #    가장 **오래된** 5건이 카드에 올라가고 있었다. 뒤집어서 자른다.
        # 🆕 2026-08-26 — «이슈»를 고르는 기준을 넣는다.
        #  [WHY] 그냥 최신순으로 자르면 "기관 순매수 상위" 같은 시황 나열 기사가
        #        위로 온다. 정작 «스페이스X 납품» 같은 사건이 밀린다.
        #  [기준] ① 공시가 가장 강하다(사실이 확정된 것)
        #         ② 제목 **맨 앞**에 종목명이 나오면 그 종목이 주인공인 기사다
        #         ③ 시황·수급 나열 기사는 뒤로 민다
        #         같은 점수면 최신 우선.
        _잡음 = ("순매수", "순매도", "상위", "특징주 마감", "코스피 마감",
                "코스닥 마감", "장마감", "개장", "시황")
        for _n in _snews:
            _lst = list(reversed(_snews[_n]))          # 최신순
            _sc = []
            for _i, _it in enumerate(_lst):
                _t = _it.get("t") or ""
                _p = 50 if "공시" in (_it.get("k") or "") else 0
                # 제목 앞쪽에 종목명이 있으면 그 종목이 주인공인 기사다
                _pos = _t.find(_n)
                if 0 <= _pos <= 6:
                    _p += 20
                elif _pos > 20:
                    _p -= 5
                if any(_w in _t for _w in _잡음):
                    _p -= 30
                _p += (len(_lst) - _i) * 0.01          # 동점이면 최신 우선
                _sc.append((_p, _i, _it))
            _sc.sort(key=lambda x: (-x[0], x[1]))
            _snews[_n] = [x[2] for x in _sc][:5]
    except Exception as e:
        print(f"   ⚠️ 종목별 뉴스 수집 실패 — {type(e).__name__}")
        _snews = {}
    이름배열JS += "window.CP_STOCK_NEWS=" + json.dumps(_snews, ensure_ascii=False) + ";"
    이름배열JS += f"window.CP_NEWS_DAYS={NEWS_LOOKBACK};"
    이름배열JS += f"window.CP_BRIEF_DAYS={BRIEF_NEWS_DAYS};"
    # 종목 → 오늘 시장 전체 맥락 (브리핑이 "볼 것"을 만들 때 쓴다)
    _맥락 = {}
    try:
        _fh = load_json("flow_history.json") or []
        _fh = [r for r in _fh if isinstance(r, dict) and r.get("실탄") is not None]
        if _fh:
            _외 = _fs_stat([x["외현"] for x in _fh if x.get("외현") is not None])
            _기 = _fs_stat([x["기관"] for x in _fh if x.get("기관") is not None])
            if _외:
                _맥락["외국인"] = {"방향": _외["dir"], "연속": _외["연속"],
                                 "금액": _flow_amt(_외["v"])}
            if _기:
                _맥락["기관"] = {"방향": _기["dir"], "연속": _기["연속"],
                               "금액": _flow_amt(_기["v"])}
    except Exception:
        _맥락 = {}
    이름배열JS += "window.CP_MARKET=" + json.dumps(_맥락, ensure_ascii=False) + ";"

    # 🆕 2026-08-26 HO 지시 — 「반도체를 샀는데 못 가는 크기의 종목을 들고 있었다」.
    #  [WHY] 섹터가 올라도 그 안에서 대형만 갔으면 중소형을 든 사람은 소외된다.
    #        섹터만 말하면 "자리는 좋았는데 왜 나만"이 설명되지 않는다.
    #        strata_history.json에 층별 등락이 이미 매일 쌓이고 있어 새 수집이 없다.
    #  ⚠️ 층 이름은 P.stocks[nm][2]가 주는 값(대형·중형·소형)과 같아야 매칭된다.
    _층오늘 = {}
    try:
        _sh = load_json("strata_history.json") or []
        if isinstance(_sh, list) and _sh:
            _last = _sh[-1]
            if str(_last.get("날짜") or "") == str(data.get("날짜") or DATE):
                for _k in ("대형", "중형", "소형"):
                    if isinstance(_last.get(_k), (int, float)):
                        _층오늘[_k] = round(float(_last[_k]), 2)
    except Exception as e:
        print(f"   ⚠️ 층별 성적 읽기 실패 — {type(e).__name__}")
        _층오늘 = {}
    이름배열JS += "window.CP_STRATA=" + json.dumps(_층오늘, ensure_ascii=False) + ";"

    # 🆕 종목별 외국인·기관 일별 순매수 — 「기사가 없어도 남는 단서」
    #  ⚠️ 기사가 거의 안 나오는 중소형주일수록 이게 유일한 재료다.
    #  ⚠️ 쌓이는 만큼 그대로 쓴다(오늘은 1일치, 60일 뒤엔 60일치).
    #     모자란 날을 0으로 채우지 않는다 — 없는 날은 없는 것이다.
    _종목수급 = {}
    try:
        _sfh = load_json("stock_flow_history.json") or {}
        _날들 = [d for d in (_sfh.get("날짜들") or []) if str(d) <= str(DATE)][-10:]
        for _nm, _rec in (_sfh.get("종목") or {}).items():
            _seq = []
            for _d in _날들:
                _v = _rec.get(_d)
                if isinstance(_v, list) and len(_v) >= 2:
                    _seq.append([f"{str(_d)[4:6]}/{str(_d)[6:]}",
                                 round(float(_v[0] or 0), 1), round(float(_v[1] or 0), 1)])
            if _seq:
                _종목수급[_nm] = _seq
    except Exception as e:
        print(f"   ⚠️ 종목별 수급 읽기 실패 — {type(e).__name__}")
        _종목수급 = {}
    이름배열JS += "window.CP_SFLOW=" + json.dumps(_종목수급, ensure_ascii=False) + ";"
    print(f"   💰 종목별 수급 {len(_종목수급)}종목 (쌓인 거래일 {len(_날들) if '_날들' in dir() else 0}일)")

    # 🆕 레이더에 잡힌 이력 — 「이번이 3번째」는 우리만 아는 정보다
    #  ⚠️ 오늘은 빼고 «과거에 몇 번»만 센다. 오늘 잡힌 사실은 이미 위에서 말한다.
    _레이더이력 = {}
    try:
        for _ymd, _dd in archive_days(60):
            if str(_ymd) >= str(DATE):
                continue
            _lab = f"{str(_ymd)[4:6]}/{str(_ymd)[6:]}"
            # ⚠️ 두 레이더의 저장 구조가 다르다.
            #    매집레이더 = {"종목":[...]} · 강세레이더 = {"신규":{"코스피":[...],"코스닥":[...]}}
            _acc = (_dd.get("매집레이더") or {})
            for _s in (_acc.get("종목") or []):
                _n = (_s or {}).get("종목명")
                if _n:
                    _레이더이력.setdefault(_n, []).append([_lab, "매집"])
            _신규 = ((_dd.get("강세레이더") or {}).get("신규") or {})
            for _mk in ("코스피", "코스닥"):
                for _s in (_신규.get(_mk) or []):
                    _n = (_s or {}).get("종목명")
                    if _n:
                        _레이더이력.setdefault(_n, []).append([_lab, "강세"])
        for _n in _레이더이력:
            _레이더이력[_n] = _레이더이력[_n][-6:]      # 최근 6회만
    except Exception as e:
        print(f"   ⚠️ 레이더 이력 읽기 실패 — {type(e).__name__}")
        _레이더이력 = {}
    이름배열JS += "window.CP_RHIST=" + json.dumps(_레이더이력, ensure_ascii=False) + ";"
    print(f"   📡 레이더 이력 {len(_레이더이력)}종목")

    # 🆕 2026-08-29 HO 지시 — 「내 종목 브리핑」에 종목별 예보 성적을 내려준다.
    #    ⚠️ 승리만 골라 보여주지 않는다 — 손실도 있는 그대로 승률에 반영한다
    #    (원칙 3 + 「포착 그 후」의 생존 편향 금지 원칙, 유료챕터_기획.md 참고).
    #    D5를 기준으로 잡는다 — 표본이 가장 많이 찬 구간이라(120일 추적 중
    #    가장 먼저 도달하는 스냅샷) 승률이 가장 안정적으로 계산된다.
    # 🆕 2026-08-29 (2차) — 두 가지를 더한다(승패 자체는 그대로 유지).
    #    ① 표본 3회 미만은 아예 안 보여준다 — 1~2회짜리 숫자는 노이즈를
    #       "성적"으로 오해하게 만든다(「시장 국면 내비」의 "표본 5회 미만
    #       은 통계 문장 생략" 원칙과 같은 이유).
    #    ② "최고 성적"을 같이 보여준다 — 이건 숨기는 게 아니라 **추가**하는
    #       것이라 정직성 문제가 없다. 승패는 그대로 다 보이는 채로,
    #       "이 종목으로 가장 잘 맞았을 땐 이랬다"는 참고 정보를 더한다.
    _캡최소표본 = 3
    _캡통계 = {}
    try:
        _캡로그 = load_json("stock_capture_log.json") or {}
        for _n, _캡들 in _캡로그.items():
            _d5들 = [c["구간성적"]["D5"] for c in _캡들
                    if isinstance(c.get("구간성적"), dict)
                    and isinstance(c["구간성적"].get("D5"), (int, float))]
            if len(_d5들) < _캡최소표본:
                continue
            _승 = sum(1 for v in _d5들 if v > 0)
            _캡통계[_n] = {
                "횟수": len(_d5들),
                "평균": round(sum(_d5들) / len(_d5들), 2),
                "최고": round(max(_d5들), 2),
                "승": _승,
                "패": len(_d5들) - _승,
            }
    except Exception as e:
        print(f"   ⚠️ 종목별 예보 성적 읽기 실패 — {type(e).__name__}")
        _캡통계 = {}
    이름배열JS += "window.CP_CAPSTAT=" + json.dumps(_캡통계, ensure_ascii=False) + ";"
    print(f"   🎯 종목별 예보 성적 {len(_캡통계)}종목 "
          f"(D+5 기준, 표본 {_캡최소표본}회 미만 제외, 승패 전부 포함)")
    보유일 = len(payload["days"])

    # 오늘의 뉴스·공시 (브라우저가 종목명으로 매칭한다)
    # ⚠️ 요약문(본문 앞부분)까지 넘긴다(2026-08-20).
    #    제목에만 종목명이 있는 기사는 극소수다. 본문에서 언급되는 경우가 훨씬 많아
    #    제목만 보면 "오늘 뉴스가 없습니다"가 계속 나온다.
    # 🆕 2026-08-26 HO 지시 — 브리핑 뉴스를 **최근 5거래일**로 넓힌다.
    #  ⚠️ 오늘치만 보면 대부분의 종목이 매일 "재료 없음"으로 끝난다. 실제로는
    #     사흘 전 계약 공시가 오늘 주가를 움직이는 일이 흔하다.
    #  ⚠️ 제목·본문 어디에 종목명이 있든 잡는다(매칭은 브라우저가 한다).
    #  ⚠️ 여러 매체가 같은 사건을 쓰면 **한 건만** 남긴다(_news_key).
    #     남기는 쪽은 **더 최근 것** — 그래서 최신부터 훑는다.
    #  ⚠️ 날짜(k)를 반드시 함께 넘긴다. 안 붙이면 사흘 전 기사를 오늘 일로 읽는다.
    뉴스, _본지문 = [], set()
    try:
        for _ymd, _d in reversed(archive_days(BRIEF_NEWS_DAYS)):
            _lab = f"{int(str(_ymd)[4:6])}/{int(str(_ymd)[6:])}"
            _오늘인가 = 1 if str(_ymd) == str(DATE) else 0
            for n in (_d.get("뉴스원본") or []):
                _t = n.get("제목", "")
                if not _t:
                    continue
                _k = _news_key(_t)
                if not _k or _k in _본지문:
                    continue
                _본지문.add(_k)
                뉴스.append({"t": _t, "u": n.get("링크", ""),
                            "d": (n.get("요약") or "")[:400],
                            "s": n.get("출처", ""),
                            "y": int(_ymd),   # 🆕 2026-08-29 — 정렬용 실제 날짜(정수)
                                              #    'k'는 "8/24" 같은 표시용이라 정렬에 못 쓴다.
                            "k": _lab, "o": _오늘인가})
    except Exception as e:
        print(f"   ⚠️ 브리핑 뉴스 수집 실패 — {type(e).__name__}: {e}")
        뉴스 = [{"t": n.get("제목", ""), "u": n.get("링크", ""),
                "d": (n.get("요약") or "")[:400], "s": n.get("출처", ""),
                "k": "", "o": 1}
               for n in (data.get("뉴스원본") or []) if n.get("제목")]
    print(f"   📰 브리핑 뉴스 {len(뉴스)}건 (최근 {BRIEF_NEWS_DAYS}거래일, 중복 제거 후)")
    공시원 = data.get("공시")
    공시목록 = 공시원.get("목록") if isinstance(공시원, dict) else (공시원 or [])
    공시 = [{"c": g.get("회사명", ""), "t": (g.get("공시명") or "").strip(),
            "s": g.get("별점"), "u": g.get("링크", "")}
           for g in (공시목록 or []) if g.get("회사명")]

    옵션 = ""   # ⚠️ datalist 폐기 — 자체 제안창(msSug)이 대신한다
    PAY = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    NEWS = json.dumps(뉴스, ensure_ascii=False, separators=(",", ":"))
    DISC = json.dumps(공시, ensure_ascii=False, separators=(",", ":"))

    JS = ("""<script>
(function(){
 window.CP_PAINT=window.CP_PAINT||[];
 /* 🆕 2026-08-26 — 조사(助詞) 자동 선택. 파이썬의 _josa()와 같은 규칙이다.
    [WHY] «반도체이 오늘 +3.9%», «소속 구역 반도체이» 처럼 받침 없는 이름 뒤에
          '이'가 그대로 붙어 나갔다. 섹터명·종목명은 매일 바뀌므로 코드로 막는다. */
 function _josa(w,pair){
  /* ⚠️ «으로/로»처럼 두 글자짜리 조사도 있다. 문자열을 글자 단위로 쪼개면
     «으»만 나와 문장이 깨진다. → 두 글자 이상이면 배열로 넘긴다. */
  var A = (pair==='으로') ? ['으로','로'] : [pair[0], pair[1]];
  var t=String(w||'').replace(/<[^>]*>/g,'').trim();
  if(!t) return A[1];
  var ch=t.charCodeAt(t.length-1);
  if(ch>=0xAC00&&ch<=0xD7A3) return ((ch-0xAC00)%28)?A[0]:A[1];
  var c=t[t.length-1];
  if(c>='0'&&c<='9') return ('0136780'.indexOf(c)>=0)?A[0]:A[1];
  return A[1];
 }
 var K='chartpro_mystocks', MAX=""" + str(MYSTOCK_MAX) + """;
 var P=""" + PAY + """, NEWS=""" + NEWS + """, DISC=""" + DISC + """;
 // ⚠️ 기본은 **당일**. 다른 코너와 같은 창 구성·같은 이름으로 맞춘다(2026-08-21).
 var WINDOWS=[[1,'당일'],[5,'5일'],[20,'20일'],[60,'60일']], curW=1;
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
  idx=idx.slice(-n);
  /* 🆕 2026-08-24 HO 지적 — 당일 탭에 등락률이 안 나오던 버그.
     [원인] "2일 미만이면 통계가 안 된다"는 방어가 **당일 탭까지 같이 막고** 있었다.
            당일은 1일이 정답인데 1개라서 '축적 중'으로 빠졌다.
     [고침] 필요한 최소 일수를 창 크기에 맞춘다 — 당일은 1일, 나머지는 2일. */
  var 최소 = (n<=1) ? 1 : 2;
  if(idx.length<최소) return {short:true,have:idx.length};
  var tc=1,mc=1,w=0;
  idx.forEach(function(i){tc*=(1+r[i]/100); mc*=(1+P.mkt[i]/100); if(r[i]>P.mkt[i])w++;});
  return {ex:(tc-mc)*100, ret:(tc-1)*100, win:w, tot:idx.length};
 }

 /* 🆕 2026-08-26 HO 지시 — 등록 목록에 **체크박스**를 넣고, 체크한 종목끼리만
    그래프·평균에 넣는다(섹터 성적표와 같은 방식).
    [WHY] 10종목을 다 등록하면 선이 10개라 아무것도 안 보인다. 오늘 궁금한
          2~3개만 켜고 시장과 비교할 수 있어야 이 코너가 쓸모 있어진다.
    ⚠️ 선택 상태는 이 기기에만 저장한다(서버로 안 보낸다). 등록 목록과 같은 원칙.
    ⚠️ 등록은 했는데 체크가 하나도 없으면 **전부 켠 것으로 본다** — 새로 등록한
       사람이 빈 그래프를 보고 고장으로 오해하는 걸 막는다. */
 var SK='chartpro_mysel';
 function getSel(){
  try{var v=JSON.parse(localStorage.getItem(SK)||'[]');return Array.isArray(v)?v:[];}
  catch(e){return [];}
 }
 function setSel(v){try{localStorage.setItem(SK,JSON.stringify(v));}catch(e){}}
 /* 실제로 그래프·브리핑에 넣을 종목 — 체크된 것만. 하나도 없으면 전부.
    🔴 2026-08-29 HO 지적 — 브리핑 순서가 등록 순서(위 ▲▼로 바꾸는 그 순서)를
    안 따르고 있었다.
    [원인] getSel()은 «체크박스를 누른 순서»대로 쌓인다(msToggleSel이 push
    하는 순서). 등록 순서(my)와 체크 순서가 다르면 — 특히 체크를 껐다 켰다
    반복하면 — 두 순서가 어긋난다.
    [고침] getSel()의 결과는 «어느 종목이 켜져 있나»(멤버십)만 쓰고,
    실제 순서는 항상 my(등록 순서)를 기준으로 다시 줄 세운다. */
 function selected(){
  var my=get(), selSet={};
  getSel().forEach(function(n){ if(my.indexOf(n)>=0) selSet[n]=1; });
  var sel=my.filter(function(n){ return selSet[n]; });
  return sel.length?sel:my.slice();
 }
 /* 🔴 저장된 선택이 비어 있으면 «전부 켬»을 뜻한다. 그 상태에서 하나를 끄려면
    빈 배열에서 빼는 게 아니라 **지금 켜져 있는 목록(selected())에서 빼야** 한다.
    빈 배열을 그대로 조작해 «끄기»가 «켜기»로 뒤집히는 버그가 있었다. */
 window.msToggleSel=function(nm){
  var cur=selected(), i=cur.indexOf(nm);
  if(i>=0) cur.splice(i,1); else cur.push(nm);
  /* 전부 끄면 «전부 켬»과 구분이 안 된다 — 마지막 하나는 못 끄게 한다.
     ⚠️ 체크박스는 이미 시각적으로 꺼진 상태라, 그냥 return하면 화면과
        실제 상태가 어긋난다. 반드시 다시 그려 체크를 되돌린다. */
  if(!cur.length){ render(); return; }
  setSel(cur); render();
 };
 /* 🆕 전체 «해제»도 지원한다. 다만 하나도 안 켜진 상태는 «전부 켬»과
    구분이 안 되므로, 해제하면 **맨 위 한 종목만** 남긴다.
    빈 그래프를 보여주면 고장으로 오해한다. */
 window.msSelAll=function(on){
  var my=get();
  setSel(on===false ? my.slice(0,1) : []);
  render();
 };
 function render(){
  var my=get(), box=document.getElementById('ms-list');
  if(!my.length){box.innerHTML='<p style="margin:14px 0;font-size:12px;color:#7d848f;'+
   'text-align:center">위에 종목을 입력하면 구역과 시장 대비 성적을 보여드립니다</p>';
   document.getElementById('ms-sum').innerHTML='';
   var _hd0=document.getElementById('ms-selbar'); if(_hd0)_hd0.innerHTML='';
   return;}
  var html='', exs=[], _sel=selected();
  my.forEach(function(nm,_mi){
   var m=P.stocks[nm]||[[],null,null,null], c=calc(nm,curW);
   var zones=(m[0]||[]).map(function(z){return '<span style="display:inline-block;'+
     'font-size:11px;padding:2px 7px;margin:0 4px 4px 0;border-radius:99px;'+
     'background:#22303f;color:#8fd0e8">'+z+'</span>';}).join('')||
     '<span style="font-size:11px;color:#6f7784">지도 미분류</span>';
   var right='';
   if(c&&!c.short){
    /* 평균도 체크된 것만 — 그래프와 숫자가 다른 집합이면 서로를 못 믿는다. */
    if(_sel.indexOf(nm)>=0) exs.push(c.ex);
    var col=c.ex>=0?'#ff6b4a':'#5b9bff';
    /* 🆕 2026-08-24 HO 지적 — "당일 수익률이 다 이상하다".
       [원인] 숫자는 맞았다. **순서**가 문제였다. 큰 글씨가 초과수익(%p)이라
              증권앱에서 -8.7%를 보고 온 사람에게 -5.6%p가 먼저 보였다.
       [고침] 당일 탭에서는 **등락률을 큰 글씨**로 올린다. 오늘 내 계좌에
              찍힌 숫자가 먼저 보여야 한다. 초과수익은 그 아래 보조로.
       ⚠️ 5·20·60일 탭은 그대로 둔다 — 누적 구간에서는 "시장을 이겼나"가
          주인공이 맞고, 그게 이 코너의 존재 이유다. */
    var _주 = (curW<=1) ? fmt(c.ret)+'%'  : fmt(c.ex)+'%p';
    var _보 = (curW<=1) ? '시장 대비 '+fmt(c.ex)+'%p' : fmt(c.ret)+'%';
    var _주색 = (curW<=1) ? (c.ret>=0?'#ff6b4a':'#5b9bff') : col;
    right='<div style="text-align:right;flex:none;width:82px">'+
     '<div style="font-size:15px;font-weight:800;color:'+_주색+'">'+_주+'</div>'+
     '<div style="font-size:11px;color:#7d848f">'+_보+'</div>'+
     /* 🆕 2026-08-25 HO 지시 — 당일 탭의 '시장 상회/하회' 글자 제거.
        [WHY] 바로 위 줄이 이미 '시장 대비 -5.6%p'라고 말한다.
              부호만 봐도 아는 걸 한 줄 더 쓰면 칸만 좁아진다. */
     (c.tot<=1 ? '' : '<div style="font-size:10px;color:#6f7784">'+
        c.win+'/'+c.tot+'승</div>')+
     '</div>';
   }else{right='<div style="text-align:right;flex:none;width:66px;font-size:11px;'+
     'color:#6f7784">축적 중</div>';}
   var tags='';
   NEWS.forEach(function(n){if(n.t.indexOf(nm)>=0)tags+='<a href="'+n.u+'" target="_blank" '+
    'style="display:block;font-size:10.5px;color:#8fb4ee;margin-top:3px;text-decoration:none">'+
    '📰 '+n.t+'</a>';});
   DISC.forEach(function(g){if(g.c===nm)tags+='<a href="'+g.u+'" target="_blank" '+
    'style="display:block;font-size:10.5px;color:#e0c060;margin-top:3px;text-decoration:none">'+
    '📄 '+g.t+(g.s?' ('+'★'.repeat(g.s)+')':'')+'</a>';});
   /* 🆕 2026-08-25 — 종목명을 누르면 기업분석이 아래로 펼쳐진다. */
   var _on=selected().indexOf(nm)>=0;
   /* 🆕 2026-08-26 HO 지시 — 섹터 성적표(.sb-ck)와 **크기·디자인을 통일**한다.
      같은 리포트 안에서 같은 역할을 하는 조작이 서로 다르게 생기면
      독자는 두 번 배워야 한다. 14×14px · accent-color 방식을 그대로 쓴다.
      ⚠️ render()가 매번 다시 그리므로 checked를 HTML에 직접 박는다. */
   var _cb='<input type="checkbox" class="ms-ck"'+(_on?' checked':'')+
    ' onchange="msToggleSel(\\''+nm+'\\')"'+
    ' style="flex:none;width:14px;height:14px;margin-top:3px;'+
    'accent-color:#8fd0e8;cursor:pointer">';
   html+='<div style="padding:9px 8px;border-bottom:1px solid #1b212c;'+
    (_on?'':'opacity:.55')+'">'+
    '<div style="display:flex;align-items:flex-start;gap:8px">'+_cb+
    '<div style="flex:1;min-width:0">'+
    /* 🆕 2026-08-29 HO 지시 — 목록 글자가 전체적으로 작다. 13 → 14.5 */
    '<div style="font-size:14.5px;font-weight:800;color:#e8eaee">'+
    /* 🆕 2026-08-25 — 등록 목록에서는 뺐다(브리핑에만 둔다). 두 곳에 있으면
       같은 카드가 화면에 두 번 열려 중복이 된다. */
    nm+
    /* 🆕 2026-08-29 HO 지시 — 순서 바꾸기 ▲▼.
       ⚠️ 맨 위/맨 아래에서는 눌러도 소용없으므로 흐리게(0.25) 표시해
          "왜 안 되지"를 미리 막는다. */
    '<span onclick="msMove(\\''+nm+'\\',-1)" title="위로" style="color:#8fd0e8;'+
    'font-size:12px;margin-left:8px;cursor:pointer;opacity:'+(_mi===0?'.25':'1')+
    '">▲</span>'+
    '<span onclick="msMove(\\''+nm+'\\',1)" title="아래로" style="color:#8fd0e8;'+
    'font-size:12px;margin-left:4px;cursor:pointer;opacity:'+
    (_mi===my.length-1?'.25':'1')+'">▼</span>'+
    '<span onclick="msDel(\\''+nm+'\\')" style="color:#6f7784;font-size:11px;'+
    'margin-left:8px;cursor:pointer">✕</span></div>'+
    '<div style="margin-top:4px">'+zones+'</div>'+
    (m[1]?'<div style="font-size:10.5px;color:#6f7784;margin-top:3px">'+
      (m[3]||'')+' · 시총 '+m[1]+'위 ('+(m[2]||'')+')</div>':'')+
    /* 🆕 2026-08-25 HO 지시 — 등록 목록에서 기사 링크 제거.
       [WHY] 바로 아래 「내 종목 브리핑」이 같은 뉴스를 요약까지 붙여 보여준다.
             등록 목록은 '지우기·성적' 자리라 링크가 있으면 칸만 길어진다. */
    '</div>'+right+'</div></div>';
  });
  /* 🆕 그래프·브리핑·평균은 **체크된 종목만** 대상으로 한다. */
  var pick=selected();
  box.innerHTML=html; drawChart(pick); drawBrief(pick); if(window.cpFire)cpFire();
  /* 몇 개를 보고 있는지 항상 알려준다. 안 그러면 "왜 선이 줄었지?"가 된다. */
  var _hd=document.getElementById('ms-selbar');
  if(_hd){
   var _allOn=(_sel.length===my.length);
   _hd.innerHTML = my.length<2 ? '' :
    ('<label style="display:flex;align-items:center;gap:6px;font-size:11px;'+
     'color:#8b93a0;cursor:pointer">'+
     '<input type="checkbox" id="ms-all"'+(_allOn?' checked':'')+
     ' onchange="msSelAll(this.checked)"'+
     ' style="width:14px;height:14px;accent-color:#f0c65a;cursor:pointer">'+
     '전체 선택 / 해제</label>'+
     '<span style="font-size:10.5px;color:#7d848f">그래프에 '+
     '<b style="color:#8fd0e8">'+_sel.length+'개</b> / 등록 '+my.length+'개</span>'+
     '');
  }
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
 var _scbSeq=1;
 function drawBrief(my){
  var host=document.getElementById('ms-brief'); if(!host) return;
  if(!my.length){host.innerHTML='<p style="margin:14px 0;font-size:12px;color:#7d848f;'+
   'text-align:center">위 <b>내 관심종목 등록</b>에 종목을 넣으면 여기에 브리핑이 쌓입니다</p>';
   return;}
  var out='';
  my.forEach(function(nm){
   var m=P.stocks[nm]||[[],null,null,null], c=calc(nm,20);
   // ⚠️ 구역이 비면 아무것도 안 나와 "섹터가 왜 안 보이지"가 된다(2026-08-20).
   //    구역이 없으면 **오늘 주도 테마 중 이 종목이 든 것**을 대신 보여주고,
   //    그것도 없으면 '지도 미분류'라고 솔직히 적는다.
   var zlist=(m[0]||[]).slice();
   if(!zlist.length && window.CP_STOCK_THEME && window.CP_STOCK_THEME[nm])
     zlist=[window.CP_STOCK_THEME[nm]];
   var zones=zlist.length
     ? zlist.map(function(z){return '<span style="display:inline-block;'+
       'font-size:11px;padding:2px 7px;margin:0 4px 4px 0;border-radius:99px;'+
       'background:#22303f;color:#8fd0e8">'+z+'</span>';}).join('')
     : '<span style="display:inline-block;font-size:10px;padding:2px 7px;'+
       'border-radius:99px;background:#1a2029;color:#6f7784">지도 미분류</span>';
   /* 🆕 2026-08-24 HO 지시 — 섹터 배지 옆에 «토론방 가기».
      [WHY] 재료가 없는 날에도 사람들은 "남들은 뭐라 하나"가 궁금하다.
            리포트가 답을 못 주는 자리에서 **답이 있는 곳으로 보내주는 것**도 서비스다.
      ⚠️ 종목코드가 있어야 링크가 만들어진다. 없으면 배지를 아예 안 붙인다
         (죽은 링크를 놓느니 없는 게 낫다). P.stocks[nm][3]이 코드 자리다. */
   /* 🆕 2026-08-26 HO 지시 — 섹터 배지 옆에 **시총 규모(대형·중형·소형)**를 붙인다.
      [WHY] 같은 섹터를 사도 규모에 따라 하루가 갈린다. 아래 📏 블록이 그 얘기를
            하는데, 정작 «내 종목이 어느 쪽인지»가 위에 없어 연결이 안 됐다.
      ⚠️ P.stocks[nm][2]가 층 자리다. 없으면 배지를 안 붙인다(빈칸이 거짓말보다 낫다). */
   var _층=(m&&m[2])?String(m[2]):'';
   /* 🆕 2026-08-26 HO 지시 — 규모는 «참고 정보»라 눈에 덜 띄어도 된다.
      알약을 빼고 흰 글자로만 둔다(섹터 배지가 주인공 자리를 지키게). */
   if(_층) zones+='<span style="display:inline-block;font-size:11px;'+
     'margin:0 4px 4px 0;color:#c9ced6">'+_층+'주</span>';
   var _cd=(m&&m[4])?String(m[4]):'';
   if(_cd) zones+='<a href="https://finance.naver.com/item/board.naver?code='+_cd+'" '+
     'target="_blank" rel="noopener" style="display:inline-block;font-size:10px;'+
     'padding:2px 8px;margin:0 4px 4px 0;border-radius:99px;background:#2a2233;'+
     'color:#c4a8f7;text-decoration:none;font-weight:700;font-size:11px">💬 실시간 토론방</a>';
   var items='', n1=0, n2=0;
   // ⚠️ 제목 + **본문(요약)** 둘 다에서 종목명을 찾는다(2026-08-20).
   //    제목 매칭은 우선순위를 높여 위로 올리고, 많으면 상위 5건만 보여준다.
   // 🆕 2026-08-29 HO 지시 — 기간을 5→20거래일로 늘리는 대신 두 가지를 더한다.
   //    ① **최근 위주 정렬** — 예전엔 제목매칭(w=2)이 항상 위로 와서, 옛날
   //       제목매칭 기사가 최근 본문매칭 기사보다 위에 뜰 수 있었다.
   //       이제 **날짜(y)를 우선**으로 정렬하고, 같은 날이면 제목매칭을 우선한다.
   //    ② **종목별 중복 제거** — 서로 다른 매체가 같은 사건을 다르게 쓰면
   //       (_news_key의 24자 지문으로는 못 잡는 경우) 20일치를 보면 한 종목에
   //       비슷한 기사가 여러 개 뜬다. 여기서 **더 느슨한 지문**(12자)으로
   //       한 번 더 걸러, 같은 사건이면 **가장 최근 것 하나만** 남긴다.
   var hits=[];
   NEWS.forEach(function(n){
    var inT=(n.t||'').indexOf(nm)>=0, inD=((n.d||'').indexOf(nm)>=0);
    if(inT||inD) hits.push({n:n, w:(inT?2:1)});
   });
   hits.sort(function(a,b){ return (b.n.y-a.n.y) || (b.w-a.w); });
   // 종목 안에서 «같은 사건» 판정용 느슨한 지문 — 대괄호 머리말·기호 제거 후 앞 12자.
   var _fp=function(t){
    return String(t||'').replace(/\[[^\]]*\]/g,'').replace(/[^0-9A-Za-z가-힣]/g,'').slice(0,12);
   };
   var _seen={}, _hits2=[];
   hits.forEach(function(h){
    var k=_fp(h.n.t);
    if(k && _seen[k]) return;         // 이미 더 최근 것(정렬상 앞선 것)을 남겼다
    if(k) _seen[k]=1;
    _hits2.push(h);
   });
   hits=_hits2;
   n1=hits.length;
   hits.slice(0,5).forEach(function(h){
    var n=h.n;
    /* 🆕 2026-08-26 — 날짜를 반드시 붙인다. 20거래일치를 섞어 보여주므로
       안 붙이면 며칠 전 기사를 오늘 일로 오해한다. */
    var 날=n.k?'<span style="font-size:9.5px;color:#e0c060;font-weight:700">'+
      (n.o?'오늘':n.k)+'</span> ':'';
    items+='<div style="display:flex;gap:6px;margin-top:4px"><span style="flex:none">📰</span>'+
     '<div>'+날+'<a href="'+n.u+'" target="_blank" style="font-size:12px;color:#8fb4ee;'+
     'line-height:1.5;text-decoration:none">'+n.t+'</a>'+
     (h.w===1?'<span style="font-size:9.5px;color:#6f7784"> · 본문 언급</span>':'')+
     (n.s?'<span style="font-size:9.5px;color:#6f7784"> · '+n.s+'</span>':'')+
     '</div></div>';
   });
   if(n1>5) items+='<p style="margin:4px 0 0;font-size:10px;color:#6f7784">'+
     '외 '+(n1-5)+'건 더 있습니다(중복 제외) · 최근 '+(window.CP_BRIEF_DAYS||20)+'거래일</p>';
   DISC.forEach(function(g){if(g.c===nm){n2++;
    items+='<div style="display:flex;gap:6px;margin-top:4px"><span style="flex:none">📄</span>'+
     '<a href="'+g.u+'" target="_blank" style="font-size:12px;color:#e0c060;'+
     'line-height:1.5;text-decoration:none">'+g.t+(g.s?' '+'★'.repeat(g.s):'')+'</a></div>';}});
   // ⚠️ 조용한 날에도 할 말은 있다 (2026-08-18).
   //    뉴스도 공시도 없으면 '없었습니다'로 끝내지 말고,
   //    **그 종목이 속한 구역이 오늘 어땠는지**를 대신 알려준다.
   //    개별 재료가 없는 날의 주가는 대개 섹터를 따라가기 때문이다.
   /* 🆕 2026-08-24 HO 지시 — 재료가 없으면 «오늘 뉴스, 공시 없음»만 쓴다.
      [WHY] 예전엔 없는 날에도 소속 섹터 등락을 덧붙여 말을 늘렸다. 그런데
            바로 아래 '왜 올랐나' 문장이 이미 섹터를 말하고 있어 중복이었고,
            무엇보다 **없는 걸 있는 것처럼 채우는 모양**이 됐다.
            없으면 없다고 짧게 끝내는 게 이 리포트의 원칙에 맞다. */
   if(!items){
    items='<p style=\\"margin:4px 0 0;font-size:11px;color:#6f7784\\">'+
      '뉴스, 공시, 일정 없음</p>';
   }
   // ⚠️ 가장 먼저 "왜 움직였나"를 **하나로 단정**한다(2026-08-20 지시).
   //    재료를 나열만 하면 "그래서 뭐 때문인데?"가 남는다.
   //    우선순위: 공시 > 제목 뉴스 > 강세/매집 레이더 > 섹터 > 시장
   var 원인='';
   (function(){
    var d0=(c&&c.today!==null&&c.today!==undefined)?c.today:null;
    var 방향=(d0===null)?'움직였나?':(d0>=0?'올랐나?':'내렸나?');
    var 화살=(d0===null)?'':(d0>=0?'📈':'📉');
    var 왜='';
    /* 🆕 2026-08-26 — 기사에서 그 종목이 나오는 **한 문장**을 그대로 뽑는다.
       [WHY] 제목만 보면 "왜 유력한지"가 안 보인다. 근거를 눈앞에 둔다.
       ⚠️ 지어내지 않는다 — 원문에 있는 문장을 자를 뿐이다. */
    if(n2>0) 왜='오늘 나온 <b>공시</b>가 직접적인 이유로 보입니다';
    else if(hits.length&&hits[0].w===2){
     var h0=hits[0].n;
     왜=(h0.k?'['+(h0.o?'오늘':h0.k)+'] ':'')+
        '<b>'+h0.t.slice(0,26)+'</b> 뉴스가 가장 유력합니다';
    }
    else if(window.CP_HOT&&window.CP_HOT[nm]) 왜='오늘 <b>'+window.CP_HOT[nm]+'</b>에 잡혔습니다 — 큰손이 붙은 자리입니다';
    else if(hits.length){
     var h1=hits[0].n;
     왜=(h1.k?'['+(h1.o?'오늘':h1.k)+'] ':'')+'관련 <b>뉴스 본문</b>에 언급됐습니다';
    }
    /* 🆕 2026-08-26 HO 지시 — «특별한 재료없이 시장 흐름을 따라감» 삭제.
       [WHY] 매일 같은 문장이 반복돼 정보가 아니라 소음이 됐다. 재료가 없으면
             위 «뉴스, 공시, 일정 없음»이 이미 그 사실을 말한다.
             원칙 14 — 없으면 없다고 짧게 끝낸다. 여기선 아예 말하지 않는다. */
    // 원인은 별도 문단이 아니라 '오늘 분석' 안 첫 문장으로 들어간다(2026-08-21).
    // 분석과 원인이 따로 있으면 같은 얘기를 두 번 읽게 된다.
    /* 🆕 2026-08-25 HO 지시 — "왜 움직였나?" 라벨 삭제.
       [WHY] 코너 제목이 이미 '오늘 분석'이다. 그 아래 다시 질문을 던지면
             글이 한 겹 늘어날 뿐 정보가 늘지 않는다. 답만 남긴다. */
    /* 왜가 비면(재료 없는 날) 원인 문장 자체를 만들지 않는다. */
    /* 왜가 비면(재료 없는 날) 원인 문장 자체를 만들지 않는다.
       ⚠️ 핵심구절은 아래 «📰 _본»(_gist)이 이미 보여준다. 여기서 또 쓰면
          같은 문장을 두 번 읽게 된다(원칙 4). 여기는 날짜 + 제목까지만. */
    원인=왜?('<b>'+화살+'</b> '+왜+'. '):'';
   })();
   var 분석='';
   /* 🆕 2026-08-25 HO 지시 — 승패·구간 문구를 **표본이 충분할 때만** 낸다.
      [WHY] "최근 5거래일 2승 3패(40%), 시장 대비 +0.4%p입니다. 아직 5일치라
            승패는 참고만 해주세요." — 이건 정보가 아니라 변명이다.
            표본이 모자라면 그 얘기를 아예 꺼내지 않는 게 맞다.
      [규칙] 20거래일이 다 차기 전에는 승패를 말하지 않는다.
             당일 탭은 승패 대상이 아니므로 등락률만 짧게. */
   if(c&&!c.short){
    if(c.tot<=1){
     분석='오늘 '+fmt(c.ret)+'%, 시장 대비 '+fmt(c.ex)+'%p입니다. ';
    } else if(c.tot>=20){
     var 승률=c.win/c.tot*100;
     분석 = multiSpan(nm) + '최근 20거래일 '+c.win+'승 '+(c.tot-c.win)+'패('+
      승률.toFixed(0)+'%), 시장 대비 '+fmt(c.ex)+'%p입니다. ';
     분석+= (c.ex>=0
       ? (승률>=60?'꾸준히 시장을 이기고 있습니다.':'며칠에 몰아서 번 구간이라 변동이 큽니다.')
       : (승률<=30?'자리 자체가 불리했습니다 — 종목 선택 문제로 보기 어렵습니다.'
                  :'시장에 조금 뒤처지는 흐름입니다.'));
    }
    /* 20일 미만이면 승패를 말하지 않는다 — 아래 '오늘 뉴스/공시' 안내만 나간다.
       ⚠️ 여기서 if 블록을 닫으면 안 된다. 아래 코드가 전부 이 블록 안이고,
          닫으면 맨 끝의 }else{...}가 고아가 되어 **JS 전체가 죽는다.**
          (2026-08-25에 실제로 냈던 실수 — 화면이 통째로 안 그려졌다) */
    /* 🆕 2026-08-25 HO 지시 — 뉴스가 있으면 **내용을 3~4줄로** 보여준다.
       [WHY] 제목만 나열하면 눌러봐야 안다. 무슨 얘긴지 여기서 끝나야 한다.
       ⚠️ 관심종목은 **브라우저에만 있어서** Claude가 요약해줄 수 없다
          (누가 뭘 등록했는지 서버가 모른다). 그래서 RSS가 준 기사 요약문을
          그대로 다듬어 쓴다. **지어내지 않는다** — 요약문이 없으면 안 쓴다.
       ⚠️ 제목과 거의 같은 요약문은 버린다(같은 말 두 번 금지). */
    if(n2) 분석+=' 오늘 공시가 있으니 내용을 확인해 보세요.';
    if(hits.length){
     var _본 = '';
     /* ⚠️ **제목에 종목명이 들어간 기사만** 쓴다(w===2).
        본문 언급 기사까지 허용했더니 삼성전자 밑에 «삼성물산» 기사 요약이
        붙었다. 그 종목 얘기가 아닌 글을 그 종목 분석으로 보여주면 안 된다. */
     /* ⚠️ **바로 위에서 "가장 유력합니다"라고 지목한 그 기사**의 요약만 쓴다.
        다른 기사로 넘어가면 지목한 기사와 요약이 어긋나 독자가 헷갈린다.
        실제로 삼성전자 밑에 «삼성물산» 얘기가 붙는 일이 있었다.
        그 기사에 쓸 만한 요약이 없으면 **아무것도 안 쓴다.** */
     var _h0=hits[0];
     if(_h0 && _h0.w===2){
      var _d=(_h0.n.d||'').replace(/\s+/g,' ').trim();
      var _t=(_h0.n.t||'').trim();
      if(_d.length>=40 && !(_t && _d.slice(0,20)===_t.slice(0,20))) _본=_gist(_d,nm);
     }
     if(_본){
      분석+='<span style="display:block;margin-top:5px;padding:7px 9px;'+
       'background:#141922;border-radius:7px;font-size:11px;color:#a8b0ba;'+
       'line-height:1.65">📰 '+_본+'</span>';
     } else if(!n2){
      /* 🔴 2026-08-26 수정 — 뉴스를 5거래일치로 넓히면서 이 문장이
         **사흘 전 기사에도 "오늘 뉴스"라고 말하는** 거짓말이 됐다.
         실제 날짜를 보고 문장을 바꾼다. */
      var _오늘것=hits.length&&hits[0].n&&hits[0].n.o;
      분석+=_오늘것?' 오늘 뉴스가 있어 단기 변동이 커질 수 있습니다.'
                  :' 최근 나온 뉴스라 아직 영향이 남아 있을 수 있습니다.';
     }
    }
    else {
     // ⚠️ 재료가 없다고 "없었습니다"로 끝내면 이 코너의 값이 사라진다(2026-08-21).
     //    구독자가 가장 궁금해하는 건 자기 종목이다. 재료가 없는 날일수록
     //    **다음에 볼 것**을 대신 짚어줘야 한다.
     /* 🆕 2026-08-25 HO 지시 — 바로 위 '왜 움직였나'가 이미 재료 없음을
        말했다. 같은 얘기를 두 번 하지 않는다(원칙 4). */
     var 볼것=[], _구역말함=false;
     // ⓐ 소속 구역이 크게 움직였으면 그게 오늘의 이유다
     if(window.CP_SECT_TODAY){
      var zz2=(m[0]||[]), bb2=null;
      zz2.forEach(function(z){
       var v=window.CP_SECT_TODAY[z];
       if(v===undefined||v===null) return;
       if(bb2===null||Math.abs(v)>Math.abs(bb2.v)) bb2={z:z,v:v};
      });
      if(bb2&&Math.abs(bb2.v)>=1.0)
       /* 🔴 2026-08-26 삭제 — 아래 🗺️ 블록이 «같은 섹터 N% vs 이 종목 N%»를
          이미, 그것도 더 정확하게(내 종목 등락률까지 넣어) 말한다.
          여기서 또 말하면 한 카드에서 같은 섹터 숫자를 두 번 읽는다(원칙 4). */
       {_구역말함=true;}
     }
     /* 🔴 2026-08-26 HO 지시 — «시장 전체로는 외국인이 3일 연속 매도» 삭제.
        [WHY] 여기는 «내 종목» 카드다. 코스피 전체 수급은 이미 핵심편 수급
              코너에서 말했고, 이 종목과는 아무 상관이 없을 수 있다.
              종목 카드에는 **그 종목의 수급**만 넣는다 — 아래 💰 블록이 담당한다. */
     // ⓒ 레이더에 잡혔으면 그게 가장 강한 단서
     /* ⚠️ 2026-08-25 — 위 '오늘 분석' 첫 문장이 이미 레이더를 말했으면 여기서
        또 쓰지 않는다. 실제로 «오늘 매집 레이더에 잡혔습니다»가 한 종목에
        두 번 나갔다(원칙 4 — 중복해서 말하지 않는다). */
     if(window.CP_HOT&&window.CP_HOT[nm]&&볼것.length<2
        && 원인.indexOf(window.CP_HOT[nm])<0)
      볼것.push('다만 오늘 <b>'+window.CP_HOT[nm]+'</b>에 잡혔습니다 — 재료 없이 수급만 들어온 자리입니다');
     /* 🆕 2026-08-24 HO 지시 — "별 이슈 없으면 짧게 끝낸다".
        [WHY] 재료가 없는 날에 말을 늘리면 그게 곧 없는 얘기를 지어내는 것이 된다.
              단서가 있으면 하나만 붙이고, 없으면 그냥 거기서 끝낸다.
        ⚠️ 예전엔 단서가 없어도 "시장 흐름을 따라갔을 가능성이 큽니다"를 덧붙였는데,
           바로 위 '왜 올랐나/내렸나' 문장이 이미 같은 말을 하고 있어 중복이었다. */
     if(볼것.length) 분석+=' '+볼것[0]+'.';

    }
    /* ══════════════════════════════════════════════════
       🆕 2026-08-26 HO 지시 — 「뉴스가 거의 안 나온다」의 구조적 해결.
       [진단] RSS 3사는 대형주·시장 기사만 쓴다. 중소형주는 기사가 아예 없어
              기간을 늘려도 0은 0이다. **뉴스를 더 긁는 방향으로는 안 풀린다.**
       [해법] 매일 100% 채워지는 재료를 앞에 세운다 —
              ① 자리(섹터) 대비 ② 크기(시총 층) 대비 ③ 종목 수급 ④ 레이더 이력
       ⚠️ 없는 건 만들지 않는다. 각 블록은 재료가 있을 때만 나온다.
       ══════════════════════════════════════════════════ */
    var _add=[], _자리말함=false;

    /* ① 자리 대비 — "내 종목이 못 간 게 종목 탓인가 자리 탓인가" */
    var _z=null;
    if(window.CP_SECT_TODAY) (m[0]||[]).forEach(function(z){
     var v=window.CP_SECT_TODAY[z];
     if(v===undefined||v===null) return;
     if(_z===null||Math.abs(v)>Math.abs(_z.v)) _z={z:z,v:v};
    });
    /* ⚠️ calc()는 {ex,ret,win,tot}만 준다 — today 필드는 없다.
       오늘 등락률은 창을 1로 준 calc(nm,1).ret가 정답이다. */
    var _c1=calc(nm,1);
    var _ret=(_c1&&!_c1.short&&_c1.ret!==undefined&&_c1.ret!==null)?_c1.ret:null;
    /* 🆕 2026-08-26 HO 지시 — «자리»가 무슨 자리인지 헷갈린다 → **«같은 섹터»**로 바꾼다.
       리포트 다른 곳에서는 «자리»가 통하지만, 이 카드는 내 종목 하나만 보는 자리라
       무엇과 비교하는지가 문장 안에 있어야 한다. */
    if(_z&&_ret!==null){
     var _gap=_ret-_z.v;
     if(Math.abs(_gap)>=1.5){
      var _why='';
      if(_gap<0){
       /* 🆕 HO 지시 — «왜 못 따라갔는지»를 간단히 덧붙인다.
          ⚠️ 지어내지 않는다. 가진 데이터로 설명되는 것만, 강한 순서대로 하나만 고른다.
             ① 같은 섹터 안에서도 이 종목의 «덩치»가 밀린 날인가
             ② 외국인·기관이 이 종목에서 판 날인가
             ③ 둘 다 아니면 «재료가 없었다»까지만 말하고 멈춘다 */
       var _s2=window.CP_STRATA||{}, _t2=(m[2]||''), _b2=null;
       ['대형','중형','소형'].forEach(function(k){
        if(_s2[k]===undefined) return;
        if(_b2===null||_s2[k]>_s2[_b2]) _b2=k;
       });
       var _sf2=(window.CP_SFLOW||{})[nm], _flow2=null;
       if(_sf2&&_sf2.length){ _flow2=_sf2[_sf2.length-1][1]+_sf2[_sf2.length-1][2]; }
       if(_t2&&_b2&&_b2!==_t2&&(_s2[_b2]-_s2[_t2])>=0.8){
        _why=' 같은 섹터 안에서도 <b>'+_b2+'주</b>가 끌고 갔는데 이 종목은 <b>'+_t2+'주</b>라서예요.';
       }else if(_flow2!==null&&_flow2<-30){
        _why=' 외국인·기관이 이 종목에선 <b>순매도</b>였어요.';
       }else if(!hits.length&&!n2){
        _why=' 섹터를 움직인 재료가 이 종목까지는 오지 않았어요.';
       }
      }
      _add.push('🗺️ 같은 섹터(<b>'+_z.z+'</b>)는 '+fmt(_z.v)+'%였는데 이 종목은 '+
       fmt(_ret)+'%예요 — '+(_gap<0
         ? '<b style="color:#ff9a3c">섹터는 올랐는데 이 종목만 못 따라갔어요.</b>'+_why
         : '<b style="color:#74f0d4">섹터보다 더 갔어요 — 종목 자체의 힘이에요</b>'));
      _자리말함=true;
     }else{
      _add.push('🗺️ 같은 섹터(<b>'+_z.z+'</b>) '+fmt(_z.v)+'% · 이 종목 '+fmt(_ret)+
       '% — <b>섹터 흐름을 그대로 따라갔어요</b>');
      _자리말함=true;
     }
    }

    /* ② 크기 대비 — HO 지시: "반도체를 샀는데 못 가는 크기의 종목을 들고 있었다"
       [WHY] 같은 섹터를 사도 그 안에서 대형만 갔으면 중소형을 든 사람은 소외된다.
             섹터만 말하면 "자리는 좋았는데 왜 나만"이 끝까지 설명되지 않는다. */
    var _st=window.CP_STRATA||{}, _my층=(m[2]||'');
    if(_my층&&_st[_my층]!==undefined){
     var _best=null;
     ['대형','중형','소형'].forEach(function(k){
      if(_st[k]===undefined) return;
      if(_best===null||_st[k]>_st[_best]) _best=k;
     });
     /* 🆕 2026-08-26 HO 지시 — «크기»는 처음 보는 사람이 뭘 말하는지 모른다.
        → **«시가총액이 큰/중간/작은 회사»**로 풀어 쓴다. 대형·중형·소형이라는
          말 자체를 문장 안에서 정의해 주면 용어집을 안 봐도 읽힌다. */
     var _풀이={'대형':'시가총액이 큰 회사','중형':'시가총액이 중간인 회사',
              '소형':'시가총액이 작은 회사'};
     if(_best&&_best!==_my층&&(_st[_best]-_st[_my층])>=0.8){
      _add.push('📏 오늘은 <b>'+_풀이[_best]+'</b>들이 '+fmt(_st[_best])+'% 갔는데, '+
       '이 종목이 속한 <b>'+_풀이[_my층]+'</b>들은 '+fmt(_st[_my층])+'%였어요 — '+
       '<b style="color:#ff9a3c">같은 업종을 골랐어도 회사 규모 때문에 밀릴 수 있는 날</b>이었어요');
     }else if(_best===_my층){
      _add.push('📏 오늘은 <b>'+_풀이[_my층]+'</b>들이 '+fmt(_st[_my층])+
       '%로 가장 잘 갔어요 — 이 종목이 <b>그 무리에 속해 유리한 날</b>이었어요');
     }
    }

    /* ②-2 무리에서 이탈 — "오늘 하루"가 아니라 "요 며칠 계속" 뒤처지는지.
       🆕 2026-08-29 HO 지시. [WHY] 위 ① 자리 대비는 오늘 하루만 본다.
       하루 밀리는 건 흔하지만, **여러 날 연속으로** 같은 섹터보다 계속
       처지면 "이 종목만의 문제"일 확률이 높아진다 — 손절 타이밍을 놓치는
       사람들에게 실질적으로 도움이 되는 신호다.
       ⚠️ 새 수집 없음 — 사다리 그래프가 이미 쓰는 _zone_series()를
          CP_SECT_SERIES로 재노출해 재사용한다.
       ⚠️ 대표 구역은 위 ①에서 고른 _z(오늘 가장 세게 움직인 구역)를
          그대로 쓴다 — 카드마다 다른 구역을 기준 삼으면 숫자가 안 맞아
          보인다(원칙 10, 화면 설명과 코드 조건 일치). */
    if(_z&&window.CP_SECT_SERIES&&window.CP_SECT_SERIES[_z.z]){
     var _zs=window.CP_SECT_SERIES[_z.z];   // [[날짜,구역등락], ...] 최근 5일
     var _diffs=[];
     _zs.forEach(function(pair){
      var di=P.days.indexOf(pair[0]);
      if(di<0) return;
      var rv=(P.ret[nm]||[])[di];
      if(rv===null||rv===undefined) return;
      _diffs.push({d:pair[0], gap:rv-pair[1]});
     });
     /* 최근 날짜부터 거슬러 올라가며 "섹터보다 뒤처진(gap<-0.5%p)" 연속 일수 센다.
        ⚠️ 0으로 걸면 오차 수준의 하루도 "이탈"로 잡혀 매일 뜬다 — 최소한의
        문턱(0.5%p)을 둔다. */
     var _이탈연속=0, _이탈합=0;
     for(var _i=_diffs.length-1;_i>=0;_i--){
      if(_diffs[_i].gap<-0.5){ _이탈연속++; _이탈합+=_diffs[_i].gap; }
      else break;
     }
     if(_이탈연속>=3){
      _add.push('⚠️ 최근 <b>'+_이탈연속+'거래일 연속</b> <b>'+_z.z+'</b> 섹터보다 '+
       '뒤처지고 있어요 (평균 <b style="color:#5b9bff">'+
       (_이탈합/_이탈연속).toFixed(1)+'%p</b>) — 종목 자체에 원인이 있는지 '+
       '살펴볼 때예요');
     }

     /* ②-3 최근 누적 섹터 대비 성과. ①은 오늘 하루만, ②-2는 «연속으로
        밀렸나»만 본다. «최근 며칠 통틀어 섹터를 이겼나 졌나»가 비어
        있었다. _diffs(날짜별 종목-섹터 격차)를 그대로 재사용 — 새 수집
        0회. 표본 3일 미만이면 침묵, 격차 ±0.3%p 미만이면 침묵,
        연속이탈 경고가 이미 뜬 날은 생략(원칙4 — 같은 카드에서
        "뒤처진다"를 두 번 말하지 않는다). */
     if(_diffs.length>=3&&_이탈연속<3){
      var _누적=0, _이긴날=0;
      _diffs.forEach(function(x){ _누적+=x.gap; if(x.gap>0) _이긴날++; });
      var _평균=_누적/_diffs.length;
      if(Math.abs(_평균)>=0.3){
       var _이김=_평균>0;
       _add.push('📈 최근 <b>'+_diffs.length+'거래일</b> 동안 <b>'+_z.z+'</b> 섹터보다 '+
        '하루 평균 <b style="color:'+(_이김?'#74f0d4':'#ff9a3c')+'">'+
        (_평균>=0?'+':'')+_평균.toFixed(1)+'%p</b> '+(_이김?'앞섰어요':'뒤졌어요')+
        ' (<b>'+_이긴날+'/'+_diffs.length+'일</b> 섹터 상회) — '+
        (_이김
          ? '<b style="color:#74f0d4">자리도 좋았지만 이 종목이 그 안에서도 강했어요</b>'
          : '<b style="color:#ff9a3c">같은 자리에 있어도 이 종목은 덜 받았어요</b>'));
      }
     }
    }

    /* ③ 종목 수급 — 기사가 없는 중소형주일수록 유일하게 남는 단서.
       ⚠️ 쌓인 만큼만 말한다. 모자란 날을 0으로 채우지 않는다.
       🆕 2026-08-29 HO 지시 — 글자 나열("외국인 +216억 · 기관 -261억 ·
          외국인이 5일 연속…")이 한눈에 안 들어온다는 지적으로 **선그래프**로
          바꾼다. 최근 **10거래일**의 외국인·기관 순매수를 두 선으로 겹쳐
          그린다. 0선 위=매수, 아래=매도.
       ⚠️ 색은 주체를 가리킨다(외국인 금색 #f0c65a / 기관 청록 #74f0d4).
          매수·매도의 빨강/파랑을 선에 쓰면 한 선이 중간에 색이 바뀌어
          흐름을 못 읽는다. 대신 0선을 기준으로 위아래로 읽게 한다. */
    var _sf=(window.CP_SFLOW||{})[nm];
    if(_sf&&_sf.length){
     /* 최근 10거래일만 */
     var _sf10=_sf.slice(-10);
     var _f=0,_g=0;
     _sf10.forEach(function(r){_f+=r[1];_g+=r[2];});
     var _단=function(v){var a=Math.abs(v);
      return (a>=10000?(v/10000).toFixed(2)+'조':Math.round(v).toLocaleString()+'억');};
     var _합=_f+_g;
     var _일수=_sf10.length;

     /* 🔴 2026-08-29 (2차) HO 지시 — 그래프 삭제. 시도해본 막대·선그래프
        둘 다 "위 합계 문장과 숫자가 달라 헷갈린다"는 지적을 받았다
        (그래프 축은 하루 최대치, 문장은 기간 합계라 애초에 다른 걸 재는
        숫자였는데, 라벨을 아무리 붙여도 한눈에 안 풀렸다). → 그래프 없이
        **누적 합계 문장만** 남긴다. 수급 데이터가 있는 종목만 이 문장
        자체가 뜨므로(_sf&&_sf.length 조건), "데이터 있는 종목만 언급"은
        이미 만족된다. */

     /* 연속 매수/매도는 이틀 이상 쌓여야 말이 된다.
        🔴 2026-08-29 HO 지적 — 예전엔 외국인+기관을 «합쳐서» 연속을 셌더니
        화면에 "2일 연속 순매수"라고만 나와 그게 누구인지 알 수 없었다.
        주체별로 따로 세고 이름을 반드시 붙인다(원칙 11 — 단정하는 문장에는
        근거가 있어야 한다). 둘 다 해당하면 둘 다 적는다.
        ⚠️ _연속은 아래 문장 조립에서도 쓰므로 반드시 if 밖에서 선언한다. */
     var _연속={};
     if(_일수>=2){
      var _streak=function(idx){
       var n=0,dir=null;
       for(var i=_sf10.length-1;i>=0;i--){
        var v=_sf10[i][idx], d=v>0?1:(v<0?-1:0);
        if(d===0) break;
        if(dir===null) dir=d; else if(d!==dir) break;
        n++;
       }
       return {n:n, dir:dir};
      };
      /* 🆕 2026-08-29 HO 지시 — 연속을 문장 끝에 몰아 쓰지 않고
         **각 주체 금액 바로 뒤 괄호**에 붙인다. 예전엔
         "외국인 +1,058억 · 기관 +3,764억 · 외국인이 2일 연속… · 기관이 4일 연속…"
         처럼 주체 이름을 두 번씩 말해 길고 헷갈렸다. */
      _연속={};
      [['외국인',1],['기관',2]].forEach(function(pair){
       var r=_streak(pair[1]);
       if(r.n>=2) _연속[pair[0]]='('+r.n+'일 연속 '+
        (r.dir>0?'순매수':'순매도')+')';
      });
     }
     var _f문='<b>'+(_f>=0?'+':'')+_단(_f)+'</b>'+
      (_연속['외국인']?'<span style="color:#8b93a0">'+_연속['외국인']+'</span>':'');
     var _g문='<b>'+(_g>=0?'+':'')+_단(_g)+'</b>'+
      (_연속['기관']?'<span style="color:#8b93a0">'+_연속['기관']+'</span>':'');
     var _꼬리=(_일수>=2)?'':
      ' <span style="color:#6f7784">(기록 1일차 — 쌓이는 대로 흐름을 붙입니다)</span>';
     var _문='💰 최근 '+_일수+'거래일 합계 외국인 '+_f문+' · 기관 '+_g문+_꼬리;
     if(Math.abs(_합)>=50||_일수>=2) _add.push(_문);
    }

    /* ④ 레이더 이력 — 「이번이 3번째」는 우리 기록만 아는 정보다. */
    var _rh=(window.CP_RHIST||{})[nm];
    if(_rh&&_rh.length){
     var _days=[],_kinds={};
     _rh.forEach(function(r){ if(_days.indexOf(r[0])<0)_days.push(r[0]); _kinds[r[1]]=1;});
     var _kn=Object.keys(_kinds).join('·');
     var _문4='📡 예전에도 <b>'+_kn+' 레이더</b>에 <b>'+_days.length+'번</b> 잡혔어요 ('+
      _days.slice(-3).join(', ')+(_days.length>3?' 외':'')+')';
     /* 🆕 2026-08-29 HO 지시 — 예보 성적(D+5 기준)을 같이 붙인다.
        ⚠️ **승패를 있는 그대로** 보여준다. 이긴 것만 골라 보여주면
        "지운 적 없다"는 이 서비스의 핵심 신뢰를 스스로 깨는 셈이라
        (유료챕터_기획.md, 「포착 그 후」 챕터 설계 원칙) 절대 안 한다. */
     var _cs=(window.CP_CAPSTAT||{})[nm];
     if(_cs&&_cs.횟수){
      var _sc=_cs.평균>=0?'#ff6b4a':'#5b9bff';
      /* ⚠️ '최고'도 부호를 그대로 살린다. 표본 전부가 손실이면 최고조차
         마이너스일 수 있다 — 그걸 +로 우기면 그게 진짜 왜곡이다. */
      var _hc=_cs.최고>=0?'#ff6b4a':'#5b9bff';
      _문4+=' · <b>D+5 평균 <span style="color:'+_sc+'">'+
       (_cs.평균>=0?'+':'')+_cs.평균+'%</span></b> (승 '+_cs.승+' · 패 '+_cs.패+
       ') · 최고 <span style="color:'+_hc+'">'+
       (_cs.최고>=0?'+':'')+_cs.최고+'%</span>';
     }
     _add.push(_문4);
    }

    if(_add.length){
     분석+='<span style="display:block;margin-top:6px;padding:8px 10px;'+
      'background:#141922;border-radius:8px;font-size:12px;color:#a8b0ba;'+
      'line-height:1.75">'+_add.join('<br>')+'</span>';
    }
    // ⚠️ 20일 하나만 보면 "그래서 뭐"가 남는다(2026-08-20).
    //    당일·5일·20일·60일을 다 계산해 **가장 인상적인 창**을 골라 덧붙인다.
    //    (같은 방향이면 가장 긴 창, 방향이 엇갈리면 그 엇갈림 자체가 이야기다)
    // ⚠️ 매번 20일만 말하면 모든 종목의 분석이 똑같아 보인다(2026-08-21 지적).
    //    네 창을 다 계산해 **그 종목에서 가장 두드러진 창**을 골라 말한다.
    var 창=[[1,'오늘'],[5,'5일'],[20,'20일'],[60,'분기']], 결=[];
    창.forEach(function(w){
     var cc=calc(nm,w[0]);
     if(cc&&cc.diff!==null&&cc.diff!==undefined) 결.push({k:w[1],d:cc.diff,n:w[0]});
    });
    if(결.length>=2){
     var 최=결.slice().sort(function(a,b){return Math.abs(b.d)-Math.abs(a.d);})[0];
     var 짧=결[0], 김=결[결.length-1];
     if(짧.d!==null&&김.d!==null&&(짧.d>=0)!==(김.d>=0)){
      분석+=' <b>'+김.k+'로는 '+fmt(김.d)+'%p인데 '+짧.k+'은 '+fmt(짧.d)+'%p</b>로 방향이 갈렸습니다 — 흐름이 바뀌는 자리일 수 있습니다.';
     }else{
      분석+=' 기간별로 보면 <b>'+최.k+'이 '+fmt(최.d)+'%p</b>로 가장 두드러집니다.';
     }
    }
    // 소속 구역이 오늘 특별했다면 함께 짚는다
    if(window.CP_SECT_TODAY){
     var zz=(m[0]||[]), best=null;
     zz.forEach(function(z){
      var v=window.CP_SECT_TODAY[z];
      if(v===undefined||v===null) return;
      if(best===null||Math.abs(v)>Math.abs(best.v)) best={z:z,v:v};
     });
     /* 🔴 2026-08-26 수정 — 위 «볼 것»이 이미 같은 구역·같은 숫자를 말한 날에
        여기서 또 말해 한 카드 안에서 같은 문장이 두 번 나왔다(원칙 4). */
     /* 🔴 2026-08-26 — 위 🗺️ 블록이 이미 «섹터 N% vs 이 종목 N%»를 말한다.
        여기서 또 «소속 구역 …이 오늘 N%로 움직인 점도» 를 쓰면 한 카드 안에서
        같은 숫자를 세 번 읽게 된다(원칙 4). 🗺️가 떴으면 침묵한다. */
     if(best&&Math.abs(best.v)>=2&&!_구역말함&&!_자리말함)
      분석+=' 소속 구역 <b>'+best.z+'</b>'+_josa(best.z,'이가')+' 오늘 <b>'+fmt(best.v)+'%</b>로 움직인 점도 함께 보세요.';
    }
   }else{분석='성적을 말하기엔 아직 이력이 부족합니다.';}
   /* 🆕 2026-08-25 HO 지시 — 등록 목록이 아니라 **브리핑**에 기업분석을 붙인다.
      [WHY] 등록 목록은 '지우기·성적' 자리다. 브리핑이 그 종목을 실제로
            읽는 자리라, 기업분석도 여기 있어야 흐름이 안 끊긴다. */
   var _bid='scb'+(_scbSeq++);
   /* 🆕 2026-08-29 HO 지시 — 종목명 옆에 **오늘 등락률**을 붙인다.
      [WHY] 브리핑을 읽는 첫 질문이 "그래서 오늘 얼마나 올랐나"인데,
            그 숫자만 위 등록 목록으로 돌아가서 봐야 했다.
      ⚠️ calc(nm,1)이 당일 창이다(20일짜리 c와 다르다 — 혼동 주의).
         데이터가 없으면 아무것도 안 붙인다(빈칸이 거짓말보다 낫다). */
   var _t=calc(nm,1), _tr=(_t&&!_t.short&&_t.ret!=null)?_t.ret:null;
   var _tb=(_tr===null)?'':
     '<b style="margin-left:7px;font-size:13.5px;color:'+
     (_tr>=0?'#ff6b4a':'#5b9bff')+'">'+(_tr>=0?'+':'')+_tr.toFixed(2)+'%</b>';
   /* 🆕 2026-08-29 HO 지시 — 브리핑 글자가 전체적으로 작다. 조금씩 키운다
      (종목명 13.5→15, 오늘 분석 11.5→12.5, 뉴스·공시 11→12). */
   /* 🆕 2026-08-29 HO 지시 — 순서를 **종목명 · 등락률 · 기업분석**으로.
      [WHY] 등락률이 「기업분석」 뒤에 붙어 있어 이름에서 멀었다.
            종목명 바로 옆에 오늘 숫자가 붙어야 눈이 안 튄다.
      ⚠️ 「기업분석」 펼침 버튼(.sc-tap)은 .cp-sname 안에 있어야
         클릭 동작이 붙는다(sc_click 규약). 그래서 등락률을
         **.cp-sname 안, 이름과 sc-tap 사이**에 넣는다. */
   out+='<div style="padding:11px 0;border-bottom:1px solid #1b212c">'+
    '<div style="font-size:15px;font-weight:800;color:#e8eaee">'+
    '<span class="cp-sname" id="'+_bid+'-n">'+nm+_tb+
    '<span class="sc-tap"><i>▾</i>기업분석</span></span></div>'+
    '<div style="margin-top:4px">'+zones+'</div>'+items+
    /* 🆕 2026-08-26 HO 지시 — 기업분석 펼침칸을 «오늘 분석» **위**로 올린다.
       [WHY] 종목명을 눌러 회사를 확인하는 흐름인데, 카드가 오늘 분석 아래에
             열리면 방금 읽던 자리에서 시선이 건너뛴다. 이름 → 회사 → 오늘 분석
             순서가 읽는 순서와 맞는다. */
    '<div id="'+_bid+'" style="display:none"></div>'+
    '<div style="margin-top:7px;padding:8px 10px;background:#0f131a;border-radius:8px;'+
    'border-left:2.5px solid #e0c060">'+
    '<p style="margin:0;font-size:12.5px;color:#c9ced6;line-height:1.7">'+
    '<b style="color:#e0c060">오늘 분석</b> — '+원인+분석+'</p></div></div>';
  });
  host.innerHTML=out;
  /* 🆕 2026-08-25 — 클릭 핸들러는 **코드로** 붙인다.
     인라인 onclick에 따옴표를 넣으면 파이썬 문자열을 거치며 이스케이프가
     풀려 JS가 통째로 죽는다(2026-08-25에 이미 한 번 겪었다). */
  my.forEach(function(nm,i){
   var el=document.getElementById('scb'+(_scbSeq-my.length+i)+'-n');
   if(el) el.onclick=function(){ scToggle(nm,'scb'+(_scbSeq-my.length+i)); };
  });
 }
 // 내 종목들의 '시장 대비 초과수익' 곡선 — 등록 종목이 있을 때만 그린다.
 function _gist(txt, nm){
  /* 기사 요약문에서 **핵심 문장만** 골라 3줄로 줄인다.

     🆕 2026-08-25 HO 지시 — "뉴스를 이해할 수 있게 요약해야지. 핵심만!"
     ⚠️ 이건 진짜 요약이 아니라 **문장 선별**이다. 관심종목은 브라우저에만
        있어서 서버가 누가 뭘 등록했는지 모른다 → Claude가 요약해줄 수 없다.
        그래서 지어내지 않고 **원문 문장 중 중요한 것만 고른다.**
     [고르는 기준]
       ① 그 종목 이름이 들어간 문장          (가장 중요)
       ② 숫자·규모가 들어간 문장             (계약금액·목표주가·증감률)
       ③ 판단어가 들어간 문장                (전망·평가·상향·하향)
       ④ 그래도 없으면 맨 앞 문장
     ⚠️ 기자 이름·이메일·«[클릭 e종목]» 같은 꼬리는 버린다. */
  var t=(txt||'').replace(/\[[^\]]{1,12}\]/g,' ')
                 .replace(/[가-힣]{2,4}\s*기자|[\w.]+@[\w.]+/g,' ')
                 .replace(/\s+/g,' ').trim();
  var sents=t.split(/(?<=[.!?])\s+|(?<=다\.)\s*/).filter(function(x){
    return x && x.replace(/\s/g,'').length>=12;});
  if(!sents.length) return '';
  var 점=sents.map(function(x,i){
    var p=0;
    if(nm && x.indexOf(nm)>=0) p+=5;
    if(/\d/.test(x)) p+=2;
    if(/(억|조|%|배)/.test(x)) p+=2;
    if(/(전망|평가|상향|하향|기대|우려|분석|계획|밝혔|예상)/.test(x)) p+=1;
    p += Math.max(0, 2-i);                 // 앞 문장에 가산점
    return {x:x, p:p, i:i};});
  점.sort(function(a,b){return b.p-a.p || a.i-b.i;});
  var 뽑=점.slice(0,3).sort(function(a,b){return a.i-b.i;})
           .map(function(o){return o.x.trim();});
  var out=뽑.join(' ');
  if(out.length>200) out=out.slice(0,200).replace(/[,\s]+$/,'')+'…';
  return out;
 }
 function _gistNoop(){}
 /* ══════════════════════════════════════════════════════════
    🏢 종목 카드 — 이름을 누르면 아래로 펼쳐진다 (2026-08-25 신설)
    ══════════════════════════════════════════════════════════
    HO 기획 — 레이더에서 종목을 본 사람은 "이게 뭐 하는 회사지?"가 궁금하다.
    그런데 그 사람의 진짜 질문은 하나 더 있다 — **"왜 지금 내 눈앞에 있지?"**
    네이버·FnGuide는 첫 질문엔 답하지만 두 번째엔 못 답한다.
    왜 잡혔는지는 **우리 코드만 알기 때문**이다. 그래서 카드의 중심을
    '회사 소개'가 아니라 **'포착 사유서'**로 잡는다.

    ⚠️ 재무가 없으면 지어내지 않는다. "다음 발행부터"라고 솔직히 쓴다. */
 function _fmtEok(v){            /* 원 단위 → 억/조 */
  if(v===null||v===undefined||isNaN(v)) return null;
  var a=Math.abs(v)/100000000;   /* 원 → 억 */
  if(a>=10000) return (v/1000000000000).toFixed(1)+'조';
  if(a>=1) return Math.round(v/100000000).toLocaleString()+'억';
  return Math.round(v/10000).toLocaleString()+'만';
 }
 function _bars(vals, w, h){     /* 미니 막대 — 적자는 파랑 */
  w=w||96; h=h||22;
  var ok=vals.filter(function(v){return v!==null&&v!==undefined;});
  if(ok.length<2) return '';
  var mx=Math.max.apply(null,ok.map(Math.abs))||1;
  var bw=(w-(vals.length-1)*3)/vals.length, g='', z=h;
  vals.forEach(function(v,i){
   if(v===null||v===undefined) return;
   var bh=Math.max(2,Math.abs(v)/mx*(h-2));
   var c=v>=0?'#ff6b4a':'#5b9bff';
   g+='<rect x="'+(i*(bw+3)).toFixed(1)+'" y="'+(z-bh).toFixed(1)+'" width="'+bw.toFixed(1)+
      '" height="'+bh.toFixed(1)+'" rx="1.5" fill="'+c+'" opacity="'+(i===vals.length-1?1:.55)+'"/>';
  });
  return '<svg viewBox="0 0 '+w+' '+h+'" style="width:'+w+'px;height:'+h+'px;vertical-align:middle">'+g+'</svg>';
 }
 function _gauge(pct, 기준){     /* 부채비율 게이지 */
  /* 🔴 2026-08-26 HO 지적 — 대우건설처럼 부채비율이 높은 종목에서 **빨간 원이
     잘려** 나왔다. 막대 폭(110)과 viewBox 폭이 같은데 원 중심이 끝까지 가서
     반지름 4만큼이 밖으로 나갔다.
     [고침] viewBox 양옆에 반지름만큼 여백(P)을 두고, 막대는 그 안쪽에 그린다. */
  var w=110,h=12,P=5;
  var x=P+Math.max(0,Math.min(1,pct/(기준*2)))*w;
  var c=pct<=기준?'#4ade80':(pct<=기준*1.5?'#e0c060':'#ff6b4a');
  return '<svg viewBox="0 0 '+(w+P*2)+' '+h+'" style="width:'+(w+P*2)+'px;height:'+h+'px;vertical-align:middle">'+
   '<rect x="'+P+'" y="4" width="'+w+'" height="4" rx="2" fill="#232a36"/>'+
   '<line x1="'+(P+w/2)+'" y1="1" x2="'+(P+w/2)+'" y2="'+(h-1)+'" stroke="#6f7784" stroke-width="1"/>'+
   '<circle cx="'+x.toFixed(1)+'" cy="6" r="4" fill="'+c+'"/></svg>';
 }
 function _why(nm){
  /* 🎯 왜 여기 떴나 — 우리만 쓸 수 있는 칸.
     ⚠️ 레이더 조건을 **그대로** 보여준다. "추천"이 아니라 "이 조건에 걸렸다"임을
        숫자로 밝히는 것이 이 코너의 정직성이다.
     🆕 2026-08-25 — 재료를 아끼지 않는다:
        · 외국인/기관을 **나눠서** (누가 사는지가 성격을 가른다)
        · 5·20·60일 **동시 포착** (기간이 겹칠수록 우연이 아니다)
        · 매집 차수 배지 (전에도 모았던 자리인가) */
  var A=(window.CP_ACC_DETAIL||{})[nm], S=(window.CP_STR_DETAIL||{})[nm], out='';
  if(A){
   var 겹=(A.기간들||[]).length;
   out+='<p class="sc-why-t">🐢 '+(A.유형||'매집')+
     (겹>1?' <span class="sc-hot">'+(A.기간들.join('·'))+' 동시</span>':' — '+(A.기간||'')+' 기준')+
     '</p>';
   out+='<p class="sc-why-b">'+
     '<b style="color:#74f0d4">'+(A.합산||'')+'</b> · 시총의 <b style="color:#74f0d4">'+
     (A.시총대비||'')+'</b>'+(A.순위?' · 이 조건 <b>'+A.순위+'위</b>/'+(A.전체||'')+'종목':'')+'</p>';
   /* 외국인 vs 기관 — 누가 담았나 */
   if(A.외국인||A.기관){
    out+='<p class="sc-why-s">외국인 <b>'+(A.외국인||'—')+'</b>'+
      (A.외인일수!==null&&A.외인일수!==undefined?' ('+A.외인일수+'일 매수)':'')+
      ' · 기관 <b>'+(A.기관||'—')+'</b>'+
      (A.기관일수!==null&&A.기관일수!==undefined?' ('+A.기관일수+'일 매수)':'')+'</p>';
   }
   if(A.등락!==undefined&&A.등락!==null)
    out+='<p class="sc-why-m">↳ 그동안 주가는 <b>'+fmt(A.등락)+'%</b>였어요 — '+
     (A.등락<5?'<b>사들였는데 아직 안 올랐다</b>는 뜻이에요'
              :'이미 오른 상태에서 담고 있어요')+'</p>';
   if(겹>1)
    out+='<p class="sc-why-m">↳ <b>'+A.기간들.join('·')+'</b> 매집에 모두 걸렸어요 — '+
      '짧게도 길게도 사고 있다는 뜻이라 우연일 가능성이 낮아요</p>';
   if(A.배지) out+='<p class="sc-why-badge">'+A.배지+'</p>';
  }
  if(S){
   out+='<p class="sc-why-t" style="margin-top:8px">🔥 '+(S.유형||'강세')+'</p>'+
    '<p class="sc-why-b">'+(S.설명||'')+'</p>';
   if(S.종가위치!==undefined&&S.종가위치!==null)
    out+='<p class="sc-why-m">↳ 종가가 오늘 고가·저가 구간의 <b>'+
      Math.round(S.종가위치*100)+'%</b> 지점이에요 — '+
      (S.종가위치>=0.8?'<b>고가 근처에서 끝났어요</b>(매수세가 끝까지 붙음)'
                     :'장중 힘이 빠졌어요')+'</p>';
   if(S.회전율) out+='<p class="sc-why-s">회전율 <b>'+S.회전율+
     '%</b> — 하루 만에 전체 주식의 이만큼이 손을 바꿨어요</p>';
  }
  /* 과거에도 잡혔나 — 이건 다른 곳이 절대 못 한다 */
  var T=(window.CP_TRACK||{})[nm];
  if(T&&T.length){
   out+='<p class="sc-why-t" style="margin-top:8px">📌 전에도 잡혔어요</p>';
   T.forEach(function(t){
    var c=(t.등락||0)>=0?'#ff6b4a':'#5b9bff';
    out+='<p class="sc-why-b">'+t.날+' '+t.종류+' 레이더 · '+t.경과+'거래일 지나 '+
      '<b style="color:'+c+'">'+fmt(t.등락)+'%</b></p>';
   });
  }
  if(!out) out='<p class="sc-why-b">오늘 레이더 조건에는 안 걸렸어요. 등록해두신 종목이에요.</p>';
  return out;
 }
 function _fin(nm, 상세){
  /* 재무 카드.
     🔴 2026-09-01 HO 지시 — "처음 누르면 회사소개·왜주목받나만, 매출은
        여기서 나와요·매출·영업이익·영업이익률·부채비율은 자세히 보기로."
        예전엔 상세=false(요약)가 매출/영업이익/부채비율을, 상세=true(상세)가
        순이익·영업이익률(문장)을 나눠 맡았다. 이제 **전부 상세=true 하나로
        합친다** — 요약 카드에서 재무를 아예 안 보여주기로 했기 때문이다. */
  var P=(window.CP_PROFILE||{})[nm];
  if(!P||!P.연도별) return 상세?'<p class="sc-empty">🏢 재무는 아직 준비되지 않았어요 — 다음 발행부터 채워드릴게요</p>':'';
  var ys=Object.keys(P.연도별).sort();
  if(!ys.length) return 상세?'<p class="sc-empty">🏢 재무는 아직 준비되지 않았어요 — 다음 발행부터 채워드릴게요</p>':'';
  var 끝=P.연도별[ys[ys.length-1]], 첫=P.연도별[ys[0]];
  if(!상세) return '';   // ⚠️ 이제 요약 카드에서는 안 부른다. 혹시 몰라 안전하게 빈 값.

  var 매=ys.map(function(y){return P.연도별[y].매출;});
  var 영=ys.map(function(y){return P.연도별[y].영업이익;});
  var 순=ys.map(function(y){return P.연도별[y].순이익;});
  var 기간표시=ys[ys.length-1]+'년 '+(끝.구분||'')+' 기준';

  var 증='';
  if(ys.length>=2){
   var _직=P.연도별[ys[ys.length-2]]||{};
   if(_직.매출&&끝.매출){
    var g1=(끝.매출-_직.매출)/Math.abs(_직.매출)*100;
    var _추세='';
    if(ys.length>=3){
     var _직직=P.연도별[ys[ys.length-3]]||{};
     if(_직직.매출){
      var g0=(_직.매출-_직직.매출)/Math.abs(_직직.매출)*100;
      if(g1>=2&&g0>=2) _추세=' — <b style="color:#ff6b4a">2년째 늘고 있어요</b>';
      else if(g1<=-2&&g0<=-2) _추세=' — <b style="color:#5b9bff">2년째 줄고 있어요</b>';
      else if(g1>=2&&g0<=-2) _추세=' — <b style="color:#ff6b4a">줄다가 돌아섰어요</b>';
      else if(g1<=-2&&g0>=2) _추세=' — <b style="color:#5b9bff">늘다가 꺾였어요</b>';
     }
    }
    증='<p class="sc-note">매출은 '+ys[ys.length-2]+'년보다 '+
     (Math.abs(g1)<1?'<b>거의 그대로</b>예요'
       :(g1>=0?'<b style="color:#ff6b4a">'+g1.toFixed(1)+'% 늘었어요</b>'
              :'<b style="color:#5b9bff">'+Math.abs(g1).toFixed(1)+'% 줄었어요</b>'))+
     _추세+'.</p>';
   }
  }
  // 🆕 2026-09-01 — 영업이익률을 부채비율과 같은 «게이지 행» 형태로.
  //    전엔 문장 하나(사유: 요약에 매출/영업이익 숫자가 이미 있어서
  //    비율만 문장으로 덧붙이면 충분했다)였는데, 이제 재무 4종을
  //    한자리에 나란히 두기로 했으니 같은 행 모양으로 맞춘다.
  var 이익률행='';
  if(끝.매출&&끝.영업이익!==null){
   var m=끝.영업이익/끝.매출*100;
   var mc=m>=15?'#4ade80':(m>=0?'#e0c060':'#ff6b4a');
   이익률행='<div class="sc-row"><span class="sc-k">영업이익률</span>'+_gauge(Math.max(0,m),30)+
    '<b class="sc-v" style="color:'+mc+'">'+m.toFixed(1)+'%</b></div>'+
    '<p class="sc-note">100원 팔아 '+m.toFixed(0)+'원 남긴다는 뜻이에요.</p>';
  }
  var 부채='';
  if(끝.부채&&끝.자본){
   var r=끝.부채/끝.자본*100;
   부채='<div class="sc-row"><span class="sc-k">부채비율</span>'+_gauge(r,100)+
    '<b class="sc-v" style="color:'+(r<=100?'#4ade80':(r<=150?'#e0c060':'#ff6b4a'))+'">'+
    r.toFixed(0)+'%</b></div>';
  }
  var 적자경고='';
  if(끝.영업이익!==null&&끝.영업이익<0)
   적자경고='<p class="sc-warn">⚠️ 가장 최근 확정 연도가 <b>영업적자</b>예요</p>';
  else if(영.length>=2&&영[영.length-2]!==null&&영[영.length-2]<0&&끝.영업이익>0)
   적자경고='<p class="sc-warn">⚠️ 적자였다가 <b>흑자로 돌아선</b> 상태예요 — 이어지는지가 관건이에요</p>';

  var out='<div class="sc-fin"><p class="sc-h">💰 돈은 벌고 있나 <span class="sc-sub">'+
   기간표시+'</span></p>'+
   '<div class="sc-row"><span class="sc-k">매출</span>'+_bars(매)+
   '<b class="sc-v">'+(_fmtEok(끝.매출)||'—')+'</b></div>'+
   '<div class="sc-row"><span class="sc-k">영업이익</span>'+_bars(영)+
   '<b class="sc-v" style="color:'+((끝.영업이익||0)>=0?'#ff6b4a':'#5b9bff')+'">'+
   (_fmtEok(끝.영업이익)||'—')+'</b></div>'+
   이익률행+부채+증+적자경고;

  // ── 여기부터는 기존 "조금 더 들어가면" 부가정보 — 순이익·시총배수·출처.
  out+='<div class="sc-row"><span class="sc-k">순이익</span>'+_bars(순)+
   '<b class="sc-v" style="color:'+((끝.순이익||0)>=0?'#ff6b4a':'#5b9bff')+'">'+
   (_fmtEok(끝.순이익)||'—')+'</b></div>';
  if(P.시총&&끝.영업이익>0){
   var 배=(P.시총*100000000)/끝.영업이익;
   out+='<p class="sc-note">지금 시가총액은 <b>연간 영업이익의 '+배.toFixed(0)+'배</b>예요. '+
    '시장이 앞으로 더 벌 거라고 보고 있다는 뜻이에요.</p>';
  }
  out+='<p class="sc-src">출처 — DART 사업보고서(연결 우선). 최근 확정 연도 기준이라 '+
   '올해 실적은 아직 안 들어가 있어요.</p>';
  return out+'</div>';
 }
 function scToggle(nm, id){
  var box=document.getElementById(id);
  if(!box) return;
  if(box.dataset.open==='1'){ box.style.display='none'; box.dataset.open='0'; return; }
  if(!box.dataset.built){
   var P=(window.CP_PROFILE||{})[nm]||{};
   var 개=(P.개요||{});
   var 한줄=(window.CP_ONELINE||{})[nm]||'';
   var B=(window.CP_BASIC||{})[nm]||{};
   /* 🆕 2026-08-25 — 카드 맨 위 한 줄에 «오늘 얼마 / 어느 급» 을 박는다.
      종목을 처음 보는 사람이 제일 먼저 알아야 하는 것이다. */
   var 기본='';
   if(B.등락!==undefined&&B.등락!==null){
    var bc=B.등락>=0?'#ff6b4a':'#5b9bff';
    기본='<p class="sc-basic">오늘 <b style="color:'+bc+'">'+fmt(B.등락)+'%</b>'+
     (B.순위?' · 시총 '+B.순위+'위':'')+(B.층?' ('+B.층+'주)':'')+
     (B.시장?' · '+B.시장:'')+'</p>';
   }
   /* 🆕 2026-08-26 HO 지시 — "뭐 하는 회사인지" 를 맨 위에.
      ⚠️ 매출 비중(사업 포트폴리오)은 DART 주요계정에 없어서 못 만든다.
         지어내지 않고, 있는 재료(섹터 + 묶인 테마)로 **성격만** 알려준다. */
   var 테마=(window.CP_THEMES||{})[nm]||[];
   /* 🆕 2026-08-26 HO 지시 — 회사 소개가 «건설·부동산 쪽 회사예요»로 끝나
      너무 피상적이었다. 저장돼 있던 **업종명·설립연도·대표**를 꺼내 쓴다. */
   var 회사='';
   var _업=개.업종명||'', _설=개.설립연||'';
   var _본문='';
   if(_업){
    /* ⚠️ 조사는 반드시 _josa()로. «기계·장비 제조이», «반도체으로» 같은
       문장이 그대로 나갔다. 업종명·섹터명은 매일 바뀌므로 코드로 막는다. */
    _본문='<b>'+_업+'</b>'+_josa(_업,'이가')+' 본업이에요';
    if(한줄&&한줄!==_업)
     _본문+=' (시장에서는 <b>'+한줄+'</b>'+_josa(한줄,'으로')+' 분류돼요)';
    _본문+='.';
   }else if(한줄){
    _본문='<b>'+한줄+'</b> 쪽 회사예요.';
   }
   /* 🔴 2026-08-26 HO 지시 — 설립연도·대표 이름 삭제.
      [WHY] 투자 판단에 안 쓰이는 정보다. 카드에 줄이 하나 늘 뿐이고,
            정작 궁금한 «왜 올랐나»를 아래로 밀어낸다. */
   var _연혁='';
   /* 📊 2026-09-01 (2차) HO 지시 — "매출은 여기서 나와요"를 요약(앞면)이
      아니라 «자세히 보기»로 옮긴다. 앞면은 어떤 회사인지·왜 주목받는지
      딱 두 가지만 보여준다. ⚠️ _bp 계산 자체는 여기서 한다(어차피
      회사소개 문구가 "포트폴리오 있음/없음"을 알아야 하므로) — 실제
      막대 렌더는 scMore로 옮긴다. */
   var _bp=(window.CP_BIZPORT||{})[nm]||null;
   if(_본문||테마.length||_연혁){
    회사='<div class="sc-blk"><p class="sc-h">🏢 어떤 회사냐면요</p>'+
     (_본문?'<p class="sc-biz">'+_본문+'</p>':'')+_연혁+
     (테마.length?'<p class="sc-note">시장에서는 '+
       테마.map(function(t){return '<b>'+t+'</b>';}).join(' · ')+
       ' 테마로 묶여 있어요.</p>':'')+
     /* 포트폴리오가 있으면 «자세히 보기에서 확인» 안내로, 없으면
        정직하게 «비워둡니다»(원칙 14). 둘 다 한 줄로 짧게 — 앞면은
        어디까지나 요약이라, 안내문이 본문보다 길면 안 된다. */
     (_bp?'<p class="sc-src">매출은 어느 사업에서 나오는지 «자세히 보기»에서 볼 수 있어요.</p>'
         :'<p class="sc-src">매출을 어느 사업에서 얼마나 버는지(사업 포트폴리오)는 '+
     'DART 사업보고서 원문을 읽어야 나와요. 지금은 준비 중이라, 확인되기 전까지 '+
     '<b>지어내지 않고 비워둡니다.</b></p>')+'</div>';
   }
   /* 🆕 2026-08-26 HO 지시 — "사람들이 제일 궁금한 건 «이 종목이 최근에 왜 올랐나»다".
      그동안 이 내용이 «자세히 보기» 안에 숨어 있어 대부분 못 봤다.
      → **요약 자리로 끌어올린다.** 순서: 회사 소개 → 왜 주목받나 → 재무. */
   var _뉴=(window.CP_STOCK_NEWS||{})[nm]||[];
   var _왜='';
   if(_뉴.length){
    var _lst='';
    _뉴.slice(0,4).forEach(function(n){
     _lst+='<p class="sc-news">'+(n.k?'<span class="sc-kind">'+n.k+'</span> ':'')+
      '<a href="'+n.u+'" target="_blank">'+n.t+'</a></p>';});
    _lst+='<p class="sc-note">이 종목 이름이 들어간 <b>최근 기사·공시</b>예요. '+
     '재료가 실제 매출로 잡히기까지는 보통 <b>2~4분기</b>가 걸려서, '+
     '지금 주가에 반영된 건 대개 <b>기대</b>예요.</p>';
   }else{
    _lst='<p class="sc-note">기록에 남은 기간 안에 이 종목 이름이 들어간 '+
     '기사·공시가 <b>없었어요</b>.</p>';
   }
   /* 🔴 2026-08-26 (2차) HO 지시 — 이 칸에서 **매집·레이더 이야기를 뺀다.**
      [WHY] «매집 6번 잡혔다»·«강세 레이더에 걸렸다»는 위쪽 레이더 코너와
            「내 종목 브리핑」이 이미 말한다. 여기서 또 하면 세 번째다(원칙 4).
      👉 이 칸은 «투자자가 알고 싶어 하는 이슈»만 담는다 —
         "스페이스X에 납품하게 됐다" 같은 **사건**. 그건 뉴스·공시에 있다.
      ⚠️ 이슈가 없으면 없다고 짧게 끝낸다. 수급 숫자로 칸을 채우지 않는다. */
   _왜='<div class="sc-blk"><p class="sc-h">🔥 요즘 왜 주목받냐면요</p>'+_lst+'</div>';
   box.innerHTML='<div class="sc-card">'+
    (한줄?'<p class="sc-def">'+한줄+'</p>':'')+기본+회사+_왜+
    /* 🔴 2026-09-01 HO 지시 — "처음 누르면 어떤 회사인지·왜 주목받는지
       두 가지만 나와야 해." 재무 요약(_fin)을 요약 카드에서 뺐다.
       매출·영업이익·부채비율·영업이익률은 이제 «자세히 보기»에서만
       (매출 막대그래프와 같이) 보여준다. */
    '<p class="sc-more" id="'+id+'-m">자세히 보기 ↓</p>'+
    '<div id="'+id+'-d" style="display:none"></div></div>';
   box.dataset.built='1';
   /* ⚠️ 인라인 onclick에 따옴표를 넣으면 이 JS가 파이썬 문자열을 거치며
      이스케이프가 풀려 문법이 깨진다(2026-08-25 실제 사고).
      → 핸들러는 **코드로 붙인다.** 따옴표 중첩이 아예 없어진다. */
   var _m=document.getElementById(id+'-m');
   if(_m) _m.onclick=function(){ scMore(nm, id); };
  }
  box.style.display='block'; box.dataset.open='1';
 }
 function scMore(nm, id){
  var d=document.getElementById(id+'-d');
  if(!d) return;
  if(d.dataset.open==='1'){ d.style.display='none'; d.dataset.open='0'; return; }
  if(!d.dataset.built){
   /* 🔴 2026-09-01 HO 지시 — 자세히 보기 순서를 다시 정리했다.
      [순서] 매출은 여기서 나와요(막대) → 매출/영업이익/영업이익률/부채비율
      (_fin true 안에 다 들어있다) → 투자판단 문구.
      ⚠️ 매출 막대(사업 포트폴리오)는 scToggle에서 계산해둔 window.CP_BIZPORT를
      여기서 **다시** 읽는다 — scToggle과 scMore는 별개 함수라 변수를
      못 나눠 쓴다(간단히 재조회하는 쪽이 상태 관리보다 안전하다). */
   var _bp=(window.CP_BIZPORT||{})[nm]||null;
   var _포트='';
   if(_bp&&_bp.부문&&_bp.부문.length){
    var _rows='';
    var _sorted=_bp.부문.slice().sort(function(a,b){return (b.비중||0)-(a.비중||0);});
    _sorted.forEach(function(seg){
     var _p=Math.max(0,Math.min(100,seg.비중||0));
     _rows+='<div class="bp-row">'+
      '<div class="bp-top"><span class="bp-k">'+seg.이름+'</span>'+
      '<b class="bp-v">'+(_p<10?_p.toFixed(1):Math.round(_p))+'%</b></div>'+
      '<span class="bp-bar"><i style="width:'+_p.toFixed(1)+'%"></i></span></div>';
    });
    _포트='<div class="sc-blk"><p class="sc-h">📊 매출은 여기서 나와요</p>'+
     '<div class="bp-wrap">'+_rows+'</div>'+
     '<p class="sc-src">'+(_bp.기준||'사업보고서')+' 기준'+
     (_bp.rcp?' · <a href="https://dart.fss.or.kr/dsaf001/main.do?rcpNo='+_bp.rcp+
       '" target="_blank">DART 원문</a>':'')+
     '</p></div>';
   }
   d.innerHTML=
    _포트+
    _fin(nm,true)+
    '<p class="sc-disc">투자 판단을 대신하지 않아요. 조건과 숫자를 그대로 보여드릴 뿐이에요.</p>';
   d.dataset.built='1';
  }
  d.style.display='block'; d.dataset.open='1';
 }
 /* ⚠️ 이 스크립트는 즉시실행 함수 안에 있어서 함수가 전역에 안 붙는다.
    인라인 onclick은 전역에서만 찾으므로 **명시적으로 window에 붙인다.**
    (2026-08-25 — 이걸 안 해서 "scToggle is not defined"가 났다) */
 window.scToggle=scToggle; window.scMore=scMore;
 function multiSpan(nm){
  /* 구간 특징 — **뚜렷할 때만** 한 줄. 아니면 아무 말도 안 한다.

     🆕 2026-08-25 HO 지시 — "5일 +0.4%p · 이 구간이 가장 크게 앞섰어요"처럼
        의미 없는 문장이 매일 나왔다. 표본도 모자라고 격차도 미미한데
        굳이 한 줄을 채운 셈이다.
     [규칙]
       ① 20일 구간까지 다 있어야 한다(= 최소 20거래일 축적)
       ② 그리고 아래 둘 중 하나가 **뚜렷할 때만** 말한다:
          · 방향 전환 — 긴 구간과 5일의 부호가 반대이고, 둘 다 1%p 이상
          · 가속·감속 — 5일이 긴 구간의 2배 이상이거나 1/3 이하
       ③ 둘 다 아니면 **빈 문자열**. 억지로 채우지 않는다.
     ⚠️ 데이터가 쌓이고 실제로 이슈가 생겼을 때만 발화하는 구조다. */
  var W=[5,10,15,20], got=[];
  W.forEach(function(w){var c=calc(nm,w);
   if(c&&!c.short&&c.tot>=w) got.push({w:w,ex:c.ex,tot:c.tot});});
  if(got.length<4) return '';          // ① 20일이 다 안 찼으면 침묵
  var s5=got[0], sL=got[got.length-1];
  var a=Math.abs(s5.ex), b=Math.abs(sL.ex);
  function tag(w,v,말){
   var col=v>=0?'#ff6b4a':'#5b9bff';
   return '<span style="display:block;margin:2px 0 5px;font-size:11px;color:#8b93a0">'+
     '<b style="color:#c9ced6">'+w+'일 </b>'+
     '<b style="color:'+col+'">'+fmt(v)+'%p</b> · '+말+'</span>';
  }
  /* ② 방향 전환 — 둘 다 1%p 이상일 때만 (미미한 부호 차이는 소음) */
  if(a>=1 && b>=1){
   if(s5.ex>0 && sL.ex<0)
    return tag(20, sL.ex, '길게는 뒤처졌는데 <b>최근 5일은 앞섭니다</b> — 돌아서는 중일 수 있어요');
   if(s5.ex<0 && sL.ex>0)
    return tag(20, sL.ex, '길게는 앞섰는데 <b>최근 5일에 밀렸습니다</b> — 쉬어가는 자리인지가 갈림길');
  }
  /* ② 가속·감속 — 2배 이상 벌어질 때만 */
  if(b>=1 && a>=b*2)
   return tag(5, s5.ex, (s5.ex>=0?'<b>앞서는 폭이 빠르게 커지는</b> 중입니다'
                                 :'<b>뒤처지는 폭이 빠르게 커지는</b> 중입니다'));
  if(b>=1.5 && a<=b/3)
   return tag(20, sL.ex, (sL.ex>=0?'앞서 있지만 <b>최근 들어 힘이 빠졌습니다</b>'
                                  :'뒤처졌지만 <b>최근 들어 격차를 좁혔습니다</b>'));
  return '';                           // ③ 뚜렷하지 않으면 침묵
 }
 function drawTodayBars(my, host){
  /* 당일 초과수익 막대 — 종목별로 '오늘 시장을 얼마나 이겼나'를 나란히. */
  var last=P.days.length-1;
  while(last>=0 && P.mkt[last]==null) last--;
  if(last<0||!my.length){host.innerHTML=''; return;}
  var mv=P.mkt[last], rows=[];
  my.forEach(function(nm){var r=P.ret[nm];
   if(!r||r[last]==null) return;
   rows.push({nm:nm, ex:r[last]-mv, ret:r[last]});});
  if(!rows.length){host.innerHTML=''; return;}
  rows.sort(function(a,b){return b.ex-a.ex;});
  var W=360,H=Math.max(70,26+rows.length*22),L=70,R=52,mx=1;  /* R=수치 자리. +33.1%p가 잘려 넓혔다 */
  rows.forEach(function(x){mx=Math.max(mx,Math.abs(x.ex));});
  var z=L+(W-L-R)/2, half=(W-L-R)/2;
  /* 🆕 2026-08-24 HO 지시 — 시장평균을 그래프에 직관적으로.
     [WHY] 막대가 0선 기준이면 "0보다 크다"는 건 알겠는데
           **그 0이 코스피라는 걸** 모른다. 선에 이름을 붙여준다.
     세로 점선 + 상단 라벨로 "여기가 코스피" 를 못 박는다. */
  var g='<line x1="'+z+'" y1="16" x2="'+z+'" y2="'+(H-6)+'" stroke="#f0c65a" '+
        'stroke-width="1.4" stroke-dasharray="3 2"/>'+
        '<text x="'+z+'" y="10" text-anchor="middle" font-size="8.5" font-weight="800" '+
        'fill="#f0c65a">코스피 '+fmt(mv)+'%</text>'+
        /* ⚠️ 화살표는 **가리키는 방향**이 곧 뜻이다. 반대로 쓰면 정반대로 읽힌다. */
        '<text x="'+(z+half*0.55)+'" y="10" text-anchor="middle" font-size="8" '+
        'fill="#ff6b4a">이긴 쪽 →</text>'+
        '<text x="'+(z-half*0.55)+'" y="10" text-anchor="middle" font-size="8" '+
        'fill="#5b9bff">← 진 쪽</text>';
  rows.forEach(function(x,i){
   var y=20+i*22, w=Math.abs(x.ex)/mx*half*0.9;
   var c=x.ex>=0?'#ff6b4a':'#5b9bff';
   g+='<rect x="'+(x.ex>=0?z:z-w)+'" y="'+y+'" width="'+Math.max(2,w)+'" height="12" rx="2.5" fill="'+c+'"/>';
   g+='<text x="'+(L-5)+'" y="'+(y+10)+'" text-anchor="end" font-size="9.5" fill="#c9ced6">'+
      (x.nm.length>7?x.nm.slice(0,7):x.nm)+'</text>';
   g+='<text x="'+(W-R+3)+'" y="'+(y+10)+'" font-size="9.5" font-weight="700" fill="'+c+'">'+
      fmt(x.ex)+'%p</text>';});
  host.innerHTML='<p style="margin:9px 0 3px;font-size:10.5px;color:#8b93a0">'+
   '오늘 <b style="color:#c9ced6">시장 대비 수익률</b>(%p) · 노란 점선이 코스피예요</p>'+
   '<svg viewBox="0 0 '+W+' '+H+'" style="width:100%;height:auto">'+g+'</svg>';
 }
 function drawChart(my){
  var host=document.getElementById('ms-chart'); if(!host) return;
  var W=360,H=150,L=30,R=10,T=12,B=20;
  var idx=[]; for(var i=0;i<P.days.length;i++){if(P.mkt[i]!=null)idx.push(i);}
  /* 🆕 2026-08-24 HO 지시 — **당일 탭에도 그래프**를 준다.
     [문제] 당일(curW=1)이면 점이 1개라 선을 못 그려서 그래프가 통째로 사라졌다.
            탭을 눌렀는데 화면이 비면 고장으로 보인다.
     [해법] 당일 탭에서는 선 대신 **막대**로 그린다.
            하루치는 '추이'가 아니라 '비교'라서, 종목별 초과수익을 나란히
            세우는 편이 오히려 읽기 쉽다. 형태를 바꿔 정보를 살린다. */
  if(curW<=1){ drawTodayBars(my, host); return; }
  /* 🆕 2026-08-25 HO 지적 — 20일·60일을 눌러도 5일과 같은 그림이 나온다.
     [원인] 쌓인 거래일이 7일뿐이면 slice(-20)도 slice(-60)도 **똑같이 7일**을
            돌려준다. 그래서 탭만 바뀌고 그림은 그대로였다.
     [고침] 요청한 기간과 실제 기간이 다르면 **그 사실을 화면에 쓴다.** */
  var _요청=curW;
  idx=idx.slice(-curW);
  var _부족=(idx.length<_요청);
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
  var _제목=_부족
    ? '시장 대비 초과수익 <b style="color:#e0c060">— '+_요청+'일치를 요청했지만 '+
      '아직 '+idx.length+'거래일만 쌓였어요</b>'
    : '시장 대비 초과수익 <span style="color:#6f7784">('+idx.length+'거래일)</span>';
  host.innerHTML='<p style="margin:9px 0 3px;font-size:10.5px;color:#8b93a0;line-height:1.5">'+
   _제목+'</p>'+
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

 /* 🆕 2026-08-29 HO 지시 — 내 종목 **순서 바꾸기**.
    [WHY] 지금은 등록한 순서대로 고정이라, 비중이 큰 종목이나 오늘 제일
          궁금한 종목이 맨 아래 있으면 매번 스크롤해야 했다.
    ⚠️ 순서는 등록 목록·브리핑·그래프가 **모두 같은 배열**(localStorage의 K)을
       쓰므로, 여기만 바꾸면 세 곳이 한꺼번에 따라온다.
    ⚠️ 드래그가 아니라 ▲▼ 버튼으로 한다 — 모바일에서 드래그는 스크롤과
       충돌해 오작동이 잦고, 라이브러리 없이 만들면 코드가 크게 늘어난다. */
 window.msMove=function(nm,d){
  var my=get(), i=my.indexOf(nm);
  if(i<0) return;
  var j=i+d;
  if(j<0||j>=my.length) return;      // 맨 위에서 ▲, 맨 아래에서 ▼는 무시
  my.splice(j,0,my.splice(i,1)[0]);
  set(my);
  render();   // ⚠️ render()가 목록·그래프·브리핑(drawBrief)·cpFire를 전부 다시 그린다
 };

 /* 내보내기 / 불러오기
    [WHY] localStorage는 기기·브라우저마다 따로다. PC에 넣어도 폰엔 없고,
          카톡·텔레그램 인앱 브라우저는 아예 다른 저장소를 쓴다.
          코드로 막을 수 없으니 **되살릴 수단**을 준다. */
 window.msExport=function(){
  var my=get();
  if(!my.length){alert('먼저 종목을 등록해 주세요.'); return;}
  var code='CP:'+my.join('|');
  var msg='내 관심종목 '+my.length+'종목 백업 코드입니다. 복사해 두었다가 '
        + '다른 기기에서 [불러오기]에 붙여넣으세요.';
  // ⚠️ alert 문구에 줄바꿈을 넣지 않는다. 이 JS는 파이썬 문자열을 거쳐 HTML로
  //    출력되는데, 그 과정에서 이스케이프가 풀려 **문자열 리터럴이 깨진다**
  //    (2026-08-20 실제 사고 — 관심종목 JS 전체가 죽었다).
  var ok=false;
  try{ if(navigator.clipboard){navigator.clipboard.writeText(code); ok=true;} }catch(e){}
  if(ok) alert(msg+' (이미 복사됨) — '+code);
  else prompt(msg, code);
 };
 window.msImport=function(){
  var t=prompt('내보내기로 받은 코드를 붙여넣어 주세요');
  if(!t) return;
  t=t.trim();
  if(t.indexOf('CP:')!==0){alert('코드 형식이 아닙니다. CP: 로 시작해야 합니다.'); return;}
  var names=t.slice(3).split('|').map(function(x){return x.trim();}).filter(Boolean);
  var ok=[], bad=[];
  names.forEach(function(n){
   if(P.stocks[n]){ if(ok.indexOf(n)<0) ok.push(n); } else bad.push(n);
  });
  if(!ok.length){alert('불러올 수 있는 종목이 없습니다.'); return;}
  if(ok.length>MAX) ok=ok.slice(0,MAX);
  set(ok); render();
  alert(ok.length+'종목을 불러왔습니다.'+(bad.length?' (건너뜀: '+bad.join(', ')+')':''));
 };

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
        # 🆕 2026-08-22 — JS는 curW=1(당일)로 시작하는데 화면 강조만 5일에
        #    걸려 있어, 실제로는 당일 값인데 5일 탭이 켜져 보이는 불일치였다.
        f'cursor:pointer;font-weight:{800 if n==1 else 600};'
        f'background:{"#2a3446" if n==1 else "#171c25"};'
        f'color:{"#f0c65a" if n==1 else "#7d848f"};'
        f'-webkit-tap-highlight-color:transparent">{이름}</span>'
        # ⚠️ '당일' 추가(2026-08-20) — 섹터 성적표와 같은 창 구성으로 맞춘다.
    # ⚠️ 다른 코너(섹터 성적표·크기별·수급 타임라인)와 **글자까지 똑같이** 맞춘다.
    #    "이번 주"와 "5일"이 섞이면 같은 기능인 줄 모른다(2026-08-20 지시).
    for n, 이름 in [(1, "당일"), (5, "5일"), (20, "20일"), (60, "60일")])

    return ('<div style="background:#141922;border:1px solid #232a36;border-radius:12px;'
            'padding:13px 14px;margin:10px 0 0">'
            # ⚠️ 큰 제목은 입력창 바로 밑(ms-sug 다음)에 있다. 여기 또 두면 두 번 나온다.
            # 🆕 2026-08-22 HO 지시 — "내 관심종목 등록"이 다른 카드 소제목과
            #    똑같은 크기(11.5px 회색)라 묻혀 보인다. 이 카드는 핵심편의
            #    새 진입점이라 제목을 눈에 띄게 키운다("등록하기"로 행동 유도도 함께).
            '<p style="margin:0 0 6px;font-size:17px;font-weight:800;color:#f0c65a">'
            '📋 내 종목 등록하기</p>'
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
            '<div id="ms-sug" style="display:none;background:#0f131a;border:1px solid #2a3446;'
            'border-radius:8px;margin:0 0 10px;max-height:186px;overflow-y:auto"></div>'
            # ⚠️ 제목을 **입력창 바로 밑**에 둔다(2026-08-18 지시).
            #    등록하자마자 "그래서 내 종목이 이기고 있나"가 바로 이어져야 한다.
            '<p style="margin:13px 0 9px;font-size:17px;font-weight:800;color:#f2f4f7">'
            '내 종목은 시장을 이기고 있나</p>'
            f'<div style="display:flex;gap:6px;margin-bottom:9px">{탭}</div>'
            # 🆕 2026-08-26 — 체크 개수 표시 + 전체/기본 버튼 자리
            '<div id="ms-selbar" style="display:flex;justify-content:space-between;'
            'align-items:center;margin:8px 0 2px;min-height:0"></div>'
            '<div id="ms-list"></div>'
            # ⚠️ 관심종목은 이 기기에만 저장된다. 기기를 바꾸거나 앱 캐시를 지우면
            #    사라진다(브라우저 사양이라 코드로 못 막는다).
            #    → 짧은 코드로 옮겨 담을 수 있게 한다.
            '<div class="ms-bk">'
            '<button onclick="msExport()" class="ms-bk-b">📤 내보내기</button>'
            '<button onclick="msImport()" class="ms-bk-b">📥 불러오기</button>'
            '<span class="ms-bk-t">기기를 바꾸거나 앱 캐시를 지우면 목록이 사라집니다 — '
            '코드를 복사해 두세요</span></div>'
            '<div id="ms-sum"></div><div id="ms-chart"></div>'
            '<details style="margin:10px 0 0;padding:9px 10px;background:#0f131a;'
            'border-radius:8px;border:1px solid #1e2531">'
            '<summary style="font-size:11.5px;color:#e0c060;font-weight:700;'
            'cursor:pointer;list-style:none">📖 내 종목 보는 방법 '
            '<span style="color:#6f7784;font-weight:600">(눌러서 펼치기)</span></summary>'
            '<p style="margin:6px 0 0;font-size:11px;color:#7d848f;line-height:1.65">'
            '<b style="color:#9aa0aa">%p</b>는 코스피보다 얼마나 더 벌었나입니다. '
            '아래 작은 숫자는 실제 수익률, 그 아래는 그 기간 코스피를 이긴 날의 수입니다.<br>'
            '<b style="color:#8fd0e8">파란 태그</b>가 그 종목이 속한 섹터입니다. '
            '한 종목이 두 섹터에 걸치면 <b style="color:#9aa0aa">오늘 더 세게 움직인 섹터</b>가 앞에 옵니다.<br>'
            '<b style="color:#9aa0aa">내 종목 평균</b>은 모든 종목을 같은 금액씩 샀다고 가정한 값입니다. '
            '실제 보유 비중은 받지 않으므로 참고용입니다.<br>'
            '</p></details></div>' + JS
            + '<script>' + 이름배열JS + """
/* 자체 자동완성 (datalist 대체)
   [WHY] 입력창을 누르기만 해도 전 종목 목록이 뜨면 모바일에서 키보드가 가려진다.
         글자를 1자 이상 넣었을 때만, 앞글자 일치 우선으로 최대 8개만 보여준다. */
function msSug(){
  var el=document.getElementById('ms-in'), box=document.getElementById('ms-sug');
  if(!el||!box) return;
  var q=(el.value||'').trim();
  if(!q){ box.style.display='none'; box.innerHTML=''; return; }
  /* 🆕 2026-08-24 HO 지시 — 영문 종목명은 대소문자를 가리지 않는다.
     [WHY] 'kt'를 쳐도 'KT'가, 'SK'를 쳐도 'sk'가 나와야 한다.
           한글은 대소문자 개념이 없어 이 변환의 영향을 받지 않는다.
     ⚠️ 비교만 소문자로 하고, 화면에 보여주는 이름은 원본 그대로 쓴다. */
  var qL=q.toLowerCase();
  var names=(window.CP_NAMES||[]), head=[], part=[];
  for(var i=0;i<names.length;i++){
    var n=names[i], nL=n.toLowerCase();
    if(nL.indexOf(qL)===0){ if(head.length<8) head.push(n); }
    else if(nL.indexOf(qL)>-1){ if(part.length<8) part.push(n); }
  }
  var out=head.concat(part).slice(0,8);
  if(!out.length){ box.style.display='none'; box.innerHTML=''; return; }
  var h='';
  for(var j=0;j<out.length;j++){
    h+='<div class="ms-sug-i" data-n="'+out[j]+'" style="padding:9px 11px;font-size:12.5px;'
      +'color:#e8eaee;cursor:pointer;border-bottom:1px solid #1a2029">'+out[j]+'</div>';
  }
  box.innerHTML=h; box.style.display='block';
}
function msPick(n){
  var el=document.getElementById('ms-in'), box=document.getElementById('ms-sug');
  if(el) el.value=n;
  if(box){ box.style.display='none'; box.innerHTML=''; }
  if(typeof msAdd==='function') msAdd();
}
document.addEventListener('input',function(e){ if(e.target&&e.target.id==='ms-in') msSug(); });
document.addEventListener('click',function(e){
  var it=(e.target&&e.target.closest)?e.target.closest('.ms-sug-i'):null;
  if(it){ msPick(it.getAttribute('data-n')); return; }
  if(!e.target||e.target.id!=='ms-in'){
    var box=document.getElementById('ms-sug');
    if(box) box.style.display='none';
  }
});
""" + '</script>')


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
            '📰 뉴스 · 📄 공시 중 <b>최근 5거래일 안에 그 종목이 언급된 것만</b> 붙습니다. '
            '별일 없는 날은 짧게 끝납니다.</p></div>')


# 🗓️ 섹터 분류 기준 변경 안내 — 이 날짜까지만 띄운다(지나면 자동으로 사라진다).
#   ⚠️ 원칙 3 "틀린 걸 지우지 않는다" — 기준이 바뀌면 조용히 바꾸지 않고 밝힌다.
#   2026-08-22: 구역 배정을 '오늘의 네이버 테마' → '업종(WICS)+수동 핀'으로 바꿨다.
#   그 전에는 S7 테마 때문에 삼성생명이 반도체로, 수소차 테마 때문에 기아가
#   전력·신재생·원전으로 잡혔다. 표본도 6종목 → 166종목으로 늘어 숫자 자체가 달라진다.
SECTOR_RULE_CHANGED = "20260822"
SECTOR_RULE_NOTE_UNTIL = "20260912"      # 3주 뒤 자동 종료


def sector_rule_note():
    """섹터 분류 기준이 바뀌었음을 알리는 안내 상자(기간 지나면 빈 문자열)."""
    try:
        if DATE > SECTOR_RULE_NOTE_UNTIL:
            return ""
    except Exception:
        return ""
    return ('<div style="background:#1a1710;border:1px solid #3d3320;border-radius:10px;'
            'padding:11px 12px;margin:0 0 10px">'
            '<p style="margin:0 0 4px;font-size:12px;font-weight:700;color:#f0c65a">'
            '🗓️ 2026-08-22부터 섹터 분류 기준이 바뀌었습니다</p>'
            '<p style="margin:0;font-size:11.5px;color:#c9ced6;line-height:1.6">'
            '예전에는 <b>그날의 네이버 테마</b>로 섹터를 정했습니다. 그래서 삼성생명이 '
            '<b>반도체</b>에, 기아·현대차가 <b>전력·신재생·원전</b>에 들어가는 일이 있었습니다. '
            '이제는 <b>업종(표준 산업분류)</b>을 주소로 씁니다. '
            '섹터당 종목 수가 크게 늘어(예: 반도체 6종목 → 166종목) '
            '<b>이전 리포트의 섹터 숫자와는 이어지지 않습니다.</b> '
            '지난 기록을 지우지 않고 그대로 두되, 이 점을 밝혀둡니다.</p></div>')


_ZONE_MEM_CACHE = {}


def _zone_members():
    """{섹터명: [(종목명, 등락률), ...]} — 오늘 격자에서 대표 종목을 뽑아 둔다.

    🆕 2026-08-22 — 「돌아올 섹터」·「섹터 성적표」에서 섹터명을 누르면
       그 섹터에 뭐가 들었는지 보여주기 위한 재료. 섹터 지도(격자)가
       이미 쓰는 계좌격자.행의 칸별 '종목'을 그대로 재활용한다 —
       새 수집이 전혀 필요 없다.
    """
    if _ZONE_MEM_CACHE:
        return _ZONE_MEM_CACHE
    try:
        일 = archive_days(1)
        if not 일:
            return {}
        _, d = 일[-1]
        for r in ((d.get("계좌격자") or {}).get("행") or []):
            nm = r.get("테마")
            if not nm:
                continue
            목록 = []
            for 층 in ("대형", "중형", "소형"):
                for x in ((r.get("칸") or {}).get(층) or {}).get("종목") or []:
                    if x.get("명") is not None:
                        목록.append((x["명"], x.get("등")))
            if 목록:
                목록.sort(key=lambda t: -(t[1] if isinstance(t[1], (int, float)) else -99))
                _ZONE_MEM_CACHE[nm] = 목록
    except Exception as e:
        print(f"   ⚠️ 섹터 구성종목 준비 실패 — {type(e).__name__} (코너는 그대로 동작)")
    return _ZONE_MEM_CACHE


def zone_member_panel(섹터명, pid, 최대=8, 여백=95):
    """섹터명을 눌렀을 때 펼쳐지는 대표 종목 패널. 종목이 없으면 빈 문자열.

    여백: 왼쪽 들여쓰기(px). 돌아올 섹터는 이름칸 폭(95)에 맞추고,
          섹터 성적표는 행 전체 폭을 쓰므로 0으로 준다.
    """
    목록 = (_zone_members().get(섹터명) or [])[:최대]
    if not 목록:
        return ""
    칩 = "".join(
        f'<span style="display:inline-block;font-size:10.5px;color:#d5d9e0;'
        f'background:#141922;border:1px solid #232a36;border-radius:5px;'
        f'padding:2px 7px;margin:0 4px 4px 0;white-space:nowrap">{n} '
        f'<b style="color:{"#ff6b4a" if (v or 0) >= 0 else "#5b9bff"}">'
        f'{(v or 0):+.1f}%</b></span>'
        for n, v in 목록)
    return (f'<div id="{pid}" style="display:none;margin:2px 0 8px {여백}px;'
            f'padding:8px 9px;background:#0f131a;border-radius:6px">'
            f'<p style="margin:0 0 5px;font-size:10.5px;color:#e0c060;font-weight:700">'
            f'{섹터명} 대표 종목 '
            f'<span style="color:#6f7784;font-weight:600">· 다시 누르면 닫혀요</span></p>'
            f'<div>{칩}</div></div>')


ZTOG_JS = ('<script>function ztog(id){var e=document.getElementById(id);'
           'if(e)e.style.display=(e.style.display==="none"?"block":"none");}</script>')

# 🆕 2026-08-22 — "누르면 종목이 나온다"는 신호.
#    섹터 지도 / 섹터 성적표 / 돌아올 섹터 **세 곳이 똑같은 모양**을 써야
#    구독자가 "아, 이거 누르는 거구나"를 한 번만 배우고 전부에 적용할 수 있다.
#    원래 섹터 지도에만 있던 금색 ▾를 기준으로 삼되, 9px은 작아서 안 보인다는
#    지적으로 12px로 키웠다. 세 곳 모두 이 상수 하나만 쓴다 — 따로 쓰면 또 어긋난다.
ZONE_ARROW = ('<span style="color:#e0c060;font-size:12px;font-weight:900;'
              'flex:none;margin-left:3px">&nbsp;▾</span>')


_ZONE_TODAY_STAT = {}


def _zone_today_stat():
    """오늘 격자 행에서 {섹터: {중앙값, 평균, 확산도, 종목수}}.

    ⚠️ 2026-08-25 이전 archive에는 '확산도'·'평균' 키가 없다.
       없으면 조용히 빼고 있는 것만 보여준다(빈칸이 거짓말보다 낫다).
    """
    if _ZONE_TODAY_STAT:
        return _ZONE_TODAY_STAT
    try:
        for _, d in archive_days(1):
            for r in ((d.get("계좌격자") or {}).get("행") or []):
                nm = r.get("테마")
                if not nm:
                    continue
                _ZONE_TODAY_STAT[nm] = {"중앙값": r.get("전체"),
                                        "평균": r.get("평균"),
                                        "확산도": r.get("확산도"),
                                        "종목수": r.get("종목수")}
    except Exception as e:
        print(f"   ⚠️ 섹터 통계 읽기 실패 — {type(e).__name__}")
    return _ZONE_TODAY_STAT


def _확산도최고():
    """오늘 전 섹터 중 최고 확산도. 없으면 None."""
    vals = [v.get("확산도") for v in _zone_today_stat().values()
            if isinstance(v.get("확산도"), (int, float))]
    return max(vals) if vals else None


# ══════════════════════════════════════════════════════════════
# 🛫 항로도 — 최근 코스피 흐름 → 지금 위치 → 특징 (2026-08-25 신설)
# ══════════════════════════════════════════════════════════════
#  HO 기획 — "어제까지 무슨 일이 있었는지(맥락), 오늘이 그 흐름의 어디인지(위치),
#             그래서 내일 뭘 하라는 건지(행동)"
#
#  ⚠️ 이 코너의 값어치는 **"몇 번째냐"**에 있다.
#     다른 시황은 "오늘 3% 빠졌습니다"로 끝난다. 항로도는
#     "이 낙폭은 올해 3번째이고, 앞선 두 번은 2일·4일 만에 멈췄습니다"라고 말한다.
#     이건 기록을 쌓지 않은 곳은 흉내낼 수 없다. 오래될수록 강해진다.
#
#  ⚠️ 확정된 규칙 (HO 승인 2026-08-25)
#     · 문턱      = 20일 안에서 최고/최저  (대략 20일에 한 번꼴로 걸린다)
#     · 최대 개수 = 2개  (3개 이상 걸려도 강한 순으로 둘만)
#     · 표본      = 3회부터 빈도 문장을 낸다. 그 미만은 "N번째"만 말한다
#                   (3회일 땐 "통계가 아니라 사례"라고 밝힌다)
ROUTE_창 = 20            # '평소'의 기준이 되는 되돌아보기 구간(거래일)
ROUTE_최대 = 2           # 하루에 보여줄 특징 개수
ROUTE_최소표본 = 3       # 이보다 적으면 빈도 문장을 내지 않는다
ROUTE_그래프일수 = 20    # 미니 차트에 그릴 거래일


def _route_rows():
    """market_history에서 거래일 행만 뽑아 오래된 순으로."""
    try:
        with open("market_history.json", encoding="utf-8") as f:
            일별 = (json.load(f) or {}).get("일별") or []
    except Exception as e:
        print(f"   ⚠️ 항로도 — 시장 이력 읽기 실패({type(e).__name__})")
        return []
    out = []
    본 = set()
    for r in 일별:
        d = str(r.get("날짜") or "").replace("-", "")
        if len(d) != 8 or d in 본:
            continue
        if not isinstance(r.get("코스피"), (int, float)):
            continue
        본.add(d)
        r = dict(r)
        r["_ymd"] = d
        out.append(r)
    out.sort(key=lambda x: x["_ymd"])
    return out


def _route_features(rows):
    """오늘의 '특징'을 강한 순으로 뽑는다.

    각 특징 = {강도, 제목, 설명, 같은사례[과거 인덱스…]}
    ⚠️ 없는 특징은 만들지 않는다. 평범한 날은 빈 리스트가 정답이다.
    """
    if len(rows) < 5:
        return []
    오늘 = rows[-1]
    등락 = [r.get("코스피등락") for r in rows]
    종가 = [r.get("코스피") for r in rows]
    창 = rows[-ROUTE_창:]
    특징 = []

    # ── ① 연속 상승/하락 ──
    방향 = 1 if (등락[-1] or 0) > 0 else (-1 if (등락[-1] or 0) < 0 else 0)
    연속 = 0
    if 방향:
        for v in reversed(등락):
            if v is None or (v > 0) != (방향 > 0) or v == 0:
                break
            연속 += 1
    if 연속 >= 3:
        말 = "올랐습니다" if 방향 > 0 else "빠졌습니다"
        # 과거에 같은 길이 이상의 연속이 있었던 지점
        사례 = []
        run = 0
        for i, v in enumerate(등락):
            if v is None or v == 0 or (v > 0) != (방향 > 0):
                run = 0
                continue
            run += 1
            if run == 연속 and i != len(등락) - 1:
                사례.append(i)
        특징.append({"강도": 80 + 연속, "제목": f"{연속}일 연속 {'상승' if 방향>0 else '하락'}",
                     "설명": f"코스피가 {연속}거래일 내리 {말}", "사례": 사례})

    # ── ② 20일 고점/저점 대비 ──
    유효 = [(i, v) for i, v in enumerate(종가) if isinstance(v, (int, float))]
    if len(유효) >= 5:
        창유효 = 유효[-ROUTE_창:]
        고 = max(창유효, key=lambda x: x[1])
        저 = min(창유효, key=lambda x: x[1])
        현 = 유효[-1][1]
        낙폭 = (현 - 고[1]) / 고[1] * 100
        상승폭 = (현 - 저[1]) / 저[1] * 100
        if 낙폭 <= -3 and 고[0] != 유효[-1][0]:
            특징.append({"강도": 70 + min(20, abs(낙폭)),
                         "제목": f"{ROUTE_창}일 고점 대비 {낙폭:.1f}%",
                         "설명": f"{ROUTE_창}거래일 중 가장 높았던 자리에서 "
                                 f"{abs(낙폭):.1f}% 내려와 있습니다", "사례": []})
        elif 상승폭 >= 3 and 저[0] != 유효[-1][0]:
            특징.append({"강도": 70 + min(20, 상승폭),
                         "제목": f"{ROUTE_창}일 저점 대비 +{상승폭:.1f}%",
                         "설명": f"{ROUTE_창}거래일 중 가장 낮았던 자리에서 "
                                 f"{상승폭:.1f}% 올라와 있습니다", "사례": []})

    # ── ③ 등락률 이상치 — 기록 전체에서 몇 번째인가 ──
    오늘등락 = 등락[-1]
    if isinstance(오늘등락, (int, float)) and abs(오늘등락) >= 1.0:
        같은편 = [v for v in 등락[:-1]
                 if isinstance(v, (int, float)) and (v > 0) == (오늘등락 > 0)]
        더큰 = sum(1 for v in 같은편 if abs(v) > abs(오늘등락))
        순위 = 더큰 + 1
        창등락 = [v for v in [r.get("코스피등락") for r in 창][:-1]
                 if isinstance(v, (int, float))]
        창최고 = 창등락 and abs(오늘등락) > max(abs(v) for v in 창등락)
        if 창최고 or 순위 <= 3:
            방 = "상승" if 오늘등락 > 0 else "하락"
            꼬리 = (f"기록 {len(등락)}거래일 중 {순위}번째로 큰 {방}폭"
                   if 순위 <= 5 else f"{ROUTE_창}일 안에서 가장 큰 {방}폭")
            특징.append({"강도": 90 if 순위 == 1 else 75,
                         "제목": f"오늘 {오늘등락:+.2f}% — {ROUTE_창}일 최대 {방}",
                         "설명": 꼬리, "사례": []})

    # ── ④ 수급 이상치 (실탄이 평소 대비) ──
    실 = [r.get("실탄") for r in rows if isinstance(r.get("실탄"), (int, float))]
    if len(실) >= 6:
        오늘실 = 실[-1]
        과거 = [abs(v) for v in 실[:-1][-ROUTE_창:]]
        평소 = sum(과거) / len(과거) if 과거 else 0
        if 평소 and abs(오늘실) >= 평소 * 2:
            특징.append({"강도": 72,
                         "제목": f"실탄이 평소의 {abs(오늘실)/평소:.1f}배",
                         # ⚠️ _flow_amt는 부호를 붙인다. abs()를 넘기면
                         #    "+4.96조 (순매도)"처럼 **모순된 문장**이 나온다.
                         #    방향은 말로만 쓰고 숫자는 크기만 보여준다.
                         "설명": f"외국인·기관 합이 "
                                 f"{'순매수' if 오늘실>=0 else '순매도'} "
                                 f"{_flow_amt(abs(오늘실)).lstrip('+')}로 "
                                 f"최근 평균보다 훨씬 큽니다", "사례": []})

    # ── ⑤ 사이드카·서킷 (2026-08-25부터 적재) ──
    조치 = 오늘.get("시장조치")
    if 조치:
        과거조치 = sum(1 for r in rows[:-1] if r.get("시장조치"))
        특징.append({"강도": 99, "제목": " · ".join(조치),
                     "설명": f"기록상 {과거조치 + 1}번째입니다", "사례": []})

    특징.sort(key=lambda x: -x["강도"])
    return 특징[:ROUTE_최대]


def _route_spark(rows):
    """코스피 20일 미니 차트 — 종가 선 + 오늘 점."""
    유효 = [(r["_ymd"], r["코스피"]) for r in rows
           if isinstance(r.get("코스피"), (int, float))][-ROUTE_그래프일수:]
    if len(유효) < 4:
        return ""
    vals = [v for _, v in 유효]
    hi, lo = max(vals), min(vals)
    rng = (hi - lo) or 1
    W, H, T, B = 320, 62, 8, 14
    n = len(vals)
    pts = []
    for i, v in enumerate(vals):
        x = 4 + i * (W - 8) / max(1, n - 1)
        y = T + (hi - v) / rng * (H - T - B)
        pts.append((x, y))
    선 = " ".join(f"{x:.0f},{y:.0f}" for x, y in pts)
    lx, ly = pts[-1]
    첫, 끝 = 유효[0][0], 유효[-1][0]
    return (f'<svg viewBox="0 0 {W} {H}" style="width:100%;height:auto;margin:6px 0 2px">'
            f'<polyline points="{선}" fill="none" stroke="#f0c65a" stroke-width="2"/>'
            f'<circle cx="{lx:.0f}" cy="{ly:.0f}" r="3.5" fill="#f0c65a"/>'
            f'<text x="4" y="{H-3}" font-size="8" fill="#6f7784">'
            f'{첫[4:6]}/{첫[6:]}</text>'
            f'<text x="{W-4}" y="{H-3}" font-size="8" fill="#6f7784" '
            f'text-anchor="end">{끝[4:6]}/{끝[6:]}</text></svg>')


def build_route_map():
    """🛫 항로도 — 흐름 그림 + 오늘의 특징."""
    rows = _route_rows()
    if len(rows) < 5:
        return ""
    특징 = _route_features(rows)
    그림 = _route_spark(rows)
    if not 그림:
        return ""
    if 특징:
        블록 = ""
        for f in 특징:
            사례수 = len(f.get("사례") or [])
            꼬리 = ""
            if 사례수:
                if 사례수 + 1 >= ROUTE_최소표본:
                    꼬리 = (f'<span class="rt-freq">기록상 {사례수 + 1}번째 · '
                           f'앞선 {사례수}번의 그 뒤는 아래 참고</span>')
                else:
                    꼬리 = (f'<span class="rt-freq">기록상 {사례수 + 1}번째 — '
                           f'표본이 적어 아직 통계가 아니라 사례입니다</span>')
            블록 += (f'<div class="rt-item"><p class="rt-t">{f["제목"]}</p>'
                     f'<p class="rt-d">{f["설명"]}</p>{꼬리}</div>')
    else:
        # ⚠️ 특징이 없으면 억지로 만들지 않는다. 그것 자체가 정보다.
        블록 = ('<div class="rt-item"><p class="rt-d">'
                '오늘은 특별히 튀는 구간이 없었어요. '
                '평소 범위 안에서 움직인 하루입니다.</p></div>')
    return (f'<div class="rt-box"><p class="rt-h">🛫 지금 코스피는 어느 구간인가</p>'
            f'{그림}{블록}'
            f'<p class="rt-note">📌 과거에 이런 구간이 몇 번 있었는지를 세어 알려드려요. '
            f'앞으로 어떻게 된다는 예측이 아니라 <b>기록상의 빈도</b>입니다. '
            f'기록이 쌓일수록 이 자리는 촘촘해집니다.</p></div>')


# ══════════════════════════════════════════════════════════════
# 🔍 오늘 이상했던 것 — 남들이 안 보는 각도 (2026-08-25 신설)
# ══════════════════════════════════════════════════════════════
#  HO 지시 — 「다음 거래일 예보」를 빼고 이 자리를 대신한다.
#
#  ⚠️ 왜 예보를 뺐나
#     Claude에게 오늘 숫자만 주고 내일을 말하라고 시킨 구조라
#     "3조 넘으면 이탈 지속" 같은 **상식 재진술**이 나왔다.
#     핵심편 한가운데는 리포트의 얼굴인데 가장 확신 없는 코너가 앉아 있었다.
#
#  ⚠️ 이 코너의 정체성 — **예측하지 않는다. 대신 남들이 안 보는 걸 짚는다.**
#     시황은 전부 '움직인 것'으로 쓴다. 그런데 순환매에서 다음 순번은
#     대개 **안 움직인 것**에서 나온다. 거기가 우리 자리다.
#
#  ⚠️ 억지로 만들지 않는다. 걸리는 게 없으면 코너 자체를 띄우지 않는다.
#     매일 뭔가를 말하려 들면 그 순간 이 코너도 예보와 같아진다.
ODD_최대 = 2          # 하루에 보여줄 개수
ODD_확산_고 = 65      # 이 이상이면 '고르게 올랐다'
ODD_확산_저 = 35      # 이 이하면 '고르게 밀렸다'


def _odd_market():
    """오늘 코스피·코스닥 등락률."""
    try:
        for _, d in archive_days(1):
            지 = (d.get("지수수급") or {}).get("지수") or {}
            def _f(x):
                try:
                    return float(str(x).replace(",", ""))
                except Exception:
                    return None
            return (_f((지.get("코스피") or {}).get("등락률")),
                    _f((지.get("코스닥") or {}).get("등락률")))
    except Exception:
        pass
    return None, None


def _odd_items(data=None):
    """이상 신호 목록만 돌려준다(렌더 없이).

    🆕 2026-08-26 — 「오늘 이것만 확실히 기억합시다」가 같은 판정을 써야 해서
       감지부와 렌더부를 나눴다. 같은 로직을 두 벌 두면 언젠가 어긋난다.
    """
    코, 닥 = _odd_market()
    통계 = _zone_today_stat()
    if not 통계:
        return []
    항목 = []

    # ── ① 시장과 반대로 간 자리 ──
    #   코스피가 크게 빠진 날 '고르게 오른' 섹터. 시황이 절대 안 다루는 자리다.
    if isinstance(코, (int, float)) and abs(코) >= 1.0:
        for nm, v in 통계.items():
            if nm == "기타":          # 잡동사니 묶음은 제외(위 주석 참조)
                continue
            확 = v.get("확산도")
            중 = v.get("중앙값")
            n = v.get("종목수")
            if not isinstance(확, (int, float)) or not isinstance(중, (int, float)):
                continue
            if 코 < 0 and 확 >= ODD_확산_고 and 중 > 0:
                항목.append({
                    "강도": 90 + (확 - ODD_확산_고),
                    "제목": f"다 빠지는데 안 빠진 곳 — {nm}",
                    "본문": f"코스피가 {코:+.2f}%인 날인데 <b>{nm}</b>은 "
                            f"{n}종목 중 <b>{확:.0f}%</b>가 올랐어요"
                            f"(가운데 종목 {중:+.2f}%).",
                    "뜻": "시장 전체가 밀리는 날 이렇게 고르게 버틴 자리는, "
                          "돈이 빠져나간 게 아니라 <b>남아 있었다</b>는 뜻이에요. "
                          "순환매에서는 이런 자리가 다음 순번이 되기도 해요."})
            elif 코 > 0 and 확 <= ODD_확산_저 and 중 < 0:
                항목.append({
                    "강도": 88 + (ODD_확산_저 - 확),
                    "제목": f"다 오르는데 못 오른 곳 — {nm}",
                    "본문": f"코스피가 {코:+.2f}%인 날인데 <b>{nm}</b>은 "
                            f"{n}종목 중 오른 게 <b>{확:.0f}%</b>뿐이에요"
                            f"(가운데 종목 {중:+.2f}%).",
                    "뜻": "시장이 오르는데 이 자리만 비켜갔다면 "
                          "<b>아직 순번이 안 온 것</b>일 수도, "
                          "이유가 따로 있는 것일 수도 있어요."})

    # ── ② 겉과 속이 다른 섹터 ──
    #   중앙값은 낮은데 확산도가 높으면 "조용히 다 같이" 오른 것이고,
    #   중앙값은 높은데 확산도가 낮으면 "몇 종목이 끌어올린" 것이다.
    for nm, v in 통계.items():
        # 🆕 2026-08-26 — 「기타」는 어느 섹터에도 안 걸린 **잡동사니 묶음**이다.
        #    1,000종목이 한 칸에 들어 있어 확산도가 늘 시장 평균처럼 나온다.
        #    "기타가 고르게 올랐다"는 통찰이 아니라 소음이라 뺀다.
        if nm == "기타":
            continue
        확, 중, n = v.get("확산도"), v.get("중앙값"), v.get("종목수")
        평 = v.get("평균")
        if not all(isinstance(x, (int, float)) for x in (확, 중, 평)):
            continue
        if 평 - 중 >= 1.5 and 확 < 55:
            항목.append({
                "강도": 78 + (평 - 중),
                "제목": f"소수가 끌어올린 자리 — {nm}",
                "본문": f"<b>{nm}</b> 평균은 {평:+.2f}%인데 가운데 종목은 "
                        f"{중:+.2f}%예요. 오른 종목은 {확:.0f}%뿐이고요.",
                "뜻": "평균만 보면 좋아 보이지만 <b>몇 종목이 만든 숫자</b>예요. "
                      "이런 날 섹터를 통째로 사면 평균과 다른 결과가 나옵니다."})
        elif 중 - 평 >= 1.0 and 확 >= 60:
            항목.append({
                "강도": 76 + (중 - 평),
                "제목": f"조용히 같이 오른 자리 — {nm}",
                "본문": f"<b>{nm}</b>은 튀는 종목 없이 {n}종목 중 "
                        f"<b>{확:.0f}%</b>가 함께 올랐어요(가운데 {중:+.2f}%).",
                "뜻": "한두 종목이 끌어올린 게 아니라 <b>자리 전체가 움직인</b> 날이에요. "
                      "이런 상승이 대체로 더 오래 갑니다."})

    # ── ③ 코스피·코스닥이 갈린 날 ──
    if isinstance(코, (int, float)) and isinstance(닥, (int, float)):
        격차 = 닥 - 코
        if abs(격차) >= 2.0:
            큰, 작 = ("코스닥", "코스피") if 격차 > 0 else ("코스피", "코스닥")
            항목.append({
                "강도": 85,
                "제목": f"지수가 갈렸어요 — {큰} 쪽으로",
                "본문": f"코스피 {코:+.2f}% · 코스닥 {닥:+.2f}%로 "
                        f"<b>{abs(격차):.1f}%p</b> 벌어졌어요.",
                "뜻": "두 지수가 이만큼 갈리는 날은 <b>대형주와 중소형주에 서로 다른 돈</b>이 "
                      "움직인 날이에요. 내 종목이 어느 쪽인지가 오늘 성적을 갈랐을 거예요."})

    항목.sort(key=lambda x: -x["강도"])
    return 항목[:ODD_최대]


def build_odd_today():
    """🙈 2026-08-26 — 「오늘 이것만 확실히 기억합시다」가 이 내용을 흡수했다.

    ⚠️ HO 지시로 별도 코너를 없앴다. 같은 이야기를 두 자리에서 하면
       둘 다 힘을 잃는다(원칙 4 — 중복해서 말하지 않는다).
    ⚠️ 감지 로직(_odd_items)은 그대로 살아 있고 요약 코너가 쓴다.
       다시 독립 코너로 되살리려면 이 함수만 예전처럼 렌더하면 된다.
    """
    return ""


# ══════════════════════════════════════════════════════════════
# 🧩 여기까지 정리하면 — 중간 요약 (2026-08-26 신설, HO 기획)
# ══════════════════════════════════════════════════════════════
#  HO 기획 — "대부분 여기까지 읽고 머리에 정리가 안 되거든? 어느 정도 정리가
#             된 후에 섹터와 종목으로 넘어가면 좋을 것 같아서."
#
#  ⚠️ 이 코너의 성격 — **새 정보를 주지 않는다.** 위에서 이미 말한 것들을
#     한 문장씩으로 줄여 다시 세워주는 자리다. 새 걸 넣으면 요약이 아니라
#     또 하나의 코너가 되고, 독자는 다시 복잡해진다.
#  ⚠️ 숫자는 기계가 만든 것만 쓴다(Claude 미개입). 요약이 원문과 어긋나면
#     그게 가장 나쁜 사고다.
#  ⚠️ 아주 쉬운 말로. 여기가 막히면 아래 섹터·종목을 못 읽는다.
def build_midsummary(data, 해석):
    """🧠 오늘 이것만 확실히 기억합시다 — 핵심만 남기는 중간 정리.

    🆕 2026-08-26 HO 지시 — 이름·성격을 바꿨다.
       "꼭 알아야 하는 정보를 기억하는 것이 중요하다. 위의 모든 정보를
        주지 않아도 된다. 핵심적인 부분만 다뤄도 된다."
    ⚠️ 그래서 **나열을 버리고 3가지로 줄인다.**
       ① 오늘 무슨 날이었나 (한 문장)
       ② 돈이 어디로 갔나 (섹터 + 왜 그게 의미 있는지)
       ③ 이상했던 것 하나 (남들이 안 보는 각도 — 「오늘 이상했던 것」 흡수)
    ⚠️ 각 줄마다 **"그래서 뭘 기억하면 되는지"**를 반드시 붙인다.
       숫자만 다시 말하면 요약이 아니라 반복이다.
    ⚠️ 숫자는 기계가 만든 것만. 없는 건 그 줄을 통째로 빼고 지어내지 않는다.
    """
    핵심 = (해석 or {}).get("핵심편") or {}
    줄 = []

    def _f(x):
        try:
            return float(str(x).replace(",", "").replace("%", ""))
        except Exception:
            return None

    지 = (data.get("지수수급") or {}).get("지수") or {}
    코 = _f((지.get("코스피") or {}).get("등락률"))
    닥 = _f((지.get("코스닥") or {}).get("등락률"))

    # ── ① 오늘은 어떤 날이었나 ──
    정의 = (핵심.get("오늘의정의") or "").strip()
    if 정의 or 코 is not None:
        본문 = f"<b>{정의}</b>" if 정의 else ""
        if 코 is not None and 닥 is not None:
            _지수말 = f"코스피 {코:+.2f}% · 코스닥 {닥:+.2f}%"
            본문 = (본문 + f'<br><span class="ms-num">{_지수말}</span>') if 본문 else _지수말
        if 코 is not None and 닥 is not None and (코 >= 0) != (닥 >= 0):
            기억 = ("큰 회사와 작은 회사에 <b>서로 다른 돈</b>이 움직인 날이에요. "
                   "내 종목이 어느 쪽인지가 오늘 성적을 갈랐어요.")
        elif 코 is not None:
            기억 = ("시장 전체가 같은 방향이었어요. "
                   "오늘 내 종목이 반대로 갔다면 <b>종목 자체의 이유</b>가 있다는 뜻이에요.")
        else:
            기억 = ""
        줄.append(("1", "오늘은 이런 날", 본문, 기억))

    # ── ② 돈이 간 자리 ──
    try:
        통 = _zone_today_stat()
        후보 = [(nm, v) for nm, v in 통.items()
               if isinstance(v.get("중앙값"), (int, float)) and nm != "기타"]
        if 후보:
            후보.sort(key=lambda x: -x[1]["중앙값"])
            nm, v = 후보[0]
            확 = v.get("확산도")
            본문 = (f'<b>{nm}</b>로 갔어요'
                   f'<br><span class="ms-num">가운데 종목 {v["중앙값"]:+.2f}%'
                   + (f' · {v.get("종목수","")}종목 중 {확:.0f}% 상승' if isinstance(확, (int, float)) else '')
                   + '</span>')
            if isinstance(확, (int, float)) and 확 >= 65:
                기억 = ("몇 종목이 아니라 <b>자리 전체</b>가 올랐어요. "
                       "이런 상승이 보통 더 오래 갑니다.")
            elif isinstance(확, (int, float)) and 확 < 50:
                기억 = ("<b>몇 종목만</b> 끌어올린 자리예요. "
                       "섹터를 통째로 사면 평균과 다른 결과가 나올 수 있어요.")
            else:
                기억 = "이 자리가 며칠 이어지는지가 주도주인지 아닌지를 가릅니다."
            줄.append(("2", "돈은 여기로", 본문, 기억))
    except Exception:
        pass

    # ── ③ 이상했던 것 (기존 「오늘 이상했던 것」을 흡수) ──
    try:
        특 = (_odd_items(data) or [])
        if 특:
            it = 특[0]
            줄.append(("3", "그런데 이상한 게",
                       f'<b>{it["제목"]}</b><br><span class="ms-num">'
                       f'{re.sub(r"<[^>]+>", "", it["본문"])}</span>',
                       it["뜻"]))
    except Exception:
        pass

    if len(줄) < 2:
        return ""
    본문 = "".join(
        f'<div class="ms-row"><span class="ms-no">{i}</span>'
        f'<div class="ms-txt"><p class="ms-k">{k}</p>'
        f'<p class="ms-v">{v}</p>'
        + (f'<p class="ms-t">👉 {t}</p>' if t else '')
        + '</div></div>'
        for i, k, v, t in 줄)
    return (f'<div class="ms-box"><p class="ms-h">🧠 오늘 이것만 확실히 기억합시다</p>'
            f'<p class="ms-s">위에 숫자가 많았죠? 정말 기억할 건 이 {len(줄)}가지예요.</p>'
            f'{본문}'
            f'<p class="ms-note">여기까지가 <b>시장 이야기</b>예요. '
            f'이제 <b>내 종목</b>은 어땠는지 보러 갈게요 👇</p></div>')


KSIC_중분류 = {
    "01": "농업", "03": "어업", "05": "석탄 광업", "06": "원유·천연가스",
    "07": "금속 광업", "08": "비금속광물 광업",
    "10": "식료품 제조", "11": "음료 제조", "12": "담배 제조",
    "13": "섬유제품 제조", "14": "의복·의류 제조", "15": "가죽·가방·신발 제조",
    "16": "목재·나무제품 제조", "17": "펄프·종이 제조", "18": "인쇄·기록매체",
    "19": "석유정제품 제조", "20": "화학물질·화학제품 제조",
    "21": "의약품 제조", "22": "고무·플라스틱 제조", "23": "비금속 광물제품 제조",
    "24": "1차 금속 제조", "25": "금속가공제품 제조",
    "26": "전자부품·컴퓨터·통신장비 제조", "27": "의료·정밀·광학기기 제조",
    "28": "전기장비 제조", "29": "기계·장비 제조",
    "30": "자동차·트레일러 제조", "31": "기타 운송장비 제조",
    "32": "가구 제조", "33": "기타 제품 제조", "34": "산업용 기계 수리",
    "35": "전기·가스·증기 공급", "36": "수도업", "37": "하수·폐수 처리",
    "38": "폐기물 수집·처리", "39": "환경 정화·복원",
    "41": "종합 건설", "42": "전문직별 공사",
    "45": "자동차 판매·수리", "46": "도매·상품중개", "47": "소매업",
    "49": "육상 운송", "50": "수상 운송", "51": "항공 운송", "52": "창고·운송 서비스",
    "55": "숙박업", "56": "음식점·주점",
    "58": "출판업", "59": "영상·음향 제작·배급", "60": "방송업",
    "61": "통신업", "62": "컴퓨터 프로그래밍·시스템 통합",
    "63": "정보서비스업",
    "64": "금융업", "65": "보험업", "66": "금융·보험 관련 서비스",
    "68": "부동산업",
    "70": "연구개발업", "71": "전문서비스업", "72": "건축기술·엔지니어링",
    "73": "기타 과학기술 서비스", "74": "전문·과학·기술 서비스",
    "75": "사업시설 관리", "76": "임대업",
    "84": "공공행정", "85": "교육 서비스",
    "86": "보건업", "87": "사회복지 서비스",
    "90": "창작·예술·여가", "91": "스포츠·오락",
    "94": "협회·단체", "95": "수리업", "96": "기타 개인 서비스",
}


_TODAY_DATA_CACHE = {}


def _today_data():
    """오늘 data_*.json 전체. _zone_today_stat()과 같은 방식으로 한 번만 읽는다."""
    if _TODAY_DATA_CACHE:
        return _TODAY_DATA_CACHE.get("d") or {}
    try:
        for _, d in archive_days(1):
            _TODAY_DATA_CACHE["d"] = d
    except Exception as e:
        print(f"   ⚠️ 오늘 데이터 읽기 실패 — {type(e).__name__}")
        _TODAY_DATA_CACHE["d"] = {}
    return _TODAY_DATA_CACHE.get("d") or {}


def _zone_themes(구역명, 최대=3):
    """그 섹터를 오늘 실제로 이끈 **네이버 테마** 이름들.

    🆕 2026-08-26 — 섹터(15칸)는 «몇 달간 돈이 어디로 도는가»를 재는 안 바뀌는
    주소다. 그런데 그것만 말하면 «어느 반도체냐»가 빠진다. 실측 8/25 반도체 섹터
    안에서 HBM·CXL·소캠·온디바이스 AI 네 테마가 동시에 뛰었고, 정작 삼성전자는
    0.00%였다. 같은 섹터를 든 두 사람이 완전히 다른 하루를 보낸 것이다.

    [원칙] 섹터를 쪼개지 않는다 — 쪼개면 「돌아올 섹터」 등판 횟수와 항로도 표본이
           전부 0으로 되돌아간다. 대신 **섹터와 테마 사이를 이어준다.**
    ⚠️ data["주도섹터"]에 «계좌구역»과 «테마명»이 이미 같이 저장돼 있다 — 새 수집 0회.
    ⚠️ 오른 테마만 쓴다. 섹터가 1위인데 내린 테마를 «이끌었다»고 할 수는 없다.
    """
    data = _today_data()
    try:
        _cands = []
        for t in (data.get("주도섹터") or []):
            if (t or {}).get("계좌구역") != 구역명:
                continue
            _nm = t.get("테마명")
            _up = t.get("테마등락")
            if _nm and isinstance(_up, (int, float)) and _up > 0:
                _cands.append((float(_up), _nm))
        _cands.sort(reverse=True)
        _seen, _out = set(), []
        for _, _nm in _cands:
            if _nm in _seen:
                continue
            _seen.add(_nm)
            _out.append(_nm)
            if len(_out) >= 최대:
                break
        return _out
    except Exception:
        return []


def _zone_size_split(구역명):
    """그 섹터 안에서 **대형·중형·소형 중 어디가 이끌었나**.

    🆕 2026-08-26 — «반도체 +3.9%»만 보면 삼성전자를 든 사람은 «내 건 왜 안 갔지»가
    된다. 실측 8/25 반도체: 대형 +3.69%(삼성전자 0.00·하이닉스 +0.42)인데
    중형 +5.25%였다. **같은 자리를 사도 크기가 다르면 다른 하루**였다.
    ⚠️ data["계좌격자"]에 이미 칸별 등락률이 있다 — 새 수집 0회.
    ⚠️ 종목이 3개 미만인 칸은 버린다. 한두 종목이 만든 숫자를 «크기의 특징»이라
       부르면 그게 곧 착시다(섹터 순위에서 평균을 버린 것과 같은 이유).
    """
    data = _today_data()
    try:
        for 행 in ((data.get("계좌격자") or {}).get("행") or []):
            if (행 or {}).get("테마") != 구역명:
                continue
            _칸 = 행.get("칸") or {}
            _vals = []
            for _k in ("대형", "중형", "소형"):
                _c = _칸.get(_k) or {}
                _v, _n = _c.get("등락률"), _c.get("종목수") or 0
                if isinstance(_v, (int, float)) and _n >= 3:
                    _vals.append((_k, float(_v), int(_n)))
            if len(_vals) < 2:
                return None
            _hi = max(_vals, key=lambda x: x[1])
            _lo = min(_vals, key=lambda x: x[1])
            # 격차가 작으면 «크기와 무관한 날»이다 — 억지로 말하지 않는다.
            if (_hi[1] - _lo[1]) < 1.5:
                return None
            return {"강": _hi, "약": _lo}
        return None
    except Exception:
        return None


def build_sector_ladder():
    """🪜 섹터 순위 사다리 — 최근 며칠 순위 이동을 선 하나로 보여준다.

    ⚠️ 2026-08-22 신설 — "순환매·주도주 감을 잡는 게 이 리포트의 메인"이라는
       지적으로, 표(성적표)보다 먼저 눈에 들어올 '동선' 그림을 핵심편에 둔다.
       재료는 이미 계산되는 _zone_series()를 그대로 쓴다 — 새 수집 불필요.
       (섹터 순위 타일과 같은 원천 데이터, 표현만 다르다 — 원칙 5 위반 아님:
        저긴 표, 여긴 선. 저긴 심층편, 여긴 핵심편 요약.)
    """
    구역, 시장 = _zone_series()
    if not 구역:
        return ""
    전체날짜 = sorted(set().union(*[set(v) for v in 구역.values()]))
    일별순위, 일별개수 = {}, {}
    for d in 전체날짜:
        오늘값 = [(nm, v.get(d)) for nm, v in 구역.items() if v.get(d) is not None]
        if len(오늘값) < 8:      # 격자가 부실한 날(휴장 잔재 등)은 순위에서 뺀다
            continue
        오늘값.sort(key=lambda x: -x[1])
        일별순위[d] = {nm: i + 1 for i, (nm, _) in enumerate(오늘값)}
        일별개수[d] = len(오늘값)

    사용일 = sorted(일별순위)[-5:]     # 최근 5거래일 (HO 지시 2026-08-22)
    if len(사용일) < 3:
        return ""     # 표본 부족 — 조용히 생략(축적되면 자동으로 나타난다)

    오늘 = 사용일[-1]
    # 🆕 2026-08-22 HO 지시 — 6개는 선이 엉켜 오히려 못 읽는다. **오늘 상위 3개만.**
    #    "지금 주도주가 뭔가"에 답하는 게 목적이지 순위표를 보여주는 게 아니다.
    표시 = sorted(일별순위[오늘], key=lambda nm: 일별순위[오늘][nm])[:3]   # 오늘 상위 3개
    최대순위 = max(일별개수.values())

    # 🆕 2026-08-22 — 라벨 글자를 키우면서 오른쪽 자리도 함께 넓혔다(148 → 210).
    #    아래쪽 라벨이 밀려 내려갈 수 있으므로 세로 여유도 더 준다.
    # 🆕 2026-08-22 — 우여백 300은 과했다. 선이 좌우로 짜부라져 흐름이 안 보였다.
    #    viewBox를 넓혀(680→980) **그래프 폭은 넉넉히 두고** 오른쪽 이름 자리만 얹는다.
    # 🆕 2026-08-22 — 이름 자리를 줄이고(300→252) 좌우 여백도 좁혀 선을 더 벌린다.
    # 🆕 2026-08-26 HO 지시 — 섹터명 글자를 31→40으로 키웠더니
    #    «전력·신재생·원전» 같은 긴 이름이 오른쪽으로 잘렸다.
    #    ⚠️ 우여백만 늘리면 그래프 폭이 줄어 선이 짜부라진다.
    #       **viewBox(W)를 같이 넓혀** 그래프 폭은 유지하고 이름 자리만 더 준다.
    # 🆕 2026-08-29 HO 지시 — 선그래프가 너무 작다. 좌우를 최대한 쓴다.
    #    ⚠️ 우여백(섹터명 자리)을 줄이면 긴 이름이 잘린다. 그래서
    #       **W를 크게 늘려** 그래프 폭(가용폭)을 벌리고, 이름 자리는 오히려
    #       조금 더 준다(섹터명을 40→52로 키웠으므로).
    #       1180-40-452 = 688 → 1620-40-530 = 1050 (그래프 폭 +53%)
    #    ⚠️ 우여백 470으로 먼저 잡았더니 「전력·신재생·원전」(9자)의 끝이
    #       1551/1560으로 9px만 남았다. 이보다 긴 이름이 나오면 잘린다
    #       (2026-08-26에 실제로 겪은 사고와 같은 상황) → 530으로 늘려
    #       한 글자분 이상 여유를 둔다. 가용폭은 1050 그대로다.
    W, 좌여백, 우여백 = 1620, 40, 530
    가용폭 = W - 좌여백 - 우여백
    x간격 = (가용폭 / (len(사용일) - 1)) if len(사용일) > 1 else 0
    # 🆕 2026-08-22 — 날짜·그래프가 위 문장에 붙어 보인다는 지적으로 더 내린다.
    # 🆕 2026-08-29 HO 지시 — 위아래도 더 넓게. 날짜 글자를 키우면서 Y0를
    #    내리고, 행높이도 키워 선의 오르내림이 실제로 눈에 보이게 한다
    #    (15.5는 순위가 1·2·3위로 붙으면 거의 평평해 보였다).
    Y0, 행높이 = 128, 26
    # ⚠️ 높이는 **표시하는 3개 섹터가 실제로 지나간 순위 범위**로 잡는다.
    #    예전엔 전체 섹터수(16)를 그대로 곱해 아래가 통째로 비었다.
    _쓴순위 = [일별순위[d][nm] for nm in 표시 for d in 사용일 if nm in 일별순위[d]]
    H = Y0 + max(max(_쓴순위, default=1), 3) * 행높이 + 66

    def xy(i, rk):
        return 좌여백 + i * x간격, Y0 + (rk - 1) * 행높이

    팔레트 = ["#f0c65a", "#ff6b4a", "#5b9bff", "#4ade80", "#f472e6", "#74f0d4"]
    선들, 점들 = [], []
    # (섹터명, 색, 좌표목록) — 라벨 겹침을 먼저 푼 뒤 그 결과로 선을 그린다
    코스 = []
    for ci, nm in enumerate(표시):
        col = 팔레트[ci % len(팔레트)]
        pts = [(i, 일별순위[d][nm]) for i, d in enumerate(사용일) if nm in 일별순위[d]]
        if len(pts) >= 2:
            코스.append([nm, col, pts, xy(*pts[-1])[1]])   # 마지막 원소 = 끝점 y

    # 🆕 2026-08-22 HO 지적 — 글자만 벌리고 선은 그대로라 선끼리 붙어 안 보인다.
    #    순위가 1·2·3위로 붙으면 끝점 y도 15.5px 간격이라 선 3개가 겹쳐 보인다.
    #    → **라벨 위치를 먼저 확정하고, 선의 끝점도 그 위치로 끌어올린다.**
    #      선과 라벨이 같은 높이에서 만나므로 어느 선이 어느 섹터인지도 명확해진다.
    # 🆕 2026-08-26 HO 지시 — 오늘(마지막) 쪽 선·라벨이 붙어 읽기 어렵다.
    #    라벨 글자를 키우면 필요한 세로 간격도 같이 커져야 겹치지 않는다.
    # 🆕 2026-08-29 — 섹터명을 40→52로 키웠으니 라벨 간격도 같이 키운다.
    #    안 그러면 이름끼리 겹친다(2026-08-26에 같은 이유로 조정한 적 있음).
    라벨높이 = 78
    코스.sort(key=lambda t: t[3])
    for i in range(1, len(코스)):
        if 코스[i][3] - 코스[i - 1][3] < 라벨높이:
            코스[i][3] = 코스[i - 1][3] + 라벨높이

    라벨들 = []
    for nm, col, pts, 끝y in 코스:
        path, prev = "", None
        for k, (i, rk) in enumerate(pts):
            x, y = xy(i, rk)
            if k == len(pts) - 1:
                y = 끝y                     # 마지막 점만 라벨 높이에 맞춰 벌린다
            if prev is None:
                path = f"M {x:.0f} {y:.0f} "
            else:
                px, py = prev
                mx = (px + x) / 2
                path += f"C {mx:.0f} {py:.0f}, {mx:.0f} {y:.0f}, {x:.0f} {y:.0f} "
            prev = (x, y)
        # 🆕 2026-08-29 HO 지시 — 선이 너무 얇다. 3.4 → 5.2.
        #    ⚠️ viewBox가 1620이라 화면에서는 폭에 맞춰 축소된다. 즉 여기
        #       숫자를 키워야 실제 화면에서 굵어진다(글자 크기와 같은 이유).
        선들.append(f'<path d="{path}" fill="none" stroke="{col}" stroke-width="5.2" '
                    f'stroke-linecap="round" opacity="0.9"/>')
        lx = xy(pts[-1][0], 1)[0]
        점들.append(f'<circle cx="{lx:.0f}" cy="{끝y:.0f}" r="5" fill="{col}" '
                    f'stroke="#12161d" stroke-width="1.5"/>')
        # 🆕 2026-08-22 — SVG는 화면 폭에 맞춰 축소되므로 font-size를 키워도
        #    실제로는 작게 보인다. 섹터명은 **아래 HTML 목록**이 크게 보여주니
        #    그래프에는 순위 변동(▲▼)만 남겨 선이 가려지지 않게 한다.
        # 🆕 2026-08-22 — 섹터명을 다시 넣는다. SVG가 축소돼 작아 보이므로
        #    viewBox 기준 글자를 크게 잡고(26) 오른쪽 자리도 넉넉히 준다.
        라벨들.append(
            # 🆕 2026-08-22 — 순위 변동(▲7 등) 표시는 뺐다(HO 지시).
            #    선의 오르내림이 이미 같은 정보를 보여주고 있어 숫자가 중복이었다.
            #    섹터명만 남기니 라벨이 훨씬 깔끔하고 크게 보인다.
            f'<text x="{lx+16:.0f}" y="{끝y:.0f}" dominant-baseline="central" '
            # 🆕 2026-08-26 HO 지시 — 섹터명이 너무 작다. 31 → 40.
            #    ⚠️ SVG가 화면 폭에 맞춰 축소되므로 viewBox 기준 숫자를 키워야
            #       실제 화면에서 커진다.
            # 🆕 2026-08-29 HO 지시 — 섹터명도 더 크게. 40 → 52.
            f'font-size="52" font-weight="800" fill="{col}">{nm}</text>')

    날짜라벨 = "".join(
        # 🆕 2026-08-26 (2차) HO 지시 — 날짜가 여전히 작다. 22 → 32 + 굵게.
        # 🆕 2026-08-29 HO 지시 — 32도 작다. 44로. (font-weight가 두 번
        #    적혀 있던 것도 정리 — 뒤엣것이 앞엣것을 덮어써 무해했지만 혼란만 준다)
        f'<text x="{좌여백 + i * x간격:.0f}" y="58" text-anchor="middle" font-size="44" '
        f'font-weight="800" fill="#b6bec9">'
        f'{"오늘" if i == len(사용일) - 1 else d[4:6] + "/" + d[6:]}</text>'
        for i, d in enumerate(사용일))

    # ── 🆕 2026-08-22 — 사다리 섹터를 눌러 대표 종목을 볼 수 있게 ──
    #    ⚠️ SVG <text> 안에는 다른 코너와 똑같은 금색 ▾ 화살표를 넣을 수 없다
    #       (SVG는 HTML 요소를 품지 못하고, 폰트·정렬이 달라 모양도 안 맞는다).
    #       → 그래프 바로 아래에 **HTML 줄**을 따로 두고 거기에 화살표를 붙인다.
    #       세 코너(지도·성적표·돌아올섹터)와 같은 ZONE_ARROW를 쓰므로 모양이 같다.
    # 🆕 2026-08-22 HO 지시 — 눌러야 보이던 대표 종목을 **항상 펼쳐서** 보여준다.
    #    "주도 섹터가 뭔지"보다 "그래서 어떤 종목인지"가 독자의 실제 관심사라,
    #    한 번 더 누르게 만들 이유가 없다.
    사다리목록 = ""
    _줄 = []
    for nm, col, pts, 끝y in 코스:
        목록 = (_zone_members().get(nm) or [])[:6]
        if not 목록:
            continue
        # 🆕 2026-08-29 (2차) HO 지시 — 심층편에서 섹터명을 눌렀을 때 나오는
        #    패널(zone_member_panel)과 **완전히 같은 디자인**으로 통일한다.
        #    [WHY] 같은 «그 섹터의 종목들»을 보여주는 자리인데 핵심편·심층편이
        #    서로 다르게 생기면 구독자는 같은 걸 두 번 배워야 한다(체크박스를
        #    섹터 성적표와 통일했던 것과 같은 이유).
        #    ⚠️ 종목들 테두리를 섹터 색상으로 넣되, 투명도를 낮춰(55)
        #       은은하게 — 색만 진하게 두면 종목명보다 색이 먼저
        #       눈에 들어와 주인공이 바뀐다(2026-09-01 HO 지시).
        칩 = "".join(
            f'<span style="display:inline-block;font-size:10.5px;color:#d5d9e0;'
            f'background:#141922;border:1px solid {col}55;border-radius:5px;'
            f'padding:2px 7px;margin:0 4px 4px 0;white-space:nowrap">{n} '
            f'<b style="color:{"#ff6b4a" if (v or 0) >= 0 else "#5b9bff"}">'
            f'{(v or 0):+.1f}%</b></span>'
            for n, v in 목록)
        # 🆕 2026-08-25 — 순위 기준을 화면에 밝힌다.
        #  ⚠️ HO 지적의 뿌리: 대표 종목이 +30%인데 순위는 2위라 이상해 보였다.
        #     대표 종목은 그 섹터 '최고 상승'이고, 순위는 '가운데 종목' 기준이다.
        #     이 둘이 다르다는 걸 안 밝히면 매일 같은 오해가 반복된다.
        _st = _zone_today_stat().get(nm) or {}
        _중 = _st.get("중앙값")
        _확 = _st.get("확산도")
        _n = _st.get("종목수")
        _요약 = ""
        if _중 is not None:
            _c = "#ff6b4a" if _중 >= 0 else "#5b9bff"
            _요약 = (f'<span style="font-size:10px;color:#8b93a0;font-weight:600">'
                   f'가운데 종목 <b style="color:{_c}">{_중:+.2f}%</b>')
            if _확 is not None and _n:
                _요약 += f' · {_n}종목 중 <b style="color:#c9ced6">{_확:.0f}%</b> 상승'
        _요약 += '</span>'
        # 🆕 2026-08-25 HO 지시 — 「가장 고르게 오른 자리」 배지.
        #  ⚠️ 왜 필요한가: 순위는 '가운데 종목이 얼마나'만 말한다. 그런데
        #     순환매에서 진짜 중요한 건 **몇 종목이나 같이 올랐나**다.
        #     확산도가 높은데 순위가 낮은 자리 = 소수 급등이 아니라
        #     섹터 전체에 돈이 퍼지는 중 = **다음 주도 후보**.
        #  ⚠️ 오늘 전 섹터 중 확산도 1위일 때만 붙인다. 매일 붙으면 의미가 없다.
        if _확 is not None and _확 == _확산도최고():
            _요약 += ('<span style="display:inline-block;margin-left:5px;font-size:9px;'
                    'font-weight:800;color:#74f0d4;border:1px solid #74f0d4;'
                    'border-radius:999px;padding:1px 6px">가장 고르게 올랐어요</span>')
        # 🆕 2026-08-26 — 섹터→테마·크기 브릿지 두 줄.
        #  [WHY] «반도체 1위»는 맞는 말인데 «어느 반도체냐»가 빠져 있었다.
        #        섹터를 쪼개는 대신(축적이 리셋된다) 두 층을 이어서 답한다.
        _브릿지 = ""
        _tm = _zone_themes(nm)
        if _tm:
            _브릿지 += (
                f'<p style="margin:0 0 3px;font-size:10.5px;color:#8b93a0;'
                f'line-height:1.55">↳ 그중에서도 '
                f'<b style="color:#e0c060">{" · ".join(_tm)}</b>'
                f'{"가" if len(_tm) == 1 else " 테마가"} 이끌었어요</p>')
        _sz = _zone_size_split(nm)
        if _sz:
            _강, _약 = _sz["강"], _sz["약"]
            _브릿지 += (
                f'<p style="margin:0 0 4px;font-size:10.5px;color:#8b93a0;'
                f'line-height:1.55">↳ <b style="color:#c9ced6">{_강[0]}주</b>가 '
                f'<b style="color:{"#ff6b4a" if _강[1] >= 0 else "#5b9bff"}">'
                f'{_강[1]:+.2f}%</b>로 이끌고 {_약[0]}주는 '
                f'<b style="color:{"#ff6b4a" if _약[1] >= 0 else "#5b9bff"}">'
                f'{_약[1]:+.2f}%</b> — 같은 자리라도 <b style="color:#c9ced6">'
                f'크기에 따라 다른 하루</b>였어요</p>')
        _줄.append(
            f'<div style="padding:8px 9px;margin-top:6px;background:#0f131a;'
            f'border-radius:8px;border-left:3px solid {col}">'
            f'<p style="margin:0 0 2px;font-size:13px;font-weight:800;color:#e8eaee">'
            f'{nm}</p><p style="margin:0 0 5px">{_요약}</p>'
            # 🆕 2026-08-29 — 심층편 zone_member_panel과 같은 «어두운 패널»
            #    안에 칩을 담는다(배경 #0f131a → 한 단계 더 어두운 #0a0d13 +
            #    금색 제목줄). 이게 두 코너를 같아 보이게 하는 핵심이다.
            f'{_브릿지}'
            f'<div style="margin-top:4px;padding:8px 9px;background:#0a0d13;'
            f'border-radius:6px">'
            f'<p style="margin:0 0 5px;font-size:10.5px;color:#e0c060;'
            f'font-weight:700">{nm} 대표 종목</p>'
            f'<div>{칩}</div></div></div>')
    if _줄:
        사다리목록 = ('<p style="margin:11px 0 0;font-size:11px;color:#e0c060">'
                  '이 섹터들, 어떤 종목이 담겨 있냐면요</p>' + "".join(_줄))

    # ── 🆕 2026-08-22 — '가장 밀린 자리' 한 줄을 이 카드 안으로 합친다 ──
    #    예전엔 build_sector_brief()가 칩으로 상위3/하위3을 따로 보여줬는데,
    #    사다리와 상위 섹터가 겹쳐 핵심편에서 같은 순위를 두 번 말하고 있었다.
    #    → 상위는 그림(사다리), 하위는 텍스트 한 줄. 형태를 달리해 중복감을 없앤다.
    # 🆕 2026-08-25 HO 지적 — **비교군이 안 맞았다.**
    #  ⚠️ 위(사다리)는 «오늘 중앙값 %»로 순위를 매기는데, 아래(밀린 자리)는
    #     «초과수익 %p»를 쓰고 있었다. 단위도 기준도 다르다.
    #     그래서 코스피가 -3.12% 빠진 날 "가장 밀린 자리"가 +2.9%p로 찍혀
    #     상위 섹터(가운데 종목 +1.4%)보다 높아 보이는 모순이 생겼다.
    #  [고침] 같은 순위표의 **반대쪽 끝**을 쓴다 — 위와 정확히 같은 값·같은 단위.
    하위줄 = ""
    _최신 = max(set().union(*[set(v) for v in 구역.values()])) if 구역 else None
    if _최신:
        _통계 = [(nm, v[_최신]) for nm, v in 구역.items()
               if isinstance(v.get(_최신), (int, float))]
        if len(_통계) >= 6:
            _통계.sort(key=lambda x: x[1])
            _하 = _통계[:3]
            _칩 = " · ".join(
                f'<b style="color:{sector_color(nm)}">{nm}</b> '
                f'<span style="color:#8b93a0">{v:+.2f}%</span>' for nm, v in _하)
            하위줄 = ('<p style="margin:9px 0 0;padding-top:9px;'
                    'border-top:.5px solid rgba(255,255,255,.08);'
                    'font-size:11.5px;color:#7d848f;line-height:1.6">'
                    f'⤷ 오늘 가장 밀린 자리 — {_칩}<br>'
                    '<span style="font-size:10.5px">내 종목이 여기 있다면 '
                    '<b style="color:#c9ced6">종목이 아니라 자리가 불리했던 것</b>이에요 · '
                    '순환매에서는 이 자리가 다음 순번이 되기도 해요</span></p>')

    return ZTOG_JS + f'''
  <div style="background:#141922;border:1px solid #232a36;border-radius:12px;
              padding:13px 14px;margin:10px 0 0">
    <p style="margin:0 0 2px;font-size:11.5px;color:#8b93a0">오늘 주도 섹터</p>
    <p style="margin:0 0 6px;font-size:17px;font-weight:800;color:#f2f4f7">
      📶 오늘 상위 섹터, 며칠째 이 자리일까요</p>
    <svg viewBox="0 0 {W} {H}" style="width:100%;height:auto">
      {날짜라벨}
      {"".join(선들)}{"".join(점들)}{"".join(라벨들)}
    </svg>
    <p style="margin:8px 0 0;font-size:11px;color:#7d848f;line-height:1.5">
      선이 위로 갈수록 그날 순위가 높았다는 뜻이에요 · 전체 {최대순위}개 섹터 중 순위 ·
      계속 위쪽이면 주도주 지속, 최근 올라오는 중이면 다음 주도주 후보예요</p>
    {사다리목록}
    {하위줄}
  </div>'''


def build_sector_brief():
    """📈 오늘 섹터 한 줄 — 핵심편용 요약.

    ⚠️ 왜 만들었나 (2026-08-22)
      핵심편과 심층편에 **완전히 같은** 섹터 성적표 카드가 두 번 나왔다.
      탭·체크박스·선 그래프·보는 방법까지 전부 같아서 '요약'이 아니라 '복붙'이었다.
      그렇다고 핵심편에서 통째로 빼면 「팩트 → 해석 → 섹터 → 감정」 흐름이 끊긴다.
      → 핵심편에는 **오늘 가장 센 곳/가장 약한 곳 한 줄**만 남기고,
        판단에 필요한 표는 심층편 한 곳에서만 보여준다.
    """
    구역, 시장 = _zone_series()
    if not 구역 or not 시장:
        return ""
    통계 = []
    for nm, 일별 in 구역.items():
        st = _zone_stat(일별, 시장, 1)      # 당일 창
        if st:
            통계.append((nm, st[0]))        # (섹터명, 초과수익%p)
    if len(통계) < 4:
        return ""
    통계.sort(key=lambda x: -x[1])
    상, 하 = 통계[:3], 통계[-3:][::-1]

    def 칩(items, 색):
        return "".join(
            f'<span style="display:inline-flex;align-items:center;gap:3px;'
            f'background:#1b2230;border:1px solid #262e3c;border-radius:999px;'
            f'padding:2px 8px;margin:3px 3px 0 0;font-size:11px;color:#c9ced6">'
            f'<b style="color:{sector_color(nm)}">●</b>{nm}'
            f'<b style="color:{색}">{v:+.1f}%p</b></span>'
            for nm, v in items)

    # ⚠️ 라벨을 데이터로 정한다 — 2026-08-22.
    #    "시장을 이긴 자리"라고 써놓고 값이 −1.1%p면 그 자체가 거짓말이다.
    #    실제로 코스피가 오른 날 전 섹터가 코스피에 지는 경우가 있다
    #    (2026-08-21: 코스피 +0.88%인데 대형주 몇 종목만 올려서 전 섹터 초과수익 음수).
    if 상[0][1] > 0:
        위라벨 = "시장을 이긴 자리"
    else:
        위라벨 = "그나마 덜 밀린 자리 — 오늘은 코스피를 이긴 섹터가 없습니다"
    아래라벨 = "시장에 가장 크게 진 자리" if 하[0][1] < 0 else "가장 덜 오른 자리"

    return ('<div style="background:#141922;border:1px solid #232a36;border-radius:12px;'
            'padding:13px 14px;margin:10px 0 0">'
            '<p style="margin:0 0 2px;font-size:11.5px;color:#8b93a0">섹터 성적</p>'
            '<p style="margin:0 0 8px;font-size:17px;font-weight:800;color:#f2f4f7">'
            '📈 오늘, 자리가 갈랐습니다'
            '<span style="font-size:11.5px;font-weight:600;color:#8b93a0">'
            ' · 코스피 대비 초과수익</span></p>'
            f'<p style="margin:0 0 2px;font-size:11.5px;color:#8b93a0">{위라벨}</p>'
            f'<div style="margin:0 0 9px">{칩(상, FS_BUY if 상[0][1] > 0 else "#8b93a0")}</div>'
            f'<p style="margin:0 0 2px;font-size:11.5px;color:#8b93a0">{아래라벨}</p>'
            f'<div>{칩(하, FS_SELL)}</div>'
            '<p style="margin:9px 0 0;font-size:11px;color:#8b93a0;line-height:1.5">'
            '내 종목이 아래쪽에 있다면 <b style="color:#c9ced6">종목 선택이 아니라 '
            '자리가 불리했다</b>는 뜻입니다 · 전체 순위와 기간별 추이는 '
            '<b style="color:#f0c65a">심층편 &lt;섹터 성적표&gt;</b>에 있습니다</p></div>')


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
    # 🆕 2026-08-26 HO 지시 — 기본 탭을 **5일**로 (순위 타일과 통일).
    #  [WHY] 당일 하나만 보면 "오늘 셌다"로 끝나고 흐름이 안 보인다.
    #        5일이면 한 주 흐름이 보여 '주도 섹터'라는 이 코너의 목적이 산다.
    기본idx = next((i for i, (n, _, _) in enumerate(ZONE_WINDOWS) if n == 5), 0)

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
                # 🆕 2026-08-22 — 섹터명을 누르면 대표 종목이 펼쳐진다.
                #    체크박스(선 그래프 토글)와 역할이 다르니 이름 <div>에만 onclick.
                #    ⚠️ 성적표는 탭 4개(당일/5/20/60)가 같은 섹터를 반복 렌더하므로
                #       id가 겹치지 않게 전역 일련번호를 쓴다.
                _GRID_SEQ[0] += 1
                _pid = f"sbm{_GRID_SEQ[0]}"
                _panel = zone_member_panel(nm, _pid, 여백=0)
                # 🆕 2026-08-22 — 이름과 화살표 분리(위 돌아올 섹터와 같은 이유).
                _이름 = (f'<div class="sb-name" onclick="ztog(\'{_pid}\')" '
                       f'style="font-size:11px;color:#e8eaee;font-weight:700;'
                       f'display:flex;align-items:center;gap:1px;'
                       f'border-radius:4px;padding:1px 3px;cursor:pointer;'
                       f'-webkit-tap-highlight-color:transparent">'
                       f'<span style="min-width:0;overflow:hidden;text-overflow:ellipsis;'
                       f'white-space:nowrap">{nm}</span>{ZONE_ARROW}</div>'
                       if _panel else
                       f'<div class="sb-name" style="font-size:11px;color:#e8eaee;'
                       f'font-weight:700;overflow:hidden;text-overflow:ellipsis;'
                       f'white-space:nowrap;border-radius:4px;padding:1px 3px">{nm}</div>')
                줄.append(
                    f'<div class="sb-row{"" if 보임 else " sb-more"}" data-zone="{nm}" '
                    f'style="display:{"flex" if 보임 else "none"};align-items:center;gap:6px;'
                    f'padding:5px 4px;border-bottom:1px solid #1b212c;border-radius:6px">'
                    f'<input type="checkbox" class="sb-ck" data-idx="{idx}" data-zone="{nm}" '
                    f'{체크} onchange="sbTog({idx})" '
                    f'style="flex:none;width:14px;height:14px;accent-color:{색맵[nm]};cursor:pointer">'
                    f'<div style="width:78px;flex:none;min-width:0">'
                    f'{_이름}'
                    f'<div style="font-size:9px;color:#7d848f">{승}승 {총-승}패 · {승/총*100:.0f}%</div></div>'
                    f'<div style="flex:1;position:relative;height:17px;background:#161b24;'
                    f'border-radius:3px;min-width:40px">'
                    f'<div style="position:absolute;left:50%;top:-2px;width:1px;height:21px;'
                    f'background:#3a4150"></div>{바}</div>'
                    f'<div style="width:48px;flex:none;text-align:right">'
                    f'<div style="font-size:11.5px;font-weight:800;color:{c}">{초:+.1f}%p</div>'
                    f'<div style="font-size:9px;color:#7d848f">{수:+.1f}%</div></div></div>'
                    + _panel)

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
                      f'data-y0="{_ey:.1f}" x="{W-R+7}" y="{_ey+3.5:.1f}" font-size="11" font-weight="700" '
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

    return (ZTOG_JS
            + '<div style="background:#141922;border:1px solid #232a36;border-radius:12px;'
            'padding:13px 14px;margin:10px 0 0">'
            # 🆕 2026-08-22 HO 지시 — 분류 변경 안내 배너 제거.
            #    (함수 sector_rule_note()는 남겨 둔다 — §8 삭제 금지)
            '<p style="margin:0 0 2px;font-size:11.5px;color:#8b93a0">섹터 성적표</p>'
            '<p style="margin:0 0 3px;font-size:17px;font-weight:800;color:#f2f4f7">'
            '어느 섹터가 시장을 이겼나 '
            '<span style="font-size:11.5px;font-weight:600;color:#8b93a0">'
            '· 시장 대비 초과수익률</span></p>'
            '<p style="margin:0 0 3px;font-size:10.5px;color:#e0c060">'
            '👆 섹터 이름을 누르면 대표 종목이 나옵니다</p>'
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
    # 📅 거래일만 — archive_days()가 휴장일 중복을 걸러준다
    for _ymd, _d in archive_days(40):
        try:
            _v = (_d.get("신용잔고") or {}).get("잔고")
            if isinstance(_v, (int, float)):
                _hist.append(_v)
        except Exception:
            continue
    추이HTML = ""
    if len(_hist) >= 3:
        _hi, _lo = max(_hist), min(_hist)
        _rng = max(1.0, _hi - _lo)
        # 🆕 2026-08-26 HO 지적 — 선그래프 위에 아래 설명 글자가 겹쳤다.
        #  [원인] preserveAspectRatio="none"으로 세로를 42px에 강제로 눌러놓고,
        #     설명문 margin은 2px뿐이라 선이 아래로 내려오면 글자와 부딪혔다.
        #  [고침] 캔버스를 56으로 키우고 선이 그려지는 영역을 위쪽으로 제한한 뒤,
        #     설명문에 여유(margin 6px)를 준다. 오른쪽 끝점도 안쪽으로 당겨
        #     동그라미가 잘리지 않게 한다.
        _W, _H = 300, 56
        _pad = 8                      # 선이 아래로 내려올 수 있는 하한
        _pts = " ".join(f"{i*(_W-6)/(len(_hist)-1):.0f},{_H-_pad-(v-_lo)/_rng*(_H-_pad-6):.0f}"
                        for i, v in enumerate(_hist))
        _c = "#ff6b4a" if _hist[-1] >= _hist[0] else "#5b9bff"
        추이HTML = (f'<svg viewBox="0 0 {_W} {_H}" preserveAspectRatio="none" '
                  f'style="width:100%;height:52px;display:block;margin-top:7px">'
                  f'<polyline points="{_pts}" fill="none" stroke="{_c}" stroke-width="2"/>'
                  f'<circle cx="{_W-6}" cy="{_H-_pad-(_hist[-1]-_lo)/_rng*(_H-_pad-6):.0f}" r="3" '
                  f'fill="{_c}"/></svg>'
                  f'<p style="margin:6px 0 0;font-size:9.5px;color:#6f7784;line-height:1.5">'
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
    else:
        # ⚠️ 없으면 조용히 빼지 않는다(2026-08-21 지시).
        #    빠지면 "왜 안 보이지"를 알 수가 없다. **없다는 사실 자체를 알린다.**
        신용HTML = ('<div style="margin-top:9px;padding:9px 10px;background:#1a1610;'
                   'border:1px solid #3a3020;border-radius:8px">'
                   '<div style="display:flex;justify-content:space-between;align-items:center">'
                   '<span style="font-size:11.5px;color:#8b93a0">신용융자 잔고</span>'
                   '<span style="font-size:12px;font-weight:800;color:#e0c060">미수집</span></div>'
                   '<p style="margin:5px 0 0;font-size:11px;color:#7d848f;line-height:1.6">'
                   '빚내서 산 돈이 얼마나 쌓였는지를 보는 지표입니다. '
                   '<b style="color:#9aa0aa">아직 수집원을 붙이는 중</b>이라 오늘은 표시하지 못합니다 — '
                   '없는 숫자를 지어내지 않기 위해 비워 둡니다.</p></div>')

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
        # ⚠️ 색은 리포트 전체 규칙과 같아야 한다 — 좋아짐=빨강 / 나빠짐=파랑.
        #    (예전엔 초록/보라였는데 수급 색 규칙이 바뀌어 여기만 남아 있었다)
        if 변화 > 2:
            색, 표식, 꼴 = FS_BUY, "", "in"       # 관제탑에 가까워짐 = 들어옴
            # ⚠️ 섹터명 옆 화살표(▲▼=)는 뺐다(2026-08-19).
            #    점의 모양·색이 이미 같은 말을 하고 있어 글자만 어수선해졌다.
        elif 변화 < -2:
            색, 표식, 꼴 = FS_SELL, "", "out"    # 멀어짐 = 빠짐
        else:
            색, 표식, 꼴 = "#f0c65a", "", "stay"  # 제자리
        # ── 이동 자취 ──
        #  ⚠️ 예전엔 이동선이 굵어서 점과 구분이 안 됐다.
        #     선은 **가늘고 옅은 점선**으로 낮추고, 끝에 **화살촉**을 달아
        #     "어디서 어디로" 갔는지를 방향으로 읽게 한다.
        # ⚠️ 이동 자취는 **다가온 섹터만** 그린다 (2026-08-18 지시).
        #    멀어진 섹터까지 선을 그으면 화면이 선으로 뒤덮여 정작 봐야 할
        #    "달아오르는 곳"이 안 보인다. 멀어진 섹터는 점(속 빈 원)으로만 남긴다.
        if 꼴 == "in":
            자취 += (f'<circle cx="{ox:.0f}" cy="{oy:.0f}" r="2.6" fill="none" '
                     f'stroke="{색}" stroke-width="1" opacity=".45"/>')
            자취 += (f'<line x1="{ox:.0f}" y1="{oy:.0f}" x2="{nx:.0f}" y2="{ny:.0f}" '
                     f'stroke="{색}" stroke-width="1.3" stroke-dasharray="3 3" opacity=".5"/>')
            # 화살촉 — 이동 방향 (어제 → 오늘)
            import math as _rm
            _ang = _rm.degrees(_rm.atan2(ny - oy, nx - ox))
            _hx = nx - (nx - ox) * 0.22
            _hy = ny - (ny - oy) * 0.22
            자취 += (f'<g transform="translate({_hx:.1f} {_hy:.1f}) rotate({_ang:.0f})">'
                     f'<path d="M0 0 L-6 -3.4 L-6 3.4 Z" fill="{색}" opacity=".8"/></g>')

        # ── 오늘 자리 (점) ──
        #  들어옴 / 빠짐 / 제자리를 **색뿐 아니라 모양으로도** 갈라 놓는다.
        #    들어옴 = 채운 원 + 바깥 링   (다가온 느낌)
        #    빠짐   = 속 빈 원            (비어 나간 느낌)
        #    제자리 = 작은 채운 원
        #  레이더처럼 천천히 명멸시키되, 섹터마다 시작을 어긋나게 해 요란하지 않게.
        # ⚠️ 다가온 섹터(꼴=="in")는 **모두 같은 박자로** 깜빡인다.
        #    같이 반짝여야 "오늘 여기가 달아올랐다"가 한 덩어리로 보인다.
        #    나머지는 시작을 어긋나게 해 조용히 명멸시킨다(요란함 방지).
        _dly = "0s" if 꼴 == "in" else f"{(_di * 0.37) % 3.2:.2f}s"
        _cls = f'class="rdr-dot" style="animation-delay:{_dly}"'
        if 꼴 == "in":
            점 += (f'<circle cx="{nx:.0f}" cy="{ny:.0f}" r="13" fill="{색}" '
                   f'fill-opacity=".16" {_cls}/>')
            점 += (f'<circle cx="{nx:.0f}" cy="{ny:.0f}" r="8" fill="{색}" '
                   f'stroke="#0b0e13" stroke-width="2" {_cls}/>')
        elif 꼴 == "out":
            점 += (f'<circle cx="{nx:.0f}" cy="{ny:.0f}" r="7.5" fill="#0b0e13" '
                   f'stroke="{색}" stroke-width="3" {_cls}/>')
        else:
            점 += (f'<circle cx="{nx:.0f}" cy="{ny:.0f}" r="5.5" fill="{색}" '
                   f'stroke="#0b0e13" stroke-width="1.6" {_cls}/>')
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
    변동표 = hide("어제대비움직임", 변동표)

    # 접근/이탈은 짝을 이루는 정보라 나란히 두는 편이 비교가 쉽다.
    #   좁은 화면에서 세로로 쌓이면 두 줄을 눈으로 왕복해야 해서 대비가 안 잡힌다.
    def _칸(제목, 값, 색):
        return (f'<div style="flex:1;min-width:0;background:#141922;border-radius:8px;'
                f'padding:8px 9px">'
                f'<p style="margin:0;font-size:10.5px;color:#8b93a0">{제목}</p>'
                f'<p style="margin:3px 0 0;font-size:12.5px;font-weight:700;color:{색};'
                f'word-break:keep-all;line-height:1.35">{값}</p></div>')
    접근값, 접근색 = ((최대접근[0], FS_BUY) if 최대접근[1] > 0.5 else ("오늘은 없음", "#6f7784"))
    이탈값, 이탈색 = ((최대이탈[0], FS_SELL) if 최대이탈[1] > 0.5 else ("오늘은 없음", "#6f7784"))
    # ⚠️ 모양을 갈랐으면 그 뜻을 반드시 그림 옆에 적어야 한다.
    #    안 적으면 "왜 어떤 건 속이 비었지?"에서 멈춘다.
    범례 = ('<div style="display:flex;gap:11px;flex-wrap:wrap;justify-content:center;'
            'margin:8px 0 10px;font-size:10px;color:#8b93a0;font-weight:700">'
            f'<span><svg width="15" height="15" viewBox="0 0 15 15" style="display:inline-block;'
            f'vertical-align:-3px"><circle cx="7.5" cy="7.5" r="7" fill="{FS_BUY}" fill-opacity=".18"/>'
            f'<circle cx="7.5" cy="7.5" r="4.5" fill="{FS_BUY}"/></svg> 들어옴(달아오름)</span>'
            f'<span><svg width="15" height="15" viewBox="0 0 15 15" style="display:inline-block;'
            f'vertical-align:-3px"><circle cx="7.5" cy="7.5" r="4.5" fill="#0b0e13" '
            f'stroke="{FS_SELL}" stroke-width="2.4"/></svg> 빠짐</span>'
            '<span><svg width="15" height="15" viewBox="0 0 15 15" style="display:inline-block;'
            'vertical-align:-3px"><circle cx="7.5" cy="7.5" r="3.4" fill="#f0c65a"/></svg> 제자리</span>'
            '<span><svg width="26" height="10" viewBox="0 0 26 10" style="display:inline-block;'
            'vertical-align:-1px"><line x1="0" y1="5" x2="18" y2="5" stroke="#8b93a0" '
            'stroke-width="1.3" stroke-dasharray="3 3"/><path d="M26 5 L18 1.6 L18 8.4 Z" '
            'fill="#8b93a0"/></svg> 어제에서 오늘로 이동</span>'
            '</div>')
    # ⚠️ '이탈' 칸은 뺐다(2026-08-18). 이 코너의 질문은
    #    "오늘 어디가 달아올랐나" 하나다. 이탈까지 같이 두면 초점이 흐려진다.
    패널 = (범례 + '<div style="display:flex;gap:7px">'
            + _칸("가장 빠르게 접근", 접근값, 접근색) + '</div>')

    return ('<div style="background:#141922;border:1px solid #232a36;border-radius:12px;'
            'padding:12px 14px;margin:10px 0 0">'
            '<p style="margin:0 0 2px;font-size:11.5px;color:#8b93a0">뜨는 현장</p>'
            '<p style="margin:0 0 8px;font-size:17px;font-weight:800;color:#f2f4f7">'
            '오늘 관제탑에 가까워진 주인공</p>'
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
              'cursor:pointer;list-style:none">📖 보는 방법 '
              '<span style="color:#6f7784;font-weight:600">(눌러서 펼치기)</span></summary>'
              '<div style="height:6px"></div>'
              '<p style="margin:0;font-size:11.5px;color:#9aa0aa;line-height:1.75">'
              '<b style="color:#22d3ee">가운데가 관제탑</b>입니다. '
              '<b style="color:#e8eaee">가까울수록 오늘 시장을 세게 끌었다</b>는 뜻입니다.<br>'
              f'<b style="color:{FS_BUY}">● 채운 점</b> = 어제보다 안쪽으로 <b>들어옴</b> · '
              f'<b style="color:{FS_SELL}">○ 빈 점</b> = 바깥으로 <b>빠짐</b> · '
              '<b style="color:#f0c65a">● 금색</b> = 제자리<br>'
              '<b style="color:#e8eaee">점선 화살표</b>는 어제 자리에서 오늘 자리까지 움직인 거리입니다.</p>'
              '<div style="height:9px"></div>'
              '<p style="margin:0;font-size:11.5px;color:#9aa0aa;line-height:1.75;'
              'border-top:1px solid #1e2531;padding-top:8px">'
              '<b style="color:#e8eaee">내 종목 구역과 뭐가 다른가요?</b><br>'
              '구역은 <b>안 바뀌는 주소</b>(내 종목이 사는 동네), '
              '여기는 <b>매일 바뀌는 사건 현장</b>(오늘 어디서 불이 났나)입니다.<br>'
              '구역은 <b>얼마나 올랐나</b>를, 여기는 <b>얼마나 돈이 붙었나</b>를 봅니다. '
              '<b>올랐는데 여기선 바깥</b>이면 돈이 안 붙은 상승이라 오래가기 어렵고, '
              '<b>덜 올랐는데 여기선 안쪽</b>이면 돈이 먼저 들어오는 자리일 수 있습니다.</p>'
              '</details>'
            + '<p style="margin:8px 0 0;font-size:11px;color:#6f7784;line-height:1.5">'
            '어제 주도 6위 밖이던 섹터는 바깥에서 출발한 것으로 표시됩니다</p></div>')


# ── 3. 경사선 (테마별 대형→중형→소형) ────────────────────────
def _tier_series():
    """archive에서 {섹터: {날짜: {대형·중형·소형 등락률}}} 을 만든다."""
    out = {}
    # 📅 거래일만 — archive_days()가 휴장일 중복을 걸러준다
    for 날짜, d in archive_days():
        for r in ((d.get("계좌격자") or {}).get("행") or []):
            nm, 칸 = r.get("테마"), (r.get("칸") or {})
            if nm in ZONE_EXCLUDE:      # 매일 내용물이 바뀌는 칸 — 누적 금지
                continue
            # (휴장일 중복은 위 _tier_skip 가드에서 이미 걸러진다)
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
# 🆕 2026-08-24 — CYC_TOP 5 → 3 (HO 확정)
#  ⚠️ 왜 5가 아니라 3인가
#     15슬롯 중 5개면 **전체의 33%가 매일 '지금 주도'**로 분류된다.
#     주도주 매매를 하는 독자에게 "1/3이 다 주도주"는 정보가 아니다.
#     실측: 5위·6위 초과수익 격차가 매일 0.06~1.01%p로 거의 붙어 있어
#     '5위 안'은 통계적 벽이 아니라 순위표의 임의 절단선일 뿐이었다.
#  ⚠️ 그리고 「주도 섹터 사다리」가 이미 상위 3개를 쓰고 있었다.
#     같은 것을 두 코너가 다른 숫자로 정의하면 독자는 "뭐가 진짜 주도주지?"가 된다.
#  ⚠️ 채점 기준(rs_grade_html)도 이 값을 함께 쓴다 → 기준이 엄해진다.
#     2026-08-24 기준 미채점 예보가 1건뿐이라 소급 왜곡은 사실상 없다.
CYC_TOP = 3           # 상위 N위를 '주도권 안'으로 본다
# 🆕 2026-08-24 — 평균주기를 화면에 쓰기 위한 **최소 간격 표본 수**
#  ⚠️ 예전엔 간격이 **1개(등판 2회)**만 있어도 그 값을 "평균 주기"라고 찍었다.
#     실제로 자동차·부품이 등판 2회 → 간격 1개를 "평균 주기 5일"로 표시하고 있었다.
#     우연히 나온 숫자 하나를 통계처럼 보여주는 건 이 리포트의 정직성 원칙에 어긋난다.
#  ⚠️ 미달이면 평균주기를 None으로 두고 "표본이 적다"고 그대로 말한다.
#     None이면 D-day도 안 나오고 그룹은 '대기'로 간다(기존 graceful 경로 재사용).
CYC_MIN_간격 = 3      # 간격 3개 = 등판 4회 이상이어야 '평균'이라 부른다
# ⚠️ 다른 코너(섹터 성적표·크기별·관심종목)와 **같은 창 구성**으로 맞춘다(2026-08-21).
#    코너마다 기간이 다르면 같은 기능인 줄 모른다.
CYC_WINS = [(1, "당일"), (5, "5일"), (20, "20일"), (60, "60일")]


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
            "간격수": len(간격),
            # 🆕 2026-08-24 — 간격이 CYC_MIN_간격 미만이면 '평균'이라 부르지 않는다.
            "평균주기": (sum(간격) / len(간격)) if len(간격) >= CYC_MIN_간격 else None,
            "경과": (len(rk) - 1 - 구간[-1][1]) if 구간 else len(rk),
            "현재": rk[-1]}


def build_sector_map():
    """🗺️ 섹터 순위 타일 — 주도권이 어떻게 돌았나."""
    날짜, 순위, 초과 = _cyc_rank()
    if not 날짜:
        return ""
    이름 = sorted(순위)
    탭, 패널 = "", ""
    # 🆕 2026-08-26 HO 지시 — 기본 탭을 **5일**로.
    #  [WHY] 당일 한 칸만 보면 '순위가 어떻게 돌았나'라는 이 코너의 목적이 안 산다.
    #        5일이면 한 주 흐름이 보여서 첫 화면부터 의미가 생긴다.
    _기본 = next((i for i, (n, _) in enumerate(CYC_WINS) if n == 5), 0)
    for idx, (n, lab) in enumerate(CYC_WINS):
        켬 = idx == _기본
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
              f'style="flex:1;text-align:center;font-size:11.5px;padding:.42rem .2rem;'
              f'border-radius:8px;cursor:pointer;font-weight:800;white-space:nowrap;'
              f'background:{"#1b2432" if 켬 else "#0d1118"};'
              f'border:1px solid {"#3a465c" if 켬 else "#1e2531"};'
              f'color:{"#fff" if 켬 else "#7d848f"}">{lab}</span>')

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
            '<p style="margin:0 0 2px;font-size:11.5px;color:#8b93a0">섹터 순위 타일</p>'
            '<p style="margin:0 0 10px;font-size:17px;font-weight:800;color:#f2f4f7">'
            '주도권이 어떻게 돌았나</p>'
            f'<div style="display:flex;gap:6px;margin-bottom:9px">{탭}</div>' + 패널 +
            '<p style="margin:9px 0 0;font-size:11px;color:#7d848f;line-height:1.6">'
            '<b style="color:#c9ced6">진한 색 = 상위 3위</b> · 연한 색 = 4~6위 · 회색 = 하위권<br>'
            '섹터는 <b>그 기간 누적 초과수익이 높은 순</b>으로 정렬 · 가로 눈금은 <b>주 단위</b><br>'
            '<b style="color:#f0c65a">금색 테두리</b> = 내 관심종목이 속한 섹터</p>'
            '</div>' + JS)



# ══════════════════════════════════════════════════════
# 🔮 돌아올 섹터 — 예보 저장 · 적중률 채점
# ══════════════════════════════════════════════════════
#  ⚠️ 왜 필요한가 (2026-08-21)
#     "이 섹터가 곧 온다"고 매일 말하면서 **맞았는지는 한 번도 안 세었다.**
#     리포트의 정체성이 "자기 예보를 채점표로 남긴다"인데 이 코너만 빠져 있었다.
#
#  ⚠️ 절대 원칙 2 — 없는 비교는 만들지 않는다.
#     과거 예보를 저장한 적이 없으므로 **지금 적중률을 계산하면 지어낸 숫자**다.
#     오늘부터 쌓고, 표본 5회가 넘을 때까지는 "축적 중"만 말한다.
RS_FILE = "return_sector_log.json"
RS_HORIZON = 10        # 예보 후 몇 거래일 안에 상위권에 들면 '적중'인가
RS_MIN_SAMPLE = 5      # 이 미만이면 적중률을 말하지 않는다


def _rs_log():
    try:
        v = load_json(RS_FILE)
        return v if isinstance(v, list) else []
    except Exception:
        return []


def rs_save_forecast(임박목록):
    """오늘의 '임박' 예보를 기록한다. 같은 날 두 번 저장하지 않는다."""
    if not 임박목록:
        return
    log = _rs_log()
    if any(r.get("날짜") == DATE for r in log):
        return
    log.append({"날짜": DATE, "임박": list(임박목록)[:6], "채점": None})
    try:
        with open(RS_FILE, "w", encoding="utf-8") as f:
            json.dump(log[-400:], f, ensure_ascii=False, indent=1)
        print(f"   🔮 돌아올 섹터 예보 {len(임박목록)}건 기록")
    except Exception as e:
        print(f"   ⚠️ 예보 기록 실패: {type(e).__name__}")


def rs_grade(날짜들, 순위):
    """지난 예보를 채점한다 — 예보 후 RS_HORIZON 거래일 안에 CYC_TOP 안에 들었나.

    반환: (적중, 총, 표본충분?)
    """
    log = _rs_log()
    if not log or not 날짜들:
        return 0, 0, False
    idx = {d: i for i, d in enumerate(날짜들)}
    적중 = 총 = 0
    for r in log:
        d0 = r.get("날짜")
        if d0 not in idx:
            continue
        i0 = idx[d0]
        if i0 + RS_HORIZON >= len(날짜들):
            continue                       # 아직 결과가 안 나온 예보는 세지 않는다
        for nm in (r.get("임박") or []):
            rk = 순위.get(nm)
            if not rk:
                continue
            총 += 1
            창 = [v for v in rk[i0 + 1: i0 + 1 + RS_HORIZON] if v]
            if 창 and min(창) <= CYC_TOP:
                적중 += 1
    return 적중, 총, 총 >= RS_MIN_SAMPLE


def rs_grade_html(날짜들, 순위):
    """적중률 한 줄. 표본이 모자라면 축적 상태만 정직하게 알린다."""
    적중, 총, 충분 = rs_grade(날짜들, 순위)
    if not 충분:
        return ('<p class="rs-grade dim">⏳ 적중률은 '
                f'예보 <b>{총}건</b>이 쌓였습니다 · '
                f'<b>{RS_MIN_SAMPLE}건</b>부터 공개합니다 '
                f'(예보 후 {RS_HORIZON}거래일 안에 상위 {CYC_TOP}위 진입 여부로 채점)</p>')
    율 = 적중 / 총 * 100
    c = FS_BUY if 율 >= 50 else FS_SELL
    return ('<p class="rs-grade">📊 <b>지금까지의 적중률</b> — '
            f'임박이라고 말한 <b>{총}번</b> 중 <b style="color:{c}">{적중}번</b>이 '
            f'{RS_HORIZON}거래일 안에 상위 {CYC_TOP}위에 들었습니다 '
            f'(<b style="color:{c}">{율:.0f}%</b>). '
            '과거 기록이며 확률 예측이 아닙니다.</p>')


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
    # 오늘의 '임박' 예보를 기록해 둔다 — 나중에 채점하기 위해서다
    rs_save_forecast([n for n in 순위 if 그룹(n) == "임박"])
    본문 = rs_grade_html(날짜, 순위)
    # 🆕 2026-08-24 — 주기를 말할 수 있는 섹터가 하나도 없으면 그 사실을 **맨 위에**
    #    한 줄로 밝힌다. 이 안내가 없으면 아래 줄마다 "표본이 적습니다"만 반복돼
    #    독자는 코너가 고장 난 줄 안다. 표본이 차면 이 줄은 자동으로 사라진다.
    if not any(ST[n]["평균주기"] for n in ST):
        본문 += (f'<p style="margin:0 0 10px;padding:7px 9px;background:#0f131a;'
                f'border-left:2px solid #5b9bff;border-radius:0 6px 6px 0;'
                f'font-size:10.5px;color:#8d949f;line-height:1.6">'
                f'📌 지금은 비교할 수 있는 거래일이 <b style="color:#c9ced6">{len(날짜)}일</b>뿐이라, '
                f'아직 어느 섹터도 \'평균 주기\'를 말할 단계가 아닙니다. '
                f'지금 상위권에 있는 곳만 사실대로 알려드리고, 주기는 기록이 쌓이는 대로 붙이겠습니다.<br>'
                f'<span style="color:#6f7784">아래 줄의 <b style="color:#8d949f">등판 N회</b>는 '
                f'그 섹터가 최근 {len(날짜)}일 안에 상위 {CYC_TOP}위에 든 횟수입니다 — '
                f'주기를 말하려면 최소 {CYC_MIN_간격 + 1}회가 필요합니다.</span></p>')
    for key, 라벨, 색, 설명 in GRP:
        멤버 = [n for n in 순위 if 그룹(n) == key]
        if not 멤버:
            continue
        if key == "대기":
            멤버.sort(key=lambda n: (dday(n) if dday(n) is not None else 999))
        else:
            멤버.sort(key=lambda n: -(위상(n) or 0))
        # 🆕 2026-08-22 HO 지시 — 그룹마다 "가장 핫한/가장 임박한" 상위 2개만 먼저
        #    보여주고, 나머지는 더보기로 접는다. 정렬은 이미 위에서 그 기준대로
        #    돼 있으니(대기=D-day 임박순, 나머지=위상 높은순) 앞 2개를 자르기만
        #    하면 된다.
        앞2, 뒤나머지 = 멤버[:2], 멤버[2:]

        def _row(nm):
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
                # 🆕 2026-08-24 — 왜 주기를 안 보여주는지 숫자로 밝힌다.
                #    ⚠️ 단, 한 번도 등판 못 한 섹터에 "표본이 적다"고 하면 오해다.
                #       그건 표본 문제가 아니라 **아직 상위권에 못 온 것**이다. 문장을 나눈다.
                if not _s["회수"]:
                    주기문 = f"최근 {len(날짜)}일간 상위 {CYC_TOP}위 진입 없음"
                else:
                    # 🆕 2026-08-26 — 「표본이 적어 아직 주기를 못 믿습니다」가
                    #    섹터 줄마다 최대 16번 반복돼 소음이 됐다. 사유는 코너
                    #    맨 위 안내가 이미 한 번 말한다. 여기는 **사실(등판 횟수)만**
                    #    남긴다. 표본이 차면 위 안내가 사라지고 평균 주기가 들어온다.
                    주기문 = f"등판 {_s['회수']}회"
            # 🆕 2026-08-22 — 섹터명을 누르면 대표 종목이 펼쳐진다(섹터 지도와 같은 방식).
            #    "돌아올 섹터라는데, 그래서 뭘 사라는 거지?"에 답이 없던 문제를 메운다.
            _pid = f"rsm_{_GRID_SEQ[0]}_{abs(hash(nm)) % 99999}"
            _GRID_SEQ[0] += 1
            _panel = zone_member_panel(nm, _pid)
            # 🆕 2026-08-22 — 섹터명이 길면 ellipsis가 화살표까지 잘라먹었다.
            #    이름과 화살표를 **분리**해서, 줄어드는 건 이름만이고
            #    화살표(flex:none)는 항상 자리를 지키게 한다.
            _이름셀 = (f'<span class="rs-name" onclick="ztog(\'{_pid}\')" '
                     f'style="width:88px;flex:none;min-width:0;display:flex;'
                     f'align-items:center;justify-content:flex-end;gap:1px;'
                     f'font-size:10.5px;font-weight:600;color:#e8eaee;'
                     f'padding:1px 3px;border-radius:4px;cursor:pointer;'
                     f'-webkit-tap-highlight-color:transparent">'
                     f'<span style="min-width:0;overflow:hidden;text-overflow:ellipsis;'
                     f'white-space:nowrap">{nm}</span>{ZONE_ARROW}</span>'
                     if _panel else
                     f'<span class="rs-name" style="width:88px;flex:none;min-width:0;'
                     f'font-size:10.5px;font-weight:600;color:#e8eaee;text-align:right;'
                     f'padding:1px 3px;border-radius:4px;overflow:hidden;'
                     f'text-overflow:ellipsis;white-space:nowrap">{nm}</span>')
            return (f'<div class="rs-row" data-zone="{nm}" '
                     f'style="display:flex;align-items:center;gap:7px;margin-bottom:5px">'
                     f'{_이름셀}'
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
                     f'{주기문}</p>{_panel}')

        rows = "".join(_row(nm) for nm in 앞2)
        더보기 = ""
        if 뒤나머지:
            gid = f"rsMore_{key}"
            더보기 = (f'<div class="hidden-block" id="{gid}">'
                     f'{"".join(_row(nm) for nm in 뒤나머지)}</div>'
                     f'<button class="more-btn" style="margin:2px 0 6px 95px;font-size:10px;'
                     f'padding:.25rem .6rem;max-width:calc(100% - 95px);white-space:nowrap;'
                     f'overflow:hidden;text-overflow:ellipsis" '
                     f'onclick="toggleMore(\'{gid}\',this,'
                     f'\'▾ {라벨} {len(뒤나머지)}개 더보기\')">▾ {라벨} {len(뒤나머지)}개 더보기</button>')
        rows += 더보기

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
    return (ZTOG_JS
            + '<div style="background:#141922;border:1px solid #232a36;border-radius:12px;'
            'padding:13px 14px;margin:10px 0 0">'
            '<p style="margin:0 0 2px;font-size:11.5px;color:#8b93a0">돌아올 섹터</p>'
            '<p style="margin:0 0 4px;font-size:17px;font-weight:800;color:#f2f4f7">'
            '다음 순번은 어디인가</p>'
            '<p style="margin:0 0 11px;font-size:10.5px;color:#e0c060">'
            '👆 섹터 이름을 누르면 대표 종목이 나옵니다</p>'
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
# ⚠️ 5일 탭 추가(2026-08-21) — 포착 직후 며칠이 가장 중요한데 그걸 못 보고 있었다.
#    다른 코너와 같은 창 구성으로 맞춘다.
CAP_WINS = [(5, "5일"), (20, "20일"), (60, "60일"), (120, "120일")]
CAP_KINDS = [("강세", "강세레이더", "#ff6b4a"), ("매집", "매집레이더", "#4ade80")]


def _cap_curves(일수, 시장):
    """{종류: {경과: 평균등락}} 과 지수 벤치마크 {경과: 평균등락}."""
    # 📅 거래일만 — archive_days()가 휴장일 중복을 걸러준다
    파일들 = archive_days(일수)
    종가 = _index_close_map()
    날짜들 = sorted(종가)
    _idx = 1 if 시장 == "코스닥" else 0
    곡선 = {k: {} for k, _, _ in CAP_KINDS}
    벤치 = {}
    쌍 = {k: {} for k, _, _ in CAP_KINDS}
    for _ymd, d in 파일들:
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


# ══════════════════════════════════════════════════════════════
# 🛬 포착 그 후 — 레이더 성능 공시 (2026-08-24 신설, HO 지시)
# ══════════════════════════════════════════════════════════════
#  왜 만드나 — 종목을 골라주는 서비스는 널렸지만 **자기 성적을 매일 공개하는
#  서비스는 없다.** 사람이 하는 채널은 구조적으로 못 한다(틀린 걸 지워야 장사가
#  되니까). 우리는 지운 적이 없다는 게 상품이다.
#
#  ⚠️ 이 숫자가 정확히 무슨 뜻인가 (HO 질문에 대한 답을 코드에 박아둔다)
#     "D+5 평균 +3.1%" = **5거래일 전에 레이더가 잡은 종목들이,
#      포착 당일 종가 대비 오늘까지 평균 3.1% 올랐다**는 뜻이다.
#     · 기준가 = 포착일 종가(추적 데이터의 '포착가')
#     · 5거래일은 달력이 아니라 **장이 열린 날**로 센다
#     · 아직 5일이 안 지난 종목은 그 탭 계산에서 빠진다
#     ⚠️ 구독자는 포착 당일 종가에 살 수 없다. 그래서 이건
#        "이만큼 벌 수 있었다"가 아니라 **지표 자체의 성능**이다.
#
#  ⚠️ 표본이 없으면 지어내지 않는다. 그 탭은 "축적 중 (N일 경과)"만 보여준다.
# 🆕 2026-08-24 HO 확정 — 탭을 **점(정확히 N일)이 아니라 구간(N~M일)**으로 잡는다.
#  ⚠️ 왜 구간인가 — 정확히 5일차인 종목만 세면 표본이 하루치(한두 종목)로 쪼그라든다.
#     그날 시장이 급락했으면 성적 전체가 그 하루에 휘둘린다.
#     5~10일로 넓히면 표본이 몇 배가 되고, 서로 다른 날에 포착된 종목이 섞여
#     **특정 하루의 운**이 희석된다.
#  ⚠️ 대가도 있다 — 5일 보유와 10일 보유가 한 평균에 섞인다. 그래서
#     **벤치마크(같은 기간 코스피)를 반드시 함께** 보여준다. 보유 기간이
#     섞여도 "시장보다 나았나"는 그대로 성립하기 때문이다.
CATCH_WINS = [(5, 10, "5일"), (20, 30, "20일"),
              (60, 80, "60일"), (120, 160, "120일")]
CATCH_MIN_표본 = 3
_MKT_CLOSE_CACHE = {}


def _catch_rows(data, key):
    """추적 목록을 꺼낸다. key = '매집레이더' | '강세레이더'."""
    tr = ((data.get(key) or {}).get("추적")) or []
    return [t for t in tr if isinstance(t, dict)
            and isinstance(t.get("이후등락"), (int, float))
            and isinstance(t.get("경과"), int)]


def _market_close_map():
    """{YYYYMMDD: 코스피 종가} — market_history.json에서.

    ⚠️ 벤치마크를 여기서 만드는 이유: 추적 데이터에 '포착지수'를 넣기 시작한 건
       오늘부터라, 그것만 쓰면 당분간 벤치마크가 전부 빈칸이 된다.
       market_history에는 코스피 종가가 예전부터 쌓여 있어 **소급 계산이 된다.**
    """
    if _MKT_CLOSE_CACHE:
        return _MKT_CLOSE_CACHE
    try:
        with open("market_history.json", encoding="utf-8") as f:
            일별 = (json.load(f) or {}).get("일별") or []
        for r in 일별:
            d = str(r.get("날짜") or "").replace("-", "")
            v = r.get("코스피")
            if len(d) == 8 and isinstance(v, (int, float)):
                _MKT_CLOSE_CACHE[d] = float(v)
    except Exception as e:
        print(f"   ⚠️ 벤치마크용 지수 이력 읽기 실패 — {type(e).__name__}")
    return _MKT_CLOSE_CACHE


def _bench_for(포착일):
    """포착일 대비 오늘까지의 코스피 등락(%)."""
    m = _market_close_map()
    if not m:
        return None
    시작 = m.get(str(포착일))
    끝 = m.get(max(m))
    if not 시작 or not 끝:
        return None
    return (끝 - 시작) / 시작 * 100


def _catch_stat(rows, lo, hi):
    """경과 lo~hi 거래일 구간 종목들의 성적 + 같은 기간 코스피."""
    대상 = [t for t in rows if lo <= t.get("경과", -1) <= hi]
    if len(대상) < CATCH_MIN_표본:
        남은 = [lo - t["경과"] for t in rows if t.get("경과", 0) < lo]
        return {"부족": True, "수": len(대상), "대기": len(rows),
                "곧": min(남은) if 남은 else None}
    수익 = [t["이후등락"] for t in 대상]
    벤치들 = [b for b in (_bench_for(t.get("포착일")) for t in 대상)
             if isinstance(b, (int, float))]
    승 = sum(1 for x in 수익 if x > 0)
    평균 = sum(수익) / len(수익)
    벤치 = (sum(벤치들) / len(벤치들)) if 벤치들 else None
    best = max(대상, key=lambda t: t["이후등락"])
    worst = min(대상, key=lambda t: t["이후등락"])
    return {"부족": False, "수": len(대상), "평균": 평균, "승": 승,
            "승률": 승 / len(대상) * 100, "벤치": 벤치,
            "초과": (평균 - 벤치) if 벤치 is not None else None,
            "최고": (best.get("종목명"), best["이후등락"]),
            "최저": (worst.get("종목명"), worst["이후등락"])}


def _catch_card(rows, lo, hi, 이름):
    st = _catch_stat(rows, lo, hi)
    if st["부족"]:
        곧 = (f' · 가장 빠른 종목이 {st["곧"]}거래일 뒤 들어옵니다'
             if st.get("곧") is not None else "")
        return (f'<div class="cg-card"><p class="cg-h">{이름}</p>'
                f'<p class="cg-empty">축적 중 — {lo}~{hi}거래일 구간에 든 종목 '
                f'{st["수"]}개(추적 중 {st.get("대기", 0)}종목){곧}</p></div>')
    c = "#ff6b4a" if st["평균"] >= 0 else "#5b9bff"
    hn, hv = st["최고"]; ln, lv = st["최저"]
    if st["초과"] is not None:
        ec = "#ff6b4a" if st["초과"] >= 0 else "#5b9bff"
        벤치HTML = (f'<p class="cg-bench">같은 기간 코스피 '
                   f'<b>{st["벤치"]:+.1f}%</b> · 초과수익 '
                   f'<b style="color:{ec}">{st["초과"]:+.1f}%p</b></p>')
    else:
        벤치HTML = '<p class="cg-bench">벤치마크에 필요한 지수 이력이 부족합니다</p>'
    return (f'<div class="cg-card"><p class="cg-h">{이름}'
            f'<span class="cg-n">{st["수"]}종목 · {lo}~{hi}일</span></p>'
            f'<div class="cg-main"><span class="cg-avg" style="color:{c}">'
            f'{st["평균"]:+.1f}%</span>'
            f'<span class="cg-win">승률 {st["승률"]:.0f}% '
            f'({st["승"]}/{st["수"]})</span></div>'
            f'{벤치HTML}'
            f'<p class="cg-ext">🏆 {hn} {hv:+.1f}% · 💀 {ln} {lv:+.1f}%</p></div>')


def _catch_compare(돈몰림, V반등, 매집, lo, hi):
    """세 기법의 **시장 대비 성적**을 한 그래프에 나란히.

    🆕 2026-08-26 HO 지시 — "두 개의 데이터를 쌓아주고 시장 대비 그래프로 그려줘".
    ⚠️ 절대수익이 아니라 **초과수익(%p)**으로 그린다.
       같은 기간 시장이 -4%였는지 +2%였는지에 따라 -3%의 의미가 정반대다.
       세 기법이 각자 다른 날 잡혔으니 벤치마크도 각자 다르다 — 그래서
       "얼마 벌었나"가 아니라 "시장보다 얼마나 나았나"로만 비교가 성립한다.
    ⚠️ 표본이 없는 기법은 막대를 그리지 않는다. 0으로 그리면 "성적 0"으로 읽힌다.
    """
    항목 = []
    for rows, 이름, 색 in ((돈몰림, "돈이 몰림", "#f0c65a"),
                          (V반등, "V자 반등", "#74f0d4"),
                          (매집, "조용히 모으는 손", "#8fd0e8")):
        st = _catch_stat(rows, lo, hi)
        if st["부족"] or st.get("초과") is None:
            continue
        항목.append((이름, 색, st["초과"], st["수"]))
    if len(항목) < 2:
        return ""
    mx = max(abs(v) for _, _, v, _ in 항목) or 1
    W, H = 320, 24 + len(항목) * 26
    L, R = 96, 46
    z = L + (W - L - R) / 2
    half = (W - L - R) / 2
    g = (f'<line x1="{z:.0f}" y1="16" x2="{z:.0f}" y2="{H - 6}" stroke="#f0c65a" '
         f'stroke-width="1.4" stroke-dasharray="3 2"/>'
         f'<text x="{z:.0f}" y="10" text-anchor="middle" font-size="8.5" '
         f'font-weight="800" fill="#f0c65a">시장과 같음</text>')
    for i, (이름, 색, v, n) in enumerate(항목):
        y = 22 + i * 26
        w = abs(v) / mx * half * 0.9
        # 🆕 2026-08-29 HO 지시 — 막대 색을 **시장 대비 우열**로 칠한다.
        #    [WHY] 예전엔 기법마다 고정색(금색·청록·하늘)이라, 정작 이 그래프가
        #    말하려는 «시장을 이겼나»가 색에서 안 보였다. 방향은 막대가 왼쪽/
        #    오른쪽인 것으로만 알 수 있어 한눈에 안 들어왔다.
        #    → 리포트 전체 색 규칙 그대로: 시장보다 나으면 빨강(#ff6b4a),
        #      못하면 파랑(#5b9bff). 같은 뜻에 같은 색을 쓴다.
        _막대색 = "#ff6b4a" if v >= 0 else "#5b9bff"
        g += (f'<rect x="{(z if v >= 0 else z - w):.1f}" y="{y}" '
              f'width="{max(2, w):.1f}" height="13" rx="2.5" fill="{_막대색}"/>'
              f'<text x="{L - 6}" y="{y + 10}" text-anchor="end" font-size="9" '
              f'fill="#c9ced6">{이름}</text>'
              f'<text x="{W - R + 4}" y="{y + 10}" font-size="9.5" font-weight="800" '
              f'fill="{_막대색}">{v:+.1f}%p</text>'
              f'<text x="{L - 6}" y="{y + 21}" text-anchor="end" font-size="7.5" '
              f'fill="#6f7784">{n}종목</text>')
    최고 = max(항목, key=lambda x: x[2])
    _최고색 = "#ff6b4a" if 최고[2] >= 0 else "#5b9bff"
    return (f'<div class="cg-cmp"><p class="cg-cmp-h">📊 세 기법, 시장 대비로 비교하면</p>'
            f'<svg viewBox="0 0 {W} {H}" style="width:100%;height:auto">{g}</svg>'
            f'<p class="cg-cmp-n">'
            f'<b style="color:#ff6b4a">빨강(오른쪽)</b>은 같은 기간 시장보다 나았다는 뜻이고, '
            f'<b style="color:#5b9bff">파랑(왼쪽)</b>은 시장에 못 미쳤다는 뜻이에요. '
            f'지금은 <b style="color:{_최고색}">{최고[0]}</b>이 가장 앞서 있어요 — '
            f'다만 표본이 적을 때는 순서가 자주 바뀝니다.</p></div>')


def build_catch_after(data):
    """강세·매집 두 레이더의 포착 후 성적을 기간 탭으로 보여준다."""
    # 🆕 2026-08-26 HO 지시 — 강세를 **기법별로 쪼갠다.**
    #  [WHY] 「돈이 몰림」과 「V자 반등」은 재는 기준부터 다른 별개 기법이다.
    #        한 평균에 섞으면 어느 쪽이 유효한지 영영 알 수 없다.
    #  ⚠️ 추적 데이터의 '유형들'로 나눈다(한 종목이 둘 다일 수 있어 중복 허용).
    #  ⚠️ 2026-08-25 이전 추적분에는 '유형들'이 없다 → 어느 쪽에도 안 들어간다.
    #     지어내지 않는다. 표본은 앞으로 쌓이는 것부터 정확해진다.
    매집 = _catch_rows(data, "매집레이더")
    _강세전체 = _catch_rows(data, "강세레이더")
    def _유형필터(rows, 키):
        return [t for t in rows if 키 in (t.get("유형들") or [])]
    돈몰림 = _유형필터(_강세전체, "돈이 몰린 종목")
    V반등 = _유형필터(_강세전체, "V자 반등 종목")
    if not 매집 and not _강세전체:
        return ""
    탭, 패널 = "", ""
    for i, (lo, hi, lab) in enumerate(CATCH_WINS):
        n = lo
        켬 = " on" if i == 0 else ""
        # 🆕 2026-08-29 HO 지시 — 탭 디자인 정리.
        #    [문제] «5일»(큰 글씨) 밑에 «5~10일»(작은 글씨)이 붙어 있었다.
        #    같은 말을 두 번 하면서 탭만 두 줄로 두꺼워지고 지저분했다.
        #    (2026-08-25에 "라벨만 보면 딱 5일차로 읽힌다"는 지적을 부제로
        #     해결했었는데, 그게 오히려 새 문제를 만든 셈이다.)
        #    [고침] 부제를 없애고 **라벨 자체를 구간으로** 바꾼다 — «D+5~10».
        #    한 줄이라 깔끔하고, 구간이라는 사실도 라벨에 그대로 담긴다.
        탭 += (f'<span class="cg-tab{켬}" data-n="{n}" '
               f'onclick="cgWin({n})">D+{lo}~{hi}</span>')
        본문 = (_catch_card(돈몰림, lo, hi, "💰 돈이 몰림(강세)")
              + _catch_card(V반등, lo, hi, "📈 V자 반등(전환)")
              + _catch_card(매집, lo, hi, "🐢 조용히 모으는 손(매집)")
              + _catch_compare(돈몰림, V반등, 매집, lo, hi))
        패널 += (f'<div class="cg-panel" data-n="{n}" '
                 f'style="display:{"block" if i == 0 else "none"}">{본문}</div>')
    # 🆕 2026-08-25 HO 지시 — 탭 라벨은 «5일»인데 실제로는 5~10일 구간이다.
    #  ⚠️ 라벨만 보면 "딱 5일차"로 읽힌다. 화면 설명문은 실제 코드 조건과
    #     일치해야 한다(원칙 10). 탭 바로 아래 박스에 구간을 못 박는다.
    return (f'<div class="cg-box"><div class="cg-tabs">{탭}</div>{패널}'
            f'<p class="cg-note">📌 <b>이 숫자가 뜻하는 것</b> — '
            f'«5일 +3.1%»는 <b>포착한 지 5~10거래일 된 종목들이 '
            f'포착가 대비 지금 평균 3.1% 올라 있다</b>는 뜻이에요. '
            f'딱 5일차만 세면 종목이 한두 개뿐이라 그날 시장에 휘둘려서, '
            f'구간으로 넓혀 표본을 늘렸어요(20일 탭은 20~30일, 60일 탭은 60~80일). '
            f'그래서 <b>같은 기간 코스피</b>를 꼭 같이 봐주세요 — '
            f'시장이 -5%인데 -3%면 진 게 아니라 이긴 거예요. '
            f'포착은 추천이 아니라 레이더가 걸러낸 자리이고, 이 표는 '
            f'그 레이더가 잘 작동하는지에 대한 성적표예요. '
            f'좋게 나오든 나쁘게 나오든 지우지 않습니다.</p></div>'
            f'<script>function cgWin(n){{'
            f'document.querySelectorAll(".cg-tab").forEach(function(t){{'
            f't.classList.toggle("on",t.dataset.n==n);}});'
            f'document.querySelectorAll(".cg-panel").forEach(function(p){{'
            f'p.style.display=(p.dataset.n==n)?"block":"none";}});}}</script>')


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
              f'style="flex:1;text-align:center;font-size:11.5px;padding:.42rem .2rem;'
              f'border-radius:8px;cursor:pointer;font-weight:800;white-space:nowrap;'
              f'background:{"#1b2432" if 켬 else "#0d1118"};'
              f'border:1px solid {"#3a465c" if 켬 else "#1e2531"};'
              f'color:{"#fff" if 켬 else "#7d848f"}">{lab}</span>')
    JS = """<script>
window.cpTab=function(i){
 document.querySelectorAll('.cp-panel').forEach(function(p){
  p.style.display=(p.dataset.idx==i)?'block':'none';});
 document.querySelectorAll('.cp-tab').forEach(function(t){
  var on=t.dataset.idx==i;
  t.style.background=on?'#1b2432':'#0d1118';
  t.style.border='1px solid '+(on?'#3a465c':'#1e2531');
  t.style.color=on?'#fff':'#7d848f';});};
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
    기본idx = 0   # 기본 탭은 **당일** — "오늘 어디가 셌나"부터 본다 (2026-08-18)

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
                       f'<text x="{X["소형"]+10}" y="{y2+3.5:.0f}" font-size="11" font-weight="700" '
                       f'fill="{c}">{nm[:8]}</text></g>')
            # 시장 평균 — 금색은 '내 섹터' 전용이므로 흰 점선으로.
            # ⚠️ 점선은 '내 관심종목 섹터' 전용이라, 시장 평균은 굵은 흰 실선으로 구분한다.
            mp = " ".join(f'{X[t]},{Y(시장[t]):.0f}' for t in ("대형", "중형", "소형"))
            선 += (f'<polyline points="{mp}" fill="none" stroke="#ffffff" stroke-width="3.4" '
                   f'stroke-linejoin="round" opacity=".9"/>')
            for t in ("대형", "중형", "소형"):
                선 += (f'<circle cx="{X[t]}" cy="{Y(시장[t]):.0f}" r="4" fill="#ffffff" '
                       f'stroke="#141922" stroke-width="1.2"/>')
            선 += (f'<text x="{X["소형"]+10}" y="{Y(시장["소형"])+3.5:.0f}" font-size="11" font-weight="700" '
                   f'fill="#ffffff" font-weight="700">시장 평균</text>')

            축 = "".join(
                f'<line x1="{X[t]}" y1="{T-8}" x2="{X[t]}" y2="{H-B+8}" stroke="#232a36" '
                f'stroke-width="1"/><text x="{X[t]}" y="{T-14}" text-anchor="middle" '
                f'font-size="13.5" font-weight="900" fill="#e8eaee">{t}</text>' for t in X)
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
            '섹터내 대형, 중형, 소형 누가 강했나?</p>'
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
    # 📅 거래일만 — archive_days()가 휴장일 중복을 걸러준다
    파일들 = archive_days(일수)
    if len(파일들) < 3:
        return ""
    # ⚠️ 3개월판은 이력이 충분할 때만 낸다.
    #    지금처럼 19일치뿐이면 66일을 요구해도 결국 같은 19일을 쓰게 되어
    #    1개월판과 **글자 하나 다르지 않은 그림**이 두 번 나온다.
    #    같은 걸 두 번 보여주면 구독자는 "대충 만들었네"로 읽는다. 차라리 숨긴다.
    if 개월 == 3 and len(파일들) < 33:
        return ""
    쌍 = {}          # (종목,포착일) → (경과, 이후등락) 최신값
    for _ymd, _d in 파일들:
        _키 = "강세레이더" if 종류 == "강세" else "매집레이더"
        tr = ((_d.get(_키) or {}).get("추적")) or []
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



def _anomaly_signals(data):
    """🚨 오늘만 나타난 신호 — **오늘 리포트에서 가장 인상적인 2~3가지.**

    ⚠️ 이 코너의 정체 (2026-08-21 확정)
       **종목만 보여주는 코너가 아니다.** 오늘 리포트 전체를 훑어
       "이건 평소와 다르다" 싶은 것을 골라 주는 자리다.
       재료는 **지수·수급·섹터·정책·종목** 어디서든 나올 수 있다.

    ⚠️ 뽑는 원칙
       ① **평소와 다른 것**만 (매일 나오는 건 신호가 아니다)
       ② 종목 언급은 **많아야 1줄** — 여러 줄에 흩뿌리면 초점이 사라진다
       ③ 총 2~3줄. 하나도 없으면 **코너 자체를 띄우지 않는다**
       ④ 강한 순으로 정렬해 위에서부터 자른다
    """
    def _nm_ok(n):
        n = str(n or "")
        if not n:
            return False
        for k in ("KODEX", "TIGER", "KBSTAR", "ARIRANG", "HANARO", "ACE ",
                  "RISE ", "PLUS ", "SOL ", "KOSEF", "ETN", "스팩", "레버리지", "인버스"):
            if k.upper() in n.upper():
                return False
        return True

    후보 = []      # (강도, 앵커, 태그, 문장) — 강도가 높을수록 인상적
    종목줄 = None
    try:
        지 = ((data.get("지수수급") or {}).get("지수") or {})
        def _등(k):
            try:
                return float(str((지.get(k) or {}).get("등락률") or "").replace("%", ""))
            except (TypeError, ValueError):
                return None
        코, 닥 = _등("코스피"), _등("코스닥")

        # ── 지수 ── 코스피·코스닥이 반대로 가거나 격차가 크게 벌어진 날
        if 코 is not None and 닥 is not None:
            갭 = abs(코 - 닥)
            if (코 >= 0) != (닥 >= 0):
                후보.append((95, "#score", "디커플링",
                             f'코스피 <b>{코:+.2f}%</b> · 코스닥 <b>{닥:+.2f}%</b> — '
                             f'두 시장이 <b>반대로 갔습니다</b>'))
            elif 갭 >= 2.0:
                후보.append((80, "#score", "격차",
                             f'코스피와 코스닥 격차가 <b>{갭:.1f}%p</b> — '
                             f'같은 시장인데 딴 나라처럼 움직였습니다'))

        # ── 수급 ── 연속·규모·비차익
        h = load_json("flow_history.json") or []
        h = [r for r in h if isinstance(r, dict) and r.get("실탄") is not None]
        if h:
            t = h[-1]
            for key, nm in (("외현", "외국인"), ("기관", "기관")):
                arr = [x.get(key) for x in h if x.get(key) is not None]
                st = _fs_stat(arr)
                if not st:
                    continue
                if st["연속"] >= 4:
                    후보.append((85, "#flow", "연속",
                                 f'{nm}이 <b>{st["연속"]}일 연속 {st["dir"]}</b> — '
                                 f'한 방향으로 굳어지고 있습니다'))
                elif st["연속"] == 1 and st["n"] >= 5:
                    _앞 = [v for v in arr[:-1]][-6:]
                    _같 = sum(1 for v in _앞 if (v >= 0) != (st["v"] >= 0))
                    if _같 >= 4:
                        후보.append((88, "#flow", "전환",
                                     f'{nm}이 <b>{_같}일 만에 {st["dir"]}로 돌아섰습니다</b> — '
                                     f'방향이 바뀌는 자리일 수 있습니다'))
            st실 = _fs_stat([x["실탄"] for x in h])
            if st실 and st실["배수"] >= 2.0:
                후보.append((82, "#flow", "규모",
                             f'실탄이 평소의 <b>{_배수말(st실["배수"])}</b> — 유별나게 큰 하루입니다'))
            _r = basket_ratio(t.get("비차익"), t.get("실탄"))
            if _r is not None and abs(_r) >= 150:
                후보.append((75, "#flow", "비차익",
                             f'비차익이 실탄의 <b>{abs(_r):.0f}%</b> — '
                             f'종목이 아니라 <b>지수를 통째로</b> 사고판 날입니다'))

        # ── 섹터 ── 확산도 만점이 여럿
        만점 = [x.get("테마명") for x in (data.get("주도섹터") or [])
                if (x.get("확산도") or 0) >= 100]
        if len(만점) >= 3:
            후보.append((70, "#sectors", "확산",
                         f'<b>{len(만점)}개 섹터</b>가 확산도 100% — '
                         f'그 안에서는 <b>안 오른 종목이 하나도 없었습니다</b>'))

        # ── 종목 (최대 1줄) ── 강세 > 매집 > 주인공
        강 = []
        for v in ((data.get("강세레이더") or {}).get("신규") or {}).values():
            for x in (v or []):
                if _nm_ok(x.get("종목명")):
                    강.append((x.get("종목명"), x.get("등락률")))
        강.sort(key=lambda t_: -(t_[1] or 0))
        if 강:
            n_, v_ = 강[0]
            더 = f' 외 {len(강)-1}종목' if len(강) > 1 else ''
            종목줄 = (60, "#radar", "불난자리",
                     f'<b>{n_}</b>' + (f'가 <b>+{v_:.1f}%</b>' if isinstance(v_, (int, float)) else '')
                     + f'{더} — 거래량과 주가가 함께 터졌습니다')
        else:
            쌍 = [x for x in ((data.get("매집레이더") or {}).get("종목") or [])
                  if x.get("유형") == "쌍끌이" and _nm_ok(x.get("종목명"))]
            쌍.sort(key=lambda x: -(x.get("매집강도") or x.get("시총대비") or 0))
            if 쌍:
                종목줄 = (55, "#acc", "매집",
                         f'<b>{쌍[0].get("종목명")}</b>' +
                         (f' 외 {len(쌍)-1}종목' if len(쌍) > 1 else '') +
                         ' — 외국인·기관이 <b>둘 다</b> 조용히 사 모았습니다')
    except Exception:
        pass

    후보.sort(key=lambda t_: -t_[0])
    # ⚠️ 종목줄은 **최대 1개**만. 나머지는 시장 차원 신호로 채운다.
    묶음 = 후보[:3]
    if 종목줄:
        묶음 = 후보[:2] + [종목줄]
        묶음.sort(key=lambda t_: -t_[0])
    return [(a, b, c) for _, a, b, c in 묶음[:3]]

def _tomorrow_line(data):
    """🌅 내일 볼 것 — **숫자 기준선 하나**로 못 박는다.

    ⚠️ "확인하세요"는 채점할 수 없다. **넘느냐 마느냐**로 써야
       다음날 자동으로 맞았는지 셀 수 있다.
    """
    try:
        h = load_json("flow_history.json") or []
        h = [r for r in h if isinstance(r, dict) and r.get("외현") is not None]
        if not h:
            return ""
        외 = _fs_stat([x["외현"] for x in h])
        기 = _fs_stat([x["기관"] for x in h if x.get("기관") is not None])
        if not 외:
            return ""
        # 기준선 = 최근 20일 평균 규모의 절반 (반올림해서 읽기 쉽게)
        선 = max(1000, round(외["평소"] * 0.5 / 1000) * 1000)
        if 외["v"] >= 0:
            본문 = (f'외국인 순매수가 <b>{선:,.0f}억을 넘으면</b> 오늘 흐름이 이어지는 것으로 봅니다. '
                   f'<b>마이너스로 돌아서면</b> 오늘은 하루짜리였던 겁니다.')
        else:
            본문 = (f'외국인 순매도가 <b>{선:,.0f}억 안으로 줄면</b> 진정 신호로 봅니다. '
                   f'<b>더 커지면</b> 이탈이 이어지는 중입니다.')
        if 기 and 기["연속"] >= 3:
            본문 += f' 함께 볼 것 — <b>기관이 {기["연속"]}일 연속 {기["dir"]}</b>를 멈추는지.'
        _만기, _ = expiry_note()
        if _만기:
            본문 += (' ⚠️ 내일은 <b>만기일</b>입니다 — 비차익이 기계적으로 튀니 '
                    '그 숫자로 판단하지 마세요.')
        return 본문
    except Exception:
        return ""


def build_core(핵심편, data, 해석):
    """핵심편 '90초 브리핑' — 리포트 최상단.

    글(정의·공감·왜·특징·뒤집어보기)은 Claude가, 숫자 타일·티저는 코드가 만든다.
    ⚠️ 핵심편이 없으면 **조용히 사라지지 않는다** (2026-08-19).
       핵심편은 100% Claude 해석글이라, 워크플로를 '재사용(무료)'으로 돌리면
       archive/report_YYYYMMDD.json 자체가 안 만들어져 통째로 빠진다.
       예전에는 빈 문자열만 반환해서, 발행하고 나서야 "핵심편이 없다"를 알았다.
       (같은 사고가 여러 번 반복됐다)
       → 이제 **자리에 안내 상자를 남기고 빌드 로그에도 크게 경고**한다.
    """
    if not 핵심편:
        # ⚠️ 오늘 해석글이 없으면 **가장 최근 거래일의 핵심편**을 빌려 쓴다(2026-08-21).
        #    재사용(무료)으로 돌려도 90초 브리핑이 사라지지 않게 하기 위함이다.
        #    ⚠️ 반드시 '어제 글'임을 화면에 밝힌다. 오늘 글인 척하면 거짓말이 된다.
        _대체, _대체날 = None, None
        try:
            for _f in sorted(alist(r"report_\d{8}\.json"), reverse=True):
                _ymd = _f[7:15]
                if _ymd >= DATE:
                    continue
                with open(apath(_f), encoding="utf-8") as _fp:
                    _k = ((json.load(_fp).get("해석글") or {}).get("핵심편")) or None
                if _k:
                    _대체, _대체날 = _k, _ymd
                    break
        except Exception:
            _대체 = None
        if _대체:
            print(f"ℹ️ 오늘 해석글이 없어 {_대체날} 핵심편을 빌려 씁니다(화면에 명시).")
            _배너 = (
                '<div style="background:#2a1a12;border:1px solid #6b3f1f;border-radius:10px;'
                'padding:9px 12px;margin:0 0 12px">'
                '<p style="margin:0;font-size:11.5px;color:#f0c65a;font-weight:800">'
                f'⚠️ 아래 90초 브리핑은 <b>{_대체날[4:6]}/{_대체날[6:]} 글</b>입니다</p>'
                '<p style="margin:4px 0 0;font-size:10.5px;color:#c9ced6;line-height:1.6">'
                '오늘 해석글이 아직 만들어지지 않아 직전 거래일 것을 그대로 싣습니다. '
                '아래 <b>숫자와 표는 모두 오늘 것</b>이니 안심하고 보셔도 됩니다.</p></div>')
            return _배너 + build_core(_대체, data, 해석)
        print("=" * 60)
        print("⚠️  핵심편 없음 — 오늘 해석글(archive/report_*.json)이 없습니다.")
        print("    워크플로를 'Claude 해석글 = 새로 생성(과금)'으로 다시 돌리세요.")
        print("=" * 60)
        return (
            '<div style="background:#2a1a12;border:1px solid #6b3f1f;border-radius:12px;'
            'padding:14px 16px;margin:0 0 14px">'
            '<p style="margin:0;font-size:13px;font-weight:800;color:#f0c65a">'
            '⏱️ 핵심편이 아직 준비되지 않았습니다</p>'
            '<p style="margin:6px 0 0;font-size:11.5px;color:#c9ced6;line-height:1.7">'
            '오늘의 해석글이 만들어지지 않아 90초 브리핑을 실을 수 없습니다. '
            '아래 <b>정밀 관제(심층편)</b>의 숫자와 표는 모두 정상입니다.<br>'
            '<span style="color:#8b93a0">운영자: 워크플로를 '
            '<b style="color:#f0c65a">Claude 해석글 = 새로 생성</b>으로 다시 실행하면 채워집니다.</span></p>'
            '</div>')
    # 금요일·연휴 직전에는 "내일"이 틀린 말이 된다 → 실제 다음 거래일로 표기.
    try:
        _NEXT_LABEL = trading_day_context(
            datetime.strptime(data.get("날짜") or DATE, "%Y%m%d").date())["다음거래일표현"]
    except Exception:
        _NEXT_LABEL = "내일"
    지수수급 = data.get("지수수급") or {}
    코수 = 지수수급.get("코스피_수급") or {}
    rows = _load_market_history()

    # ── 지수 헤더 ──
    # 🆕 2026-08-22 HO 지시 — 핵심편 헤더 막대와 심층편 「오늘의 성적표」가
    #    같은 지수·수급을 **다른 그림**으로 두 번 보여줘 헷갈린다는 지적.
    #    → 핵심편도 심층편과 **똑같은 성적표 카드**를 쓴다. 같은 정보는 같은 모양으로.
    #    ⚠️ 계기판(core_flow_gauge)은 그대로 둔다 — 실탄은 성적표에 없는 정보다.
    #    ⚠️ 🚦신호등은 **반드시 유지**한다. 옛 헤더 안에 들어 있어서 헤더를 걷어낼 때
    #       같이 사라진 적이 있다(2026-08-22 사고). 지금은 별도 함수로 분리했다.
    _지수 = (지수수급 or {}).get("지수") or {}
    _코, _닥 = _지수.get("코스피", {}), _지수.get("코스닥", {})
    _닥수 = (지수수급 or {}).get("코스닥_수급") or {}
    신호등블록 = build_signal_head(지수수급, data.get("파생"), 코수,
                              관제=data.get("관제지수"),
                              사건명=(해석.get("사건명") or ""))
    # ⚠️ id="score"는 「오늘 확인해야 할 신호」의 '확인 ↓' 이동 목적지다.
    # 🔴 큰 계기판(core_flow_gauge) 호출 안 함 — 성적표 카드 안에 코스피·
    #    코스닥 각각의 미니 계기판이 이미 들어있어, 코스피만 크게 한 번
    #    더 보여주면 원칙5(같은 그림 두 번) 위반이 된다. 함수 자체는
    #    안 지웠다(원칙3) — 되살리려면 여기 + core_flow_gauge()만 붙이면 됨.
    지수스트립 = (f'<div class="idx-grid" id="score">'
                f'{build_score_card("KOSPI", _코, 코수)}'
                f'{build_score_card("KOSDAQ", _닥, _닥수)}</div>'
                + _flow_comment())

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
    # ── 📰 오늘 시장을 움직인 것들 + 🧭 왜 이렇게 움직였을까요 = 한 카드 ──
    # 🆕 2026-08-22 HO 지시 — 둘을 합친다.
    #    팩트(태그별 소주제)를 먼저 보여주고, 같은 상자 안에서 바로
    #    "그래서 왜 그랬냐면요"로 닫는다. 카드가 둘로 나뉘어 있으면
    #    독자가 팩트만 보고 스크롤을 내려 '왜'를 놓친다.
    #    소주제(반도체·수급·산업·글로벌 등) 분류는 그대로 유지한다.
    이슈블록 = (f'<div class="iss90"><p class="iss90-h">📰 오늘, 시장에 무슨 일이 있었냐면요</p>'
              f'<p class="iss90-s">뉴스 중에서 오늘 진짜로 주가를 움직인 것만 골랐어요</p>{이슈들}</div>'
              ) if 이슈들 else (
                  # ⚠️ 재사용 모드에선 핵심이슈가 없어 코너가 통째로 사라졌다(2026-08-21).
                  #    자리를 지키고 "왜 없는지"를 알려준다.
                  '<div class="iss90"><p class="iss90-h">📰 오늘, 시장에 무슨 일이 있었냐면요</p>'
                  '<p class="iss90-s">오늘 이슈 정리가 아직 준비되지 않았어요 — '
                  '아래 숫자와 표는 모두 오늘 것입니다</p></div>')

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
    # 🆕 2026-08-24 HO 지시 — 제목을 **말 거는 형태**로. 단정형보다 읽게 만든다.
    뒤집블록 = (f'<div class="q90-flip"><p class="qf-h">🔄 오늘을 뒤집어 볼까요?</p>'
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
    # ⚠️ 오늘만의 이상 신호가 있으면 그걸 우선한다. 없으면 코너 자체를 띄우지 않는다.
    #    매일 나오는 코너는 특별함이 없어 아무도 안 누른다(2026-08-21).
    이상 = _anomaly_signals(data)
    if 이상:
        이상HTML = ('<div class="q90-tease"><p class="qt-h">🚨 오늘 확인해야 할 신호</p>'
                   + "".join(f'<a class="qt" href="{h}"><span class="qt-tag">{t}</span>'
                             f'<span>{txt}</span><span class="qt-go">확인 ↓</span></a>'
                             for h, t, txt in 이상) + '</div>')
    else:
        이상HTML = ""
    티저HTML = "".join(
        f'<a class="qt" href="{h}"><span class="qt-tag">{t}</span><span>{txt}</span>'
        f'<span class="qt-go">확인 ↓</span></a>' for h, t, txt in 티저들[:3])

    # 🌅 내일장 — **숫자 기준선 하나**로 못 박는다(2026-08-21).
    #    "확인하세요"는 채점할 수 없다. 넘느냐 마느냐로 써야 다음날 자동 채점된다.
    내일선 = _tomorrow_line(data)

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
        # ⚠️ 숫자 기준선을 **맨 앞**에 둔다(2026-08-21). 이게 채점 가능한 유일한 문장이다.
        _본문 = (f'<p class="tmr-line">{내일선}</p>' if 내일선 else '') + \
               f'<p class="tmr-b">{pick}</p>'
        내일대응 = (f'<div class="tmr"><p class="tmr-h">🌅 {_NEXT_LABEL}장, 이것만 기억하세요</p>'
                   f'{_본문}</div>')

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
    # ⚠️ 사건명은 신호등 옆에 이미 들어간다(2026-08-19). 위에 또 두면 같은 문장이 두 번.
    사건명블록 = ""
    # 🆕 2026-08-22 HO 지시 — 「오늘 N가지만 기억하세요」 가림.
    #    되살리려면 HIDDEN_CHAPTERS에서 "딱N"만 빼면 된다.
    딱N블록 = hide("딱N", build_top_picks(해석))
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
    # ⚠️ '내 종목 구역'(격자)은 핵심편에서 뺐다(2026-08-19 HO 지시).
    #    심층편에서 자세히 다루므로, 90초 브리핑에서는 흐름을 끊는다.
    격자블록 = hide("핵심편격자",
                  build_account_grid(data.get("계좌격자"), data.get("주도섹터"))
                  + build_sector_scoreboard())
    변속기블록 = hide("수급변속기", build_flow_gearbox())

    # ── 🧭 「그래서 왜 이렇게 움직였냐면요」 코너 삭제 (2026-08-22 HO 지시) ──
    #  이제 각 이슈(반도체·수급·산업·글로벌…)의 '내용' 안에서 '왜'까지 끝낸다.
    #  별도 코너로 두면 같은 원인을 두 번 말하게 되고, 독자는 이슈를 읽고 나서
    #  아래에서 또 원인 설명을 만나 "아까 읽은 건가?" 하게 된다.
    #  ⚠️ 필드(왜그런가·수급왜) 자체는 지우지 않는다 — 심층편·이모지 회피 로직이
    #     참조하고 있고, 되살릴 때를 위해 남겨 둔다(§8 삭제 금지).
    움직인것들 = f'<div class="movers90">{이슈블록}</div>' if 이슈블록 else ""

    # 🆕 2026-08-22 HO 지시 — 「오늘은 '○○'인 날이에요」를 **신호등 바로 밑**으로.
    #    예전엔 성적표·계기판을 다 지나서야 나왔는데, 신호등(색)과 정의(말)는
    #    "오늘이 어떤 하루였나"를 각각 색과 문장으로 말하는 한 쌍이라 붙여야 한다.
    정의블록 = (f'<p class="q90-def">{핵심편.get("오늘의정의","")}</p>'
             + (f'<p class="q90-gloss">{핵심편.get("정의풀이")}</p>'
                if 핵심편.get("정의풀이") else ''))

    return (장전경고 + 사건명블록 + '<div class="q90"><div class="q90-top">'
            '<span class="q90-badge">⏱️ 3분 브리핑</span>'
            '<span class="q90-sub">핵심 요약편입니다</span></div>'
            + 신호등블록 + 정의블록 + 지수스트립
            # ⚠️ 공감문구는 '내 계좌만 왜 이러지' 코너로 흡수했다(2026-08-19).
            #    감정을 다루는 자리가 두 군데로 갈리면 둘 다 힘을 잃는다.
            # ⚠️ 배치 (2026-08-19 HO 지시)
            #    ① 3줄 요약은 가린다 — 아래 '딱 N가지'와 역할이 겹친다
            #    ② 📰 오늘 시장을 움직인 것들(팩트) → 🧭 왜 이렇게(해석) 순서로 붙인다
            #       팩트 바로 다음에 해석이 와야 "아, 이래서 내렸구나"가 각인된다
            #    ③ 😐 내 계좌만 왜 이러지(감정)는 그 뒤 — 이해한 다음에 공감이 온다
            # ⚠️ 배치 (2026-08-19 확정)
            #    📰 팩트 → 🧭 해석 → 📈 섹터 성적표 → 😐 감정 → 💰 수급
            #    "왜 그랬는지 이해한 다음에 위로가 온다"는 순서다.
            + hide("삼줄요약", f'<div class="q90-3">{삼줄}</div>')
            # 🆕 2026-08-22 — 📰팩트 + 🧭해석을 한 카드(움직인것들)로 합쳤다.
            + 움직인것들
            # 🆕 2026-08-26 HO 지시 — 감정 코너(😐 …올라타지 못했다면)를
            #    「오늘을 뒤집어 볼까요?」 **뒤로** 보낸다.
            #    [WHY] 사실 → 뒤집어 보기(관점) → 그제서야 감정. 위로가 먼저 오면
            #          아직 이해가 안 된 상태라 공감이 붕 뜬다.
            # ⚠️ 계기판을 헤더 막대 바로 밑으로 올렸으므로(2026-08-20)
            #    여기 제목·부제는 뺐다. 막대 → 계기판 흐름이 이미 설명이다.
            + '<div class="mny">'
            # ⚠️ 수급 코너는 **계기판 하나**로 압축했다(2026-08-19).
            #    타일(외국인/기관/개인 수치)은 맨 위 헤더 막대와 같은 말이고,
            #    노란 네모 1,2,3은 계기판 배지와 겹친다 → 둘 다 뺐다.
            + hide("수급타일", f'<div class="mny-tiles">{타일HTML}</div>')
            + 변속기블록
            # ⚠️ 왜블록(🧭 왜 이렇게)은 위쪽 해석블록으로 합쳤다(2026-08-19).
            #    여기서는 계기판 밑에 **수급 특징 한 줄**만 남긴다.
            + hide("수급특징", f'<div class="mny-feat">{특징}</div>')
            + '</div>'
            + 격자블록
            # 🆕 2026-08-22 HO 지시
            #  · 핵심디버전스(「지수는 오르는데 큰돈은 빠지는 중 — 심층편에서 자세히」) 삭제
            #    → 티저만 던지고 답을 심층편으로 미루니 핵심편에서 얻는 게 없었다.
            #  · 내일대응(「○요일장, 이것만 기억하세요」) 삭제
            #    → 아래 관전포인트(예보)와 역할이 겹친다. 예보가 더 구체적이라 그쪽만 남긴다.
            #  · 관전포인트를 핵심편 **맨 끝**으로. "오늘"을 다 읽고 "내일"로 닫는 순서.
            + 뒤집블록 + 내종목 + 딱N블록
            # 🆕 2026-08-22 HO 지시 — 「다음 거래일 예보」를 뒤집어보기 **바로 뒤로**.
            #    "오늘을 뒤집어 보면 → 그래서 내일은" 으로 이어지는 게 자연스럽고,
            #    맨 끝에 두면 레이더 카드들에 묻혀 잘 안 읽힌다.
            # 🆕 2026-08-25 HO 기획 — 「항로도」를 예보 **바로 앞**에.
            #    맥락(지금 어느 구간) → 판단(그래서 내일)의 순서를 만든다.
            #    예보만 있으면 "오늘 숫자로 내일 찍기"가 되고, 항로도가 앞에
            #    붙으면 "흐름 → 위치 → 판단"이 된다.
            + hide("항로도", build_route_map())
            # 🆕 2026-08-25 HO 지시 — 「다음 거래일 예보」를 핵심편에서 **뺀다.**
            #  ⚠️ 이유: 근거 없는 판단이 너무 많이 들어갔다. Claude에게 오늘
            #     숫자만 주고 내일을 말하라고 시킨 구조라 "3조 넘으면 이탈 지속"
            #     같은 상식 재진술이 나왔다. 핵심편 한가운데는 리포트의 얼굴인데
            #     **가장 확신 없는 코너**가 앉아 있었다.
            #  ⚠️ 삭제가 아니라 가림 — 심층편에는 그대로 있고, 채점표의 재료라
            #     예보 자체를 없애면 「어제 뭐라고 했나」가 같이 죽는다.
            + hide("핵심편예보", build_watchpoints(해석.get("관전포인트"), _NEXT_LABEL))
            # 🆕 2026-08-25 — 예보가 있던 자리를 「오늘 이상했던 것」이 대신한다.
            + build_odd_today()
            # 🆕 2026-08-26 HO 기획 — 「오늘 이상했던 것」 바로 뒤에 중간 요약.
            #    여기까지가 '시장 이야기'다. 머리를 한 번 정리하고
            #    아래 섹터·내 종목으로 넘어가게 한다.
            + build_midsummary(data, 해석)
            # 🆕 2026-08-22 HO 지시 — 「오늘 주도 섹터」(사다리)를 뒤집어보기 뒤로.
            #    ⚠️ 섹터 코너는 핵심편에 이것 하나뿐이다(칩은 2026-08-22에 제거).
            #       상위는 사다리 그림, 하위는 그 카드 안 한 줄로 흡수했다.
            + hide("핵심편섹터사다리", build_sector_ladder())
            # 🆕 2026-08-22 HO 지시 — 「오늘 확인해야 할 신호」 가림.
            + hide("확인해야할신호", 이상HTML)
            # 🆕 2026-08-22 HO 지시 — 레이더 두 코너를 나란히. **강세가 먼저, 매집이 뒤.**
            #    성격이 정반대라(강세=이미 터진 것 / 매집=아직 안 터진 것)
            #    붙여 놓으면 대비가 살아난다.
            + build_core_strong(data.get("강세레이더"))
            + build_core_accum(data.get("매집레이더"))
            # 🆕 2026-08-22 HO 지시 — 핵심편 맨 끝에 관심종목 등록·종목 브리핑을 추가.
            #    ⚠️ 예보(관전포인트)는 위 뒤집어보기 뒤로 옮겼다. 여기서 또 부르면
            #       같은 카드가 두 번 나온다(실제로 한 번 그렇게 됐다).
            #    ⚠️ 두 함수 다 **자체 카드 헤더를 이미 갖고 있어서** 별도 제목을
            #       안 붙였다. 심층편에서 쓰던 `sec-label`은 밝은 배경(#1a1a1a
            #       텍스트) 전용이라, 어두운 핵심편(q90)에 그대로 쓰면 글자가
            #       배경에 묻혀 안 보인다 — 실제로 넣었다가 잡은 실수다.
            #    ⚠️ 심층편에도 같은 코너가 그대로 남아 있다 — 지우지 않았다.
            #       핵심편만 보는 무료 독자·바쁜 유료 독자를 위한 자리이고,
            #       심층편까지 정독하는 독자에게는 다시 봐도 자연스러운 위치라
            #       중복 삭제 대상으로 보지 않는다.
            + build_my_stocks(data)
            + build_stock_brief()
            + '</div>'
            + ('<div class="deep-cut" id="deep">'
               '<span class="deep-arrow">⌄</span>'
               '<div class="deep-txt"><p class="deep-t1">여기까지가 핵심편입니다</p>'
               '<p class="deep-t2">지금부터는 근거와 상세를 담은 <b>심층편</b></p>'
               # 🆕 2026-08-26 — 이 경계가 나중에 무료·유료의 경계가 된다.
               #    ⚠️ HO 지시 — 지금은 «유료·멤버 전용» 같은 말을 쓰지 않는다.
               #       아직 아무것도 못 지키는 시점에 조건부터 말하면 신뢰를 먼저 쓴다.
               #       «곧 정식 공개» 예고만 남기고, 자물쇠로 변화만 암시한다.
               #    ⚠️ 날짜·가격은 쓰지 않는다. 못 지킬 약속을 화면에 박지 않는다.
               '<p class="deep-pre">🔒 <b>심층편은 곧 공개됩니다</b></p>'
               '</div>'
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
    금 = _flow_amt(비차익)      # ⚠️ %만 말하면 "그래서 얼마?"가 남는다
    산다 = 실탄 >= 0

    if band == "odd":
        return (f"비중이 <b>{pct}</b>로 나왔습니다. 오류가 아니라 "
                f"<b>한쪽은 지수를 통째로 사고 다른 쪽은 개별 종목을 반대로 판</b> 날입니다. "
                f"이런 날은 지수와 개별 종목의 방향이 크게 엇갈리기 쉬우니, "
                f"<b>지수만 보고 내 종목을 판단하면 어긋납니다.</b>")
    if 산다 and band == "low":
        return (f"실탄은 들어왔지만 바스켓은 <b>{금}</b>({pct})뿐입니다. "
                f"지수 상승을 <b>소수 종목이 만들었다</b>는 뜻이라, "
                f"대부분의 계좌는 지수만큼 못 올랐을 겁니다. "
                f"이런 날은 지수 방향보다 <b>어느 섹터에 있느냐</b>가 수익을 가릅니다.")
    if 산다 and band == "mid":
        return (f"바스켓 <b>{금}</b>(비중 {pct}) — 지수 전체와 개별 종목이 <b>절반씩 섞인</b> 매수입니다. "
                f"지수도 오르고 종목별 편차도 남는 구간이라, "
                f"<b>지수를 따라가되 섹터가 성과를 가른다</b>고 보면 됩니다.")
    if 산다 and band == "high":
        return (f"바스켓 매수가 <b>{금}</b>로 실탄의 <b>{pct}</b>입니다. 종목을 고른 게 아니라 "
                f"<b>한국 시장 자체를 담은</b> 날이라, 대형주·지수를 따라가는 자리가 유리합니다. "
                f"넓게 들어온 돈은 좁게 들어온 돈보다 <b>흐름이 오래 이어지는 편</b>이지만, "
                f"소형 테마는 상대적으로 소외될 수 있습니다.")
    if (not 산다) and band == "low":
        return (f"실탄은 빠졌지만 바스켓은 <b>{금}</b>({pct})뿐입니다. "
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
    개인 = f(코수.get("개인"))          # 🆕 2026-08-22 — 아래 ①에서 사실 확인용
    실탄오늘 = (외 + 기) if (외 is not None and 기 is not None) else None

    h = load_json("flow_history.json") or []
    h = [x for x in h if isinstance(x, dict) and x.get("실탄") is not None]
    h20 = h[-20:]
    실탄20 = sum(x.get("실탄") or 0 for x in h20) if h20 else None
    외20 = sum(x.get("외현") or 0 for x in h20) if h20 else None

    signals = []   # (등급, 아이콘, 제목, 설명)

    # ① 지수 상승 vs 20일 실탄 유출 (고점 경계)
    if 코등 is not None and 코등 > 0.3 and 실탄20 is not None and 실탄20 < 0 and len(h20) >= 8:
        # ⚠️ 2026-08-22 수정 — 예전에는 개인 수급을 **확인하지 않고**
        #    "개인이 밀어올린 상승"이라고 단정했다. 실제로 2026-08-21에는
        #    코스피 개인이 −1.17조 순매도인데도 이 문장이 그대로 나갔다.
        #    → 오늘 개인이 실제로 순매수일 때만 그렇게 쓴다. 아니면 사실만 말한다.
        if 개인 is not None and 개인 > 0:
            누가 = ("외국인·기관이 아니라 <b>개인이 밀어올린</b> 상승일 수 있어")
        elif 개인 is not None and 개인 < 0:
            누가 = (f"오늘은 개인마저 <b>{_flow_amt(개인)}</b> 팔았습니다. "
                   f"즉 <b>소수 종목에만 돈이 몰린</b> 상승이라")
        else:
            누가 = "무엇이 지수를 올렸는지 <b>수급으로는 확인되지 않아</b>"
        signals.append((
            "warn", "⚠️",
            "지수는 오르는데, 큰돈은 빠지는 중",
            f"코스피가 <b>{코등:+.1f}%</b> 올랐지만 최근 {len(h20)}일 실탄은 "
            f"<b>{_flow_amt(실탄20)}</b> 빠져나갔습니다. {누가}, "
            f"<b>지속력은 지켜봐야</b> 합니다."))

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
        # ⚠️ 이 가지는 코등>0.5 AND 닥등<0 일 때만 들어온다 —
        #    즉 "대형주만 웃고"라는 말이 데이터로 항상 참이다. (2026-08-22 점검 완료)
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
FS_IND = "#a78bfa"                            # 개인 (연보라)
#  ⚠️ 개인은 실탄(외국인+기관)의 **거울**이다. 현물시장이 제로섬이라
#     둘은 대체로 반대로 움직인다. 그래서 매수/매도 색(빨강·파랑)이나
#     외국인·기관 색과 겹치면 안 된다 → 따로 연보라를 쓴다.
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
    "핵심편예보",         # 🆕 2026-08-25 HO 지시 — 근거 없는 판단이 많아 뺐다
    # 🆕 2026-08-25 HO 지시 — 「항로도」는 **기록이 더 쌓인 뒤** 핵심편에 켠다.
    #  ⚠️ 지금 표본이 26거래일뿐이라 "기록상 2번째"밖에 못 말한다.
    #     이 코너의 값어치는 "올해 3번째" 같은 빈도에 있는데, 지금 켜면
    #     그 값어치를 보여주지 못한 채 첫인상만 소모한다.
    #  👉 켤 때: 이 줄만 지우면 된다. 코드는 이미 다 돌아가고 있다.
    #     대략 3~4개월(60~80거래일)쯤 쌓이면 대부분의 특징이 3회 표본을 넘긴다.
    "항로도",
    "심층편관심종목",     # 🆕 2026-08-24 HO 지시 — 핵심편에 같은 코너가 있어 중복
    "확인해야할신호",     # 🆕 2026-08-22 HO 지시 — 「오늘 확인해야 할 신호」
    "심층편성적표",       # 🆕 2026-08-22 — 핵심편 헤더가 같은 카드를 쓴다(중복)
    "심층편관전포인트",   # 🆕 2026-08-22 — 예보를 핵심편 맨 끝으로 옮겼다(중복)
    "그들은뭐라했나",     # 🆕 2026-08-22 HO 지시
    "딱N",                # 🆕 2026-08-22 HO 지시 — 「오늘 N가지만 기억하세요」
    "포착성적",           # 2026-08-21 — 표본이 쌓이면 되살릴 것
    "군중나침반",         # 2026-08-21 — 신용잔고를 수급 타임라인으로 옮김
    "섹터크기별",         # 🆕 2026-08-22 HO 지시 — 심층편에서 가림
    "삼줄요약",           # 2026-08-19 — '딱 N가지'와 역할 중복
    "수급타일",           # 2026-08-19 — 헤더 수급 막대와 같은 말
    "수급특징",           # 2026-08-19 — 계기판 배지와 겹침
    "핵심편격자",         # 2026-08-19 — 내 종목 구역·섹터 성적표는 심층편에서 다룬다
    "핵심편섹터",         # 🆕 2026-08-22 — 심층편과 **글자 하나까지 똑같은** 카드가
                        #    두 번 렌더돼 원칙 5("같은 그림을 두 번 보여주지 않는다")를
                        #    어기고 있었다. 체크박스 id도 겹쳐 선 그래프 연동이 흔들린다.
                        #    핵심편에는 아래 build_sector_brief()로 한 줄만 남긴다.
    "수급변속기",         # 2026-08-19 — 계기판과 역할이 겹친다
    "새테마",               # 2026-08-19 — 어차피 '오늘의 주인공'에 같은 테마가 나온다
    "지수와수급나란히",     # 2026-08-18 — 통합 타임라인과 역할이 겹침
    "어제대비움직임",       # 2026-08-18 — 레이더 그림과 같은 내용을 표로 반복
    "과거엔어땠나",         # 2026-08-18 — 차별점이 없어 보류 (표본 쌓이면 되살릴 것)
    # 🔴 2026-08-29 HO 지시 — 심층편 시황 정리.
    #    핵심편 「오늘, 시장에 무슨 일이 있었냐면요」 + 심층편 「이슈 해부」와
    #    **같은 질문에 세 번 답하는** 구조였다. 과거(무슨 일이 있었나)는
    #    핵심편이 전담하고, 심층편은 현재(이슈 해부)·미래(프로의 판단)를
    #    맡는 것으로 시제를 나눴다.
    "오늘의시장",
    # 🔴 2026-08-29 (2차) HO 지시 — 「섹터 지도」(build_account_grid, 📊)를
    #    가린다. 섹터 성적표(build_sector_scoreboard, 📈)와 같은 15칸 데이터를
    #    표/그림으로 두 번 보여주는 중복이었다 — 섹터 성적표만 남긴다.
    #    ⚠️ 핵심편에도 같은 함수가 있는데 그건 이미 "핵심편격자"로 가려진
    #    상태였다(2026-08-19). 이번 건 심층편 쪽 호출만 새로 가리는 것이다.
    #    나중에 이 자리에 테마 순환 챕터를 넣을 계획 — 되살릴 땐 이 줄만
    #    지우면 된다.
    "섹터지도",
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


FLOW_창 = 20          # 🆕 2026-08-22 — 순위를 세는 창. generate_report와 반드시 같아야 한다.


def _배수말(배수):
    """평소 대비 크기를 사람이 읽는 말로 바꾼다.

    ⚠️ 2026-08-21 실제 사고: 실탄 721억 / 평소 25,975억 = 0.0277배를
       "{:.1f}배"로 찍어 화면에 **"0.0배"**가 나왔다. 같은 화면 본문은
       "3% 수준"이라고 써서 독자 눈에는 계산 오류로 보였다.
       → 0.1배 미만은 배수 대신 **퍼센트**로 말한다.
    """
    if not 배수:
        return "—"
    if 배수 < 0.1:
        return f"{배수 * 100:.0f}%"
    return f"{배수:.1f}" + "배"


def _fs_stat(arr, 평소일수=20):
    """주체 하나의 오늘 성적 — 방향별 순위·상위%·N일 만의 최대·연속일수·평소 배수.

    ⚠️ 매도인 날에 '매수 기준 15위'라고 쓰면 정반대로 읽힌다.
       매수면 큰 순, 매도면 작은 순으로 세어 **그 방향에서 몇 번째인가**를 말한다.
    """
    전체 = [v for v in arr if v is not None]
    if not 전체:
        return None
    # ⚠️ 2026-08-22 — 순위를 세는 창을 "오늘 포함 최근 20거래일"로 못 박는다.
    #    예전에는 넘어온 배열 전체(21일)로 셌는데 generate_report는 20일로 세서,
    #    같은 날 실탄이 화면엔 "매수 11위/21일", Claude 글엔 "20일 중 13위"로 갈렸다.
    arr = 전체[-FLOW_창:]
    n = len(arr)
    v = arr[-1]
    rk = (sorted(arr, reverse=True) if v >= 0 else sorted(arr)).index(v) + 1
    back = 1
    for j in range(2, n + 1):
        ok = (v == max(arr[-j:])) if v >= 0 else (v == min(arr[-j:]))
        if ok:
            back = j
        else:
            break
    # 평소(=비교 기준)는 오늘을 뺀 직전 20거래일. generate_report의 평균()과 같은 규칙.
    기준 = 전체[-(평소일수 + 1):-1] if len(전체) >= 6 else 전체[:-1]
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
    """실탄 계기 — DIAL 01 '기본 정돈형' (2026-08-18 확정).

    바늘이 가리키는 건 금액이 아니라 **평소 대비 배수**다.
    금액을 바늘로 그리면 "3조가 얼마나 큰지"를 여전히 모른다.

    설계 포인트
      · 눈금 라벨(2배·1배·평소)을 **호 바깥**에 둔다 → 바늘이 글자를 안 가린다.
      · 매수 쪽은 옅은 빨강, 매도 쪽은 옅은 파랑으로 미리 갈라둔다.
      · ⚠️ **매도인 날은 바늘도 파랑**이다. 바늘 색이 곧 방향이라
        각도를 보기 전에 색만으로 매수/매도가 잡힌다.
    """
    import math as _m
    배수, 양 = st["배수"], st["v"] >= 0
    deg = max(-86, min(86, 배수 / 2 * 90)) * (1 if 양 else -1)   # ±2배 = ±90°
    c = FS_BUY if 양 else FS_SELL
    cx = cy = 66
    r = 50

    def _p(d, rr):
        a = _m.radians(d - 90)
        return cx + rr * _m.cos(a), cy + rr * _m.sin(a)

    def _arc(rr, d0, d1, w, col, op=1.0):
        x0, y0 = _p(d0, rr); x1, y1 = _p(d1, rr)
        return (f'<path d="M{x0:.1f} {y0:.1f} A{rr} {rr} 0 0 1 {x1:.1f} {y1:.1f}" '
                f'fill="none" stroke="{col}" stroke-width="{w}" stroke-opacity="{op}"/>')

    g = [_arc(r, -90, 90, 13, "#161c26"),
         _arc(r, 0, 90, 13, FS_BUY, .22),
         _arc(r, -90, 0, 13, FS_SELL, .22)]
    for d, lab in ((-90, "2배"), (-45, "1배"), (0, "평소"), (45, "1배"), (90, "2배")):
        a, b = _p(d, r - 8), _p(d, r + 8)
        g.append(f'<line x1="{a[0]:.1f}" y1="{a[1]:.1f}" x2="{b[0]:.1f}" y2="{b[1]:.1f}" '
                 f'stroke="#0b0e13" stroke-width="{2.4 if d == 0 else 1.6}"/>')
        t = _p(d, r + 15)
        anc = "middle" if abs(d) < 90 else ("start" if d < 0 else "end")
        dx = 0 if abs(d) < 90 else (2 if d < 0 else -2)
        g.append(f'<text x="{t[0]+dx:.1f}" y="{t[1]+3:.1f}" font-size="7.5" fill="#6f7784" '
                 f'font-weight="700" text-anchor="{anc}">{lab}</text>')
    g.append(f'<g transform="rotate({deg:.1f} {cx} {cy})">'
             f'<path d="M{cx-3.4} {cy} L{cx} {cy-r+6} L{cx+3.4} {cy} Z" fill="{c}"/></g>')
    g.append(f'<circle cx="{cx}" cy="{cy}" r="5" fill="#0f131a" stroke="{c}" stroke-width="2.4"/>')
    g.append(f'<text x="{cx}" y="{cy+22}" font-size="15" fill="{c}" font-weight="900" '
             f'text-anchor="middle">{_배수말(배수)}</text>')
    g.append(f'<text x="{cx}" y="{cy+33}" font-size="7.5" fill="#7d848f" font-weight="700" '
             f'text-anchor="middle">평소 대비</text>')
    return f'<svg class="fs-g" viewBox="-6 -4 144 108" style="width:{W}px">{"".join(g)}</svg>'

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
        return "⚡", f'평소의 {_배수말(st["배수"])}'
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
          {st["dir"]} <b>{st["rk"]}위</b>/{st["n"]}일 · 평소 하루치의 <b>{_배수말(st["배수"])}</b></p>
      </div>'''


def _market_rows():
    """market_history.json의 일별 배열. 개인 수급이 여기 있다."""
    try:
        m = load_json("market_history.json")
    except Exception:
        return []
    if isinstance(m, dict):
        return m.get("일별") or []
    return m if isinstance(m, list) else []


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
    # 개인은 flow_history에 없고 market_history에 있다 → 날짜로 맞춰 붙인다
    개 = []
    try:
        # ⚠️ market_history는 '2026-08-20', flow_history는 '20260820' 형식이다.
        #    그대로 맞추면 교집합이 0이 되어 개인 선이 통째로 안 그려진다(2026-08-21).
        _mh = {str(r.get("날짜", "")).replace("-", ""): r
               for r in (_market_rows() or [])}
        for x in sl:
            _v = (_mh.get(x.get("날짜")) or {}).get("개인_코스피")
            개.append(_v if isinstance(_v, (int, float)) else None)
    except Exception:
        개 = [None] * q

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
    H = 372   # 신용잔고 레인(+72) 포함 — 2026-08-21
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
    # 개인 누적 — 값이 없는 날은 0으로 두지 않고 직전 값을 유지한다(선이 튀지 않게)
    C개, _acc, _has = [], 0, False
    for v in 개:
        if isinstance(v, (int, float)):
            _acc += v; _has = True
        C개.append(_acc)
    # ⚠️ 개인 선은 뺐다(2026-08-21 지시). 실탄(외국인+기관)의 거울이라
    #    선이 하나 더 늘 뿐 새 정보가 없었다. 대신 아래 칸에 **신용잔고**를 넣는다.
    _has = False
    if _has:
        _ity = _lbl_y(YA(C개[-1]) + 3)
        g.append(f'<text x="{W-PR+4}" y="{_ity:.1f}" font-size="8.5" fill="{FS_IND}" '
                 f'font-weight="800">개인</text>')

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
            # ⚠️ %만 있으면 "그래서 얼마?"가 안 보인다. 금액을 같이 적는다(2026-08-18).
            ty = min(max(YC(rs[-1]) - 9, CT + 24), CB - 15)   # 아래 줄(+12) 자리 확보
            _bc = FS_BUY if (비[-1] or 0) >= 0 else FS_SELL
            g.append(f'<text x="{X(q-1)-5:.1f}" y="{ty:.1f}" font-size="9" fill="{_bc}" '
                     f'font-weight="900" text-anchor="end">{rs[-1]:.0f}%</text>')
            # 🆕 2026-08-26 — 위 %는 font-size 9인데 간격이 9px뿐이라 두 줄이 붙었다.
            #    («103%» 와 «−2.73조»가 겹쳐 보이던 원인) 12px로 벌린다.
            g.append(f'<text x="{X(q-1)-5:.1f}" y="{ty+12:.1f}" font-size="7.5" fill="{_bc}" '
                     f'font-weight="800" text-anchor="end" opacity=".9">{_flow_amt(비[-1])}</text>')
    else:
        g.append(f'<text x="{W/2:.1f}" y="{(CT+CB)/2+4:.1f}" font-size="8" fill="#4a5462" '
                 f'text-anchor="middle" font-weight="700">이 구간에는 비차익 데이터가 없습니다</text>')
    g.append(f'<rect x="{W-PR-136}" y="{CT+1}" width="132" height="12" rx="3" fill="#0a0e14" opacity=".92"/>')
    g.append(f'<text x="{W-PR-133}" y="{CT+10:.1f}" font-size="7.5" fill="#8b93a0" font-weight="800">🧺 비차익 — 비중(%) · 금액</text>')

    # ── 레인 D · 💳 신용융자 잔고 ─────────────────────────
    #  왜 보나: 빚내서 산 돈이 쌓일수록 **반대매매 위험**이 커진다.
    #    지수가 빠질 때 빚으로 산 물량이 강제로 나오면서 낙폭이 증폭된다.
    #    개인의 조바심을 보여주는 유일한 지표라, 개인 순매수 선보다 정보가 많다.
    #  ⚠️ 수집원이 아직 불안정하다. 값이 없으면 **레인 자리에 그 사실을 적는다.**
    #     조용히 빼면 "왜 없지"를 알 수가 없다.
    DT, DB = 296, 356
    g.append(f'<line x1="{PL}" y1="{DT-8}" x2="{W-PR}" y2="{DT-8}" '
             f'stroke="#fff" stroke-opacity=".07"/>')
    _신 = []
    try:
        for _ymd, _d in archive_days(q):
            _v = (_d.get("신용잔고") or {}).get("잔고")
            _신.append(_v if isinstance(_v, (int, float)) else None)
    except Exception:
        _신 = []
    _실값 = [v for v in _신 if v is not None]
    if len(_실값) >= 3:
        _hi, _lo = max(_실값), min(_실값)
        _sp = (_hi - _lo) or 1
        _Y = lambda v: DB - (DB - DT - 12) * (v - _lo) / _sp
        _pts, _prev = [], None
        for k, v in enumerate(_신):
            if v is None:
                continue
            _pts.append(f"{X(k):.1f},{_Y(v):.1f}")
        g.append(f'<polyline points="{" ".join(_pts)}" fill="none" stroke="{FS_IND}" '
                 f'stroke-width="2" stroke-linejoin="round"/>')
        _last = [v for v in _신 if v is not None][-1]
        g.append(f'<circle cx="{X(q-1):.1f}" cy="{_Y(_last):.1f}" r="3" fill="{FS_IND}"/>')
        _증 = (_실값[-1] - _실값[-2]) if len(_실값) >= 2 else 0
        _c = FS_BUY if _증 >= 0 else FS_SELL
        g.append(f'<text x="{W-PR+4}" y="{_Y(_last)+3:.1f}" font-size="8.5" '
                 f'fill="{FS_IND}" font-weight="800">신용</text>')
        # 🆕 2026-08-26 HO 지적(2차) — 금액과 코너 제목이 겹쳤다.
        #  [원인] 둘 다 y=DT+10 **같은 높이**였다. 제목은 왼쪽, 금액은 오른쪽
        #     정렬이라 평소엔 안 부딪히다가, 금액이 «+100.75조 (-46,087억)»처럼
        #     길어지는 날 왼쪽으로 밀려와 제목 위에 올라탔다.
        #  [고침] 금액을 **한 줄 아래로** 내린다(DT+21). 제목과 높이를 다르게 두면
        #     금액이 아무리 길어져도 겹칠 수가 없다.
        g.append(f'<text x="{W-PR-4}" y="{DT+21:.1f}" font-size="8" fill="{_c}" '
                 f'font-weight="800" text-anchor="end">{_flow_amt(_실값[-1])} '
                 f'({_증:+,.0f}억)</text>')
    else:
        g.append(f'<text x="{(PL+W-PR)/2:.0f}" y="{(DT+DB)/2:.0f}" font-size="8.5" '
                 f'fill="#6f7784" text-anchor="middle">신용융자 잔고는 아직 수집 전입니다 '
                 f'— 없는 숫자를 지어내지 않습니다</text>')
    g.append(f'<text x="{W-PR-133}" y="{DT+10:.1f}" font-size="7.5" fill="#8b93a0" '
             f'font-weight="800">💳 신용융자 잔고 — 빚내서 산 돈</text>')

    # ── 공통 날짜축 ──
    step = max(1, q // 4)
    for k in range(0, q, step):
        g.insert(0, f'<line x1="{X(k):.1f}" y1="{AT}" x2="{X(k):.1f}" y2="{CB}" stroke="#1a2029" stroke-width="1"/>')
        g.append(f'<text x="{X(k):.1f}" y="{H-6}" font-size="7" fill="#5b6472" '
                 f'text-anchor="middle" font-weight="700">{날[k]}</text>')
    g.append(f'<text x="{X(q-1):.1f}" y="{H-6}" font-size="7" fill="#c9d0d9" '
             f'text-anchor="middle" font-weight="800">{날[-1]}</text>')
    return f'<svg viewBox="0 0 {W} {H}">{"".join(g)}</svg>'


def _flow_comment():
    """계기판 밑 한 줄 코멘트 — 오늘 수급의 특징을 짧게 짚는다.

    ⚠️ 긴 설명은 위쪽 '🧭 왜 이렇게 움직였을까요'가 맡는다.
       여기는 **계기판 숫자를 말로 풀어주는 한두 줄**이면 충분하다.
    """
    try:
        h = load_json("flow_history.json") or []
        h = [r for r in h if isinstance(r, dict) and r.get("실탄") is not None]
    except Exception:
        return ""
    st = _fs_stat([r["실탄"] for r in h])
    if not st:
        return ""
    외 = _fs_stat([r["외현"] for r in h if r.get("외현") is not None])
    기 = _fs_stat([r["기관"] for r in h if r.get("기관") is not None])
    c = FS_BUY if st["v"] >= 0 else FS_SELL
    # 🆕 2026-08-22 HO 지시 — 핵심편이므로 '~습니다'체를 **'~요'체**로 바꾸고
    #    "그래서 어떤 하루였나"까지 한 마디 붙인다. 숫자만 읽어주면 계기판과 같은 말이다.
    조각 = []
    if 외 and 기 and (외["v"] >= 0) != (기["v"] >= 0):
        큰 = "외국인" if abs(외["v"]) >= abs(기["v"]) else "기관"
        작 = "기관" if 큰 == "외국인" else "외국인"
        방향 = "사들이는" if (외["v"] if 큰 == "외국인" else 기["v"]) >= 0 else "파는"
        조각.append(f'오늘은 <b>{큰}</b>이 {방향} 쪽이었고 <b>{작}</b>은 정반대였어요. '
                    f'둘이 밀고 당긴 끝에 실탄은 '
                    f'<b style="color:{c}">{_flow_amt(st["v"])}</b>로 남았고요.')
    elif st["v"] >= 0:
        조각.append(f'외국인·기관이 <b>둘 다 사는 쪽</b>이었어요. '
                    f'그래서 실탄이 <b style="color:{c}">{_flow_amt(st["v"])}</b>만큼 쌓였죠.')
    else:
        조각.append(f'외국인·기관이 <b>둘 다 파는 쪽</b>이었어요. '
                    f'실탄이 <b style="color:{c}">{_flow_amt(st["v"])}</b>로 빠져나갔고요.')

    if st["배수"] >= 1.5:
        조각.append(f'규모가 평소의 <b>{_배수말(st["배수"])}</b>예요. '
                    f'이 정도면 <b>확실히 유별난 하루</b>죠.')
    elif st["배수"] < 0.6:
        조각.append(f'다만 규모가 평소의 <b>{_배수말(st["배수"])}</b>밖에 안 돼요. '
                    f'방향은 정해졌는데 <b>힘이 실리진 않은</b> 하루예요.')
    else:
        조각.append(f'규모는 평소의 <b>{_배수말(st["배수"])}</b> 정도라 평범한 편이에요.')

    # 🆕 2026-08-22 HO 지시 — "그래서 이게 무슨 뜻이냐"를 한 마디 덧붙인다.
    #    숫자만 읽어주면 계기판을 말로 옮긴 것에 지나지 않는다.
    #    ⚠️ 개인 수급을 쓰려 했으나 flow_history.json에는 '개인' 필드가 **없다**
    #       (외현·기관·외선·비차익·실탄만 있다). 없는 값을 추정해 쓰면
    #       "개인이 밀어올렸다" 류의 오발화가 또 나온다 → 연속일수만 쓴다.
    연속 = _fs_streak([r["실탄"] for r in h]) if len(h) >= 3 else 0
    if 연속 >= 3:
        조각.append(f'<b>{연속}일째 같은 방향</b>이라 흐름이 굳어지는 중이에요.')
    elif 연속 == 2:
        조각.append(f'어제에 이어 <b>이틀째 같은 방향</b>이에요 — '
                    f'하루 더 이어지면 흐름으로 볼 만해요.')
    elif 연속 == 1 and len(h) >= 2:
        조각.append(f'어제와 <b>방향이 바뀐</b> 날이에요 — 하루짜리인지 '
                    f'시작인지는 내일 봐야 알겠죠.')
    return f'<p class="mny-cmt">{" ".join(조각)}</p>'


def _fs_streak(vals):
    """실탄이 같은 방향으로 며칠째인지. (0이면 오늘 방향이 바뀐 것)"""
    if not vals:
        return 0
    양수 = vals[-1] >= 0
    n = 0
    for v in reversed(vals):
        if (v >= 0) == 양수:
            n += 1
        else:
            break
    return n


def _flow_spark3():
    """실탄 3일 추이 미니 그래프 — 계기판 오른쪽 빈 공간에.

    ⚠️ 계기판은 '오늘 하루'만 말한다. 어제·그제와 비교가 없으면
       "0.7배"가 늘 그런 건지 오늘만 그런 건지 알 수 없다.
       막대 3개면 충분하다 — 크게 그리면 계기판과 주인공을 다툰다.
    """
    try:
        h = load_json("flow_history.json") or []
        # 🆕 2026-08-24 HO 지시 — 3일 → **5일**.
        #  ⚠️ 3일은 "어제·그제"라 방향이 안 보인다. 5일이면 한 주가 되어
        #     "이번 주 내내 빠졌다 / 중간에 꺾였다"가 그림으로 읽힌다.
        h = [r for r in h if isinstance(r, dict) and r.get("실탄") is not None][-5:]
    except Exception:
        return ""
    if len(h) < 2:
        return ""
    vals = [r["실탄"] for r in h]
    날 = [f'{r["날짜"][4:6]}/{r["날짜"][6:]}' for r in h]
    # 막대가 3 → 5개로 늘어 폭을 다시 잡는다(넓히지 않고 막대를 좁힌다 —
    # 계기판 옆 자리가 정해져 있어 넓히면 계기판이 밀린다).
    # 🆕 2026-08-24 HO 지적 — 마지막 날짜 글자와 막대가 겹쳤다.
    #  ⚠️ 원인: 높이 54 안에서 0선(z)이 30, 막대가 최대 22px 아래로 자라
    #     52까지 내려오는데 날짜를 51(H-3)에 찍었다. 정확히 겹친다.
    #  [고침] 캔버스를 62로 키우고, 아래로 자라는 폭을 16으로 줄이고,
    #         날짜는 그보다 더 아래(59)에 둔다. 0선도 26으로 올린다.
    W, H = 92, 62
    mx = max(abs(v) for v in vals) or 1
    z = 26
    n = len(vals)
    간격 = (W - 12) / max(1, n)
    bw = max(6, 간격 - 4)
    g = [f'<line x1="4" y1="{z}" x2="{W-4}" y2="{z}" stroke="#fff" stroke-opacity=".16"/>']
    for i, v in enumerate(vals):
        x = 6 + i * 간격
        y = z - (v / mx) * (20 if v >= 0 else 16)
        c = FS_BUY if v >= 0 else FS_SELL
        g.append(f'<rect x="{x:.0f}" y="{min(z,y):.1f}" width="{bw}" '
                 f'height="{max(2,abs(y-z)):.1f}" rx="2.5" fill="{c}" '
                 f'opacity="{1 if i==len(vals)-1 else .48}"/>')
        # ⚠️ 세 날짜를 다 적으면 6.5px로 뭉갠다. **오늘만** 적고 나머지는 비운다.
        if i == len(vals) - 1:
            g.append(f'<text x="{x+bw/2:.0f}" y="{H-2}" font-size="7.5" fill="#c9d0d9" '
                     f'text-anchor="middle" font-weight="800">{날[i]}</text>')
    return (f'<div class="fg-spark"><p class="fg-spark-t">최근 {len(vals)}일 실탄</p>'
            f'<svg viewBox="0 0 {W} {H}">{"".join(g)}</svg></div>')


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
            # 🆕 2026-08-22 HO 지시 — 계기판만 덩그러니 있으면 "이게 뭘 재는 건지"를
            #    모른다. 게이지 위에 무엇을 재는 계기인지 이름을 붙인다.
            f'<div class="core-g-l"><p class="core-g-cap">코스피 실탄</p>'
            f'{_fs_gauge(st, 104)}</div>'
            f'<div class="core-g-r">'
            f'<p class="core-g-v" style="color:{c}">{_flow_amt(st["v"])}</p>'
            f'<p class="core-g-s">실탄 · {st["dir"]} <b>{st["rk"]}위</b>/{st["n"]}일</p>'
            f'<p class="core-g-k" style="border-color:{c}55;color:{c}">{ico} {key}</p>'
            f'</div>{_flow_spark3()}</div>'
            # 🆕 2026-08-24 HO 지시 — '실탄' 설명을 **접기(details) 폐지 → 한 줄 상시 노출**로.
            #    ⚠️ 접어두면 초보는 끝까지 안 눌러본다. 실탄은 리포트 전체에서 계속 쓰는
            #       핵심 용어라, 매일 눈에 한 번은 스쳐야 학습이 된다.
            #    ⚠️ 한 줄을 넘기지 않는 것이 이 문구의 조건이다(넘으면 다시 '설명 블록'이 된다).
            #       그래서 '선물·비차익은 단위가 달라 제외' 같은 부연은 의도적으로 버렸다.
            f'<p style="margin:9px 0 0;font-size:11px;color:#7d848f;'
            f'line-height:1.5;letter-spacing:-.2px">'
            f'💡 <b style="color:#9aa0aa">실탄</b> = 외국인 + 기관 순매수 합 '
            f'<span style="color:#6f7784">(개인 제외)</span></p>')



def build_atc_talk(해석):
    """📡 관제교신 — 타임라인 아래 해석 (2026-08-21 확정 문체).

    ③ 관제탑 교신체 + ④ 질문-답변체 조합.
    ⚠️ 이 리포트에서 가장 어려운 영역이라 **쉽고 재미있게** 푸는 것이 목적이다.
       딱딱한 증권사 문체를 쓰지 않기로 했다.
    ⚠️ Claude가 쓰는 글이라 '재사용' 모드에서는 안 나온다(graceful — 빈 문자열).
    """
    t = (해석 or {}).get("관제교신") or {}
    항적 = (t.get("항적보고") or "").strip()
    주목 = (t.get("주목지점") or "").strip()
    믿음 = (t.get("믿어도되나") or "").strip()
    내일 = (t.get("내일볼것") or "").strip()
    if not (항적 or 주목):
        return ""
    블록 = ""
    if 항적:
        블록 += f'<p class="atc-p atc-lead">{항적}</p>'
    if 주목:
        블록 += f'<p class="atc-p">{주목}</p>'
    if 믿음:
        # ⚠️ Claude가 <br>을 빼먹으면 세 항목이 한 줄로 붙어 못 읽는다(2026-08-21).
        #    코드에서 **강제로 줄을 나눈다.** 글쓴이에게 맡기지 않는다.
        _t = 믿음.replace("<br><br>", "\n").replace("<br>", "\n")
        for _k in ("믿어도 되는 것", "의심스러운 것", "아직 모르는 것"):
            _t = re.sub(r"\s*(?:<b>)?\s*\*{0,2}" + _k + r"\*{0,2}\s*(?:</b>)?\s*",
                        "\n<b>" + _k + "</b> ", _t)
        _줄 = [x.strip() for x in _t.split("\n") if x.strip()]
        블록 += ('<div class="atc-ask">'
                + "".join(f'<p class="atc-q">{x}</p>' for x in _줄) + '</div>')
    if 내일:
        블록 += f'<p class="atc-next">{내일}</p>'
    return f'<div class="atc">{블록}</div>'


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
        <span><i style="background:{FS_IND}"></i>신용융자 잔고 — 빚내서 산 돈</span>
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


def build_flow_signal(파생, 지수수급, 해석=None):
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
    배수문 = f" · 평소의 {_배수말(배수)}" if (배수 and N >= 6) else ""
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
            크기말 = f"최근 {len(기준들)}거래일 하루 평균({평소실탄:,.0f}억)의 <b>{_배수말(배수)}</b> — 눈에 띄게 큰 하루입니다."
        elif 배수 >= FLOW_강한배수:
            크기말 = f"최근 {len(기준들)}거래일 하루 평균({평소실탄:,.0f}억)의 <b>{_배수말(배수)}</b>로 평소보다 큽니다."
        elif 배수 >= 0.6:
            크기말 = f"규모는 최근 {len(기준들)}거래일 하루 평균({평소실탄:,.0f}억)과 <b>비슷한 수준</b>({_배수말(배수)})입니다."
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
      <div class="fs-v5-g">{계기HTML}</div>
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
    {build_atc_talk(해석)}
    <div class="fs-read">
      <p class="fs-read-t">🧺 오늘의 프로그램 비차익 판독</p>
      <p class="fs-read-b">{바스켓읽기}</p>
    </div>
    <div class="fs-read stat">
      <p class="fs-read-t">📊 비중 구간별 사후 통계 <span>(5거래일 뒤)</span></p>
      <p class="fs-read-b dim">{바스켓통계}</p>
    </div>
    {f'<p class="fs-combo"><b>{조합[1]}</b> — {조합[2]}</p>' if 조합 else ''}
    {f'<p class="fs-warn">{만기배지} — {만기설명}</p>' if 만기배지 else ''}
    {나란히블록}{hidden_note()}
    {hide("과거엔어땠나", flow_pattern_analysis())}
    {읽는법블록}
  </div>'''



# ── 🌏 바깥 날씨 — 지표별 5일 추이 선 ──────────────────
#  ⚠️ 숫자와 등락률만 있으면 "높은 건가 낮은 건가"를 모른다.
#     5일 선 하나면 **오르던 중인지 내리던 중인지**가 바로 보인다.
#     카드 오른쪽 빈 공간에 작게 넣는다(주인공은 여전히 숫자다).
# ── 🌏 바깥 날씨 — 지표별 5일 추이 선 ──────────────────
#  ⚠️ 숫자와 등락률만 있으면 "높은 건가 낮은 건가"를 모른다.
#     5일 선 하나면 **오르던 중인지 내리던 중인지**가 바로 보인다.
#  ⚠️ 색은 리포트 어디에도 안 쓰는 색으로 골랐다(2026-08-21).
#     빨강·파랑(매수/매도), 자홍·민트(외국인/기관), 금색(선물)과 겹치면 뜻이 두 개가 된다.
MACRO_LINE = {
    # 🆕 2026-08-22 — 파스텔이 화면에서 너무 흐리다는 지적으로 진한 톤으로 교체.
    #    기존 지수(#c1432b·#2e6bd6)·개인(#a78bfa)·관심종목(#f0c65a)과 안 겹치는
    #    범위에서 골랐다.
    "원달러환율": ("#0ea5e9", "환율"),   # 진한 하늘 — 통화
    "WTI유가":    ("#ea580c", "유가"),   # 진한 주황 — 원유
    "미국채10년": ("#7c3aed", "금리"),   # 진한 보라 — 채권
    "국제금":     ("#ca8a04", "금"),     # 진한 금 — 금
}


def _macro_hist(key, days=5):
    """archive에서 해당 지표의 최근 days거래일 (날짜, 값)."""
    out = []
    for _ymd, d in archive_days(days):
        try:
            it = (d.get("매크로") or {}).get(key)
            v = (it or {}).get("값") if isinstance(it, dict) else None
            if isinstance(v, (int, float)):
                out.append((str(_ymd), float(v)))
        except Exception:
            continue
    return out


def _macro_spark(key, 표시명):
    """5일 추이 선 — 날짜축·기준선·끝값까지 제대로 그린다.

    ⚠️ 처음엔 점 몇 개만 잇고 끝냈는데, 그러면 **뭘 보라는 건지 모르는 그림**이 된다.
       · 첫날 대비 오르내림을 **면(area)** 으로 채워 방향을 한눈에
       · 첫날 값을 **점선 기준선**으로 깔아 "지금 위인지 아래인지"를 보이게
       · 날짜(첫날·마지막날)와 **5일 변화율**을 함께 적는다
    """
    hs = _macro_hist(key)
    if len(hs) < 3:
        return ""
    col, _nm = MACRO_LINE.get(key, ("#8b93a0", 표시명))
    vs = [v for _, v in hs]
    ds = [d for d, _ in hs]
    W, H = 158, 58
    L, R, T, B = 2, 2, 12, 15
    hi, lo = max(vs), min(vs)
    rng = (hi - lo) or (abs(hi) * 0.001 or 1)
    X = lambda i: L + (W - L - R) * i / (len(vs) - 1)
    Y = lambda v: T + (H - T - B) * (1 - (v - lo) / rng)
    기준 = vs[0]
    변화 = (vs[-1] - 기준) / 기준 * 100 if 기준 else 0
    pts = " ".join(f"{X(i):.1f},{Y(v):.1f}" for i, v in enumerate(vs))
    면 = f"{X(0):.1f},{Y(기준):.1f} " + pts + f" {X(len(vs)-1):.1f},{Y(기준):.1f}"
    g = [f'<polygon points="{면}" fill="{col}" opacity=".14"/>',
         f'<line x1="{L}" y1="{Y(기준):.1f}" x2="{W-R}" y2="{Y(기준):.1f}" '
         f'stroke="{col}" stroke-width="1" stroke-dasharray="3 3" opacity=".45"/>',
         f'<polyline points="{pts}" fill="none" stroke="{col}" stroke-width="2" '
         f'stroke-linejoin="round" stroke-linecap="round"/>',
         f'<circle cx="{X(len(vs)-1):.1f}" cy="{Y(vs[-1]):.1f}" r="3" fill="{col}"/>',
         f'<text x="{L}" y="{H-4}" font-size="7.5" fill="#6f7784" font-weight="700">'
         f'{ds[0][4:6]}/{ds[0][6:]}</text>',
         f'<text x="{W-R}" y="{H-4}" font-size="7.5" fill="#9aa0aa" font-weight="800" '
         f'text-anchor="end">{ds[-1][4:6]}/{ds[-1][6:]}</text>',
         f'<text x="{W-R}" y="8.5" font-size="8" fill="{col}" font-weight="800" '
         f'text-anchor="end">{len(vs)}일 {변화:+.1f}%</text>']
    return f'<svg class="mr-spark" viewBox="0 0 {W} {H}">{"".join(g)}</svg>'

def build_macro_card(item, 해설="", _key=None):
    if not item:
        return '<div class="mr-card"><p class="mr-label">—</p><p class="mr-val">— (준비중)</p></div>'
    cls = "dn" if item["등락률"] < 0 else "up"
    단위 = item.get("단위", "")
    값표시 = f"{단위}{item['값']:,.2f}" if 단위 == "$" else f"{item['값']:,.2f}{단위}"
    해설HTML = f'<p class="mr-comment">{해설}</p>' if 해설 else ''
    스파크 = _macro_spark(_key or item.get("표시명"), item.get("표시명"))
    return f'''
    <div class="mr-card">
      <div class="mr-top">
        <div class="mr-left">
          <p class="mr-label">{item['표시명']}</p>
          <p class="mr-val">{값표시}</p>
          <span class="{cls}" style="font-size:11px;font-weight:700">{item['등락률']:+.2f}%</span>
        </div>
        {스파크}
      </div>
      {해설HTML}
    </div>'''


def build_html(data, report):
    지수 = (data.get("지수수급") or {}).get("지수") or {}
    코 = 지수.get("코스피", {})
    닥 = 지수.get("코스닥", {})
    코수 = (data.get("지수수급") or {}).get("코스피_수급") or {}
    닥수 = (data.get("지수수급") or {}).get("코스닥_수급") or {}
    # 🆕 2026-08-22 — 예보 카드 제목에 쓸 다음 거래일 표기.
    #    build_core 안에도 같은 계산이 있지만 그건 그 함수의 지역변수라 여기선 못 쓴다.
    try:
        _NEXT = trading_day_context(
            datetime.strptime(data.get("날짜") or DATE, "%Y%m%d").date())["다음거래일표현"]
    except Exception:
        _NEXT = "내일"
    해석 = (report or {}).get("해석글", {})

    # 🆕 2026-08-26 — inherit_report.py가 전날 해석글을 승계했으면 그 사실을 밝힌다.
    #  [WHY] 해석글이 없다고 발행을 멈추면 하루가 통째로 빈다. 숫자·표는 전부
    #        정상인데도 그렇다. 그래서 **발행은 하되 어제 글임을 숨기지 않는다.**
    #  ⚠️ 이건 «오늘 글인 척»과 «발행 중단» 사이의 타협이다. 배너를 빼면
    #     어제 시황을 오늘 것으로 읽게 되므로 **절대 조용히 넘어가지 않는다.**
    _승계 = (report or {}).get("승계원본")
    승계배너 = ""
    if _승계:
        _md = f"{_승계[4:6]}/{_승계[6:]}"
        print(f"🔁 해석글 승계본으로 빌드합니다 — 원본 {_승계} (화면에 명시됨)")
        승계배너 = (
            '<div style="background:#2a1a12;border:1px solid #6b3f1f;'
            'border-radius:12px;padding:12px 14px;margin:0 0 14px">'
            '<p style="margin:0;font-size:12.5px;color:#f0c65a;font-weight:800">'
            f'⚠️ 오늘 해설은 <b>{_md} 글</b>을 그대로 싣습니다</p>'
            '<p style="margin:5px 0 0;font-size:11px;color:#c9ced6;line-height:1.7">'
            '오늘 해석글이 아직 만들어지지 않아 직전 거래일 글로 대신합니다. '
            '<b style="color:#e8eaee">지수·수급·섹터·레이더의 숫자와 표는 모두 '
            '오늘 것</b>이니 그대로 보셔도 됩니다.<br>'
            '<span style="color:#8b93a0">글로 된 해설(시황·이슈 해부·프로의 시선)만 '
            f'{_md} 것이라는 뜻이에요. 오늘 글이 준비되면 이 자리에서 바로 바뀝니다.</span>'
            '</p></div>')
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
    _catch_after_block = build_catch_after(data)   # 🆕 2026-08-24 포착 그 후

    # 🆕 2026-08-24 HO 지시 — 「내 관심종목」·「내 종목 브리핑」을 **심층편에서 뺀다.**
    #  ⚠️ 핵심편에 같은 코너가 그대로 있다. 두 편에 나오면 같은 화면을 두 번 보는 셈이고,
    #     특히 '등록하는 입력창'이 두 군데면 어디서 등록해야 하는지 헷갈린다.
    #  ⚠️ 삭제가 아니라 가림이다. 되살리려면 HIDDEN_CHAPTERS에서 키만 빼면 된다.
    #     §8 규칙대로 **제목 라벨까지 함께** hide() 안에 넣는다(라벨만 남는 실수 방지).
    _mystock_deep = hide("심층편관심종목",
        '<p class="sec-label"><small>내 자리</small>'
        '📋 내 종목 등록하기</p>'
        + build_my_stocks(data) + build_stock_brief())

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
<!-- ⚠️ 캐시 금지 (2026-08-18)
     GitHub Pages는 index.html을 10분 캐시하라고 지시하는데,
     모바일 인앱 브라우저(카톡·텔레그램)는 그보다 훨씬 오래 붙들고 있어
     PC와 모바일이 서로 다른 날 리포트를 보여주는 일이 생겼다.
     아래 세 줄이 "매번 서버에 다시 물어봐라"라고 지시한다. -->
<meta http-equiv="Cache-Control" content="no-cache, no-store, must-revalidate">
<meta http-equiv="Pragma" content="no-cache">
<meta http-equiv="Expires" content="0">
<meta name="cp-build" content="{BUILD_STAMP}">
<script>
/* 캐시된 옛 페이지를 자동으로 갈아끼운다.
   [WHY] 메타 태그만으로는 이미 캐시에 남은 페이지를 못 지운다.
         페이지가 열리면 서버에 최신 표식을 물어보고, 내가 들고 있는 것과
         다르면 한 번만 강제로 다시 받는다. (사용자가 ?v= 를 붙일 필요 없음) */
(function(){{
  try{{
    var mine=document.querySelector('meta[name="cp-build"]');
    mine=mine?mine.getAttribute('content'):'';
    if(!mine||location.search.indexOf('cpfresh=')>-1) return;
    fetch(location.pathname+'?cpcheck='+Date.now(),{{cache:'no-store'}})
      .then(function(r){{return r.text();}})
      .then(function(t){{
        var m=t.match(/name="cp-build" content="(\d+)"/);
        if(m&&m[1]&&m[1]!==mine){{
          location.replace(location.pathname+'?cpfresh='+m[1]);
        }}
      }}).catch(function(){{}});
  }}catch(e){{}}
}})();
</script>
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
/* 🆕 2026-08-26 심층편 칩 네비 — 코너를 줄이지 않고 '길다'는 체감만 줄인다.
   심층편은 16개 코너가 한 줄로 이어져 있어 "채점표만 보고 싶다"는 독자가
   전부를 손가락으로 지나쳐야 했다. 내용은 그대로, 이동 수단만 붙인다.
   ⚠️ .deep-wrap 안에서만 sticky다 — 핵심편에서는 안 나온다(의도).
   ⚠️ HO 지적 — 밝은 바에 흰 칩은 배경에 묻혀 안 보였다.
      심층편 배경(#e6e9ef)이 밝으므로 바를 **어둡게 반전**시켜 대비를 만든다. */
.cp-nav{{position:sticky;top:0;z-index:45;display:flex;gap:8px;overflow-x:auto;
  margin:-1.4rem -1.75rem 1.1rem;padding:11px 1.75rem;
  background:#0d1117;border-bottom:3px solid #e0c060;
  box-shadow:0 4px 14px rgba(0,0,0,.38);
  -webkit-overflow-scrolling:touch;scrollbar-width:none}}
.cp-nav::-webkit-scrollbar{{display:none}}
/* 🆕 2026-08-26 (2차) HO 지적 — "여전히 존재감이 없다".
   [고침] ① 바 배경을 거의 검정(#0d1117)으로 내려 대비를 키우고
          ② 칩 글자를 밝게(#e8eaee) + 11.5 → 12.5px
          ③ 활성 칩은 금색 채움 + 바깥 링으로 한 겹 더 띄운다. */
.cp-chip{{flex:none;font-size:12.5px;font-weight:700;color:#e8eaee;
  background:#252c36;border:1px solid #4a5462;border-radius:999px;
  padding:8px 15px;cursor:pointer;white-space:nowrap;font-family:inherit;
  line-height:1;-webkit-tap-highlight-color:transparent;
  transition:background .15s,color .15s}}
.cp-chip:hover{{background:#333c48;border-color:#6b7787}}
.cp-chip.on{{background:#e0c060;color:#14181f;border-color:#e0c060;font-weight:800;
  box-shadow:0 0 0 3px rgba(224,192,96,.22)}}
/* 넓은 화면 — 칩 6개가 다 들어가 스크롤이 없다. 왼쪽에 몰리면 허전해서
   가운데로 모아 탭바처럼 보이게 한다. */
@media (min-width:769px){{
  .cp-nav{{justify-content:center;gap:10px}}
  .cp-chip{{font-size:13px;padding:9px 17px}}
}}
/* 앵커는 보이지 않는 표식. scroll-margin-top이 칩바 높이만큼 자리를 비워
   제목이 칩바에 가려지는 것을 막는다. */
.nv-a{{display:block;height:0;overflow:hidden;scroll-margin-top:60px}}
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
/* 🆕 2026-08-22 — 관제지수 카드 오른쪽 지수 요약(스타일 A). 지수+등락률만. */
.gz-idx{{flex:none;border-left:1px solid rgba(255,255,255,.09);padding-left:16px;align-self:center}}
/* 라벨·종가·등락률 3열 그리드. 종가는 오른쪽 정렬해 자릿수가 달라도 세로로 맞는다. */
.gz-idx-row{{display:grid;grid-template-columns:auto minmax(58px,auto) 54px;align-items:baseline;column-gap:9px;padding:3px 0}}
.gz-idx-n{{font-size:11.5px;color:#8b93a0}}
.gz-idx-v{{font-size:12.5px;color:#e8eaee;font-variant-numeric:tabular-nums;text-align:right}}
.gz-idx-p{{font-size:12.5px;font-weight:800;font-variant-numeric:tabular-nums;text-align:right}}
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
.si-lens{{font-size:10px;font-weight:700;background:rgba(255,255,255,.12);color:#c9c4f0;padding:2px 8px;border-radius:4px;white-space:nowrap;flex-shrink:0;margin-top:3px;height:fit-content;display:flex;flex-direction:column;gap:1px;align-items:center}}
.si-act{{font-size:8px;font-weight:900;color:#8b93a0;letter-spacing:.03em}}
.study-src{{font-size:10.5px;font-weight:600;color:#5b8a2a;background:#dcebc8;display:inline-block;padding:2px 9px;border-radius:99px;margin:2px 0 6px}}
.study-box{{background:linear-gradient(135deg,#EAF3DE,#f2f7e8);border-radius:var(--rlg);padding:.95rem 1.1rem;margin-bottom:1rem;font-size:12.5px;color:#3B6D11;line-height:1.8}}
.hidden-block{{display:none}} .hidden-block.open{{display:block}}
/* 🆕 2026-08-22 — "확인 ↓"으로 이동했을 때 제목이 화면 맨 위에 딱 붙어
   잘려 보이던 문제. 앵커 대상에 위 여백을 준다. */
html{{scroll-behavior:smooth}}
#score,#flow,#radar,#acc,#watch,#deep{{scroll-margin-top:64px}}
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
.rd-name{{font-size:12.5px;font-weight:700;color:var(--ink);display:flex;align-items:center;gap:6px;flex-wrap:wrap;margin:0}}
/* 🆕 2026-08-25 — 유형 배지 전용 줄. 이름과 분리해 배지끼리만 줄바꿈한다. */
.rd-badges{{display:flex;align-items:center;gap:5px;flex-wrap:wrap;margin:4px 0 0}}
.rd-tag{{font-size:8.5px;font-weight:700;padding:1px 5px;border-radius:4px;white-space:nowrap}}
.rd-new{{background:#FAECE7;color:#993C1D}} .rd-stay{{background:#FAEEDA;color:#854F0B}}
.rd-meta{{font-size:10.5px;color:var(--sub);margin-top:2px}}
.rd-nums{{text-align:right;flex-shrink:0}}
.rd-score{{display:block;font-size:15px;font-weight:800;color:#8a5a1f}}\n.rd-boom{{background:#FAECE7;color:#C1432B}}
.rd-chg{{font-size:11px;font-weight:700}}
/* 🆕 2026-08-22 — V자 반등은 전일 종가 대비로는 하락일 수 있다. 색을 나눈다. */
.rd-chg.up{{color:#c1432b}} .rd-chg.dn{{color:#2e6bd6}}
.ac-gap{{text-align:right;flex-shrink:0}}
.ac-gap b{{display:block;font-size:14px;font-weight:800;color:#8a5a1f}}
.ac-char{{display:block;font-size:9px;color:var(--sub);white-space:nowrap}}
.ac-two{{display:grid;grid-template-columns:1fr 1fr;gap:10px}}
.ac-col{{background:var(--bg2);border-radius:var(--rmd);padding:.7rem .8rem}}
.ac-col-t{{font-size:12px;font-weight:800;color:var(--ink)}}
.ac-col-s{{font-size:9.5px;color:var(--sub);margin:2px 0 .5rem}}
.ac-rank{{font-size:11px;font-weight:800;color:#c9c1b0;font-style:italic;width:14px;flex-shrink:0}}
.ac-info{{flex:1;min-width:0}}
/* 🆕 2026-08-25 HO 지적 — 심층편 매집 종목명이 희미해서 안 보인다.
   [원인] var(--ink)가 이 배경에서는 대비가 약했고, 글자도 11.5px로 작았다.
          아래 meta(회색 10px)와 무게 차이가 거의 없어 묻혔다. */
.ac-name{{font-size:14px;font-weight:800;color:var(--ink);display:flex;align-items:center;gap:5px;flex-wrap:wrap}}
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

/* ⚠️ 위 문장들과 붙어 보여 답답했다(2026-08-20). 위 여백을 준다. */
/* 🆕 2026-08-22 — 신호등 바로 밑으로 올라오면서 위 여백을 줄였다.
   신호등(색)과 정의(말)는 한 쌍이라 붙어 보여야 한다. */
.q90-def{{margin-top:.35rem;font-size:21px;font-weight:800;color:#fff;line-height:1.45;letter-spacing:-.02em;margin-bottom:.5rem}}
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
.ix-bv{{width:118px;text-align:right;font-size:13.5px;font-weight:900;flex-shrink:0;line-height:1.05}}
.ix-bv small{{font-size:10px;color:#9aa0a8;font-weight:600;display:block;margin-top:5px;word-break:keep-all;line-height:1.4}}
.ix-scale{{display:flex;justify-content:space-between;font-size:8.5px;color:#6b7078;padding-left:57px;padding-right:109px}}
.ix-flow{{display:flex;justify-content:space-between;align-items:center;margin-top:11px;padding-top:10px;border-top:1px solid rgba(255,255,255,.08)}}
.ix-flow-k{{font-size:11px;color:#9aa0a8;font-weight:700}}
.ix-flow-v{{font-size:14.5px;font-weight:900}}
/* ⚠️ 수급 값 색도 막대와 같아야 한다. 막대만 바꾸고 숫자를 초록/보라로 두면
   같은 줄 안에서 색이 둘로 갈려 더 헷갈린다. (2026-08-18) */
.ix-head .buy{{color:#ff6b4a}} .ix-head .sell{{color:#ff6b4a}} .ix-head .flat{{color:#8a909a}}
.ix-head .sellv{{color:#5b9bff}}
.ix-ring{{width:42px;height:42px;border-radius:50%;border:3px solid #ff6b4a;display:flex;align-items:center;justify-content:center;font-size:20px;font-weight:900;flex-shrink:0}}
.hi-ring{{width:42px;height:42px;border-radius:50%;border:3px solid #ff6b4a;display:flex;align-items:center;justify-content:center;font-size:20px;font-weight:900;flex-shrink:0}}
.hi-gauge{{width:46px;height:46px;position:relative;flex-shrink:0}}
.hi-gauge-c{{position:absolute;inset:0;display:flex;align-items:center;justify-content:center;font-size:14px}}
.hi-light{{display:flex;flex-direction:column;gap:5px;flex-shrink:0;padding:6px 5px;background:rgba(0,0,0,.25);border:1px solid rgba(255,255,255,.12);border-radius:10px}}
.hi-light .hi-dot{{width:12px;height:12px;border-radius:50%;border:1.5px solid rgba(255,255,255,.25)}}
.hi-light .hi-dot.on{{background:var(--gc);animation:hiblink 1.5s ease-in-out infinite}}
@keyframes hiblink{{0%,100%{{box-shadow:0 0 18px var(--gc),0 0 6px var(--gc);opacity:1;transform:scale(1.12)}}50%{{box-shadow:0 0 2px var(--gc);opacity:.32;transform:scale(1)}}}}
/* 🆕 2026-08-22 — 레이더 두 코너의 이모지에 성격을 담은 움직임을 준다.
   ⚠️ prefers-reduced-motion을 켠 사용자에게는 멈춘다(멀미·발작 유발 방지). */
/* 🆕 2026-08-25 (3차) — HO: "빨리가 아니라 **리얼하게**".
   [핵심] 진짜 불은 **일정한 리듬으로 안 흔들린다.** 불규칙해야 불처럼 보인다.
          그래서 키프레임 간격을 일부러 들쭉날쭉하게 잡는다(7·19·26·41·58·73·88%).
          모양(scaleX/Y 왜곡)은 여전히 안 건드린다 — 이모지는 글자라 찌그러진다.
          대신 밝기·채도가 살짝 출렁이고 아주 조금 떠오른다.
   [거북이] 진짜 거북이는 등속으로 안 간다. **한 걸음 내딛고 오래 멈춘다.**
          0~22%에 움직이고 22~62%는 완전히 정지, 다시 돌아오고 또 정지.
          이 '멈춤'이 있어야 기어가는 것처럼 보인다. */
@keyframes cpFlame{{
 0%   {{transform:translateY(0)    rotate(-3deg) scale(1);   filter:brightness(1)}}
 7%   {{transform:translateY(-1px) rotate(2deg)  scale(1.05);filter:brightness(1.22)}}
 19%  {{transform:translateY(0)    rotate(-1deg) scale(.98); filter:brightness(.96)}}
 26%  {{transform:translateY(-2px) rotate(4deg)  scale(1.08);filter:brightness(1.3)}}
 41%  {{transform:translateY(0)    rotate(-2deg) scale(1.01);filter:brightness(1.02)}}
 58%  {{transform:translateY(-1px) rotate(3deg)  scale(1.06);filter:brightness(1.26)}}
 73%  {{transform:translateY(0)    rotate(-3deg) scale(.99); filter:brightness(.94)}}
 88%  {{transform:translateY(-1px) rotate(1deg)  scale(1.04);filter:brightness(1.16)}}
 100% {{transform:translateY(0)    rotate(-3deg) scale(1);   filter:brightness(1)}}}}
@keyframes cpTurtle{{
 0%   {{transform:translateX(0)   rotate(0)}}
 10%  {{transform:translateX(3px) rotate(-2deg)}}   /* 앞발을 뻗는다 */
 22%  {{transform:translateX(6px) rotate(1deg)}}    /* 몸을 끌어당긴다 */
 62%  {{transform:translateX(6px) rotate(0)}}       /* ⬅ 오래 멈춘다 */
 72%  {{transform:translateX(3px) rotate(2deg)}}
 84%  {{transform:translateX(0)   rotate(-1deg)}}
 100% {{transform:translateX(0)   rotate(0)}}}}
.cp-flame{{display:inline-block;animation:cpFlame 2.4s linear infinite;
  transform-origin:50% 92%}}
.cp-turtle{{display:inline-block;animation:cpTurtle 5.2s ease-in-out infinite;
  transform-origin:50% 85%}}
@media (prefers-reduced-motion:reduce){{.cp-flame,.cp-turtle{{animation:none}}}}
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
.ix-cum .buy{{color:#ff6b4a}} .ix-cum .sellv{{color:#5b9bff}}
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
.q90-gloss{{font-size:12px;color:#9aa0a8;line-height:1.7;margin:-.2rem 0 1rem}}
.mine-f2{{font-size:13px;font-weight:800;color:#fff;margin-top:.5rem}}
.q90-cut{{text-align:center;font-size:12px;color:var(--sub);background:var(--bg2);border:.5px solid var(--line);border-radius:99px;padding:9px 0;margin:.6rem 0 0}}
.deep-cut{{display:flex;align-items:center;justify-content:center;gap:16px;margin:1.2rem 0 .2rem;padding:1rem 1rem;background:linear-gradient(180deg,#2a2e36,#20242b);border-radius:14px;border:1px solid rgba(224,192,96,.25)}}
.deep-arrow{{font-size:38px;font-weight:900;color:#e0c060;line-height:.6;animation:deepbob 1.4s ease-in-out infinite}}
@keyframes deepbob{{0%,100%{{transform:translateY(-2px)}}50%{{transform:translateY(3px)}}}}
.deep-txt{{text-align:center}}
.deep-t1{{font-size:12px;color:#9aa0a8;font-weight:700}}
.deep-t2{{font-size:14px;color:#e8e6e2;font-weight:800;margin-top:2px}}
.deep-t2{{word-break:keep-all}}
.deep-t2 b{{color:#e0c060}}
.deep-pre{{display:inline-block;margin-top:8px;padding:6px 12px;font-size:11px;
  font-weight:700;color:#cdd2da;background:rgba(224,192,96,.10);
  border:.5px solid rgba(224,192,96,.32);border-radius:14px;line-height:1.6;
  word-break:keep-all;max-width:19em}}
.deep-pre b{{color:#e0c060}}
.tmr{{margin-top:1rem;padding:.9rem 1rem;background:linear-gradient(180deg,#2b2f37,#242830);border-radius:12px;border-left:4px solid #e0c060}}
.tmr-h{{font-size:17px;font-weight:800;color:#e0c060;margin-bottom:6px}}
.tmr-b{{font-size:13px;color:#e8e6e2;line-height:1.7}}



















@media (max-width:600px){{
  body{{padding:8px 0}}
  .rp{{padding:1.1rem 1rem 1.5rem;border-radius:0;max-width:100%}}
  .deep-wrap{{margin-left:-1rem;margin-right:-1rem;padding-left:1rem;padding-right:1rem}}
  .cp-nav{{margin-left:-1rem;margin-right:-1rem;padding-left:1rem;padding-right:1rem}}
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
.core-g-cap{{font-size:9.5px;font-weight:800;color:#8b93a0;margin:0 0 1px;letter-spacing:.02em;white-space:nowrap}}
.core-g-l svg{{max-width:96px}}
.core-g-x{{font-size:11px;font-weight:900;margin:.1rem 0 0}}
.core-g-v{{font-size:23px;font-weight:900;margin:0;letter-spacing:-.04em;font-variant-numeric:tabular-nums;line-height:1.1}}
.core-g-s{{font-size:10.5px;color:#8b93a0;margin:.2rem 0 0}}
.core-g-s b{{color:#c9d0d9}}
.core-g-k{{display:inline-block;font-size:10px;font-weight:800;padding:.15rem .5rem;border-radius:20px;border:1px solid #2a3342;background:#0d1118;margin:.35rem 0 0;white-space:nowrap}}   /* 🆕 2026-08-22 — "평소보다 조용한 하루"가 "하루"만 다음 줄로 떨어지던 문제. 배지 문구는 10자 안팎이라 한 줄 강제해도 좁은 화면에서 안 넘친다 */
/* 뜨는 현장 레이더 — 섹터 점이 천천히 명멸한다 */
/*   ⚠️ 빠르게 깜빡이면 요란하고 눈이 아프다. 3.2초 주기 ease-in-out으로
       숨 쉬듯 느리게, 투명도만 오간다(크기는 안 건드려 위치가 안 흔들린다).
       섹터마다 시작 시점을 어긋나게 해 한꺼번에 켜지지 않게 한다. */
@keyframes rdrpulse{{0%,100%{{opacity:1}}50%{{opacity:.42}}}}
.rdr-dot{{animation:rdrpulse 3.2s ease-in-out infinite}}
@media (prefers-reduced-motion:reduce){{.rdr-dot{{animation:none}}}}
/* 매집 레이더 기간 탭 */
.ac-tabs{{display:flex;gap:.35rem;margin:.7rem 0 .6rem}}
/* ⚠️ 이 코너는 밝은 배경 카드 위에 놓인다. 탭을 검게 두면 배경에 파묻혀
   "누를 수 있는 것"으로 안 보인다 → 밝은 회색 위에 금색 선택으로 바꿨다. */
.ac-tab{{flex:1;text-align:center;font-size:12px;font-weight:800;padding:.5rem 0;border-radius:8px;background:#eef1f6;border:1px solid #d6dbe4;color:#6b7280;cursor:pointer}}
.ac-tab.on{{background:#f0c65a;border-color:#d8ab35;color:#2a2410}}
.ac-tab.off{{opacity:.4;cursor:default}}
.ac-body{{display:none}}
.ac-body.on{{display:block}}
/* 헤더 수급 배지 — 각 줄은 반드시 한 줄로(줄바꿈 금지) */
.ix-bv small .bdg1,.ix-bv small .bdg2{{display:block;white-space:nowrap;line-height:1.35}}
.ix-bv small .bdg2{{color:#7d848f;font-size:9px}}
/* ── 기간 탭 공통 (오늘·5일·20일·60일) ──
   ⚠️ 코너마다 탭 모양이 제각각이면 같은 기능인 줄 모른다(2026-08-20 지시).
      섹터 성적표·크기별·관심종목·수급 타임라인·매집 레이더가 전부 같은 모양을 쓴다. */
/* 🆕 2026-08-24 매집 차수·연속 배지 */
.ac-badge{{margin:2px 0 0;line-height:1.4}}
.ac-badge:empty{{display:none}}
/* 🆕 2026-08-24 (2차) — HO: "배지가 너무 강렬해서 종목명이 묻힌다".
   [원칙] 배지는 **보조 정보**다. 주인공은 종목명이어야 한다.
          알약(pill) 배경을 걷어내고 글자만 남긴다. 채도도 한 단계 낮춘다.
   ⚠️ 2차 이상 매집만 예외 — 드물고 중요해서 굵기로만 살짝 남긴다.
      (색을 살리지 않고 굵기로 구분하면 시선을 덜 뺏는다) */
/* 🆕 2026-08-25 HO 지시 — 배경만 빼고 **테두리는 색으로 남긴다**.
   [의도] 배경이 있으면 덩어리로 보여 종목명과 시선을 다툰다.
          테두리만 있으면 윤곽은 유지되면서 무게가 확 준다. */
.ab{{display:inline-block;font-size:8.5px;font-weight:600;padding:0 5px;
  margin:2px 3px 0 0;line-height:1.55;border-radius:999px;
  background:none;border:1px solid currentColor}}
.ab1{{color:#5f9a8c}}
.ab2{{color:#d1a83f;font-weight:800}}
.abc{{color:#9b8ac0}}
.abn{{color:#77a377}}
.abd{{color:#5a616b}}
/* 🆕 2026-08-26 강세 레이더 안내 (조건 설명 바로 밑) */
.rd-guide{{background:rgba(255,255,255,.55);border:1px solid #e6e2da;
  border-radius:10px;padding:10px 11px;margin:8px 0 10px}}
.rd-guide-h{{margin:0 0 6px;font-size:12.5px;font-weight:800;color:var(--ink)}}
.rd-guide-b{{margin:0;font-size:11.5px;color:#3d4450;line-height:1.75}}
.rd-guide-n{{margin:6px 0 0;font-size:10.5px;color:#6b7280;line-height:1.6}}
/* 🆕 2026-08-25 종목 카드 */
.sc-guide{{background:#141922;border:1px solid #2a3446;border-radius:11px;
  padding:11px 12px;margin:14px 0 8px}}
.sc-guide-h{{margin:0 0 5px;font-size:13px;font-weight:800;color:#8fd0e8}}
.sc-guide-b{{margin:0;font-size:11.5px;color:#c9ced6;line-height:1.7}}
.sc-guide-n{{margin:6px 0 0;font-size:10px;color:#7d848f;line-height:1.6}}
/* 🆕 2026-08-25 — «▾ 기업분석» 배지를 눈에 띄게. 눌러야 하는 것이므로
   장식이 아니라 **버튼처럼** 보여야 한다. */
/* 🆕 2026-08-25 (3차) — HO 지시: "기업분석은 핵심편 디자인으로 전부 통일".
   [반성] 직전 판에서 배경 밝기에 맞춰 배지를 두 벌로 나눴는데, 그러자
          "심층편만 다르게 보인다"는 새 불만이 생겼다. 카드 내부는 원래도
          고정 다크 팔레트라 똑같았는데, **바깥 배지만** 갈라놓은 게 문제였다.
   [고침] 배지를 핵심편 스타일(하늘색 채움 알약) **한 가지로 고정**한다.
          배경이 밝은 곳에서도 대비가 되도록 살짝 그림자를 준다. */
/* 🆕 2026-08-26 HO 지시 — "확실히 누를 수 있도록" 더 크게.
   [WHY] 눌러야 열리는 버튼인데 장식처럼 작으면 아무도 안 눌러본다.
         모바일에서 손가락으로 짚으려면 최소한의 높이가 필요하다. */
/* 🆕 2026-08-26 HO 지시 — 알약은 작게, **화살표만** 크게.
   [WHY] 알약이 커지니 종목명과 시선을 다퉜다. 정작 눌러야 할 신호는
         화살표 하나면 충분하다. 글자는 줄이고 화살표만 키운다. */
.sc-tap{{font-size:9px;color:#0b0e13;background:#8fd0e8;font-weight:800;
  margin-left:5px;padding:1px 6px;border-radius:999px;
  white-space:nowrap;cursor:pointer;vertical-align:middle;
  box-shadow:0 1px 2px rgba(0,0,0,.3)}}
.sc-tap i{{font-style:normal;font-size:14px;line-height:1;vertical-align:-1px;
  margin-right:2px;font-weight:900}}
/* 🆕 2026-08-25 — 클래스명을 .sc-name → .cp-sname 으로 분리.
   [사고] .sc-name은 **섹터 테마명**이 이미 쓰고 있었고 color:var(--ink)였다.
          --ink는 #1a1a1a(거의 검정)이라 어두운 카드 배경에서 글자가 사라졌다.
          이름이 겹치면 이렇게 조용히 죽는다. */
.cp-sname{{cursor:pointer;color:inherit;font-weight:800}}
/* 🆕 2026-08-26 HO 지시 — 기업분석 카드가 다른 코너와 비슷해 헷갈린다.
   [해법] '펼쳐진 서랍'처럼 보이게 만든다 — 본문과 다른 층으로 인식되게.
     ① 왼쪽 굵은 하늘색 세로 띠 (이 카드만의 색)
     ② 안쪽 들여쓰기 — 종목명에 딸린 것임을 표시
     ③ 위쪽 화살표 꼬리 — 어느 종목에서 펼쳐졌는지 시선을 잇는다
     ④ 더 어두운 배경 + 안쪽 그림자로 '눌린 면' 느낌
     ⑤ 오른쪽 위 «기업분석» 꼬리표 */
.sc-card{{position:relative;background:#080b10;
  border:1px solid #2a3446;border-left:4px solid #8fd0e8;
  border-radius:4px 10px 10px 4px;
  padding:12px 12px 11px;margin:12px 0 4px 10px;
  box-shadow:inset 0 2px 8px rgba(0,0,0,.55)}}
.sc-card::before{{content:"";position:absolute;top:-7px;left:14px;
  width:12px;height:12px;background:#080b10;
  border-left:1px solid #2a3446;border-top:1px solid #2a3446;
  transform:rotate(45deg)}}
.sc-card::after{{content:"기업분석";position:absolute;top:-9px;right:12px;
  font-size:8.5px;font-weight:800;color:#8fd0e8;background:#0b0e13;
  padding:1px 6px;border-radius:999px;border:1px solid #2a3446}}
.sc-def{{margin:0 0 3px;font-size:11.5px;color:#8fd0e8;font-weight:700}}
.sc-biz{{margin:0 0 4px;font-size:11.5px;color:#c9ced6;line-height:1.6}}
.sc-basic{{margin:0 0 8px;font-size:11.5px;color:#c9ced6;font-weight:600}}
.sc-hot{{font-size:9px;color:#0b0e13;background:#74f0d4;font-weight:800;
  padding:1px 5px;border-radius:999px;vertical-align:middle}}
.sc-why-s{{margin:3px 0 0;font-size:10.5px;color:#a8b0ba;line-height:1.6}}
.sc-why-badge{{margin:5px 0 0;line-height:1.5}}
.sc-h{{margin:0 0 5px;font-size:11.5px;font-weight:800;color:#e0c060}}
.sc-sub{{font-size:9.5px;font-weight:600;color:#6f7784;margin-left:4px}}
.sc-why{{background:#141922;border-radius:8px;padding:8px 9px;margin-bottom:8px;
  border-left:3px solid #74f0d4}}
.sc-why-t{{margin:0 0 3px;font-size:12px;font-weight:800;color:#e8eaee}}
.sc-why-b{{margin:0;font-size:11px;color:#c9ced6;line-height:1.6}}
.sc-why-m{{margin:4px 0 0;font-size:10.5px;color:#8fd0e8;line-height:1.6}}
.sc-fin{{background:#141922;border-radius:8px;padding:8px 9px}}
.sc-row{{display:flex;align-items:center;gap:7px;margin-top:5px;flex-wrap:wrap}}
.sc-k{{font-size:10.5px;color:#8b93a0;width:52px;flex:none}}
.sc-v{{font-size:12px;font-weight:800;color:#e8eaee}}
.sc-warn{{margin:6px 0 0;font-size:10.5px;color:#e0c060;line-height:1.55}}
.sc-note{{margin:6px 0 0;font-size:10.5px;color:#a8b0ba;line-height:1.6}}
.sc-src{{margin:6px 0 0;font-size:9.5px;color:#6f7784;line-height:1.55}}
/* 📊 2026-09-01 정식 연결 — 사업 포트폴리오 가로 막대.
   ⚠️ 색은 하늘색 계열(#8fd0e8)로 간다 — 이 카드의 고유색이고,
      지수(빨강/파랑)·수급(초록/보라) 두 색 규칙 어디와도 안 겹친다.
   ⚠️ 이름·%를 막대 위 줄에 두고 막대는 폭 전체를 쓴다 — 한 줄에
      다 넣으면 막대가 너무 짧아 비중 차이가 눈으로 안 구분된다
      (2026-08-31 1차 시안 실패, 실측 후 이 구조로 교정). */
.bp-wrap{{margin:7px 0 0}}
.bp-row{{margin:0 0 8px}}
.bp-top{{display:flex;align-items:baseline;justify-content:space-between;
  gap:8px;margin:0 0 3px}}
.bp-k{{font-size:10.5px;color:#c8d0da;font-weight:700;
  overflow:hidden;text-overflow:ellipsis;white-space:nowrap}}
.bp-v{{flex:0 0 auto;font-size:11px;color:#8fd0e8;font-weight:800}}
.bp-bar{{display:block;width:100%;height:9px;background:#141a24;
  border-radius:3px;overflow:hidden}}
.bp-bar i{{display:block;height:100%;border-radius:3px;
  background:linear-gradient(90deg,#4d8ba3,#8fd0e8)}}
@media (max-width:360px){{
  .bp-k{{font-size:9.5px}} .bp-v{{font-size:10px}}
}}
.sc-empty{{margin:0;font-size:10.5px;color:#6f7784;line-height:1.6}}
.sc-more{{margin:8px 0 0;font-size:11px;font-weight:700;color:#f0c65a;
  cursor:pointer;text-align:center;padding:6px;background:#141922;border-radius:7px}}
.sc-blk{{background:#141922;border-radius:8px;padding:8px 9px;margin-top:7px}}
.sc-news{{margin:3px 0 0;font-size:10.5px;line-height:1.55}}
/* 🆕 2026-08-26 — 「왜 주목받나」의 수급·레이더 줄. 뉴스 링크와 구분되게
   왼쪽에 얇은 띠를 두고 글자색을 한 단계 밝게 한다. */
.sc-sig{{margin:5px 0 0;padding:5px 0 5px 9px;font-size:11px;line-height:1.65;
  color:#b6bdc7;border-left:2px solid #2b3d4a}}
.sc-sig b{{color:#e8eaee}}
.sc-news a{{color:#8fb4ee;text-decoration:none}}
.sc-kind{{font-size:9px;color:#6f7784}}
.sc-if{{margin:3px 0 0;font-size:10.5px;color:#c9ced6;line-height:1.6}}
.sc-disc{{margin:7px 0 0;font-size:9.5px;color:#6f7784;line-height:1.55}}
/* 🆕 2026-08-26 여기까지 정리하면 */
.ms-box{{background:linear-gradient(160deg,#1a2230,#141a24);
  border:1.5px solid #2f3d52;border-radius:14px;padding:13px 13px 11px;margin:12px 0 14px}}
.ms-h{{margin:0;font-size:15.5px;font-weight:800;color:#e0c060}}
.ms-s{{margin:3px 0 9px;font-size:11px;color:#8b93a0;line-height:1.6}}
.ms-row{{display:flex;gap:9px;align-items:flex-start;margin-top:9px;
  background:#0f131a;border-radius:9px;padding:9px 10px}}
.ms-no{{flex:none;width:20px;height:20px;border-radius:50%;background:#e0c060;
  color:#141a24;font-size:11.5px;font-weight:900;display:flex;
  align-items:center;justify-content:center;line-height:1}}
.ms-num{{font-size:11px;color:#8b93a0;font-weight:600}}
.ms-txt{{flex:1;min-width:0}}
.ms-k{{margin:0;font-size:10px;color:#8b93a0;font-weight:700}}
.ms-v{{margin:3px 0 0;font-size:13px;color:#e8eaee;line-height:1.65}}
.ms-t{{margin:6px 0 0;font-size:11.5px;color:#8fd0e8;line-height:1.65}}
.ms-note{{margin:10px 0 0;font-size:11px;color:#c9ced6;line-height:1.6;text-align:center}}
/* 🆕 2026-08-25 오늘 이상했던 것 */
.odd-box{{background:#141922;border:1px solid #2a3446;border-radius:12px;
  padding:12px 12px 10px;margin:10px 0 14px}}
.odd-h{{margin:0;font-size:15px;font-weight:800;color:#22d3ee}}
.odd-s{{margin:3px 0 0;font-size:11px;color:#8b93a0;line-height:1.6}}
.odd-item{{background:#0f131a;border-radius:9px;padding:9px 10px;margin-top:8px;
  border-left:3px solid #22d3ee}}
.odd-t{{margin:0 0 4px;font-size:13px;font-weight:800;color:#e8eaee}}
.odd-b{{margin:0;font-size:11.5px;color:#c9ced6;line-height:1.65}}
.odd-m{{margin:5px 0 0;font-size:11px;color:#8fd0e8;line-height:1.65}}
.odd-note{{margin:8px 0 0;font-size:10px;color:#7d848f;line-height:1.6}}
/* 🆕 2026-08-25 항로도 */
.rt-box{{background:#0f131a;border:1px solid #1e2531;border-radius:12px;
  padding:11px 11px 10px;margin:8px 0 14px}}
.rt-h{{margin:0;font-size:13px;font-weight:800;color:#f0c65a}}
.rt-item{{background:#141922;border-radius:9px;padding:8px 10px;margin-top:7px}}
.rt-t{{margin:0 0 3px;font-size:12.5px;font-weight:800;color:#e8eaee}}
.rt-d{{margin:0;font-size:11px;color:#a8b0ba;line-height:1.6}}
.rt-freq{{display:block;margin-top:4px;font-size:10px;color:#8b93a0;line-height:1.55}}
.rt-note{{margin:8px 0 0;font-size:10px;color:#7d848f;line-height:1.6}}
/* 🆕 2026-08-24 포착 그 후 */
.cg-box{{background:#0f131a;border:1px solid #1e2531;border-radius:12px;
  padding:11px 10px;margin:8px 0 14px}}
.cg-tabs{{display:flex;gap:5px;margin-bottom:9px;flex-wrap:wrap}}
/* 🆕 2026-08-29 — 부제(.cg-tab-r)를 없애고 한 줄 라벨(«D+5~10»)로 바꿨다.
   두 줄일 때 쓰던 좁은 세로 padding(5px)이 한 줄에서는 납작해 보여서
   위아래를 넉넉히(7px) 준다. */
.cg-tab{{flex:1;min-width:62px;text-align:center;padding:7px 4px;font-size:12px;
  font-weight:800;color:#7d848f;background:#141922;border:1px solid #1e2531;
  border-radius:7px;cursor:pointer;line-height:1.3;white-space:nowrap}}
.cg-tab.on{{color:#0b0e13;background:#f0c65a;border-color:#f0c65a}}
/* 🆕 2026-08-26 기법 비교 그래프 */
.cg-cmp{{background:#0b0e13;border:1px solid #232a36;border-radius:9px;
  padding:9px 10px;margin-top:7px}}
.cg-cmp-h{{margin:0 0 4px;font-size:11.5px;font-weight:800;color:#c9ced6}}
.cg-cmp-n{{margin:5px 0 0;font-size:10px;color:#8b93a0;line-height:1.6}}
.cg-range{{margin:0 0 8px;padding:5px 8px;background:#0b0e13;
  border:1px solid #232a36;border-radius:7px;
  font-size:9.5px;color:#8b93a0;text-align:center;line-height:1.5}}
.cg-card{{background:#141922;border-radius:9px;padding:9px 10px;margin-bottom:7px}}
.cg-h{{margin:0 0 5px;font-size:12px;font-weight:800;color:#c9ced6;
  display:flex;justify-content:space-between;align-items:center}}
.cg-n{{font-size:10px;font-weight:600;color:#6f7784}}
.cg-main{{display:flex;align-items:baseline;gap:9px;flex-wrap:wrap}}
.cg-avg{{font-size:20px;font-weight:900;letter-spacing:-.5px}}
.cg-win{{font-size:11px;color:#8d949f;font-weight:600}}
.cg-bench{{margin:4px 0 0;font-size:10.5px;color:#8d949f;line-height:1.5}}
.cg-ext{{margin:5px 0 0;font-size:10px;color:#7d848f;line-height:1.5}}
.cg-empty{{margin:0;font-size:10.5px;color:#6f7784;line-height:1.5}}
.cg-note{{margin:8px 0 0;padding:7px 9px;background:#141922;border-radius:7px;
  font-size:10px;color:#8d949f;line-height:1.65}}
.sb-tab,.zt-tab,.ms-tab,.fs-ptab,.ac-tab{{
  flex:1;text-align:center;font-size:11.5px;font-weight:800;padding:.42rem .2rem;
  border-radius:8px;background:#0d1118;border:1px solid #1e2531;color:#7d848f;
  cursor:pointer;letter-spacing:-.01em;white-space:nowrap}}
.sb-tab.on,.zt-tab.on,.ms-tab.on,.fs-ptab.on,.ac-tab.on,
.sb-tab.active,.zt-tab.active,.ms-tab.active{{
  background:#1b2432;border-color:#3a465c;color:#fff}}
.ac-tab.off{{opacity:.4;cursor:default}}
/* 계기판 — 3일 추이 + 실탄 설명 */
.core-g{{grid-template-columns:auto minmax(0,1fr) auto}}
.fg-spark{{text-align:center;flex:0 0 auto}}
.fg-spark svg{{width:92px}}
.fg-spark-t{{font-size:8.5px;color:#7d848f;font-weight:700;margin:0 0 2px}}
.fg-def{{font-size:10.5px;color:#8b93a0;line-height:1.7;margin:.55rem 0 0;padding-top:.5rem;border-top:1px solid rgba(255,255,255,.08)}}
.fg-def b{{color:#c9d0d9}}
@media (max-width:359px){{.core-g{{grid-template-columns:auto minmax(0,1fr)}}.fg-spark{{display:none}}}}
/* 관심종목 백업 */
.ms-bk{{display:flex;gap:6px;align-items:center;flex-wrap:wrap;margin:10px 0 0;padding-top:9px;border-top:1px solid rgba(255,255,255,.08)}}
.ms-bk-b{{font-size:11px;font-weight:800;padding:5px 10px;border-radius:7px;background:#0f131a;border:1px solid #2a3446;color:#c9ced6;cursor:pointer}}
.ms-bk-t{{font-size:9.5px;color:#6f7784;line-height:1.5;flex:1;min-width:140px}}
/* 🔮 돌아올 섹터 적중률 */
.rs-grade{{font-size:11.5px;color:#c9ced6;line-height:1.75;margin:0 0 11px;padding:10px 12px;background:#141a22;border:1px solid #24303f;border-radius:10px}}
.rs-grade.dim{{color:#8b93a0}}
.rs-grade b{{color:#fff}}
/* 🌏 바깥 날씨 — 5일 추이 선 */
.mr-top{{display:flex;align-items:center;justify-content:space-between;gap:8px}}
.mr-left{{min-width:0}}
.mr-spark{{width:158px;height:58px;flex:0 0 auto}}
@media (max-width:359px){{.mr-spark{{display:none}}}}
/* 🌅 내일장 숫자 기준선 */
.tmr-line{{font-size:12.5px;color:#f0c65a;line-height:1.8;margin:0 0 9px;padding:10px 12px;background:#1a1610;border:1px solid #3a3020;border-radius:9px;font-weight:700}}
.tmr-line b{{color:#fff}}
/* 📡 관제교신 — 타임라인 아래 해석 */
.atc{{background:#0e141c;border:1px solid #22303f;border-left:3px solid #22d3ee;border-radius:12px;padding:13px 15px;margin:12px 0 0}}
.atc-p{{font-size:12.5px;color:#c9ced6;line-height:1.85;margin:0 0 10px}}
.atc-p:last-child{{margin-bottom:0}}
.atc-lead{{color:#e8eaee}}
.atc-p b,.atc-ask b{{color:#fff;font-weight:800}}
.atc-ask{{font-size:12.5px;color:#c9ced6;line-height:1.85;margin:0 0 10px;padding:11px 12px;background:#121922;border-radius:9px;border:1px solid #1e2a36}}
.atc-q{{margin:0 0 7px}}
.atc-q:first-child{{margin-bottom:10px}}
.atc-q:last-child{{margin-bottom:0}}
.atc-next{{font-size:12.5px;color:#f0c65a;line-height:1.8;margin:0;padding-top:10px;border-top:1px solid rgba(255,255,255,.08);font-weight:700}}
.atc-next b{{color:#fff}}
/* 🧭 왜 이렇게 움직였을까요 — 팩트 바로 뒤, 핵심편에서 가장 중요한 자리 */
/* 🆕 2026-08-22 — 📰팩트 + 🧭해석을 한 덩어리로 묶는 바깥 카드.
   안쪽 두 블록의 위/아래 여백을 죽여 "한 이야기"로 붙여 보이게 한다. */
.movers90{{background:#12171f;border:1px solid #232a36;border-radius:14px;padding:.55rem .6rem;margin-top:.8rem}}
.movers90 .iss90{{margin-top:0;background:transparent;padding:.35rem .45rem}}
.movers90 .q90-whybox{{margin:.3rem 0 0;border-radius:10px}}
.q90-whybox{{background:#141a22;border:1px solid #24303f;border-left:3px solid #e0c060;border-radius:12px;padding:12px 14px;margin:12px 0 0}}
.q90-why-h{{font-size:14px;font-weight:900;color:#f0c65a;margin:0 0 7px;letter-spacing:-.02em}}
.q90-why-b{{font-size:13px;color:#c9ced6;line-height:1.8;margin:0 0 8px}}
.q90-why-b:last-child{{margin-bottom:0}}
.q90-why-b b{{color:#fff;font-weight:800}}
/* 계기판 밑 한 줄 코멘트 */
.mny-cmt{{font-size:11.5px;color:#9aa0aa;line-height:1.75;margin:9px 0 0;padding-top:9px;border-top:1px solid rgba(255,255,255,.08)}}
.mny-cmt b{{color:#e8eaee}}
/* 🆕 어디에도 안 걸린 새 테마 */
.nt-box{{background:#141922;border:1px solid #2a3342;border-left:3px solid #ef4444;border-radius:12px;padding:12px 14px;margin:10px 0 0}}
.nt-k{{font-size:11px;color:#8b93a0;font-weight:700;margin:0}}
.nt-t{{font-size:16px;font-weight:900;color:#f2f4f7;margin:3px 0 0;letter-spacing:-.02em}}
.nt-s{{font-size:11px;color:#8b93a0;margin:5px 0 0;line-height:1.6}}
.nt-chips{{display:flex;flex-wrap:wrap;gap:5px;margin:9px 0 0}}
.nt-chip{{font-size:10.5px;font-weight:800;padding:3px 8px;border-radius:20px;border:1px solid #2a3342;background:#0d1118}}
.nt-warn{{font-size:11px;color:#e0c060;margin:9px 0 0;line-height:1.65;background:#1a1610;border-radius:8px;padding:8px 10px}}
.nt-warn b{{color:#f0c65a}}
.nt-foot{{font-size:10px;color:#6f7784;margin:9px 0 0;line-height:1.6}}
.nt-foot b{{color:#9aa0aa}}
/* 오늘의 성적표 SCORE B */
.idx-card2.sc2wrap{{display:block}}
.sc2{{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1.12fr);gap:.6rem;align-items:center}}
.sc2-l{{min-width:0}}
.sc2-r{{min-width:0}}
.sc2-tagbox{{margin:.7rem 0 0;padding:.65rem .1rem 0;border-top:1px solid rgba(255,255,255,.07)}}
.sc2-tag{{display:inline-block;font-size:9.5px;font-weight:800;padding:.1rem .45rem;border-radius:20px;border:1px solid #2a3342}}
.sc2-txt{{font-size:10.5px;color:#8b93a0;margin:.28rem 0 0;line-height:1.6}}
.sc2-txt b{{color:#c9d0d9}}
.sc2-bot{{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:.55rem;
  align-items:center;margin:.6rem 0 0;padding:.55rem 0 0;
  border-top:1px solid rgba(255,255,255,.07)}}
.sc2-g{{display:flex;align-items:center;gap:.45rem;min-width:0}}
.sc2-g-l{{flex:0 0 auto}}
.sc2-g-r{{min-width:0}}
.sc2-g-v{{margin:0;font-size:13px;font-weight:900;letter-spacing:-.3px}}
.sc2-g-s{{margin:.1rem 0 0;font-size:9.5px;color:#8b93a0;white-space:nowrap}}
.sc2-g-s b{{color:#c9d0d9}}
.sc2-g-k{{display:inline-block;margin:.22rem 0 0;font-size:9px;font-weight:800;
  padding:.08rem .38rem;border-radius:20px;border:1px solid #2a3342;
  white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:100%}}
.sc2-spark{{flex:0 0 auto;text-align:center}}
.sc2-spark-t{{margin:0 0 .1rem;font-size:8.5px;color:#6f7784;font-weight:700;
  white-space:nowrap}}
.sc2-spark svg{{width:118px;height:52px;display:block}}
@media (max-width:400px){{
  .sc2-bot{{grid-template-columns:1fr;gap:.45rem}}
  .sc2-spark{{justify-self:start}}
}}
@media (max-width:359px){{.sc2{{grid-template-columns:1fr}}}}
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
  /* 좁은 화면에선 지수 요약을 아래로 내리고 가로 전체를 쓴다 */
  /* 🆕 2026-08-22 — 좁은 화면에서 지수를 게이지 아래로 내렸더니 "25·한파" 오른쪽이
     통째로 비었다. 점수와 지수를 **같은 줄**에 두고, 게이지 바만 다음 줄로 내린다. */
  .gz-numwrap{{flex:none}}
  /* 🆕 2026-08-22 — 전체 폭으로 늘려 좌우로 벌어지던 것을 고쳤다.
     블록을 **오른쪽으로 밀어 붙이고**(margin-left:auto) 위쪽 여백도 준다. */
  .gz-idx{{flex:none;margin-left:auto;margin-top:16px;padding-left:14px;border-left:none;
    padding-left:0;align-self:flex-start;order:0}}
  .gz-bodywrap{{order:3}}
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
  {승계배너}
  {build_core(해석.get('핵심편'), data, 해석)}

  <div class="deep-wrap">
  <nav class="cp-nav" id="cpnav" aria-label="심층편 바로가기">
    <button type="button" class="cp-chip" data-go="nv-flow">수급</button>
    <button type="button" class="cp-chip" data-go="nv-star">주인공</button>
    <button type="button" class="cp-chip" data-go="nv-sector">섹터</button>
    <button type="button" class="cp-chip" data-go="nv-radar">종목 레이더</button>
    <button type="button" class="cp-chip" data-go="nv-catch">포착 그 후</button>
    <button type="button" class="cp-chip" data-go="nv-score">채점표</button>
  </nav>
  {build_gauge(data.get('관제지수'), 오늘한줄평, 지수)}

  <!-- 🆕 2026-08-22 — 핵심편 헤더가 같은 성적표 카드를 쓰게 되면서 여기는 중복이 됐다.
       ⚠️ 예전엔 여기에 빈 <div id="score">만 남겨뒀는데, 「확인 ↓」을 누르면
          **아무것도 없는 자리**로 이동했다. id는 실제 내용이 있는
          핵심편 성적표 카드(.idx-grid)로 옮겼다. -->
  {hide("심층편성적표", f'''<p class="sec-label"><small>지수 + 수급</small>📊 오늘의 성적표</p>
  <div class="idx-grid">
    {build_score_card("KOSPI", 코, 코수)}
    {build_score_card("KOSDAQ", 닥, 닥수)}
  </div>''')}

  <!-- 🔴 2026-08-29 HO 지시 — 「오늘의 시장」 가림.
       [WHY] 핵심편 「오늘, 시장에 무슨 일이 있었냐면요」와 바로 아래
       「이슈 해부」가 **같은 질문**("오늘 무슨 일이 있었나")에 답하고 있어
       같은 얘기를 세 번 하는 구조였다. 심층편 독자는 핵심편을 먼저 읽고
       내려오므로, 과거(무슨 일이 있었나)는 핵심편이 전담한다.
       ⚠️ 해석글의 «오늘의_시장» 필드 자체는 그대로 둔다 — generate_report가
       계속 만들고, 되살리려면 이 hide()만 풀면 된다(원칙: 지우지 않는다). -->
  {hide("오늘의시장", f'<div class="today-market">💡 <b>오늘의 시장:</b> {오늘의시장}</div>')}

  <p class="sec-label"><small>핵심 이슈</small>🔬 이슈 해부 — 이 이슈가 어디까지 닿나</p>
  {build_issues(해석.get('핵심이슈'))}

  <p class="sec-label"><small>환율 · 유가 · 금리 · 금</small>🌏 바깥 날씨</p>
  <div class="macro-row">
    {build_macro_card((data.get('매크로') or {}).get('원달러환율'), (해석.get('매크로해설') or {}).get('환율',''), '원달러환율')}
    {build_macro_card((data.get('매크로') or {}).get('WTI유가'), (해석.get('매크로해설') or {}).get('유가',''), 'WTI유가')}
    {build_macro_card((data.get('매크로') or {}).get('미국채10년'), (해석.get('매크로해설') or {}).get('금리',''), '미국채10년')}
    {build_macro_card((data.get('매크로') or {}).get('국제금'), (해석.get('매크로해설') or {}).get('금',''), '국제금')}
  </div>

  <!-- ⚠️ 수급을 주인공보다 먼저 본다(2026-08-21 지시).
       "돈이 어디로 갔나"를 알고 나서 "어디가 떴나"를 봐야 인과가 맞다. -->
  <span class="nv-a" id="nv-flow"></span>
  <p class="sec-label" id="flow"><small>수급 관제신호</small>💰 큰돈은 어디로 갔나</p>
  <!-- 🆕 2026-08-22 — "확인 ↓"(#flow)도 같은 이유로 죽어 있었다. -->
  {build_flow_signal(data.get('파생'), data.get('지수수급'), 해석)}

  <span class="nv-a" id="nv-star"></span>
  <p class="sec-label"><small>오늘의 주인공</small>🏆 오늘의 주인공
    <span style="font-size:11px;font-weight:600;color:#8b93a0">· 상승률 + 거래대금 + 확산도 기준</span></p>
  {dev_note(f"전체 테마 중 등락률 상위 {(data.get('설정') or {}).get('주도섹터',{}).get('1차후보','?')}개를 1차 후보로 추림 → "
            f"{(data.get('설정') or {}).get('주도섹터',{}).get('가중치','?')} 점수로 재정렬 → "
            f"상위 {(data.get('설정') or {}).get('주도섹터',{}).get('선정수','?')}개. "
            f"단, 앞 카드와 종목이 {(data.get('설정') or {}).get('주도섹터',{}).get('중복제외기준','?')}개 이상 겹치면 제외")}
  {build_sectors(data.get('주도섹터'))}
  <!-- ⚠️ 접기 배경을 어둡게(#0f131a) 두니 주인공 카드(밝은 배경)와 따로 놀았다.
       (2026-08-19) → 카드와 같은 배경·테두리 변수를 쓰고, 금색 왼쪽 선으로만 구분한다. -->

  {_zone_trend_block}

  {hide("새테마", build_new_theme(data.get('계좌격자')))}

  <p class="sec-label"><small>뜨는 현장</small>📡 관제 레이더 — 오늘 관제탑에 가까워진 주인공</p>
  {hide("관제레이더", build_sector_radar())}

  {_mystock_deep}


  <span class="nv-a" id="nv-sector"></span>
  {hide("섹터지도", f'''<p class="sec-label"><small>내 자리</small>📊 섹터 지도</p>
  {build_account_grid(data.get('계좌격자'), data.get('주도섹터'))}''')}

  <p class="sec-label"><small>섹터 성적</small>📈 섹터 성적표</p>
  {build_sector_scoreboard()}

  <details style="margin:12px 0 0;padding:10px 12px;background:var(--bg);
    border:.5px solid var(--line);border-left:3px solid rgba(240,198,90,.55);
    border-radius:var(--rlg);box-shadow:0 1px 3px rgba(0,0,0,.03)">
    <summary style="font-size:11.5px;color:#a07d1f;font-weight:700;cursor:pointer;
      list-style:none">📖 오늘의 주인공과 섹터 성적표는 뭐가 다른가요?
      <span style="color:#6f7784;font-weight:600">(눌러서 펼치기)</span></summary>
    <p style="margin:6px 0 0;font-size:11px;color:#7d848f;line-height:1.65">
      <b style="color:#9aa0aa">오늘의 주인공</b>은 매일 바뀌는 <b>사건 현장</b>입니다.
      거래대금까지 보기 때문에 <b>돈이 몰린 곳</b>을 잡습니다.<br>
      <b style="color:#2c3340">섹터 성적표</b>는 안 바뀌는 <b>주소</b>입니다. 항상 같은 칸이라
      어제·지난달과 비교됩니다.<br>
      그래서 <b style="color:#2c3340">두 곳의 순위가 다를 수 있습니다.</b>
      성적표에선 강한데 여기 없다면 — <b style="color:#a07d1f">올랐지만 돈은 안 붙은 상승</b>입니다.
    </p></details>

  {hide("섹터크기별", f'''<p class="sec-label"><small>섹터 성적</small>📐 섹터 크기별 — 누가 이끌었나?</p>
  {build_slope_chart(data.get('계좌격자'))}''')}

  <p class="sec-label"><small>순환 분석</small>🗺️ 섹터 순위 타일 — 주도권이 어떻게 돌았나</p>
  {build_sector_map()}

  <p class="sec-label"><small>순환 분석</small>🔮 돌아올 섹터 — 다음 순번은</p>
  {build_return_sector()}

  {hide("군중나침반", f'''<p class="sec-label"><small>시장 심리</small>🧭 군중 나침반</p>
  {build_crowd_compass(data.get('신용잔고'))}''')}

  <!-- ⚠️ 프로의 시선·판단은 수급·심리를 다 본 **뒤에** 온다(2026-08-20 지시).
       근거(수급·나침반)를 먼저 깔고 그 위에서 판단을 말해야 설득이 된다. -->
  <p class="sec-label"><small>프로의 시선</small>🔍 남들이 놓친 자리</p>
  {build_insight(프로의시선)}
  {build_divergence_block(data, 해석)}

  <!-- 🆕 2026-08-25 — 심층편에서는 카드 기능을 한 번만 따로 설명한다.
       핵심편은 종목명 옆 «▾ 기업분석» 배지로만 알리고, 여기서는 뭐가 나오는지까지. -->
  <!-- 🆕 2026-08-26 HO 지시 — 여기 있던 「이 종목들이 왜 여기 떴냐면요」와
       「종목 이름을 누르면…」 안내를 삭제했다.
       [WHY] 왜 떴는지는 **불난 자리 코너 안**(조건 설명 바로 밑)이 제자리다.
             레이더를 보기도 전에 설명부터 나오면 순서가 거꾸로다.
       🔴 2026-08-26 사고 — 처음 지울 때 <div class="sc-guide"> **여는 태그만
          남기고** 안쪽 내용만 지웠다. 닫는 태그가 없으니 그 뒤 심층편 전체가
          어두운 박스(#141922) 안으로 들어갔고, 제목(sec-label)이 어두운 글자라
          「오늘 불난 자리」부터 마지막 교신까지 **8개 제목이 통째로 안 보였다.**
          ⚠️ 블록을 지울 때는 **여는 태그와 닫는 태그를 같이** 지운다. -->
  <span class="nv-a" id="nv-radar"></span>
  <p class="sec-label" id="radar"><small>실제 강세 레이더</small><span class="cp-flame">🔥</span> 오늘 불난 자리</p>
  {build_radar(data.get('강세레이더'), data.get('설정'))}

  <p class="sec-label" id="acc"><small>매집 레이더</small><span class="cp-turtle">🐢</span> 조용히 모으는 손</p>
  {build_accumulation(data.get('매집레이더'), data.get('설정'))}

  <span class="nv-a" id="nv-catch"></span>
  <p class="sec-label"><small>포착 그 후</small>🛬 레이더는 잘 잡았나</p>
  {_catch_after_block}
  {hide("포착성적", f'''{build_capture_paths()}''')}

  {hide("그들은뭐라했나", f'''<p class="sec-label"><small>마감 브리핑</small>📺 그들은 뭐라 했나</p>
  {build_briefings(해석.get('마감브리핑'))}''')}

  <p class="sec-label"><small>오늘의 중요 공시</small>📋 놓치면 아까운 공시</p>
  <div class="disc-box">
    {build_disclosures(data.get('공시'), 해석.get('공시해설'))}
    <p class="disc-note" style="margin-top:.6rem;font-size:9.5px">별점은 다음 거래일 변동 가능성 참고용이며 방향 예측이 아닙니다.</p>
  </div>

  <p class="sec-label"><small>챙겨볼 뉴스</small>🔥 {news_title(해석.get('핵심뉴스'))}</p>
  {build_news(해석.get('핵심뉴스'))}

  <span class="nv-a" id="nv-score"></span>
  {f'<p class="sec-label"><small>어제의 채점표</small>✅ 어제 예고, 오늘 결과는</p>{build_scorecard(해석.get("채점표"))}' if 해석.get('채점표') else ''}

  {build_story_bridge()}

  <!-- 🆕 2026-08-22 — 관전포인트(예보)를 핵심편 맨 끝으로 옮겼다. 여기는 중복이라 가린다.
       id="watch"는 다른 코너에서 거는 앵커라 자리는 남겨 둔다. -->
  <div id="watch"></div>
  {hide("심층편관전포인트", f'''<p class="sec-label"><small>{_NEXT_LABEL}의 관전 포인트</small>🗼 {_NEXT_LABEL} 이것만 보세요</p>
  {build_watchpoints(해석.get('관전포인트'), _NEXT)}''')}

  <p class="sec-label"><small>오늘의 공부</small>📚 오늘 하나만 배운다면</p>
  {build_study(오늘의공부)}

  <!-- 🗼 마지막 교신 — 하루를 닫고 내일로 넘기는 자리 (2026-08-22) -->
  {build_closing(해석, 날짜)}

  </div><!-- /deep-wrap -->

  {build_archive()}

  <p class="foot">데이터: {날짜} 기준, 한국거래소·DART·네이버 증권 종합 · 관제지수는 등락률·수급·시장폭을 근거로 한 자체 참고 지표입니다 · 별점·예측은 참고용이며 매수·매도 신호가 아닙니다 · 본 브리핑은 정보 제공 목적으로, 투자 권유가 아니며 투자 판단과 책임은 투자자 본인에게 있습니다. <span style="opacity:.5">[{SCRIPT_VERSION}]</span></p>
</div>
<script>
/* 🆕 심층편 칩 네비 — 인라인 onclick을 쓰지 않는다.
   파이썬 f-string을 거치며 따옴표 이스케이프가 풀려 JS 전체가 죽은 사고가 있었다. */
(function(){{
  var nav=document.getElementById('cpnav');
  if(!nav) return;
  var chips=[].slice.call(nav.querySelectorAll('.cp-chip'));
  chips.forEach(function(b){{
    b.addEventListener('click',function(){{
      var t=document.getElementById(b.getAttribute('data-go'));
      if(t) t.scrollIntoView({{behavior:'smooth',block:'start'}});
    }});
  }});
  /* 지금 어느 코너인지 칩에 표시한다 — 위치 감각이 없으면 네비가 있어도
     "내가 어디쯤인지"를 모른다. 활성 칩이 바 밖이면 가운데로 끌어온다. */
  var marks=chips.map(function(b){{return document.getElementById(b.getAttribute('data-go'));}});
  var tick=false;
  function sync(){{
    tick=false;
    var cur=-1;
    for(var i=0;i<marks.length;i++){{
      if(marks[i] && marks[i].getBoundingClientRect().top<=72) cur=i;
    }}
    chips.forEach(function(b,i){{
      var was=b.classList.contains('on');
      b.classList.toggle('on',i===cur);
      if(i===cur && !was && nav.scrollWidth>nav.clientWidth){{
        nav.scrollTo({{left:Math.max(0,b.offsetLeft-(nav.clientWidth-b.offsetWidth)/2),
                      behavior:'smooth'}});
      }}
    }});
  }}
  window.addEventListener('scroll',function(){{
    if(!tick){{tick=true;window.requestAnimationFrame(sync);}}
  }},{{passive:true}});
  sync();
}})();
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
