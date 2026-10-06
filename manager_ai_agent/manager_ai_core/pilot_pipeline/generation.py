"""생성 — 프롬프트를 만들고 LLM 을 불러 Rule JSON 원본을 얻는다.

LLM 은 교체 가능하다(MockLLM / OllamaLLM / AnthropicLLM). 출력은 검증 전의 원본이며,
파싱 실패는 retries 만큼 다시 시도한 뒤 오류로 돌려준다. LLM 은 후보 안의 값만 쓰고,
이행할 수 없으면 {"unsupported": "<이유>"} 로 거부할 수 있다 (SPEC §9).
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path

_SCHEMA_PATH = Path(__file__).resolve().parents[3] / "docs" / "pilot-spec" / "rule.schema.json"

SYSTEM_PROMPT = """너는 사용자의 한국어 요청을 기기 제어 Rule(JSON)로 바꾸는 번역기다.

규칙:
1. 아래 [후보]에 있는 ID 만 쓴다. 후보에 없는 동작, 기기, 장소, 객체 클래스를 만들어 내지 않는다.
2. 요청을 후보로 이행할 수 없거나(없는 기기·장소·동작) 무엇을 요청하는지 알 수 없으면 Rule 대신
   {"unsupported": "<이유 한 문장>"} 만 출력한다. 비슷한 후보로 억지로 채우지 않는다.
3. 출력은 JSON 객체 하나만. 설명, 코드 펜스 금지.
4. event 는 항상 {"request-event": ["user-request"]}.
5. 동작은 종류에 따라 슬롯에 넣는다.
   - motion-action: 이동 계열 (destination = 장소 ID)
   - perception-action: 인식 계열 (object-class = 객체 클래스 ID)
   - control-action: 기기 제어 (target = 기기 ID, args = 동작의 input 스키마에 맞는 값)
   - report-action: 결과를 알려 달라는 요청일 때 ["report-result"]
6. 대상 기기가 요청에서 특정되지 않으면 target 을 생략한다. 특정되면 반드시 그 기기 ID 를 쓴다.
7. 순서가 있으면 step 을 1부터 매긴다.
8. 장소 조건이 있으면 condition.geographic-location.destination 에 장소 ID 를 쓴다.

[Rule 형식 예 — 이 ID 들은 형식을 보이는 것일 뿐 후보가 아니다]
{"name": "short-name", "event": {"request-event": ["user-request"]},
 "condition": {"geographic-location": {"destination": ["place-x"]}},
 "action": {"control-action": [{"step": 1, "action-type": "turn-on", "target": ["device-x"]}]}}
