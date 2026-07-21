# ============================================================
# generate_report.py
# 목적: collect_data.py 가 만든 data_YYYYMMDD.json 을 읽어서
#       Claude API에게 "오늘의 시장 / 침묵의 지표 / 오늘의 공부"
#       세 가지 해석 글을 써 달라고 요청한다.
# 결과: report_YYYYMMDD.json (숫자 + 글이 합쳐진 최종 재료)
# ============================================================

import json
import os
import sys
from datetime import datetime
import anthropic  # pip install anthropic 필요

DATE = datetime.now().strftime("%Y%m%d")
DATA_PATH = f"data_{DATE}.json"
REPORT_PATH = f"report_{DATE}.json"

# ⚠️ API 키는 환경변수 ANTHROPIC_API_KEY 에서 자동으로 읽힌다
# (윈도우에서 미리 시스템 환경변수로 등록해두면 client = anthropic.Anthropic() 만으로 인식됨)
client = anthropic.Anthropic()

# 우리가 글을 쓸 때 쓸 "규칙"을 시스템 프롬프트로 고정해둔다
SYSTEM_PROMPT = """\
너는 주식 시황 리포트 "차트프로 관제탑"의 해설 작가다.
아래 규칙을 반드시 지켜라.

1. 숫자는 절대 지어내지 않는다. 입력으로 주어진 JSON 데이터에 있는 숫자만 사용한다.
2. 데이터에 없는 값은 "확인 필요"라고 쓰고 임의로 채우지 않는다.
3. 확정적인 투자 권유("오른다", "사야 한다" 등)는 쓰지 않는다.
4. 문장은 친절하고 담백하게, 초보 투자자도 이해할 수 있게 쓴다.
5. 반드시 아래 JSON 형식으로만 답한다. 그 외 설명이나 인사말은 절대 넣지 않는다.

각 항목 작성 지침:
- 한줄평: 오늘 시장의 특징을 한 문장(공백 포함 40자 이내)으로 압축. 관제지수 옆에 붙는 짧은 총평.
- 오늘의_한문장: 오늘 시장이 준 '교훈'을 격언처럼 한 문장으로. 오래 기억에 남을 만큼 담백하고 묵직하게. 투자 권유·수치 없이 통찰만. (예: "급등도 급락도, 결국 같은 수급 쏠림의 양면이다.")
- 오늘의_시장: 오늘 지수·수급·주도섹터를 근거로 한 2~3문장 총평.

출력 형식(JSON만):
{
  "한줄평": "40자 이내 한 문장",
  "오늘의_시장": "2~3문장 총평",
  "오늘의_한문장": "교훈 한 문장 (격언체)",
  "침묵의_지표": "표면적 등락 뒤 수급/심리 해석 2~3문장",
  "오늘의_공부": "오늘 데이터 관련 투자 개념 하나 쉽게 설명 2~3문장"
}
"""


def load_data():
    if not os.path.exists(DATA_PATH):
        print(f"❌ {DATA_PATH} 파일이 없습니다. collect_data.py를 먼저 실행하세요.")
        sys.exit(1)
    with open(DATA_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def ask_claude(data):
    user_message = f"오늘 수집된 시장 데이터는 다음과 같다:\n\n{json.dumps(data, ensure_ascii=False, indent=2)}"

    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1000,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_message}],
    )

    raw_text = response.content[0].text.strip()

    # Claude가 혹시 ```json ... ``` 로 감싸서 답하면 벗겨낸다
    raw_text = raw_text.replace("```json", "").replace("```", "").strip()

    try:
        return json.loads(raw_text)
    except json.JSONDecodeError:
        print("⚠️ JSON 파싱 실패. 원본 응답:")
        print(raw_text)
        sys.exit(1)


if __name__ == "__main__":
    print(f"=== {DATE} 해석 글 생성 시작 ===\n")

    data = load_data()
    글 = ask_claude(data)

    최종 = {**data, "해석글": 글}

    with open(REPORT_PATH, "w", encoding="utf-8") as f:
        json.dump(최종, f, ensure_ascii=False, indent=2)

    print("✅ 생성된 해석 글:\n")
    for key, value in 글.items():
        print(f"[{key}]\n{value}\n")

    print(f"🎉 완료! → {REPORT_PATH} 에 저장됨 (다음 단계: HTML 템플릿 삽입)")