from pptx import Presentation
from pptx.util import Inches, Pt
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN

prs = Presentation()
prs.slide_width  = Inches(13.33)
prs.slide_height = Inches(7.5)

# ── Simple Color Palette (make_ppt.py와 동일) ──
NAVY  = RGBColor(0x1F, 0x2D, 0x4E)
BLUE  = RGBColor(0x2D, 0x6A, 0xBF)
WHITE = RGBColor(0xFF, 0xFF, 0xFF)
GRAY  = RGBColor(0x55, 0x65, 0x80)
LGRAY = RGBColor(0xF4, 0xF6, 0xFA)
GREEN = RGBColor(0x27, 0xAE, 0x60)
RED   = RGBColor(0xC0, 0x39, 0x2B)
ORNG  = RGBColor(0xE6, 0x7E, 0x22)
CYAN  = RGBColor(0x16, 0xA0, 0xBF)

blank = prs.slide_layouts[6]

def rect(slide, l, t, w, h, fill=None, line=None):
    s = slide.shapes.add_shape(1, l, t, w, h)
    if fill:
        s.fill.solid(); s.fill.fore_color.rgb = fill
    else:
        s.fill.background()
    if line:
        s.line.color.rgb = line; s.line.width = Pt(1)
    else:
        s.line.fill.background()
    return s

def txt(slide, text, l, t, w, h, size=Pt(13), color=WHITE,
        bold=False, align=PP_ALIGN.LEFT, wrap=True, italic=False):
    tb = slide.shapes.add_textbox(l, t, w, h)
    tb.word_wrap = wrap
    tf = tb.text_frame; tf.word_wrap = wrap
    p = tf.paragraphs[0]; p.alignment = align
    r = p.add_run(); r.text = text
    r.font.size = size; r.font.color.rgb = color
    r.font.bold = bold; r.font.italic = italic; r.font.name = "Malgun Gothic"
    return tb

def txt_lines(slide, lines, l, t, w, h, size=Pt(12.5),
              default_color=NAVY, spacing=Pt(4)):
    tb = slide.shapes.add_textbox(l, t, w, h)
    tb.word_wrap = True
    tf = tb.text_frame; tf.word_wrap = True
    first = True
    for item in lines:
        if first:
            p = tf.paragraphs[0]; first = False
        else:
            p = tf.add_paragraph()
        p.space_before = spacing; p.alignment = PP_ALIGN.LEFT
        if isinstance(item, tuple):
            text_, color_, bold_ = item
        else:
            text_ = item; color_ = default_color; bold_ = False
        r = p.add_run(); r.text = text_
        r.font.size = size; r.font.color.rgb = color_
        r.font.bold = bold_; r.font.name = "Malgun Gothic"

def header(slide, title, subtitle=None):
    rect(slide, 0, 0, prs.slide_width, Inches(1.1), fill=NAVY)
    rect(slide, 0, Inches(1.1), prs.slide_width, Pt(2.5), fill=BLUE)
    txt(slide, title, Inches(0.4), Inches(0.1), Inches(12), Inches(0.65),
        size=Pt(24), color=WHITE, bold=True)
    if subtitle:
        txt(slide, subtitle, Inches(0.4), Inches(0.7), Inches(12), Inches(0.38),
            size=Pt(13), color=RGBColor(0xAA,0xCC,0xFF))

def image_placeholder(slide, l, t, w, h, label):
    rect(slide, l, t, w, h, fill=WHITE, line=GRAY)
    txt(slide, f"[그림 삽입: {label}]", l, t + h/2 - Inches(0.2), w, Inches(0.4),
        size=Pt(13), color=GRAY, bold=False, align=PP_ALIGN.CENTER, italic=True)

# ════════════════════════════════
#  SLIDE 1 — TITLE
# ════════════════════════════════
sl = prs.slides.add_slide(blank)
rect(sl, 0, 0, prs.slide_width, prs.slide_height, fill=LGRAY)
rect(sl, 0, 0, prs.slide_width, Inches(4.0), fill=NAVY)
rect(sl, 0, Inches(4.0), prs.slide_width, Pt(3), fill=BLUE)

