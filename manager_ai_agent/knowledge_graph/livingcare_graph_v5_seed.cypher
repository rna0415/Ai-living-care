// ============================================================
// LivingCare 지식그래프 v5 - Instance Seed Data
// livingcare_graph_v5.cypher(제약+인덱스) 다음에 실행한다.
//
// 데이터 출처 3분류 (2026-09-03 대화에서 합의):
//   [근거] 실제 임상/업계 문헌 인용 필요 - monitoring_rule, medication_knowledge,
//          observation/response_selection_policy. 대부분 v3(livingcare_graph_v3*.cypher)에서
//          이미 조사된 근거를 v5 스키마로 포팅했고, medication_knowledge는 이번에 신규 조사.
//   [증류] 시스템 설계 판단으로 충분 - loop_termination_policy, knowledge_query_policy,
//          check_item 카탈로그. 문헌 인용 없음, Claude 초안이므로 검수 필요.
//   [persona] subject 계열 - 실제 pilot 대상자 없어 synthetic persona 1명 생성.
//             실존 인물 아님.
//
// MonitoringRule 필드 설계: v5 dbml의 condition_value/condition_qualifier(varchar)는
// 사람이 읽는 요약이고, v3부터 policy_generation/rule_evaluator.py가 실제로 읽는
// threshold_kg/threshold_percent/threshold_hours 등 타입 있는 속성을 그대로 병기했다
// (Neo4j는 스키마 강제가 없어 dbml 필드 외 속성 추가 가능 - rule_evaluator.py 호환 유지 목적).
//
// Device는 v2/v3(8개) + wb_bathroom_meds 추가분(4개) + icope 추가(로봇 Function만, 신규 Device 없음)를
// 합쳐 총 13개(backup 온도센서 포함)를 그대로 재사용한다 - "기존 8개"보다 범위가 넓은데,
// wb_r5~r9 근거 규칙들이 이 4개 장치(weightscale/bloodpressuremonitor/bathroommotionsensor/
// pilldispenser) 없이는 CheckItem에 못 붙어서 확장했다. 사용자 재확인 필요하면 알려줄 것.
// ============================================================

// =========================================================
// 0. DEVICE (기존 인벤토리 재사용 - v2/v3 + wb_bathroom_meds 추가분)
// =========================================================
CREATE (:Device {device_id: "cap:doorswitch", name: "DoorSwitch", status: "idle"});
CREATE (:Device {device_id: "cap:lightswitch", name: "LightSwitch", status: "idle"});
CREATE (:Device {device_id: "cap:meter", name: "Meter", status: "idle"});
CREATE (:Device {device_id: "cap:smokesensor", name: "SmokeSensor", status: "idle"});
CREATE (:Device {device_id: "cap:temperaturesensor", name: "TemperatureSensor", status: "idle"});
CREATE (:Device {device_id: "cap:temperaturesensor_backup", name: "TemperatureSensorBackup", status: "idle"});
CREATE (:Device {device_id: "cap:motionsensor", name: "MotionSensor", status: "idle"});
CREATE (:Device {device_id: "cap:wearable_vitals", name: "WearableVitalsMonitor", status: "idle"});
CREATE (:Device {device_id: "cap:limo_robot_agent", name: "LimoRobot", status: "idle"});
CREATE (:Device {device_id: "cap:weightscale", name: "WeightScale", status: "idle"});
CREATE (:Device {device_id: "cap:bloodpressuremonitor", name: "BloodPressureMonitor", status: "idle"});
CREATE (:Device {device_id: "cap:bathroommotionsensor", name: "BathroomMotionSensor", status: "idle"});
CREATE (:Device {device_id: "cap:pilldispenser", name: "SmartPillDispenser", status: "idle"});

// =========================================================
// 1. CHECK ITEM 카탈로그 [증류]
// =========================================================
CREATE (:CheckItem {check_item_id: "ci:motion", name: "실내 활동 감지", default_action_type: "OBSERVE", sensor_type: "PIR"});
CREATE (:CheckItem {check_item_id: "ci:heartrate", name: "웨어러블 심박/동기화 감지", default_action_type: "OBSERVE", sensor_type: "wearable_ppg"});
CREATE (:CheckItem {check_item_id: "ci:weight", name: "체중 측정", default_action_type: "OBSERVE", sensor_type: "load_cell"});
CREATE (:CheckItem {check_item_id: "ci:blood_pressure", name: "혈압 측정(기립성 포함)", default_action_type: "OBSERVE", sensor_type: "oscillometric_cuff"});
CREATE (:CheckItem {check_item_id: "ci:bathroom_occupancy", name: "욕실 체류시간 감지", default_action_type: "OBSERVE", sensor_type: "PIR"});
CREATE (:CheckItem {check_item_id: "ci:medication_dispensing", name: "복약 디스펜싱 확인", default_action_type: "OBSERVE", sensor_type: "smart_dispenser"});
CREATE (:CheckItem {check_item_id: "ci:locomotion_timing", name: "이동성 측정(5회 앉았다 일어서기)", default_action_type: "OBSERVE", sensor_type: "robot_timer"});
CREATE (:CheckItem {check_item_id: "ci:smoke", name: "연기 감지", default_action_type: "OBSERVE", sensor_type: "photoelectric"});
CREATE (:CheckItem {check_item_id: "ci:door_status", name: "현관문 개폐 상태 감지", default_action_type: "OBSERVE", sensor_type: "reed_switch"});
CREATE (:CheckItem {check_item_id: "ci:temperature", name: "실내온도 측정", default_action_type: "OBSERVE", sensor_type: "thermistor"});
CREATE (:CheckItem {check_item_id: "ci:person_presence", name: "재실자 상태 확인(로봇 순찰)", default_action_type: "OBSERVE", sensor_type: "camera_lidar"});
CREATE (:CheckItem {check_item_id: "ci:energy_usage", name: "에너지 사용량 측정", default_action_type: "OBSERVE", sensor_type: "smart_meter"});
CREATE (:CheckItem {check_item_id: "ci:light_control", name: "조명 on/off 제어", default_action_type: "ACTUATE", sensor_type: "relay"});
CREATE (:CheckItem {check_item_id: "ci:robot_dispatch", name: "로봇 출동/이동", default_action_type: "ACTUATE", sensor_type: "navigation"});
CREATE (:CheckItem {check_item_id: "ci:call_caregiver", name: "보호자/케어기버 알림", default_action_type: "ACTUATE", sensor_type: "notification_api"});

