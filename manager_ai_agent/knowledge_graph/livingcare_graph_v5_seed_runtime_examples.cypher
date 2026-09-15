// ============================================================
// v5 seed + additions 위에 얹는 런타임 파이프라인 예시 (2026-09-03)
// livingcare_graph_v5_seed_additions.cypher 다음 실행.
//
// Action/Assessment/Intent/IntentCycle/ConditionRegistration/ConditionTriggerLog/
// IntentKnowledgeLookup/KnowledgeLookupTriggerLog는 원래 "시스템이 실제로 돌 때 남는 로그"라
// 미리 지어내지 않기로 했었다. 하지만 스키마 26개 테이블 중 이 8개가 전부 비어 있으면
// 구조를 검증할 방법이 없다는 지적에 따라, 이미 만든 persona 3명 + policy/rule을 실제로
// 엮은 예시 인스턴스 3개 시나리오를 채운다.
//
// 주의: 이건 실제 시스템 실행 로그가 아니라 "파이프라인이 이렇게 연결된다"는 걸 보여주는
// 손으로 짠 예시(worked example)다 - 숫자(체중 49.2kg 등)는 위 seed의 baseline/threshold와
// 앞뒤가 맞게 설계했을 뿐 실측값 아니다.
// ============================================================

// =========================================================
// 시나리오 A - WellBeing 즉시조치: 김옥순, 체중 급감 -> 로봇 확인 -> 보호자 알림
// =========================================================
CREATE (:Intent {intent_id: 1, raw_text: "오늘 옥순님 괜찮은지 확인해줘", subject_id: "subj:kim_oksun_001", target_domain: "WellBeing", needs_action: true, execution_timing: "immediate", needs_judgment: true, created_at: "2026-08-20T09:00:00+09:00"});

CREATE (:Action {action_id: 1, subject_id: "subj:kim_oksun_001", device_id: "cap:weightscale", check_item_id: "ci:weight", action_type: "OBSERVE", axis: "WellBeing", preempted: false, result_value: "49.2kg", requested_at: "2026-08-20T09:00:05+09:00", completed_at: "2026-08-20T09:00:20+09:00"});
CREATE (:Assessment {assessment_id: 1, action_id: 1, rule_id: "mr_wb6_weight_loss_frailty", subject_id: "subj:kim_oksun_001", used_baseline_id: 1, severity: "CONCERN", assessed_at: "2026-08-20T09:00:25+09:00"});
// baseline 52.0kg -> 49.2kg = -2.8kg(-5.4%), mr_wb6의 "1년 내 4.5kg 또는 5% 이상 감소" 기준(threshold_percent=5) 충족 -> CONCERN

CREATE (:IntentCycle {cycle_id: 1, intent_id: 1, sequence_no: 1, used_observation_policy_id: "obs_wellbeing_default", action_id: 1, assessment_id: 1, is_terminal: false, termination_reason: null});

CREATE (:Action {action_id: 2, subject_id: "subj:kim_oksun_001", check_item_id: "ci:call_caregiver", action_type: "ACTUATE", axis: "WellBeing", preempted: false, result_value: "caregiver_notified", requested_at: "2026-08-20T09:00:30+09:00", completed_at: "2026-08-20T09:00:35+09:00"});
CREATE (:IntentCycle {cycle_id: 2, intent_id: 1, sequence_no: 2, used_response_policy_id: "resp_wellbeing_concern", action_id: 2, is_terminal: true, termination_reason: "escalated_to_human", applied_termination_policy_id: "term_wellbeing"});

