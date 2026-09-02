# biz_desc_parser.py
# ─────────────────────────────────────────────────────────────
# 차트프로 관제탑 — 기업 설명(무엇을 만들어 파는 회사인지) 2단계 파서
#
# 🆕 2026-09-01 — biz_portfolio_parser.py와 완전히 같은 구조를 재사용한다.
#    [WHY 같은 자리·같은 방식인가]
#      · 재료가 같다: biz_report_raw.json(사업보고서 원문, 이미 2,779개
#        수집됨) — 새 DART 수집 0회.
#      · 이유가 같다: "내 종목"은 브라우저에만 저장돼 서버가 미리 알 수
#        없다. 어떤 종목을 등록해도 바로 나오려면 **상장사 전체를 미리
#        생성**해둬야 한다(사업 포트폴리오·뉴스와 동일한 제약).
#      · 검증 방식이 같다: Claude.ai에서 표본 21개 실측 검증 완료
#        (2026-09-01) — 17개 유효 표본 전부 품질 우수, 정직한 "근거
#        부족" 응답(케어젠)도 정확히 작동 확인.
#
# ── 표본 검증에서 확정된 4가지 형식 (실측, 지어낸 규칙 아님) ──────
#   형식1(단순 단일사업 → 1문장): 서진시스템
#   형식2(비유 필요 → 2문장):     LG디스플레이, 주성엔지니어링
#   형식3(제품군 여러 개 → 불릿): 아모텍, 평화산업, 코리아써키트
#   형식4(지주사·투자회사):        SK스퀘어, 해성산업
#
# ── 승급 로직은 이번엔 안 넣는다 (원칙 8) ─────────────────────
#   사업 포트폴리오는 "합계 85~115%"라는 명확한 숫자 검증 실패가
#   있어서 승급 트리거가 분명했다. 이건 그런 수치 검증이 없다 —
#   표본 21개(유효 17개)에서 JSON 파싱 실패나 이상한 응답을 한 건도
#   못 봤다. 검증 못 한 승급 로직을 미리 넣는 것보다, 먼저 Haiku만으로
#   돌려보고 실전 로그에서 문제 패턴이 보이면 그때 추가한다.
# ─────────────────────────────────────────────────────────────
import io
import json
import os
import time

import anthropic

SCRIPT_VERSION = "v2026.09.01-a1"

MODEL = "claude-haiku-4-5-20251001"
# 사업 포트폴리오와 같은 이유로 Haiku — "회사가 뭘 하는지 설명"도
# 분류·추출에 가깝고(Anthropic 가이드), 출력이 짧아 사업포트폴리오보다도
# 더 저렴하다(실측 예상 전체 $22 안팎, §비용 계산 2026-09-01 참고).
MAX_TOKENS = 900   # 표본 중 가장 길었던 아모텍(4개 불릿)도 여유 있게 커버
DESC_FILE = "biz_description.json"          # 2단계 결과(성공+정직한 "근거부족" 둘 다)
DESC_FAIL_FILE = "biz_description_fail.json"  # 기술적 실패만(API 오류·JSON 파싱 실패)
DESC_재시도일 = 30
# 사업보고서 원본(BIZ_FAIL_FILE)의 180일보다 짧게 — 기술적 실패는
# 원인이 일시적일 가능성이 높다(biz_portfolio_parser.py와 동일 판단).
DESC_실패목록_우선재시도 = os.environ.get("CP_DESC_RETRY_FAILED", "no") == "yes"
DESC_하루할당 = int(os.environ.get("CP_DESC_QUOTA", "20"))
# 다른 quota들보다 작게 시작 — 원칙 8, 처음 며칠은 로그를 눈으로 보고
# 문제 없으면 quota를 올린다.

client = anthropic.Anthropic() if os.environ.get("ANTHROPIC_API_KEY") else None