// --- Device -[:MONITORS]-> CheckItem ---
// limo_robot_agent는 person_presence를 기본으로 등록하되, locomotion_timing/robot_dispatch도
// 같은 로봇이 수행 가능 - Action.device_id/check_item_id가 각각 독립 필드라 device 쪽 1개
// 등록만으로도 Action에서 다른 check_item을 같이 타겟팅할 수 있다(스키마 제약 없음).
MATCH (d:Device {device_id: "cap:doorswitch"}), (c:CheckItem {check_item_id: "ci:door_status"}) CREATE (d)-[:MONITORS]->(c);
MATCH (d:Device {device_id: "cap:lightswitch"}), (c:CheckItem {check_item_id: "ci:light_control"}) CREATE (d)-[:MONITORS]->(c);
MATCH (d:Device {device_id: "cap:meter"}), (c:CheckItem {check_item_id: "ci:energy_usage"}) CREATE (d)-[:MONITORS]->(c);
MATCH (d:Device {device_id: "cap:smokesensor"}), (c:CheckItem {check_item_id: "ci:smoke"}) CREATE (d)-[:MONITORS]->(c);
MATCH (d:Device {device_id: "cap:temperaturesensor"}), (c:CheckItem {check_item_id: "ci:temperature"}) CREATE (d)-[:MONITORS]->(c);
MATCH (d:Device {device_id: "cap:temperaturesensor_backup"}), (c:CheckItem {check_item_id: "ci:temperature"}) CREATE (d)-[:MONITORS]->(c);
MATCH (d:Device {device_id: "cap:motionsensor"}), (c:CheckItem {check_item_id: "ci:motion"}) CREATE (d)-[:MONITORS]->(c);
MATCH (d:Device {device_id: "cap:wearable_vitals"}), (c:CheckItem {check_item_id: "ci:heartrate"}) CREATE (d)-[:MONITORS]->(c);
MATCH (d:Device {device_id: "cap:limo_robot_agent"}), (c:CheckItem {check_item_id: "ci:person_presence"}) CREATE (d)-[:MONITORS]->(c);
MATCH (d:Device {device_id: "cap:weightscale"}), (c:CheckItem {check_item_id: "ci:weight"}) CREATE (d)-[:MONITORS]->(c);
MATCH (d:Device {device_id: "cap:bloodpressuremonitor"}), (c:CheckItem {check_item_id: "ci:blood_pressure"}) CREATE (d)-[:MONITORS]->(c);
MATCH (d:Device {device_id: "cap:bathroommotionsensor"}), (c:CheckItem {check_item_id: "ci:bathroom_occupancy"}) CREATE (d)-[:MONITORS]->(c);
MATCH (d:Device {device_id: "cap:pilldispenser"}), (c:CheckItem {check_item_id: "ci:medication_dispensing"}) CREATE (d)-[:MONITORS]->(c);
// ci:call_caregiver는 물리 디바이스 없음(알림 채널) - MONITORS 관계 없이 정책에서만 참조

