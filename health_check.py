# health_check.py
# ============================================================
# 🩺 수집 건강검진 — 2026-10-22 신설 (HO «자꾸 주소가 바뀌어 데이터가 꼬인다 — 문제 있을 때마다 꼭 알려줘»)
# ------------------------------------------------------------
#  [사고] 10/21부터 네이버가 종목별 수급 주소를 없애서 매집 레이더가 «0종목»이 됐는데
#    이틀 동안 아무 알림이 없었다. 지금까지 알림은 «테마 실패», «지수 수급 실패»처럼
#    한 번 터진 곳마다 따로 붙인 방식이라, 새로 깨지는 곳은 항상 놓친다.
#  [하는 일] 오늘 data_오늘.json 의 모든 항목(1·2단계)의 «개수»를 최근 거래일 평소와 비교해서
#    평소엔 꽤 있던 게 갑자기 0이거나 크게 줄었으면 운영자에게만 텔레그램을 보낸다.
#    + 종목별 수급 이력(stock_flow_history.json)이 최신 날짜에 비어 있는지도 본다(이번 사고의 뿌리).
#  ⚠️ 읽고 알리기만 한다. 아무것도 고치거나 쓰지 않는다. 실패해도 발행은 막지 않는다.
#  ⚠️ 시장이 조용해서 진짜 0인 항목(강세 신규 포착처럼 평소에도 0~2개)은 건드리지 않도록
#     «평소 중앙값이 MIN_BASE 이상인 항목»만 본다.
# ============================================================
import glob
import json
import os
import statistics
import subprocess
import sys
from datetime import datetime

DATE = os.environ.get("CP_DATE") or datetime.now().strftime("%Y%m%d")
LOOKBACK = 7          # 비교할 직전 발행 일수
MIN_BASE = 5          # 평소 중앙값이 이보다 작으면 «원래 적은 항목» → 감시하지 않음
DROP_RATIO = 0.25     # 평소의 25% 아래로 떨어지면 이상
SKIP = {"추적", "기록", "이력", "격자", "종목사전", "meta", "설명",
        "장기기준일범위", "공시날짜"}   # 누적형·사전형·날짜 목록 — 하루 개수가 의미 없음


def _size(v):
    if isinstance(v, (list, dict, str)):
        return len(v)
    return 0 if v in (None, False) else 1


def _flatten(d):
    """{'매집레이더.중기종목': 67, ...} — 1·2단계만."""
    out = {}
    for k, v in (d or {}).items():
        if k in SKIP:
            continue
        out[k] = _size(v)
        if isinstance(v, dict):
            for k2, v2 in v.items():
                if k2 in SKIP or not isinstance(v2, (list, dict)):
                    continue
                out[f"{k}.{k2}"] = _size(v2)
    return out


def _load(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def 점검(date, archive="archive"):
    """date 날짜의 이상 항목 목록 [(이름, 오늘, 평소중앙값)] 을 돌려준다."""
    today = _load(os.path.join(archive, f"data_{date}.json"))
    if today is None:
        return None
    prev = sorted(p for p in glob.glob(os.path.join(archive, "data_2*.json"))
                  if os.path.basename(p)[5:13] < date)[-LOOKBACK:]
    hist = [_flatten(_load(p)) for p in prev if _load(p) is not None]
    if len(hist) < 3:
        return []
    now = _flatten(today)
    이상 = []
    for name in sorted({k for h in hist for k in h}):
        vals = [h.get(name, 0) for h in hist]
        base = statistics.median(vals)
        if base < MIN_BASE:
            continue
        n = now.get(name, 0)
        if n <= base * DROP_RATIO:
            이상.append((name, n, base))
    return 이상


def 수급이력점검(path="stock_flow_history.json"):
    """종목별 수급 이력의 가장 최근 두 날짜가 둘 다 비었으면 이상(발행 시각에 따라 맨 끝 하루는 늦을 수 있다)."""
    f = _load(path)
    if not f:
        return None
    날짜들 = [d for d in (f.get("날짜들") or []) if isinstance(d, str)]
    if len(날짜들) < 6:
        return None
    종목 = f.get("종목") or {}
    cnt = {d: sum(1 for v in 종목.values() if isinstance(v, dict) and v.get(d)) for d in 날짜들[-8:]}
    기준 = statistics.median([cnt[d] for d in 날짜들[-8:-2]]) if len(날짜들) >= 8 else max(cnt.values())
    if 기준 < 30:
        return None
    최근2 = 날짜들[-2:]
    if all(cnt[d] <= 기준 * 0.5 for d in 최근2):
        return f"종목별 수급 이력 — 최근 {최근2[0]}·{최근2[1]} 모두 {cnt[최근2[0]]}·{cnt[최근2[1]]}종목 (평소 약 {int(기준)}종목)"
    return None


def main():
    문제 = []
    이상 = 점검(DATE)
    if 이상 is None:
        print(f"⚠️ archive/data_{DATE}.json 을 읽지 못해 검진을 건너뜁니다.")
        return 0
    # 0이 아닌 «감소»는 첫날만 알린다(기준을 일부러 바꾼 날처럼 며칠 이어지는 잡음 방지).
    # 0이 된 항목은 계속 알린다 — 고장이면 고칠 때까지 매일 울려야 한다.
    전날 = sorted(p for p in glob.glob(os.path.join("archive", "data_2*.json"))
                 if os.path.basename(p)[5:13] < DATE)
    if 전날:
        어제이상 = {n for n, _, _ in (점검(os.path.basename(전날[-1])[5:13]) or [])}
        이상 = [(n, a, b) for n, a, b in 이상 if a == 0 or n not in 어제이상]
    for name, n, base in 이상:
        문제.append(f"{name}: 오늘 {n} (최근 평소 {base:g})")
    m = 수급이력점검()
    if m:
        문제.append(m)
    if not 문제:
        print("✅ 수집 건강검진 — 이상 없음")
        return 0
    msg = ("평소엔 꽤 있던 항목이 갑자기 비었거나 크게 줄었습니다. 네이버 등 외부 주소가 바뀌었을 수 있습니다.\n"
           + "\n".join(f"• {x}" for x in 문제[:12])
           + ("\n…외 %d건" % (len(문제) - 12) if len(문제) > 12 else ""))
    print("🩺 " + msg)
    subprocess.run([sys.executable, "notify_admin.py", "health", msg], check=False)
    return 0


if __name__ == "__main__":
    sys.exit(main())
