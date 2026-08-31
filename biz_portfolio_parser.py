# biz_portfolio_parser.py
# ─────────────────────────────────────────────────────────────
# 차트프로 관제탑 — 사업 포트폴리오(매출 비중) 2단계 파서
#
# 🆕 2026-08-31 — catchup_enrich.py에 정식 연결됨.
#    ⚠️ 아직 화면(build_html.py)에는 안 붙어 있다. build_html.py는
#       이 파일이 만드는 biz_portfolio.json을 아직 읽지 않는다 —
#       배치가 며칠 안정적으로 돈 걸 로그로 확인한 뒤에 연결한다
#       (원칙 8 — 검증 못 한 걸 화면에 바로 배포하지 않는다).
#
# 이 파일이 하는 일: biz_report_raw.json(1단계, 이미 2,775종목 수집됨)을
# 읽어서, 「매출 비중(사업 포트폴리오)」을 Claude에게 구조화해달라고 시키고
# biz_portfolio.json(2단계)에 쌓는다.
#
# ── 어디에 들어가야 하나 (제안) ──────────────────────────────
#   collect_data.py가 아니라 **catchup_enrich.py**에 새 단계로 추가하는
#   걸 추천한다.
#   [WHY] collect_data.py는 지금 Claude API를 한 번도 안 쓴다
#         (import anthropic이 아예 없다) — 순수 수집·계산 전담이다.
#         이 파서는 그 반대로 "이미 모아둔 것을 Claude가 해석"하는
#         일이라 generate_report.py의 역할에 더 가깝다. 그런데
#         generate_report.py는 "오늘 하루치 글"을 쓰는 곳이고, 이건
#         "쌓여 있는 과거 문서 2,775개를 며칠에 걸쳐 나눠서" 처리하는
#         일이라 시간 제약이 다르다.
#         → catchup_enrich.py가 이미 collect_biz_reports·
#           collect_stock_news_raw를 이 방식(quota만큼씩, 매일 발행과
#           분리)으로 돌리고 있다. 같은 자리가 맞다.
#
# ── 비용 관점 ─────────────────────────────────────────────
#   effort는 기본값(지정 안 함)으로 뒀다. generate_report.py는 "글쓰기"라
#   high가 맞지만, 이건 구조화 추출이라 정확도 대비 비용을 따져볼 필요가
#   있다. SK·HD한국조선해양 케이스처럼 판단이 까다로운 경우가 있었으니,
#   전체 확대 전에 "effort=high로 하면 이 실수가 줄어드는지"는 별도로
#   소표본 A/B가 필요하다 — 이것도 확대 전에 해보자고 제안한다.
# ─────────────────────────────────────────────────────────────
import io
import json
import os
import re
import time

import anthropic

SCRIPT_VERSION = "v2026.08.31-draft1"

MODEL = "claude-sonnet-5"          # generate_report.py와 통일
MAX_TOKENS = 1200                  # 부문 5~6개짜리 JSON이면 충분, 여유 포함
PORT_FILE = "biz_portfolio.json"           # 2단계 결과(성공+정직한 「없음」 둘 다)
PORT_FAIL_FILE = "biz_portfolio_fail.json"  # 기술적 실패만(API 오류·JSON 파싱 실패)
PORT_재시도일 = 30
# 🆕 사업보고서(BIZ_FAIL_FILE)의 재시도일(180일)보다 훨씬 짧게 잡았다.
#    [WHY] 이건 "DART에 문서가 없다"가 아니라 "API 호출이 실패했다"는
#          뜻이라 원인이 일시적(네트워크·요금제)일 가능성이 높다.
BIZPORT_하루할당 = int(os.environ.get("CP_BIZPORT_QUOTA", "20"))
# 🆕 다른 몰아모으기 quota들(300/40/150)보다 훨씬 작게 시작한다.
#    [WHY] 원칙 8 — 검증 못 한 걸 배포하지 않는다. 지금까지 표본
#          15개까지만 실제로 확인했다. 처음 며칠은 소량으로 돌려서
#          로그를 눈으로 몇 번 더 보고, 문제 없으면 quota를 올리자.

