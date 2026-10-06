"""파일럿 파이프라인 — 검색 → 생성 → 검증 → 배정, 그리고 results.jsonl 기록.

실행 예 (레포 루트에서):
  python3 -m manager_ai_agent.manager_ai_core.pilot_pipeline.pipeline \\
      --td data/limo-1.td.json --td data/factory.td.json --places data/places.json \\
      --vocab docs/pilot-spec/vocab.json --gold data/gold_smoke.jsonl \\
      --llm mock --out results.jsonl
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from manager_ai_agent.manager_ai_core.pilot_pipeline import assign, generation, retrieval, validator
from manager_ai_agent.manager_ai_core.pilot_pipeline.graph_stub import StubGraph


def run_one(row: dict, graph, llm, embedder=None, *, run: int = 1, temperature: float = 0.0,
            top_k: int = 3, hops: int = 1, retries: int = 1, examples=None) -> dict:
    """gold 한 줄을 파이프라인에 통과시켜 results 한 줄을 만든다."""
    cand = retrieval.retrieve(row["phrases"], graph, embedder, top_k=top_k, hops=hops)
    messages = generation.build_messages(row["utterance"], row["phrases"], cand, graph, examples)
    gen = generation.generate(llm, messages, temperature, retries)
    raw = gen["output"]

    final_rule, assigned, clarification, reason = None, [], None, None
    if raw is None:
        validation = {"passed": False, "first_failed_check": "schema", "detail": gen["error"]}
        verdict = "reject"
    elif "unsupported" in raw:
        validation = {"passed": False, "first_failed_check": "declined", "detail": str(raw["unsupported"])}
        verdict = "reject"
    else:
        validation = validator.validate_rule(raw, graph)
        if validation["passed"]:
            decision = assign.decide(raw, graph)
            verdict, assigned = decision["verdict"], decision["assigned_devices"]
            clarification, reason = decision["clarification"], decision["reason"]
            final_rule = raw if verdict == "execute" else None
        else:
            verdict = "reject"

    return {
        "id": row["id"], "run": run, "model": llm.name, "temperature": temperature,
        "candidates": {k: cand[k] for k in ("actions", "devices", "places", "classes")},
        "retrieval_scores": cand["scores"],
        "raw_llm_output": raw, "attempts": gen["attempts"],
        "validation": validation, "verdict": verdict, "final_rule": final_rule,
        "assigned_devices": assigned, "clarification": clarification, "reason": reason,
    }


def _read_jsonl(path: str) -> list[dict]:
    return [json.loads(l) for l in Path(path).read_text(encoding="utf-8").splitlines() if l.strip()]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--td", action="append", required=True, help="TD 파일 (여러 번)")
    ap.add_argument("--places", required=True)
    ap.add_argument("--vocab", required=True)
    ap.add_argument("--gold", required=True)
    ap.add_argument("--out", required=True)
    # Ollama 는 지금 쓰지 않아 선택지에서 뺐다(generation.py 에 주석으로 보존): choices=["mock", "ollama", ...]
    ap.add_argument("--llm", choices=["mock", "claude-cli", "anthropic"], default="mock")
    ap.add_argument("--model", default=None)
    ap.add_argument("--embedder", choices=["none", "st"], default="none")
    ap.add_argument("--runs", type=int, default=1)
    ap.add_argument("--temperature", type=float, default=0.0)
    ap.add_argument("--top-k", type=int, default=3)
    ap.add_argument("--hops", type=int, default=1)
    ap.add_argument("--retries", type=int, default=1)
    ap.add_argument("--examples", default=None, help="few-shot 예시 JSONL: utterance, phrases, output")
    args = ap.parse_args(argv)

    graph = StubGraph.load(args.td, args.places, args.vocab)
    gold = _read_jsonl(args.gold)
    if args.llm == "mock":
        llm = generation.MockLLM(gold, graph)
    elif args.llm == "claude-cli":
        llm = generation.ClaudeCLILLM(args.model or "sonnet")
    # elif args.llm == "ollama":   # 다시 쓰려면 generation.OllamaLLM 과 함께 푼다
    #     llm = generation.OllamaLLM(args.model or "qwen2.5:7b")
    else:
        llm = generation.AnthropicLLM(args.model or "claude-haiku-4-5-20251001")
    embedder = retrieval.SentenceEmbedder.load() if args.embedder == "st" else None
    examples = _read_jsonl(args.examples) if args.examples else None

    with open(args.out, "w", encoding="utf-8") as f:
        for run in range(1, args.runs + 1):
            for row in gold:
                result = run_one(row, graph, llm, embedder, run=run, temperature=args.temperature,
                                 top_k=args.top_k, hops=args.hops, retries=args.retries,
                                 examples=examples)
                f.write(json.dumps(result, ensure_ascii=False) + "\n")
                print(f"{row['id']:>6} run{run} gold={row['gold_verdict']:<18} -> {result['verdict']:<18}"
                      f" check={result['validation']['first_failed_check']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