MATCH (i:Intent {intent_id: 1}), (s:Subject {subject_id: "subj:kim_oksun_001"}) CREATE (i)-[:FOR_SUBJECT]->(s);
MATCH (c:IntentCycle) WHERE c.cycle_id IN [1, 2] MATCH (i:Intent {intent_id: 1}) CREATE (c)-[:OF_INTENT]->(i);
MATCH (c:IntentCycle {cycle_id: 1}), (p:ObservationSelectionPolicy {policy_id: "obs_wellbeing_default"}) CREATE (c)-[:USED_OBSERVATION_POLICY]->(p);
MATCH (c:IntentCycle {cycle_id: 2}), (p:ResponseSelectionPolicy {policy_id: "resp_wellbeing_concern"}) CREATE (c)-[:USED_RESPONSE_POLICY]->(p);
MATCH (c:IntentCycle {cycle_id: 2}), (p:LoopTerminationPolicy {policy_id: "term_wellbeing"}) CREATE (c)-[:APPLIED_TERMINATION_POLICY]->(p);
MATCH (c:IntentCycle), (a:Action) WHERE c.action_id = a.action_id CREATE (c)-[:PRODUCED_ACTION]->(a);
MATCH (c:IntentCycle {cycle_id: 1}), (asmt:Assessment {assessment_id: 1}) CREATE (c)-[:PRODUCED_ASSESSMENT]->(asmt);
MATCH (a:Action) WHERE a.action_id IN [1, 2] MATCH (s:Subject {subject_id: "subj:kim_oksun_001"}) CREATE (a)-[:FOR_SUBJECT]->(s);
MATCH (a:Action {action_id: 1}), (d:Device {device_id: "cap:weightscale"}) CREATE (a)-[:USES_DEVICE]->(d);
MATCH (a:Action), (c:CheckItem) WHERE a.check_item_id = c.check_item_id CREATE (a)-[:TARGETS]->(c);
MATCH (asmt:Assessment {assessment_id: 1}), (a:Action {action_id: 1}) CREATE (asmt)-[:OF_ACTION]->(a);
MATCH (asmt:Assessment {assessment_id: 1}), (r:MonitoringRule {rule_id: "mr_wb6_weight_loss_frailty"}) CREATE (asmt)-[:APPLIED_RULE]->(r);
MATCH (asmt:Assessment {assessment_id: 1}), (s:Subject {subject_id: "subj:kim_oksun_001"}) CREATE (asmt)-[:FOR_SUBJECT]->(s);
MATCH (asmt:Assessment {assessment_id: 1}), (v:VitalBaseline {id: 1}) CREATE (asmt)-[:COMPARED_TO_BASELINE]->(v);

// =========================================================
// 시나리오 B - Safety 조건등록: 이갑수, 낙상 감지 조건 -> 실제 트리거 -> 즉시 대응
// =========================================================
CREATE (:Intent {intent_id: 2, raw_text: "갑수님 낙상 나면 바로 알려줘", subject_id: "subj:lee_gapsu_003", target_domain: "Safety", needs_action: true, execution_timing: "conditional", needs_judgment: false, created_at: "2026-07-01T10:00:00+09:00"});
CREATE (:ConditionRegistration {registration_id: 1, intent_id: 2, rule_id: "mr_sf5_fall_detected", needs_judgment_at_trigger: false, fixed_check_item_id: "ci:call_caregiver", is_active: true, created_at: "2026-07-01T10:00:00+09:00"});

// 실제 낙상 발생(persona3의 FallHistory id=2, 2026-07-02T03:20:00와 동일 시각) -> 조건 발동
CREATE (:Intent {intent_id: 3, raw_text: "[system] fall_event triggered for lee_gapsu_003", subject_id: "subj:lee_gapsu_003", target_domain: "Safety", needs_action: true, execution_timing: "immediate", needs_judgment: false, created_at: "2026-07-02T03:20:05+09:00"});
CREATE (:ConditionTriggerLog {id: 1, registration_id: 1, triggered_intent_id: 3, triggered_at: "2026-07-02T03:20:05+09:00"});

CREATE (:Action {action_id: 3, subject_id: "subj:lee_gapsu_003", device_id: "cap:fall_wearable", check_item_id: "ci:fall_event", action_type: "OBSERVE", axis: "Safety", preempted: false, result_value: "fall_detected=true", requested_at: "2026-07-02T03:20:00+09:00", completed_at: "2026-07-02T03:20:00+09:00"});
CREATE (:Assessment {assessment_id: 2, action_id: 3, rule_id: "mr_sf5_fall_detected", subject_id: "subj:lee_gapsu_003", severity: "CONCERN", assessed_at: "2026-07-02T03:20:03+09:00"});
CREATE (:IntentCycle {cycle_id: 3, intent_id: 3, sequence_no: 1, action_id: 3, assessment_id: 2, is_terminal: false});

