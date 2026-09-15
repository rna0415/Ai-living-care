"""
eval_synthetic_nl_100_v2.py — 9.2절 진단 ⑤(영어 전문용어가 char n-gram을 오염시킨다)에서
제안만 했던 수정을 실제로 적용해서, 같은 합성 100개로 다시 테스트한다.

수정: 참조 문서에서 라틴 문자 조각(ICOPE, STEADI, WHO, Frailty Phenotype 등)을 정규식으로
제거한 뒤 TF-IDF를 다시 만든다. 그 외(합성 100개 문장, 라우팅 방식, 카테고리)는 전부 그대로 —
"이 수정 하나가 실제로 얼마나 도움이 되는가"만 격리해서 본다.

baseline(원래 참조 문서)과 stripped(영어 제거)을 **같은 100개**로 나란히 돌려 비교한다.

실행: python eval_synthetic_nl_100_v2.py
"""

from __future__ import annotations

import json
import re
import sys

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics import accuracy_score, confusion_matrix, f1_score, precision_score, recall_score
from sklearn.metrics.pairwise import cosine_similarity

from eval_nl_e2e import CATEGORIES, build_reference_docs
from eval_synthetic_nl_100 import SYNTHETIC
from graph_cot_agent import SeedGraph

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

_LATIN_RE = re.compile(r"[A-Za-z]+")


def strip_latin(docs: dict[str, str]) -> dict[str, str]:
    """참조 문서에서 라틴 문자 조각을 통째로 지운다 — 9.2절 진단 ⑤가 찾아낸
    'WellBeing 최고가중치 n-gram이 in/on/co 같은 영어 조각'이라는 문제의 직접 처방."""
    return {k: _LATIN_RE.sub(" ", v) for k, v in docs.items()}


def route(text: str, vectorizer: TfidfVectorizer, ref_matrix, categories: list[str]) -> tuple[str, dict]:
    q_vec = vectorizer.transform([text])
    sims = cosine_similarity(q_vec, ref_matrix)[0]
    return categories[int(sims.argmax())], {c: round(float(s), 4) for c, s in zip(categories, sims)}


def run_variant(name: str, ref_docs: dict[str, str]) -> dict:
    vectorizer = TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 4))
    ref_matrix = vectorizer.fit_transform([ref_docs[c] for c in CATEGORIES])

    rows = []
    for true_cat, sentences in SYNTHETIC.items():
        for text in sentences:
            pred, scores = route(text, vectorizer, ref_matrix, CATEGORIES)
            rows.append({"text": text, "true_category": true_cat, "predicted_category": pred,
                         "correct": pred == true_cat, "scores": scores})

    y_true = [r["true_category"] for r in rows]
    y_pred = [r["predicted_category"] for r in rows]

    acc = accuracy_score(y_true, y_pred)
    macro_f1 = f1_score(y_true, y_pred, labels=CATEGORIES, average="macro", zero_division=0)
    per_class_recall = {c: round(float(r), 4) for c, r in
                         zip(CATEGORIES, recall_score(y_true, y_pred, labels=CATEGORIES, average=None, zero_division=0))}
    per_class_precision = {c: round(float(p), 4) for c, p in
                            zip(CATEGORIES, precision_score(y_true, y_pred, labels=CATEGORIES, average=None, zero_division=0))}
    cm = confusion_matrix(y_true, y_pred, labels=CATEGORIES)
    pred_dist = {c: int(sum(1 for p in y_pred if p == c)) for c in CATEGORIES}

    print(f"\n[{name}] accuracy={acc*100:.1f}% macro-F1={macro_f1*100:.1f}%")
    print(f"  per-class recall:    {per_class_recall}")
    print(f"  per-class precision: {per_class_precision}")
    print(f"  예측 분포: {pred_dist} (실제는 카테고리당 25개 균등)")

    return {
        "name": name, "accuracy": acc, "macro_f1": macro_f1,
        "per_class_recall": per_class_recall, "per_class_precision": per_class_precision,
        "confusion_matrix": cm.tolist(), "labels": CATEGORIES, "pred_dist": pred_dist, "rows": rows,
    }


if __name__ == "__main__":
    graph = SeedGraph()
    baseline_docs = build_reference_docs(graph)
    stripped_docs = strip_latin(baseline_docs)

    print("=" * 100)
    print("[참조 문서 길이 비교 — 라틴 문자 제거 전/후]")
    for c in CATEGORIES:
        print(f"  {c:<16} baseline={len(baseline_docs[c])}자 -> stripped={len(stripped_docs[c])}자 "
              f"(제거량 {len(baseline_docs[c]) - len(stripped_docs[c])}자)")

    result_baseline = run_variant("baseline (영어 그대로)", baseline_docs)
    result_stripped = run_variant("stripped (영어 제거)", stripped_docs)

    print("\n" + "=" * 100)
    print(f"[비교] macro-F1: baseline {result_baseline['macro_f1']*100:.1f}% -> "
          f"stripped {result_stripped['macro_f1']*100:.1f}% "
          f"(Δ{(result_stripped['macro_f1']-result_baseline['macro_f1'])*100:+.1f}%p)")
    print(f"[비교] accuracy: baseline {result_baseline['accuracy']*100:.1f}% -> "
          f"stripped {result_stripped['accuracy']*100:.1f}% "
          f"(Δ{(result_stripped['accuracy']-result_baseline['accuracy'])*100:+.1f}%p)")
    for c in CATEGORIES:
        d_r = result_stripped["per_class_recall"][c] - result_baseline["per_class_recall"][c]
        print(f"  {c:<16} recall Δ{d_r*100:+.1f}%p "
              f"({result_baseline['per_class_recall'][c]*100:.0f}% -> {result_stripped['per_class_recall'][c]*100:.0f}%)")

    out = {
        "note": "9.2절 진단⑤(영어 전문용어 오염) 수정을 실제로 적용한 검증 — 합성 100개는 eval_synthetic_nl_100.py와 완전히 동일.",
        "baseline": result_baseline, "stripped": result_stripped,
        "reference_doc_lengths": {c: {"baseline": len(baseline_docs[c]), "stripped": len(stripped_docs[c])} for c in CATEGORIES},
    }
    with open("eval_synthetic_nl_100_v2_results.json", "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print("\n[export] eval_synthetic_nl_100_v2_results.json 저장 완료")
