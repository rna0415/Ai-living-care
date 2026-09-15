// ============================================================
// v5 seed 위에 얹는 증분 확장 (2026-09-03) - livingcare_graph_v5_seed.cypher 다음 실행.
// 사용자 피드백("데이터 너무 적다, 누락 많다")에 따라 3가지를 확장:
//   1. 새 디바이스 2개(낙상감지 웨어러블, 혈당계) - 사용자 승인 하에 추가한 신규 하드웨어
//   2. MedicationKnowledge 4개 -> 10개 (Beers/STOPP 추가 조사)
//   3. Persona 1명 -> 3명 (Safety/Comfort축 대조군, is_vulnerable=false 대조군 포함)
// 비파괴 - 이미 뜬 v5 seed 그래프에 MATCH/CREATE로 얹는다.
// ============================================================

// =========================================================
// 1. 신규 DEVICE + CHECKITEM [증류+근거]
// =========================================================
CREATE (:Device {device_id: "cap:fall_wearable", name: "WearableFallDetector", status: "idle"});
CREATE (:Device {device_id: "cap:glucosemonitor", name: "GlucoseMonitor", status: "idle"});

CREATE (:CheckItem {check_item_id: "ci:fall_event", name: "실시간 낙상 이벤트 감지", default_action_type: "OBSERVE", sensor_type: "accelerometer_gyroscope"});
CREATE (:CheckItem {check_item_id: "ci:glucose", name: "혈당 측정", default_action_type: "OBSERVE", sensor_type: "cgm"});

MATCH (d:Device {device_id: "cap:fall_wearable"}), (c:CheckItem {check_item_id: "ci:fall_event"}) CREATE (d)-[:MONITORS]->(c);
MATCH (d:Device {device_id: "cap:glucosemonitor"}), (c:CheckItem {check_item_id: "ci:glucose"}) CREATE (d)-[:MONITORS]->(c);

// =========================================================
// 2. 신규 MONITORING RULE [근거]
// =========================================================
CREATE (:MonitoringRule {rule_id: "mr_sf5_fall_detected", check_item_id: "ci:fall_event", axis: "Safety", severity: "CONCERN", condition_value: "낙상 이벤트 감지(가속도+자이로 임계 초과)", condition_qualifier: "fall_event_detected_immediate", uses_baseline: false, rationale: "허리 착용 3축 가속도계 기반 임계값 알고리즘은 실측 연구에서 민감도 100%·특이도 97.54%(평균 280ms 선행 감지)를 보고했다 - 오탐이 적어 즉시 concern으로 처리해도 되는 수준. fall_history 테이블이 사후 기록용인 것과 달리 이 규칙은 실시간 이벤트를 잡는다.", source: "Wearable accelerometer-based fall detection 임계값 알고리즘 연구(민감도/특이도 실측치) - PMC8322729 계열 문헌"});
CREATE (:MonitoringRule {rule_id: "mr_wb12_hypoglycemia_level1", check_item_id: "ci:glucose", axis: "WellBeing", severity: "MILD", condition_value: "54~70 mg/dL", condition_qualifier: "glucose_mgdl_between_54_70", threshold_mgdl_low: 54, threshold_mgdl_high: 70, uses_baseline: false, rationale: "ADA 기준 Level 1 저혈당 - 아직 신경당결핍 증상이 나타나기 전 구간이라 mild로 취급하되, 당뇨약(특히 설포닐우레아) 복용자에게는 조기 경보로서 의미가 있다.", source: "ADA Standards of Care in Diabetes - 6. Glycemic Goals and Hypoglycemia"});
CREATE (:MonitoringRule {rule_id: "mr_wb13_hypoglycemia_level2", check_item_id: "ci:glucose", axis: "WellBeing", severity: "CONCERN", condition_value: "54 mg/dL 미만", condition_qualifier: "glucose_mgdl_below_54", threshold_mgdl: 54, direction: "below", uses_baseline: false, rationale: "ADA 기준 Level 2 저혈당 - 신경당결핍 증상이 시작되는 임계값으로 즉각 대응이 필요하다.", source: "ADA Standards of Care in Diabetes - Level 2 hypoglycemia threshold(<54 mg/dL)"});

