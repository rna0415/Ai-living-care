"""
graph_retrieval.py  —  C1: 그래프 조회 (RAG retrieval)

v3 스키마(2026-08-31, Axis 제거·AxisKnowledge 승격) 대응 버전.

역할:
    slot(예: "motion")이 정해지면 Neo4j 지식그래프에서 "판단에 필요한 재료"를 뽑아
    하나의 context 묶음으로 돌려준다. 조회만 하고 판단은 하지 않는다
    (판단은 C2 rule_evaluator, 생성은 C3 sequence_generator 담당).

    axis 개념은 더 이상 검색 대상이 아니다 — retriever(임베딩/LLM)가 문장에서 직접
    slot을 찾아내고, 그 slot으로 AxisKnowledge를 곧장 조회한다("두 번 검색" 문제 해소,
    docs/decisions/ 참조 없이 이 파일 docstring만으로 이해되게 아래에 원리를 남긴다):
    이전엔 문장→axis(1차 검색)→그 axis의 axis_knowledge 전부 훑기(2차 검색)였는데,
    axis가 사람이 붙인 또 다른 "단어"일 뿐이라 1차 검색 자체가 불안정했다. slot은
    물리 센서 종류를 가리키는 구체명사라 그 문제가 훨씬 덜하고, AxisKnowledge가 이미
    slot 필드를 갖고 있어 그래프 재구조화만으로 검색을 한 번으로 줄일 수 있었다.

설계 원칙 (변함없음):
    1. read-only  — State 말고는 어떤 노드도 CREATE/SET 하지 않는다.
    2. 데이터 주도 — slot/기기 이름을 코드에 하드코딩하지 않는다.
    3. 격리       — 그래프에 대한 모든 Cypher는 이 파일에만 있다.

tier: 이제 Axis가 아니라 AxisKnowledge 각 rule의 속성이다. 같은 slot 안의 rule들이
서로 다른 tier를 가질 수도 있으므로(지금 데이터는 안 그렇지만), fetch_knowledge_context()는
그 slot의 rule tier 중 최솟값(가장 보수적인 tier)을 대표값으로 반환한다 — 재량 상한은
항상 더 엄격한 쪽으로 접어야 안전하기 때문.
"""

import os
from neo4j import GraphDatabase


def _load_local_env():
    """
    Windows에서 setx/시스템 환경변수는 이미 떠 있는 터미널·IDE에는 반영되지 않는다
    (레지스트리만 갱신되고 살아있는 프로세스는 갱신 전 환경을 그대로 물려받는다).
    그 문제를 피하려고 이 폴더의 .env(git에 올라가지 않음)를 직접 읽어 채운다.
    이미 환경변수로 설정된 값은 덮어쓰지 않는다(setdefault).
    """
    env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    if not os.path.exists(env_path):
        return
    with open(env_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip())


_load_local_env()

