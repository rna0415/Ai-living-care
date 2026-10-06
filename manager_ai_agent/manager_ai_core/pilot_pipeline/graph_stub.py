"""메모리 그래프 스텁 — docs/pilot-spec/graph_interface.md 를 따르는 최소 구현.

A 의 로더가 나오기 전까지 B 가 파이프라인을 개발하려고 쓴다. 같은 인터페이스이므로
A 의 로더로 바꿔 끼워도 파이프라인 코드는 그대로다. Neo4j 는 쓰지 않는다.
"""

from __future__ import annotations

import json
from collections import deque
from pathlib import Path

SLOT_BY_CLASS = {
    "MotionAction": "motion-action",
    "PerceptionAction": "perception-action",
    "ControlAction": "control-action",
}
_GROUPS = (("properties", "property"), ("actions", "action"), ("events", "event"))


def _strip(type_value, where: str) -> str:
    if not isinstance(type_value, str) or not type_value.startswith("id:"):
        raise ValueError(f"{where}: @type 은 'id:' 로 시작해야 한다 ({type_value!r})")
    return type_value[3:]


class StubGraph:
    def __init__(self, tds: list[dict], places: dict, vocab: dict):
        self._info = {i["id"]: i for i in vocab["identities"]}
        self._places = {p["id"]: p for p in places.get("places", [])}
        self._devices: dict[str, dict] = {}
        for td in tds:
            title = td.get("title")
            if not title:
                raise ValueError("TD 에 title 이 없다")
            if title in self._devices:
                raise ValueError(f"기기 ID 중복: {title}")
            self._check_td(td)
            self._devices[title] = td
        self._nodes = self._build_nodes()
        self._adj = self._build_adjacency()

    # ---- 적재 -------------------------------------------------------
    @classmethod
    def load(cls, td_paths: list[str], places_path: str, vocab_path: str) -> "StubGraph":
        read = lambda p: json.loads(Path(p).read_text(encoding="utf-8"))
        return cls([read(p) for p in td_paths], read(places_path), read(vocab_path))

    def _check_td(self, td: dict) -> None:
        title = td["title"]
        for t in [td.get("@type")] + [
            item.get("@type") for g, _ in _GROUPS for item in td.get(g, {}).values()
        ]:
            ident = _strip(t, title)
            if ident not in self._info:
                raise ValueError(f"{title}: @type '{ident}' 이 vocab 에 없다")
        loc = td.get("location")
        if loc is not None and loc not in self._places:
            raise ValueError(f"{title}: location '{loc}' 이 places 에 없다")

    # ---- 존재 확인 --------------------------------------------------
    def has_identity(self, identity_id: str) -> bool:
        return identity_id in self._info

    def has_place(self, place_id: str) -> bool:
        return place_id in self._places

    def has_device(self, device_id: str) -> bool:
        return device_id in self._devices

    def resolve_place(self, name: str) -> str | None:
        key = _norm(name)
        for pid, p in self._places.items():
            if key == _norm(pid) or key in {_norm(a) for a in p.get("aliases", [])}:
                return pid
        return None

    # ---- Identity 계층 ----------------------------------------------
    def ancestors(self, identity_id: str) -> list[str]:
        out, cur = [], self._info.get(identity_id, {}).get("parent")
        while cur is not None:
            out.append(cur)
            cur = self._info.get(cur, {}).get("parent")
        return out

    def slot_of(self, action_identity_id: str) -> str | None:
        for cls in [action_identity_id] + self.ancestors(action_identity_id):
            if cls in SLOT_BY_CLASS:
                return SLOT_BY_CLASS[cls]
        return None

    # ---- 기기가 제공하는 것 -----------------------------------------
    def _actions_of(self, device_id: str):
        for key, item in self._devices[device_id].get("actions", {}).items():
            yield key, item, _strip(item["@type"], device_id)

    def devices_with(self, action_identity_id: str) -> list[str]:
        return [
            d for d in self._devices
            if any(ident == action_identity_id for _, _, ident in self._actions_of(d))
        ]

    def input_schema(self, device_id: str, action_identity_id: str) -> dict | None:
        if device_id not in self._devices:
            return None
        for _, item, ident in self._actions_of(device_id):
            if ident == action_identity_id:
                return item.get("input")
        return None

    def device_location(self, device_id: str) -> str | None:
        return self._devices.get(device_id, {}).get("location")

    # ---- 검색용 노드 ------------------------------------------------
    def _build_nodes(self) -> list[dict]:
        nodes: list[dict] = []
        for title, td in self._devices.items():
            names = [title] + list(td.get("aliases", []))
            nodes.append({
                "node_id": title, "kind": "device", "identity": _strip(td["@type"], title),
                "device": title, "names": names,
                "text": " ".join(names + [td.get("description", "")]),
            })
            for group, kind in _GROUPS:
                for key, item in td.get(group, {}).items():
                    ident = _strip(item["@type"], title)
                    names = [key] + list(item.get("aliases", [])) + [ident]
                    desc = " ".join(
                        [item.get("description", ""), self._info.get(ident, {}).get("description", "")]
                    )
                    nodes.append({
                        "node_id": f"{title}/{key}", "kind": kind, "identity": ident,
                        "device": title, "names": names, "text": " ".join(names) + " " + desc,
                    })
        for pid, p in self._places.items():
            names = [pid] + list(p.get("aliases", []))
            nodes.append({"node_id": pid, "kind": "place", "identity": None, "device": None,
                          "names": names, "text": " ".join(names)})
        for ident, info in self._info.items():
            if "ObjectClass" in self.ancestors(ident):
                names = [ident] + list(info.get("aliases", []))
                nodes.append({"node_id": ident, "kind": "object-class", "identity": ident,
                              "device": None, "names": names,
                              "text": " ".join(names + [info.get("description", "")])})
        return nodes

    def searchable_nodes(self) -> list[dict]:
        return list(self._nodes)

    def _build_adjacency(self) -> dict[str, set[str]]:
        adj: dict[str, set[str]] = {n["node_id"]: set() for n in self._nodes}

        def link(a, b):
            if a in adj and b in adj:
                adj[a].add(b)
                adj[b].add(a)

        for n in self._nodes:
            if n["kind"] in ("action", "property", "event"):
                link(n["node_id"], n["device"])
        for title, td in self._devices.items():
            if td.get("location"):
                link(title, td["location"])
        return adj

    def neighbors(self, node_id: str, hops: int = 1) -> list[str]:
        seen, queue = {node_id}, deque([(node_id, 0)])
        while queue:
            cur, d = queue.popleft()
            if d == hops:
                continue
            for nxt in self._adj.get(cur, ()):
                if nxt not in seen:
                    seen.add(nxt)
                    queue.append((nxt, d + 1))
        seen.discard(node_id)
        return sorted(seen)


def _norm(s: str) -> str:
    return "".join(str(s).lower().split())