// =========================================================
// 2. MONITORING RULE [근거] - v3 AxisKnowledge를 v5 스키마로 포팅 + 신규 조사
// =========================================================
CREATE (:MonitoringRule {rule_id: "mr_wb1_no_motion_day", check_item_id: "ci:motion", axis: "WellBeing", severity: "CONCERN", condition_value: "4시간 이상 무동작(주간)", condition_qualifier: "no_motion_hours_day_gte", threshold_hours: 4, time_context: "day", uses_baseline: false, rationale: "주간에 4시간 이상 활동 신호가 없으면 우려 상황으로 본다. 상용 텔레케어 시스템의 12~24시간 기준보다 보수적으로 잡은 이유는, 낙상 등 응급상황 발견이 늦어질수록 예후가 나빠지기 때문.", source: "Red Alert Telecare 상용 기준(12~24h) 대비 보수적으로 재설정"});
CREATE (:MonitoringRule {rule_id: "mr_wb2_no_motion_night", check_item_id: "ci:motion", axis: "WellBeing", severity: "INFO", condition_value: "8시간 이상 무동작(야간)", condition_qualifier: "no_motion_hours_night_gte", threshold_hours: 8, time_context: "night", uses_baseline: false, rationale: "야간에는 수면 중이라 무동작이 정상이다. 8시간까지는 우려로 취급하지 않는다 - 지나치게 민감하면 불필요한 로봇 출동/알림으로 수면을 방해한다.", source: "특허 US10226177 - 낮/밤 별도 임계값 설계 관행"});
CREATE (:MonitoringRule {rule_id: "mr_wb3_night_kitchen_visit", check_item_id: "ci:motion", axis: "WellBeing", severity: "INFO", condition_value: "야간 주방 방문 감지", condition_qualifier: "kitchen_night_visit", time_context: "night", location: "kitchen", uses_baseline: false, rationale: "야간 주방 방문은 그 자체로 위험 신호는 아니지만, 수면장애나 야간 저혈당의 간접 지표로 기록해둘 가치가 있다. 당장 조치하지 않고 패턴으로만 축적.", source: "StackCare 특허(US12340890) - 야간 주방 방문 모니터링 관행"});
CREATE (:MonitoringRule {rule_id: "mr_wb4_wearable_no_sync", check_item_id: "ci:heartrate", axis: "WellBeing", severity: "MILD", condition_value: "6시간 이상 미동기화", condition_qualifier: "no_sync_hours_gte", threshold_hours: 6, uses_baseline: false, rationale: "웨어러블 동기화 자체는 착용/배터리 문제일 수 있어 단독으로는 약한 신호로만 취급한다. 다른 규칙과 동시 위반시에만 confidence를 낮춘다(오탐 방지).", source: "설계팀 자체 정책 - 웨어러블은 단독 신뢰도가 낮은 센서로 취급"});
CREATE (:MonitoringRule {rule_id: "mr_wb5_weight_gain_hf", check_item_id: "ci:weight", axis: "WellBeing", severity: "CONCERN", condition_value: "3일 내 2kg 이상 증가", condition_qualifier: "weight_gain_3day_gte", threshold_kg: 2, threshold_days: 3, direction: "gain", uses_baseline: false, rationale: "3일 이내 2kg 이상 체중이 늘면 심부전 악화의 대표적 조기경고 신호로 본다. 체액 저류가 증상보다 먼저 체중에 나타나 숨참·부종 전 단계에서 잡아낼 수 있는 몇 안 되는 선행 지표다.", source: "heartfailurematters.org 임상 권고 / Chaudhry et al. 2007, Circulation - Patterns of Weight Change Preceding Hospitalization for Heart Failure"});
CREATE (:MonitoringRule {rule_id: "mr_wb6_weight_loss_frailty", check_item_id: "ci:weight", axis: "WellBeing", severity: "CONCERN", condition_value: "1년 내 4.5kg 또는 체중 5% 이상 감소", condition_qualifier: "weight_loss_365day_kg_or_pct", threshold_kg: 4.5, threshold_percent: 5, threshold_days: 365, direction: "loss", uses_baseline: true, rationale: "1년 이내 4.5kg 이상 또는 체중의 5% 이상이 의도치 않게 줄면 노쇠(frailty) 표준 임상기준의 핵심 지표로 본다. 노쇠는 그 자체가 진단명이 아니라 낙상·입원·사망 위험이 급격히 오르는 상태 전이 신호라 조기 포착이 중요하다.", source: "Fried Frailty Phenotype 기준(Cardiovascular Health Study) - UK DRIE Study가 재확인"});
CREATE (:MonitoringRule {rule_id: "mr_wb7_orthostatic_hypotension", check_item_id: "ci:blood_pressure", axis: "WellBeing", severity: "CONCERN", condition_value: "기립 3분 내 수축기 20mmHg 또는 이완기 10mmHg 이상 하강", condition_qualifier: "postural_bp_drop", threshold_systolic_drop_mmhg: 20, threshold_diastolic_drop_mmhg: 10, measurement_window_minutes: 3, uses_baseline: false, rationale: "누운/앉은 자세에서 일어선 뒤 3분 이내 수축기 20mmHg 이상 또는 이완기 10mmHg 이상 떨어지면 기립성저혈압으로 본다(국제 합의 진단기준). 지역사회 노인의 20%가 겪을 만큼 흔하고 낙상·심혈관질환·인지저하·사망 위험과 직결된다.", source: "American Autonomic Society/AAN 합의 진단기준 - AAFP 2022 Practical Approach 리뷰(PMID 35029940)"});
CREATE (:MonitoringRule {rule_id: "mr_wb8_medication_missed_dose", check_item_id: "ci:medication_dispensing", axis: "WellBeing", severity: "MILD", condition_value: "예정시각 2시간 초과 미복용", condition_qualifier: "missed_dose_hours_gte", threshold_hours: 2, uses_baseline: false, rationale: "예정 시각으로부터 2시간 이내 복용하면 준수(adherence)로 보는 스마트 필박스 연구의 정의를 그대로 가져왔다. 1회 누락은 아직 약한 신호(깜빡함·일정 변경 등)로 취급한다.", source: "A Pilot Study to Evaluate the Acceptability of Using a Smart Pillbox (PMC6843901)"});
CREATE (:MonitoringRule {rule_id: "mr_wb9_medication_repeated_miss", check_item_id: "ci:medication_dispensing", axis: "WellBeing", severity: "CONCERN", condition_value: "2회 연속 누락", condition_qualifier: "consecutive_missed_doses_gte", threshold_count: 2, uses_baseline: false, rationale: "2회 연속 누락이면 단순 실수를 넘어 만성질환 관리 자체가 무너지고 있다는 신호로 격상한다.", source: "설계팀 정책(스마트 필박스 usability/acceptance 문헌 기반 보수적 설정)"});
CREATE (:MonitoringRule {rule_id: "mr_wb10_locomotion_chair_rise", check_item_id: "ci:locomotion_timing", axis: "WellBeing", severity: "CONCERN", condition_value: "5회 앉았다 일어서기 14초 이상", condition_qualifier: "chair_rise_5rep_seconds_gte", threshold_seconds: 14, uses_baseline: false, rationale: "5회 연속 의자 앉았다 일어서기 시간이 14초 이상이면 이동성 저하로 본다. WHO ICOPE Step1 스크리닝 도구가 locomotion 도메인 판정에 쓰는 공식 cutoff.", source: "WHO ICOPE Screening Tool - Validation of the ICOPE Screening Tool: Focus on the Chair Rise Test to Assess Locomotion (PMC8680757)"});
CREATE (:MonitoringRule {rule_id: "mr_wb11_icope_weight_loss_3kg_90d", check_item_id: "ci:weight", axis: "WellBeing", severity: "CONCERN", condition_value: "3개월 내 3kg 이상 감소", condition_qualifier: "weight_loss_90day_kg_gte", threshold_kg: 3, threshold_days: 90, direction: "loss", uses_baseline: true, rationale: "최근 3개월 이내 3kg 이상 의도치 않게 체중이 줄면 vitality(영양) 저하로 본다. WHO ICOPE Step1 스크리닝 공식 질문을 채택 - wb_r6(1년/4.5kg)보다 관측창이 짧아 더 빨리 경고를 낼 수 있다.", source: "WHO ICOPE Handbook Step 1 스크리닝(vitality domain)"});
CREATE (:MonitoringRule {rule_id: "mr_sf1_smoke_detected", check_item_id: "ci:smoke", axis: "Safety", severity: "CONCERN", condition_value: "연기 감지", condition_qualifier: "smoke_detected_immediate", uses_baseline: false, rationale: "연기 감지는 시간 지연 없이 즉시 우려 상황으로 처리한다. 화재는 확산 속도가 빨라 지연 자체가 위험을 키운다.", source: "화재경보기 업계 표준 관행(즉시 경보 원칙)"});
CREATE (:MonitoringRule {rule_id: "mr_sf2_door_open_day", check_item_id: "ci:door_status", axis: "Safety", severity: "MILD", condition_value: "주간 30분 이상 개방", condition_qualifier: "door_open_minutes_day_gte", threshold_minutes: 30, time_context: "day", uses_baseline: false, rationale: "주간에 현관문이 30분 이상 열려있으면 약한 우려로 취급한다. 낮에는 외출/배달/환기 등 정상적 이유로 문을 오래 열어두는 경우가 흔해 오탐 위험이 크다.", source: "ecobee Smart Security 'open reminder' 기본값(5분) 대비 보수적으로 완화"});
CREATE (:MonitoringRule {rule_id: "mr_sf3_door_open_night", check_item_id: "ci:door_status", axis: "Safety", severity: "CONCERN", condition_value: "야간 5분 이상 개방", condition_qualifier: "door_open_minutes_night_gte", threshold_minutes: 5, time_context: "night", uses_baseline: false, rationale: "야간에 현관문이 5분 이상 열려있으면 우려 상황으로 본다. 야간은 정상적으로 문을 열어둘 이유가 거의 없어 주간의 1/6 수준으로 민감하게 설정.", source: "YoLink 등 보안 목적 도어센서의 민감 설정 관행(1~2분) 참고"});
CREATE (:MonitoringRule {rule_id: "mr_sf4_bathroom_prolonged_occupancy", check_item_id: "ci:bathroom_occupancy", axis: "Safety", severity: "CONCERN", condition_value: "20분 이상 체류", condition_qualifier: "occupancy_minutes_gte", threshold_minutes: 20, uses_baseline: false, rationale: "욕실은 노인 낙상의 35.7%가 발생하는 단일 최빈발 장소이고, 미국 병원 낙상의 38~47%가 화장실 관련이다. 정확한 분 단위 임계값을 못박은 논문은 없어 의료시설 모니터링 실무 관행(20~30분)의 하한을 보수적으로 채택했다.", source: "Homecare Mag - The Bathroom Dilemma(낙상 통계) / 의료시설 체류시간 모니터링 관행"});
CREATE (:MonitoringRule {rule_id: "mr_cf1_temp_too_low", check_item_id: "ci:temperature", axis: "Comfort", severity: "CONCERN", condition_value: "18°C 미만", vulnerable_condition_value: "20°C 미만", condition_qualifier: "temp_celsius_below", threshold_celsius: 18, direction: "below", uses_baseline: false, rationale: "실내 온도가 18°C 미만이면 일반 인구 기준 우려 상황으로 본다. WHO는 취약군(노인 등)에는 20°C를 권장하므로 is_vulnerable=true 대상은 vulnerable_condition_value(20°C)를 대신 적용한다 - 18~20°C 구간은 일반 인구에겐 mild 수준이지만 취약군에겐 즉시 concern이다.", source: "WHO Housing and Health Guidelines (2018) - 최소 18°C 권장, 취약군 20°C 권장"});
CREATE (:MonitoringRule {rule_id: "mr_cf3_temp_too_low_night", check_item_id: "ci:temperature", axis: "Comfort", severity: "CONCERN", condition_value: "야간 18°C 미만", condition_qualifier: "temp_celsius_below_night", threshold_celsius: 18, time_context: "night", direction: "below", uses_baseline: false, rationale: "야간에는 18°C 미만이면 즉시 concern으로 처리한다. 야간 저체온 노출이 혈압 상승 등 심혈관계에 더 크게 영향을 미친다는 근거가 있어 야간 유지의 중요성을 별도로 강조한다.", source: "England Cold Weather Plan (2016) - 야간 18°C 유지 강조"});
CREATE (:MonitoringRule {rule_id: "mr_cf4_temp_too_high", check_item_id: "ci:temperature", axis: "Comfort", severity: "CONCERN", condition_value: "28°C 초과", condition_qualifier: "temp_celsius_above", threshold_celsius: 28, direction: "above", uses_baseline: false, rationale: "실내 온도가 28°C를 초과하면 우려 상황으로 본다. 노인 실내온도 상한 관련 임상연구가 26°C를 다루나 확정된 공식 가이드라인은 아니라서 2°C 여유를 둔 28°C를 임계값으로 사용한다.", source: "노인 실내온도 상한 관련 임상연구(26°C 기준)를 보수적으로 조정"});