# --- 접속 정보 (환경변수 또는 이 폴더의 .env로 덮어쓸 수 있음. 기본값 = 로컬 Docker Neo4j) ---
NEO4J_URI = os.environ.get("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.environ.get("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.environ.get("NEO4J_PASSWORD", "livingcare123")


# ---------------------------------------------------------------------
# Cypher — 모든 그래프 지식은 여기에만. (원칙 3: 격리)
# ---------------------------------------------------------------------

# 한 slot에 딸린 device들 + 각 device의 기능/상태/기기지식. AxisKnowledge를 거쳐
# APPLIES_TO로 연결된 device를 찾는다(N:M — 여러 rule이 같은 device를 공유할 수 있어
# WITH DISTINCT d로 먼저 중복을 접는다).
_DEVICES_QUERY = """
MATCH (r:AxisKnowledge {slot: $slot})-[:APPLIES_TO]->(d:Device)
WITH DISTINCT d
OPTIONAL MATCH (d)-[:HAS_FUNCTION]->(f:Function)
OPTIONAL MATCH (d)-[:HAS_STATE]->(s:State)
OPTIONAL MATCH (d)-[:HAS_DEVICE_KNOWLEDGE]->(dk:DeviceKnowledge)
RETURN d.device_id   AS device_id,
       d.device_class AS device_class,
       d.slot         AS slot,
       d.risk_tier    AS risk_tier,
       d.cost_hint    AS cost_hint,
       [x IN collect(DISTINCT f) WHERE x IS NOT NULL | {name: x.name, reachable: x.reachable}] AS functions,
       [x IN collect(DISTINCT s) WHERE x IS NOT NULL | {key: x.key, value: x.value, updated_by: x.updated_by}] AS states,
       [x IN collect(DISTINCT dk) WHERE x IS NOT NULL | properties(x)] AS device_knowledge
ORDER BY d.cost_hint, d.device_id
"""

# 한 slot에 해당하는 판단규칙(AxisKnowledge)을 통째로 조회 — day/night 등 세부
# time_context 필터링은 여기서 안 하고 rule_evaluator.py(C2)가 결정론으로 한다.
_RULES_QUERY = """
MATCH (r:AxisKnowledge {slot: $slot})
RETURN properties(r) AS rule
"""

_ALL_KNOWLEDGE_QUERY = "MATCH (r:AxisKnowledge) RETURN properties(r) AS rule ORDER BY r.slot, r.rule_id"

_ALL_SLOTS_QUERY = """
MATCH (r:AxisKnowledge)
RETURN r.slot AS slot, min(r.tier) AS tier, count(r) AS rule_count
ORDER BY slot
"""


class GraphRetriever:
    """Neo4j 연결을 쥐고 있는 조회기. with 문으로 쓰면 자동으로 닫힌다."""

    def __init__(self, uri=NEO4J_URI, user=NEO4J_USER, password=NEO4J_PASSWORD):
        # DeviceKnowledge(아직 0개)나 State.value(아직 null) 관련 "존재하지 않음"
        # 알림은 지금 단계에선 예상된 빈칸이라, 서버가 아예 안 보내도록 끈다.
        try:
            self._driver = GraphDatabase.driver(
                uri, auth=(user, password), notifications_min_severity="OFF"
            )
        except TypeError:
            self._driver = GraphDatabase.driver(uri, auth=(user, password))

    def close(self):
        self._driver.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    # --- 공개 API ------------------------------------------------------

    def list_slots(self) -> list[dict]:
        """그래프에 있는 모든 slot과 대표 tier를 반환. (라우팅/검증/디버깅용)"""
        with self._driver.session() as session:
            return session.execute_read(lambda tx: tx.run(_ALL_SLOTS_QUERY).data())

    def list_all_knowledge(self) -> list[dict]:
        """모든 AxisKnowledge를 반환 — retriever 학습 데이터/후보 문서 풀 구성용."""
        with self._driver.session() as session:
            rows = session.execute_read(lambda tx: tx.run(_ALL_KNOWLEDGE_QUERY).data())
        return [row["rule"] for row in rows]

    def fetch_knowledge_context(self, slot: str) -> dict:
        """
        한 slot의 context 묶음을 반환:
            {
              "slot":    "motion",
              "tier":    1,        # 이 slot에 걸린 rule들의 tier 중 최솟값(보수적으로)
              "devices": [ {device_id, slot, risk_tier, cost_hint,
                            functions[], states[], device_knowledge[]}, ... ],
              "rules":   [ {rule_id, slot, threshold_*, severity, rationale, tier, ...}, ... ],
            }
        """
        with self._driver.session() as session:
            devices = session.execute_read(
                lambda tx: tx.run(_DEVICES_QUERY, slot=slot).data()
            )
            rule_rows = session.execute_read(
                lambda tx: tx.run(_RULES_QUERY, slot=slot).data()
            )

        rules = [row["rule"] for row in rule_rows]
        tiers = [r["tier"] for r in rules if r.get("tier") is not None]

        return {
            "slot": slot,
            "tier": min(tiers) if tiers else 1,  # 못 찾으면 가장 보수적인 1로 폴백
            "devices": devices,
            "rules": rules,
        }

    def fetch_context_package(self, slots: list[str]) -> dict[str, dict]:
        """여러 slot(multi-label)을 한꺼번에. slot -> context 딕셔너리."""
        return {slot: self.fetch_knowledge_context(slot) for slot in slots}


# ---------------------------------------------------------------------
# 단독 실행 데모: 실제 그래프에서 motion slot의 재료가 어떻게 뽑히는지 확인
# ---------------------------------------------------------------------
if __name__ == "__main__":
    import sys
    import json

    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

    with GraphRetriever() as g:
        print("=== 그래프에 있는 slot 목록 ===")
        for slot in g.list_slots():
            print(f"  tier={slot['tier']}  {slot['slot']:12s} rules={slot['rule_count']}")

        print("\n=== motion slot context 묶음 ===")
        ctx = g.fetch_knowledge_context("motion")
        print(json.dumps(ctx, ensure_ascii=False, indent=2))
