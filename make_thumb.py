# ============================================================
# make_thumb.py  (v2026.08.12-a)
# ------------------------------------------------------------
# 카톡·텔레그램 공유 카드용 썸네일 PNG를 매일 생성한다 (1200×630).
#   레이아웃 A안: 다크 그라디언트 배경 + 한줄평(강조어 주황) + 날짜
#                + 하단 금색 바 + 공감문구
#   글 재료: report_YYYYMMDD.json (한줄평 · 핵심편.공감문구)
#   출력: thumb/YYYYMMDD.png  → report HTML의 og:image가 이 파일을 가리킨다
#   폰트: assets/fonts/NanumGothic-*.ttf (저장소 동봉)
#         → 없으면 시스템 Noto Sans CJK로 대체
# ============================================================

import json
import os
import re
from datetime import datetime

from PIL import Image, ImageDraw, ImageFont

SCRIPT_VERSION = "v2026.08.13-d"
DATE = datetime.now().strftime("%Y%m%d")

W, H = 1200, 630
BG_TOP, BG_BOT = (34, 38, 45), (43, 48, 56)          # #22262d → #2b3038
INK = (240, 240, 238)                                  # 본문 흰색
SUB = (154, 160, 168)                                  # 회색
ACCENT = (255, 154, 128)                               # 강조 주황 #ff9a80
GOLD = (224, 192, 96)                                  # 금색 바 #e0c060

FONT_DIR = os.path.join("assets", "fonts")
FONT_URL = "https://github.com/google/fonts/raw/main/ofl/nanumgothic/{}"
FALLBACKS = [
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/nanum/NanumGothic.ttf",
]


def ensure_font(name):
    """폰트 파일을 확보한다 — 저장소에 없으면 **자동으로 내려받는다.**

    폰트를 저장소에 올리지 않아도 되게 하려는 장치다.
    (수동 업로드는 실수가 잦고, 폰트가 없으면 한글이 전부 □□□로 깨진다)
    받은 파일은 assets/fonts/ 에 캐시되어 다음 실행부터는 바로 쓴다.
    네트워크가 막히면 시스템 폰트로 넘어간다.
    """
    p = os.path.join(FONT_DIR, name)
    if os.path.exists(p) and os.path.getsize(p) > 100000:
        return p
    try:
        import urllib.request
        os.makedirs(FONT_DIR, exist_ok=True)
        urllib.request.urlretrieve(FONT_URL.format(name), p)
        if os.path.getsize(p) > 100000:
            print(f"   ⬇️ 폰트 자동 다운로드: {name}")
            return p
        os.remove(p)
    except Exception as e:
        print(f"   ⚠️ 폰트 다운로드 실패({type(e).__name__}) — 시스템 폰트로 대체")
    return None


def font(name, size):
    """나눔고딕 우선(없으면 자동 다운로드), 그마저 안 되면 시스템 폰트."""
    p = ensure_font(name)
    if p:
        return ImageFont.truetype(p, size)
    for fb in FALLBACKS:
        if os.path.exists(fb):
            try:
                return ImageFont.truetype(fb, size, index=1)   # index 1 = KR
            except Exception:
                return ImageFont.truetype(fb, size)
    print("   ⚠️ 한글 폰트를 찾지 못했습니다 — 글자가 깨질 수 있습니다")
    return ImageFont.load_default()


def load_texts():
    한줄, 공감 = None, None
    try:
        with open(f"report_{DATE}.json", encoding="utf-8") as f:
            d = json.load(f)
        해석 = d.get("해석글") or {}
        한줄 = 해석.get("한줄평")
        공감 = (해석.get("핵심편") or {}).get("공감문구")
    except Exception:
        pass
    if not 한줄:
        한줄 = "오늘의 시장 관제 리포트"
    return 한줄.strip(), (공감 or "").strip()


