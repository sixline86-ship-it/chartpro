# -*- coding: utf-8 -*-
"""🧠 테마 해설 생성 — 차트프로 관제탑 (2026-10-04 신설)

[무엇] 테마 탭 챕터마다 «💡 해석과 판단»을 Claude가 매일 새로 쓴다.
       (탭 맨 위 종합 해설 칸은 2026-10-04 HO 지시로 뺐다)
       결과 = archive/theme_notes_YYYYMMDD.json
[왜]   9/23에 한 번 손으로 만든 해설 파일만 있고 매일 만드는 장치가 없었다.
       그래서 9/24부터 해설이 조용히 사라졌다(HO 2026-10-04 지적).
[어떻게]
  ① build_html의 theme_chapter_texts()로 테마 탭을 한 번 그려 보며
     챕터별 «화면에 실제로 보이는 글자»를 모은다 → 해설이 화면과 다른 말을 못 한다.
  ② 그 글자만 재료로 Claude에게 JSON을 받는다.
  ③ 형식이 틀린 칸은 버리고, 남은 것만 저장한다(빈칸은 화면에서 조용히 빠진다).
[언제] generate_report.py가 해석글을 만든 직후 부른다 → «새로 생성(과금)»일 때만 돈다.
       재사용 실행에서는 아침에 만든 파일을 그대로 쓴다.
[단독 실행] python theme_notes.py          → 생성
            python theme_notes.py --dry    → API 없이 재료만 theme_notes_facts.json으로 저장(점검용)
"""
import json
import os
import re
import sys
import time

SCRIPT_VERSION = "v2026.10.04-a"

SYSTEM = """너는 «차트프로 관제탑» 리포트의 테마 해설가다. 독자는 주식 초보~중급 개인투자자다.
입력은 오늘 리포트 «테마 탭»의 챕터별 화면 글자다(숫자·순위·테마 이름이 그대로 들어 있다).
이걸 읽고 챕터별 «해석과 판단»을 쓴다.

[절대 규칙]
1. 숫자·테마 이름·종목 이름은 입력에 있는 것만 쓴다. 새 숫자를 계산하거나 지어내지 않는다.
   입력에 없는 뉴스·사건·이유를 상상해서 붙이지 않는다. 모르면 쓰지 않는다.
2. «사세요/파세요/매수/매도 추천/목표가/오를 것이다»처럼 단정하거나 권하는 말은 쓰지 않는다.
   대신 «무엇이 보이면 어느 쪽인지»를 조건으로 말한다(예: "내일 돈이 또 늘면 ~, 줄면 ~").
3. 말투는 친절한 ~요체. 한 문장 45자 안팎, 한 문장에 숫자는 2개까지.
   어려운 말은 쉬운 말로 바꾼다: «4일 누적 점수» → «최근 4일 합산 점수», «확산도» → «테마 안에서 같이 오른 종목 비율».
4. 코드 용어(null, key, 키 이름, 영어 변수)는 절대 쓰지 않는다.
5. 챕터 글자가 «대기/아직 없음/기록 쌓는 중»뿐이면 그 챕터 해설은 만들지 않는다(키를 빼라).
6. 같은 말을 여러 챕터에서 반복하지 않는다. 챕터 해설은 «그 챕터에서만 보이는 것»을 짚는다.
7. 진짜 중요한 포인트 하나에 집중한다. 나열보다 해석.
8. «점수»·«점»·«합산 점수»·«하루 +3.5점» 같은 내부 점수 숫자는 절대 쓰지 않는다(구독자는 무슨 뜻인지 모른다).
   대신 순위·순위 변화(«12위 → 내일 10위 안»)·속도(«빠르게/천천히 올라오는 중»)·거래대금 변화로 말한다.
   (🔴 2026-10-06 HO 지시 — 다가오는 테마 해설에 점수 얘기가 나와 이해가 안 됐다)

[챕터 해설 형식 — 아래 기호만 쓴다]
> 한 줄 결론(이 챕터가 오늘 말하는 것)
@ 아이콘 제목 | 이름이나 숫자 | 짧은 설명      ← 2~4줄. 같은 무리/사실 카드
### 👉 판단
- 2~3개. «그래서 독자는 무엇을 보면 되나». 조건형으로.
! 주의 한 줄(표본이 적다, 하루치다 등 — 있을 때만)
· 굵게는 **글**. 색 강조는 {빨강:글} {파랑:글} {노랑:글} {초록:글} {주황:글} 만 (빨강=오름/들어옴, 파랑=내림/빠짐).

[출력] JSON 하나만. 설명·코드블록 표시 없이.
{"노트": {"챕터키": "해설 본문(위 형식, 줄바꿈은 \\n)", ...}}
노트의 챕터키는 입력에 온 키 이름을 그대로 쓴다."""

