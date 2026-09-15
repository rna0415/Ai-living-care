"""
graph_tools.py  —  tier>=3 에이전트 루프가 쓰는 LangChain Tool 래퍼 (Graph RAG)

v3 스키마(2026-08-31, Axis 제거·AxisKnowledge 승격) 대응 — axis_id 대신 slot을 받는다.

전부 읽기 전용이고, 여기서 새 Cypher를 만들지 않는다 — graph_retrieval.py(C1)에
이미 있는 GraphRetriever 메서드가 가져온 결과를 그대로 감쌀 뿐이다. 에이전트는
"어떤 도구를 언제·몇 번 부를지"만 스스로 결정하고, 그 도구가 실제로 무엇을 하는지
(Cypher 조회, 규칙 판단)는 여전히 고정된 결정론 코드다.

의도적 설계 편차: LangChain의 흔한 "Graph RAG" 패턴(GraphCypherQAChain 등, LLM이
Cypher를 즉석 생성)은 쓰지 않는다. graph_retrieval.py의 "그래프는 읽기 전용(MATCH)만"
· "Cypher는 한 파일에만 격리" 원칙을 깨기 때문이다. 여기 도구들은 전부 이미 검증된
고정 쿼리(fetch_knowledge_context 등)를 파이썬 함수로만 한 번 더 감싼 것이다.

build_graph_tools(retriever)가 이미 열려 있는 GraphRetriever 연결을 재사용한다
(도구마다 새 Neo4j 연결을 열지 않음) — pipeline.py/sequence_generator.py에서 호출.
"""

from langchain_core.tools import tool

from graph_retrieval import GraphRetriever
from rule_evaluator import evaluate as _evaluate_rules


def build_graph_tools(retriever: GraphRetriever) -> list:
    """읽기 전용 LangChain Tool 목록을 만든다. 반환된 도구들은 retriever를 공유한다."""

    @tool
    def search_devices_for_slot(slot: str) -> list[dict]:
        """이 slot(예: "temperature")에 연결된 device 목록을 반환한다.
        읽기 전용 — 그래프에 아무것도 쓰지 않는다. 각 device는 device_id, slot,
        risk_tier, cost_hint, functions(이름+reachable 여부), states,
        device_knowledge를 담는다."""
        return retriever.fetch_knowledge_context(slot)["devices"]

    @tool
    def search_axis_knowledge(slot: str) -> list[dict]:
        """이 slot의 판단 규칙(AxisKnowledge) 목록을 반환한다. 읽기 전용 — 그래프에
        아무것도 쓰지 않는다. 각 규칙은 rule_id, slot, tier, threshold_*, severity,
        rationale 등을 담는다."""
        return retriever.fetch_knowledge_context(slot)["rules"]

    @tool
    def check_function_reachable(slot: str, device_id: str, function_name: str) -> bool:
        """특정 slot 안의 특정 device가 가진 특정 function이 지금 reachable(사용
        가능)한지 확인한다. 읽기 전용. functions는 device_knowledge + function node
        제약의 핵심 — 여기서 false가 나온 function은 goal에 절대 포함하면 안 된다."""
        devices = retriever.fetch_knowledge_context(slot)["devices"]
        for d in devices:
            if d["device_id"] != device_id:
                continue
            for f in d.get("functions", []):
                if f.get("name") == function_name:
                    return bool(f.get("reachable"))
            return False
        return False

    @tool
    def get_device_knowledge(slot: str, device_id: str) -> list[dict]:
        """특정 device의 DeviceKnowledge(제약·근거 문서)를 반환한다. 읽기 전용.
        지금은 그래프에 DeviceKnowledge가 채워져 있지 않아 대부분 빈 리스트를
        반환한다 — 나중에 채워지면 자동으로 동작한다."""
        devices = retriever.fetch_knowledge_context(slot)["devices"]
        for d in devices:
            if d["device_id"] == device_id:
                return d.get("device_knowledge", [])
        return []

    @tool
    def evaluate_axis_rules(rules: list[dict], observations: dict, hour: int) -> dict:
        """규칙 목록 + 관측값 + 시각으로 "우려 상황인가/에스컬레이션 해야 하는가"를
        판단한다. 이 도구 자체는 100% 결정론 코드(policy_generation.rule_evaluator)이며
        LLM이 판단을 대신하지 않는다 — 에이전트는 이 도구를 언제·몇 번 부를지만
        결정한다. should_escalate, triggered_rules, highest_severity를 반환한다."""
        return _evaluate_rules(rules, observations, hour)

    return [
        search_devices_for_slot,
        search_axis_knowledge,
        check_function_reachable,
        get_device_knowledge,
        evaluate_axis_rules,
    ]
