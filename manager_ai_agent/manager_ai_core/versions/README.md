# 4개 버전 비교 — 같은 시나리오, 완전히 다른 프레임워크

> 2026-09-01 밤 작업. "할머니 괜찮은지 확인해줘"(모션 5시간 무동작, 심박 38bpm 서맥)라는
> **동일 시나리오**를 서로 코드도 프레임워크도 겹치지 않는 4가지 방식으로 구현하고 비교했다.
> v1은 기존에 이미 있던 것, v2~v4는 논문 조사를 근거로 오늘 밤 새로 만들었다.

## 요약표

| | v1 (기존) | v2 BDI | v3 형식검증 | v4 효율성 라우팅 |
|---|---|---|---|---|
| **프레임워크** | Neo4j 그래프RAG + 결정론 rule + LangGraph(선택적) | 순수 상징 BDI 추론 루프(자체 구현) | Z3 SMT 제약해결기 | asyncio + 사전컴파일 결정테이블 |
| **핵심 은유** | "지식을 검색해서 조립" | "믿음→욕구→의도 심적상태" | "안전을 수학적으로 증명" | "미리 계산해두고 캐시로 서빙" |
| **근거 문헌** | (자체 설계, 이 세션에서 축적) | HoCaMA·Virtual Carer·"Multi-agent Interactions for AAL"(BDI 패러다임) | VeriGuard(2025)·AgentGuard(2025) | Cognitive Edge Computing(2025)·SC-MAS/MasRouter(2025) |
| **판단 방식** | if/else 필드매칭(`_rule_fires`) | Desire.condition 람다 + 우선순위 | 1차논리 제약의 SAT/UNSAT | 정렬된 임계값 테이블 조회 |
| **안전 보장 방식** | 코드리뷰로 신뢰 | 없음(우선순위 순서에 암묵적으로 의존) | **수학적 증명**(반증 불가능성) | 없음(컴파일 시점 정확성에 의존) |
| **런타임 비용** | 그래프쿼리+임베딩(수십~수백ms) | 메모리 내 연산(~ms) | SMT 풀이(수 ms) | 캐시 적중 시 0.01ms |
| **확장성(새 지식 추가)** | Cypher만 추가하면 자동 반영 | Desire/Plan을 손으로 추가해야 함 | 안전명세를 손으로 추가해야 함 | 재컴파일 필요(오프라인 스텝) |
| **약점** | 임베딩 미세조정 안 됨, 실행로직 미연결 다수 | Plan 라이브러리가 도메인전문가 수작업 | 안전명세 자체가 틀리면 "증명된 오답" | 컴파일 안 된 조합은 결국 폴백(=v1으로 회귀) |

## 실행 결과 나란히 보기

```
[v1]  motion(5h) → wb_r1 발화 → dispatch_robot: "맵을 켜서 Grandma을(를) 찾고..."
      heartrate(38bpm) → wb_r12_bradycardia 발화 → call_emergency_services: 119(응급의료)

[v2]  [숙고] 활성 Desire: respond_to_cardiac_emergency, ensure_no_prolonged_inactivity
      [실행] call_119 + robot_dispatch — 우선순위(100 vs 50)로 순서만 다르게 결정

[v3]  [제안] 아무것도 안 함 → [검증] SAT(위반 가능, 반례 있음) → [수리] 안전명세를
      만족하는 행동 재합성 → {call_emergency: True, dispatch_robot: True} → UNSAT
      (위반 불가능이 수학적으로 증명됨) → 승인

[v4]  motion→table→dispatch_robot(0.05ms) / heartrate→table→call_emergency(0.05ms)
      / temperature→컴파일 안 됨→llm_fallback(800ms) → 재호출 시 전부 캐시(0.01ms, 100% 절감)
```

네 버전 다 **motion=dispatch_robot, heartrate=call_emergency**라는 같은 결론에 도달한다 —
같은 지식(오늘 낮에 만든 AxisKnowledge)을 표현 방식만 바꿔 태웠기 때문. 다른 건 "그
결론에 어떻게 도달했는지, 그리고 그 도달 과정이 무엇을 보장하는지"다.

## 각 버전이 실제로 잘하는 것