CREATE (:Action {action_id: 4, subject_id: "subj:lee_gapsu_003", check_item_id: "ci:call_caregiver", action_type: "ACTUATE", axis: "Safety", preempted: false, result_value: "caregiver_notified_emergency", requested_at: "2026-07-02T03:20:06+09:00", completed_at: "2026-07-02T03:20:10+09:00"});
CREATE (:IntentCycle {cycle_id: 4, intent_id: 3, sequence_no: 2, used_response_policy_id: "resp_safety_concern", action_id: 4, is_terminal: true, termination_reason: "escalated_to_human", applied_termination_policy_id: "term_safety"});

MATCH (i:Intent) WHERE i.intent_id IN [2, 3] MATCH (s:Subject {subject_id: "subj:lee_gapsu_003"}) CREATE (i)-[:FOR_SUBJECT]->(s);
MATCH (cr:ConditionRegistration {registration_id: 1}), (i:Intent {intent_id: 2}) CREATE (cr)-[:OF_INTENT]->(i);
MATCH (cr:ConditionRegistration {registration_id: 1}), (r:MonitoringRule {rule_id: "mr_sf5_fall_detected"}) CREATE (cr)-[:WATCHES_RULE]->(r);
MATCH (cr:ConditionRegistration {registration_id: 1}), (c:CheckItem {check_item_id: "ci:call_caregiver"}) CREATE (cr)-[:FIXED_TARGET]->(c);
MATCH (log:ConditionTriggerLog {id: 1}), (cr:ConditionRegistration {registration_id: 1}) CREATE (log)-[:OF_REGISTRATION]->(cr);
MATCH (log:ConditionTriggerLog {id: 1}), (i:Intent {intent_id: 3}) CREATE (log)-[:TRIGGERED_INTENT]->(i);
MATCH (c:IntentCycle) WHERE c.cycle_id IN [3, 4] MATCH (i:Intent {intent_id: 3}) CREATE (c)-[:OF_INTENT]->(i);
MATCH (c:IntentCycle {cycle_id: 4}), (p:ResponseSelectionPolicy {policy_id: "resp_safety_concern"}) CREATE (c)-[:USED_RESPONSE_POLICY]->(p);
MATCH (c:IntentCycle {cycle_id: 4}), (p:LoopTerminationPolicy {policy_id: "term_safety"}) CREATE (c)-[:APPLIED_TERMINATION_POLICY]->(p);
MATCH (c:IntentCycle), (a:Action) WHERE c.action_id = a.action_id AND c.cycle_id IN [3, 4] CREATE (c)-[:PRODUCED_ACTION]->(a);
MATCH (c:IntentCycle {cycle_id: 3}), (asmt:Assessment {assessment_id: 2}) CREATE (c)-[:PRODUCED_ASSESSMENT]->(asmt);
MATCH (a:Action) WHERE a.action_id IN [3, 4] MATCH (s:Subject {subject_id: "subj:lee_gapsu_003"}) CREATE (a)-[:FOR_SUBJECT]->(s);
MATCH (a:Action {action_id: 3}), (d:Device {device_id: "cap:fall_wearable"}) CREATE (a)-[:USES_DEVICE]->(d);
MATCH (a:Action) WHERE a.action_id IN [3, 4] MATCH (c:CheckItem) WHERE a.check_item_id = c.check_item_id CREATE (a)-[:TARGETS]->(c);
MATCH (asmt:Assessment {assessment_id: 2}), (a:Action {action_id: 3}) CREATE (asmt)-[:OF_ACTION]->(a);
MATCH (asmt:Assessment {assessment_id: 2}), (r:MonitoringRule {rule_id: "mr_sf5_fall_detected"}) CREATE (asmt)-[:APPLIED_RULE]->(r);
MATCH (asmt:Assessment {assessment_id: 2}), (s:Subject {subject_id: "subj:lee_gapsu_003"}) CREATE (asmt)-[:FOR_SUBJECT]->(s);

// =========================================================
// 시나리오 C - 지식조회형: 박말순(설포닐우레아 안전성) + 김옥순(조건부 재조회, 기립성저혈압)
// =========================================================
CREATE (:Intent {intent_id: 4, raw_text: "글리부리드 계속 먹어도 되나요?", subject_id: "subj:park_malsun_002", target_domain: "WellBeing", needs_action: false, execution_timing: "immediate", needs_judgment: true, created_at: "2026-08-25T14:00:00+09:00"});
CREATE (:IntentKnowledgeLookup {id: 1, intent_id: 4, used_query_policy_id: "kq_medication_safety_by_diagnosis", medication_rule_id: "mk_sulfonylurea_avoid", referenced_diagnosis_id: 3, is_active: false, answer_summary: "글리부리드(설포닐우레아)는 2023 Beers Criteria상 1차/2차 치료로는 회피 권고 대상입니다. 저혈당 위험이 있어 담당의와 대체 약제 논의를 권장합니다."});