txt(sl, "개인화 판단 에이전트 — KG + MCP + A2A",
    Inches(0.6), Inches(0.9), Inches(12), Inches(1.0),
    size=Pt(30), color=WHITE, bold=True)
txt(sl, "LivingCare v5 그래프 기반 프로토타입 · action/judgement/timing CoT 에이전트",
    Inches(0.6), Inches(1.95), Inches(12), Inches(0.55),
    size=Pt(17), color=RGBColor(0xAA,0xCC,0xFF))
txt(sl, "Ai-living-care 산학협력 프로토타입",
    Inches(0.6), Inches(2.6), Inches(10), Inches(0.42),
    size=Pt(13), color=GRAY)

items = ["① 어떤 문제인가?",
         "② 어떻게 풀었는가? — KG + MCP + A2A",
         "③ 무엇을 구현했는가?",
         "④ 어떻게 검증했는가?",
         "⑤ 결과와 시사점은?"]
txt(sl, "구성", Inches(0.6), Inches(4.3), Inches(4), Inches(0.4),
    size=Pt(14), color=NAVY, bold=True)
for i, it in enumerate(items):
    txt(sl, it, Inches(0.8), Inches(4.75)+i*Inches(0.44), Inches(11), Inches(0.42),
        size=Pt(13.5), color=NAVY)

# ════════════════════════════════
#  SLIDE 2 — PROBLEM
# ════════════════════════════════
sl = prs.slides.add_slide(blank)
rect(sl, 0, 0, prs.slide_width, prs.slide_height, fill=LGRAY)
header(sl, "① 어떤 문제인가?", "범용 LLM + 동일 프롬프트의 한계")

problems = [
    ("개인화 실패",
     "범용 LLM에 동일한 프롬프트를 쓰면 노령자 개인 특성(취약군 여부·진단명·\n"
     "복용약)이 달라져도 답변은 일반론에 머문다.\n"
     "개인 맥락에 맞는 프롬프트 해석 자체가 안 됨.",
     RED),
    ("맥락 → 실행 연결 불가",
     "같은 axis(WellBeing/Safety 등)라도 시각·개인 조건에 따라 다른 정책이\n"
     "나와야 하는데, 프롬프트만으로는 그 맥락을 함수 호출/기기 동작으로\n"
     "연결하지 못한다.",
     ORNG),
    ("정답 하나로 못 채점",
     "허용 가능한 정책이 여러 개일 수 있는데, 정답 JSON 하나와 문자열\n"
     "일치로만 비교하면 실제 정책 품질(개인화 반영 여부)을 못 잰다.",
     BLUE),
]
for i, (title, body, col) in enumerate(problems):
    lx = Inches(0.3 + i * 4.35)
    rect(sl, lx, Inches(1.25), Inches(4.15), Inches(5.4), fill=WHITE)
    rect(sl, lx, Inches(1.25), Inches(4.15), Inches(0.45), fill=col)
    txt(sl, title, lx+Inches(0.12), Inches(1.28), Inches(3.9), Inches(0.38),
        size=Pt(14), color=WHITE, bold=True)
    txt(sl, body, lx+Inches(0.15), Inches(1.82), Inches(3.85), Inches(4.5),
        size=Pt(12.5), color=NAVY, wrap=True)

rect(sl, Inches(0.3), Inches(6.85), Inches(12.7), Inches(0.5), fill=NAVY)
txt(sl, "핵심 질문: 그래프 조회 결과 자체가 개인화의 원천이 되게 할 수 있는가?",
    Inches(0.5), Inches(6.87), Inches(12.3), Inches(0.46),
    size=Pt(14), color=WHITE, bold=True, align=PP_ALIGN.CENTER)

