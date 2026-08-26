# notify_admin.py
# ============================================================
# 🚨 운영자(HO) 전용 알림 — 2026-08-22 신설
# ------------------------------------------------------------
# 목적: 발행이 정상적으로 안 됐을 때 **구독자에게는 아무것도 안 보내고**
#       운영자에게만 원인을 텔레그램으로 알린다.
#
# 언제 불리나 (daily.yml에서):
#   ① 휴장 감지  — 거래대금 0 등 (임시공휴일·임시휴장)
#   ② 해석글 없음 — Claude 생성 실패 또는 '재사용'인데 오늘 글이 없음
#   ③ 수집 실패   — collect_data가 죽음
#
# ⚠️ 구독자용 발송(notify_telegram.py)과 **채팅방을 반드시 분리**한다.
#    ADMIN_CHAT_ID가 없으면 TELEGRAM_CHAT_ID로 폴백하는데,
#    그 경우 구독자방에 오류 메시지가 갈 수 있으므로 경고를 남긴다.
# ============================================================
import os
import sys
from datetime import datetime

SCRIPT_VERSION = "v2026.08.26-k1"   # ⬅ 다른 파일과 항상 같아야 한다.

DATE = datetime.now().strftime("%Y%m%d")
SITE_URL = "https://sixline86-ship-it.github.io/chartpro/"

TOKEN = os.environ.get("TELEGRAM_TOKEN", "")
# 운영자 전용 방이 있으면 그걸 쓰고, 없으면 기존 방으로 폴백
ADMIN_ID = os.environ.get("TELEGRAM_ADMIN_CHAT_ID", "").strip()
FALLBACK = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
CHAT_ID = ADMIN_ID or FALLBACK

# 사유 코드 → 사람이 읽는 안내
안내표 = {
    "holiday": (
        "🚨 오늘 휴장으로 판단됩니다",
        "오늘 날짜의 수급 자료(외국인·기관)가 확인되지 않습니다.\n"
        "임시공휴일이거나 임시 휴장일 가능성이 큽니다.\n\n"
        "✅ 조치: 아무것도 안 했습니다. 과금도 발송도 없었습니다.\n"
        "   실제로 장이 열린 날이었다면 수집원(네이버·KRX) 장애를 의심하세요."
    ),
    "no_interp": (
        "⚠️ 해석글이 없어 발송을 멈췄습니다",
        "오늘 archive/report_{d}.json 이 만들어지지 않았습니다.\n\n"
        "가능한 원인\n"
        " · 발행 모드를 '재사용'으로 돌렸다 (가장 흔함)\n"
        " · Claude API 오류·잔액 부족\n"
        " · 응답이 max_tokens에서 잘림\n\n"
        "✅ 조치: 텔레그램 발송을 건너뛰었고, index.html도 건드리지 않았습니다.\n"
        "   Actions → '해석글 생성 (Claude)' 로그를 확인한 뒤\n"
        "   'Claude 해석글 = 새로 생성'으로 다시 실행하세요."
    ),
    # 🆕 2026-08-26 — 발행 시각을 16:50으로 당기면서 생긴 상황.
    #   수급 확정치는 대략 18시에 최종본이 되므로, 그 전에 발행하면
    #   숫자가 잠정치일 수 있다. **발행은 하되 반드시 알린다**(HO 지시).
    # 🆕 2026-08-26 — 오늘 해석글이 없어 **직전 거래일 글로 승계 발행**한 경우.
    #   발행을 멈추면 하루가 통째로 비므로, 발행은 하되 화면에 날짜를 밝히고
    #   운영자에게 원인 확인을 요청한다(HO 지시).
    "inherited": (
        "🔁 전날 해석글로 발행했습니다",
        "오늘 archive/report_{d}.json 이 없어 **직전 거래일 해석글**을 그대로 실었습니다.\n\n"
        "화면에는 «○/○ 글입니다» 배너가 표시됩니다.\n"
        "지수·수급·섹터·레이더의 숫자와 표는 **모두 오늘 것**입니다.\n\n"
        "✅ 조치: 정상 발행됐고 텔레그램도 나갔습니다.\n"
        "   뒤 회차(17:20·17:50·18:20)가 진짜 해석글로 자동 재시도합니다.\n"
        "   ⚠️ 18:20까지도 이 알림이 계속 오면 API 키·잔액과\n"
        "      Actions → '해석글 생성 (Claude)' 로그를 확인하세요."
    ),
    "incomplete": (
        "⏳ 잠정 데이터로 발행했습니다",
        "수급 확정 전(18시 이전)에 발행돼서 일부 숫자가 잠정치일 수 있습니다.\n\n"
        "✅ 조치: 리포트는 정상 발행됐고, **다음 회차가 자동으로 다시 발행**합니다.\n"
        "   (17:20 / 17:50 / 18:20 중 데이터가 완전해지는 시점)\n"
        "   형이 따로 손댈 건 없습니다. 확정본으로 덮어써집니다.\n\n"
        "⚠️ 만약 18:20까지도 이 알림이 계속 오면 수집원 장애를 의심하세요."
    ),
    "collect_fail": (
        "🔴 데이터 수집이 실패했습니다",
        "collect_data.py 가 정상 종료하지 못했습니다.\n\n"
        "✅ 조치: 이후 단계를 모두 건너뛰었습니다.\n"
        "   Actions → '시장 데이터 수집' 로그의 Traceback을 확인하세요."
    ),
}


def send(text):
    if not TOKEN or not CHAT_ID:
        print("⚠️ 텔레그램 설정 없음 — 알림을 보내지 못했습니다.")
        print(text)
        return False
    try:
        import requests
        r = requests.post(
            f"https://api.telegram.org/bot{TOKEN}/sendMessage",
            json={"chat_id": CHAT_ID, "text": text,
                  "parse_mode": "HTML", "disable_web_page_preview": True},
            timeout=15)
        ok = r.status_code == 200
        print(("✅ 운영자 알림 발송" if ok else f"❌ 발송 실패 {r.status_code} {r.text[:200]}"))
        return ok
    except Exception as e:
        print(f"❌ 발송 예외 — {type(e).__name__}: {e}")
        return False


def main():
    사유 = (sys.argv[1] if len(sys.argv) > 1 else "no_interp").strip()
    상세 = " ".join(sys.argv[2:]).strip()

    제목, 본문 = 안내표.get(사유, ("⚠️ 발행 중단", "알 수 없는 사유로 발행을 멈췄습니다."))
    본문 = 본문.format(d=DATE)

    _요일 = "월화수목금토일"[datetime.strptime(DATE, "%Y%m%d").weekday()]
    _날짜 = f"{DATE[:4]}.{DATE[4:6]}.{DATE[6:]}({_요일})"

    줄 = [f"<b>{제목}</b>", f"차트프로 관제탑 · {_날짜}", ""]
    if 상세:
        줄.append(f"<b>감지 내용</b>\n{상세}\n")
    줄.append(본문)
    줄.append("")
    줄.append(f"<i>구독자에게는 아무것도 발송되지 않았습니다.</i>")
    줄.append(f"{SITE_URL}  [{SCRIPT_VERSION}]")

    if not ADMIN_ID and FALLBACK:
        print("⚠️ TELEGRAM_ADMIN_CHAT_ID가 없어 기존 방으로 보냅니다. "
              "구독자방이라면 반드시 운영자 전용 방을 따로 만드세요.")

    send("\n".join(줄))


if __name__ == "__main__":
    main()
