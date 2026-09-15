# LivingCare 개인화 판단 에이전트 — 구현 및 평가 보고서

## 1. 문제

범용 LLM에 동일한 프롬프트를 쓰면, 노령자 개인의 특성(취약군 여부, 진단명, 복용 중인 약,
현재 맥락)이 달라져도 답변은 일반론에 머문다. 즉 개인 맥락에 맞는 프롬프트 해석과, 그
맥락에 맞는 기기 동작(정책 생성·실행)을 하지 못한다.

## 2. 해결 방향

지식그래프(KG)·함수 호출(MCP)·에이전트 호출(A2A)을 결합해, 맥락이 달라질 때마다 그에 맞는
함수 호출과 맞춤 에이전트 호출로 문제를 해결한다.

- **KG** — 개인(Subject: 진단명·복용약·취약군 여부)과 판단 규칙(MonitoringRule)·정책
  (ObservationSelectionPolicy/ResponseSelectionPolicy/LoopTerminationPolicy)을 그래프로
  분리해 보관한다. 같은 axis라도 조회 시점에 누구의 그래프를 훑느냐에 따라 다른 답이
  나온다 — 프롬프트가 아니라 그래프 조회 결과가 개인화의 원천이다.
- **MCP** — `retrieve_graph_knowledge` 도구 하나로 그래프 조회를 함수 호출 형태로 통일.
  LLM이 필요하다고 판단한 순간에만 호출한다(무조건 전체를 프롬프트에 밀어넣지 않음).
- **A2A** — axis별로 판단 주체가 다르다: 규칙이 이미 답을 정하는 축(WellBeing/Safety)은
  코드가 결정론으로 처리하고, 규칙만으로 안 되는 축(Comfort)은 LLM 에이전트가 도구를
  스스로 호출하며 판단한다. 최종 대응(response)이 정해지면 그 실행을 담당할 Worker(디바이스
  또는 서비스)에게 넘기는 경계를 명시적으로 표시한다.

## 3. 구현

프로토타입: `graph_cot_agent.py` (독립 실행, Ai-living-care 저장소의 다른 코드를
import하지 않음 — v5 seed cypher 파일만 직접 파싱해서 쓴다).

### 3.1 그래프 소스

박준상님이 작성한 v5 스키마(`livingcare_graph_v5*.cypher`, Neo4j 없이 정적 텍스트로 사용)의
실제 seed 데이터: Device 16개·CheckItem 18개·MonitoringRule 23개·MedicationKnowledge 10개·
Subject 3명(persona, synthetic) 등 총 88개 관계.

### 3.2 판단 파이프라인 — action/judgement/timing

v5 스키마 자체가 이미 3(+1)분리를 갖고 있다:

| 단계 | v5 관계 | 역할 |
|---|---|---|
| action(관측) | `ObservationSelectionPolicy -[:SELECTS]-> CheckItem` | 무엇을 관측할지 |
| judgement | `MonitoringRule -[:EVALUATES]-> CheckItem` | threshold·severity로 판단 |
| timing | `LoopTerminationPolicy -[:ESCALATES_VIA]-> CheckItem` | 몇 번 돌고 사람에게 넘길지 |
| action(대응) | `ResponseSelectionPolicy -[:SELECTS]-> CheckItem` | escalate 시 무엇을 실행할지 |

WellBeing·Safety는 코드가 규칙을 그대로 평가하는 결정론 경로, Comfort는 LLM이
`retrieve_graph_knowledge`를 스스로 호출하며 판단하는 tool-use 루프(LangChain 미사용,
raw Anthropic tool-calling)로 분기한다 — 이 경계는 숫자 tier가 아니라 seed 정책의
rationale 원문("WellBeing은 결정론", "Comfort는 에이전트 루프")을 그대로 근거로 삼았다.

### 3.3 개인화

- **Threshold 개인화** — `MonitoringRule.vulnerable_condition_value`가 있고
  `Subject.is_vulnerable=true`면 일반 threshold 대신 그 값을 쓴다(WHO 기준 일반 18°C,
  취약군 20°C). 다만 이 필드가 seed에 타입 있는 숫자가 아니라 문자열("20°C 미만")로만
  있어 정규식으로 숫자를 뽑는다 — 실제 데이터의 한계를 그대로 남겨둔 우회.
- **복약 위험 신호** — `Subject -[:TAKES]-> Drug <-[:CONCERNS]- MedicationKnowledge`를
  역추적해 개인별로 다른 위험 약물 목록을 만든다(Beers/STOPP 기준). 판단(escalate)에는
  관여하지 않고 부가 신호로 결과에 노출한다.
- **A2A dispatch 스텁** — 대응 CheckItem이 정해지면 실행 가능한 Device(또는 물리 기기가
  없는 `ci:call_caregiver`의 경우 서비스 워커)를 찾아 `a2a_dispatch`에 표시한다. 실제
  네트워크 호출은 없음 — "여기가 A2A 경계"라는 것만 결과에 남긴다.

## 4. 평가 방법론

**정답 JSON 하나와 문자열로 비교하지 않는다.** 허용 가능한 정책이 여러 개일 수 있다는
전제를 반영해, 케이스마다 "허용 가능한 것"을 집합(set)으로 선언하고 실행 결과가 그
제약조건을 만족하는지 필드별로 채점한다(`eval_graph_cot_agent.py`의 `grade()`).

채점 필드 6개: `escalate`(발화 여부 일치) · `severity`(허용 집합 안에 있는지) ·
`response_check_item`(허용 집합 안에 있는지) · `personalization`(개인별 medication_flags가
기대 집합을 포함하는지) · `required_fields`(escalate 시 필수 필드가 채워졌는지) ·
`task_dispatch`(escalate 시 실제 실행 대상이 정해졌는지).

지표 3개:
- **정책 적합률** = 6개 필드 전부 pass한 케이스 수 / 전체 케이스 수
- **필드별 오류율** = 필드별 fail 비율 — 어느 제약조건에서 주로 틀리는지 분리해서 봄
- **실제 작업 성공률** = escalate=True 케이스 중 `a2a_dispatch.worker`가 채워진 비율
  ("판단은 맞았는데 실행할 곳이 없다"를 정책 적합률과 별개로 잡아내는 지표)

