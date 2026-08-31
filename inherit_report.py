# ============================================================
# inherit_report.py  (v2026.08.30-a1)
# ------------------------------------------------------------
#  오늘 해석글(archive/report_YYYYMMDD.json)이 없을 때
#  **가장 최근 거래일의 해석글을 그대로 승계**한다.
#
#  왜 필요한가 — 예전에는 해석글이 없으면 워크플로가 텔레그램 발송과
#  index.html 갱신을 통째로 막았다. 발행이 "멈춘" 것처럼 보였고,
#  실제로 하루가 통으로 비었다. 숫자·표는 전부 정상인데도 그랬다.
#
#  📌 원칙 — 발행은 하되, **어제 글이라는 사실을 숨기지 않는다.**
#     `승계원본` 필드를 심어두면 build_html.py가 리포트 맨 위에
#     "이 글은 ○/○ 것입니다" 배너를 띄운다.
#
#  ⚠️ 이건 **임시 조치**다. 승계본이 올라간 날은 뒤 회차(17:20·17:50·18:20)가
#     다시 돌아 진짜 해석글로 덮어써야 한다. daily.yml의 중복 방지 가드가
#     `승계원본`을 보고 "아직 정상 발행 전"으로 취급하도록 해뒀다.
#
#  ⚠️ 이미 오늘 해석글이 있으면 **아무것도 하지 않는다.** 진짜 글을
#     승계본으로 덮어쓰는 사고를 막기 위해 이 순서를 반드시 지킨다.
# ============================================================
import json
import os
import re
import sys
from datetime import datetime

SCRIPT_VERSION = "v2026.08.30-a1"   # ⬅ 다른 파일과 항상 같아야 한다.

ARCHIVE = "archive"
DATE = os.environ.get("CP_DATE") or datetime.now().strftime("%Y%m%d")
TODAY_PATH = os.path.join(ARCHIVE, f"report_{DATE}.json")

# 최대 며칠 전까지 거슬러 올라갈지. 이보다 오래된 글은 시황이 완전히 달라져
# 승계해도 도움이 안 된다 — 차라리 핵심편을 비우고 사실을 알리는 게 낫다.
MAX_BACK_DAYS = 5


def main():
    if os.path.exists(TODAY_PATH):
        print(f"✅ 오늘 해석글이 이미 있습니다 — 승계하지 않습니다 ({TODAY_PATH})")
        print("inherited=no")
        return 0

    if not os.path.isdir(ARCHIVE):
        print(f"⚠️ archive 폴더가 없습니다 — 승계 불가")
        print("inherited=no")
        return 0

    후보 = sorted(
        (f for f in os.listdir(ARCHIVE) if re.fullmatch(r"report_\d{8}\.json", f)),
        reverse=True)

    for f in 후보:
        ymd = f[7:15]
        if ymd >= DATE:
            continue                      # 미래·오늘 파일은 건너뛴다
        try:
            _d0 = datetime.strptime(ymd, "%Y%m%d")
            _dn = datetime.strptime(DATE, "%Y%m%d")
        except ValueError:
            continue
        if (_dn - _d0).days > MAX_BACK_DAYS:
            print(f"⚠️ 가장 최근 해석글이 {ymd}로 {MAX_BACK_DAYS}일보다 오래됐습니다 — "
                  f"승계하지 않습니다(오래된 시황은 도움이 안 됩니다).")
            break
        try:
            with open(os.path.join(ARCHIVE, f), encoding="utf-8") as fp:
                원본 = json.load(fp)
        except Exception as e:
            print(f"   ⚠️ {f} 읽기 실패 — {type(e).__name__}. 그 앞 날짜를 봅니다.")
            continue

        if not (원본.get("해석글") or {}).get("핵심편"):
            print(f"   ⚠️ {f}에 핵심편이 없습니다. 그 앞 날짜를 봅니다.")
            continue

        # ⚠️ 승계본임을 반드시 남긴다. 이 필드 하나가
        #    ① 화면 배너 ② 워크플로 재시도 판정 둘 다를 움직인다.
        원본["승계원본"] = ymd
        원본["승계시각"] = datetime.now().strftime("%Y-%m-%d %H:%M")
        원본["날짜"] = DATE

        with open(TODAY_PATH, "w", encoding="utf-8") as fp:
            json.dump(원본, fp, ensure_ascii=False, indent=1)

        print(f"🔁 해석글 승계 — {ymd} 글을 오늘({DATE}) 자리에 넣었습니다.")
        print(f"   화면에 '{ymd[4:6]}/{ymd[6:]} 글' 배너가 표시됩니다.")
        print(f"   뒤 회차가 진짜 해석글로 덮어씁니다. [{SCRIPT_VERSION}]")
        print(f"inherited=yes from={ymd}")
        return 0

    print("⚠️ 승계할 해석글을 찾지 못했습니다 — 핵심편 없이 발행됩니다.")
    print("inherited=no")
    return 0


if __name__ == "__main__":
    sys.exit(main())
