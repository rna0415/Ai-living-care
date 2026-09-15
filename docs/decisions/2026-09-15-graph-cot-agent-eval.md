# 2026-09-15 · graph_cot_agent 평가 프로토타입(`knowledge_graph/graph_cot_agent/`) 추가

> **정본 반영** `manager_ai_agent/knowledge_graph/CLAUDE.md`

## 배경

v5 스키마(`livingcare_graph_v5*.cypher`)가 이미 갖고 있는 action(관측)/judgement(판단)/
timing(에스컬레이션)/action(대응) 3+1 분리를 그대로 매핑하는 독립 프로토타입
`graph_cot_agent.py`를 만들고, 정책 적합률·개인화·강건성·자연어 라우팅 등 여러 각도로
평가했다. Neo4j에 연결하지 않고 v5 seed `.cypher` 파일을 직접 텍스트로 파싱해서 쓰는
**완전히 독립된 코드**라 `manager_ai_core/`의 기존 Neo4j 파이프라인(`pipeline.py` 등)과
코드를 공유하지 않는다. `knowledge_graph/graph_cot_agent/`에 실험 코드로 추가한다 —
`knowledge_graph/CLAUDE.md`가 이미 "실험·미승인"으로 표시한 Neo4j 그래프 파일들과 같은
층위, 정본 승격 아님.

## 무엇을 했는가

WellBeing·Safety는 코드가 규칙을 결정론으로 평가하고, Comfort는 LLM 에이전트가
`retrieve_graph_knowledge`류 도구를 스스로 호출하는 tool-use 루프로 분기한다(raw
Anthropic tool-calling, LangChain 미사용). 평가는 정답 JSON 문자열 비교 대신, 케이스마다
"허용 가능한 것"을 집합으로 선언하고 6개 필드(`escalate`·`severity`·
`response_check_item`·`personalization`·`required_fields`·`task_dispatch`)를 채점하는
방식(`eval_graph_cot_agent.py`)을 썼다.

기본 평가에 이어, 기존 벤치마크 대비 빠져 있던 축(커버리지·안전도/편의성·개인화가 실제
판정을 바꾸는가)을 실측으로 메우고(`eval_robustness.py`), 도메인 rationale 원문 기반 오탐
시나리오(`eval_domain_scenarios.py`), 그래프 23개 규칙 전체를 지식 소스로 삼은 154개
시나리오 macro-F1(`eval_macro_f1.py`), 자연어→device 호출 end-to-end(`eval_nl_e2e.py`),
합성 100문장 스트레스 테스트와 진단(`eval_synthetic_nl_100.py`·`eval_nl_diagnostics.py`·
`eval_synthetic_nl_100_v2.py`)까지 확장했다. 전체 방법론·수치·그림은 이 폴더의
`report.md` 참조.

## 결과 요약

- **기본 회귀 15개 케이스 전부 pass**(persona 3명 × WellBeing/Safety × 관측 시나리오).
  검증 과정에서 실제 버그 2건 발견·수정: (1) `severity=INFO`(야간 무동작=정상 수면 패턴)인데
  `escalate`가 `bool(triggered)`로만 판정돼 새고 있던 것 → `severity != "INFO"` 조건 추가.
  (2) `ci:motion`이 WellBeing·Safety 두 axis 관측 목록에 동시에 있어 axis 필터 없이 규칙이
  섞일 수 있던 것 → axis 필터 추가.
- **개인화가 실제 판정을 가른다**: 취약군 threshold(20°C) vs 일반 threshold(18°C) 경계인
  19°C 관측값에서 같은 규칙·같은 관측값인데 취약군 여부만 다르면 escalate 자체가
  갈리는 것을 화이트박스로 직접 확인함.
- **강건성**: 경계값 몬테카를로(잡음 15%) 민감도·특이도 거의 100% — 해석적 정확값으로는
  99.9968%/99.9571%(오류율 2,300분의 1). 잡음 25%부터 문헌 수준(78~99%)으로 떨어짐 —
  즉 문헌의 낮은 특이도는 센서 잡음만으로는 설명 안 되고 다중 규칙 상호작용·임상 맥락
  모호성 등 이 시뮬레이션이 모델링하지 않은 요인 때문.
- **판정 커널이 그래프 규칙의 61%(14/23)만 구현**: `_evaluate_single_rule`이 인식하는
  threshold 필드가 4종류뿐이라, 체중 변화·이동성·복약 반복누락·혈당·기립성저혈압 등
  9개 규칙은 어떤 관측값을 넣어도 항상 NORMAL로 판정된다(macro-F1 94.1%(전체) vs
  100%(지원 규칙만)).
- **자연어 axis 라우터(char n-gram TF-IDF)가 그래프 원문 16개에선 accuracy 93.8%지만,
  직접 지어낸 자연스러운 구어체 합성 100문장에선 macro-F1 47.2%로 붕괴** —
  KnowledgeLookup으로 쏠리는 체계적 편향(참조 문서가 짧고 어휘가 집중돼 벡터가 뾰족함)이
  원인. 참조 문서의 영어 전문용어 제거를 실제로 시도했으나 효과 없음(46.1%, Δ-1.0%p) —
  저비용 전처리로는 되돌릴 수 없고, 형태소 분석 기반 임베딩이나 LLM 라우팅 교체가
  유일하게 검증되지 않은 해법으로 남는다.

## 승격하지 않은 것

- **위 Neo4j 파이프라인(`kg_mapping/graph_retrieval.py` 등)이나 `manager_ai_core/pipeline.py`에
  연결하지 않았다.** 독립 평가 실험으로만 존재한다.
- **Comfort축(LLM 에이전트 경로)은 이 환경에 API 키가 없어 자동채점에서 계속 제외됐다** —
  여전히 미검증. `pass^k`(반복 실행 신뢰성)도 같은 이유로 미측정.
- **`_evaluate_single_rule`의 미지원 threshold 5종(`threshold_kg`/`_percent`/`_seconds`/
  `_count`/`_mgdl*`)은 그대로 남겨뒀다** — 추가하면 macro-F1이 100%로 수렴할지 확인 가능한
  명확한 다음 작업.
- **NL 라우터 교체(형태소 분석 기반 임베딩 또는 LLM 라우팅)는 미착수** — 47.2%를 끌어올릴
  유일하게 검증된 해법이지만 이번 세션 범위 밖.
- **`mr_cf6_dark_hallway_night`(seed의 axis-관측정책 불일치)·`mr_wb3_night_kitchen_visit`
  ("패턴 기록" 미구현)는 코드가 아니라 seed 데이터/설계 자체의 gap이라 그대로 보고만 하고
  임의로 고치지 않았다.**
