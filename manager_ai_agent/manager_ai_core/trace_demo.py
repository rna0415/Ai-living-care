"""
trace_demo.py  —  파이프라인 한 번을 '단계마다 데이터를 다 펼쳐서' 보여주는 학습용 추적기.

목적: 자연어 한 문장이 들어가서 로봇 intent가 나올 때까지, 각 단계가
      "무엇을 받아서 무엇을 내놓는지"를 눈으로 따라가며 이해하기 위한 것.

사용법 (직접 질문을 바꿔가며 실험해보세요):
    python trace_demo.py
    python trace_demo.py "방 온도 너무 낮은 거 아니야?" 15
    python trace_demo.py "가스레인지 안 껐어?" 3
    (두 번째 인자는 시각(hour). 낮/밤 규칙이 갈리는 걸 보려면 15와 3을 비교)
"""

import sys
import os
import json

# Windows 콘솔/Git Bash에서 한글이 깨지지 않게 출력 인코딩을 UTF-8로 고정
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

sys.path.append(os.path.join(os.path.dirname(__file__), "kg_mapping"))
sys.path.append(os.path.join(os.path.dirname(__file__), "policy_generation"))

from graph_retrieval import GraphRetriever
from rule_evaluator import evaluate
from sequence_generator import generate_sequence, _choose_backend
from pipeline import (
    determine_active_axes, build_observations,
    select_goal_device, safety_gate, AXIS_BY_ID,
)
from axis_routing import get_axis_scores, THRESHOLD, USING_REAL_EMBEDDINGS


def _hr(title):
    print("\n" + "─" * 68)
    print(f"■ {title}")
    print("─" * 68)


def trace(query: str, hour: int):
    print("=" * 68)
    print(f"입력 자연어: \"{query}\"   (시각 hour={hour})")
    print("=" * 68)

    # ── 단계 0: 라우팅 준비 ────────────────────────────────────────
    mode = "진짜 임베딩(ko-sroberta)" if USING_REAL_EMBEDDINGS else "폴백(단어겹침·부정확)"
    threshold = THRESHOLD if USING_REAL_EMBEDDINGS else 0.35

    # ── 단계 1: 임베딩 라우팅 (자연어 → 어느 축?) ──────────────────
    _hr("1단계 [라우팅]  자연어를 임베딩해서 어느 축(axis)에 걸리나 계산")
    print(f"  라우팅 모드: {mode} (threshold={threshold})")
    scores = get_axis_scores(query)
    print(f"  축별 유사도 점수:")
    for aid, s in scores.items():
        mark = "  ← 활성(threshold 넘음)" if s >= threshold else ""
        print(f"     {AXIS_BY_ID[aid]['label']:10s} {round(s,3)}{mark}")
    active = determine_active_axes(scores, threshold)
    if not active:
        print("\n  → 어떤 축도 threshold를 못 넘음 → OOS(우리 영역 아님). 여기서 종료.")
        return

    print(f"\n  → 활성 축: {[AXIS_BY_ID[a]['label'] for a in active]}")

    with GraphRetriever() as g:
        for axis_id in active:
            label = AXIS_BY_ID[axis_id]["label"]
            print("\n" + "#" * 68)
            print(f"#  축 '{label}' 처리")
            print("#" * 68)

            # ── 단계 2: C1 그래프 조회 ──────────────────────────────
            _hr(f"2단계 [C1 그래프 조회]  '{label}' 축에서 tier·기기·규칙을 Neo4j로 조회")
            ctx = g.fetch_axis_context(axis_id)
            print(f"  tier: {ctx['tier']}  (LLM에게 허용된 재량 상한, 불변)")
            print(f"  가져온 기기 {len(ctx['devices'])}개:")
            for d in ctx["devices"]:
                fns = [f"{f['name']}(reachable={f.get('reachable')})" for f in d["functions"]]
                print(f"     - {d['device_id']:26s} slot={d['slot']:14s} "
                      f"cost={d['cost_hint']:4s} risk={d['risk_tier']}")
                print(f"       기능={fns}  상태(State)={d['states']}")
            print(f"  가져온 판단 규칙 {len(ctx['rules'])}개:")
            for r in ctx["rules"]:
                thr = (r.get("threshold_hours") or r.get("threshold_minutes")
                       or r.get("threshold_celsius"))
                print(f"     - {r['rule_id']:26s} slot={r.get('slot'):12s} "
                      f"severity={r.get('severity'):12s} 임계={thr} "
                      f"시간대={r.get('time_context','-')}")

            # ── 단계 3: 관측값 구성 ─────────────────────────────────
            _hr("3단계 [관측값]  각 슬롯의 '현재 값'을 준비 (State 비면 mock)")
            obs, mock_slots = build_observations(ctx)
            print(f"  관측값: {obs}")
            if mock_slots:
                print(f"  (실제 센서값이 아직 그래프에 없어 mock 사용: {mock_slots})")

            # ── 단계 4: C2 규칙 평가 (판단) ────────────────────────
            _hr("4단계 [C2 규칙 평가=판단]  관측값을 규칙 임계값과 비교 (코드가 판단, LLM 아님)")
            evaluation = evaluate(ctx["rules"], obs, hour)
            print(f"  시간대 판정: {evaluation['time_context']}")
            if evaluation["triggered_rules"]:
                print(f"  발화한 규칙:")
                for r in evaluation["triggered_rules"]:
                    print(f"     - {r['rule_id']} (severity={r['severity']})")
                    print(f"       근거: {r['rationale'][:60]}...")
            else:
                print("  발화한 규칙: 없음")
            print(f"  ▶ should_escalate = {evaluation['should_escalate']}")

            # ── 단계 5: device fallback + 코드 게이트 ───────────────
            _hr("5단계 [device fallback + 안전 게이트]  reachable한 device를 순서대로 시도, "
                "위험 기기(로봇)는 저비용 센서를 먼저 거쳤는지 코드가 확인")
            device, tried = select_goal_device(ctx["devices"])
            if len(tried) > 1:
                print(f"  device fallback: {tried[:-1]} 실패 → {device['device_id'] if device else 'None'} 사용")
            ok, reason = safety_gate(ctx, device, obs)
            print(f"  목표 기기: {device['device_id'] if device else '없음(no_device)'}")
            print(f"  게이트 통과? {ok} ({reason})")
            gated_device = device if ok else None

            # ── 단계 6: C3 생성 (조립, tier<=2 결정론 / tier>=3 에이전트 루프) ─────
            _hr(f"6단계 [C3 생성=조립]  판단 결과를 로봇 intent로 조립 "
                f"(tier={ctx['tier']}, 백엔드: {_choose_backend()})")
            seq = generate_sequence(label, evaluation, gated_device, ctx["rules"],
                                    tier=ctx["tier"], axis_id=axis_id, hour=hour, retriever=g)
            print("  최종 결과:")
            print(json.dumps(seq, ensure_ascii=False, indent=4))
            if seq.get("agent_trace"):
                print(f"  [에이전트 루프] {len(seq['agent_trace'])}회 도구 호출: "
                      f"{[t['tool'] for t in seq['agent_trace']]}")


if __name__ == "__main__":
    query = sys.argv[1] if len(sys.argv) > 1 else "할머니 괜찮은지 확인해줘"
    hour = int(sys.argv[2]) if len(sys.argv) > 2 else 15
    trace(query, hour)
