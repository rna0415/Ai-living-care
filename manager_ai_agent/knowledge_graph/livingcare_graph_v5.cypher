// ============================================================
// LivingCare 지식그래프 v5 - Selection Policy 3분리 스키마
// 원본: Desktop/데이터베이스/livingcare_schema_v5.dbml (관계형 개념 스키마)
// v2/v3(Axis/Device/Function/State/AxisKnowledge)를 대체한다.
//
// 관계형 -> 그래프 매핑 원칙
//   - PK가 있는 엔티티 테이블         -> 노드 (Label, {xxx_id} UNIQUE 제약)
//   - 속성 없는 순수 N:M 조인 테이블  -> 관계 (예: observation_policy_checkitem -> SELECTS)
//   - FK 컬럼 하나짜리 1:N            -> 관계 (예: subject_diagnosis.subject_id -> HAS_DIAGNOSIS)
//   - subject_medication / medication_knowledge_drug는 둘 다 (엔티티)-[:REL]->(Drug)
//     형태로 합쳐, drug_name으로 자연히 겹치는 Drug 노드를 공유한다
//     (예: 이 약을 복용 중인 환자 <-> 이 약에 대한 medication_knowledge 조회가 그래프 순회로 연결됨)
//
// 아직 인스턴스 데이터 없음 - v2/v3와 달리 이 파일은 스키마(제약+인덱스)만 정의한다.
// 실제 subject/check_item/policy/rule 데이터는 별도로 적재한다.
// ============================================================

// =========================================================
// 1. SUBJECT 계열
// =========================================================
CREATE CONSTRAINT subject_id_unique IF NOT EXISTS FOR (s:Subject) REQUIRE s.subject_id IS UNIQUE;
CREATE CONSTRAINT diagnosis_id_unique IF NOT EXISTS FOR (d:Diagnosis) REQUIRE d.id IS UNIQUE;
CREATE CONSTRAINT vital_baseline_id_unique IF NOT EXISTS FOR (v:VitalBaseline) REQUIRE v.id IS UNIQUE;
CREATE CONSTRAINT fall_history_id_unique IF NOT EXISTS FOR (f:FallHistory) REQUIRE f.id IS UNIQUE;
CREATE CONSTRAINT drug_name_unique IF NOT EXISTS FOR (d:Drug) REQUIRE d.name IS UNIQUE;

// (Subject)-[:HAS_DIAGNOSIS]->(Diagnosis)                 // subject_diagnosis
// (Subject)-[:TAKES {is_active}]->(Drug)                  // subject_medication
// (Subject)-[:HAS_BASELINE]->(VitalBaseline)               // vital_baseline
// (Subject)-[:HAS_FALL_EVENT]->(FallHistory)               // fall_history

// =========================================================
// 2. CHECK ITEM / DEVICE
// =========================================================
CREATE CONSTRAINT check_item_id_unique IF NOT EXISTS FOR (c:CheckItem) REQUIRE c.check_item_id IS UNIQUE;
CREATE CONSTRAINT device_id_unique IF NOT EXISTS FOR (d:Device) REQUIRE d.device_id IS UNIQUE;

// (Device)-[:MONITORS]->(CheckItem)                        // device.check_item_id
// (Device)-[:EXECUTING]->(Action)                           // device.current_action_id, status='busy'일 때만 존재

// =========================================================
// 3. SELECTION POLICY 3분리 + LOOP TERMINATION
// =========================================================
CREATE CONSTRAINT obs_policy_id_unique IF NOT EXISTS FOR (p:ObservationSelectionPolicy) REQUIRE p.policy_id IS UNIQUE;
CREATE CONSTRAINT resp_policy_id_unique IF NOT EXISTS FOR (p:ResponseSelectionPolicy) REQUIRE p.policy_id IS UNIQUE;
CREATE CONSTRAINT term_policy_id_unique IF NOT EXISTS FOR (p:LoopTerminationPolicy) REQUIRE p.policy_id IS UNIQUE;
CREATE CONSTRAINT query_policy_id_unique IF NOT EXISTS FOR (p:KnowledgeQueryPolicy) REQUIRE p.policy_id IS UNIQUE;

CREATE INDEX obs_policy_axis IF NOT EXISTS FOR (p:ObservationSelectionPolicy) ON (p.axis);
CREATE INDEX resp_policy_axis_severity IF NOT EXISTS FOR (p:ResponseSelectionPolicy) ON (p.axis, p.min_severity);
CREATE INDEX term_policy_axis IF NOT EXISTS FOR (p:LoopTerminationPolicy) ON (p.axis);

// (ObservationSelectionPolicy)-[:SELECTS {priority}]->(CheckItem)   // observation_policy_checkitem
// (ResponseSelectionPolicy)-[:SELECTS {priority}]->(CheckItem)      // response_policy_checkitem
// (LoopTerminationPolicy)-[:ESCALATES_VIA]->(CheckItem)             // escalation_check_item_id

// =========================================================
// 4. MONITORING RULE
// =========================================================
CREATE CONSTRAINT monitoring_rule_id_unique IF NOT EXISTS FOR (r:MonitoringRule) REQUIRE r.rule_id IS UNIQUE;
CREATE INDEX monitoring_rule_axis_severity IF NOT EXISTS FOR (r:MonitoringRule) ON (r.axis, r.severity);

