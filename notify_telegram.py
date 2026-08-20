# ============================================================
# notify_telegram.py  (v2026.08.12-a)
# ------------------------------------------------------------
# 리포트가 발행된 뒤, 텔레그램으로 완성 알림을 보낸다.
#   - 오늘 report_YYYYMMDD.json 에서 관제지수·한줄평을 읽어
#     간단한 메시지 + 리포트 링크를 전송한다.
#   - 토큰/chat_id 는 환경변수(GitHub Secrets)에서 읽는다.
# ============================================================

import json
import os
import requests
from datetime import datetime

SCRIPT_VERSION = "v2026.08.21-n20"   # ⬅ 다른 4개 파일과 항상 같아야 한다.
DATE = datetime.now().strftime("%Y%m%d")
REPORT_PATH = (os.path.join("archive", f"report_{DATE}.json")
               if os.path.exists(os.path.join("archive", f"report_{DATE}.json"))
               else f"report_{DATE}.json")

# 배포된 리포트 주소
#   ⚠️ index.html(고정 주소)이 아니라 **날짜별 페이지**로 보낸다.
#   텔레그램·카톡은 같은 URL의 미리보기를 캐싱해서, 고정 주소로 보내면
#   어제의 썸네일·제목이 그대로 뜬다. 날짜가 다르면 캐시가 원천적으로 안 생긴다.
SITE_URL = "https://sixline86-ship-it.github.io/chartpro/"
REPORT_URL = f"{SITE_URL}report_{DATE}.html"

TOKEN = os.environ.get("TELEGRAM_TOKEN", "")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")


def build_message():
    """붙여넣기용 캡션.

    ⚠️ 역할 분담 원칙(v-l5) — 같은 문장이 세 번 반복되던 문제를 고쳤다.
       카톡에 이 글을 붙여넣으면 화면에 네 자리가 생긴다.
         ① 이 캡션 (말풍선)      ② 썸네일 그림  ③ 미리보기 제목  ④ 미리보기 설명
       예전에는 ①③이 한줄평, ②도 한줄평이라 **같은 말이 세 번** 나왔다.
       그래서 자리마다 서로 다른 것만 담게 나눴다.
         ① 캡션      = 브랜드 + 날짜 + 링크   (여기)
         ② 썸네일    = 한줄평 + 공감문구      (make_thumb.py)
         ③ 제목      = 오늘의 정의            (build_html.py og:title)
         ④ 설명      = 관제지수               (build_html.py og:description)
    """
    _요일 = "월화수목금토일"[datetime.strptime(DATE, "%Y%m%d").weekday()]
    날짜표기 = f"{int(DATE[4:6])}월 {int(DATE[6:])}일({_요일}) 마감"
    return f"🗼 차트프로 관제탑 · {날짜표기}\n\n{REPORT_URL}"


def _thumb_path():
    """오늘 썸네일 파일 경로 (없으면 None)."""
    p = os.path.join("thumb", f"{DATE}.png")
    return p if os.path.exists(p) else None


def main():
    if not TOKEN or not CHAT_ID:
        print("⚠️ TELEGRAM_TOKEN / TELEGRAM_CHAT_ID 가 없어 알림을 건너뜁니다.")
        return

    msg = build_message()

    # ── ① 썸네일이 있으면 sendPhoto로 '직접 업로드' ──────────────
    #  ⚠️ 왜 바꿨나: 예전에는 sendMessage + link_preview_options만 보냈다.
    #     그러면 텔레그램이 우리 페이지를 **직접 크롤링해서** og:image를 읽어야
    #     썸네일이 뜬다. 그런데
    #       · GitHub Pages 배포가 아직 안 끝났거나
    #       · 텔레그램이 그 URL을 이미 캐시해 뒀거나
    #       · 크롤러가 늦게 오면
    #     그림 없이 글자만 나간다. 실제로 계속 그랬다.
    #  → 파일을 우리가 직접 올려버리면 크롤링·캐시와 무관하게 100% 나온다.
    사진 = _thumb_path()
    if 사진:
        try:
            with open(사진, "rb") as f:
                r = requests.post(
                    f"https://api.telegram.org/bot{TOKEN}/sendPhoto",
                    data={"chat_id": CHAT_ID, "caption": msg},
                    files={"photo": (os.path.basename(사진), f, "image/png")},
                    timeout=30,
                )
            if r.status_code == 200:
                print(f"✅ 텔레그램 전송 완료 (썸네일 직접 첨부: {사진}) [{SCRIPT_VERSION}]")
                return
            print(f"⚠️ sendPhoto 실패 HTTP {r.status_code}: {r.text[:200]} — 글만 재시도합니다")
        except Exception as e:
            print(f"⚠️ sendPhoto 오류: {type(e).__name__}: {e} — 글만 재시도합니다")
    else:
        print(f"⚠️ 썸네일 파일 없음(thumb/{DATE}.png) — 글만 보냅니다")

    # ── ② 사진이 없거나 실패하면 기존 방식(링크 미리보기)으로 폴백 ──
    try:
        r = requests.post(
            f"https://api.telegram.org/bot{TOKEN}/sendMessage",
            json={"chat_id": CHAT_ID, "text": msg,
                  "link_preview_options": {"url": REPORT_URL,
                                           "prefer_large_media": True,
                                           "show_above_text": True}},
            timeout=15,
        )
        if r.status_code == 200:
            print("✅ 텔레그램 알림 전송 완료 (링크 미리보기)")
        else:
            print(f"⚠️ 텔레그램 전송 실패 HTTP {r.status_code}: {r.text[:200]}")
    except Exception as e:
        print(f"⚠️ 텔레그램 전송 오류: {type(e).__name__}: {e}")


if __name__ == "__main__":
    main()