# ════════════════════════════════
#  SLIDE 3 — SOLUTION: KG + MCP + A2A
# ════════════════════════════════
sl = prs.slides.add_slide(blank)
rect(sl, 0, 0, prs.slide_width, prs.slide_height, fill=LGRAY)
header(sl, "② 어떻게 풀었는가?", "KG · MCP · A2A를 결합해 맥락별 함수/에이전트 호출로 해결")

cols_data = [
    ("KG — 지식그래프", BLUE, [
        "개인(Subject: 진단명·복용약·취약군 여부)과",
        "판단 규칙(MonitoringRule)·정책을",
        "그래프로 분리해 보관",
        "",
        "같은 axis라도 누구의 그래프를",
        "조회하느냐에 따라 다른 답이 나옴",
        "",
        "→ 프롬프트가 아니라 그래프 조회",
        "   결과가 개인화의 원천",
    ]),
    ("MCP — 함수 호출", GREEN, [
        "retrieve_graph_knowledge 도구",
        "하나로 그래프 조회를 통일",
        "",
        "LLM이 '필요하다'고 판단한",
        "순간에만 호출",
        "",
        "→ 전체 그래프를 프롬프트에",
        "   미리 밀어넣지 않음",
    ]),
    ("A2A — 에이전트 호출", ORNG, [
        "axis별로 판단 주체가 다름:",
        "규칙이 답을 정하는 축(WellBeing/",
        "Safety)은 코드가 결정론 처리",
        "",
        "규칙만으론 안 되는 축(Comfort)은",
        "LLM 에이전트가 도구를 스스로",
        "호출하며 판단",
        "",
        "→ 최종 대응은 실행 Worker에게",
        "   넘기는 경계를 명시",
    ]),
]
for ci, (title, col, lines) in enumerate(cols_data):
    lx = Inches(0.3 + ci*4.35)
    rect(sl, lx, Inches(1.25), Inches(4.15), Inches(5.85), fill=WHITE)
    rect(sl, lx, Inches(1.25), Inches(4.15), Inches(0.42), fill=col)
    txt(sl, title, lx+Inches(0.12), Inches(1.28), Inches(3.9), Inches(0.36),
        size=Pt(14), color=WHITE, bold=True)
    txt_lines(sl, lines, lx+Inches(0.15), Inches(1.78), Inches(3.9), Inches(5.1),
              default_color=NAVY, size=Pt(12))

# ════════════════════════════════
#  SLIDE 4 — 구현: v5 그래프 구조
# ════════════════════════════════
sl = prs.slides.add_slide(blank)
rect(sl, 0, 0, prs.slide_width, prs.slide_height, fill=LGRAY)
header(sl, "③ 무엇을 구현했는가?", "v5 그래프의 3+1 정책 분리 → action/judgement/timing 그대로 매핑")

rect(sl, Inches(0.3), Inches(1.25), Inches(6.6), Inches(5.85), fill=WHITE)
txt(sl, "판단 파이프라인 (발명한 분류가 아니라 스키마가 준 분류)",
    Inches(0.42), Inches(1.3), Inches(6.3), Inches(0.38), size=Pt(13.5), color=NAVY, bold=True)

