# ============================================================
# build_html.py  (v2)
#  data_YYYYMMDD.json (+ report_YYYYMMDD.json 있으면) → report_YYYYMMDD.html
#  포함: 관제지수 게이지(산정기준 토글) · 주도섹터6(짙은분홍) · 예측셀프체크
# ============================================================

import json
import os
from datetime import datetime

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


# ── 섹터 지형도 (v8 스타일: 0선 기준 세로 막대) ──
def build_terrain(주도섹터):
    """주도섹터 6개의 테마 등락률로 0선 기준 막대 차트를 그린다."""
    if not 주도섹터:
        return ""
    cols = []
    for a in 주도섹터[:6]:
        et = a.get("테마등락")
        v = et if isinstance(et, (int, float)) else 0
        # 막대 높이: |등락률| × 배율 (최대 70px 근처), 최소 3px
        h = min(70, max(3, abs(v) * 8))
        if v >= 0:
            bar = f'<div class="bar pos" style="height:{h}px"></div>'
            val = f'<span class="bar-val pos" style="bottom:calc(50% + {h+3}px)">{v:+.1f}%</span>'
        else:
            bar = f'<div class="bar neg" style="height:{h}px"></div>'
            val = f'<span class="bar-val neg" style="top:calc(50% + {h+3}px)">{v:+.1f}%</span>'
        name = a["테마명"]
        # 이름이 길면 자르기
        disp = name if len(name) <= 6 else name[:5] + "…"
        cols.append(f'''
      <div class="bar-col">
        <div class="bar-zone">{val}{bar}</div>
        <p class="bar-name">{disp}</p>
      </div>''')
    return f'''
  <div class="terrain-box">
    <p class="terrain-title">📊 오늘의 섹터 지형도 — 주도 6개 업종 등락률</p>
    <div class="bar-chart">{"".join(cols)}</div>
  </div>'''