- **v1**: 그래프에 지식만 넣으면 top-k 검색부터 다 자동 — **지식이 계속 늘어나는 상황**에 제일 유리
- **v2 (BDI)**: 여러 목표가 충돌할 때 "지금 뭘 우선할지"를 명시적 심적상태로 관리 — **여러 desire가 동시에 경쟁하는 복잡한 상황**(예: 로봇 배터리 부족 desire vs 관찰 desire)에 확장하기 좋음
- **v3 (Z3)**: "이 행동이 안전한가"를 테스트케이스 몇 개가 아니라 **모든 가능한 입력에 대해 수학적으로 증명** — 오탐 한 번이 생명과 직결되는 심박수/화재 같은 tier=1 규칙에 제일 잘 맞음. 이번 세션에서 실제로 로직 버그(`repair()`가 자기 자신을 반환)를 검증기가 스스로 SAT/UNSAT 불일치로 잡아냈다
- **v4 (엣지)**: 배터리 제약이 있는 실제 로봇/엣지 디바이스에 배포한다면 **압도적으로 저렴** — 반복 관측(예: 5분마다 같은 상태 재확인)에서 비용이 사실상 0에 수렴

## 발전 방향 제안

이 넷은 서로 배타적이지 않다. 특히 **v3의 안전검증 레이어를 v1의 최종 게이트로 얹는 조합**을
추천한다 — v1(지식 검색+조립)이 행동을 제안하면, 실행 직전에 v3 스타일 Z3 검증을 한 번
통과시키는 것. 이러면:
- v1의 확장성(그래프만 키우면 됨)은 그대로 유지
- tier=1(생명 직결) 규칙만 골라 Z3 안전명세로 이중화 → "코드가 맞게 짜였는지"를 테스트가
  아니라 증명으로 보장
- v4의 캐시 레이어도 v1 위에 얇게 얹을 수 있음(반복 관측 낭비 줄이기) — 이건 순수 엔지니어링
  이라 리스크 없이 바로 적용 가능

즉 v1을 골격으로 유지하되, **v3을 안전 게이트로, v4를 성능 레이어로 부분 흡수**하는 게
전부 새로 만드는 것보다 현실적이다. v2(BDI)는 지금처럼 desire가 2개뿐일 땐 과합인데,
나중에 "동시에 여러 돌봄 목표가 자원(로봇 1대)을 놓고 경쟁"하는 시나리오가 생기면
그때 v1 위에 얹을 만하다.

## 참고문헌

- Rao & Georgeff, *BDI Agents: From Theory to Practice*, 1995 (BDI 패러다임 원전)
- [HoCaMA: Home Care Hybrid Multiagent Architecture](https://www.academia.edu/33273345/HoCaMA_Home_Care_Hybrid_Multiagent_Architecture)
- [Multi-agent Interactions for Ambient Assisted Living](https://www.researchgate.net/publication/220992594_Multi-agent_Interactions_for_Ambient_Assisted_Living)
- [Intention Recognition for Multiple Agents](https://arxiv.org/pdf/2112.02513)
- [VeriGuard: Enhancing LLM Agent Safety via Verified Code Generation](https://arxiv.org/abs/2510.05156) (2025)
- [Provably Secure Agent Guardrail](https://arxiv.org/pdf/2605.29251) (2025)
- [Cognitive Edge Computing: A Comprehensive Survey on Optimizing Large Models and AI Agents for Pervasive Deployment](https://arxiv.org/abs/2501.03265) (2025)
- [SC-MAS: Constructing Cost-Efficient Multi-Agent Systems with Edge-Level Heterogeneous Collaboration](https://arxiv.org/pdf/2601.09434) (2025)

## 파일 지도

```
versions/
  v2_bdi/bdi_agent.py, scenario.py           — python scenario.py로 실행
  v3_formal_verification/verified_agent.py    — python verified_agent.py로 실행 (z3-solver 필요, pip install z3-solver)
  v4_efficiency_routing/edge_router.py, scenario.py — python scenario.py로 실행 (표준 라이브러리만 사용)
  README.md                                    — 이 문서
```

## 정직하게 밝히는 한계

- 넷 다 이번 세션에서 급조한 **데모 스케일**이다 — v1처럼 108개 지식 전부를 커버하지 않고, "할머니 괜찮은지" 시나리오(motion+heartrate, 필요시 temperature)만 재현했다.
- v2의 Desire/Plan, v3의 안전명세, v4의 DECISION_TABLE은 전부 **오늘 v1에서 확인한 값(threshold_hours=4, threshold_bpm=40)을 손으로 옮겨 적은 것**이다 — v1처럼 Neo4j에서 자동으로 끌어오지 않는다(각 프레임워크의 설계상 의도된 차이이기도 하다: BDI/형식검증/엣지컴파일은 원래 "미리 정제된 지식"을 전제로 하는 패러다임).
- 정식 벤치마크(지연시간 실측, 안전성 커버리지 비교)는 안 했다 — 위 표의 "런타임 비용"은 실측이 아니라 설계상 기대치다.