CHAPTER_NAMES = {
    "레이더": "📡 테마 레이더(최근 4일 합산 1~10위, 이야기 묶음 포함)",
    "생존": "⏳ 테마들 평균 수명(10위권에 며칠 머무나)",
    "돈의이동": "🌊 돈의 이동 경로(테마별 최근 10거래일 순위 길 — 어디서 올라와 어디로 빠졌나)",
    "다가오는": "🛬 다가오는 테마(11~20위, 올라오는 속도)",
    "거꾸로": "🌊 물 밑에서 돈 들어오는 테마(20위 밖인데 돈이 느는 곳)",
    "섹터테마": "🗺️ 섹터 × 테마",
    "짝꿍": "🔗 테마 짝꿍(같이 움직이는 테마)",
    "오늘뜬": "🏆 오늘 뜬 테마(오늘 하루 기준)",
    "채점판": "📊 테마 채점판(앞서 지목한 테마의 그 뒤)",
    "판단-순환": "🔄 테마 수명표(판단 탭 — 테마별 지금 어느 단계)",
    "판단-성과": "🎯 자리별 실제 성과(판단 탭)",
    "판단-엇갈림": "⚡ 엇갈리는 신호(판단 탭)",
}


def _facts():
    import build_html as B
    data = B.load_json(B.DATA_PATH)
    if not data:
        raise RuntimeError(f"{B.DATA_PATH} 없음")
    B.prep_data(data)
    report = B.load_json(B.REPORT_PATH)
    return B, B.theme_chapter_texts(data, report)


def _clean(obj, keys):
    """형식이 틀린 칸은 버린다 — 반쯤 깨진 해설을 내보내느니 빈칸이 낫다."""
    out = {}
    n = obj.get("노트") if isinstance(obj, dict) else None
    if isinstance(n, dict):
        nn = {}
        for k, v in n.items():
            if k in keys and isinstance(v, str) and v.strip():
                if re.search(r"\bnull\b|undefined|NaN", v):
                    continue
                nn[k] = {"해석": v.strip()}
        out["노트"] = nn
    return out


def run(client=None, model=None, dry=False):
    t0 = time.time()
    B, facts = _facts()
    print(f"🧠 테마 해설 재료: 챕터 {len(facts)}개 · {sum(len(v) for v in facts.values()):,}자 "
          f"({time.time()-t0:.0f}초)")
    if dry:
        with open("theme_notes_facts.json", "w", encoding="utf-8") as f:
            json.dump(facts, f, ensure_ascii=False, indent=1)
        print("   (--dry) theme_notes_facts.json 저장 — API는 부르지 않았습니다")
        return None
    if not facts:
        print("   ⚠️ 재료가 없습니다(테마 수집 실패일 수 있음) — 해설을 만들지 않습니다")
        return None
    if client is None:
        import anthropic
        client = anthropic.Anthropic()
    model = model or "claude-sonnet-5"
    body = "\n\n".join(f"### [{k}] {CHAPTER_NAMES.get(k, k)}\n{v}" for k, v in facts.items())
    msg = (f"오늘 날짜: {B.DATE}\n아래는 오늘 테마 탭 챕터별 화면 글자다. "
           f"챕터키 = 대괄호 안 이름.\n\n{body}")
    kw = dict(model=model, max_tokens=16000, system=SYSTEM,
              messages=[{"role": "user", "content": msg}])
    if model in ("claude-sonnet-5", "claude-opus-4-8", "claude-fable-5"):
        kw["output_config"] = {"effort": "medium"}
    obj = None
    for 시도 in (1, 2):
        with client.messages.stream(**kw) as st:
            resp = st.get_final_message()
        raw = "".join(getattr(b, "text", "") for b in resp.content if getattr(b, "type", "") == "text")
        _u = getattr(resp, "usage", None)
        if _u is not None:
            print(f"   🧾 토큰: 입력 {getattr(_u, 'input_tokens', 0):,} · 출력 {getattr(_u, 'output_tokens', 0):,}")
        m = re.search(r"\{.*\}", raw, re.S)
        try:
            obj = json.loads(m.group(0) if m else raw)
            break
        except Exception:
            print(f"   ⚠️ JSON 형식이 아닙니다 ({시도}/2)" + (" — 한 번 더 시도" if 시도 == 1 else ""))
            kw["max_tokens"] = 24000
    if obj is None:
        raise RuntimeError("테마 해설 JSON 파싱 실패")
    out = _clean(obj, set(facts))
    out = {"날짜": B.DATE, "버전": SCRIPT_VERSION, **out}
    path = B.asave(B.THEME_NOTES_FILE)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    print(f"   ✅ 테마 해설 저장 → {path} (챕터 {len(out.get('노트') or {})}개 · {time.time()-t0:.0f}초)")
    return out


if __name__ == "__main__":
    run(dry="--dry" in sys.argv)