def build_sectors(주도섹터):
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
def build_disclosures(disc):
    if not disc:
        return '<p class="disc-note" style="color:#8a909a">오늘 수집된 관심 유형 공시가 없습니다.</p>'
    rows = []
    for item in disc[:5]:
        rows.append(f'''
    <a class="disc-row" href="{item['링크']}" target="_blank">
      <div class="disc-head"><span class="disc-name">{item['회사명']}</span>
        <span class="stars">{stars_html(item['별점'])}</span></div>
      <p class="disc-note">{item['공시명']} <span class="disc-lnk">↗ 상세보기</span></p>
    </a>''')
    return "".join(rows)


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
      <span class="news-tag {cls}">{tag}</span>{제목}'''
    if 링크:
        title_html = f'<a href="{링크}" target="_blank">{본문}</a>'
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


def build_news(핵심뉴스):
    if not 핵심뉴스:
        return '<div class="pending">⏳ 네이버 증권 인기뉴스 크롤링 준비중</div>'
    앞3 = 핵심뉴스[:3]
    뒤 = 핵심뉴스[3:10]
    앞HTML = "".join(one_news_item(i + 1, it) for i, it in enumerate(앞3))
    뒤HTML = "".join(one_news_item(i + 4, it) for i, it in enumerate(뒤))
    더보기 = ""
    if 뒤:
        더보기 = f'''
  <div class="hidden-block" id="moreNews"><div class="news-wrap" style="border:none;box-shadow:none;margin:0">{뒤HTML}</div></div>
  <button class="more-btn" onclick="toggleMore('moreNews',this,'▾ 핵심뉴스 {len(뒤)}개 더보기')">▾ 핵심뉴스 {len(뒤)}개 더보기</button>'''
    return f'<div class="news-wrap">{앞HTML}</div>{더보기}'


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
    침묵의지표 = 해석.get("침묵의_지표", "")
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
.terrain-title{{font-size:10.5px;font-weight:700;color:#c8ccd2;margin-bottom:.4rem;letter-spacing:.04em}}
.bar-chart{{display:grid;grid-template-columns:repeat(6,1fr);gap:6px}}
.bar-col{{display:flex;flex-direction:column;align-items:center}}
.bar-zone{{position:relative;width:100%;height:150px}}
.bar-zone::after{{content:'';position:absolute;left:6%;right:6%;top:50%;height:1px;background:rgba(255,255,255,.25)}}
.bar{{position:absolute;left:50%;transform:translateX(-50%);width:55%;max-width:24px;border-radius:4px;z-index:1}}
.bar.pos{{bottom:50%;background:linear-gradient(180deg,#ff8a6e,#C1432B)}}
.bar.neg{{top:50%;background:linear-gradient(180deg,#2E6BD6,#7fa8e8)}}
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
.sc-vol{{text-align:right;color:var(--up);font-weight:700;font-size:11px;font-variant-numeric:tabular-nums}}

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
.silent-box{{background:#F4F2FA;border-radius:var(--rlg);padding:.95rem 1.1rem;margin-bottom:1rem;font-size:12.5px;color:#33305e;line-height:1.8}}
.study-box{{background:linear-gradient(135deg,#EAF3DE,#f2f7e8);border-radius:var(--rlg);padding:.95rem 1.1rem;margin-bottom:1rem;font-size:12.5px;color:#3B6D11;line-height:1.8}}
.hidden-block{{display:none}} .hidden-block.open{{display:block}}
.more-btn{{display:block;width:100%;text-align:center;font-size:11.5px;font-weight:600;color:var(--sub);background:var(--bg2);border:.5px solid var(--line);border-radius:99px;padding:7px 0;cursor:pointer;font-family:var(--font-sans);margin-bottom:1rem}}
.macro-row{{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:8px;margin-bottom:1rem}}
.mr-card{{background:var(--bg2);border-radius:var(--rmd);padding:.7rem .9rem}}
.mr-label{{font-size:11px;color:var(--sub);margin-bottom:3px}}
.mr-val{{font-size:15px;font-weight:700;color:var(--sub)}}

/* ── 오늘의 한 문장 (필사 코너) ── */
.quote-box{{background:linear-gradient(135deg,#1c1f24,#2c3038);border-radius:var(--rlg);padding:1.6rem 1.4rem;color:#e8e6e2;margin-bottom:1rem;text-align:center;position:relative;overflow:hidden}}
.quote-mark{{font-size:52px;font-weight:800;color:rgba(127,168,232,.25);line-height:.5;height:24px}}
.quote-text{{font-size:16px;font-weight:700;color:#fff;line-height:1.75;letter-spacing:-.01em;margin:.4rem 0 .8rem;word-break:keep-all}}
.quote-sub{{font-size:11px;color:#9aa0a8}}

.foot{{font-size:10px;color:#b0aca6;line-height:1.6;border-top:.5px solid var(--line);padding-top:.8rem;margin-top:1.2rem}}

/* ── 모바일 ── */
@media (max-width:600px){{
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
  .bar-chart{{gap:3px}} .bar-zone{{height:120px}} .bar-val{{font-size:8.5px}} .bar-name{{font-size:8.5px}}
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
      <p class="{'ic-chg-dn' if '-' in str(코.get('등락방향','')) else 'ic-chg-up'}">{코.get('등락방향','—')} {코.get('등락률','—')}%</p>
      <div class="sup-grid">
        <div class="sup"><p class="sup-who">외국인</p><p class="sup-amt {money_class(코수.get('외국인'))}">{fmt_flow(코수.get('외국인'))}</p></div>
        <div class="sup"><p class="sup-who">기관</p><p class="sup-amt {money_class(코수.get('기관계'))}">{fmt_flow(코수.get('기관계'))}</p></div>
        <div class="sup"><p class="sup-who">개인</p><p class="sup-amt {money_class(코수.get('개인'))}">{fmt_flow(코수.get('개인'))}</p></div>
      </div>
    </div>
    <div class="idx-card2">
      <p class="ic-mkt">KOSDAQ</p>
      <p class="ic-num">{닥.get('종가','—')}</p>
      <p class="{'ic-chg-dn' if '-' in str(닥.get('등락방향','')) else 'ic-chg-up'}">{닥.get('등락방향','—')} {닥.get('등락률','—')}%</p>
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

  <p class="sec-label">🏆 주도 섹터 — 오늘 가장 강했던 6개 업종</p>
  {build_sectors(data.get('주도섹터'))}

  <p class="sec-label">📺 마감 브리핑 — 4사 관점 비교</p>
  <div class="pending">⏳ 유튜브 자막 API 연동 준비중 (삼프로TV·한국경제TV·이데일리TV·토마토TV)</div>

  <p class="sec-label">🔥 핵심 뉴스 TOP 10 요약</p>
  {build_news(해석.get('핵심뉴스'))}

  <p class="sec-label">📋 오늘의 공시</p>
  <div class="disc-box">
    {build_disclosures(data.get('공시'))}
    <p class="disc-note" style="margin-top:.6rem;font-size:9.5px">별점은 다음 거래일 변동 가능성 참고용이며 방향 예측이 아닙니다.</p>
  </div>

  <p class="sec-label">🔍 프로의 시선</p>
  {f'<div class="silent-box">🔍 {침묵의지표}</div>' if 침묵의지표 else '<div class="pending">⏳ 조용한 강세 · 짖지 않은 개 · 다음 시나리오 — Claude 해석 연동 후 자동 생성</div>'}

  <p class="sec-label">🌐 환율 · 유가 · 금리</p>
  <div class="macro-row">
    <div class="mr-card"><p class="mr-label">원/달러 환율</p><p class="mr-val">— (준비중)</p></div>
    <div class="mr-card"><p class="mr-label">WTI 유가</p><p class="mr-val">— (준비중)</p></div>
    <div class="mr-card"><p class="mr-label">금리</p><p class="mr-val">— (준비중)</p></div>
  </div>

  <p class="sec-label">📚 오늘의 공부</p>
  {f'<div class="study-box">📚 {오늘의공부}</div>' if 오늘의공부 else '<div class="pending">⏳ 오늘 이슈에서 출제하는 경제교실 — Claude 해석 연동 후 자동 생성</div>'}

  <p class="sec-label">🗼 다음 거래일 관전포인트</p>
  <div class="pending">⏳ ①②③ 관전포인트 — Claude 해석 연동 후 자동 생성</div>

  <!-- 오늘의 한 문장 (필사 코너) -->
  <p class="sec-label">✍️ 오늘의 한 문장</p>
  <div class="quote-box">
    <div class="quote-mark">“</div>
    <p class="quote-text">{오늘의문장}</p>
    <p class="quote-sub">— 차트프로 관제탑, {날짜}</p>
  </div>

  <p class="foot">데이터: {날짜} 기준, 한국거래소·DART·네이버 증권 종합 · 관제지수는 등락률·수급·시장폭을 근거로 한 자체 참고 지표입니다 · 별점·예측은 참고용이며 매수·매도 신호가 아닙니다 · 본 브리핑은 정보 제공 목적으로, 투자 권유가 아니며 투자 판단과 책임은 투자자 본인에게 있습니다.</p>
</div>
<script>
function toggleMore(id,btn,label){{
  var el=document.getElementById(id);
  var open=el.classList.toggle('open');
  btn.textContent=open?'▴ 접기':label;
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
    print(f"🎉 완료! → {OUT_PATH}")
