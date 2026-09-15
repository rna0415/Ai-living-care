"""
eval_nl_diagnostics.py — 라우터가 왜 무너지는지(macro-F1 94.4%→47.2%) 5가지 각도로 정밀
진단한다. eval_synthetic_nl_100_results.json(각 문항의 4-way 코사인 점수 전부 저장돼 있음)을
재사용하고, 참조 문서 벡터라이저를 다시 불러 "왜 KnowledgeLookup으로 쏠리는가"의 어휘
수준 근거까지 뽑는다.

5개 진단:
  ① 클래스별 precision/recall/F1 — 어디서 새는지 숫자로
  ② 예측 분포 vs 실제 분포 — "쏠림"을 직접 눈으로
  ③ 평균 유사도 행렬 — count가 아니라 실제 코사인 점수 크기로 본 confusion
  ④ confidence margin — 정답/오답이 "애매하게" 틀렸는지 "확신에 차서" 틀렸는지
  ⑤ 참조 문서 top n-gram — KnowledgeLookup 문서가 왜 어디에나 걸리는지 어휘 증거

실행: python eval_nl_diagnostics.py
"""

from __future__ import annotations

import json
import sys

import matplotlib.pyplot as plt
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer

from eval_nl_e2e import CATEGORIES, build_reference_docs
from graph_cot_agent import SeedGraph

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

plt.rcParams["font.family"] = "Malgun Gothic"
plt.rcParams["axes.unicode_minus"] = False

BLUE, ORANGE, AQUA, RED, VIOLET = "#2a78d6", "#eb6834", "#1baf7a", "#e34948", "#4a3aa7"
TEXT, MUTED, GRID = "#0b0b0b", "#52514e", "#e3e2dd"
CAT_COLORS = {"WellBeing": BLUE, "Safety": ORANGE, "Comfort": AQUA, "KnowledgeLookup": RED}


def _style(ax):
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    ax.spines["left"].set_color(GRID)
    ax.spines["bottom"].set_color(GRID)
    ax.yaxis.grid(True, color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)


with open("eval_synthetic_nl_100_results.json", encoding="utf-8") as f:
    data = json.load(f)
rows = data["rows"]

print("=" * 100)
print("[진단 ①] 클래스별 precision / recall / F1")
print("-" * 100)
per_class = {}
for cat in CATEGORIES:
    tp = sum(1 for r in rows if r["true_category"] == cat and r["predicted_category"] == cat)
    fp = sum(1 for r in rows if r["true_category"] != cat and r["predicted_category"] == cat)
    fn = sum(1 for r in rows if r["true_category"] == cat and r["predicted_category"] != cat)
    prec = tp / (tp + fp) if (tp + fp) else 0.0
    rec = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = 2 * prec * rec / (prec + rec) if (prec + rec) else 0.0
    per_class[cat] = {"precision": prec, "recall": rec, "f1": f1, "tp": tp, "fp": fp, "fn": fn}
    print(f"  {cat:<16} precision={prec*100:5.1f}%  recall={rec*100:5.1f}%  f1={f1*100:5.1f}%  "
          f"(tp={tp}, fp={fp}, fn={fn})")

fig, ax = plt.subplots(figsize=(8.5, 5))
x = np.arange(len(CATEGORIES))
w = 0.26
for i, metric in enumerate(["precision", "recall", "f1"]):
    vals = [per_class[c][metric] * 100 for c in CATEGORIES]
    bars = ax.bar(x + (i - 1) * w, vals, width=w, label=metric,
                   color=[BLUE, ORANGE, AQUA][i])
    for b in bars:
        h = b.get_height()
        ax.annotate(f"{h:.0f}", (b.get_x() + b.get_width() / 2, h), xytext=(0, 3),
                    textcoords="offset points", ha="center", va="bottom", fontsize=8.5, color=TEXT)