## 5. 결과

테스트 케이스 15개 — persona 3명(김옥순=취약/심부전/기립성저혈압, 박말순=비취약/당뇨,
이갑수=취약/치매/낙상이력) × axis(WellBeing/Safety) × 관측 시나리오(정상/이상, 낮/밤) 12개 +
경계값·회귀 케이스 3개. Comfort축(LLM 에이전트 경로)은 이 환경에 API 키가 없어
자동채점에서 제외했다.

| 지표 | 값 |
|---|---|
| 정책 적합률 | 100.0% (15/15) |
| 실제 작업 성공률 | 100.0% (7/7, escalate 케이스 전부 dispatch 대상 확보) |
| 필드별 오류율 | 전부 0.0% |

**처음 12개는 전부 pass라 그레이더가 실제로 뭔가 잡아내는지 검증이 안 됐다** — 경계값
케이스를 추가하는 과정에서 실제 버그를 하나 찾았다: 야간 8시간 무동작
(`mr_wb2_no_motion_night`, severity=INFO — "야간 무동작은 정상 수면 패턴"이라 대응 불필요)
이 `escalate=true`로 새고 있었다. `ResponseSelectionPolicy`엔 INFO를 받는 min_severity가
없어서 `response_check_item`은 항상 None인데 `escalate`만 true인 모순 상태였다. 원인은
`_evaluate_rules()`가 severity 무관하게 `escalate = bool(triggered)`로만 판정했던 것 —
`escalate = bool(triggered) and severity != "INFO"`로 고쳤다. 이 케이스(`wb_night_info_
boundary_regression`)를 포함해 지금은 15개 전부 pass다.

**개인화가 실제로 다른 결과를 만드는지**는 persona별 `medication_flags` 개수로 확인된다
(정책 적합률 자체는 규칙이 맞게 동작하면 persona 간 차이가 없는 게 정상 — "정확성"과
"개인화"는 다른 축이라 별도 지표로 봤다):

| persona | 취약군 | 활성 복용약 | 위험 flag 수 |
|---|---|---|---|
| 김옥순(subj:kim_oksun_001) | true | furosemide, lorazepam | 3 |
| 박말순(subj:park_malsun_002) | false | glyburide | 1 |
| 이갑수(subj:lee_gapsu_003) | true | risperidone, diphenhydramine | 2 |

같은 axis·같은 관측값이어도 누구의 그래프를 조회하느냐에 따라 다른 위험 신호가 나온다 —
2절에서 말한 "그래프 조회 결과가 개인화의 원천"이라는 주장의 직접적 증거다.

**그림**: `fig_core_metrics.png`(핵심 지표) · `fig_field_error_rate.png`(필드별 오류율) ·
`fig_persona_comparison.png`(persona별 정책 적합률 vs 개인화 신호 수 비교). 이 환경엔
MATLAB이 없어 `eval_report.m` 대신 `make_eval_figures.py`(matplotlib, 같은
`eval_results.json` 입력·같은 파일명)로 생성 — MATLAB이 있는 환경에서는 `eval_report.m`을
그대로 써도 동일한 3장이 나온다.

## 6. 기존 연구 대비 빠진 평가 축 → 실측으로 메움

같은 문제(에이전트 정책 준수·개인화·KG 조회·임상 알림)를 다루는 기존 연구·벤치마크와
대조했을 때 우리 3개 지표에 구조적으로 빠져 있던 축 셋 — **커버리지(검색 recall), 안전도/
편의성(sensitivity/specificity), 개인화가 실제로 판정을 바꾸는가** — 를 실제로 채웠다.
아래는 그 결과다(`eval_robustness.py`).

### 6.1 커버리지 — 다중 CheckItem 스캔 (RAGAS Context Recall 대응)

기존엔 `ObservationSelectionPolicy`가 준 CheckItem 중 **우선순위 1순위만** 봤다
(WellBeing 7개 중 `ci:motion` 하나). `graph_cot_agent.py`의 `_evaluate_rules()`를
**전체 CheckItem을 훑도록** 바꿨다 — 부수 효과로 실제 버그도 하나 더 찾았다: `ci:motion`이
WellBeing·Safety 두 axis의 관측 목록에 동시에 들어있는데, `rule.axis`로 걸러내지 않으면
Safety를 판단하다가 WellBeing 규칙이 새어 들어올 수 있었다(axis 필터 추가로 수정).

- 다중 스캔 결과 WellBeing 케이스의 retriever 호출이 6회 → 11~12회로 늘었다(실제로 더
  넓게 훑는다는 증거). 기존 15개 케이스 결과는 전부 그대로 유지됨(회귀 없음, 재검증 완료).
- 여전히 못 채우는 구멍 하나: `mr_cf6_dark_hallway_night`(axis=Safety, CheckItem=
  `ci:ambient_light`)는 `ci:ambient_light`가 **`obs_comfort_default`에만** 등록돼 있고
  `obs_safety_default`엔 없어서, Safety든 Comfort든 이 규칙에 닿는 경로가 없다 — 이건
  커버리지 로직 문제가 아니라 **seed 데이터 자체의 axis-관측정책 불일치**다(그대로 보고,
  임의로 고치지 않음).

### 6.2 안전도(민감도) · 편의성(특이도) — 경계값 몬테카를로

결정론 시스템이라 같은 관측값을 반복 실행해도 항상 같은 결과가 나와 `pass^k`(τ-bench)는
그대로는 못 쓴다 — 대신 **관측값에 실측 센서 잡음을 섞어 반복 실행**하는 방식으로 바꿨다.
시나리오 3개(WellBeing/motion 주간, Safety/door_status 야간, Safety/bathroom_occupancy)
× 참값 구간 3개(확실히 정상 / 경계 / 확실히 위험) × 200회, 잡음 표준편차 = threshold의 15%.

| 시나리오 | 민감도(안전도) | 특이도(편의성) | 경계에서 escalate율 |
|---|---|---|---|
| WellBeing/motion(주간, 4h) | 100.0% | 100.0% | 50.5% |
| Safety/door_status(야간, 5min) | 100.0% | 99.5% | 44.5% |
| Safety/bathroom_occupancy(20min) | 100.0% | 100.0% | 49.5% |