"""


def _candidate_block(candidates: dict, graph) -> str:
    nodes = {n["node_id"]: n for n in graph.searchable_nodes()}
    lines = ["[후보]"]
    lines.append("기기:")
    for dev in candidates["devices"]:
        node = nodes.get(dev, {})
        loc = graph.device_location(dev)
        lines.append(f"- {dev} (위치: {loc or '없음'}): {node.get('text', '')}")
        for nid, n in nodes.items():
            if n["kind"] == "action" and n["device"] == dev:
                schema = graph.input_schema(dev, n["identity"])
                inp = f" input={json.dumps(schema, ensure_ascii=False)}" if schema else ""
                lines.append(f"    · 동작 {n['identity']} [{graph.slot_of(n['identity'])}]{inp}")
    lines.append("장소: " + (", ".join(
        f"{p}({'/'.join(nodes[p]['names'][1:])})" if p in nodes else p for p in candidates["places"]
    ) or "없음"))
    lines.append("객체 클래스: " + (", ".join(candidates["classes"]) or "없음"))
    return "\n".join(lines)


def build_messages(utterance: str, phrases: list[str], candidates: dict, graph,
                   examples: list[dict] | None = None) -> list[dict]:
    schema = json.dumps(json.loads(_SCHEMA_PATH.read_text(encoding="utf-8")),
                        ensure_ascii=False, separators=(",", ":"))
    messages = [{"role": "system", "content": SYSTEM_PROMPT + "\n[출력 스키마]\n" + schema}]
    for ex in examples or []:
        messages.append({"role": "user", "content": f"요청: {ex['utterance']}\n어구: {ex['phrases']}"})
        messages.append({"role": "assistant", "content": json.dumps(ex["output"], ensure_ascii=False)})
    messages.append({
        "role": "user",
        "content": f"{_candidate_block(candidates, graph)}\n\n요청: {utterance}\n어구: {phrases}\nJSON:",
    })
    return messages


# ---- LLM 백엔드 ---------------------------------------------------------
class MockLLM:
    """배선 시험용 가짜 LLM. gold 를 보고 정해진 출력을 돌려준다(실제 번역이 아님)."""

    name = "mock"

    def __init__(self, gold_rows: list[dict], graph):
        self._rows = {r["utterance"]: r for r in gold_rows}
        self._graph = graph

    def complete(self, messages: list[dict], temperature: float = 0.0) -> str:
        utter = re.search(r"요청: (.*)\n어구:", messages[-1]["content"]).group(1)
        row = self._rows[utter]
        event = {"request-event": ["user-request"]}
        if row["label"] == "normal":
            return json.dumps({"name": row["id"], "event": event, "action": row["gold_rule"]},
                              ensure_ascii=False)
        if row["label"] == "ambiguous":
            devs = row["gold_candidates"]
            shared = set(self._graph.devices_with("turn-on")) >= set(devs)
            action = "turn-on" if shared else next(
                a for a in ("start", "turn-off", "stop")
                if set(self._graph.devices_with(a)) >= set(devs))
            return json.dumps({"name": row["id"], "event": event,
                               "action": {"control-action": [{"step": 1, "action-type": action}]}})
        return json.dumps({"unsupported": f"mock: {row.get('invalid_reason', 'invalid')}"})


class OllamaLLM:
    def __init__(self, model: str = "qwen2.5:7b", url: str | None = None, seed: int = 0):
        self.name = f"ollama:{model}"
        self._model, self._seed = model, seed
        self._url = (url or os.environ.get("OLLAMA_URL", "http://localhost:11434")).rstrip("/")

    def complete(self, messages: list[dict], temperature: float = 0.0) -> str:
        import requests

        resp = requests.post(f"{self._url}/api/chat", timeout=300, json={
            "model": self._model, "messages": messages, "stream": False, "format": "json",
            "options": {"temperature": temperature, "seed": self._seed},
        })
        resp.raise_for_status()
        return resp.json()["message"]["content"]


class AnthropicLLM:
    """Anthropic Messages API (requests 만 사용). ANTHROPIC_API_KEY 필요. 아직 실행해 보지 않았다."""

    def __init__(self, model: str = "claude-haiku-4-5-20251001"):
        self.name = f"anthropic:{model}"
        self._model = model

    def complete(self, messages: list[dict], temperature: float = 0.0) -> str:
        import requests

        system = "\n".join(m["content"] for m in messages if m["role"] == "system")
        chat = [m for m in messages if m["role"] != "system"]
        resp = requests.post(
            "https://api.anthropic.com/v1/messages", timeout=120,
            headers={"x-api-key": os.environ["ANTHROPIC_API_KEY"],
                     "anthropic-version": "2023-06-01", "content-type": "application/json"},
            json={"model": self._model, "max_tokens": 1024, "temperature": temperature,
                  "system": system, "messages": chat},
        )
        resp.raise_for_status()
        return "".join(b.get("text", "") for b in resp.json()["content"])


# ---- 파싱과 재시도 ------------------------------------------------------
def parse_json_object(text: str):
    """코드 펜스나 앞뒤 설명이 붙어도 첫 JSON 객체를 꺼낸다. 실패하면 ValueError."""
    cleaned = re.sub(r"```(?:json)?", "", text).strip()
    start = cleaned.find("{")
    if start < 0:
        raise ValueError("JSON 객체가 없음")
    obj, _ = json.JSONDecoder().raw_decode(cleaned[start:])
    if not isinstance(obj, dict):
        raise ValueError("JSON 객체가 아님")
    return obj


def generate(llm, messages: list[dict], temperature: float = 0.0, retries: int = 1) -> dict:
    """{"output": dict|None, "raw_text": str|None, "attempts": int, "error": str|None}"""
    raw, error = None, None
    for attempt in range(1, retries + 2):
        try:
            raw = llm.complete(messages, temperature)
            return {"output": parse_json_object(raw), "raw_text": raw, "attempts": attempt, "error": None}
        except ValueError as e:
            error = f"unparseable: {e}"
        except Exception as e:  # 네트워크 등
            error = f"llm error: {e}"
            break
    return {"output": None, "raw_text": raw, "attempts": attempt, "error": error}