MATCH (r:MonitoringRule) WHERE r.check_item_id IS NOT NULL
MATCH (c:CheckItem {check_item_id: r.check_item_id})
CREATE (r)-[:EVALUATES]->(c);

// =========================================================
// 3. MEDICATION KNOWLEDGE [근거] - 신규 조사 (Beers Criteria / STOPP-START)
// =========================================================
CREATE (:MedicationKnowledge {rule_id: "mk_benzodiazepine_avoid", drug_class: "Benzodiazepine", recommendation: "avoid", condition: "모든 노인 환자 - 발작/REM수면행동장애/금단증상/중증불안/시술마취 등 예외적 경우만 허용", rationale: "노인은 벤조디아제핀 민감도가 높고 장시간 작용 약물의 대사가 느려, 인지장애·섬망·낙상·골절·교통사고 위험이 전 연령대보다 크게 높아진다. 진정작용이 졸림/반응지연/균형장애를 유발해 고관절 골절과 낙상으로 직결된다.", source: "AGS 2023 Updated Beers Criteria for Potentially Inappropriate Medication Use in Older Adults (J Am Geriatr Soc, PMID 37139824)"});
CREATE (:MedicationKnowledge {rule_id: "mk_ppi_long_term", drug_class: "Proton Pump Inhibitor", recommendation: "avoid_scheduled_use_over_8_weeks", condition: "고위험 적응증(예: 바레트식도, 만성 NSAID 병용) 없이 8주 이상 정기 복용", rationale: "8주 이상 정기적 PPI 복용은 골소실·골절, Clostridioides difficile 감염 위험을 높인다. 장기 복용과 비타민 B12·칼슘 결핍의 연관성도 일관되게 보고된다.", source: "AGS Beers Criteria(2019 개정, 2023판에서도 유지) - 고위험군 아니면 8주 초과 정기 사용 회피 권고"});
CREATE (:MedicationKnowledge {rule_id: "mk_diuretic_orthostatic", drug_class: "Diuretic (loop/thiazide)", recommendation: "monitor_orthostatic_bp", condition: "기립성저혈압 병력 또는 낙상 이력이 있는 환자", rationale: "이뇨제는 혈량저하와 기립성저혈압을 유발해 낙상·실신 위험 인자가 된다. STOPPFall Delphi 연구에서 이뇨제가 기립성저혈압 위험이 가장 높은 약물군으로 확인되었고, 야뇨·탈수·저나트륨혈증 등과 함께 감량(deprescribing) 고려 대상으로 명시된다.", source: "STOPP/START v2 Fall-Risk-Increasing Drugs(FRIDs) 섹션 / STOPPFall Delphi Study(Age and Ageing, PMC 6043386)"});
CREATE (:MedicationKnowledge {rule_id: "mk_acei_start_hf", drug_class: "ACE inhibitor", recommendation: "start_if_missing", condition: "수축기 심부전 또는 관상동맥질환이 있고 금기(고칼륨혈증, 혈관부종 병력 등)가 없는 환자", rationale: "수축기 심부전 환자에서 ACE 억제제 누락은 START 기준으로 검토한 처방 누락(PPO) 중 가장 흔한 항목으로 확인됐다 - 적절한 적응증이 있는데도 처방되지 않은 과소치료 사례.", source: "STOPP/START criteria version 3 (European Geriatric Medicine, PMC10447584) - START 기준 PPO 최다 항목"});

