"""
evaluate_axis_retrieval.py  —  Method 1(문장 임베딩 vs 손으로 쓴 축 설명) vs
                                Method 2(문장 임베딩 vs 그래프에서 뽑은 축 문서) 비교

두 방법 모두:
    1. 같은 문장 인코더(jhgan/ko-sroberta-multitask)로 검증 문장을 인코딩
    2. 축마다 미리 계산된 중심 벡터와 코사인 유사도 계산
    3. 가장 유사도가 높은 축을 예측 axis로 채택 (top-1)

차이는 축 중심 벡터의 출처뿐:
    Method 1 = axis_centroids.json  (axis_routing.py가 쓰는 것, 손으로 쓴 설명+예시 문장 기반)
    Method 2 = graph_axis_vectors.json (build_graph_axis_vectors.py가 Neo4j에서 뽑아 만든 것)

validation_sentences.json의 gold_axis가 null인 문장(OOS)은 top-1 정확도 계산에서
제외하고, 대신 "OOS 문장에 대해 최고 유사도가 얼마나 낮게 나오는가"를 별도로 기록해
두 방법의 OOS 분리력을 눈으로 비교할 수 있게 한다.

Neo4j 연결이 필요 없다 — 두 centroid 파일 모두 미리 캐시돼 있다.
"""

import json
import os

import numpy as np
from sentence_transformers import SentenceTransformer

_DIR = os.path.dirname(os.path.abspath(__file__))
_PARENT = os.path.dirname(_DIR)

TEXT_CENTROIDS_PATH = os.path.join(_PARENT, "axis_centroids.json")
GRAPH_CENTROIDS_PATH = os.path.join(_DIR, "graph_axis_vectors.json")
VALIDATION_PATH = os.path.join(_DIR, "validation_sentences.json")
RESULTS_PATH = os.path.join(_DIR, "results.json")

AXIS_LABELS = {
    "onto:saref/WellBeing": "WellBeing",
    "onto:saref/Safety": "Safety",
    "onto:saref/Comfort": "Comfort",
}
AXIS_IDS = list(AXIS_LABELS.keys())


def load_centroids(path):
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    return data["model"], {axis_id: np.array(vec) for axis_id, vec in data["centroids"].items()}


def score_all(vec, centroids):
    return {axis_id: float(np.dot(vec, c) / (np.linalg.norm(vec) * np.linalg.norm(c)))
            for axis_id, c in centroids.items()}


def evaluate(method_name, centroids, model, sentences):
    rows = []
    correct = 0
    on_topic_n = 0
    oos_max_scores = []
    confusion = {g: {p: 0 for p in AXIS_IDS} for g in AXIS_IDS}

    for item in sentences:
        vec = model.encode(item["text"])
        scores = score_all(vec, centroids)
        pred_axis = max(scores, key=scores.get)
        pred_score = scores[pred_axis]

        row = {
            "id": item["id"],
            "text": item["text"],
            "gold_axis": item["gold_axis"],
            "pred_axis": pred_axis,
            "pred_score": pred_score,
            "scores": scores,
        }
        rows.append(row)

        if item["gold_axis"] is None:
            oos_max_scores.append(pred_score)
        else:
            on_topic_n += 1
            confusion[item["gold_axis"]][pred_axis] += 1
            if pred_axis == item["gold_axis"]:
                correct += 1

    accuracy = correct / on_topic_n if on_topic_n else float("nan")

    per_axis = {}
    for axis_id in AXIS_IDS:
        tp = confusion[axis_id][axis_id]
        support = sum(confusion[axis_id].values())
        predicted_as = sum(confusion[g][axis_id] for g in AXIS_IDS)
        precision = tp / predicted_as if predicted_as else float("nan")
        recall = tp / support if support else float("nan")
        per_axis[axis_id] = {"precision": precision, "recall": recall, "support": support}

    return {
        "method": method_name,
        "accuracy": accuracy,
        "on_topic_n": on_topic_n,
        "correct": correct,
        "confusion": confusion,
        "per_axis": per_axis,
        "oos_max_scores": oos_max_scores,
        "rows": rows,
    }


def main():
    with open(VALIDATION_PATH, encoding="utf-8") as f:
        sentences = json.load(f)

    model_name_1, text_centroids = load_centroids(TEXT_CENTROIDS_PATH)
    model_name_2, graph_centroids = load_centroids(GRAPH_CENTROIDS_PATH)
    assert model_name_1 == model_name_2, "두 방법이 다른 임베딩 모델을 쓰면 비교가 불공정해진다"

    model = SentenceTransformer(model_name_1)

    result_1 = evaluate("method1_text_centroid", text_centroids, model, sentences)
    result_2 = evaluate("method2_graph_grounded", graph_centroids, model, sentences)

    print(f"=== {result_1['method']} ===")
    print(f"accuracy: {result_1['accuracy']:.3f} ({result_1['correct']}/{result_1['on_topic_n']})")
    print(f"per-axis: {json.dumps(result_1['per_axis'], indent=2)}")
    print(f"OOS max scores: {result_1['oos_max_scores']}")

    print(f"\n=== {result_2['method']} ===")
    print(f"accuracy: {result_2['accuracy']:.3f} ({result_2['correct']}/{result_2['on_topic_n']})")
    print(f"per-axis: {json.dumps(result_2['per_axis'], indent=2)}")
    print(f"OOS max scores: {result_2['oos_max_scores']}")

    mismatches = [
        (r1["id"], r1["text"], r1["gold_axis"], r1["pred_axis"], r2["pred_axis"])
        for r1, r2 in zip(result_1["rows"], result_2["rows"])
        if r1["gold_axis"] is not None and (r1["pred_axis"] != r2["pred_axis"])
    ]
    print(f"\n두 방법의 예측이 갈린 문장 ({len(mismatches)}개):")
    for id_, text, gold, p1, p2 in mismatches:
        print(f"  [{id_}] {text}\n    gold={gold}  method1={p1}  method2={p2}")

    with open(RESULTS_PATH, "w", encoding="utf-8") as f:
        json.dump({"method1": result_1, "method2": result_2}, f, ensure_ascii=False, indent=2)
    print(f"\nwrote {RESULTS_PATH}")


if __name__ == "__main__":
    main()