client = anthropic.Anthropic() if os.environ.get("ANTHROPIC_API_KEY") else None


# ── 시스템 프롬프트 ────────────────────────────────────────
# 🔴 2026-08-31 — Claude.ai에서 표본 15개를 두 번 돌려 실측 검증했다
#    (1차 6개 5/5 정답 + HD한국조선해양 오답 1건 발견 → 규칙 수정 →
#     2차 15개 14/15 정답). 아래 각 규칙 옆 [근거]는 그 과정에서 실제로
#     관찰된 실패 사례다. 지어낸 규칙이 아니라 실측 기반이다.
SYSTEM_PROMPT = """너는 한국 기업 사업보고서에서 «매출 비중»만 정확히 뽑는 도구다.
설명하지 말고 JSON만 출력한다.

출력 형식 (이것 외에 아무것도 쓰지 마라):
{"부문":[{"이름":"...","비중":00.0}, ...],"기준":"2025년 사업보고서","확신":"높음"}
또는 뽑을 수 없으면: {"부문":[],"사유":"..."}

규칙:
1. «이 회사 전체 매출을 사업/제품별로 나눈 비율»만 뽑는다.
   다음은 절대 뽑지 마라 — 전부 다른 표다:
   · 원재료 «매입» 비중  [근거: 슈프리마 SENSOR/IC/PCB 매입표]
   · 생산능력·생산실적·가동률
   · 영업손익·자산·부채 등 재무제표 항목  [근거: 삼성바이오로직스]
   · 판매 «대수»·수량 비중  [근거: 케이카 판매대수표]
2. 비중이 %로 안 적혀 있고 «금액»만 있으면 직접 계산해서 채운다.
   [근거: GRT는 %가 아예 없고 금액만 있었다]
3. 합계·소계·계·연결조정·내부거래제거 행은 **제외**한다.
   [근거: 한전기술 «소계», 두산밥캣 «조정및제거»]
4. 지주회사/모회사인 경우: 원문에 «당사의 매출액은 ~로 구성»처럼
   **회사 자신을 주어로 한 합산 문장**이 있으면 그 숫자를 채택한다.
   종속기업 개별 사업 설명만 있고 이런 합산 문장이 없을 때만 «없음».
   [근거: SK "당사의 별도 재무제표 기준 영업수익은 투자부문 24.0%,
    사업부문 76.0%" → 채택. CJ는 CJ이엔엠·CJ프레시웨이 등 자회사
    개별 표만 있고 "당사(CJ㈜)의 매출액은" 문장이 없어서 → 없음]
5. 🆕 «사업부문» 컬럼과 그 **하위** 구분(수출/내수, 매출유형, 품목)을
   혼동하지 마라. 표에 "사업 부문 | 매출유형(수출/내수) | 품목"처럼
   두 층이 같이 있으면, **사업부문 컬럼 값끼리** 합쳐서 비중을 낸다.
   하위 구분(수출/내수 등)이 있다고 해서 "사업부문이 아니라 매출유형
   구분"이라고 판단해 통째로 없음 처리하지 마라.
   [근거: 루트로닉 — "사업 부문(의료기기/상품/부품) × 매출유형(수출/
    내수)" 2층 구조인데, 하위층만 보고 «없음»으로 잘못 답한 사례가
    있었다. 정답은 의료기기 88.38% / 상품 0.99% / 부품 9.33%다]
6. 가장 최근 연도 하나만 쓴다. 여러 해가 나란히 있으면 제일 왼쪽(최근)만.
7. 부문 이름은 원문 표기를 그대로 쓰되 15자 이내로 줄인다.
8. 비중 합계는 90~110% 사이여야 한다. 벗어나면 잘못 읽은 것이므로
   {"부문":[],"사유":"합계 이상"}을 출력한다.
9. 표가 잘려 있거나 애매하면 **억지로 만들지 말고** 빈 배열을 반환한다.
   틀린 값을 내는 것이 빈칸보다 훨씬 나쁘다.
10. 사업보고서에 부문 구분이 실제로 없는 회사도 있다(신약 파이프라인
    기업, 스팩, 단일사업 회사 등). 그건 실패가 아니라 «없음»이 정답이다.
    [근거: 스팩은 «기업인수목적회사로 해당사항이 없습니다», LG화학은
     매출비중표 자체가 캡처 구간 안에 없었다 — 둘 다 «없음»이 맞다.
     화인베스틸(형강 단일사업)도 매출유형(제품/상품/기타)뿐이라 «없음»]
"""