MATCH (r:MonitoringRule) WHERE r.rule_id IN ["mr_sf5_fall_detected", "mr_wb12_hypoglycemia_level1", "mr_wb13_hypoglycemia_level2"]
MATCH (c:CheckItem {check_item_id: r.check_item_id})
CREATE (r)-[:EVALUATES]->(c);

// =========================================================
// 3. MEDICATION KNOWLEDGE 확장 [근거] - 4개 -> 10개
// =========================================================
CREATE (:MedicationKnowledge {rule_id: "mk_nsaid_avoid", drug_class: "NSAID", recommendation: "avoid_chronic_use", condition: "만성 통증 관리 목적 지속 사용, 특히 고용량 아스피린(>325mg/day) 병용", rationale: "궤양·위장관 출혈·천공 위험 때문에 회피 권고한다. 노인은 위장관 보호 기전이 약화돼 있어 젊은 연령대보다 위험이 크다.", source: "AGS 2023 Updated Beers Criteria - NSAID(고용량 아스피린 포함) 회피 권고"});
CREATE (:MedicationKnowledge {rule_id: "mk_anticholinergic_dementia", drug_class: "Anticholinergic (1세대 항히스타민 등)", recommendation: "avoid_in_dementia", condition: "치매 또는 인지장애가 있는 환자", rationale: "중추신경계 항콜린 부작용(인지기능 추가 저하, 섬망 위험) 때문에 치매/인지장애 환자에게는 회피 권고한다.", source: "AGS 2023 Updated Beers Criteria - 치매/인지장애 환자 항콜린제 회피"});
CREATE (:MedicationKnowledge {rule_id: "mk_antipsychotic_dementia", drug_class: "Antipsychotic", recommendation: "avoid_for_dementia_behavioral_symptoms", condition: "비약물적 개입이 실패했거나 불가능하고 자타해 위협이 있는 경우 외 치매/섬망 행동증상 치료 목적 사용", rationale: "뇌졸중 위험 증가, 인지기능 저하 및 사망률 증가와 연관된다. 사용하더라도 주기적 감량 시도가 필요하다.", source: "AGS 2023 Updated Beers Criteria - 치매 행동증상에 대한 항정신병약 회피"});
CREATE (:MedicationKnowledge {rule_id: "mk_opioid_benzo_combo", drug_class: "Opioid + Benzodiazepine 병용", recommendation: "avoid_concurrent_use", condition: "대안이 없는 경우가 아니면 두 약물 동시 처방 자체를 회피, 부득이하면 호흡억제 징후 밀착 모니터링", rationale: "벤조디아제핀(GABA-A 수용체)과 오피오이드(뮤 수용체)가 서로 다른 경로로 호흡을 억제해 병용시 치명적 호흡억제 위험이 커진다. FDA가 2016년 두 약물군 라벨에 블랙박스 경고를 추가했다.", source: "FDA Drug Safety Communication(2016) 병용 블랙박스 경고 / 노인 낙상위험약물(FRIDs) 임상 지침"});
CREATE (:MedicationKnowledge {rule_id: "mk_sulfonylurea_avoid", drug_class: "Sulfonylurea", recommendation: "avoid_as_first_or_second_line", condition: "더 안전한 대체 약제 사용에 실질적 장벽이 없는 한 1차/2차 단독요법 또는 병용요법으로 사용", rationale: "저혈당 위험 근거 수준이 높고 심혈관계 사건·전체 사망률에도 중등도 우려가 있다. 2023년 개정판은 장시간형(글리부리드 등)뿐 아니라 전체 설포닐우레아로 회피 권고를 확대했다 - 부득이 사용시 장시간형보다 단시간형(글리피지드)을 권고.", source: "AGS 2023 Updated Beers Criteria - 설포닐우레아 전체로 회피 범위 확대"});
CREATE (:MedicationKnowledge {rule_id: "mk_digoxin_dose_limit", drug_class: "Digoxin", recommendation: "avoid_dose_over_0.125mg_and_first_line", condition: "심부전 또는 심방세동의 1차 치료로 사용하거나 1일 0.125mg 초과 용량 사용", rationale: "심부전·심방세동 1차 치료로는 회피하고, 사용하더라도 1일 0.125mg을 넘지 않도록 권고한다.", source: "AGS 2023 Updated Beers Criteria - 디곡신 용량 상한 및 1차치료 회피"});