CREATE (:Drug {name: "lorazepam"});
CREATE (:Drug {name: "omeprazole"});
CREATE (:Drug {name: "furosemide"});
CREATE (:Drug {name: "lisinopril"});

MATCH (m:MedicationKnowledge {rule_id: "mk_benzodiazepine_avoid"}), (d:Drug {name: "lorazepam"}) CREATE (m)-[:CONCERNS]->(d);
MATCH (m:MedicationKnowledge {rule_id: "mk_ppi_long_term"}), (d:Drug {name: "omeprazole"}) CREATE (m)-[:CONCERNS]->(d);
MATCH (m:MedicationKnowledge {rule_id: "mk_diuretic_orthostatic"}), (d:Drug {name: "furosemide"}) CREATE (m)-[:CONCERNS]->(d);
MATCH (m:MedicationKnowledge {rule_id: "mk_acei_start_hf"}), (d:Drug {name: "lisinopril"}) CREATE (m)-[:CONCERNS]->(d);

// =========================================================
// 4. OBSERVATION / RESPONSE SELECTION POLICY [근거]
// =========================================================
CREATE (:ObservationSelectionPolicy {policy_id: "obs_wellbeing_default", axis: "WellBeing", goal_pattern: "평소 어떻게 지내는지/괜찮은지 확인", decision_basis: "recent_condition + history - WHO ICOPE Step1 스크리닝 도메인(locomotion, vitality) 기반", rationale: "ICOPE의 6개 intrinsic capacity 도메인 중 현재 센서로 구현 가능한 locomotion(이동성)·vitality(영양)를 우선 관측 대상으로 삼는다. Cognition/Psychological/Vision/Hearing은 자가보고가 필요해 이번 범위에서 제외(knowledge_graph/CLAUDE.md에 기록된 기존 결정과 동일).", source: "WHO ICOPE Handbook, Fried Frailty Phenotype"});
CREATE (:ObservationSelectionPolicy {policy_id: "obs_safety_default", axis: "Safety", goal_pattern: "위험한 상황인지 확인", decision_basis: "vulnerability + immediate_risk - CDC STEADI 낙상위험 평가 도메인 + 욕실 낙상 통계", rationale: "화재(연기)·문 개방·욕실 체류를 우선 관측한다. 욕실은 노인 낙상의 35.7%가 발생하는 단일 최빈발 장소라 Safety축에서 최우선 순위로 둔다.", source: "CDC STEADI, Homecare Mag 낙상 통계"});
CREATE (:ObservationSelectionPolicy {policy_id: "obs_comfort_default", axis: "Comfort", goal_pattern: "환경이 쾌적한지 확인", decision_basis: "environmental_threshold - WHO 주거환경 온도 가이드라인", rationale: "로봇 출동이 필요 없는 센서 전용 축(tier=4)이라 온도를 상시 관측한다.", source: "WHO Housing and Health Guidelines (2018)"});

