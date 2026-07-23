# ============================================================
# generate_report.py  (v2)
# ------------------------------------------------------------
# 목적: collect_data.py 가 만든 data_YYYYMMDD.json 을 읽어서
#       Claude API에게 해석 글을 써 달라고 요청한다.
# 결과: report_YYYYMMDD.json  (숫자 + 해석글)
#
# 만드는 글 5가지:
#   한줄평 / 오늘의_시장 / 오늘의_한문장 / 침묵의_지표 / 오늘의_공부
# ============================================================

import json
import os
import sys
import time
from datetime import datetime
import anthropic  # pip install anthropic

DATE = datetime.now().strftime("%Y%m%d")
DATA_PATH = f"data_{DATE}.json"
REPORT_PATH = f"report_{DATE}.json"

# ── 사용할 모델 선택 ────────────────────────────────────
# 아래 4개 중 쓰고 싶은 것의 # 를 지우고, 나머지는 # 를 붙이면 된다.
# (가격은 입력/출력 100만 토큰당. 2026년 7월 기준)
MODEL = "claude-sonnet-5"      # $2/$10 도입가 · 속도·지능 균형 (추천 기본값)
# MODEL = "claude-opus-4-8"    # $5/$25 · 복잡한 작업용 (약 2.5배 비용)
# MODEL = "claude-fable-5"     # $10/$50 · 최상위 (약 5배 비용)
# MODEL = "claude-haiku-4-5"   # $1/$5  · 가장 저렴·빠름 (품질 테스트용)

# API 키는 환경변수 ANTHROPIC_API_KEY 에서 자동으로 읽힌다
client = anthropic.Anthropic()


SYSTEM_PROMPT = """\
너는 주식 시황 리포트 "차트프로 관제탑"의 해설 작가다.
아래 규칙을 반드시 지켜라.

1. 숫자는 절대 지어내지 않는다. 입력으로 주어진 JSON 데이터에 있는 숫자만 사용한다.
2. 데이터에 없는 값은 "확인 필요"라고 쓰고 임의로 채우지 않는다.
3. 확정적인 투자 권유("반드시 오른다", "사야 한다" 등)는 쓰지 않는다.
   전망이 필요하면 조건문(If-Then)으로 쓴다.
4. 문장은 친절하고 담백하게, 초보 투자자도 이해할 수 있게 쓴다.
   과장·신파·상투어는 피한다.
5. 반드시 아래 JSON 형식으로만 답한다. 그 외 설명이나 인사말은 절대 넣지 않는다.

각 항목 작성 지침:
- 한줄평: 오늘 시장의 특징을 한 문장(공백 포함 40자 이내)으로 압축. 관제지수 옆에 붙는 짧은 총평.
- 오늘의_시장: 지수·수급·주도섹터 숫자를 근거로 한 2~3문장 총평.
- 오늘의_한문장: 오늘 시장이 준 '교훈'을 격언처럼 한 문장으로. 오래 기억에 남을 만큼
  담백하고 묵직하게. 수치·종목명 없이 통찰만.
- 침묵의_지표: 표면적 등락 뒤에 숨은 수급·심리 해석 2~3문장.
- 오늘의_공부: 오늘 데이터와 연결되는 투자 개념 하나를 쉽게 설명 2~3문장.
- 핵심이슈: 입력된 '뉴스원본' 제목들을 보고, 오늘 시장을 움직인 굵직한 이슈 3~4개를 뽑아
  각각 태그(반도체/정책/수급/글로벌 등 적절히)와 1~2문장 설명으로 정리.
- 핵심뉴스: 입력된 '뉴스원본'을 최대 10개까지 정리한다.
  ⚠️ 매우 중요 — 절대 규칙:
    1) 제목이 겹치거나 같은 사안을 다루면 하나로 합친다.
    2) 각 항목에 태그를 붙인다: 시황 / 정책 / 특징주 / 글로벌 중 하나.
    3) 2~3문장으로 요약하되 직접 브리핑하듯 자연스럽게 쓴다("~했습니다" 체).
    4) "링크"는 입력된 '뉴스원본'의 링크를 글자 하나 틀리지 않고 그대로 복사한다.
       링크를 새로 만들거나 추측하거나 변형하는 것은 절대 금지.
       합쳐진 여러 기사 중에서는 대표로 하나의 원본 링크만 사용한다.
    5) '뉴스원본'이 비어 있으면 핵심이슈·핵심뉴스는 빈 배열 [] 로 둔다. 지어내지 않는다.

── 톤 예시 (이 결을 따를 것. 그대로 베끼지는 말 것) ──

[한줄평 예시]
- "반도체발 수급 사고, 양대 시장 사이드카"
- "지수는 올랐지만, 오른 종목은 적었다"
- "외국인이 돌아온 하루, 다만 조용하게"

[오늘의_한문장 예시]
- "급등도 급락도, 결국 같은 수급 쏠림의 양면이다."
- "지수가 오른 날과 내 계좌가 오른 날은 다르다."
- "시장이 조용할 때 움직이는 돈이, 시끄러울 때 값을 매긴다."

위 예시처럼 — 짧고, 대구를 이루고, 여운이 남게. 감탄사·수식어·상투어는 빼고
명사와 동사만으로 승부한다. "~하는 것이 중요합니다" 같은 훈계조는 쓰지 않는다.

출력 형식(JSON만):
{
  "한줄평": "...",
  "오늘의_시장": "...",
  "오늘의_한문장": "...",
  "침묵의_지표": "...",
  "오늘의_공부": "...",
  "핵심이슈": [
    {"태그": "반도체", "내용": "..."}
  ],
  "핵심뉴스": [
    {"태그": "시황", "제목": "...", "요약": "...", "링크": "입력 데이터의 원본 링크 그대로"}
  ]
}
"""