**해석**: 확실한 위험/정상 구간에서는 잡음이 있어도 민감도·특이도가 거의 100% — 결정론
threshold 로직 자체는 강건하다. 경계 바로 위에서는 escalate율이 44~50%로 정확히 "동전
던지기"에 가깝게 나오는데, 이건 결함이 아니라 **step function의 정상적인 특성**이다(경계에
아주 가까운 참값은 잡음만으로도 넘었다 안 넘었다 한다 — 임상 CDS 문헌이 말하는 "sensitivity/
specificity가 시스템마다 크게 벌어진다"는 현상과 같은 원인). 다음 단계로 이 경계 폭 자체를
좁히는 게(예: 이력현상/hysteresis 추가) 다음 개선 지점.

### 6.3 개인화가 실제로 판정을 바꾸는가 — 경계 관측값 직접 검증

이전엔 "medication_flags 개수가 persona마다 다르다"는 **부가 정보 수준**의 증거만 있었다.
이번엔 `mr_cf1_temp_too_low`(일반군 18°C 미만 / 취약군 20°C 미만)를 18~20°C 사이 관측값
(19°C)으로 직접 찔러서, **같은 관측값·같은 규칙인데 취약군 여부만 다르면 escalate 자체가
갈리는지** 확인했다(Comfort축은 LLM 에이전트 경로라 `run()`으로는 못 돌려서, threshold
비교 로직을 직접 호출하는 화이트박스 테스트로 확인).

| 관측값 | 김옥순(취약군) | 박말순(비취약군) |
|---|---|---|
| 17.5°C | escalate | escalate |
| **19.0°C** | **escalate (개인화 threshold 적용)** | **정상 (일반 threshold 적용)** |
| 20.5°C | 정상 | 정상 |

19°C에서 취약군은 위험(20°C 기준 미달)으로, 비취약군은 정상(18°C 기준 충족)으로 **실제로
갈린다** — 개인화가 부가 정보가 아니라 안전 판정 자체를 바꾼다는 걸 직접 확인했다.

**그림**: `fig_sensitivity_specificity.png`.

### 6.4 "100%가 의심스럽다" — 기존 논문 수치와 정면으로 맞대본 결과

6.2의 100%/99.5%를 그대로 믿기엔 근거가 얕다는 지적이 맞다. 세 가지로 정면 검증했다
(`eval_roc_curve.py` · `eval_noise_sensitivity.py` · `eval_ppv_analysis.py`).

**① 3개 구간이 아니라 18단계 연속 곡선으로 다시 봤다** — 참값/threshold 비율을 0.3배~2.0배까지
0.1 단위로 스윕(N=300/점, 총 16,200회). 결과는 `fig_response_curve.png`: 0.8배에서 8~9%,
0.9배에서 20~27%, threshold 정확히 그 지점에서 46~53%, 1.1배에서 74~80%, 1.2배부터 90%
이상으로 매끄러운 S자 곡선을 그린다. **"100%"는 곡선 전체의 이야기가 아니라 threshold에서
충분히 먼(1.4배 이상) 구간에서만 나오는 값이다** — 3개 구간짜리 표만 봤을 때보다 훨씬 더
정직한 그림.

**② 몬테카를로 200회의 "100%"는 표본 크기 착시였다** — 200회 중 0회 발생했다고 확률이
정말 0은 아니다. 잡음 모델(가우시안)이 정확히 알려진 형태라 정규분포 CDF로 **해석적 정확값**을
구했다: 특이도 = **99.9571%**, 민감도 = **99.9968%**. 진짜 오류 확률은 0.043%(2,300번에 1번
꼴)로, 200회 표본으로는 볼 확률이 낮았을 뿐이다.

