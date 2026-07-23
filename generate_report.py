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

# 사용할 모델 — 현재 세대 Sonnet.
# (문서 작성·구조적 분석에 적합하고 비용도 합리적)
MODEL = "claude-sonnet-5"

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
  (예시 톤: "급등도 급락도, 결국 같은 수급 쏠림의 양면이다.")
- 침묵의_지표: 표면적 등락 뒤에 숨은 수급·심리 해석 2~3문장.
- 오늘의_공부: 오늘 데이터와 연결되는 투자 개념 하나를 쉽게 설명 2~3문장.

출력 형식(JSON만):
{
  "한줄평": "...",
  "오늘의_시장": "...",
  "오늘의_한문장": "...",
  "침묵의_지표": "...",
  "오늘의_공부": "..."
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


if __name__ == "__main__":
    print(f"=== {DATE} 해석 글 생성 시작 (모델: {MODEL}) ===\n")

    data = load_data()

    try:
        글 = ask_claude(data)
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