CREATE (:Intent {intent_id: 5, raw_text: "이뇨제 계속 먹어도 되는지, 혈압 문제 생기면 다시 알려줘", subject_id: "subj:kim_oksun_001", target_domain: "WellBeing", needs_action: false, execution_timing: "conditional", needs_judgment: true, created_at: "2026-08-10T07:00:00+09:00"});
CREATE (:IntentKnowledgeLookup {id: 2, intent_id: 5, used_query_policy_id: "kq_current_medication_interaction", medication_rule_id: "mk_diuretic_orthostatic", referenced_diagnosis_id: 2, trigger_rule_id: "mr_wb7_orthostatic_hypotension", is_active: true, answer_summary: "furosemide(이뇨제) 복용 중이며 기립성저혈압 위험 인자입니다. 기립혈압 측정에서 기준치 이상 하강이 감지되면 재조회합니다."});
CREATE (:KnowledgeLookupTriggerLog {id: 1, lookup_id: 2, triggered_at: "2026-08-10T07:15:00+09:00", answer_summary_at_trigger: "기립성저혈압 기준(수축기 20mmHg/이완기 10mmHg 하강) 충족 감지 - furosemide 재검토 필요, 담당의 상담 권장"});

MATCH (i:Intent) WHERE i.intent_id IN [4, 5] MATCH (kl:IntentKnowledgeLookup) WHERE (i.intent_id = 4 AND kl.id = 1) OR (i.intent_id = 5 AND kl.id = 2) CREATE (kl)-[:OF_INTENT]->(i);
MATCH (i:Intent {intent_id: 4}), (s:Subject {subject_id: "subj:park_malsun_002"}) CREATE (i)-[:FOR_SUBJECT]->(s);
MATCH (i:Intent {intent_id: 5}), (s:Subject {subject_id: "subj:kim_oksun_001"}) CREATE (i)-[:FOR_SUBJECT]->(s);
MATCH (kl:IntentKnowledgeLookup {id: 1}), (p:KnowledgeQueryPolicy {policy_id: "kq_medication_safety_by_diagnosis"}) CREATE (kl)-[:USED_QUERY_POLICY]->(p);
MATCH (kl:IntentKnowledgeLookup {id: 2}), (p:KnowledgeQueryPolicy {policy_id: "kq_current_medication_interaction"}) CREATE (kl)-[:USED_QUERY_POLICY]->(p);
MATCH (kl:IntentKnowledgeLookup {id: 1}), (m:MedicationKnowledge {rule_id: "mk_sulfonylurea_avoid"}) CREATE (kl)-[:ABOUT_MEDICATION_RULE]->(m);
MATCH (kl:IntentKnowledgeLookup {id: 2}), (m:MedicationKnowledge {rule_id: "mk_diuretic_orthostatic"}) CREATE (kl)-[:ABOUT_MEDICATION_RULE]->(m);
MATCH (kl:IntentKnowledgeLookup {id: 1}), (d:Diagnosis {id: 3}) CREATE (kl)-[:REFERENCED_DIAGNOSIS]->(d);
MATCH (kl:IntentKnowledgeLookup {id: 2}), (d:Diagnosis {id: 2}) CREATE (kl)-[:REFERENCED_DIAGNOSIS]->(d);
MATCH (kl:IntentKnowledgeLookup {id: 2}), (r:MonitoringRule {rule_id: "mr_wb7_orthostatic_hypotension"}) CREATE (kl)-[:TRIGGER_RULE]->(r);
MATCH (log:KnowledgeLookupTriggerLog {id: 1}), (kl:IntentKnowledgeLookup {id: 2}) CREATE (log)-[:OF_LOOKUP]->(kl);

// =========================================================
// 검증
// =========================================================
MATCH (n) WHERE any(l IN labels(n) WHERE l IN ["Intent","IntentCycle","ConditionRegistration","ConditionTriggerLog","IntentKnowledgeLookup","KnowledgeLookupTriggerLog","Action","Assessment"])
RETURN labels(n)[0] AS label, count(n) AS n ORDER BY label;