**③ 잡음 크기를 스윕해서 "문헌 수준 특이도(78~99%)까지 떨어지려면 잡음이 얼마나 커야
하는가"를 거꾸로 구했다** — 답은 **약 25%**(우리가 실제 쓴 15%의 1.7배). `fig_noise_
sensitivity.png`를 보면 15%에서는 거의 100%였다가 25%를 넘는 순간부터 문헌 범위 안으로
들어간다. **즉 CDS 문헌의 78~99%라는 낮은 특이도는 "센서가 부정확해서"만으로는 설명되지
않는다** — 문헌의 alert fatigue 시스템은 다중 규칙 상호작용, 임상 맥락의 모호함, 데이터
입력 오류 등 우리 시뮬레이션이 아예 모델링하지 않은 요인들을 같이 겪는다. 우리가 잰 건 그
전체 파이프라인 중 **"threshold 비교 로직 하나가 센서 잡음에 강건한가"라는 좁은 질문**이고,
그 질문에 대한 답이 거의 100%인 건 의심스러운 게 아니라 **정확히 그 좁은 질문에 대한 올바른
답**이다.

**④ PPV(양성 예측도)로 현실성 체크** — 특이도가 아무리 높아도 진짜 위험 상황의 발생률
(prevalence)이 낮으면 PPV(경보가 울렸을 때 진짜 위험할 확률)는 떨어진다(베이즈 정리).
해석적 정확값(민감도 99.9968%, 특이도 99.9571%)으로 발생률을 0.1%~50%까지 바꿔가며 PPV를
계산했더니, **0.003% 미만의 극단적으로 낮은 발생률에서만 문헌 PPV 하한(5.8%)보다 낮아진다**
— 그 외 현실적인 발생률 범위에서는 PPV가 70~99.96%로 문헌 범위(5.8~54%)보다 오히려 훨씬
높게 나온다. ③의 결론과 같은 이야기다: 우리가 검증한 좁은 층위(순수 threshold 로직)는
문헌이 보고하는 실전 시스템보다 통계적으로 더 잘 나올 수밖에 없다 — 실전 시스템은 우리가
안 잰 다른 실패 요인들을 같이 겪기 때문이다.

**⑤ τ-bench와는 애초에 비교하면 안 된다** — τ-bench(Sierra, 2024)는 GPT-4o 기준
retail 61.2%·airline 35.2% pass^1을 보고한다(frontier 모델도 대부분 70% 미만). 이건
**LLM이 다중 턴 대화에서 애매한 사용자 요청을 정책 위반 없이 처리하는 과제**의 성공률이고,
우리 결정론 경로(WellBeing/Safety)는 **if-else 임계값 비교**라 과제 자체의 난이도가 다르다.
우리 "정책 적합률 100%"를 τ-bench의 61%/35%와 나란히 놓고 "우리가 더 낫다"고 하면 그 자체가
오도(誤導)다 — 공정한 비교가 되려면 Comfort축(LLM 에이전트 경로)을 API 키로 실제로 돌려서
그 결과를 τ-bench 수치와 맞대야 한다(아직 못 함, 10절 한계 참조).

**결론**: 100%는 의심할 지점이 아니라 **"무엇을 100%라고 주장하는지"를 정확히 좁혀야 할
지점**이었다 — "이 결정론 threshold 로직은 적당한 센서 잡음(15%)에 강건하다"는 좁은 주장은
해석적으로 검증됐고(99.96~100%), "이 시스템이 실전에서 alert fatigue 없이 잘 작동한다"는
넓은 주장은 **여전히 검증 안 됐다**(그러려면 실측 센서·실제 노인·실제 오경보 이력이 필요).
이 보고서는 앞으로도 이 둘을 섞어 쓰지 않는다.

**그림**: `fig_response_curve.png` · `fig_noise_sensitivity.png`.

## 7. 실전 근접 검증 — 도메인 오탐 시나리오 (`eval_domain_scenarios.py`)

"실전에서 잘 작동한다"는 넓은 주장을 검증할 지표는 **이 환경에 없다** — 실측 센서·실제
노인·실제 오경보 이력이 있어야 하고, 우리 시스템 자신을 대상으로 한 시뮬레이션은 아무리
정교해져도(6.4의 몬테카를로·PPV처럼) 여전히 자기참조적이다. 대신 **그나마 가장 실전에
가까운 검증**을 했다: 추상적 가우시안 잡음이 아니라, **그래프 안 규칙들의 rationale에 도메인
전문가가 직접 적어둔 실제 오탐 원인**(배달·환기·웨어러블 충전 등)을 시나리오로 재현해서
시스템이 그 알려진 함정을 실제로 피하는지 대조했다. 지어낸 시나리오가 아니라 전부 rule의
rationale 원문에서 그대로 가져왔다.

| 시나리오 | 근거(rationale 원문) | 결과 |
|---|---|---|
| 택배 수령(문 15분) | "외출/배달/환기 등 정상적 이유로 문을 오래 열어두는 경우가 흔해 오탐 위험" | 미발화 — 정상 |
| 긴 환기(문 25분, threshold 30분 직전) | 위와 동일 | 미발화 — threshold 여유폭 확인 |
| 정상 야간 수면(무동작 7h) | "야간엔 수면 중이라 무동작이 정상" | 미발화 — 정상 |
| 웨어러블 충전 중(단독 미동기화) | "단독으로는 약한 신호로만 취급" | **발화(MILD) but 로봇 확인만** — 보호자 알림 안 감(설계 의도대로) |
| 야간 주방 방문(패턴 기록용) | "당장 조치 안 함, 패턴으로만 축적" | 미발화 — **그런데 threshold 필드가 아예 없어서 "패턴 기록" 자체가 미구현** |
| 장시간 목욕(욕실 25분) | 예외 조항 없음(대조군) | 발화(CONCERN) — 느긋한 목욕도 무조건 위험으로 잡음 |

**정성적 결론(정확도 숫자 아님)**:
- 4번(웨어러블 단독 신호)은 특히 의미 있다 — 단순 escalate=True/False가 아니라 **"약한 신호는
  로봇이 먼저 확인하고, 보호자 알림은 보류한다"는 2단계 대응 설계가 실제로 작동**하는 걸
  확인했다. 이건 6.2~6.4의 threshold 정확성 테스트로는 안 보이던 것이다.
- 5번은 진짜 gap이다 — "패턴으로만 기록"하겠다는 설계 의도가 있는데 실제로는 threshold 필드가
  없어서 이 규칙이 **어떤 관측값을 넣어도 항상 미발화**한다(코드가 틀린 게 아니라 애초에
  "기록" 기능 자체를 안 만들었다). 앞으로 만들 게 명확해졌다.
- 6번은 판정을 유보한다 — "예외 조항이 없다"는 게 결함인지 의도적으로 보수적인 설계인지는
  이 시스템 자체 정보만으로는 못 가른다. 실제 배포 후 오경보 이력이 쌓여야 판단 가능한
  영역이라, 정직하게 "모른다"로 남긴다.

**이게 우리가 보여줄 수 있는 한계다**: 알려진 실전 함정 목록에 대해 하나씩 대조했고, 대부분
설계 의도대로 동작했으며, 실제 gap도 하나 찾았다. 이것도 "실전 검증"은 아니다 — "우리가
아는 실전 함정에 대해서는 대조해봤다"는 정도다. 진짜 실전 검증은 실측 배포 데이터로만
가능하고, 그건 이 프로토타입의 범위 밖이다.

## 8. 지식 증류 대량 시나리오 — Macro-F1 등 표준 분류 지표 (`eval_macro_f1.py`)

7절이 손으로 고른 6개 시나리오였다면, 이번엔 **그래프의 MonitoringRule 23개 전부를 지식
소스로 삼아 154개 시나리오를 기계적으로 생성**했다 — "지식 증류": 사람이 정답을 지어내는
게 아니라 규칙 자체의 threshold·severity·direction에서 정답 라벨을 뽑아낸다. 규칙마다
확실히 발화해야 하는 관측값(threshold의 1.1~2.2배) 5개, 확실히 발화하면 안 되는 관측값
(threshold의 0.1~0.9배) 5개, 경계값 1개를 표준 라이브러리(`sklearn.metrics`)로 채점했다.
`run()`의 axis 라우팅은 우회하고 판정 커널(`_evaluate_single_rule`) 하나만 떼어 테스트했다
— 6.1~7절이 파이프라인 층위였다면 이건 그보다 한 단계 안쪽, 순수 규칙 채점 로직 층위다.

**핵심 발견**: `_evaluate_single_rule`이 인식하는 threshold 필드는 4종류
(`threshold_hours`/`minutes`/`lux`/`celsius` + `_immediate`)뿐이다. 그래프의 23개 규칙 중
**9개(39%)는 이 4종류에 안 들어가는 필드**(`threshold_kg`, `threshold_percent`,
`threshold_seconds`, `threshold_count`, `threshold_mgdl*`, 그리고 필드 자체가 없는
`mr_wb3`)를 쓴다 — 체중 변화, 이동성(의자 일어서기 시간), 복약 반복누락, 혈당,
기립성저혈압(mmHg 하강폭)이 전부 여기 해당한다.

| | N | accuracy | macro-F1 | macro-precision | macro-recall |
|---|---|---|---|---|---|
| **전체 23개 규칙**(미지원 9개 포함) | 154 | 94.2% | **94.1%** | 97.4% | 91.7% |
| 지원 규칙만(14개) | 136 | 100% | 100% | 100% | 100% |

**클래스별(전체 규칙 기준)**: NORMAL F1=94%, INFO F1=92%, MILD F1=98%, CONCERN F1=92%.
Confusion matrix를 보면 오류가 전부 "실제로는 위험(INFO/MILD/CONCERN)인데 NORMAL로
예측"하는 방향으로만 나는데(반대 방향 오류 0건), 이건 로직이 틀려서가 아니라 **미지원
threshold 필드를 가진 규칙은 어떤 관측값을 넣어도 무조건 NORMAL로 나오기 때문**이다 —
9개 규칙의 "positive(발화해야 함)" 시나리오가 전부 이 방향으로 샌다.

**이게 "지원 규칙만 100%"보다 훨씬 의미 있는 숫자다**: 94.1%는 판정 로직 자체의 정확성이
아니라 **"그래프가 정의한 지식 중 시스템이 실제로 구현한 비율"**을 드러낸다. 앞으로 이
9개 규칙의 threshold 타입을 `_evaluate_single_rule`에 추가하면(체중 변화율, 초 단위,
mmHg 하강폭 등) macro-F1이 100%로 수렴할지 확인 가능한, 명확한 다음 작업 목록이 됐다.

**그림**: `fig_confusion_matrix.png` · `fig_per_class_f1.png`.

## 9. 자연어 → device 호출 전체 파이프라인 (`eval_nl_e2e.py`)

6~8절은 전부 axis를 사람이 코드로 직접 넘겨줬다 — **"자연어를 이해했다"는 걸 검증한 적이
없다.** 이 절이 그 빠진 연결고리다. 그래프에 실제로 존재하는 자연어 **전부**(지어낸 문장
없음)를 모았다: `Intent.raw_text` 5개 + `ObservationSelectionPolicy.goal_pattern` 3개 +
`ResponseSelectionPolicy.problem_pattern` 5개 + `KnowledgeQueryPolicy.goal_pattern` 3개
= 16개. 이게 이 그래프가 가진 자연어의 전체 집합이다.

**라우터**: 임베딩 모델이 없어 char n-gram TF-IDF + 코사인 유사도로 axis(WellBeing/Safety/
Comfort/KnowledgeLookup 4-way)를 분류했다 — 그래프의 policy 텍스트(goal_pattern·
decision_basis·rationale) 자체를 기준 문서로 썼다(외부 학습 데이터 없음). 실제 repo의
axis_routing.py도 임베딩이 없을 때 이 수준의 폴백을 쓴다.

사용자가 요청한 4가지를 전부 채점했다:

| 단계 | 무엇을 검증하나 |
|---|---|
| ① 라우팅 | 자연어가 맞는 axis로 가는가 |
| ② 지식 | `grounded_on`(발화 규칙)이 실제로 그 axis 소속인가 — 그래프로 재검증(자기 신뢰 안 함) |
| ③ device | 호출된 device가 그 axis의 `ResponseSelectionPolicy`가 실제로 지정한 기기 목록에 있는가 |
| ④ 정책 | 산출된 severity가 그 시나리오가 의도한 등급과 일치하는가 |

### 결과

**라우팅(16개 전부)**: accuracy=93.8%, macro-F1=94.4% — **15/16 정답**. 유일한 실패는
`intent3`("[system] fall_event triggered for lee_gapsu_003")가 Safety가 아니라
WellBeing으로 갔다. 이건 무작위 오류가 아니라 설명 가능하다 — 이 문장은 사용자 발화가
아니라 **시스템이 만든 로그 문자열**이고(식별자·영문 위주, 한국어 자연어 문맥이 거의
없음), char n-gram 라우터가 기대는 한국어 문맥 신호가 애초에 부족했다. `fig_nl_routing.png`.

**파이프라인 전체(16개 중 실행 가능한 8개만)**: 나머지 8개(조건부 등록형 2개, 지식조회형
5개, Comfort 에이전트형은 obs_comfort/resp_cf_mild 2개지만 라우팅까지는 채점하고 여기서
제외)는 우리가 구현한 흐름(A=true·T=immediate)이 아니라서 억지로 통과시키지 않고
"미구현이라 검증 불가"로 명시했다.

| 단계 | 통과율(N=8) |
|---|---|
| 라우팅 | 87.5% (7/8) |
| 지식조회 | 100.0% |
| device 호출 | 100.0% |
| 정책 반영 | 100.0% |
| **전체(4개 동시 통과)** | **87.5%** |

`fig_nl_funnel.png`. 라우팅만 유일한 병목이고, **일단 axis가 맞으면 그 뒤(지식 조회 →
판단 → device 호출)는 8/8 전부 맞다** — 6~8절에서 이미 검증한 판정 커널의 정확성이
자연어 입력에서도 그대로 유지된다는 뜻. 이게 지금까지 중 가장 완전한 end-to-end 증거다:
자연어에서 시작해 실제로 그래프가 지정한 device까지 정확히 도달하는지, 사람이 axis를
대신 정해주지 않고 확인했다.

**그림**: `fig_nl_routing.png` · `fig_nl_funnel.png`.

### 9.1 합성 100개 스트레스 테스트 — 라우터가 실제로는 얼마나 취약한가 (`eval_synthetic_nl_100.py`)

**주의**: 여기부터는 그래프 원문이 아니라 **내가 지어낸 합성 문장 100개**다(카테고리당 25개,
격식체·구어체·직접질문·간접질문 혼합). 위 9절의 16개와 절대 같은 신뢰도로 인용하면 안 된다
— 9절은 "그래프가 검증했다"고 쓸 수 있지만, 여기는 "라우터의 일반화 능력을 스트레스
테스트했다"로만 쓴다. 이 구분을 report 전체에서 지켰다.

16개짜리 표본은 통계적으로 너무 작았다(카테고리당 4~5개). 100개로 늘려서 **같은 라우터**를
다시 돌렸더니:

| | N | accuracy | macro-F1 |
|---|---|---|---|
| 그래프 원문(9절) | 16 | 93.8% | 94.4% |
| **합성 100개(자연스러운 구어체)** | 100 | **50.0%** | **47.2%** |

**절반 가까이 틀린다.** `fig_16_vs_100_comparison.png`가 이 낙차를 그대로 보여준다. 원인은
confusion matrix(`fig_synthetic100_confusion.png`)에 명확하다 — **KnowledgeLookup으로
쏠린다**(WellBeing 25개 중 14개, Safety 25개 중 10개, Comfort 25개 중 12개가 전부
KnowledgeLookup으로 오분류). recall은 KnowledgeLookup만 96%, 나머지 세 axis는 20~48%.

**왜 이런 일이 생기는가**: char n-gram TF-IDF 라우터가 참조하는 문서(9절에서 그래프의
`goal_pattern`/`decision_basis`/`rationale`을 이어붙인 것)는 **정책 문서체·전문용어
중심**(WHO ICOPE, STEADI, 낙상 통계 등)인데, 실제 발화는 **짧고 구어체**다. 같은
"WellBeing"이어도 그래프 원문("평소 어떻게 지내는지/괜찮은지 확인")과 자연 발화("할머니
요즘 잘 지내시는지 봐줘")는 표면적 어휘가 거의 안 겹친다 — 반면 KnowledgeLookup 참조
문서는 상대적으로 짧고 일반적인 조사·어미 위주라("먹어도 되는지", "확인해줘") 오히려
아무 문장과도 코사인 유사도가 얼추 맞아버린다. **고전적인 학습-테스트 분포 불일치
(train-test distribution shift) 문제**다.

**결론**: 9절의 93.8%는 "라우터가 자연어를 이해한다"는 증거가 아니라 **"참조 문서와
표면적으로 비슷한 문장은 잘 맞춘다"**는 훨씬 좁은 증거였다. 이 100개 스트레스 테스트가
그 착시를 걷어냈다 — 지금 라우터(char n-gram TF-IDF, 정책 텍스트 기준 문서)는 **실전
배포 수준의 자연어 이해에는 못 미친다.** 형태소 분석기 기반 임베딩이나 LLM 기반 라우팅
(API 키 필요, 아직 이 환경에서 미검증)으로 교체해야 한다는 게 이번에 정량적으로 확인됐다.

**그림**: `fig_synthetic100_confusion.png` · `fig_16_vs_100_comparison.png`.

### 9.2 상세 진단 — 왜 무너지는가, 메커니즘 5가지 (`eval_nl_diagnostics.py`)

9.1절은 "무너진다"는 사실과 "학습-테스트 분포 불일치"라는 큰 방향의 원인만 보였다. 여기서는
같은 합성 100개 결과(`eval_synthetic_nl_100_results.json`)를 5가지 각도로 다시 잘라
**정확히 어느 지점이 고장났는지**, 그리고 **왜 하필 KnowledgeLookup으로 쏠리는지**를
메커니즘 수준까지 확인했다.

**① 클래스별 precision/recall/F1** (`fig_diag1_per_class_prf.png`)

| axis | precision | recall | F1 |
|---|---|---|---|
| WellBeing | 62.5% | **20.0%** | 30.3% |
| Safety | 69.2% | 36.0% | 47.4% |
| Comfort | 63.2% | 48.0% | 54.5% |
| KnowledgeLookup | **40.0%** | 96.0% | 56.5% |

패턴이 뚜렷하다 — WellBeing/Safety/Comfort는 **precision은 60%대로 나쁘지 않은데 recall이
낮다**(자기 문장인데 못 알아본다), KnowledgeLookup은 정반대로 **recall은 96%인데 precision이
40%**(아무 문장이나 갖다 붙인다). 즉 문제는 "라우터가 전부 못 맞춘다"가 아니라 **KnowledgeLookup
쪽으로 체계적으로 쏠리는 편향** 하나로 거의 다 설명된다.

**② 예측 분포 편향** (`fig_diag2_prediction_bias.png`)

실제 분포는 카테고리당 25개로 균등한데, 예측 분포는 WellBeing 8개(0.32배) · Safety 13개(0.52배)
· Comfort 19개(0.76배) · **KnowledgeLookup 60개(2.40배)**. ①의 recall/precision 역전을
그대로 숫자로 확인— 라우터가 사실상 "애매하면 KnowledgeLookup"이라는 편향된 사전확률로
동작하고 있다.

**③ 평균 코사인 유사도 행렬** (`fig_diag3_avg_similarity.png`)

카운트가 아니라 **평균 유사도 점수 자체**를 보면 원인이 더 분명해진다:

|  | WellBeing 문서 | Safety 문서 | Comfort 문서 | KnowledgeLookup 문서 |
|---|---|---|---|---|
| WellBeing 문장 | 0.047 | 0.040 | 0.048 | **0.074** |
| Safety 문장 | 0.048 | 0.073 | 0.037 | 0.066 |
| Comfort 문장 | 0.023 | 0.029 | 0.081 | 0.067 |
| KnowledgeLookup 문장 | 0.029 | 0.025 | 0.023 | **0.203** |

KnowledgeLookup 참조 문서는 자기 문장과의 평균 유사도(0.203)가 다른 모든 셀보다 압도적으로
높다 — 문서가 짧고 어휘가 집중돼 있어서(약/진단명/약물 같은 단어가 반복) 벡터가 "뾰족하다".
반면 **WellBeing 문장은 자기 축의 참조 문서(0.047)보다 오히려 KnowledgeLookup 문서와의
유사도(0.074)가 더 높다** — WellBeing 참조 문서가 자기 축 문장도 제대로 못 알아보는 역전
현상이 숫자로 잡힌다.

**④ 확신도(margin) 분포** (`fig_diag4_confidence_margin.png`)

1등 점수와 2등 점수의 차이(margin)를 정답/오답으로 나누면 정답 평균 0.113, 오답 평균 0.047 —
오답은 대략 절반 수준의 margin으로, "확신을 갖고 틀린" 게 아니라 **애초에 근소한 차이로
갈린 판정**이었다. 이 자체는 다소 안심되는 부분이다(라우터가 터무니없이 자신만만하게
틀리는 게 아니라, 애매한 경계에서 밀리는 것) — 하지만 margin이 좁다는 건 그만큼 참조
문서 설계가 카테고리를 잘 분리하지 못한다는 뜻이기도 하다.

**⑤ 참조 문서별 TF-IDF 최고 가중치 n-gram** (`fig_diag5_top_ngrams.png`) — **가장 결정적인 발견**

카테고리별 참조 문서에서 TF-IDF 가중치가 가장 높은(=라우팅 판단에 가장 큰 영향을 주는)
char n-gram 상위 8개를 뽑아보면:

- **WellBeing**: `in, on, co, it, el, ng, ing, io` — **전부 영어 글자 조각**이다.
- **Safety**: `간, safe, afet, 개방, sa, saf, fe, afe` — 역시 절반이 영어 조각(`safe`/`afet`/`saf`/`fe`/`afe`는 전부 "Safety"라는 단어 자체의 부분 문자열).
- **Comfort**: `온, 어, 없, 는, 환경, 온도` — 온전한 한국어 도메인 어휘.
- **KnowledgeLookup**: `약, 단명, 진단, 진단명, y_, 는지, 약물` — 온전한 한국어 도메인 어휘.

원인은 참조 문서를 만들 때 그래프의 `rationale`/`decision_basis` 텍스트를 그대로 이어붙인
것에 있다. 이 텍스트 안에는 "WHO ICOPE", "Frailty Phenotype", "CDC STEADI" 같은 영어
전문용어, 그리고 **축 이름 자체("WellBeing은 tier=1(결정론) 축", "Safety는 즉시…")가
한국어 rationale 문장 속에 영어 그대로 인용**돼 있다. char n-gram(2~4자) 토크나이저는 이걸
그대로 쪼개서 `in`, `on`, `safe`, `afet` 같은 조각을 "이 카테고리의 특징 어휘"로 학습해버린다
— TF-IDF는 문서 간에 희귀할수록 가중치를 높게 주는데, 영어 조각은 다른 3개 문서엔 거의 안
나오니 오히려 가중치가 치솟는다. **결과적으로 WellBeing·Safety 참조 문서의 TF-IDF 벡터
용량 상당 부분이, 한국어 구어체 질문과는 절대 매칭될 수 없는 영어 글자 조각에 낭비되고
있었다.** KnowledgeLookup·Comfort 문서는 상대적으로 영어 전문용어가 적어 이 오염을
덜 겪었고, 그게 ①~③에서 본 성능 격차의 실제 메커니즘이다.

**결론 — 9.1절보다 더 구체적이고 실행 가능한 원인**: "정책 문서체 vs 구어체"라는 큰 분포
차이 위에, **참조 문서 구성 과정 자체의 결함**이 하나 더 겹쳐 있었다 — 영어 전문용어를
거르지 않고 그대로 char n-gram 벡터화에 넣은 것. 이건 임베딩/LLM 라우팅으로 완전히
갈아엎지 않아도 **당장 시도해볼 수 있는 저비용 수정**이다(참조 문서에서 영어 토큰을
제거하거나 별도 가중치를 주는 전처리). 다만 이걸 고쳐도 ③에서 본 "KnowledgeLookup
문서가 구조적으로 더 뾰족하다"는 문제나 9.1절의 근본적인 분포 불일치는 그대로 남는다 —
이번 진단은 "왜 하필 KnowledgeLookup으로 쏠리는가"에 대한 추가 원인 하나를 정량적으로
더 찾아낸 것이지, 47.2%를 저절로 94.4%로 되돌릴 해법은 아니다.

**그림**: `fig_diag1_per_class_prf.png` · `fig_diag2_prediction_bias.png` ·
`fig_diag3_avg_similarity.png` · `fig_diag4_confidence_margin.png` · `fig_diag5_top_ngrams.png`.

### 9.3 9.2절 제안을 실제로 적용해봤다 — 결과는 거의 무효과 (`eval_synthetic_nl_100_v2.py`)

9.2절은 "영어 전문용어를 참조 문서에서 제거하면 저비용으로 시도해볼 만하다"고 제안만 하고
검증은 안 했다. 실제로 적용해봤다 — 참조 문서에서 라틴 문자 조각을 정규식으로 지운 뒤
(WellBeing 682자→467자, Safety 456자→387자, Comfort 292자→234자, KnowledgeLookup 409자
→315자, 전부 실제로 줄어듦을 확인) **같은 합성 100개**로 다시 라우팅했다.

| | accuracy | macro-F1 |
|---|---|---|
| baseline(영어 그대로) | 50.0% | 47.2% |
| stripped(영어 제거) | 49.0% | **46.1%** |

**도움이 안 됐다 — 오히려 미세하게 더 나빠졌다(Δ-1.0%p).** 클래스별로 쪼개보면 상쇄가
일어난다: WellBeing recall은 20%→24%(+4%p)로 살짝 좋아졌지만, Safety recall이
36%→28%(**-8%p**)로 더 크게 나빠져 순효과가 마이너스다(`fig_english_strip_comparison.png`).

**왜 안 통했는가**: Safety에서 새로 틀린 두 문장("현관문 계속 열려있는 거 아니야?",
"문 열린 채로 오래 방치돼있는지 확인해줘")의 실제 점수를 까보면, 영어를 지운 뒤
**Safety 자체 점수도 올랐다**(0.0622→0.0737, 0.1218→0.1444) — 즉 영어 조각이 Safety를
방해하고 있던 게 아니었다. 문제는 **KnowledgeLookup 점수가 그보다 더 많이 올랐다는
것**(0.0603→0.0760, 0.1157→0.1458, 상대 증가폭이 Safety보다 큼) — 참조 문서 길이가
줄면서 TF-IDF 정규화가 전체적으로 재조정됐는데, 이미 9.2절 진단③에서 확인한 대로
KnowledgeLookup 문서가 구조적으로 더 뾰족하고 촘촘해서(자기-유사도 0.203, 다른 문서의
2.5배 이상) 이 재조정의 수혜를 더 크게 받았다. 두 사례 모두 원래도 Safety와
KnowledgeLookup 점수가 근소했던(margin < 0.007) 경계 케이스였고, 영어 제거가 그 근소한
우위를 뒤집은 것이다.

**결론**: 영어 전문용어 오염(진단⑤)은 실재하는 현상이지만, 그것을 제거해도
KnowledgeLookup의 구조적 우위(진단③, 문서가 짧고 어휘가 집중돼 벡터가 뾰족함)는 전혀
줄어들지 않는다 — 오히려 다른 문서가 짧아지면서 상대적으로 더 유리해질 수도 있다.
9.1~9.2절에서 나온 "학습-테스트 분포 불일치"와 "영어 오염"은 둘 다 실재하는 문제였지만,
**이 라우터의 47.2%를 끌어올릴 진짜 레버는 아니었다** — char n-gram TF-IDF라는 방법
자체의 한계(형태소 분석 기반 임베딩이나 LLM 라우팅으로 교체)가 여전히 유일하게 검증된
해법이라는 게 이번 실험으로 오히려 더 분명해졌다.

**그림**: `fig_english_strip_comparison.png`.

## 10. 남은 한계

- **[핵심] NL 라우터가 자연스러운 구어체에서 macro-F1 47.2%로 붕괴** — 9.1절에서 확인.
  9절의 93.8%는 참조 문서(정책 문서체)와 표면적으로 비슷한 문장에서만 나오는 좁은 숫자였다.
  char n-gram TF-IDF를 형태소 분석 기반 임베딩이나 LLM 라우팅으로 교체하기 전엔 이 시스템을
  "자연어를 이해한다"고 말할 수 없다 — 지금까지 나온 한계 중 가장 실사용에 직접적인 영향을
  준다(축 라우팅이 전체 파이프라인의 유일한 입구이므로).
- **참조 문서의 영어 전문용어 오염(진단 ⑤)은 실재하지만, 제거해도 라우터가 안 나아짐** —
  9.3절에서 실제로 라틴 문자를 제거하고 재검증했다: macro-F1 47.2%→46.1%(Δ**-1.0%p**,
  오히려 미세 악화). WellBeing recall은 +4%p 좋아졌지만 Safety recall이 -8%p 나빠져
  상쇄됐다 — 원인은 문서가 짧아지며 TF-IDF 정규화가 재조정될 때 KnowledgeLookup의 이미
  더 뾰족한 벡터(진단 ③)가 상대적으로 더 큰 수혜를 입었기 때문. **저비용 전처리로는 이
  붕괴를 못 되돌린다는 게 실측으로 확인됐다** — 형태소 분석 기반 임베딩이나 LLM 라우팅
  교체가 유일하게 남은, 검증되지 않은 해법이다.
- **`pass^k`(반복 실행 신뢰성) 여전히 미측정** — API 키가 있어야 하는 Comfort축(LLM
  에이전트 경로)에서만 의미가 있는 지표라, 이 환경에선 계속 막혀 있다.
- **15개 기본 케이스가 전부 pass** — 6.1~6.3의 실측으로 강건성은 별도로 확인했지만, 기본
  그레이더(`eval_graph_cot_agent.py`)의 커버리지(존재하지 않는 axis, subject_id 오탈자 등)는
  여전히 비어 있다.
- **취약군 threshold가 정규식 추출** — 타입 있는 필드로 seed 스키마를 보강하면 해소된다.
- **`mr_cf6_dark_hallway_night` 데이터 불일치** — 6.1에서 발견한 대로 seed 쪽에서
  `obs_safety_default`에 `ci:ambient_light`를 추가해야 해소된다(코드 문제 아님).
- **`mr_wb3_night_kitchen_visit` "패턴 기록" 미구현** — 7절에서 발견. threshold 필드가 없어
  이 규칙은 항상 미발화하고, "당장 조치 안 하고 패턴으로 축적"하겠다는 설계 의도(기록
  자체)는 구현된 적이 없다. escalate 로직이 아니라 별도의 로깅 메커니즘이 필요.
- **진짜 실전 검증(field validation)은 이 프로토타입 범위 밖** — 7절이 할 수 있는 최선은
  "알려진 실전 함정과 대조"였다. 실측 센서·실제 대상자·실제 오경보 이력이 쌓여야만 "실전에서
  잘 작동한다"는 넓은 주장을 검증할 수 있다.
- **판정 커널이 그래프 규칙의 61%(14/23)만 구현** — 8절 macro-F1에서 정량화됨. 체중
  변화율(`threshold_kg`/`threshold_percent`) · 초 단위 이동성(`threshold_seconds`) ·
  혈당(`threshold_mgdl*`) · 복약 반복누락 횟수(`threshold_count`) · 기립성저혈압
  하강폭(`threshold_*_drop_mmhg`) 5가지 threshold 유형을 `_evaluate_single_rule`에
  추가하면 9개 규칙이 전부 커버된다 — 범위가 명확한 다음 작업.
- **NL 라우터가 자연 발화(6개)에서만 검증됨, 조건부/지식조회 흐름(8개) 자체가 미구현** —
  9절에서 라우팅은 16개 전부 채점했지만 다운스트림(지식/device/정책)은 8개만 실행 가능했다.
  `intent2`("낙상 나면 바로 알려줘")·`intent4/5`(복약 질문)류는 axis 라우팅과 별개로
  `ConditionRegistration`/`IntentKnowledgeLookup` 파이프라인 자체를 새로 만들어야 검증
  가능하다. 또한 char n-gram TF-IDF 라우터는 시스템이 만든 로그성 문자열(`intent3`)에서
  실패했다 — 형태소 분석기나 임베딩 기반 라우터로 바꾸면 해소될 가능성이 높다.
