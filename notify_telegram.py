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
    """오늘 리포트에서 관제지수·한줄평을 읽어 메시지를 만든다.
    파일이 없거나 값이 없으면 링크만 보낸다."""
    날짜표기 = f"{DATE[:4]}.{DATE[4:6]}.{DATE[6:]}"
    지수, 구간, 한줄 = None, None, None
    try:
        with open(REPORT_PATH, "r", encoding="utf-8") as f:
            d = json.load(f)
        관제 = d.get("관제지수") or {}
        지수 = 관제.get("점수")
        구간 = 관제.get("구간")
        한줄 = (d.get("해석글") or {}).get("한줄평")
    except Exception:
        pass  # 값 없으면 링크만

    줄 = [f"🗼 차트프로 관제탑 · {날짜표기}"]
    if 지수 is not None:
        줄.append(f"오늘의 관제지수: {지수}" + (f" ({구간})" if 구간 else ""))
    if 한줄:
        줄.append(f"💬 {한줄}")
    줄.append("")
    줄.append(f"👉 {REPORT_URL}")
    return "\n".join(줄)


def main():
    if not TOKEN or not CHAT_ID:
        print("⚠️ TELEGRAM_TOKEN / TELEGRAM_CHAT_ID 가 없어 알림을 건너뜁니다.")
        return

    msg = build_message()
    try:
        r = requests.post(
            f"https://api.telegram.org/bot{TOKEN}/sendMessage",
            json={"chat_id": CHAT_ID, "text": msg,
                  # 미리보기를 크게 + 본문 위에 — 썸네일이 카드의 주인공이 되게
                  "link_preview_options": {"url": REPORT_URL,
                                           "prefer_large_media": True,
                                           "show_above_text": True}},
            timeout=15,
        )
        if r.status_code == 200:
            print("✅ 텔레그램 알림 전송 완료")
        else:
            # 실패 원인을 바로 알 수 있게 (토큰/chat_id 문제 등)
            print(f"⚠️ 텔레그램 전송 실패 HTTP {r.status_code}: {r.text[:200]}")
    except Exception as e:
        print(f"⚠️ 텔레그램 전송 오류: {type(e).__name__}: {e}")


if __name__ == "__main__":
    main()
