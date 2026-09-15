"""
call_trace_demo.py  —  '어떤 함수가 어떤 순서로 호출되나'를 눈으로 보는 데모.

실제 파이프라인 함수들을 얇게 감싸서(wrap), 호출될 때마다
   [번호] 모듈.함수()
를 찍는다. 중첩 호출(예: generate_sequence 안에서 _choose_backend, _ollama_intent)도
자동으로 순서대로 나온다.

사용법: python call_trace_demo.py
"""

import sys
import os
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

sys.path.append(os.path.join(os.path.dirname(__file__), "kg_mapping"))
sys.path.append(os.path.join(os.path.dirname(__file__), "policy_generation"))

import pipeline
import sequence_generator
from graph_retrieval import GraphRetriever
from pipeline import AXIS_BY_ID, THRESHOLD, USING_REAL_EMBEDDINGS

_n = 0


def _wrap(label, fn):
    """호출 시 [번호] 모듈.함수() 를 찍고 원래 함수를 실행하는 래퍼."""
    def w(*args, **kwargs):
        global _n
        _n += 1
        print(f"      [{_n:2}] {label}.{fn.__name__}()")
        return fn(*args, **kwargs)
    w.__name__ = fn.__name__
    return w


# pipeline 네임스페이스의 단계 함수들을 감싼다 (pipeline이 이 이름으로 호출하므로)
for name in ["get_axis_scores", "determine_active_axes", "build_observations",
             "select_goal_device", "safety_gate", "evaluate", "generate_sequence"]:
    setattr(pipeline, name, _wrap("pipeline", getattr(pipeline, name)))

# sequence_generator 내부 함수들도 감싼다 (generate_sequence가 내부에서 호출 → 중첩으로 보임).
# generate_sequence_agentic/_validate_agentic/_get_chat_model은 tier>=3(현재 Comfort)
# 에이전트 루프를 탈 때만 실제로 찍힌다 — 이 파일이 이름 목록만으로 존재 여부를
# 확인하지 않는 구조라서, 예전엔 이미 사라진 이름(_build_prompt 등)이 방치돼 있었다
# (2026-08-24, select_goal_device 개명 작업 중 발견해 함께 정리).
for name in ["_choose_backend", "_build_decision", "_call_ollama", "_call_claude",
             "_fallback_contract", "_validate", "generate_sequence_agentic",
             "_validate_agentic", "_get_chat_model"]:
    setattr(sequence_generator, name, _wrap("sequence_generator", getattr(sequence_generator, name)))

# GraphRetriever.fetch_axis_context (C1 조회)도 감싼다
_orig_fetch = GraphRetriever.fetch_axis_context
def _fetch_wrap(self, axis_id):
    global _n
    _n += 1
    print(f"      [{_n:2}] graph_retrieval.GraphRetriever.fetch_axis_context()")
    return _orig_fetch(self, axis_id)
GraphRetriever.fetch_axis_context = _fetch_wrap


def drive(query: str, hour: int, g: GraphRetriever):
    """pipeline.run과 같은 순서로 단계를 밟되, 호출 추적이 잘 보이게 최소 출력."""
    global _n
    _n = 0
    print("=" * 64)
    print(f'예시: "{query}"   (hour={hour})')
    print("=" * 64)
    threshold = THRESHOLD if USING_REAL_EMBEDDINGS else 0.35

    print("  [단계 1] 라우팅")
    scores = pipeline.get_axis_scores(query)
    active = pipeline.determine_active_axes(scores, threshold)
    print(f"        → 활성 축: {[AXIS_BY_ID[a]['label'] for a in active] or '없음(OOS)'}")
    if not active:
        print("        → OOS. 여기서 종료 (C1~C3 호출 안 됨)\n")
        return

    for axis_id in active:
        label = AXIS_BY_ID[axis_id]["label"]
        print(f"  [단계 2] '{label}' 축: C1 그래프 조회(tier 포함)")
        ctx = g.fetch_axis_context(axis_id)
        print(f"        → tier={ctx['tier']}")
        print(f"  [단계 3] 관측값 구성")
        obs, _m = pipeline.build_observations(ctx)
        print(f"  [단계 4] C2 규칙 평가(판단)")
        ev = pipeline.evaluate(ctx["rules"], obs, hour)
        print(f"  [단계 5] device fallback 선택 + 안전 게이트")
        dev, tried = pipeline.select_goal_device(ctx["devices"])
        if len(tried) > 1:
            print(f"        → fallback: {tried[:-1]} 실패 → {dev['device_id'] if dev else 'None'}")
        ok, _r = pipeline.safety_gate(ctx, dev, obs)
        print(f"  [단계 6] C3 생성(조립, tier={ctx['tier']})  ← 이 안에서 아래 함수들이 중첩 호출됨")
        seq = pipeline.generate_sequence(label, ev, dev if ok else None, ctx["rules"],
                                         tier=ctx["tier"], axis_id=axis_id, hour=hour, retriever=g)
        print(f"        → 결과: escalate={seq['escalate']}, source={seq['source']}")
        if seq.get("agent_trace"):
            print(f"        → 에이전트 루프 도구 호출: {[t['tool'] for t in seq['agent_trace']]}")
    print()


if __name__ == "__main__":
    examples = [
        ("할머니 괜찮은지 확인해줘", 15),      # 정상 에스컬레이션 (로봇 intent 생성)
        ("방 온도 너무 낮은 거 아니야?", 15),   # 판단은 되나 로봇 없는 축(Comfort)
        ("파스타 만드는 법 알려줘", 15),        # OOS (1단계에서 종료)
    ]
    with GraphRetriever() as g:
        for query, hour in examples:
            drive(query, hour, g)
