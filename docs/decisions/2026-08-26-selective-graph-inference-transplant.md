# 2026-08-26 · graph-inference 순수 코어만 main에 선별 이식한다

> **정본 반영** `SOT.md` · `CLAUDE.md` · `manager_ai_agent/CLAUDE.md` · `manager_ai_agent/manager_ai_core/CLAUDE.md` · `manager_ai_agent/manager_ai_core/kg_mapping/CLAUDE.md` · `manager_ai_agent/manager_ai_core/policy_generation/CLAUDE.md` · `manager_ai_agent/knowledge_graph/CLAUDE.md` · `docs/architecture.md` · `docs/status.md` · `docs/api-spec.md` · `docs/harness/manager-ai.md` · `docs/conventions.md`

`mac/graph-inference`에서 축 라우팅, 결정론적 규칙 평가, 사전 해소 context→C2 오케스트레이션 아이디어만 가져온다.
main 구현은 scorer·사전 해소 context·관측값을 주입받는 순수 코드로 두고, KG/Neo4j 파일 직접 접근,
누락 관측의 mock 자동 대체, device-specific RobotTask/LLM sequence 생성은 제거한다. 따라서 출력은
L1/L2 계약이 아니며 Worker로 직접 보내지 않는다.

판정 전에 규칙 ID·severity·시간 문맥·predicate·유한 수치와 양의 escalation 임계값을 검증한다.
빈 규칙이나 context·source·관측 누락은 정상으로 간주하지 않고 `indeterminate`/`complete=false`로
보존한다. 다만 완결성 결함과 별개로 실제 escalation 근거가 하나라도 있으면 최상위 상태는
`escalate`를 유지해 경고를 억제하지 않는다.

표준 A2A HTTP 전환과 Frontend gateway는 정본 승인이 없어서 이식하지 않는다. Worker wrapper와
`NavigateFunction`/`ObserveFunction` rename은 D-17 소유 경계와 SOT D-11을 지키기 위해 이식하지 않는다.
격리 가능한 graph-inference 회귀는 표준 라이브러리 `unittest` 17건으로 고정한다.
