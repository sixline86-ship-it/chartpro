# watchdog.py
# ============================================================
# 🐕 저녁 정식 발행 누락 감시 — 2026-09-29 신설
# ------------------------------------------------------------
#  [사고] 9/28 저녁 cron-job.org 3회(18:07·18:27·18:47)가 흔적 없이
#    돌지 않았다. 아무 알림도 없어 다음 날 아침에야 알았고, 그 사이
#    장중(14:10) 잠정 데이터가 그날 기록으로 남았다.
#  [하는 일] 19:30쯤 한 번 불려서 «오늘이 거래일인데 정식 발행이
#    끝났나?»만 본다. 안 끝났으면 운영자(형)에게만 텔레그램을 보낸다.
#    ⚠️ 아무것도 고치거나 쓰지 않는다 — 읽고, 알리기만 한다.
#
#  정식 발행 완료의 기준 (셋 다 만족해야 한다)
#    ① archive/report_오늘.json 이 있다        (해석글이 있다)
#    ② 그 안에 «승계원본»이 없다               (남의 날 글을 빌린 게 아니다)
#    ③ archive/data_오늘.json 의 완전 = true   (18시 이후 확정 데이터다)
# ============================================================
import json
import os
import subprocess
import sys
from datetime import datetime

# ⚠️ collect_data.py · inherit_report.py 와 같은 목록. 셋을 함께 고친다.
_KRX_휴장 = {
    "20260101", "20260216", "20260217", "20260218", "20260302", "20260501",
    "20260505", "20260525", "20260603", "20260717", "20260817", "20260924",
    "20260925", "20261005", "20261009", "20261225", "20261231",
}

DATE = os.environ.get("CP_DATE") or datetime.now().strftime("%Y%m%d")


def _알림(사유, 상세):
    print(f"📮 운영자 알림 — {사유}: {상세}")
    subprocess.run([sys.executable, "notify_admin.py", 사유, 상세], check=False)


def main():
    # 12월 20일부터 내년 목록이 들어 있는지 본다 (없으면 1월 1일부터 구멍).
    # 목록 추가는 매년 12월 8일 Claude 예약 작업이 파일을 만들어 형에게 보낸다.
    # 이 알림은 그게 빠졌을 때의 안전망이다.
    if DATE[4:6] == "12" and int(DATE[6:]) >= 20:
        내년 = str(int(DATE[:4]) + 1)
        if not any(d.startswith(내년) for d in _KRX_휴장):
            _알림("holiday_list", f"{내년}년 휴장일 목록이 없습니다.")

    요일 = datetime.strptime(DATE, "%Y%m%d").weekday()
    if 요일 >= 5 or DATE in _KRX_휴장:
        print(f"😴 {DATE}는 휴장일 — 감시할 발행이 없습니다.")
        return 0

    문제 = []
    rp = os.path.join("archive", f"report_{DATE}.json")
    dp = os.path.join("archive", f"data_{DATE}.json")

    if not os.path.exists(rp):
        문제.append("해석글(report) 없음")
    else:
        try:
            with open(rp, encoding="utf-8") as f:
                r = json.load(f)
            if r.get("승계원본"):
                문제.append(f"해석글이 {r['승계원본']} 글을 빌린 승계본")
        except Exception as e:
            문제.append(f"해석글 읽기 실패 — {type(e).__name__}")

    if not os.path.exists(dp):
        문제.append("데이터(data) 없음")
    else:
        try:
            with open(dp, encoding="utf-8") as f:
                d = json.load(f)
            완전성 = d.get("데이터완전성") or {}
            if 완전성.get("완전") is not True:
                사유 = " · ".join(완전성.get("사유") or []) or "사유 미상"
                문제.append(f"데이터 미완 — {사유}")
        except Exception as e:
            문제.append(f"데이터 읽기 실패 — {type(e).__name__}")

    if 문제:
        _알림("missing_publish", " / ".join(문제))
    else:
        print(f"✅ {DATE} 정식 발행 정상 완료 — 알림 없음")
    return 0


if __name__ == "__main__":
    sys.exit(main())