# ── 시스템 프롬프트 ────────────────────────────────────────
# 🔴 2026-09-01 — Claude.ai에서 표본 21개 실측 검증(HO가 직접 4개
#    정답 예시를 만들어줌: 서진시스템·주성엔지니어링·아모텍·SK스퀘어).
#    아래 예시 4개는 그 실측 검증에 쓰인 것과 **똑같은 문구**다 —
#    ⚠️ 이 4개 회사 자체는 이후 실전 배치 대상에서 각별히 주의:
#    모델이 새로 생성하지 않고 이 예시를 그대로 베낄 위험이 있다
#    (실측으로 확인됨 — 표본 검증 때 3개가 토씨 하나 안 틀리고 예시와
#    똑같이 나왔었다). 하지만 이건 "예시로 준 회사와 실제 검증 대상
#    회사가 겹칠 때"만 생기는 문제이므로, 실전 배치(이 스크립트)에서는
#    애초에 검증에 안 썼던 새 회사들 위주로 돌아가 대부분 문제 없다.
#    다만 서진시스템·주성엔지니어링·아모텍·SK스퀘어 4개는 나중에 결과를
#    한 번 훑어봐서 예시를 그대로 베낀 건 아닌지 확인할 가치가 있다.
SYSTEM_PROMPT = """너는 한국 기업 사업보고서를 읽고, 이 회사가 정확히 무엇을 만들어서
누구에게 파는지 일반인도 바로 이해할 수 있게 설명하는 도구다.
설명하지 말고 JSON만 출력한다.

회사 성격에 따라 아래 4가지 형식 중 맞는 걸 골라서 써라.

【형식1 — 단순·단일사업이면 1문장으로 충분】
"서진시스템은 ESS·반도체·통신장비에 들어가는 금속 구조물과 부품을 만들고,
고객사가 원하는 경우 완제품 조립까지 대신해 돈을 버는 회사예요."

【형식2 — 이해에 비유가 필요하면 2문장(사실+비유)】
"주성엔지니어링은 반도체 웨이퍼 위에 아주 얇은 막을 입히는 장비를 만들어
반도체 제조업체에 판매하는 회사예요.
쉽게 말하면 반도체는 여러 층을 쌓아 만드는 '초미세 빌딩'과 비슷해요.
주성엔지니어링 장비는 그 빌딩의 벽과 절연층을 원자 단위로 아주 얇고
균일하게 코팅하는 기계입니다."

【형식3 — 제품군이 여러 개면 불릿 목록(각각 짧은 비유)】
"아모텍은 전기가 불안정하게 흐르거나 전파가 서로 방해하지 않도록 막아주는
세라믹 부품과 안테나, 자동차용 모터를 만들어 전자·자동차 업체에 판매하는
회사예요.
쉽게 말하면 전자제품 안에서 다음 세 가지 일을 합니다.
- EMC 부품: 갑자기 들어오는 정전기와 전자파를 막아주는 경비원
- 안테나: 스마트폰·자동차가 무선신호를 주고받게 하는 귀와 입
- MLCC: 필요한 순간 전기를 잠깐 저장했다가 안정적으로 내보내는 초소형 물탱크
- BLDC 모터: 브러시가 없어 수명이 길고 소음이 적은 자동차·가전용 모터"

【형식4 — 지주사·투자회사면 "직접 안 만들고 투자한다" + 구체적 계열사명 +
투자 비유, 가장 비중 큰 자산을 콕 짚기】
"SK스퀘어는 SK하이닉스, 11번가, SK플래닛 같은 ICT·반도체 관련 자산에
투자하고, 지분가치 상승·배당·매각·자사주 소각으로 주주가치를 키우는
회사예요.
쉽게 말하면, SK스퀘어는 공장을 직접 돌리는 회사라기보다 '좋은 기술회사
지분을 들고 있는 투자 지갑'에 가까워요. 그 지갑 안에서 가장 큰 자산이
바로 SK하이닉스입니다."

공통 규칙:
1. "전기전자·부품 쪽 회사예요" 처럼 업종 분류만 반복하지 마라. 실제
   제품명·서비스명·계열사명을 원문에서 찾아 구체적으로 써라.
2. 원문에 목차만 있고 실제 사업 설명이 안 보이면, 절대 지어내지 말고
   "근거 부족"이라고만 답해라. 틀린 설명이 빈칸보다 훨씬 나쁘다.
3. 계열사명·제품명은 **원문에 실제로 있는 것만** 쓴다. 일반 상식으로
   알고 있는 계열사라도 원문에 없으면 쓰지 마라.
4. 여러 사업을 하면 매출 비중이 큰 순서로 짚되, 억지로 1~2개로 줄이지
   말고 실제로 구분되는 사업 단위 수만큼 불릿을 써라.
5. 출력 형식(이것 외에 아무것도 쓰지 마라):
   {"설명":"...","확신":"높음"} 또는 {"설명":null,"사유":"근거 부족"}
"""


