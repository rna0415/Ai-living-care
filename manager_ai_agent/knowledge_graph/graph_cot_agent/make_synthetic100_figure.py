"""make_synthetic100_figure.py -> fig_synthetic100_confusion.png, fig_16_vs_100_comparison.png"""

import json

import matplotlib.pyplot as plt
import numpy as np

plt.rcParams["font.family"] = "Malgun Gothic"
plt.rcParams["axes.unicode_minus"] = False

BLUE, ORANGE, AQUA, RED = "#2a78d6", "#eb6834", "#1baf7a", "#e34948"
TEXT, MUTED, GRID = "#0b0b0b", "#52514e", "#e3e2dd"

with open("eval_synthetic_nl_100_results.json", encoding="utf-8") as f:
    data = json.load(f)

labels = data["labels"]
cm = np.array(data["confusion_matrix"])
cm_norm = cm / cm.sum(axis=1, keepdims=True)

# ---- 1. confusion matrix ----
fig, ax = plt.subplots(figsize=(6, 5.3))
im = ax.imshow(cm_norm, cmap="Reds", vmin=0, vmax=1)
ax.set_xticks(range(len(labels)))
ax.set_yticks(range(len(labels)))
ax.set_xticklabels(labels, rotation=20, ha="right")
ax.set_yticklabels(labels)
ax.set_xlabel("예측 라벨", color=MUTED)
ax.set_ylabel("실제 라벨", color=MUTED)
ax.set_title(f"Confusion Matrix — 합성 100개 (macro-F1={data['macro_f1']*100:.1f}%)",
             color=TEXT, fontsize=11, loc="left")
for i in range(len(labels)):
    for j in range(len(labels)):
        color = "white" if cm_norm[i, j] > 0.5 else TEXT
        ax.text(j, i, f"{cm[i, j]}", ha="center", va="center", color=color, fontsize=13, fontweight="bold")
fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
fig.tight_layout()
fig.savefig("fig_synthetic100_confusion.png", dpi=150, bbox_inches="tight")
plt.close(fig)

# ---- 2. 16개(그래프 원문) vs 100개(합성) 비교 ----
with open("eval_nl_e2e_results.json", encoding="utf-8") as f:
    real16 = json.load(f)

fig, ax = plt.subplots(figsize=(6.5, 4.5))
names = ["그래프 원문 16개\n(9절)", "합성 100개\n(9.1절)"]
values = [real16["summary"]["routing_macro_f1"] * 100, data["macro_f1"] * 100]
bars = ax.bar(names, values, color=[AQUA, RED], width=0.5)
for b in bars:
    h = b.get_height()
    ax.annotate(f"{h:.1f}%", (b.get_x() + b.get_width() / 2, h), xytext=(0, 5),
                textcoords="offset points", ha="center", va="bottom", fontsize=13, color=TEXT, fontweight="bold")
ax.set_ylim(0, 112)
ax.set_ylabel("라우팅 macro-F1 (%)", color=MUTED)
ax.set_title("같은 라우터, 다른 입력 — 그래프 원문 vs 자연스러운 구어체",
              color=TEXT, fontsize=12, loc="left")
for s in ("top", "right"):
    ax.spines[s].set_visible(False)
ax.spines["left"].set_color(GRID)
ax.spines["bottom"].set_color(GRID)
ax.yaxis.grid(True, color=GRID, linewidth=0.8)
ax.set_axisbelow(True)
fig.tight_layout()
fig.savefig("fig_16_vs_100_comparison.png", dpi=150, bbox_inches="tight")
plt.close(fig)

print("저장 완료: fig_synthetic100_confusion.png, fig_16_vs_100_comparison.png")
