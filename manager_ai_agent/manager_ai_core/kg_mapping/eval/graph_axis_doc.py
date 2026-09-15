"""
graph_axis_doc.py  —  axis별 Neo4j 그래프 내용을 문장 임베딩용 텍스트로 직렬화

axis_routing.py의 ONTO_AXES[*]["embed_text"]는 사람이 손으로 쓴 짧은 축 설명이다
(예: WellBeing = "사람의 상태, 웰빙, 안부 확인, 괜찮은지 확인, 활동 여부"). 이 파일은
같은 축을 GraphRetriever.fetch_axis_context()가 실제로 반환하는 그래프 내용
(device_class, function 이름, AxisKnowledge의 rationale/threshold/severity)으로부터
자동으로 텍스트를 만든다 — 두 방식의 유일한 차이는 "축을 대표하는 텍스트가 어디서
왔는가"이고, 임베딩 모델(jhgan/ko-sroberta-multitask)과 비교 방식(코사인 유사도)은
동일하게 유지해 공정 비교가 되게 한다.

읽기 전용 — 그래프에 아무것도 쓰지 않는다.
"""

import os
import sys

# kg_mapping/eval/ 밑이라 부모 폴더(graph_retrieval.py가 있는 곳)를 sys.path에 얹는다
# (pipeline.py가 kg_mapping/·policy_generation/에 쓰는 것과 같은 패턴)
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from graph_retrieval import GraphRetriever


def build_axis_document(retriever: GraphRetriever, axis_id: str) -> str:
    """axis_id 하나의 context를 사람이 읽는 한국어 텍스트 한 덩어리로 직렬화."""
    ctx = retriever.fetch_axis_context(axis_id)
    lines = [f"축 이름: {ctx['label']}"]

    device_classes = sorted({d["device_class"] for d in ctx["devices"] if d.get("device_class")})
    if device_classes:
        lines.append("관련 기기: " + ", ".join(device_classes))

    function_names = sorted({
        f["name"]
        for d in ctx["devices"]
        for f in d.get("functions", [])
        if f.get("name")
    })
    if function_names:
        lines.append("관련 기능: " + ", ".join(function_names))

    for rule in ctx["rules"]:
        parts = []
        if rule.get("slot"):
            parts.append(f"슬롯={rule['slot']}")
        if rule.get("severity"):
            parts.append(f"심각도={rule['severity']}")
        if rule.get("rationale"):
            parts.append(rule["rationale"])
        if parts:
            lines.append("판단 규칙: " + " / ".join(parts))

    for d in ctx["devices"]:
        for dk in d.get("device_knowledge", []):
            statement = dk.get("statement")
            if statement:
                lines.append("기기 지식: " + statement)

    return "\n".join(lines)


def build_all_axis_documents(retriever: GraphRetriever, axis_ids: list[str]) -> dict[str, str]:
    return {axis_id: build_axis_document(retriever, axis_id) for axis_id in axis_ids}


if __name__ == "__main__":
    import sys
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

    with GraphRetriever() as g:
        axes = [a["id"] for a in g.list_axes() if a["id"].startswith("onto:saref/")]
        docs = build_all_axis_documents(g, axes)
        for axis_id, doc in docs.items():
            print(f"=== {axis_id} ===")
            print(doc)
            print()