pipe_rows = [
    ("action(관측)", "ObservationSelectionPolicy -[:SELECTS]-> CheckItem", "무엇을 관측할지", BLUE),
    ("judgement", "MonitoringRule -[:EVALUATES]-> CheckItem", "threshold·severity로 판단", ORNG),
    ("timing", "LoopTerminationPolicy -[:ESCALATES_VIA]-> CheckItem", "몇 번 돌고 사람에게 넘길지", GREEN),
    ("action(대응)", "ResponseSelectionPolicy -[:SELECTS]-> CheckItem", "escalate 시 무엇을 실행할지", RED),
]
for i, (label, rel, role, col) in enumerate(pipe_rows):
    ly = Inches(1.78) + i * Inches(1.15)
    rect(sl, Inches(0.38), ly, Inches(6.42), Inches(1.05), fill=LGRAY if i%2==0 else WHITE)
    rect(sl, Inches(0.38), ly, Inches(1.35), Inches(1.05), fill=col)
    txt(sl, label, Inches(0.38), ly, Inches(1.35), Inches(1.05),
        size=Pt(12.5), color=WHITE, bold=True, align=PP_ALIGN.CENTER)
    txt(sl, rel, Inches(1.85), ly+Inches(0.08), Inches(4.85), Inches(0.5),
        size=Pt(11), color=GRAY)
    txt(sl, role, Inches(1.85), ly+Inches(0.58), Inches(4.85), Inches(0.4),
        size=Pt(12.5), color=NAVY, bold=True)

rect(sl, Inches(7.05), Inches(1.25), Inches(5.95), Inches(5.85), fill=WHITE)
rect(sl, Inches(7.05), Inches(1.25), Inches(5.95), Inches(0.42), fill=BLUE)
txt(sl, "개인화 메커니즘",
    Inches(7.17), Inches(1.28), Inches(5.7), Inches(0.36), size=Pt(14), color=WHITE, bold=True)

personalize = [
    ("Threshold 개인화", NAVY, True),
    ("  vulnerable_condition_value + Subject.is_vulnerable", GRAY, False),
    ("  → 일반군/취약군 다른 기준(WHO 18°C vs 20°C)", NAVY, False),
    ("", NAVY, False),
    ("복약 위험 신호", NAVY, True),
    ("  Subject -[TAKES]-> Drug <-[CONCERNS]- MedicationKnowledge", GRAY, False),
    ("  → 복용약에 따라 개인별로 다른 위험 flag(Beers/STOPP 기준)", NAVY, False),
    ("", NAVY, False),
    ("A2A dispatch 스텁", NAVY, True),
    ("  대응 CheckItem 확정 시 실행 Worker(디바이스/서비스) 표시", GRAY, False),
    ("  → 판단과 실행의 경계를 결과에 명시(네트워크 호출 없음)", NAVY, False),
]
txt_lines(sl, personalize, Inches(7.2), Inches(1.78), Inches(5.65), Inches(5.2), size=Pt(12.5))

# ════════════════════════════════
#  SLIDE 5 — 검증 방법론
# ════════════════════════════════
sl = prs.slides.add_slide(blank)
rect(sl, 0, 0, prs.slide_width, prs.slide_height, fill=LGRAY)
header(sl, "④ 어떻게 검증했는가?", "정답 JSON 문자열 비교 대신 제약조건(constraint) 채점")

rect(sl, Inches(0.3), Inches(1.25), Inches(6.15), Inches(5.85), fill=WHITE)
rect(sl, Inches(0.3), Inches(1.25), Inches(6.15), Inches(0.42), fill=RED)
txt(sl, "기존 방식의 문제", Inches(0.42), Inches(1.28), Inches(5.9), Inches(0.36), size=Pt(14), color=WHITE, bold=True)
old_way = [
    ("정답 JSON 하나를 정해두고", NAVY, False),
    ("실행 결과와 문자열 일치로 비교", NAVY, False),
    ("", NAVY, False),
    ("→ 허용 가능한 정책이 여러 개일 수", RED, False),
    ("   있다는 사실을 반영 못 함", RED, False),
    ("→ '어디서 왜 틀렸는지' 안 보임", RED, False),
]
txt_lines(sl, old_way, Inches(0.45), Inches(1.78), Inches(5.8), Inches(4.5), size=Pt(13))

