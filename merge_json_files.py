# merge_json_files.py
# ------------------------------------------------------------
# 🆕 2026-08-29 — daily.yml(매일 발행)과 enrich.yml(몰아 모으기)이
# 같은 JSON 파일(stock_profile·biz_report_raw·stock_news_raw·corp_map·
# corp_stockcode·biz_report_fail·stock_news_fail)에 각자 다른 종목을
# 추가하다가, git의 줄 단위 rebase가 "CONFLICT (content)"로 막히는
# 사고가 실측 확인됐다(enrich.yml 17분 실행분이 이 이유로 통째로 소실).
#
# 이 스크립트는 git한테 병합을 맡기지 않고, 두 실행이 각각 만든 JSON을
# 딕셔너리 수준에서 직접 합친다:
#   최종 결과 = 원격(origin/main)의 최신본 + 이 실행이 로컬에서 새로
#              만든 항목
# 두 실행이 서로 다른 종목을 추가했을 뿐이라면 이 방식은 절대 충돌이
# 안 난다. 같은 키를 양쪽이 동시에 건드린 경우에만 로컬(이번 실행) 값이
# 우선한다 — 방금 이 실행이 실제로 확인한 값이 더 최신이라서다.
#
# ⚠️ YAML의 run: 블록 안에 heredoc으로 파이썬을 직접 넣었더니
#    (a) YAML 블록 스칼라 들여쓰기 규칙과 (b) 파이썬 최상위 코드는
#    들여쓰면 안 된다는 규칙이 서로 충돌해 두 번 다 깨졌다.
#    → 아예 별도 파일로 분리하는 게 안전하다는 걸 실측으로 배웠다.
import json
import subprocess

FILES = [
    "stock_profile.json",
    "corp_map.json",
    "corp_stockcode.json",
    "biz_report_raw.json",
    "stock_news_raw.json",
    "biz_report_fail.json",
    "stock_news_fail.json",
    # 🆕 2026-08-31 — 사업 포트폴리오 2단계 파서가 만드는 두 파일.
    #    daily.yml은 안 건드리지만(enrich.yml 전용), enrich.yml을
    #    연달아 두 번 돌리는 경우엔 여기서도 같은 충돌이 날 수 있어
    #    같은 방식으로 병합 대상에 넣는다.
    "biz_portfolio.json",
    "biz_portfolio_fail.json",
    # 🆕 2026-09-01 — 기업 설명 2단계 파서가 만드는 두 파일. 같은 이유로
    #    (enrich.yml 연달아 두 번 돌릴 때 충돌 방지) 병합 대상에 넣는다.
    "biz_description.json",
    "biz_description_fail.json",
]


def main():
    for fn in FILES:
        try:
            with open(fn, encoding="utf-8") as f:
                local = json.load(f)
        except FileNotFoundError:
            continue
        try:
            remote_raw = subprocess.run(
                ["git", "show", f"origin/main:{fn}"],
                capture_output=True, text=True, check=True,
            ).stdout
            remote = json.loads(remote_raw) if remote_raw.strip() else {}
        except Exception:
            remote = {}
        if remote == local:
            continue
        merged = {**remote, **local}  # 이번 실행이 새로 만든 값이 우선
        with open(fn, "w", encoding="utf-8") as f:
            json.dump(merged, f, ensure_ascii=False, separators=(",", ":"))
        print(f"  🔀 {fn}: 원격 {len(remote)} + 로컬 {len(local)} → 병합 {len(merged)}")


if __name__ == "__main__":
    main()