def _pick_blocks(v, 블록길이=2500):
    """회사 개요 용도 — 매출표 스코어링(숫자+% 패턴) 대신 본문조각을
    최우선으로 쓰고, 보조조각(매출비중 단서로 찾은 것) 1개를 보충한다.

    ⚠️ biz_portfolio_parser._pick_blocks와 다르다 — 거기는 "표"를 찾는
       거라 숫자+% 패턴 점수로 블록을 고르지만, 여기는 "회사가 뭘
       하는지 서술"을 찾는 거라 보통 문서 맨 앞(사업의 개요)에 있다.
       그래서 본문조각(문서 앞부분)을 그냥 최우선으로 둔다.
    ⚠️ 목차만 걸린 경우(LG디스플레이 실측 사례) 보조조각에 실제 사업
       서술이 섞여 있을 수 있어 1개를 추가로 붙인다 — 표본 검증에서
       이 방식으로 LG디스플레이도 정상 처리됐다.
    """
    본문 = v.get("본문조각", "") or ""
    out = [f"[본문조각]\n{본문[:블록길이]}"]
    보조 = (v.get("보조조각") or [])
    if 보조:
        e = 보조[0]
        out.append(f"[보조:{e.get('단서','')}]\n{(e.get('글','') or '')[:1500]}")
    return "\n\n".join(out)


def _is_broken(v):
    """인코딩이 깨진 문서인지 판정 — biz_portfolio_parser.py와 동일 기준.

    ⚠️ 기준을 다르게 두면 나중에 "왜 두 파서 결과가 다르지"를 또
       한 번 조사해야 한다. 같은 원본(biz_report_raw.json)을 쓰니
       판정 기준도 같게 맞춘다.
    """
    t = (v.get("본문조각", "") or "")[:3000]
    return sum(1 for w in ["있습니다", "사업", "회사", "매출", "당사", "주요"] if w in t) <= 1


def _call(text, model=None):
    kwargs = dict(
        model=model or MODEL,
        max_tokens=MAX_TOKENS,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": text}],
    )
    with client.messages.stream(**kwargs) as stream:
        response = stream.get_final_message()
    조각들 = [b.text for b in response.content if getattr(b, "type", None) == "text"]
    return "\n".join(조각들).strip()


def _parse_json(raw):
    t = raw.replace("```json", "").replace("```", "").strip()
    시작, 끝 = t.find("{"), t.rfind("}")
    if 시작 != -1 and 끝 != -1:
        t = t[시작:끝 + 1]
    return json.loads(t)


def _load_json(path, 기본):
    if not os.path.exists(path):
        return 기본
    try:
        with io.open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return 기본