rect(sl, Inches(6.7), Inches(1.25), Inches(6.3), Inches(5.85), fill=WHITE)
rect(sl, Inches(6.7), Inches(1.25), Inches(6.3), Inches(0.42), fill=GREEN)
txt(sl, "채택 방식 — 제약조건 채점", Inches(6.82), Inches(1.28), Inches(6.0), Inches(0.36), size=Pt(14), color=WHITE, bold=True)
new_way = [
    ("케이스마다 '허용 가능한 것'을 집합으로 선언", NAVY, False),
    ("  (severity_allowed, response_check_item_allowed, ...)", GRAY, False),
    ("", NAVY, False),
    ("필드 6개를 각각 pass/fail로 채점:", NAVY, True),
    ("  escalate · severity · response_check_item ·", GRAY, False),
    ("  personalization · required_fields · task_dispatch", GRAY, False),
    ("", NAVY, False),
    ("테스트 케이스 12개 = persona 3명 × axis(WellBeing/", NAVY, False),
    ("Safety) × 관측 시나리오(정상/이상, 낮/밤)", NAVY, False),
]
txt_lines(sl, new_way, Inches(6.82), Inches(1.78), Inches(6.05), Inches(5.2), size=Pt(12.5))

rect(sl, Inches(0.3), Inches(6.95), Inches(12.7), Inches(0.42), fill=NAVY)
txt(sl, "정책 적합률 = 6개 필드 전부 pass한 케이스 수 / 전체  |  필드별 오류율  |  실제 작업 성공률 = escalate 케이스 중 실행 대상이 확보된 비율",
    Inches(0.4), Inches(6.97), Inches(12.5), Inches(0.38), size=Pt(11.5), color=WHITE, align=PP_ALIGN.CENTER)

# ════════════════════════════════
#  SLIDE 6 — 결과
# ════════════════════════════════
sl = prs.slides.add_slide(blank)
rect(sl, 0, 0, prs.slide_width, prs.slide_height, fill=LGRAY)
header(sl, "④ 검증 결과", "15개 케이스 — persona 3명 × WellBeing/Safety × 정상/이상/경계값")

callouts = [
    ("정책 적합률", "100.0%", "15 / 15 (경계값 케이스 포함)", GREEN),
    ("실제 작업 성공률", "100.0%", "7 / 7 (escalate)", CYAN),
    ("필드별 오류율", "0.0%", "6개 필드 전부", BLUE),
]
for i, (label, value, sub, col) in enumerate(callouts):
    lx = Inches(0.3 + i*4.25)
    rect(sl, lx, Inches(1.25), Inches(4.0), Inches(1.5), fill=WHITE)
    rect(sl, lx, Inches(1.25), Inches(4.0), Inches(0.38), fill=col)
    txt(sl, label, lx, Inches(1.27), Inches(4.0), Inches(0.34), size=Pt(13), color=WHITE, bold=True, align=PP_ALIGN.CENTER)
    txt(sl, value, lx, Inches(1.6), Inches(4.0), Inches(0.6), size=Pt(28), color=col, bold=True, align=PP_ALIGN.CENTER)
    txt(sl, sub, lx, Inches(2.3), Inches(4.0), Inches(0.4), size=Pt(10.5), color=GRAY, align=PP_ALIGN.CENTER)

txt(sl, "※ 위 100%는 '결정론 threshold 로직이 정확한가'를 잰 좁은 값이다 — 다음 슬라이드에서 정면 검증",
    Inches(0.3), Inches(2.82), Inches(12.7), Inches(0.3), size=Pt(11), color=RED,
    align=PP_ALIGN.CENTER, italic=True)

# persona 표 — 개인화가 실제로 다른 결과를 만드는지
rect(sl, Inches(0.3), Inches(3.15), Inches(6.15), Inches(2.0), fill=WHITE)
txt(sl, "persona별 개인화 신호 (같은 axis·같은 관측값이어도 다름)",
    Inches(0.42), Inches(3.2), Inches(5.9), Inches(0.36), size=Pt(12.5), color=NAVY, bold=True)
