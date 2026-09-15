"""make_f1_figure.py -> fig_confusion_matrix.png, fig_per_class_f1.png"""

import json

import matplotlib.pyplot as plt
import numpy as np

plt.rcParams["font.family"] = "Malgun Gothic"
plt.rcParams["axes.unicode_minus"] = False

BLUE, ORANGE, AQUA, RED = "#2a78d6", "#eb6834", "#1baf7a", "#e34948"
TEXT, MUTED, GRID = "#0b0b0b", "#52514e", "#e3e2dd"

with open("eval_macro_f1_results.json", encoding="utf-8") as f:
    data = json.load(f)

# ---- 1. confusion matrix (전체 규칙) ----
rep = data["report_all_rules"]
labels = rep["labels"]
cm = np.array(rep["confusion_matrix"])
cm_norm = cm / cm.sum(axis=1, keepdims=True)

fig, ax = plt.subplots(figsize=(5.5, 5))
im = ax.imshow(cm_norm, cmap="Blues", vmin=0, vmax=1)
ax.set_xticks(range(len(labels)))
ax.set_yticks(range(len(labels)))
ax.set_xticklabels(labels)
ax.set_yticklabels(labels)
ax.set_xlabel("예측 라벨", color=MUTED)
ax.set_ylabel("실제 라벨", color=MUTED)
ax.set_title(f"Confusion Matrix — 전체 23개 규칙 (macro-F1={rep['macro_f1']*100:.1f}%)",
             color=TEXT, fontsize=11, loc="left")
for i in range(len(labels)):
    for j in range(len(labels)):
        color = "white" if cm_norm[i, j] > 0.5 else TEXT
        ax.text(j, i, f"{cm[i, j]}", ha="center", va="center", color=color, fontsize=12, fontweight="bold")
fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04, label="행 기준 비율")
fig.tight_layout()
fig.savefig("fig_confusion_matrix.png", dpi=150, bbox_inches="tight")
plt.close(fig)

# ---- 2. 지원 규칙만 vs 전체 — per-class F1 비교 ----
rep_sup = data["report_supported_only"]

def per_class_f1(report_data, labels):
    # classification_report 텍스트가 아니라 confusion matrix에서 직접 재계산(정확)
    cm = np.array(report_data["confusion_matrix"])
    f1s = []
    for i in range(len(labels)):
        tp = cm[i, i]
        fp = cm[:, i].sum() - tp
        fn = cm[i, :].sum() - tp
        prec = tp / (tp + fp) if (tp + fp) > 0 else 0
        rec = tp / (tp + fn) if (tp + fn) > 0 else 0
        f1 = 2 * prec * rec / (prec + rec) if (prec + rec) > 0 else 0
        f1s.append(f1)
    return f1s

f1_all = per_class_f1(rep, labels)
f1_sup = per_class_f1(rep_sup, rep_sup["labels"])

x = np.arange(len(labels))
w = 0.32
fig, ax = plt.subplots(figsize=(7.5, 4.5))
b1 = ax.bar(x - w / 2, [v * 100 for v in f1_sup], width=w, color=AQUA, label="지원 규칙만 (14개)")
b2 = ax.bar(x + w / 2, [v * 100 for v in f1_all], width=w, color=BLUE, label="전체 규칙 (23개, 미지원 9개 포함)")
for bars in (b1, b2):
    for b in bars:
        h = b.get_height()
        ax.annotate(f"{h:.0f}%", (b.get_x() + b.get_width() / 2, h), xytext=(0, 3),
                    textcoords="offset points", ha="center", va="bottom", fontsize=9, color=TEXT)
ax.set_xticks(x)
ax.set_xticklabels(labels)
ax.set_ylim(0, 112)
ax.set_ylabel("F1 (%)", color=MUTED)
ax.set_title("클래스별 F1 — 지원 규칙만 vs 전체(미지원 threshold 타입 포함)",
             color=TEXT, fontsize=12, loc="left")
for s in ("top", "right"):
    ax.spines[s].set_visible(False)
ax.spines["left"].set_color(GRID)
ax.spines["bottom"].set_color(GRID)
ax.yaxis.grid(True, color=GRID, linewidth=0.8)
ax.set_axisbelow(True)
ax.legend(loc="lower center", bbox_to_anchor=(0.5, -0.28), ncol=2, frameon=False, fontsize=9)
fig.tight_layout()
fig.savefig("fig_per_class_f1.png", dpi=150, bbox_inches="tight")
plt.close(fig)

print("저장 완료: fig_confusion_matrix.png, fig_per_class_f1.png")