CREATE (:ResponseSelectionPolicy {policy_id: "resp_wellbeing_concern", axis: "WellBeing", min_severity: "CONCERN", problem_pattern: "장시간 무동작/체중 급변/이동성 저하 등 WellBeing 이상 신호", decision_basis: "urgency + resource_availability - 로봇 출동 가능 여부를 우선 확인 후 필요시 보호자 알림", rationale: "WellBeing은 tier=1(결정론) 축이라 즉시 로봇을 보내 상태를 확인하고, 확인 결과가 여전히 concern이면 보호자에게 알린다.", source: "knowledge_graph/CLAUDE.md tier 시스템(2026-08-24) - WellBeing=tier1"});
CREATE (:ResponseSelectionPolicy {policy_id: "resp_safety_concern", axis: "Safety", min_severity: "CONCERN", problem_pattern: "연기 감지/야간 장시간 문 개방/욕실 장시간 체류", decision_basis: "urgency - Safety는 즉시 대응이 최우선, 로봇 확인보다 보호자 알림을 먼저 발송", rationale: "Safety는 tier=1이면서 오탐의 대가보다 미대응의 대가가 훨씬 큰 축이라, 로봇 출동과 별개로 보호자 알림을 동시에 발송한다.", source: "knowledge_graph/CLAUDE.md tier 시스템 - Safety=tier1, 로봇 출동 축"});
CREATE (:ResponseSelectionPolicy {policy_id: "resp_comfort_mild", axis: "Comfort", min_severity: "MILD", problem_pattern: "실내 온도 이상(너무 낮음/높음)", decision_basis: "resource_availability + time_of_day - 로봇 없는 센서 전용 축, 자동 제어 장치가 없어 현재는 보호자 알림만 가능", rationale: "Comfort는 tier=4(에이전트 루프)지만 온도조절 액추에이터가 인벤토리에 없어 실제 대응은 보호자 알림뿐이다 - 냉난방 제어 장치 추가가 필요한 알려진 한계.", source: "knowledge_graph/CLAUDE.md tier 시스템 - Comfort=tier4"});

