"""
eval_synthetic_nl_100.py — 합성(내가 지어낸) 자연어 100개로 NL 라우터를 스트레스 테스트한다.

**9절(eval_nl_e2e.py)과의 결정적 차이**: 거기 16개는 전부 그래프에 실제로 있는 텍스트
(Intent.raw_text, goal_pattern, problem_pattern)였다. 여기 100개는 **내가 지어낸 문장**이다
— WellBeing/Safety/Comfort/KnowledgeLookup 주제와 어휘는 그래프 도메인(활동·체중·복약·
화재·낙상·온도·조명·약물상호작용)에서 가져왔지만, 문장 자체와 정답 라벨은 내가 붙였다.
그래서 이 결과를 "그래프가 검증했다"고 쓰면 안 된다 — **라우터의 일반화 능력을 보는
스트레스 테스트**로만 쓴다. 16개는 표본이 너무 작아 통계적으로 약했다는 문제를 100개로
보완하되, 그 대가로 "정답이 그래프가 아니라 내 판단"이라는 걸 명시한다.

카테고리당 25개, 격식체/비격식체/직접질문/간접질문을 섞어 실제 발화 다양성에 더 가깝게 했다.

실행: python eval_synthetic_nl_100.py
"""

from __future__ import annotations

import json
import sys

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics import accuracy_score, classification_report, confusion_matrix, f1_score
from sklearn.metrics.pairwise import cosine_similarity

from eval_nl_e2e import CATEGORIES, build_reference_docs
from graph_cot_agent import SeedGraph

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

# --------------------------------------------------------------------------- #
# 합성 100개 — 내가 지어냄. 카테고리당 25개.
# --------------------------------------------------------------------------- #
SYNTHETIC = {
    "WellBeing": [
        "할머니 요즘 잘 지내시는지 봐줘", "아버지 오늘 컨디션 어떤지 확인 좀",
        "어머니 밥은 잘 드시고 계신지 궁금해", "할아버지 요즘 기운 없어 보이던데 확인해줄래",
        "오늘 움직임이 좀 적으신 것 같은데 괜찮으신지", "요즘 계속 방에만 계시는 것 같아서 걱정돼",
        "체중이 갑자기 줄었다고 들었는데 확인 가능해?", "최근에 살이 빠지신 것 같던데 체크해줘",
        "약 제때 챙겨 드시고 계신지 확인해줘", "오늘 약 드셨는지 좀 봐줄래",
        "웨어러블 워치 신호가 며칠째 안 잡히는데 왜 그런지", "심박수 센서가 계속 연결이 안 되는 것 같아",
        "어젯밤에 잘 주무셨는지 궁금해", "밤새 움직임이 없었는데 정상인지 확인해줘",
        "요즘 걸음걸이가 느려지신 것 같은데", "의자에서 일어나는 게 힘드신 것 같아",
        "혈당 수치가 괜찮으신지 확인해줄 수 있어?", "어제부터 기력이 없어 보이시는데 상태 좀 봐줘",
        "며칠째 식사량이 줄어든 것 같아서", "아침에 일어나셨는지 확인 좀 해줘",
        "오늘 하루 종일 어떻게 지내셨는지 요약해줘", "최근 활동량이 줄어든 게 걱정돼",
        "혼자 계신데 별일 없으신지 봐줘", "요즘 자주 깜빡깜빡 하시는 것 같아 상태 확인 부탁해",
        "컨디션 체크 한번 해줄래",
    ],
    "Safety": [
        "가스레인지 안 끄고 나가신 거 아닌지 확인해줘", "부엌에서 타는 냄새 안 나는지 체크해줘",
        "현관문 계속 열려있는 거 아니야?", "문 안 잠그고 주무신 건 아닌지 걱정돼",
        "화장실에 너무 오래 계신 것 같은데", "욕실에서 안 나오시는데 괜찮으신지 확인 좀",
        "넘어지신 건 아닌지 확인해줘", "갑자기 쓰러지신 것 같으면 바로 알려줘",
        "연기 감지되면 즉시 알려줘", "화재 위험 없는지 확인해줘",
        "밤에 화장실 가시다 넘어지신 건 아닌지", "문 열어놓고 외출하신 거 아닌지 봐줘",
        "낙상 위험 있는지 순찰 좀 돌아줘", "야간에 이상 소리 나면 확인해줘",
        "욕조에서 미끄러지신 건 아닌지 걱정돼", "현관 잠금장치 확인해줘",
        "가스 냄새 나는지 체크해줘", "계단에서 넘어지신 거 아닌지 확인",
        "새벽에 인기척 없는데 괜찮으신지", "문 열린 채로 오래 방치돼있는지 확인해줘",
        "불이 난 건 아닌지 확인 부탁해", "화장실 바닥 미끄러워서 걱정되는데 상태 확인해줘",
        "밤사이 위험한 일 없었는지 순찰해줘", "낙상 감지되면 바로 보호자한테 알려줘",
        "문단속 잘 하셨는지 확인 좀",
    ],
    "Comfort": [
        "방 온도가 너무 낮은 거 아니야?", "실내가 너무 추운 것 같은데 확인해줘",
        "집 안이 너무 더운 거 아닌지 봐줘", "난방 좀 틀어드려야 할 것 같은데",
        "에어컨 세게 틀어져 있는 거 아닌지", "거실이 너무 어두운 것 같아",
        "조명 좀 밝게 해줘", "복도가 캄캄한데 불 좀 켜줘",
        "습도가 너무 높은 거 아닌지 확인해줘", "환기가 잘 안 되는 것 같은데",
        "창문 열어서 환기 좀 시켜줘", "실내 공기가 답답한 것 같아",
        "밤에 방이 너무 서늘한 거 아닌지", "온도 조절 좀 해줄 수 있어?",
        "지금 실내 온도 몇 도야?", "조명 밝기 확인 좀 해줘",
        "겨울인데 난방 잘 되고 있는지", "여름에 냉방 너무 세게 틀어진 거 아닌지",
        "습도 조절 좀 해줘", "방이 쾌적한지 확인해줘",
        "야간에 조명이 너무 밝아서 수면 방해되지 않는지", "거실 온도 좀 확인해줄래",
        "집안 환경이 괜찮은지 전반적으로 봐줘", "통풍이 잘 되는지 확인 부탁해",
        "실내가 너무 건조한 거 아닌지",
    ],
    "KnowledgeLookup": [
        "이 약 먹어도 되는지 확인해줄 수 있어?", "혈압약이랑 이 약 같이 먹어도 되나",
        "당뇨약 복용 중인데 이 약 괜찮을까", "이 약 부작용이 뭐가 있는지 알려줘",
        "지금 먹는 약이랑 상호작용 있는지 확인해줘", "심부전 있으신데 이 약 드셔도 되는지",
        "이 진단명이면 뭘 조심해야 해?", "치매 환자한테 이 약 써도 되는지",
        "골다공증 있는데 이 약 먹어도 될까", "이 약 노인한테 위험하다고 들었는데 맞아?",
        "수면제 복용해도 되는지 궁금해", "진통제 장기 복용해도 괜찮은지",
        "이 약이랑 저 약 같이 먹어도 되나요", "항생제 복용 중인데 다른 약 먹어도 되는지",
        "이뇨제 복용 중인데 주의할 점이 뭐야", "고혈압 환자가 조심해야 할 약이 뭐야",
        "이 약 복용 후 어지러우면 어떻게 해야 해", "신장 기능 안 좋으신데 이 약 괜찮은지",
        "벤조디아제핀 계열 약 복용해도 되는지", "이 질환 있을 때 피해야 할 약이 뭐야",
        "항응고제 복용 중인데 이 약 먹어도 되는지", "낙상 위험 높이는 약이 뭐가 있어?",
        "이 약 복용 시 음식 제한이 있는지", "파킨슨병 환자한테 이 약 써도 되는지",
        "약 복용 시간 겹쳐도 괜찮은지 확인해줘",
    ],
}


