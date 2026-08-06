# ============================================================
# build_html.py  (v2)
#  data_YYYYMMDD.json (+ report_YYYYMMDD.json 있으면) → report_YYYYMMDD.html
#  포함: 관제지수 게이지(산정기준 토글) · 주도섹터6(짙은분홍) · 예측셀프체크
# ============================================================

import json
import os
import html
from datetime import datetime

SCRIPT_VERSION = "v2026.08.06-d"   # ⬅ 버전 표시
# ⚙️ 개발용 조건 표시 — 배포 시 False로 바꾸면 모든 조건 설명이 사라진다
SHOW_CRITERIA = True

DATE = datetime.now().strftime("%Y%m%d")
DATA_PATH = f"data_{DATE}.json"
REPORT_PATH = f"report_{DATE}.json"
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
    return f'''
    <div class="sector-card">
      <div class="sc-head {head_cls}">
        <div class="sc-name-row">{theme_label(a['테마명'])}
          <span class="sc-chg {badge_cls}">{et_s}</span></div>
        <p class="sc-score">주도력 {점수}점</p>
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
        rows.append(f'''
    <div class="iss"><span class="itag">{it.get('태그','')}</span>
      <span class="iss-text">{it.get('내용','')}</span></div>''')
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
    return f"인기 뉴스 TOP {n}" if n else "인기 뉴스"


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


# ── 수급 관제신호 (실탄·3질문·누적 그래프) ──
FLOW_강한배수 = 1.4      # 평소 대비 이 배수 이상이면 "강한"
FLOW_바스켓선 = 0.45     # 바스켓 비중 이 이상이면 "폭넓은 매수"
FLOW_선물유의 = 0.5      # 선물이 평소의 이 배수 이상일 때만 반대 신호로 인정


def _flow_amt(v):
    """억원 → '+1.17조' / '−2,672억' 표기"""
    if v is None:
        return "—"
    a, s = abs(v), ("+" if v > 0 else "−")
    if a >= 10000:
        t = f"{a/10000:.2f}".rstrip("0").rstrip(".")
        return f"{s}{t}조"
    return f"{s}{a:,.0f}억"


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
    기준들 = 이력[:-1] if N >= 6 else 이력
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
        선물유의 = (평소선물 and abs(외선) / 평소선물 >= FLOW_선물유의) or abs(외선) >= 1000

    # ── 체크③: 바스켓 비중 ──
    비중 = None
    if 비차익 is not None and 실탄 and 방향양 == (비차익 >= 0) and abs(실탄) > 0:
        비중 = max(0.0, min(1.5, 비차익 / 실탄)) if 실탄 != 0 else None

    # ── 칩 ──
    칩 = []
    if 비중 is not None and 비중 >= FLOW_바스켓선:
        칩.append(("good", f"🧺 폭넓은 {'매수' if 방향양 else '매도'} — 바스켓 {비중*100:.0f}%"))
    elif 비중 is not None:
        칩.append(("info", f"🎯 종목 선별형 — 바스켓 {비중*100:.0f}%"))
    if 선물동의 is False and 선물유의:
        칩.append(("warn", "⚠️ 선물은 반대 (헤지 동반)"))
    elif 선물동의 is True and 선물유의:
        칩.append(("good", "🤝 선물도 같은 방향"))
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
    답1 = (f"들어왔습니다. 평소({평소실탄:,.0f}억/일)의 <b>{배수:.1f}배</b> 규모입니다."
          if (방향양 and 배수 and N >= 6) else
          ("들어왔습니다." if 방향양 else
           (f"빠져나갔습니다. 평소의 <b>{배수:.1f}배</b> 규모입니다." if (배수 and N >= 6) else "빠져나갔습니다.")))
    행들.append(체크행(("y" if 방향양 else "n", "✓" if 방향양 else "✗"),
                    "돈이 들어왔나?", "실탄 = 외국인+기관 현물", 답1,
                    _flow_amt(실탄), vc, "방향"))

    if 외선 is None:
        행들.append(체크행(("h", "—"), "선물도 동의하나?", "외국인 선물 방향",
                        "오늘은 선물 수급을 확보하지 못했습니다.", "—", "mid", "확신"))
    elif 선물동의:
        행들.append(체크행(("y", "✓"), "선물도 동의하나?", "외국인 선물 방향",
                        "현물과 선물이 같은 방향 — 확신이 실린 수급입니다.",
                        _flow_amt(외선), vc, "확신"))
    else:
        행들.append(체크행(("h", "△"), "선물도 동의하나?", "외국인 선물 방향",
                        f"현물은 {'사면서' if 방향양 else '팔면서'} 선물은 반대로 갔습니다. "
                        f"<b>보험(헤지)을 든 {'매수' if 방향양 else '매도'}</b>라 확신은 한 단계 낮춰 봅니다.",
                        _flow_amt(외선), "mid", "확신"))

    if 비중 is None:
        행들.append(체크행(("h", "—"), "폭넓게 샀나?", "비차익 ÷ 실탄",
                        "오늘은 프로그램매매(비차익) 데이터를 확보하지 못해 폭은 확인 불가입니다.",
                        "—", "mid", "폭"))
    elif 비중 >= FLOW_바스켓선:
        행들.append(체크행(("y", "✓"), "폭넓게 샀나?", "비차익 ÷ 실탄",
                        f"실탄의 <b>{비중*100:.0f}%</b>가 시장 전체(바스켓) {'매수' if 방향양 else '매도'} — "
                        f"몇 종목이 아니라 <b>한국 시장 자체</b>{'를 산' if 방향양 else '에서 나간'} 겁니다.",
                        f"{비중*100:.0f}%", vc, "폭"))
    else:
        행들.append(체크행(("h", "△"), "폭넓게 샀나?", "비차익 ÷ 실탄",
                        f"바스켓 비중 <b>{비중*100:.0f}%</b> — 시장 전체보다 특정 종목 위주의 선별 "
                        f"{'매수' if 방향양 else '매도'}입니다.", f"{비중*100:.0f}%", "mid", "폭"))

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
        if n >= 6:
            bx = X(n-5) - BW*0.9
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
              '<span><i class="l-fu"></i>외국인 선물 누적 · 방향 참고</span></div>') if len(선물있는) >= 2 else ""
        그래프HTML = (f'<svg viewBox="0 0 {W0} {H0}" preserveAspectRatio="none" style="width:100%;display:block">'
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
    <div class="fs-checks">
      <p class="fs-checks-t">🔍 세 가지만 확인하면 됩니다</p>
      {"".join(행들)}
    </div>
    <div class="fs-cum">
      <div class="fs-cum-head">
        <span class="fs-cum-t">📈 실탄이 쌓이는 흐름 — 최근 {min(N,20)}거래일</span>
        {배지HTML}
      </div>
      {그래프HTML}
      {판독HTML}
    </div>
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

    # ── 카톡 공유 카드(OG) 문구를 오늘 데이터로 자동 생성 ──
    관제 = data.get("관제지수") or {}
    if 관제:
        og_title = f"🗼 차트프로 관제탑 {날짜} — 관제지수 {관제.get('점수','')} · {관제.get('구간','')}"
    else:
        og_title = f"🗼 차트프로 관제탑 {날짜}"
    # 설명: 한줄평이 있으면 그걸, 없으면 코스피 등락 요약
    if isinstance(오늘한줄평, str) and not 오늘한줄평.startswith("—"):
        og_desc = 오늘한줄평
    else:
        og_desc = f"코스피 {코.get('등락률','')}% · 오늘의 시장 온도를 관제지수로"

    return f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>차트프로 관제탑 · {날짜}</title>
<meta property="og:title" content="{og_title}">
<meta property="og:description" content="{og_desc}">
<meta property="og:type" content="article">
<!-- og:image는 자동화 단계에서 리포트 캡처 이미지 경로로 추가 예정 -->
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
a{{color:inherit;text-decoration:none}}
.top-bar{{display:flex;justify-content:space-between;padding-bottom:1rem;border-bottom:.5px solid var(--line);margin-bottom:.9rem}}
.rp-title{{font-size:17px;font-weight:800}}
.badge{{font-size:11px;color:var(--sub);background:var(--bg2);padding:3px 9px;border-radius:var(--rmd);border:.5px solid var(--line);height:fit-content}}
.sec-label{{font-size:11px;font-weight:600;color:var(--sub);letter-spacing:.07em;text-transform:uppercase;margin:1.5rem 0 .7rem;display:flex;gap:6px}}
.sec-label::after{{content:'';flex:1;height:.5px;background:var(--line);align-self:center}}
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
.ic-num{{font-size:19px;font-weight:800}}
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
.issue-box{{background:var(--bg2);border-radius:var(--rlg);padding:.9rem 1.1rem;margin-bottom:1rem}}
.iss{{display:flex;align-items:flex-start;gap:8px;padding:7px 0;border-bottom:.5px solid var(--line);line-height:1.65}}
.iss:last-child{{border-bottom:none;padding-bottom:0}}
.itag{{font-size:10px;font-weight:600;padding:2px 7px;border-radius:4px;white-space:nowrap;flex-shrink:0;margin-top:2px;background:#E6F1FB;color:#0C447C}}
.iss-text{{font-size:12.5px;color:var(--ink)}}

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
.silent-wrap{{background:#F4F2FA;border-radius:var(--rlg);padding:.95rem 1.05rem;margin-bottom:1rem}}
.silent-head{{font-size:12.5px;font-weight:800;color:#3C3489;margin-bottom:.6rem}}
.si-item{{display:flex;gap:9px;padding:7px 0;border-bottom:.5px solid #e0dcf0;font-size:12.5px;line-height:1.75;color:#33305e}}
.si-item:last-child{{border-bottom:none;padding-bottom:0}}
.si-lens{{font-size:10px;font-weight:700;background:#E3DFF5;color:#3C3489;padding:2px 8px;border-radius:4px;white-space:nowrap;flex-shrink:0;margin-top:3px;height:fit-content}}
.study-src{{font-size:10.5px;font-weight:600;color:#5b8a2a;background:#dcebc8;display:inline-block;padding:2px 9px;border-radius:99px;margin:2px 0 6px}}
.study-box{{background:linear-gradient(135deg,#EAF3DE,#f2f7e8);border-radius:var(--rlg);padding:.95rem 1.1rem;margin-bottom:1rem;font-size:12.5px;color:#3B6D11;line-height:1.8}}
.hidden-block{{display:none}} .hidden-block.open{{display:block}}
.more-btn{{display:block;width:100%;text-align:center;font-size:11.5px;font-weight:600;color:var(--sub);background:var(--bg2);border:.5px solid var(--line);border-radius:99px;padding:7px 0;cursor:pointer;font-family:var(--font-sans);margin-bottom:1rem}}
.macro-row{{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:8px;margin-bottom:1rem}}
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
.rd-foot{{font-size:9.5px;color:var(--sub);line-height:1.6;margin-top:.5rem;padding-top:.7rem;border-top:.5px solid var(--line)}}

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
/* 수급 관제신호 */
.fs-box{{background:linear-gradient(180deg,#1c1f24,#282c33);border-radius:var(--rlg);padding:1.1rem 1.1rem .95rem;color:#e8e6e2;margin-bottom:1rem}}
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
.fs-ck-v small{{display:block;font-size:8.5px;font-weight:700;color:#767c86}}
.fs-cum{{padding-top:.95rem}}
.fs-cum-head{{display:flex;align-items:baseline;justify-content:space-between;gap:8px;flex-wrap:wrap;margin-bottom:.2rem}}
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
.fs-x{{display:flex;justify-content:space-between;font-size:9px;color:#767c86;font-weight:600;margin-top:3px;padding:0 2px}}
.fs-read{{font-size:11.5px;color:#c3c8ce;line-height:1.75;margin-top:.65rem}}
.fs-read b{{color:#fff}}
.fs-building{{background:rgba(255,255,255,.04);border:.5px dashed rgba(255,255,255,.16);border-radius:var(--rmd);padding:1.1rem;text-align:center;font-size:11px;color:#9aa0a8;margin-top:.4rem}}
.fs-foot{{font-size:9.5px;color:#8a909a;line-height:1.7;margin-top:.8rem;border-top:.5px solid rgba(255,255,255,.08);padding-top:.6rem}}
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

  {build_gauge(data.get('관제지수'), 오늘한줄평)}

  {build_terrain(data.get('주도섹터'))}

  <p class="sec-label">📊 지수 + 수급</p>
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

  <p class="sec-label">🔥 핵심 이슈</p>
  {build_issues(해석.get('핵심이슈'))}

  <p class="sec-label">🌐 환율 · 유가 · 금리</p>
  <div class="macro-row">
    {build_macro_card((data.get('매크로') or {}).get('원달러환율'), (해석.get('매크로해설') or {}).get('환율',''))}
    {build_macro_card((data.get('매크로') or {}).get('WTI유가'), (해석.get('매크로해설') or {}).get('유가',''))}
    {build_macro_card((data.get('매크로') or {}).get('미국채10년'), (해석.get('매크로해설') or {}).get('금리',''))}
  </div>

  <p class="sec-label">🏆 주도 섹터 — 오늘 가장 강했던 6개 업종</p>
  {dev_note(f"전체 테마 중 등락률 상위 {(data.get('설정') or {}).get('주도섹터',{}).get('1차후보','?')}개를 1차 후보로 추림 → "
            f"{(data.get('설정') or {}).get('주도섹터',{}).get('가중치','?')} 점수로 재정렬 → "
            f"상위 {(data.get('설정') or {}).get('주도섹터',{}).get('선정수','?')}개. "
            f"단, 앞 카드와 종목이 {(data.get('설정') or {}).get('주도섹터',{}).get('중복제외기준','?')}개 이상 겹치면 제외")}
  {build_sectors(data.get('주도섹터'))}

  <p class="sec-label">📡 실제 강세 레이더 — 오늘 새로 포착</p>
  {build_radar(data.get('강세레이더'), data.get('설정'))}

  <p class="sec-label">🐢 5일 매집 레이더 — 조용히 쌓이는 돈</p>
  {build_accumulation(data.get('매집레이더'), data.get('설정'))}

  <p class="sec-label">📺 마감 브리핑 — 방송사별 관점</p>
  {build_briefings(해석.get('마감브리핑'))}

  <p class="sec-label">🔍 프로의 시선</p>
  {build_insight(프로의시선)}

  <p class="sec-label">💰 수급 관제신호 — 오늘 큰돈은 어느 쪽으로 움직였나</p>
  {build_flow_signal(data.get('파생'), data.get('지수수급'))}

  <p class="sec-label">📋 오늘의 중요 공시</p>
  <div class="disc-box">
    {build_disclosures(data.get('공시'), 해석.get('공시해설'))}
    <p class="disc-note" style="margin-top:.6rem;font-size:9.5px">별점은 다음 거래일 변동 가능성 참고용이며 방향 예측이 아닙니다.</p>
  </div>

  <p class="sec-label">🔥 {news_title(해석.get('핵심뉴스'))}</p>
  {build_news(해석.get('핵심뉴스'))}

  {f'<p class="sec-label">✅ 어제의 채점표</p>{build_scorecard(해석.get("채점표"))}' if 해석.get('채점표') else ''}

  <p class="sec-label">🗼 내일의 관전 포인트</p>
  {(''.join(f'<div class="watch-item"><span>{pt}</span></div>' for pt in 해석.get('관전포인트'))) if 해석.get('관전포인트') else '<div class="pending">⏳ ①②③ 관전포인트 — Claude 해석 연동 후 자동 생성</div>'}

  <p class="sec-label">📚 오늘의 공부</p>
  {build_study(오늘의공부)}

  <!-- 오늘의 한 문장 (필사 코너) -->
  <p class="sec-label">✍️ 오늘의 한 문장</p>
  <div class="quote-box">
    <div class="quote-mark">“</div>
    <p class="quote-text">{오늘의문장}</p>
    <p class="quote-sub">— 차트프로 관제탑, {날짜}</p>
  </div>

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