MATCH (p:ObservationSelectionPolicy {policy_id: "obs_wellbeing_default"}), (c:CheckItem {check_item_id: "ci:motion"}) CREATE (p)-[:SELECTS {priority: 1}]->(c);
MATCH (p:ObservationSelectionPolicy {policy_id: "obs_wellbeing_default"}), (c:CheckItem {check_item_id: "ci:locomotion_timing"}) CREATE (p)-[:SELECTS {priority: 2}]->(c);
MATCH (p:ObservationSelectionPolicy {policy_id: "obs_wellbeing_default"}), (c:CheckItem {check_item_id: "ci:weight"}) CREATE (p)-[:SELECTS {priority: 3}]->(c);
MATCH (p:ObservationSelectionPolicy {policy_id: "obs_wellbeing_default"}), (c:CheckItem {check_item_id: "ci:heartrate"}) CREATE (p)-[:SELECTS {priority: 4}]->(c);
MATCH (p:ObservationSelectionPolicy {policy_id: "obs_wellbeing_default"}), (c:CheckItem {check_item_id: "ci:medication_dispensing"}) CREATE (p)-[:SELECTS {priority: 5}]->(c);
MATCH (p:ObservationSelectionPolicy {policy_id: "obs_wellbeing_default"}), (c:CheckItem {check_item_id: "ci:person_presence"}) CREATE (p)-[:SELECTS {priority: 6}]->(c);

MATCH (p:ObservationSelectionPolicy {policy_id: "obs_safety_default"}), (c:CheckItem {check_item_id: "ci:smoke"}) CREATE (p)-[:SELECTS {priority: 1}]->(c);
MATCH (p:ObservationSelectionPolicy {policy_id: "obs_safety_default"}), (c:CheckItem {check_item_id: "ci:door_status"}) CREATE (p)-[:SELECTS {priority: 2}]->(c);
MATCH (p:ObservationSelectionPolicy {policy_id: "obs_safety_default"}), (c:CheckItem {check_item_id: "ci:bathroom_occupancy"}) CREATE (p)-[:SELECTS {priority: 3}]->(c);
MATCH (p:ObservationSelectionPolicy {policy_id: "obs_safety_default"}), (c:CheckItem {check_item_id: "ci:motion"}) CREATE (p)-[:SELECTS {priority: 4}]->(c);

MATCH (p:ObservationSelectionPolicy {policy_id: "obs_comfort_default"}), (c:CheckItem {check_item_id: "ci:temperature"}) CREATE (p)-[:SELECTS {priority: 1}]->(c);

MATCH (p:ResponseSelectionPolicy {policy_id: "resp_wellbeing_concern"}), (c:CheckItem {check_item_id: "ci:robot_dispatch"}) CREATE (p)-[:SELECTS {priority: 1}]->(c);
MATCH (p:ResponseSelectionPolicy {policy_id: "resp_wellbeing_concern"}), (c:CheckItem {check_item_id: "ci:call_caregiver"}) CREATE (p)-[:SELECTS {priority: 2}]->(c);

MATCH (p:ResponseSelectionPolicy {policy_id: "resp_safety_concern"}), (c:CheckItem {check_item_id: "ci:call_caregiver"}) CREATE (p)-[:SELECTS {priority: 1}]->(c);
MATCH (p:ResponseSelectionPolicy {policy_id: "resp_safety_concern"}), (c:CheckItem {check_item_id: "ci:robot_dispatch"}) CREATE (p)-[:SELECTS {priority: 2}]->(c);

MATCH (p:ResponseSelectionPolicy {policy_id: "resp_comfort_mild"}), (c:CheckItem {check_item_id: "ci:call_caregiver"}) CREATE (p)-[:SELECTS {priority: 1}]->(c);

// =========================================================
// 5. LOOP TERMINATION POLICY [증류] - 기존 tier 설계를 그대로 반영
// =========================================================
CREATE (:LoopTerminationPolicy {policy_id: "term_safety", axis: "Safety", max_cycles: 1, escalation_check_item_id: "ci:call_caregiver", rationale: "Safety는 tier=1(결정론, 재량 없음) 축이라 재시도 없이 1회 확인 후 바로 사람에게 넘긴다 - 오판 여지를 최소화하는 게 재시도로 시간을 버는 것보다 우선.", source: "knowledge_graph/CLAUDE.md tier 시스템(2026-08-24) 설계 판단 - 문헌 인용 아님, 검수 필요"});
CREATE (:LoopTerminationPolicy {policy_id: "term_wellbeing", axis: "WellBeing", max_cycles: 2, escalation_check_item_id: "ci:call_caregiver", rationale: "WellBeing도 tier=1이지만 Safety보다 급성 위험도가 낮아(무동작/체중변화 등은 서서히 진행) 1번 더 재확인할 여유를 둔다.", source: "설계 판단 - 검수 필요"});
CREATE (:LoopTerminationPolicy {policy_id: "term_comfort", axis: "Comfort", max_cycles: 5, escalation_check_item_id: "ci:call_caregiver", rationale: "Comfort는 tier=4(에이전트 루프 파일럿) 축으로 로봇 출동 없는 센서 전용이라 재시도 비용이 낮다 - 재량을 가장 많이 허용.", source: "knowledge_graph/CLAUDE.md tier 시스템 - Comfort=tier4"});