pt_headers = ["persona", "취약군", "위험 flag 수"]
pt_rows = [
    ("김옥순 (심부전/기립성저혈압)", "O", "3"),
    ("박말순 (당뇨, 대조군)", "X", "1"),
    ("이갑수 (치매/낙상이력)", "O", "2"),
]
cw2 = [Inches(3.1), Inches(1.3), Inches(1.6)]
cx2 = [Inches(0.42)]
for w in cw2[:-1]: cx2.append(cx2[-1]+w)
for h, x, w in zip(pt_headers, cx2, cw2):
    txt(sl, h, x, Inches(3.62), w, Inches(0.3), size=Pt(11), color=GRAY, bold=True)
for ri, row in enumerate(pt_rows):
    ly = Inches(3.95) + ri*Inches(0.38)
    for v, x, w in zip(row, cx2, cw2):
        txt(sl, v, x, ly, w, Inches(0.34), size=Pt(12), color=NAVY)

image_placeholder(sl, Inches(6.7), Inches(3.15), Inches(6.3), Inches(3.95),
                   "fig_core_metrics.png / fig_field_error_rate.png / fig_persona_comparison.png")

rect(sl, Inches(0.3), Inches(5.3), Inches(6.15), Inches(1.8), fill=LGRAY)
txt(sl, "같은 axis·같은 관측값이어도 누구의 그래프를 조회하느냐에 따라\n"
        "다른 위험 신호가 나온다 — 프롬프트가 아니라 그래프 조회 결과가\n"
        "개인화의 원천이라는 주장의 직접적 증거.",
    Inches(0.45), Inches(5.4), Inches(6.0), Inches(1.6), size=Pt(12), color=NAVY)

# ════════════════════════════════
#  SLIDE 6.5 — "100%가 의심스럽다" 정면 검증
# ════════════════════════════════
sl = prs.slides.add_slide(blank)
rect(sl, 0, 0, prs.slide_width, prs.slide_height, fill=LGRAY)
header(sl, "④ \"100%가 의심스럽다\"", "4가지로 정면 검증 — 좁은 주장과 넓은 주장을 분리한다")

