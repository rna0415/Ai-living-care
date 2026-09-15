# -*- coding: utf-8 -*-
"""
v2_bdi/bdi_agent.py — Belief-Desire-Intention(BDI) 기반 Manager-Worker 멀티에이전트.

v1(Neo4j 그래프RAG + 결정론 rule_evaluator + 선택적 LangGraph 에이전트, 임베딩 검색)과
프레임워크 자체가 다르다 — 그래프 조회·임베딩 검색이 여기엔 전혀 없다. 대신 고전
BDI 에이전트 아키텍처(Rao & Georgeff, "BDI Agents: From Theory to Practice", 1995)를
직접 구현한다. 노인돌봄(AAL) 도메인에 BDI를 적용한 선행 문헌 — HoCaMA(Home Care Hybrid
Multiagent Architecture), Virtual Carer(AAL expert system), "Multi-agent Interactions
for Ambient Assisted Living" — 이 전부 BDI 패러다임으로 "돌봄인의 행동/과업을
표현"한다고 밝히고 있어, 그 설계를 그대로 코드로 옮겼다.

BDI 사이클: 지각(Worker→Belief 갱신) → 옵션생성(활성 Desire) → 숙고(우선순위로 Intention
커밋) → 수단-목적 추론(Plan의 다음 step 실행) → (다음 tick에) 실패/완료 시 재평가.

v1과의 핵심 차이:
  - v1: "질의 → top-k 검색 → 규칙평가 → 정책조회 → 조립"의 선형 파이프라인 함수 호출
  - v2: Manager가 독립된 Worker 객체들과 메시지를 주고받으며 자기 심적상태(Belief/
        Desire/Intention)를 스스로 갱신하는 에이전트 루프 — Worker는 Manager 내부
        함수가 아니라 자기 완결적인 sense/act 인터페이스를 가진 별도 객체.
"""

from dataclasses import dataclass


# ---------------------------------------------------------------------
# Belief — 세계에 대한 사실. Worker가 지각해서 갱신한다.
# ---------------------------------------------------------------------
class BeliefBase:
    def __init__(self):
        self._facts: dict[str, object] = {}

    def update(self, key, value):
        self._facts[key] = value

    def get(self, key, default=None):
        return self._facts.get(key, default)

    def snapshot(self) -> dict:
        return dict(self._facts)


# ---------------------------------------------------------------------
# Worker — 지각(sense) 또는 행동(act) 능력 하나만 갖는 독립 에이전트.
# ---------------------------------------------------------------------
class Worker:
    def __init__(self, name: str, sense_fn=None, act_fn=None):
        self.name = name
        self._sense_fn = sense_fn
        self._act_fn = act_fn

    def sense(self):
        return self._sense_fn() if self._sense_fn else None

    def act(self, **kwargs):
        return self._act_fn(**kwargs) if self._act_fn else {"status": "no_actuator"}


# ---------------------------------------------------------------------
# Desire — 추구 가능한 목표. condition(beliefs)이 참이면 "활성"된다.
# ---------------------------------------------------------------------
@dataclass
class Desire:
    name: str
    priority: int
    condition: callable   # (BeliefBase) -> bool
    plan_name: str


# ---------------------------------------------------------------------
# Plan — Desire를 달성하는 구체적 행동 순서(수단-목적 추론의 "수단").
# ---------------------------------------------------------------------
@dataclass
class Plan:
    name: str
    steps: list   # list[callable(beliefs, workers) -> dict]


# ---------------------------------------------------------------------
# Intention — Manager가 지금 커밋한 (desire, plan) 쌍 + 진행 상태.
# ---------------------------------------------------------------------
@dataclass
class Intention:
    desire: Desire
    plan: "Plan"
    step_index: int = 0
    done: bool = False


class ManagerAgent:
    """BDI 추론 사이클을 도는 Manager. Worker들을 소유하고 메시지(함수 호출)로 통신한다."""

    def __init__(self, workers: dict[str, Worker], desires: list[Desire], plans: dict[str, Plan]):
        self.workers = workers
        self.desires = sorted(desires, key=lambda d: -d.priority)
        self.plans = plans
        self.beliefs = BeliefBase()
        self.intentions: list[Intention] = []
        self.trace: list[str] = []

    def perceive(self):
        """① 지각 — 모든 Worker에게 sense() 메시지를 보내 Belief를 갱신한다."""
        for key, worker in self.workers.items():
            value = worker.sense()
            if value is not None:
                self.beliefs.update(key, value)
                self.trace.append(f"[지각] {worker.name} -> belief[{key}]={value}")

    def deliberate(self) -> list[Desire]:
        """② 옵션생성(우선순위순) — 지금 Belief로 활성화되는 Desire를 찾는다."""
        options = [d for d in self.desires if d.condition(self.beliefs)]
        self.trace.append(f"[숙고] 활성 Desire: {[d.name for d in options]}")
        return options

    def commit(self, options: list[Desire]):
        """③ 커밋 — 이미 같은 Desire를 추구 중이 아니면 새 Intention을 만든다."""
        committed = {i.desire.name for i in self.intentions if not i.done}
        for d in options:
            if d.name in committed:
                continue
            plan = self.plans[d.plan_name]
            self.intentions.append(Intention(desire=d, plan=plan))
            self.trace.append(f"[커밋] Intention 생성: {d.name} (plan={plan.name})")

    def execute(self) -> list[dict]:
        """④ 수단-목적 추론 — 미완료 Intention마다 Plan의 다음 step을 실행한다."""
        results = []
        for intention in self.intentions:
            if intention.done:
                continue
            steps = intention.plan.steps
            if intention.step_index >= len(steps):
                intention.done = True
                continue
            step = steps[intention.step_index]
            result = step(self.beliefs, self.workers)
            self.trace.append(
                f"[실행] {intention.desire.name}::{intention.plan.name}[{intention.step_index}] -> {result}")
            intention.step_index += 1
            if intention.step_index >= len(steps):
                intention.done = True
            results.append({"desire": intention.desire.name, "result": result})
        return results

    def cycle(self) -> list[dict]:
        """BDI 사이클 한 바퀴: 지각 → 숙고 → 커밋 → 실행."""
        self.perceive()
        options = self.deliberate()
        self.commit(options)
        return self.execute()