CREATE (:Drug {name: "ibuprofen"});
CREATE (:Drug {name: "diphenhydramine"});
CREATE (:Drug {name: "risperidone"});
CREATE (:Drug {name: "oxycodone"});
CREATE (:Drug {name: "glyburide"});
CREATE (:Drug {name: "digoxin"});

MATCH (m:MedicationKnowledge {rule_id: "mk_nsaid_avoid"}), (d:Drug {name: "ibuprofen"}) CREATE (m)-[:CONCERNS]->(d);
MATCH (m:MedicationKnowledge {rule_id: "mk_anticholinergic_dementia"}), (d:Drug {name: "diphenhydramine"}) CREATE (m)-[:CONCERNS]->(d);
MATCH (m:MedicationKnowledge {rule_id: "mk_antipsychotic_dementia"}), (d:Drug {name: "risperidone"}) CREATE (m)-[:CONCERNS]->(d);
MATCH (m:MedicationKnowledge {rule_id: "mk_opioid_benzo_combo"}), (d:Drug {name: "oxycodone"}) CREATE (m)-[:CONCERNS]->(d);
MATCH (m:MedicationKnowledge {rule_id: "mk_opioid_benzo_combo"}), (d:Drug {name: "lorazepam"}) CREATE (m)-[:CONCERNS]->(d);
MATCH (m:MedicationKnowledge {rule_id: "mk_sulfonylurea_avoid"}), (d:Drug {name: "glyburide"}) CREATE (m)-[:CONCERNS]->(d);
MATCH (m:MedicationKnowledge {rule_id: "mk_digoxin_dose_limit"}), (d:Drug {name: "digoxin"}) CREATE (m)-[:CONCERNS]->(d);

// =========================================================
// 4. RESPONSE POLICY - severity 계층 확장 [증류]
// =========================================================
CREATE (:ResponseSelectionPolicy {policy_id: "resp_wellbeing_mild", axis: "WellBeing", min_severity: "MILD", problem_pattern: "웨어러블 미동기화, 복약 1회 누락, 저혈당 Level1(54~70mg/dL) 등 약한 신호", decision_basis: "urgency 낮음 - 로봇 확인을 우선하고 보호자 알림은 보류, 반복되면 다음 사이클에서 격상", rationale: "MILD 단계에서 바로 보호자를 부르면 오탐 부담이 커진다 - 로봇이 먼저 확인하고 CONCERN으로 격상될 때만 resp_wellbeing_concern으로 넘어간다.", source: "설계 판단 - 검수 필요"});
CREATE (:ResponseSelectionPolicy {policy_id: "resp_safety_mild", axis: "Safety", min_severity: "MILD", problem_pattern: "주간 문 장시간 개방 등 약한 안전신호", decision_basis: "urgency 낮음 - 로봇으로 우선 확인, 보호자 알림은 보류", rationale: "Safety도 MILD 단계(sf_r2 주간 문개방 등)까지 전부 보호자를 부르면 오탐 비용이 과하다 - 로봇 확인을 거치는 완충 단계를 둔다.", source: "설계 판단 - 검수 필요"});

MATCH (p:ResponseSelectionPolicy {policy_id: "resp_wellbeing_mild"}), (c:CheckItem {check_item_id: "ci:robot_dispatch"}) CREATE (p)-[:SELECTS {priority: 1}]->(c);
MATCH (p:ResponseSelectionPolicy {policy_id: "resp_safety_mild"}), (c:CheckItem {check_item_id: "ci:robot_dispatch"}) CREATE (p)-[:SELECTS {priority: 1}]->(c);

// 기존 관측 정책에 신규 CheckItem 편입 (priority 0 = 최상위로 삽입, 기존 번호 유지)
MATCH (p:ObservationSelectionPolicy {policy_id: "obs_safety_default"}), (c:CheckItem {check_item_id: "ci:fall_event"}) CREATE (p)-[:SELECTS {priority: 0}]->(c);
MATCH (p:ObservationSelectionPolicy {policy_id: "obs_wellbeing_default"}), (c:CheckItem {check_item_id: "ci:glucose"}) CREATE (p)-[:SELECTS {priority: 7}]->(c);