def load_data():
    if not os.path.exists(DATA_PATH):
        print(f"❌ {DATA_PATH} 파일이 없습니다. collect_data.py를 먼저 실행하세요.")
        sys.exit(1)
    with open(DATA_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def extract_text(response):
    """응답에서 '진짜 글'만 뽑아낸다.

    ⚠️ 중요: 최신 모델은 생각(thinking) 블록을 함께 돌려줄 수 있다.
    그래서 content[0] 을 그냥 집으면 생각 블록을 집을 위험이 있다.
    반드시 type == 'text' 인 블록만 골라야 한다.
    """
    조각들 = []
    for block in response.content:
        if getattr(block, "type", None) == "text":
            조각들.append(block.text)
    return "\n".join(조각들).strip()


def parse_json(raw_text):
    """```json 감싸기 등을 벗겨내고 JSON으로 변환."""
    t = raw_text.replace("```json", "").replace("```", "").strip()
    # 혹시 앞뒤에 잡소리가 붙었으면 첫 { 부터 마지막 } 까지만 취한다
    시작 = t.find("{")
    끝 = t.rfind("}")
    if 시작 != -1 and 끝 != -1:
        t = t[시작:끝 + 1]
    return json.loads(t)


def ask_claude(data, 시도=1):
    user_message = (
        "오늘 수집된 시장 데이터는 다음과 같다:\n\n"
        + json.dumps(data, ensure_ascii=False, indent=2)
    )

    response = client.messages.create(
        model=MODEL,
        max_tokens=4000,   # 생각 블록까지 여유 있게
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_message}],
    )

    raw = extract_text(response)
    try:
        return parse_json(raw)
    except json.JSONDecodeError:
        if 시도 < 2:
            print("⚠️ JSON 형식이 아니어서 한 번 더 시도합니다...")
            time.sleep(2)
            return ask_claude(data, 시도 + 1)
        print("❌ JSON 파싱 실패. 받은 응답:")
        print(raw[:500])
        raise


def verify_news_links(글, 원본뉴스):
    """Claude가 만든 '핵심뉴스'의 링크가 실제 원본 목록에 있는지 검증한다.
    프롬프트로 '지어내지 말라'고 지시해도 완전히 믿을 수는 없으므로,
    코드로 한 번 더 대조한다. 원본에 없는 링크는 즉시 걸러낸다(지어낸 것으로 간주)."""
    원본링크들 = {item["링크"] for item in (원본뉴스 or [])}
    핵심뉴스 = 글.get("핵심뉴스", [])
    검증됨 = []
    걸러짐 = 0
    for item in 핵심뉴스:
        if item.get("링크") in 원본링크들:
            검증됨.append(item)
        else:
            걸러짐 += 1
    if 걸러짐:
        print(f"⚠️ 핵심뉴스 중 {걸러짐}건은 원본에 없는 링크라 제외했습니다 (지어낸 것으로 간주).")
    글["핵심뉴스"] = 검증됨
    return 글


if __name__ == "__main__":
    print(f"=== {DATE} 해석 글 생성 시작 (모델: {MODEL}) ===\n")

    data = load_data()

    try:
        글 = ask_claude(data)
        글 = verify_news_links(글, data.get("뉴스원본"))
    except Exception as e:
        # 실패해도 파이프라인 전체가 죽지 않도록 명확히 알리고 종료.
        # (build_html.py 는 해석글 없이도 리포트를 만들 수 있다)
        print("\n❌ 해석 글 생성 실패")
        print(f"   원인: {type(e).__name__}: {e}")
        print("   → 리포트는 해석글 없이 생성됩니다. 잔액/키/모델명을 확인하세요.")
        sys.exit(1)

    최종 = {**data, "해석글": 글}
    with open(REPORT_PATH, "w", encoding="utf-8") as f:
        json.dump(최종, f, ensure_ascii=False, indent=2)

    print("✅ 생성된 해석 글:\n")
    for key, value in 글.items():
        print(f"[{key}]\n{value}\n")

    print(f"🎉 완료! → {REPORT_PATH}")