checks = [
    ("①", BLUE, "3구간 표 → 18단계 연속 곡선",
     "참값/threshold 0.3~2.0배, N=300×18. threshold에서만\n매끄러운 S자 — 100%는 곡선 전체가 아니라 1.4배 이상\n구간에서만 나오는 값."),
    ("②", ORNG, "몬테카를로 0/200은 표본 착시",
     "가우시안 CDF로 해석적 정확값 재계산:\n특이도=99.9571%, 민감도=99.9968%.\n진짜 오류확률 0.043%(2,300번에 1번) — 200회로는 안 보였을 뿐."),
    ("③", GREEN, "잡음 스윕 — 문헌 특이도(78~99%) 도달점",
     "실제 쓴 잡음(15%)의 약 1.7배(25%)를 줘야 문헌 수준까지\n떨어진다 → 문헌의 낮은 특이도는 센서 잡음이 아니라\n다른 요인(임상 맥락·다중 규칙) 때문."),
    ("④", RED, "PPV·τ-bench로 범위 확인",
     "PPV는 발생률 0.003% 밑에서만 문헌 범위(5.8~54%) 진입.\nτ-bench(GPT-4o 61.2%/35.2%)는 LLM 대화 과제라 우리\nif-else 로직과 나란히 비교하면 그 자체가 오도."),
]
for i, (num, col, title, body) in enumerate(checks):
    lx = Inches(0.3 + (i % 2) * 6.4)
    ly = Inches(1.25 + (i // 2) * 1.85)
    rect(sl, lx, ly, Inches(6.15), Inches(1.7), fill=WHITE)
    rect(sl, lx, ly, Inches(0.55), Inches(1.7), fill=col)
    txt(sl, num, lx, ly + Inches(0.55), Inches(0.55), Inches(0.6),
        size=Pt(20), color=WHITE, bold=True, align=PP_ALIGN.CENTER)
    txt(sl, title, lx + Inches(0.68), ly + Inches(0.08), Inches(5.35), Inches(0.4),
        size=Pt(13), color=col, bold=True)
    txt(sl, body, lx + Inches(0.68), ly + Inches(0.5), Inches(5.35), Inches(1.15),
        size=Pt(10.5), color=NAVY)

rect(sl, Inches(0.3), Inches(5.05), Inches(12.7), Inches(1.05), fill=NAVY)
txt(sl, "결론: 100%는 \"이 threshold 로직은 적당한 센서잡음에 강건하다\"는 좁은 주장에 대한 정확한 값이다.\n"
        "\"실전에서 alert fatigue 없이 잘 작동한다\"는 넓은 주장은 여전히 미검증 — 이 둘을 섞어 쓰지 않는다.",
    Inches(0.5), Inches(5.2), Inches(12.3), Inches(0.8), size=Pt(13), color=WHITE, align=PP_ALIGN.CENTER)

image_placeholder(sl, Inches(0.3), Inches(6.2), Inches(6.15), Inches(1.0), "fig_response_curve.png")
image_placeholder(sl, Inches(6.55), Inches(6.2), Inches(6.5), Inches(1.0), "fig_noise_sensitivity.png")

# ════════════════════════════════
#  SLIDE 7 — INSIGHTS (시사점)
# ════════════════════════════════
sl = prs.slides.add_slide(blank)
rect(sl, 0, 0, prs.slide_width, prs.slide_height, fill=LGRAY)
header(sl, "⑤ 결과의 시사점", "실제로 만들고 검증하며 확인한 것들")

insights = [
    (GREEN, "시사점 1",
     "그래프 조회 결과 자체가 개인화의 원천이다",
     "같은 axis·같은 관측값이어도 subject별 위험 flag 수가 다르게 나옴(김옥순 3 · 박말순 1 · "
     "이갑수 2) — 프롬프트가 아니라 그래프가 개인화를 만든다는 걸 실측으로 확인."),
    (BLUE, "시사점 2",
     "3분리 정책 스키마가 action/judgement/timing과 정확히 대응한다",
     "그래프 스키마(ObservationSelectionPolicy/MonitoringRule/LoopTerminationPolicy/"
     "ResponseSelectionPolicy)가 이미 CoT 계획 구조와 1:1 대응 — 별도 분류 체계를 발명할 필요가 없었음."),
    (ORNG, "시사점 3",
     "결정론 ↔ LLM 에이전트 경계는 숫자 tier가 아니라 정책 텍스트로 충분히 근거 있다",
     "WellBeing/Safety=결정론, Comfort=에이전트 루프라는 구분이 seed 정책 rationale 원문에 "
     "이미 명시돼 있었음 — 별도 tier 필드를 새로 만들 필요가 없었음."),
    (RED, "시사점 4",
     "정책 적합률과 개인화는 서로 다른 축이다",
     "정확성(적합률)은 persona 간 동일(100%)해야 정상이고, '다르게 판단했다'는 증거는 "
     "별도 지표(위험 flag 수)로 봐야 한다 — 문자열 일치 채점으로는 이 구분 자체가 안 보임."),
    (CYAN, "시사점 5",
     "판단이 맞아도 실행할 곳이 없으면 실패다",
     "escalate 판단이 맞아도 실행 Worker가 없으면 무의미 — 정책 적합률과 별개로 '실제 작업 "
     "성공률'을 둬야 물리 기기 없는 채널(ci:call_caregiver)도 서비스 워커로 잡아낼 수 있음."),
]

positions_layout = [
    (Inches(0.3),  Inches(1.25)),
    (Inches(6.7),  Inches(1.25)),
    (Inches(0.3),  Inches(3.75)),
    (Inches(6.7),  Inches(3.75)),
    (Inches(3.5),  Inches(6.2)),
]
for i, ((lx, ly), (col, num, title, body)) in enumerate(zip(positions_layout, insights)):
    h = Inches(2.3) if i < 4 else Inches(1.1)
    w = Inches(6.15) if i < 4 else Inches(6.3)
    rect(sl, lx, ly, w, h, fill=WHITE)
    rect(sl, lx, ly, w, Inches(0.42), fill=col)
    txt(sl, num, lx+Inches(0.12), ly+Inches(0.05), Inches(1.5), Inches(0.36),
        size=Pt(13), color=WHITE, bold=True)
    txt(sl, title, lx+Inches(0.12), ly+Inches(0.48), w-Inches(0.2), Inches(0.6),
        size=Pt(12.5), color=col, bold=True)
    if i < 4:
        txt(sl, body, lx+Inches(0.15), ly+Inches(1.1), w-Inches(0.25), Inches(1.1),
            size=Pt(11), color=GRAY)
    else:
        txt(sl, body, lx+Inches(0.15), ly+Inches(0.62), w-Inches(0.25), Inches(0.44),
            size=Pt(10.5), color=GRAY)

# ════════════════════════════════
#  SLIDE 8 — 한계 & 다음 단계
# ════════════════════════════════
sl = prs.slides.add_slide(blank)
rect(sl, 0, 0, prs.slide_width, prs.slide_height, fill=NAVY)
rect(sl, 0, Inches(1.0), prs.slide_width, Pt(2.5), fill=BLUE)

txt(sl, "한계와 다음 단계", Inches(0.4), Inches(0.15), Inches(12), Inches(0.72),
    size=Pt(28), color=WHITE, bold=True)

limits = [
    ("검증 심도", RED,
     "12개 케이스가 전부 pass — 규칙 구현이 맞다는 확인이지, 그레이더 자체가 실패를 "
     "잡아내는지는 별도 검증 필요. 의도적 실패 케이스(경계값·존재하지 않는 axis)로 다음에 확인."),
    ("Comfort축 미평가", ORNG,
     "LLM 에이전트 경로는 API 키가 있어야 실행 가능. 붙이면 구조화 출력이 아닌 자유 "
     "reasoning이 섞여 LLM-judge 기반 채점이 추가로 필요."),
    ("단일 CheckItem만 평가", BLUE,
     "ObservationSelectionPolicy가 여러 CheckItem을 우선순위로 갖고 있어도 지금은 1순위만 봄 "
     "— 다중 CheckItem 순회로 확장 필요."),
    ("취약군 threshold 정규식 추출", CYAN,
     "vulnerable_condition_value가 타입 있는 숫자가 아니라 문자열이라 정규식으로 우회 — "
     "seed 스키마에 타입 있는 필드 보강하면 해소."),
]
for i, (label, col, body) in enumerate(limits):
    ly = Inches(1.15) + i*Inches(1.5)
    rect(sl, Inches(0.3), ly, Inches(2.0), Inches(1.3), fill=col)
    txt(sl, label, Inches(0.3), ly, Inches(2.0), Inches(1.3),
        size=Pt(13.5), color=WHITE, bold=True, align=PP_ALIGN.CENTER)
    rect(sl, Inches(2.4), ly, Inches(10.55), Inches(1.3), fill=RGBColor(0x1E,0x2A,0x50))
    txt(sl, body, Inches(2.55), ly+Inches(0.15), Inches(10.25), Inches(1.05),
        size=Pt(12.5), color=WHITE)

txt(sl, "graph_cot_agent.py · eval_graph_cot_agent.py · eval_report.m · report.md",
    Inches(0.3), Inches(7.1), Inches(12.7), Inches(0.34),
    size=Pt(11), color=GRAY, align=PP_ALIGN.CENTER)

# ════════════════════════════════
#  SAVE
# ════════════════════════════════
out = r"C:\Users\A\AppData\Local\Temp\claude\C--Users-A\d9d2df23-5c30-4ca2-924f-3ffeb2fc6e31\scratchpad\LivingCare_개인화_에이전트.pptx"
prs.save(out)
print("OK:", out)