// (MonitoringRule)-[:EVALUATES]->(CheckItem)                        // check_item_id

// =========================================================
// 5. MEDICATION KNOWLEDGE
// =========================================================
CREATE CONSTRAINT med_knowledge_rule_id_unique IF NOT EXISTS FOR (m:MedicationKnowledge) REQUIRE m.rule_id IS UNIQUE;

// (MedicationKnowledge)-[:CONCERNS]->(Drug)                         // medication_knowledge_drug

// =========================================================
// 6. ACTION / ASSESSMENT
// =========================================================
CREATE CONSTRAINT action_id_unique IF NOT EXISTS FOR (a:Action) REQUIRE a.action_id IS UNIQUE;
CREATE CONSTRAINT assessment_id_unique IF NOT EXISTS FOR (a:Assessment) REQUIRE a.assessment_id IS UNIQUE;
CREATE INDEX action_axis IF NOT EXISTS FOR (a:Action) ON (a.axis);

// (Action)-[:FOR_SUBJECT]->(Subject)
// (Action)-[:USES_DEVICE]->(Device)
// (Action)-[:TARGETS]->(CheckItem)
// (Assessment)-[:OF_ACTION]->(Action)
// (Assessment)-[:APPLIED_RULE]->(MonitoringRule)
// (Assessment)-[:FOR_SUBJECT]->(Subject)
// (Assessment)-[:COMPARED_TO_BASELINE]->(VitalBaseline)             // used_baseline_id, rule.uses_baseline=true일 때만

// =========================================================
// 7. INTENT + 실행 파이프라인
// =========================================================
CREATE CONSTRAINT intent_id_unique IF NOT EXISTS FOR (i:Intent) REQUIRE i.intent_id IS UNIQUE;
CREATE CONSTRAINT intent_cycle_id_unique IF NOT EXISTS FOR (c:IntentCycle) REQUIRE c.cycle_id IS UNIQUE;
CREATE CONSTRAINT condition_registration_id_unique IF NOT EXISTS FOR (r:ConditionRegistration) REQUIRE r.registration_id IS UNIQUE;
CREATE CONSTRAINT condition_trigger_log_id_unique IF NOT EXISTS FOR (l:ConditionTriggerLog) REQUIRE l.id IS UNIQUE;
CREATE CONSTRAINT intent_knowledge_lookup_id_unique IF NOT EXISTS FOR (l:IntentKnowledgeLookup) REQUIRE l.id IS UNIQUE;
CREATE CONSTRAINT knowledge_lookup_trigger_log_id_unique IF NOT EXISTS FOR (l:KnowledgeLookupTriggerLog) REQUIRE l.id IS UNIQUE;

CREATE INDEX intent_target_domain IF NOT EXISTS FOR (i:Intent) ON (i.target_domain);

// --- A=true, T=immediate (intent_cycle) ---
// (Intent)-[:FOR_SUBJECT]->(Subject)
// (IntentCycle)-[:OF_INTENT]->(Intent)
// (IntentCycle)-[:USED_OBSERVATION_POLICY]->(ObservationSelectionPolicy)
// (IntentCycle)-[:USED_RESPONSE_POLICY]->(ResponseSelectionPolicy)
// (IntentCycle)-[:PRODUCED_ACTION]->(Action)
// (IntentCycle)-[:PRODUCED_ASSESSMENT]->(Assessment)
// (IntentCycle)-[:APPLIED_TERMINATION_POLICY]->(LoopTerminationPolicy)   // max_iterations_reached / escalated_to_human일 때만

// --- A=true, T=conditional (condition_registration) ---
// (ConditionRegistration)-[:OF_INTENT]->(Intent)
// (ConditionRegistration)-[:WATCHES_RULE]->(MonitoringRule)
// (ConditionRegistration)-[:FIXED_TARGET]->(CheckItem)                   // needs_judgment_at_trigger=false일 때만
// (ConditionTriggerLog)-[:OF_REGISTRATION]->(ConditionRegistration)
// (ConditionTriggerLog)-[:TRIGGERED_INTENT]->(Intent)                    // 새 intent 생성, 이후 IntentCycle 흐름 재사용

// --- A=false (지식조회형, intent_knowledge_lookup) ---
// (IntentKnowledgeLookup)-[:OF_INTENT]->(Intent)
// (IntentKnowledgeLookup)-[:USED_QUERY_POLICY]->(KnowledgeQueryPolicy)   // needs_judgment=false면 없음
// (IntentKnowledgeLookup)-[:ABOUT_MEDICATION_RULE]->(MedicationKnowledge)
// (IntentKnowledgeLookup)-[:REFERENCED_DIAGNOSIS]->(Diagnosis)
// (IntentKnowledgeLookup)-[:TRIGGER_RULE]->(MonitoringRule)              // execution_timing=conditional일 때만
// (KnowledgeLookupTriggerLog)-[:OF_LOOKUP]->(IntentKnowledgeLookup)

// =========================================================
// 검증 (제약/인덱스 생성 확인용 - 데이터 적재 후 실행)
// =========================================================
SHOW CONSTRAINTS;
SHOW INDEXES;