def _pick_blocks(v, 최대블록=2, 블록길이=1800):
    """숫자+% 패턴이 많은 블록을 우선으로 골라 이어붙인다.

    ⚠️ 원문 전체를 보내면 토큰이 폭발한다. 표가 있을 법한 자리만
       골라 보내되, 한 블록만 보내면 표가 잘린 경우를 놓친다
       (씨엔플러스 사례 — 2026-08-31 발견).
    """
    blocks = [("본문조각", v.get("본문조각", "") or "")]
    for e in (v.get("보조조각") or []):
        blocks.append((f"보조:{e.get('단서', '')}", e.get("글", "") or ""))

    def score(t):
        return len(re.findall(r"[\d,]{3,}\s+[0-9]{1,3}\.[0-9]{1,2}\s*%", t))

    blocks.sort(key=lambda b: -score(b[1]))
    out = [f"[{l}]\n{t[:블록길이]}" for l, t in blocks[:최대블록] if t]
    return "\n\n".join(out)


def _is_broken(v):
    """인코딩이 깨진 문서인지 판정.

    🔴 2026-08-31 실측 — biz_report_raw.json 2,775개 중 **9개**(0.3%)가
       한글이 깨져 있었다(가온전선·삼성SDI·포스코퓨처엠 등). 깨진 걸
       API에 보내면 돈만 쓰고 반드시 실패한다. 보내기 전에 걸러낸다.
    ⚠️ 2026-08-31 (2차) — 단어 수를 4개로 줄여 처음 넣었다가, DB손해보험
       등 9개 종목이 억울하게 «깨짐»으로 잘못 잡히는 걸 발견했다.
       보험사류는 "매출" 대신 "보험료수익" 같은 다른 용어를 쓰는 경우가
       있어 4단어 기준(있습니다/사업/회사/매출)이 너무 좁았다.
       "당사"·"주요" 2개를 다시 넣어 **9개(0.3%)로 재확인된 원래
       기준**으로 되돌린다.
       ⚠️ 이 값이 앞으로도 바뀔 수 있다 — 새 종목이 수집될 때마다
          한 번씩 눈으로 재확인하는 습관이 안전하다(원칙 11).
    ⚠️ 이 9개는 여기서 고치지 않는다 — 원본 수집(collect_biz_reports)
       단의 인코딩 판정 로직을 손볼 별도 작업이다. 여기서는
       «지금은 처리 못 함»으로만 표시하고 넘어간다(원칙 14).
    """
    t = (v.get("본문조각", "") or "")[:3000]
    return sum(1 for w in ["있습니다", "사업", "회사", "매출", "당사", "주요"] if w in t) <= 1


def _call(text):
    kwargs = dict(
        model=MODEL,
        max_tokens=MAX_TOKENS,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": text}],
    )
    # ⚠️ effort는 일부러 안 넣었다 — 위 상단 주석 "비용 관점" 참고.
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