def wrap(draw, text, fnt, max_w):
    """단어 단위 줄바꿈 — 한 줄이 max_w를 넘지 않게."""
    lines, cur = [], ""
    for word in text.split():
        cand = (cur + " " + word).strip()
        if draw.textlength(cand, font=fnt) <= max_w:
            cur = cand
        else:
            if cur:
                lines.append(cur)
            cur = word
    if cur:
        lines.append(cur)
    return lines[:3]      # 최대 3줄 — 넘치면 잘라도 카드가 깨지는 것보단 낫다


def pick_accent(한줄):
    """한줄평에서 강조할 어절 하나 — 따옴표 안 > 숫자 포함 > 가장 긴 어절."""
    m = re.search(r"['\u2018\u2019\"\u201c\u201d]([^'\u2018\u2019\"\u201c\u201d]{2,12})['\u2018\u2019\"\u201c\u201d]", 한줄)
    if m:
        return m.group(1)
    for w in 한줄.split():
        if re.search(r"\d", w):
            return w
    words = 한줄.split()
    return max(words, key=len) if words else ""


def main():
    한줄, 공감 = load_texts()

    img = Image.new("RGB", (W, H), BG_TOP)
    draw = ImageDraw.Draw(img)
    # 세로 그라디언트
    for y in range(H):
        t = y / H
        c = tuple(round(a + (b - a) * t) for a, b in zip(BG_TOP, BG_BOT))
        draw.line([(0, y), (W, y)], fill=c)

    # 상단: 브랜드 + 날짜
    f_brand = font("NanumGothic-Bold.ttf", 34)
    f_date = font("NanumGothic-Regular.ttf", 30)
    draw.text((70, 62), "차트프로 관제탑", font=f_brand, fill=SUB)
    요일 = "월화수목금토일"[datetime.now().weekday()]
    날짜문 = f"{int(DATE[4:6])}월 {int(DATE[6:])}일 ({요일}) 마감"
    dw = draw.textlength(날짜문, font=f_date)
    draw.text((W - 70 - dw, 66), 날짜문, font=f_date, fill=SUB)

    # 중앙: 한줄평 (강조어만 주황)
    f_main = font("NanumGothic-ExtraBold.ttf", 76)
    lines = wrap(draw, 한줄, f_main, W - 140)
    if len(lines) == 3:                       # 3줄이면 글자를 줄여 2~3줄 안정화
        f_main = font("NanumGothic-ExtraBold.ttf", 62)
        lines = wrap(draw, 한줄, f_main, W - 140)
    강조 = pick_accent(한줄)
    line_h = int(f_main.size * 1.32)
    total_h = line_h * len(lines)
    y = (H - total_h) // 2 - 20
    for line in lines:
        x = 70
        if 강조 and 강조 in line:
            before, after = line.split(강조, 1)
            if before:
                draw.text((x, y), before, font=f_main, fill=INK)
                x += draw.textlength(before, font=f_main)
            draw.text((x, y), 강조, font=f_main, fill=ACCENT)
            x += draw.textlength(강조, font=f_main)
            if after:
                draw.text((x, y), after, font=f_main, fill=INK)
        else:
            draw.text((x, y), line, font=f_main, fill=INK)
        y += line_h

    # 하단: 금색 바 + 공감문구
    bar_y = H - 150
    draw.rounded_rectangle([70, bar_y, 78, bar_y + 74], radius=4, fill=GOLD)
    if 공감:
        f_feel = font("NanumGothic-Bold.ttf", 40)
        draw.text((100, bar_y + 14), 공감, font=f_feel, fill=(200, 205, 212))
    f_foot = font("NanumGothic-Regular.ttf", 24)
    draw.text((100, H - 52), "매일 저녁 · 숫자로 검증하는 시장 관제", font=f_foot, fill=SUB)

    os.makedirs("thumb", exist_ok=True)
    out = os.path.join("thumb", f"{DATE}.png")
    img.save(out, "PNG")
    print(f"✅ 썸네일 생성: {out}  ({W}×{H}) [{SCRIPT_VERSION}]")


if __name__ == "__main__":
    main()