ax.set_xticks(x)
ax.set_xticklabels(CATEGORIES)
ax.set_ylim(0, 112)
ax.set_ylabel("%", color=MUTED)
ax.set_title("① 클래스별 precision/recall/F1 (합성 100개)", color=TEXT, fontsize=12, loc="left")
_style(ax)
ax.legend(loc="upper right", frameon=False, fontsize=9)
fig.tight_layout()
fig.savefig("fig_diag1_per_class_prf.png", dpi=150, bbox_inches="tight")
plt.close(fig)


print("\n" + "=" * 100)
print("[진단 ②] 예측 분포 vs 실제 분포 — '쏠림'")
print("-" * 100)
true_dist = {c: sum(1 for r in rows if r["true_category"] == c) for c in CATEGORIES}
pred_dist = {c: sum(1 for r in rows if r["predicted_category"] == c) for c in CATEGORIES}
for c in CATEGORIES:
    print(f"  {c:<16} 실제={true_dist[c]:>3}개   예측={pred_dist[c]:>3}개"
          f"   (쏠림 배율 {pred_dist[c]/true_dist[c]:.2f}x)")

fig, ax = plt.subplots(figsize=(8, 5))
w = 0.35
ax.bar(x - w / 2, [true_dist[c] for c in CATEGORIES], width=w, color=MUTED, label="실제 분포(균등, 25개씩)")
bars = ax.bar(x + w / 2, [pred_dist[c] for c in CATEGORIES], width=w,
              color=[CAT_COLORS[c] for c in CATEGORIES], label="예측 분포")
for b, c in zip(bars, CATEGORIES):
    ax.annotate(f"{pred_dist[c]}", (b.get_x() + b.get_width() / 2, b.get_height()), xytext=(0, 3),
                textcoords="offset points", ha="center", va="bottom", fontsize=10, color=TEXT, fontweight="bold")
ax.set_xticks(x)
ax.set_xticklabels(CATEGORIES)
ax.set_ylabel("개수", color=MUTED)
ax.set_title("② 예측이 KnowledgeLookup으로 쏠린다 — 실제 vs 예측 분포", color=TEXT, fontsize=12, loc="left")
_style(ax)
ax.legend(loc="upper left", frameon=False, fontsize=9)
fig.tight_layout()
fig.savefig("fig_diag2_prediction_bias.png", dpi=150, bbox_inches="tight")
plt.close(fig)


print("\n" + "=" * 100)
print("[진단 ③] 평균 코사인 유사도 행렬 (count 아니라 점수 크기)")
print("-" * 100)
avg_sim = np.zeros((len(CATEGORIES), len(CATEGORIES)))
for i, true_cat in enumerate(CATEGORIES):
    subset = [r for r in rows if r["true_category"] == true_cat]
    for j, pred_cat in enumerate(CATEGORIES):
        avg_sim[i, j] = np.mean([r["scores"][pred_cat] for r in subset])
print("rows=실제 axis, cols=참조문서별 평균 코사인 점수")
print(f"{'':16}" + "".join(f"{c:>16}" for c in CATEGORIES))
for i, true_cat in enumerate(CATEGORIES):
    print(f"{true_cat:<16}" + "".join(f"{avg_sim[i,j]:>16.4f}" for j in range(len(CATEGORIES))))

fig, ax = plt.subplots(figsize=(6.5, 5.3))
im = ax.imshow(avg_sim, cmap="RdPu", vmin=0)
ax.set_xticks(range(len(CATEGORIES)))
ax.set_yticks(range(len(CATEGORIES)))
ax.set_xticklabels(CATEGORIES, rotation=20, ha="right")
ax.set_yticklabels(CATEGORIES)
ax.set_xlabel("참조 문서(예측 후보)", color=MUTED)
ax.set_ylabel("실제 axis", color=MUTED)
ax.set_title("③ 평균 코사인 유사도 — KnowledgeLookup 열이 전체적으로 진하다",
             color=TEXT, fontsize=11, loc="left")
for i in range(len(CATEGORIES)):
    for j in range(len(CATEGORIES)):
        color = "white" if avg_sim[i, j] > avg_sim.max() * 0.6 else TEXT
        ax.text(j, i, f"{avg_sim[i, j]:.3f}", ha="center", va="center", color=color, fontsize=11, fontweight="bold")
fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
fig.tight_layout()
fig.savefig("fig_diag3_avg_similarity.png", dpi=150, bbox_inches="tight")
plt.close(fig)


print("\n" + "=" * 100)
print("[진단 ④] confidence margin — 1등과 2등 점수 차이")
print("-" * 100)
margins_correct, margins_wrong = [], []
for r in rows:
    sorted_scores = sorted(r["scores"].values(), reverse=True)
    margin = sorted_scores[0] - sorted_scores[1]
    (margins_correct if r["correct"] else margins_wrong).append(margin)

print(f"  정답인 경우  margin 평균={np.mean(margins_correct):.4f}  (n={len(margins_correct)})")
print(f"  오답인 경우  margin 평균={np.mean(margins_wrong):.4f}  (n={len(margins_wrong)})")
print("  -> margin이 작을수록 '애매하게' 틀렸다는 뜻(둘 중 뭐가 나와도 이상하지 않은 수준)")

fig, ax = plt.subplots(figsize=(7, 4.5))
bp = ax.boxplot([margins_correct, margins_wrong], tick_labels=["정답", "오답"],
                 patch_artist=True, widths=0.5)
for patch, color in zip(bp["boxes"], [AQUA, RED]):
    patch.set_facecolor(color)
    patch.set_alpha(0.5)
ax.set_ylabel("1등-2등 코사인 점수 차이(margin)", color=MUTED)
ax.set_title("④ 정답/오답의 확신도(margin) 분포", color=TEXT, fontsize=12, loc="left")
_style(ax)
fig.tight_layout()
fig.savefig("fig_diag4_confidence_margin.png", dpi=150, bbox_inches="tight")
plt.close(fig)


print("\n" + "=" * 100)
print("[진단 ⑤] 참조 문서 top n-gram — KnowledgeLookup이 왜 '만능'인가")
print("-" * 100)
graph = SeedGraph()
ref_docs = build_reference_docs(graph)
vectorizer = TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 4))
ref_matrix = vectorizer.fit_transform([ref_docs[c] for c in CATEGORIES])
feature_names = np.array(vectorizer.get_feature_names_out())

top_ngrams = {}
for i, cat in enumerate(CATEGORIES):
    row = ref_matrix[i].toarray().flatten()
    top_idx = row.argsort()[::-1][:10]
    top_ngrams[cat] = [(feature_names[j], round(float(row[j]), 4)) for j in top_idx if row[j] > 0]
    print(f"  {cat}: {[t[0] for t in top_ngrams[cat]]}")

fig, axes = plt.subplots(1, 4, figsize=(15, 4.5))
for ax, cat in zip(axes, CATEGORIES):
    terms = [t[0].strip() or "(공백)" for t in top_ngrams[cat][:8]][::-1]
    vals = [t[1] for t in top_ngrams[cat][:8]][::-1]
    ax.barh(terms, vals, color=CAT_COLORS[cat])
    ax.set_title(cat, fontsize=11, color=TEXT)
    ax.tick_params(labelsize=9)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
fig.suptitle("⑤ 참조 문서에서 TF-IDF 가중치가 가장 높은 char n-gram (상위 8개)", fontsize=12, color=TEXT)
fig.tight_layout()
fig.savefig("fig_diag5_top_ngrams.png", dpi=150, bbox_inches="tight")
plt.close(fig)

out = {
    "per_class_prf": per_class,
    "true_distribution": true_dist, "predicted_distribution": pred_dist,
    "avg_similarity_matrix": avg_sim.tolist(), "categories": CATEGORIES,
    "margin_correct_mean": float(np.mean(margins_correct)), "margin_wrong_mean": float(np.mean(margins_wrong)),
    "margin_correct_all": margins_correct, "margin_wrong_all": margins_wrong,
    "top_ngrams_per_category": top_ngrams,
}
with open("eval_nl_diagnostics_results.json", "w", encoding="utf-8") as f:
    json.dump(out, f, ensure_ascii=False, indent=2)

print("\n[export] fig_diag1~5*.png + eval_nl_diagnostics_results.json 저장 완료")
