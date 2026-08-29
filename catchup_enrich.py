# ============================================================
# catchup_enrich.py  (v2026.08.29-a2)
# ------------------------------------------------------------
#  「몰아 모으기」 — 발행 파이프라인과 완전히 분리된 수집 전용 스크립트.
#
#  🎯 왜 필요한가
#     매일 발행(daily.yml)은 16:50까지 끝나야 해서 할당량을 작게 유지해야
#     한다(기업 프로필 20종목·사업보고서 2건·종목뉴스 10종목). 이 속도로는
#     상장사 3,957개를 다 채우는 데 몇 달~몇 년이 걸린다.
#
#     그런데 "빨리 모으는" 것과 "매일 제시간에 발행하는" 것은 서로 다른
#     제약이다. 이 스크립트는 발행에 안 쓰이므로 시간제한이 없다 —
#     GitHub Actions 무료 한도(6시간) 안에서 원하는 만큼 크게 돌릴 수 있다.
#
#  ⚠️ 이 스크립트는 daily.yml이 아니라 **별도 workflow(enrich.yml)**에서만
#     실행된다. 평소 발행에는 전혀 관여하지 않는다.
#  ⚠️ 레이더 목록을 비워서(`[]`) 넘긴다 — 그러면 각 collect_* 함수가 스스로
#     "레이더에 안 잡힌 나머지"를 채우는 기존 로직(폴백)을 그대로 탄다.
#  ⚠️ 동시 실행 주의 — 발행이 도는 중에 이 스크립트를 같이 돌리면 같은
#     json 파일을 둘이 동시에 써서 git push가 충돌할 수 있다. **발행이
#     끝난 뒤(예: 저녁 늦게나 주말)에 돌리는 걸 권장한다.**
# ============================================================
import os
import sys

SCRIPT_VERSION = "v2026.08.29-a2"

# ⚠️ collect_data.py의 세 할당량은 import 시점이 아니라 **모듈 속성**으로
#    존재하므로, import 뒤에 직접 덮어써도 된다(환경변수를 미리 안 깔아도 됨).
#    다만 명시성을 위해 환경변수도 같이 설정해 둔다.
os.environ.setdefault("CP_PROFILE_QUOTA", "300")
os.environ.setdefault("CP_BIZ_QUOTA", "40")
os.environ.setdefault("CP_SNEWS_QUOTA", "150")

import collect_data as cd  # noqa: E402  (환경변수를 먼저 깔아야 하므로 뒤에 import)

# 명시적으로 한 번 더 덮어쓴다(다른 스크립트가 이미 import해 캐시된 상황 방지).
cd.PROFILE_하루할당 = int(os.environ["CP_PROFILE_QUOTA"])
cd.BIZ_하루할당 = int(os.environ["CP_BIZ_QUOTA"])
cd.SNEWS_하루할당 = int(os.environ["CP_SNEWS_QUOTA"])


def main():
    print(f"🚀 몰아 모으기 시작 [{SCRIPT_VERSION}] — "
          f"프로필 {cd.PROFILE_하루할당} · 사업보고서 {cd.BIZ_하루할당} · "
          f"종목뉴스 {cd.SNEWS_하루할당}")

    if not cd.DART_KEY:
        print("❌ DART_API_KEY가 없습니다 — 아무것도 못 합니다.")
        sys.exit(1)

    지도 = cd.build_corp_map()
    print(f"📇 corp_map {len(지도)}건")

    try:
        cd.collect_stock_profiles([], {})
    except Exception as e:
        print(f"⚠️ 프로필 수집 실패 — {type(e).__name__}: {e}")

    try:
        cd.collect_biz_reports([])
    except Exception as e:
        print(f"⚠️ 사업보고서 수집 실패 — {type(e).__name__}: {e}")

    try:
        코드지도 = cd.build_stock_code_map()
        print(f"📇 종목코드 지도 {len(코드지도)}건")
        cd.collect_stock_news_raw([], 코드지도)
    except Exception as e:
        print(f"⚠️ 종목뉴스 수집 실패 — {type(e).__name__}: {e}")

    print("🏁 몰아 모으기 종료")


if __name__ == "__main__":
    main()
