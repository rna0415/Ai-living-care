"""
build_graph_axis_vectors.py  —  Method 2(그래프 기반)용 axis 벡터를 미리 계산해 캐싱

axis_centroids.json(Method 1)과 같은 포맷으로 graph_axis_vectors.json을 만든다.
차이는 오직 하나 — 축을 대표하는 텍스트의 출처:
    Method 1: 손으로 쓴 축 설명 문장(axis_routing.py의 ONTO_AXES[*]["embed_text"])
              + 예시 문장 수십 개(axis_centroids.json 자체에는 원본 예시 문장이 없고
              사전에 오프라인으로 만들어진 중심값만 있음)
    Method 2: graph_axis_doc.py가 Neo4j에서 실제로 뽑아온 axis별 device/function/
              rule rationale 텍스트

두 방식 모두 같은 임베딩 모델(jhgan/ko-sroberta-multitask)을 쓴다 — 비교 대상은
"축 표현이 어디서 왔는가"이지 임베딩 모델 자체가 아니다.

실행에는 살아있는 Neo4j 연결이 필요하다(그래프에서 읽어와야 하므로). 한 번 실행해
캐시 파일을 만들어두면, 평가 스크립트(evaluate_axis_retrieval.py)는 이 캐시만 읽고
Neo4j 없이도 돌아간다 — Neo4j가 "실험·미승인"이라 상시로 떠 있으리라는 보장이 없기
때문(kg_mapping/CLAUDE.md).
"""

import json
import os
import sys

import numpy as np
from sentence_transformers import SentenceTransformer

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from graph_retrieval import GraphRetriever
from graph_axis_doc import build_axis_document

MODEL_NAME = "jhgan/ko-sroberta-multitask"
_OUT_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "graph_axis_vectors.json")

AXIS_IDS = ["onto:saref/WellBeing", "onto:saref/Safety", "onto:saref/Comfort"]


def main():
    model = SentenceTransformer(MODEL_NAME)

    with GraphRetriever() as g:
        documents = {axis_id: build_axis_document(g, axis_id) for axis_id in AXIS_IDS}

    centroids = {}
    for axis_id, doc in documents.items():
        vec = model.encode(doc)
        vec = vec / np.linalg.norm(vec)
        centroids[axis_id] = vec.tolist()

    out = {
        "model": MODEL_NAME,
        "centroids": centroids,
        "source_documents": documents,
    }
    with open(_OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)

    print(f"wrote {_OUT_PATH}")
    for axis_id, doc in documents.items():
        print(f"  {axis_id}: {len(doc)} chars of graph-derived text")


if __name__ == "__main__":
    main()