def parse_biz_portfolio(quota=None, biz_file="biz_report_raw.json"):
    """biz_report_raw.json → biz_portfolio.json.

    ⚠️ 이 함수는 아직 어디서도 호출되지 않는다(검토용). 실제로 붙일 때는
       catchup_enrich.py에 다른 collect_* 함수들과 나란히 넣고,
       merge_json_files.py의 FILES 목록에도 이 두 파일(PORT_FILE·
       PORT_FAIL_FILE)을 추가해야 한다 — enrich.yml이 daily.yml과
       공유하게 될 파일이기 때문이다(§6 병합기 문서 참고).
    """
    if client is None:
        print("   ⚠️ ANTHROPIC_API_KEY 없음 — 사업 포트폴리오 파싱 건너뜀")
        return
    if not os.path.exists(biz_file):
        print(f"   ⚠️ {biz_file} 없음 — 사업 포트폴리오 파싱 건너뜀")
        return

    quota = quota or BIZPORT_하루할당
    biz = _load_json(biz_file, {})
    저장 = _load_json(PORT_FILE, {})
    실패 = _load_json(PORT_FAIL_FILE, {})
    오늘 = time.strftime("%Y%m%d")

    # 후보: 아직 처리 안 한 것 + 최근에 기술적 실패 안 한 것 + 인코딩 정상인 것
    후보 = []
    깨짐스킵 = 0
    for nm, v in biz.items():
        if not isinstance(v, dict) or nm in 저장:
            continue
        if _is_broken(v):
            깨짐스킵 += 1
            continue
        마지막실패 = 실패.get(nm)
        if 마지막실패:
            try:
                a = time.strptime(오늘, "%Y%m%d")
                b = time.strptime(마지막실패, "%Y%m%d")
                if (time.mktime(a) - time.mktime(b)) / 86400 < PORT_재시도일:
                    continue
            except Exception:
                pass
        후보.append(nm)

    print(f"📊 사업 포트폴리오 파싱 후보 {len(후보)}개 "
          f"(인코딩 깨짐 {깨짐스킵}개 제외 · 오늘 최대 {quota}개)")

    성공, 없음, 실패건 = 0, 0, 0
    합계이상 = 0
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

        segs = j.get("부문") or []
        if not segs:
            # 정직한 «없음»은 실패가 아니다 — 저장해서 매번 다시 안 묻는다.
            저장[nm] = {"부문": [], "사유": j.get("사유", ""), "확인일": 오늘}
            실패.pop(nm, None)
            없음 += 1
            print(f"   ⭕ {nm} — 없음: {j.get('사유', '')[:50]}")
        else:
            tot = sum(float(s.get("비중") or 0) for s in segs)
            if not (85 <= tot <= 115):
                # 모델이 규칙 8을 안 지켰다 — 코드 쪽에서도 한 번 더 막는다.
                print(f"   ⚠️ {nm} — 합계 {tot:.1f}% 이상해서 버림")
                실패[nm] = 오늘
                합계이상 += 1
                실패건 += 1
            else:
                저장[nm] = {
                    "부문": sorted(segs, key=lambda s: -(s.get("비중") or 0)),
                    "기준": j.get("기준", ""),
                    "확신": j.get("확신", ""),
                    "확인일": 오늘,
                }
                실패.pop(nm, None)
                성공 += 1
                head = " · ".join(f"{s['이름']} {s['비중']}%" for s in segs[:3])
                print(f"   ✅ {nm} — {len(segs)}부문 합계{tot:.1f}% · {head}")
        time.sleep(0.6)

    if 성공 or 없음:
        with io.open(PORT_FILE, "w", encoding="utf-8") as f:
            json.dump(저장, f, ensure_ascii=False, separators=(",", ":"))
    if 실패건:
        with io.open(PORT_FAIL_FILE, "w", encoding="utf-8") as f:
            json.dump(실패, f, ensure_ascii=False, separators=(",", ":"))

    print(f"📊 사업 포트폴리오 — 성공 {성공} · 없음 {없음} · 실패 {실패건}"
          f"(합계이상 {합계이상}) · 누적 {len(저장)}종목")


if __name__ == "__main__":
    # 검토·수동 시험용. 실제 배치 실행은 catchup_enrich.py에 붙인 뒤엔
    # 거기서 quota를 넘겨받아 호출한다.
    parse_biz_portfolio()