// =========================================================
// 5. PERSONA 확장 [persona] - synthetic, 실존 인물 아님 (1명 -> 3명)
// =========================================================

// --- Persona 2: 대조군 - is_vulnerable=false, 당뇨(설포닐우레아) ---
CREATE (:Subject {subject_id: "subj:park_malsun_002", name: "박말순(synthetic persona, 실존 인물 아님)", age: 78, is_vulnerable: false, created_at: "2026-09-03T00:00:00+09:00"});
CREATE (:Diagnosis {id: 3, condition_name: "제2형 당뇨병(Type 2 Diabetes Mellitus)", diagnosed_at: "2018-05-20"});
MATCH (s:Subject {subject_id: "subj:park_malsun_002"}), (d:Diagnosis {id: 3}) CREATE (s)-[:HAS_DIAGNOSIS]->(d);
MATCH (s:Subject {subject_id: "subj:park_malsun_002"}), (dr:Drug {name: "glyburide"}) CREATE (s)-[:TAKES {is_active: true}]->(dr);
CREATE (:VitalBaseline {id: 2, vital_type: "weight", baseline_value: 61.0, recorded_at: "2026-06-01T09:00:00+09:00"});
MATCH (s:Subject {subject_id: "subj:park_malsun_002"}), (v:VitalBaseline {id: 2}) CREATE (s)-[:HAS_BASELINE]->(v);
// is_vulnerable=false라 mr_cf1의 condition_value(18°C, 일반군) 분기가 걸린다 - persona1(취약군, 20°C 분기)과의 대조군.

// --- Persona 3: Safety축 중심 - 혈관성 치매, 항정신병약+항콜린제 병용, 낙상 이력 ---
CREATE (:Subject {subject_id: "subj:lee_gapsu_003", name: "이갑수(synthetic persona, 실존 인물 아님)", age: 85, is_vulnerable: true, created_at: "2026-09-03T00:00:00+09:00"});
CREATE (:Diagnosis {id: 4, condition_name: "혈관성 치매(Vascular Dementia)", diagnosed_at: "2023-01-15"});
MATCH (s:Subject {subject_id: "subj:lee_gapsu_003"}), (d:Diagnosis {id: 4}) CREATE (s)-[:HAS_DIAGNOSIS]->(d);
MATCH (s:Subject {subject_id: "subj:lee_gapsu_003"}), (dr:Drug {name: "risperidone"}) CREATE (s)-[:TAKES {is_active: true}]->(dr);
MATCH (s:Subject {subject_id: "subj:lee_gapsu_003"}), (dr:Drug {name: "diphenhydramine"}) CREATE (s)-[:TAKES {is_active: true}]->(dr);
CREATE (:FallHistory {id: 2, occurred_at: "2026-07-02T03:20:00+09:00", note: "야간에 방에서 낙상 - 골절 없음, 응급실 내원"});
MATCH (s:Subject {subject_id: "subj:lee_gapsu_003"}), (f:FallHistory {id: 2}) CREATE (s)-[:HAS_FALL_EVENT]->(f);
// risperidone -> mk_antipsychotic_dementia, diphenhydramine -> mk_anticholinergic_dementia 둘 다 실제로 걸리는
// 전형적 치매환자 다약제 문제 사례(치매 진단 + 항정신병약 + 항콜린제 동시 복용).

// =========================================================
// 검증
// =========================================================
MATCH (s:Subject) OPTIONAL MATCH (s)-[:TAKES]->(dr:Drug)<-[:CONCERNS]-(m:MedicationKnowledge)
WITH s, collect(DISTINCT dr.name) AS drugs, collect(DISTINCT m.rule_id) AS flagged_by
RETURN s.name, s.is_vulnerable, drugs, flagged_by ORDER BY s.subject_id;
MATCH (r:MonitoringRule) RETURN count(r) AS total_monitoring_rules;
MATCH (m:MedicationKnowledge) RETURN count(m) AS total_medication_knowledge;