def parse_biz_description(quota=None, biz_file="biz_report_raw.json"):
    """biz_report_raw.json → biz_description.json.

    catchup_enrich.py에서 collect_biz_reports() 직후, biz_portfolio
    파싱과 같은 자리에서 호출된다. merge_json_files.py의 FILES 목록과
    enrich.yml의 git add 목록에도 DESC_FILE·DESC_FAIL_FILE이 등록돼
    있어야 한다.
    """
    if client is None:
        print("   ⚠️ ANTHROPIC_API_KEY 없음 — 기업 설명 파싱 건너뜀")
        return
    if not os.path.exists(biz_file):
        print(f"   ⚠️ {biz_file} 없음 — 기업 설명 파싱 건너뜀")
        return

    quota = quota or DESC_하루할당
    biz = _load_json(biz_file, {})
    저장 = _load_json(DESC_FILE, {})
    실패 = _load_json(DESC_FAIL_FILE, {})
    오늘 = time.strftime("%Y%m%d")

    # 후보 선정 — biz_portfolio_parser.py와 동일한 갱신 감지 로직.
    # 접수번호(공시마다 고유)가 바뀌면 새 사업보고서가 나온 것이므로
    # 다시 파싱 대상이 된다(원칙 3 — 옛 값을 지우는 게 아니라 성공하면
    # 덮어쓸 뿐이라 안전하다).
    후보 = []
    갱신대상 = []
    깨짐스킵 = 0
    for nm, v in biz.items():
        if not isinstance(v, dict):
            continue
        if nm in 저장:
            _저장된접수 = 저장[nm].get("접수번호")
            _현재접수 = v.get("접수번호")
            if _저장된접수 and _현재접수 and _저장된접수 != _현재접수:
                갱신대상.append(nm)
            else:
                continue
        if _is_broken(v):
            깨짐스킵 += 1
            continue
        마지막실패 = 실패.get(nm)
        if 마지막실패 and not DESC_실패목록_우선재시도:
            try:
                a = time.strptime(오늘, "%Y%m%d")
                b = time.strptime(마지막실패, "%Y%m%d")
                if (time.mktime(a) - time.mktime(b)) / 86400 < DESC_재시도일:
                    continue
            except Exception:
                pass
        후보.append(nm)

    if 갱신대상:
        print(f"   🏢 🔄 새 사업보고서 감지 — 접수번호가 바뀐 {len(갱신대상)}개를 "
              f"다시 파싱합니다: {', '.join(갱신대상[:10])}"
              + (" ..." if len(갱신대상) > 10 else ""))

    print(f"🏢 기업 설명 파싱 후보 {len(후보)}개 "
          f"(인코딩 깨짐 {깨짐스킵}개 제외 · 오늘 최대 {quota}개)"
          + (" · 🔁 실패목록 강제 재시도 모드" if DESC_실패목록_우선재시도 else ""))

    성공, 없음, 실패건 = 0, 0, 0
    for nm in 후보[:quota]:
        text = _pick_blocks(biz[nm])
        if not text.strip():
            실패[nm] = 오늘
            실패건 += 1
            continue
        try:
            raw = _call(text)
            j = _parse_json(raw)
        except Exception as e:
            print(f"   ⚠️ {nm} — {type(e).__name__}, 다음에 재시도")
            실패[nm] = 오늘
            실패건 += 1
            time.sleep(1)
            continue

        설명 = j.get("설명")
        if not 설명:
            # 정직한 "근거 부족"도 실패가 아니다 — 저장해서 매번 다시
            # 안 묻는다(원칙 14). 접수번호도 같이 저장해 새 보고서가
            # 나오면 재확인 대상이 되게 한다.
            저장[nm] = {"설명": None, "사유": j.get("사유", ""), "확인일": 오늘,
                        "접수번호": biz[nm].get("접수번호")}
            실패.pop(nm, None)
            없음 += 1
            print(f"   ⭕ {nm} — 근거부족: {(j.get('사유') or '')[:50]}")
        else:
            저장[nm] = {
                "설명": 설명,
                "확신": j.get("확신", ""),
                "확인일": 오늘,
                "접수번호": biz[nm].get("접수번호"),
            }
            실패.pop(nm, None)
            성공 += 1
            print(f"   ✅ {nm} — {설명[:60].replace(chr(10), ' ')}...")
        time.sleep(0.6)

    if 성공 or 없음:
        with io.open(DESC_FILE, "w", encoding="utf-8") as f:
            json.dump(저장, f, ensure_ascii=False, separators=(",", ":"))
    if 실패건:
        with io.open(DESC_FAIL_FILE, "w", encoding="utf-8") as f:
            json.dump(실패, f, ensure_ascii=False, separators=(",", ":"))

    print(f"🏢 기업 설명 — 성공 {성공} · 근거부족 {없음} · 실패 {실패건} "
          f"· 누적 {len(저장)}종목")


if __name__ == "__main__":
    # 검토·수동 시험용. 실제 배치 실행은 catchup_enrich.py에 붙인 뒤엔
    # 거기서 quota를 넘겨받아 호출한다.
    parse_biz_description()
