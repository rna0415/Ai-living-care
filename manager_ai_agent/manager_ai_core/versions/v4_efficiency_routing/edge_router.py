# -*- coding: utf-8 -*-
"""
v4_efficiency_routing/edge_router.py — 효율성(지연시간/비용) 중심 엣지 라우팅 프레임워크.

근거 문헌: "Cognitive Edge Computing: A Comprehensive Survey on Optimizing Large Models
and AI Agents for Pervasive Deployment"(2025) — 온디바이스/엣지 배포에서 컨텍스트 압축·
동적 라우팅·적응적 지능(캐시 적중 시 재계산 생략)을 표준 최적화 축으로 제시. "SC-MAS:
Constructing Cost-Efficient Multi-Agent Systems with Edge-Level Heterogeneous
Collaboration"(2025, MasRouter) — 멀티에이전트 시스템에서 요청마다 무거운 모델을 쓰지
않고 난이도별로 라우팅해 비용을 낮추는 설계.

핵심 아이디어: "요청이 올 때마다 그래프 순회 + 임베딩 계산"(v1) 하지 않는다. 대신
오프라인에서 결정테이블을 한 번 컴파일해두고(compile once), 요청 시점엔 캐시→컴파일
테이블→(그래도 없으면) 무거운 폴백 순으로 **티어를 낮은 비용부터 시도**한다. 여러 slot도
순차(v1의 for loop)가 아니라 asyncio로 동시에 처리한다.

v1(런타임 Neo4j+임베딩)·v2(BDI 심적상태 시뮬레이션)·v3(SMT 형식검증)과 완전히 다른
프레임워크: asyncio 이벤트루프 + 사전 컴파일 결정테이블 + LRU 캐시 + 티어별 비용계측.
"""

import asyncio
import time


# ---------------------------------------------------------------------
# ① 오프라인 컴파일 — 그래프를 "요청 시점에 조회"하지 않고 배포 전에 한 번만 읽어
#    순수 파이썬 자료구조로 굳힌다. 실제 배포라면 빌드 스크립트가 Neo4j에서 읽어 이
#    딕셔너리를 생성 — 여기선 v1 그래프에서 확인한 핵심 rule 3개를 그 결과라고 가정.
# ---------------------------------------------------------------------
def compile_decision_table(rows: list[dict]) -> dict:
    table: dict[str, list[tuple]] = {}
    for r in rows:
        table.setdefault(r["slot"], []).append((r["threshold"], r["direction"], r["action"]))
    return table


DECISION_TABLE = compile_decision_table([
    {"slot": "heartrate", "threshold": 40, "direction": "below", "action": "call_emergency_services"},
    {"slot": "motion", "threshold": 4.0, "direction": "above_eq", "action": "dispatch_robot"},
    {"slot": "temperature", "threshold": 18, "direction": "below", "action": "dispatch_robot"},
])

# 티어별 상대 비용(ms) — 실측이 아니라 "캐시 << 컴파일테이블 << LLM 폴백"이라는
# 엣지AI 문헌의 정성적 순서를 정량화해서 보여주기 위한 추정치.
TIER_COST_MS = {"cache": 0.01, "table": 0.05, "llm_fallback": 800.0}


class EdgeRouter:
    """캐시 → 컴파일테이블 → LLM폴백 순으로 티어를 낮은 비용부터 시도하는 라우터."""

    def __init__(self):
        self._cache: dict[tuple, dict] = {}
        self.stats = {"cache_hits": 0, "table_hits": 0, "llm_fallbacks": 0}

    def _table_lookup(self, slot: str, value) -> dict | None:
        for threshold, direction, action in DECISION_TABLE.get(slot, []):
            if direction == "below" and value is not None and value < threshold:
                return {"action": action}
            if direction == "above_eq" and value is not None and value >= threshold:
                return {"action": action}
        return None

    async def route(self, slot: str, value) -> dict:
        key = (slot, value)
        t0 = time.perf_counter()

        if key in self._cache:
            self.stats["cache_hits"] += 1
            return {**self._cache[key], "tier": "cache", "cost_ms": TIER_COST_MS["cache"]}

        hit = self._table_lookup(slot, value)
        if hit is not None:
            self.stats["table_hits"] += 1
            result = {**hit, "tier": "table", "cost_ms": TIER_COST_MS["table"]}
            self._cache[key] = {"action": hit["action"]}
            return result

        # L2 폴백: 컴파일 테이블에 없는 조합 -> 비용이 큰 모델 호출이 필요하다고 가정(mock).
        self.stats["llm_fallbacks"] += 1
        await asyncio.sleep(0)  # 실제로는 여기서 LLM 호출(비동기 I/O)
        result = {"action": "no_action_uncompiled", "tier": "llm_fallback", "cost_ms": TIER_COST_MS["llm_fallback"]}
        self._cache[key] = {"action": result["action"]}
        return result

    async def route_many(self, observations: dict[str, object]) -> dict[str, dict]:
        """여러 slot을 순차(v1의 for loop)가 아니라 asyncio.gather로 동시에 처리."""
        keys = list(observations.keys())
        results = await asyncio.gather(*(self.route(k, observations[k]) for k in keys))
        return dict(zip(keys, results))