MATCH (p:LoopTerminationPolicy), (c:CheckItem {check_item_id: p.escalation_check_item_id}) CREATE (p)-[:ESCALATES_VIA]->(c);

// =========================================================
// 6. KNOWLEDGE QUERY POLICY [증류]
// =========================================================
CREATE (:KnowledgeQueryPolicy {policy_id: "kq_medication_safety_by_diagnosis", goal_pattern: "이 약 먹어도 되는지 / 복용해도 되는지", query_scope: "by_drug_name + by_diagnosis - STOPP/START처럼 진단명별 금기·주의 사항까지 함께 확인", rationale: "약물 단독 정보만으로는 불충분하고, 환자의 진단명과 교차 확인해야 STOPP류 판단이 가능하다.", source: "설계 판단 - 검수 필요"});
CREATE (:KnowledgeQueryPolicy {policy_id: "kq_current_medication_interaction", goal_pattern: "지금 먹는 약이랑 같이 먹어도 되는지", query_scope: "by_current_medications - subject_medication의 활성 약물 목록 전체와 상호작용 확인", rationale: "신약 하나만 볼 게 아니라 현재 복용 중인 약 전체와의 상호작용을 봐야 한다.", source: "설계 판단 - 검수 필요"});
CREATE (:KnowledgeQueryPolicy {policy_id: "kq_diagnosis_general_care", goal_pattern: "이 질환에 대해 뭘 조심해야 하는지", query_scope: "by_diagnosis - 특정 약물 질의가 아닌 진단명 기반 일반 주의사항 조회", rationale: "약물명이 특정되지 않은 일반 질의는 진단명 기준으로 medication_knowledge.condition을 넓게 매칭한다.", source: "설계 판단 - 검수 필요"});

// =========================================================
// 7. SUBJECT PERSONA [persona] - synthetic, 실존 인물 아님
// =========================================================
CREATE (:Subject {subject_id: "subj:kim_oksun_001", name: "김옥순(synthetic persona, 실존 인물 아님)", age: 82, is_vulnerable: true, created_at: "2026-09-03T00:00:00+09:00"});

CREATE (:Diagnosis {id: 1, condition_name: "고혈압(Hypertension)", diagnosed_at: "2015-03-10"});
CREATE (:Diagnosis {id: 2, condition_name: "수축기 심부전(HFrEF)", diagnosed_at: "2022-11-02"});
MATCH (s:Subject {subject_id: "subj:kim_oksun_001"}), (d:Diagnosis {id: 1}) CREATE (s)-[:HAS_DIAGNOSIS]->(d);
MATCH (s:Subject {subject_id: "subj:kim_oksun_001"}), (d:Diagnosis {id: 2}) CREATE (s)-[:HAS_DIAGNOSIS]->(d);

// 심부전 치료제(furosemide)로 mk_diuretic_orthostatic 근거와 연결, 수면제(lorazepam)로 mk_benzodiazepine_avoid와 연결
MATCH (s:Subject {subject_id: "subj:kim_oksun_001"}), (dr:Drug {name: "furosemide"}) CREATE (s)-[:TAKES {is_active: true}]->(dr);
MATCH (s:Subject {subject_id: "subj:kim_oksun_001"}), (dr:Drug {name: "lorazepam"}) CREATE (s)-[:TAKES {is_active: true}]->(dr);

CREATE (:VitalBaseline {id: 1, vital_type: "weight", baseline_value: 52.0, recorded_at: "2026-06-01T09:00:00+09:00"});
MATCH (s:Subject {subject_id: "subj:kim_oksun_001"}), (v:VitalBaseline {id: 1}) CREATE (s)-[:HAS_BASELINE]->(v);

CREATE (:FallHistory {id: 1, occurred_at: "2026-03-14T22:10:00+09:00", note: "욕실에서 미끄러짐, 경미한 타박상 - 병원 이송 없음"});
MATCH (s:Subject {subject_id: "subj:kim_oksun_001"}), (f:FallHistory {id: 1}) CREATE (s)-[:HAS_FALL_EVENT]->(f);

// =========================================================
// 검증
// =========================================================
MATCH (r:MonitoringRule) RETURN r.axis, count(r) AS rules ORDER BY r.axis;
MATCH (c:CheckItem) RETURN c.check_item_id, count{(c)<-[:MONITORS]-()} AS devices, count{(c)<-[:EVALUATES]-()} AS rules_evaluating, count{(c)<-[:SELECTS]-()} AS policies_selecting ORDER BY c.check_item_id;
MATCH (s:Subject)-[:TAKES]->(dr:Drug)<-[:CONCERNS]-(m:MedicationKnowledge) RETURN s.name, dr.name, m.rule_id, m.recommendation;
