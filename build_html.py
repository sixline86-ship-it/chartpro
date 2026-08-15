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

SCRIPT_VERSION = "v2026.08.14-k4"   # ⬅ 버전 표시
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
    return f'''
    <div class="sector-card">
      <div class="sc-head {head_cls}">
        <div class="sc-name-row">{theme_label(a['테마명'])}
          <span class="sc-chg {badge_cls}">{et_s}</span></div>
        <p class="sc-score">주도력 {점수}점</p>
        {f'<p class="sc-strline">{강도배지}</p>' if 강도배지 else ''}
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
        return '<p class="smut">오늘 수집된 주도 섹터 데이터가 없습니다.</p>'
    앞2 = 주도섹터[:2]
    뒤4 = 주도섹터[2:6]
    앞 = "".join(one_sector_card(a) for a in 앞2)
    뒤 = "".join(one_sector_card(a) for a in 뒤4)
    더보기 = ""
    if 뒤4:
        더보기 = f'''
  <div class="hidden-block" id="moreSectors"><div class="sector-grid">{뒤}</div></div>
  <button class="more-btn" onclick="toggleMore('moreSectors',this,'▾ 주도 섹터 더보기 ({len(뒤4)}개)')">▾ 주도 섹터 더보기 ({len(뒤4)}개)</button>'''
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
    #   색 규칙: 지수는 HTS식(상승 빨강 / 하락 파랑),
    #            수급은 매수 초록 / 매도 보라(#a78bfa) — 지수 색과 겹치지 않게.
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
            # v: 억원. 매수(+)=초록, 매도(-)=보라. ±3조(30,000억)를 최대폭으로.
            if v is None:
                return (f'<div class="ix-bar-row"><span class="ix-bn">{nm}</span>'
                        f'<div class="ix-bt"><span class="ix-bz"></span></div>'
                        f'<span class="ix-bv flat">—<small>&nbsp;</small></span></div>')
            매수 = v >= 0
            w = min(abs(v) / 30000.0, 1.0) * 50.0
            색 = ("linear-gradient(90deg,#4ade80,#2a9d5a)" if 매수
                  else "linear-gradient(270deg,#a78bfa,#7c5cd6)")
            side = "left" if 매수 else "right"
            vcls = "buy" if 매수 else "sellv"
            return (f'<div class="ix-bar-row"><span class="ix-bn">{nm}</span>'
                    f'<div class="ix-bt"><span class="ix-bz"></span>'
                    f'<div class="ix-bf" style="{side}:50%;width:{w:.1f}%;background:{색}"></div></div>'
                    f'<span class="ix-bv {vcls}">{_flow_amt(v)}<small>{배지}</small></span></div>')

        수급블록 = (f'<div class="ix-div"></div><p class="ix-grouplbl">수급 (±3조 · 매수 초록 / 매도 보라)</p>'
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
        flowdot = ('<div class="h-item"><span class="h-dot" style="background:#4ade80"></span>'
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


def _grid_cell_color(v):
    """등락률 → 배경색. 지수 관례(빨강=상승/파랑=하락)를 따른다.
    색 진하기는 절대값 구간으로 4단계. 색만으로 구분하지 않도록 숫자를 항상 함께 쓴다."""
    if v is None:
        return "transparent"
    a = abs(v)
    op = 0.55 if a >= 3 else (0.42 if a >= 2 else (0.28 if a >= 1 else (0.18 if a >= 0.5 else 0.10)))
    hexcol = "#e24b4a" if v >= 0 else "#378add"
    return f"{hexcol}{int(op*255):02x}"


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


def build_account_grid(격자):
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
    콜 = ('<colgroup><col style="width:29%"><col style="width:17.75%">'
          '<col style="width:17.75%"><col style="width:17.75%"><col style="width:17.75%"></colgroup>')

    def _짧은기준(층):
        """'301위 이하' 같은 긴 라벨은 좁은 칸에서 옆 칸과 겹친다 → 숫자만 남긴다."""
        t = str(기준.get(층, "")).strip()
        t = t.replace("위 이하", "~").replace("위 이상", "~").replace("위", "")
        return t.replace(" ", "")
    머리 = ('<tr><th style="text-align:left;padding:6px 3px 6px 2px;font-size:12px;'
            'color:#9aa0aa;font-weight:600">테마</th>'
            + "".join(f'<th style="padding:6px 1px;font-size:11.5px;color:#9aa0aa;font-weight:600;text-align:center">'
                      f'{층}<br><span style="font-size:9.5px;opacity:.7;white-space:nowrap">'
                      f'{_짧은기준(층)}</span></th>'
                      for 층 in ("대형", "중형", "소형"))
            + '<th style="padding:6px 1px;font-size:12px;color:#e8eaee;font-weight:700;text-align:center">전체</th></tr>')

    몸 = []
    for r in 행들:
        칸들 = []
        for 층 in ("대형", "중형", "소형"):
            c = (r.get("칸") or {}).get(층) or {}
            v = c.get("등락률")
            if v is None:
                칸들.append('<td style="padding:7px 2px;text-align:center;font-size:12px;'
                            'color:#6b7280;background:#ffffff08;border-radius:4px">—</td>')
            else:
                칸들.append(f'<td style="padding:7px 2px;text-align:center;font-size:12.5px;'
                            f'color:#e8eaee;background:{_grid_cell_color(v)};border-radius:4px">'
                            f'{v:+.1f}</td>')
        전 = r.get("전체")
        if isinstance(전, (int, float)):
            전칸 = (f'<td style="padding:7px 2px;text-align:center;font-size:12.5px;font-weight:700;'
                   f'color:#e8eaee;background:{_grid_cell_color(전)};border-radius:4px">{전:+.1f}</td>')
        else:
            전칸 = '<td style="padding:7px 2px;text-align:center;font-size:12px;color:#6b7280">—</td>'
        # 모바일(가로 360px)에서 표가 잘리지 않게: 테마명은 '·' 뒤에서 줄바꿈을 허용한다.
        #   예) '인터넷·게임·엔터' → '인터넷·' / '게임·' / '엔터' 로 접힘
        #   nowrap을 유지하면 이 한 칸이 표 전체 폭을 밀어내 가로 스크롤이 생긴다.
        테마명 = str(r.get("테마", "")).replace("·", "·<wbr>")
        몸.append('<tr>'
                  f'<td style="padding:7px 3px 7px 2px;font-size:11.5px;color:#d5d9e0;'
                  f'line-height:1.3;word-break:keep-all;overflow-wrap:anywhere">{테마명}</td>'
                  + "".join(칸들) + 전칸 + '</tr>')

    # ── 크기 전체 + 20일 스파크라인 3줄 (수위 항로를 여기에 흡수) ──
    이력 = _load_strata_history()
    스파크 = []
    for 층 in ("대형", "중형", "소형"):
        v = 크기.get(층)
        sv = _spark_svg([r.get(층) for r in 이력])
        스파크.append(
            f'<div style="display:flex;align-items:center;gap:8px;min-width:0">'
            f'<span style="font-size:12.5px;color:#9aa0aa;width:32px;flex:none">{층}</span>'
            f'<span style="font-size:14px;font-weight:700;width:52px;flex:none;'
            f'color:{"#ff6b4a" if (v or 0) >= 0 else "#5b9bff"}">'
            f'{v:+.2f}</span>{sv}</div>' if isinstance(v, (int, float)) else "")

    프리 = ""
    if isinstance(프리미엄, (int, float)):
        추이 = [r.get("크기프리미엄") for r in 이력 if isinstance(r.get("크기프리미엄"), (int, float))]
        평균 = (sum(추이) / len(추이)) if len(추이) >= 5 else None
        비교 = (f' · 최근 {len(추이)}일 평균 {평균:+.1f}%p' if 평균 is not None else " · 추이 축적 중")
        방향 = "대형 쏠림" if 프리미엄 > 0 else "소형 우위"
        프리 = (f'<p style="margin:10px 0 0;font-size:12.5px;color:#c9ced6">'
                f'크기 프리미엄 <b style="color:#f0c65a">{프리미엄:+.2f}%p</b> '
                f'({방향}){비교}</p>')

    return ('<div style="background:#161a22;border:1px solid #232a36;border-radius:14px;'
            'padding:14px 14px 12px;margin:0 0 14px">'
            '<p style="margin:0 0 2px;font-size:12px;color:#8b93a0;letter-spacing:.02em">내 계좌 좌표</p>'
            '<p style="margin:0 0 10px;font-size:17.5px;font-weight:800;color:#f2f4f7">'
            '오늘 내 종목은 어디에 있었나</p>'
            # min-width를 없애 화면 폭에 맞춘다 — 모바일에서 한눈에 다 보이게.
            f'<table style="width:100%;border-collapse:separate;border-spacing:2px;'
            f'table-layout:fixed">{콜}{머리}{"".join(몸)}</table>'
            '<div style="margin-top:12px;padding-top:10px;border-top:1px solid #232a36;'
            'display:flex;flex-direction:column;gap:5px">'
            + "".join(스파크) + '</div>' + 프리
            + '<div style="margin:10px 0 0;padding:9px 10px;background:#0f131a;'
              'border-radius:8px;border:1px solid #1e2531">'
              '<p style="margin:0 0 5px;font-size:11.5px;color:#8b93a0;font-weight:700">'
              '📖 이렇게 보세요</p>'
              '<p style="margin:0;font-size:11px;color:#7d848f;line-height:1.65">'
              '<b style="color:#9aa0aa">가로로 읽으면</b> — 같은 테마라도 대형·중형·소형 중 '
              '어디가 올랐는지 보입니다. 내 종목 크기 칸이 빨간색이면 그 흐름에 올라탄 것입니다.<br>'
              '<b style="color:#9aa0aa">세로로 읽으면</b> — 오늘 어느 테마가 주인공이었는지 보입니다. '
              '맨 오른쪽 <b style="color:#9aa0aa">전체</b> 칸이 그 테마의 평균입니다.<br>'
              '<b style="color:#9aa0aa">색</b> — 빨강은 오른 칸, 파랑은 내린 칸이고 진할수록 폭이 큽니다.<br>'
              '<b style="color:#9aa0aa">맨 아래 가로선</b> — 대형·중형·소형의 최근 20거래일 추이입니다.'
              '</p></div>'
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
            f'<p style="margin:0 0 9px;font-size:13.5px;font-weight:700;color:#f0c65a">'
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
    if len(vals) < 4:
        return ""
    최근 = vals[-4:]
    오늘 = 최근[-1]
    차분 = [최근[i + 1] - 최근[i] for i in range(len(최근) - 1)]
    오름 = sum(1 for d in 차분 if d > 0)
    내림 = sum(1 for d in 차분 if d < 0)
    어제 = 최근[-2]

    if 오늘 > 0 and 어제 <= 0:
        상태, 색, 설명 = "매수 전환", "#4ade80", "팔던 흐름이 사는 쪽으로 돌아섰습니다"
    elif 오늘 < 0 and 어제 >= 0:
        상태, 색, 설명 = "매도 전환", "#a78bfa", "사던 흐름이 파는 쪽으로 돌아섰습니다"
    elif 오늘 > 0 and 오름 >= 2:
        상태, 색, 설명 = "매수 가속", "#4ade80", "사는 힘이 점점 세지고 있습니다"
    elif 오늘 > 0 and 내림 >= 2:
        상태, 색, 설명 = "매수 감속", "#86efac", "여전히 사지만 힘은 빠지는 중입니다"
    elif 오늘 < 0 and 내림 >= 2:
        상태, 색, 설명 = "매도 가속", "#a78bfa", "파는 힘이 점점 세지고 있습니다"
    elif 오늘 < 0 and 오름 >= 2:
        상태, 색, 설명 = "매도 감속", "#c4b5fd", "여전히 팔지만 힘은 빠지는 중입니다"
    else:
        상태, 색, 설명 = "속도 유지", "#9aa0aa", "흐름의 세기에 큰 변화가 없습니다"

    막대 = []
    최대 = max(abs(v) for v in 최근) or 1
    for v in 최근:
        h = max(4, int(abs(v) / 최대 * 34))
        c = "#4ade80" if v >= 0 else "#a78bfa"
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
            f'<p style="margin:4px 0 0;font-size:11.5px;color:#6f7784">최근 4거래일 실탄 {수치}</p>'
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
    for nm in 이름들:
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
        점 += (f'<circle cx="{nx:.0f}" cy="{ny:.0f}" r="7" fill="{색}" '
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
        변동행.append(
            f'<div style="display:flex;justify-content:space-between;gap:8px;'
            f'padding:4px 0;border-bottom:1px solid #1b212c">'
            f'<span style="font-size:11.5px;color:#c9ced6">{re.sub(r"[（(].*", "", nm).strip()[:9]}{신규}</span>'
            f'<span style="font-size:11.5px;font-weight:700;color:{c};white-space:nowrap">{화}</span></div>')
    변동표 = ('<div style="margin:10px 0 0;padding-top:8px;border-top:1px solid #232a36">'
              '<p style="margin:0 0 4px;font-size:11.5px;color:#8b93a0;font-weight:700">'
              '📊 어제 대비 움직임</p>' + "".join(변동행) + '</div>') if 변동행 else ""

    # ⚠️ 모든 섹터가 제자리인 날(휴장 등 데이터 동일)에 "정유 65 → 65"가
    #    접근·이탈 양쪽에 뜨면 의미 없는 정보다. 실제 이동이 있을 때만 표시한다.
    if 최대접근[1] > 0.5:
        접근HTML = (f'<p style="margin:0;font-size:11.5px;color:#8b93a0">가장 빠르게 접근</p>'
                    f'<p style="margin:2px 0 10px;font-size:13.5px;font-weight:700;color:#4ade80">'
                    f'{최대접근[0]}</p>')
    else:
        접근HTML = ('<p style="margin:0;font-size:11.5px;color:#8b93a0">가장 빠르게 접근</p>'
                    '<p style="margin:2px 0 10px;font-size:13px;font-weight:700;color:#6f7784">'
                    '오늘은 없음</p>')
    if 최대이탈[1] > 0.5:
        이탈HTML = (f'<p style="margin:0;font-size:11.5px;color:#8b93a0">가장 빠르게 이탈</p>'
                    f'<p style="margin:2px 0 0;font-size:13.5px;font-weight:700;color:#a78bfa">'
                    f'{최대이탈[0]}</p>')
    else:
        이탈HTML = ('<p style="margin:0;font-size:11.5px;color:#8b93a0">가장 빠르게 이탈</p>'
                    '<p style="margin:2px 0 0;font-size:13px;font-weight:700;color:#6f7784">'
                    '오늘은 없음</p>')
    패널 = 접근HTML + 이탈HTML

    return ('<div style="background:#141922;border:1px solid #232a36;border-radius:12px;'
            'padding:12px 14px;margin:10px 0 0">'
            '<p style="margin:0 0 2px;font-size:11.5px;color:#8b93a0">관제 레이더</p>'
            '<p style="margin:0 0 8px;font-size:16px;font-weight:800;color:#f2f4f7">'
            '오늘 관제탑에 가까워진 섹터</p>'
            '<div style="display:flex;flex-wrap:wrap;gap:10px;align-items:center">'
            f'<svg width="350" height="300" viewBox="0 25 350 300" style="flex:none;max-width:100%">'
            f'{링}{축}<circle cx="{cx}" cy="{cy}" r="4" fill="#f0c65a"/>'
            f'{자취}{점}{라벨}</svg>'
            f'<div style="flex:1;min-width:150px">{패널}</div></div>'
            + 변동표
            + '<div style="margin:10px 0 0;padding:9px 10px;background:#0f131a;'
              'border-radius:8px;border:1px solid #1e2531">'
              '<p style="margin:0 0 5px;font-size:11.5px;color:#8b93a0;font-weight:700">'
              '📖 이렇게 보세요</p>'
              '<p style="margin:0;font-size:11px;color:#7d848f;line-height:1.65">'
              '<b style="color:#9aa0aa">가운데 금색 점이 관제탑</b>입니다. 섹터 점이 여기에 '
              '<b style="color:#9aa0aa">가까울수록 오늘 시장을 세게 끌고 갔다</b>는 뜻이고, '
              '바깥에 있을수록 뒤로 밀렸다는 뜻입니다.<br>'
              '<b style="color:#4ade80">초록 ▲</b> 어제보다 안쪽으로 들어옴 (달아오르는 중) · '
              '<b style="color:#a78bfa">보라 ▼</b> 바깥으로 밀림 (식는 중) · '
              '<b style="color:#f0c65a">금색 =</b> 어제와 비슷한 자리<br>'
              '<b style="color:#9aa0aa">속 빈 점 → 꽉 찬 점</b>으로 이어진 선이 '
              '어제 자리에서 오늘 자리까지 움직인 거리입니다. 선이 길수록 하루 사이 변화가 큽니다.'
              '</p></div>'
            + '<p style="margin:8px 0 0;font-size:11px;color:#6f7784;line-height:1.5">'
            '어제 주도 6위 밖이던 섹터는 바깥에서 출발한 것으로 표시됩니다</p></div>')


# ── 3. 경사선 (테마별 대형→중형→소형) ────────────────────────
def build_slope_chart(격자):
    """대형에서 소형으로 가는 경사선. 열 줄이 모두 우하향이면 '크기가 수익을 갈랐다'는 뜻."""
    행들 = [r for r in (격자 or {}).get("행", [])
            if all(isinstance((r.get("칸") or {}).get(t, {}).get("등락률"), (int, float))
                   for t in ("대형", "중형", "소형"))]
    if len(행들) < 4:
        return ""
    행들 = sorted(행들, key=lambda r: r["전체"], reverse=True)
    강조 = 행들[:3] + 행들[-3:]
    나머지 = 행들[3:-3]

    vs = [v for r in 행들 for v in (r["칸"]["대형"]["등락률"], r["칸"]["중형"]["등락률"],
                                    r["칸"]["소형"]["등락률"])]
    lo, hi = min(vs), max(vs)
    rng = (hi - lo) or 1.0
    W, H, T, B = 520, 300, 40, 40
    X = {"대형": 150, "중형": 300, "소형": 450}
    def Y(v): return T + (hi - v) / rng * (H - T - B)

    선 = ""
    for r in 나머지:
        p = " ".join(f'{X[t]},{Y(r["칸"][t]["등락률"]):.0f}' for t in ("대형", "중형", "소형"))
        선 += f'<polyline points="{p}" fill="none" stroke="#4a5260" stroke-width="1.5" opacity=".55"/>'
    for i, r in enumerate(행들[:3] + 행들[-3:]):
        c = "#ff6b4a" if i < 3 else "#5b9bff"
        p = " ".join(f'{X[t]},{Y(r["칸"][t]["등락률"]):.0f}' for t in ("대형", "중형", "소형"))
        선 += f'<polyline points="{p}" fill="none" stroke="{c}" stroke-width="2.5" stroke-linejoin="round"/>'
        for t in ("대형", "중형", "소형"):
            선 += f'<circle cx="{X[t]}" cy="{Y(r["칸"][t]["등락률"]):.0f}" r="4" fill="{c}"/>'
        y0 = Y(r["칸"]["대형"]["등락률"])
        선 += (f'<text x="140" y="{y0+4:.0f}" text-anchor="end" font-size="12" fill="#c9ced6">'
               f'{r["테마"][:7]}</text>')

    축 = "".join(f'<line x1="{X[t]}" y1="{T-10}" x2="{X[t]}" y2="{H-B+10}" stroke="#232a36" '
                 f'stroke-width="1"/><text x="{X[t]}" y="{T-18}" text-anchor="middle" '
                 f'font-size="12" fill="#9aa0aa">{t}</text>' for t in X)
    영 = (f'<line x1="140" y1="{Y(0):.0f}" x2="470" y2="{Y(0):.0f}" stroke="#3a4150" '
          f'stroke-width="1" stroke-dasharray="4 4"/>') if lo < 0 < hi else ""

    하향 = sum(1 for r in 행들 if r["칸"]["대형"]["등락률"] > r["칸"]["소형"]["등락률"])
    결론 = (f'{len(행들)}개 테마 중 <b style="color:#f0c65a">{하향}개</b>가 우하향 — '
            + ("오늘은 테마보다 크기가 수익을 갈랐습니다" if 하향 >= len(행들) * 0.7
               else "테마별로 크기 효과가 갈렸습니다"))

    return ('<div style="background:#141922;border:1px solid #232a36;border-radius:12px;'
            'padding:12px 14px;margin:10px 0 0">'
            '<p style="margin:0 0 2px;font-size:11.5px;color:#8b93a0">크기 경사선</p>'
            '<p style="margin:0 0 8px;font-size:16px;font-weight:800;color:#f2f4f7">'
            '대형에서 소형으로 갈 때 무슨 일이</p>'
            '<div style="overflow-x:auto">'
            f'<svg width="520" height="{H}" viewBox="0 0 {W} {H}" style="min-width:480px">'
            f'{축}{영}{선}</svg></div>'
            f'<p style="margin:6px 0 0;font-size:12.5px;color:#c9ced6">{결론}</p>'
            '<p style="margin:4px 0 0;font-size:11.5px;color:#6f7784">'
            '빨강 = 상위 3테마 · 파랑 = 하위 3테마 · 회색 = 나머지</p></div>')


# ── 4. 포착 항로 (레이더 성적) ───────────────────────────────
def build_capture_path(개월=1):
    """강세 레이더가 포착한 종목들이 그 뒤 실제로 걸어간 길.

    ⚠️ 성과 표시가 아니라 **지표 성능 공시**다. 최저 사례도 반드시 함께 낸다.
    """
    일수 = 22 if 개월 == 1 else 66
    파일들 = sorted(alist(r"data_\d{8}\.json"))[-일수:]
    if len(파일들) < 3:
        return ""
    쌍 = {}          # (종목,포착일) → (경과, 이후등락) 최신값
    for f in 파일들:
        try:
            with open(apath(f), encoding="utf-8") as fp:
                tr = ((json.load(fp).get("강세레이더") or {}).get("추적")) or []
        except Exception:
            continue
        for t in tr:
            g, r = t.get("경과"), t.get("이후등락")
            if isinstance(g, int) and isinstance(r, (int, float)):
                쌍[(t.get("종목명"), t.get("포착일"))] = (g, r, t.get("종목명"))
    if len(쌍) < 5:
        return ""

    별 = {}
    for (g, r, nm) in 쌍.values():
        별.setdefault(g, []).append(r)
    최종 = [(v[1], v[2]) for v in 쌍.values()]
    평균 = sum(r for r, _ in 최종) / len(최종)
    승률 = sum(1 for r, _ in 최종 if r > 0) / len(최종) * 100
    중앙 = sorted(r for r, _ in 최종)[len(최종) // 2]
    최고 = max(최종, key=lambda x: x[0])
    최저 = min(최종, key=lambda x: x[0])

    Ds = sorted(d for d in 별 if d >= 0)
    if len(Ds) < 3:
        return ""
    곡선 = [(d, sum(별[d]) / len(별[d])) for d in Ds]
    vs = [v for _, v in 곡선]
    lo, hi = min(vs + [0]), max(vs + [0])
    rng = (hi - lo) or 1.0
    W, H = 520, 200
    def PX(d): return 60 + (d - Ds[0]) / max(1, (Ds[-1] - Ds[0])) * 420
    def PY(v): return 30 + (hi - v) / rng * 130

    선 = " ".join(f"{PX(d):.0f},{PY(v):.0f}" for d, v in 곡선)
    영 = f'<line x1="55" y1="{PY(0):.0f}" x2="485" y2="{PY(0):.0f}" stroke="#3a4150" stroke-dasharray="4 4"/>'
    눈 = "".join(f'<text x="{PX(d):.0f}" y="185" text-anchor="middle" font-size="11" '
                 f'fill="#6f7784">D+{d}</text>' for d in Ds[::max(1, len(Ds)//5)])

    라벨 = "1개월" if 개월 == 1 else "3개월"
    return ('<div style="background:#141922;border:1px solid #232a36;border-radius:12px;'
            'padding:12px 14px;margin:10px 0 0">'
            '<p style="margin:0 0 2px;font-size:11.5px;color:#8b93a0">포착 항로</p>'
            f'<p style="margin:0 0 8px;font-size:16px;font-weight:800;color:#f2f4f7">'
            f'레이더가 잡은 종목들, 그 뒤 {라벨}</p>'
            '<div style="overflow-x:auto">'
            f'<svg width="520" height="{H}" viewBox="0 0 {W} {H}" style="min-width:480px">{영}'
            f'<polyline points="{선}" fill="none" stroke="#d85a30" stroke-width="3" '
            f'stroke-linejoin="round"/>{눈}</svg></div>'
            f'<p style="margin:6px 0 0;font-size:13px;color:#e8eaee">'
            f'포착 {len(최종)}종목 · 평균 <b>{평균:+.1f}%</b> · 중앙값 {중앙:+.1f}% · 승률 {승률:.0f}%</p>'
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
        내일대응 = (f'<div class="tmr"><p class="tmr-h">🌅 내일장, 이것만 기억하세요</p>'
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
    격자블록 = build_account_grid(data.get("계좌격자")) + build_sector_radar()
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

    질문3 = "폭넓게 샀나?" if 방향양 else "폭넓게 팔았나?"
    if 비중상태 == "없음":
        행들.append(체크행(("h", "—"), 질문3, "비차익 ÷ 실탄",
                        "오늘은 프로그램매매(비차익) 데이터를 확보하지 못해 폭은 확인 불가입니다.",
                        "—", "mid", "폭"))
    elif 비중상태 == "보류":
        행들.append(체크행(("h", "—"), 질문3, "비차익 ÷ 실탄",
                        f"오늘 실탄이 <b>{_flow_amt(실탄)}</b>으로 작아, 비율로 나누면 값이 크게 튑니다. "
                        f"오늘은 폭 판정을 보류합니다.",
                        "판정 보류", "mid", f"비차익 {_flow_amt(비차익)}"))
    elif 비중상태 == "역방향":
        행들.append(체크행(("h", "△"), 질문3, "비차익 ÷ 실탄",
                        f"실탄은 {'유입' if 방향양 else '유출'}인데 바스켓은 <b>반대로 "
                        f"{_flow_amt(비차익)}</b>입니다. 지수 전체와 개별 종목이 서로 다른 방향으로 "
                        f"움직인 날입니다.", "반대", "mid", f"비차익 {_flow_amt(비차익)}"))
    elif 비중상태 == "초과":
        행들.append(체크행(("h", "△"), 질문3, "비차익 ÷ 실탄",
                        f"바스켓 {_flow_amt(비차익)}이 실탄 {_flow_amt(실탄)}보다 <b>커서 "
                        f"{비중*100:.0f}%</b>가 나왔습니다. 오류가 아니라 <b>한쪽은 지수를 통째로 "
                        f"{'사고' if 방향양 else '팔고'} 다른 쪽은 개별 종목을 반대로 매매해 "
                        f"서로 상계된</b> 상태입니다.",
                        f"{비중*100:.0f}%", "mid", f"비차익 {_flow_amt(비차익)}"))
    else:
        p = 비중 * 100
        매매 = "매수" if 방향양 else "매도"
        if p >= 90:
            답3 = (f"실탄의 <b>{p:.0f}%</b> — 사실상 <b>전부 바스켓</b>입니다. 종목을 고른 게 아니라 "
                  f"코스피200을 통째로 {'담은' if 방향양 else '내놓은'} 날입니다.")
            아이 = ("y", "✓")
        elif p >= 65:
            답3 = (f"실탄의 <b>{p:.0f}%</b>가 시장 전체(바스켓) {매매} — 몇 종목이 아니라 "
                  f"<b>한국 시장 자체</b>{'를 산' if 방향양 else '에서 나간'} 겁니다.")
            아이 = ("y", "✓")
        elif p >= FLOW_바스켓선*100:
            답3 = (f"실탄의 <b>{p:.0f}%</b>가 바스켓 {매매}입니다. 지수 전체와 개별 종목이 "
                  f"<b>절반씩 섞인</b> 흐름입니다.")
            아이 = ("y", "✓")
        elif p >= 20:
            답3 = (f"바스켓 비중 <b>{p:.0f}%</b> — 시장 전체보다 <b>특정 종목·업종 위주</b>의 "
                  f"선별 {매매}에 가깝습니다.")
            아이 = ("h", "△")
        else:
            답3 = (f"바스켓 비중 <b>{p:.0f}%</b>로 거의 없습니다. 지수가 아니라 "
                  f"<b>골라잡은 종목</b>에 돈이 오간 날입니다.")
            아이 = ("h", "△")
        행들.append(체크행(아이, 질문3, "비차익 ÷ 실탄",
                        답3, f"{p:.0f}%", vc if p >= FLOW_바스켓선*100 else "mid",
                        f"비차익 {_flow_amt(비차익)}"))

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

    return f'''
  <div class="fs-box">
    <div class="fs-verdict">
      <div class="fs-ico {vc}"><svg width="26" height="26" viewBox="0 0 26 26"><path d="M13 {'22 V6 M13 6 l-7 7 M13 6 l7 7' if 방향양 else '4 V20 M13 20 l-7 -7 M13 20 l7 -7'}" stroke="{'#ff8a6e' if 방향양 else '#7fa8e8'}" stroke-width="3.6" stroke-linecap="round" stroke-linejoin="round" fill="none"/></svg></div>
      <div class="fs-main">
        <p class="fs-k">오늘의 실탄 (외국인+기관이 실제 주식에 넣은 현금){쌓임안내}</p>
        <div class="fs-row"><span class="fs-num {vc}">{_flow_amt(실탄)}</span><span class="fs-state {vc}">{상태}{배수문}</span></div>
        <div class="fs-chips">{칩HTML}</div>
      </div>
    </div>
    {temp_inline()}
    <div class="fs-checks">
      <p class="fs-checks-t">🔍 세 가지만 확인하면 됩니다</p>
      {"".join(행들)}
    </div>
    {f'<p class="fs-combo"><b>{조합[1]}</b> — {조합[2]}</p>' if 조합 else ''}
    {f'<p class="fs-warn">{만기배지} — {만기설명}</p>' if 만기배지 else ''}
    <div class="fs-splittitle">📊 지수와 수급, 나란히 보기 <span>— 최근 {min(N,20)}거래일</span></div>
    <div class="fs-cum">
      <div class="fs-cum-head">{배지HTML}</div>
      {그래프HTML}
      {판독HTML}
    </div>
    {flow_pattern_analysis()}
    <p class="fs-foot">읽는 법: 아래 막대는 <b>그날그날의 실탄</b>(빨강 = 들어옴 · 파랑 = 빠짐), 흰 선은 그것이 <b>차곡차곡 쌓인 누적</b>입니다.
      선이 우상향이면 큰돈이 시장에 쌓이는 중입니다. 흐린 파란 점선은 <b>외국인 선물 누적</b>으로, 현물과 단위가 달라 <b>크기가 아니라 방향만</b> 견주는 참고선입니다. ※ 오늘까지의 수급 사실 정리이며 내일의 예측이나 매매 신호가 아닙니다.</p>
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
    날짜 = f"{data['날짜'][:4]}.{data['날짜'][4:6]}.{data['날짜'][6:]}"

    # ── 공유 카드(OG) — 같은 문장이 세 번 겹치던 문제를 역할 분담으로 해결 ──
    #   og:title = 한줄평 (카드 흰 글씨)  /  og:description = 날짜만 (회색 글씨)
    #   og:image = 매일 새로 생성되는 썸네일 PNG (make_thumb.py)
    #   관제지수는 카드에서 전부 뺀다 — 클릭 전 사람에게는 의미 없는 숫자.
    관제 = data.get("관제지수") or {}
    if isinstance(오늘한줄평, str) and not 오늘한줄평.startswith("—"):
        og_title = 오늘한줄평
    else:
        og_title = f"차트프로 관제탑 {날짜}"
    _d = data["날짜"]
    _요일 = "월화수목금토일"[datetime.strptime(_d, "%Y%m%d").weekday()]
    og_desc = f"{int(_d[4:6])}월 {int(_d[6:])}일 ({_요일}) 마감 · 차트프로 관제탑"
    og_img = f"https://sixline86-ship-it.github.io/chartpro/thumb/{_d}.png"
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
.ix-scale{{display:flex;justify-content:space-between;font-size:8.5px;color:#6b7078;padding-left:57px}}
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

.iss90-h{{font-size:12.5px;font-weight:800;color:#e0c060;margin-bottom:.15rem}}

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

.mny-h{{font-size:12.5px;font-weight:800;color:#e0c060;margin-bottom:.15rem}}

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

.mw-h{{font-size:11.5px;font-weight:800;color:#e0c060;margin-bottom:.35rem}}

.mw-b{{font-size:13px;color:#fff;line-height:1.75;font-weight:600}}

.mw-b b{{color:#e0c060;font-weight:800}}

.mine{{background:rgba(143,180,238,.09);border:.5px solid rgba(143,180,238,.22);border-radius:var(--rmd);padding:.9rem 1rem;margin-top:.8rem}}

.mine-h{{font-size:15.5px;font-weight:800;color:var(--dn-soft);margin-bottom:.5rem}}

.mine-b{{font-size:13px;color:#dfe3e8;line-height:1.8}}

.mine-b b{{color:#fff;font-weight:800}}

.mine-split{{margin-top:.7rem;display:grid;grid-template-columns:1fr 1fr;gap:7px}}

.ms{{background:rgba(0,0,0,.2);border-radius:6px;padding:.6rem .7rem}}

.ms-k{{font-size:11px;font-weight:800;color:#e0c060;margin-bottom:3px}}

.ms-v{{font-size:12px;color:#c3c8ce;line-height:1.6}}

.mine-f{{font-size:11.5px;color:#8a909a;margin-top:.65rem;line-height:1.6}}


.q90-flip{{background:rgba(224,192,96,.07);border-left:3px solid #e0c060;padding:.9rem 1rem;margin-top:.8rem}}

.qf-h{{font-size:15.5px;font-weight:800;color:#e0c060;margin-bottom:.45rem}}

.qf-b{{font-size:13.5px;color:#dfe3e8;line-height:1.8}}

.qf-b b{{color:#fff;font-weight:800}}

.q90-tease{{margin-top:1rem;padding-top:.9rem;border-top:.5px solid rgba(255,255,255,.1)}}

.qt-h{{font-size:15.5px;font-weight:800;color:var(--up-soft);margin-bottom:.6rem}}

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
.tmr-h{{font-size:15.5px;font-weight:800;color:#e0c060;margin-bottom:6px}}
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
.fs-temp{{padding:.2rem 0 .75rem;border-bottom:.5px solid rgba(255,255,255,.1)}}
.fs-temp-t{{font-size:10.5px;font-weight:700;color:#c8ccd2;letter-spacing:.04em;margin-bottom:.45rem}}
.fs-temp-t span{{font-weight:600;color:#8a909a;letter-spacing:0}}
.ft-row{{display:grid;grid-template-columns:48px 92px 1fr auto;gap:9px;align-items:baseline;padding:5px 0}}
.ft-who{{font-size:11.5px;font-weight:700;color:#9aa0a8}}
.ft-val{{font-size:14.5px;font-weight:800;font-variant-numeric:tabular-nums}}
.ft-val.b{{color:#ff9a80}} .ft-val.s{{color:#8fb4ee}}
.ft-avg{{font-size:10px;color:#7d838c;font-weight:600;white-space:nowrap}}
.ft-bad i{{font-style:normal;font-size:9.5px;font-weight:800;color:#d8dce2;background:rgba(255,255,255,.07);border:.5px solid rgba(255,255,255,.13);border-radius:99px;padding:2px 8px;white-space:nowrap}}
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
.dv-h{{font-size:14px;font-weight:800;color:#f0efec;margin-bottom:.7rem}}
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
</style>
</head>
<body>
<div class="rp">
  <div class="top-bar">
    <p class="rp-title">🗼 차트프로 관제탑</p>
    <span class="badge">{날짜} 마감</span>
  </div>

  {build_core(해석.get('핵심편'), data, 해석)}

  <div class="deep-wrap">
  {build_gauge(data.get('관제지수'), 오늘한줄평)}

  {build_terrain(data.get('주도섹터'))}

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

  <p class="sec-label"><small>주도 섹터</small>🏆 오늘의 주인공 — 시장을 끌고 간 6개 업종</p>
  {dev_note(f"전체 테마 중 등락률 상위 {(data.get('설정') or {}).get('주도섹터',{}).get('1차후보','?')}개를 1차 후보로 추림 → "
            f"{(data.get('설정') or {}).get('주도섹터',{}).get('가중치','?')} 점수로 재정렬 → "
            f"상위 {(data.get('설정') or {}).get('주도섹터',{}).get('선정수','?')}개. "
            f"단, 앞 카드와 종목이 {(data.get('설정') or {}).get('주도섹터',{}).get('중복제외기준','?')}개 이상 겹치면 제외")}
  {build_sectors(data.get('주도섹터'))}

  <p class="sec-label"><small>크기별 경사</small>📐 대형이 끌었나, 소형이 끌었나</p>
  {build_slope_chart(data.get('계좌격자'))}

  <p class="sec-label"><small>1개월 항로</small>🛬 관제탑에 다녀간 섹터들</p>
  {build_capture_path(1)}

  <p class="sec-label"><small>프로의 시선</small>🔍 남들이 놓친 자리</p>
  {build_insight(프로의시선)}
  {build_divergence_block(data, 해석)}

  <p class="sec-label"><small>수급 관제신호</small>💰 큰돈은 어디로 갔나</p>
  {build_flow_signal(data.get('파생'), data.get('지수수급'))}

  <p class="sec-label" id="radar"><small>실제 강세 레이더</small>🔥 오늘 불 붙은 곳</p>
  {build_radar(data.get('강세레이더'), data.get('설정'))}

  <p class="sec-label" id="acc"><small>매집 레이더</small>🐢 조용히 모으는 손</p>
  {build_accumulation(data.get('매집레이더'), data.get('설정'))}

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

  <p class="sec-label" id="watch"><small>내일의 관전 포인트</small>🗼 내일 이것만 보세요</p>
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