def route(text, vectorizer, ref_matrix, categories):
    q_vec = vectorizer.transform([text])
    sims = cosine_similarity(q_vec, ref_matrix)[0]
    return categories[sims.argmax()], {c: round(float(s), 4) for c, s in zip(categories, sims)}


if __name__ == "__main__":
    graph = SeedGraph()
    ref_docs = build_reference_docs(graph)
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

    print("=" * 100)
    print(f"[합성 100개 라우팅] N={len(rows)}, accuracy={acc*100:.1f}%, macro-F1={macro_f1*100:.1f}%")
    print("-" * 100)
    print(classification_report(y_true, y_pred, labels=CATEGORIES, zero_division=0))

    cm = confusion_matrix(y_true, y_pred, labels=CATEGORIES)
    print("confusion matrix (rows=true, cols=pred):", CATEGORIES)
    for label, row in zip(CATEGORIES, cm):
        print(f"  {label:<16} {row.tolist()}")

    print("\n[오분류 목록]")
    for r in rows:
        if not r["correct"]:
            print(f"  \"{r['text']}\"  true={r['true_category']} -> pred={r['predicted_category']}  "
                  f"scores={r['scores']}")

    out = {
        "note": "이 데이터는 합성(지어낸) 자연어다 — 그래프 원본 텍스트가 아님. 9절(eval_nl_e2e.py)의 16개만 그래프 원본.",
        "n": len(rows), "accuracy": acc, "macro_f1": macro_f1,
        "labels": CATEGORIES, "confusion_matrix": cm.tolist(), "rows": rows,
    }
    with open("eval_synthetic_nl_100_results.json", "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print("\n[export] eval_synthetic_nl_100_results.json 저장 완료")
