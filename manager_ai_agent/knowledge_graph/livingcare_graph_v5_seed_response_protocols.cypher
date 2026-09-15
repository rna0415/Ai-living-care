// ============================================================
// v5 seed 위에 얹는 "감지 이후 대응" 지식 확장 (2026-09-04) [근거]
// livingcare_graph_v5_seed_comfort_setpoints.cypher 다음 실행.
//
// 온도 setpoint랑 같은 패턴 - 알람 임계값만 있고 "그다음 뭘 하나"가 없던 3곳을 채운다.
//   1. 저혈당 대응 프로토콜 (기존 규칙에 속성 추가)
//   2. 기립성저혈압 즉각 대응 (기존 규칙에 속성 추가)
//   3. 조명(밝기) - 규칙 자체가 없어서 신규 Device+CheckItem+MonitoringRule 추가
//      (cap:lightsensor는 실제 인벤토리에 없음 - 시연용으로 사용자 승인 하에 추가)
// ============================================================

// =========================================================
// 1. 저혈당 대응 프로토콜 - ADA Rule of 15
// =========================================================
MATCH (r:MonitoringRule {rule_id: "mr_wb12_hypoglycemia_level1"})
SET r.response_protocol = "15-15 규칙: 빠른흡수 탄수화물 15g 섭취(설탕 1큰술 / 과일주스·일반탄산음료 반컵 / 사탕 약 6개 / 대추 3알 중 택1) 후 15분 대기, 재측정. 70mg/dL 이하로 계속 나오면 15g을 반복 섭취.",
    r.response_protocol_source = "ADA Rule of 15 - American Diabetes Association 공식 저혈당 대응 지침(70mg/dL 이하에서 트리거)";

MATCH (r:MonitoringRule {rule_id: "mr_wb13_hypoglycemia_level2"})
SET r.response_protocol = "15-15 규칙 그대로 적용하되 Level 2(54mg/dL 미만)는 신경당결핍 증상 시작 구간이라 의식 확인을 함께 한다 - 의식이 없거나 삼킬 수 없는 상태면 15-15 규칙 대신 즉시 응급 대응(보호자/응급 호출)으로 전환.",
    r.response_protocol_source = "ADA Rule of 15 + Severe Hypoglycemia 가이드(의식저하 시 경구 섭취 대신 응급대응 전환 원칙)";

// =========================================================
// 2. 기립성저혈압 즉각 대응 - 근육 counter-maneuver
// =========================================================
MATCH (r:MonitoringRule {rule_id: "mr_wb7_orthostatic_hypotension"})
SET r.response_protocol = "즉시 앉거나 누워서(가능하면 다리를 올린 자세로) 혈압이 회복될 시간을 준다. 다리 꼬기·둔근 조이기·주먹 쥐기 같은 하지·둔부 근육수축 동작(physical counter-maneuver)으로 정맥환류를 늘리는 것이 1차 비약물적 대응이다. 만약 실신까지 갔다면 곧바로 일어나지 말고 물 470ml(16온스) 섭취 후 20분 이상 누운 자세를 유지한 뒤에 천천히 일어난다.",
    r.response_protocol_source = "Circulation: Arrhythmia and Electrophysiology - Orthostatic Hypotension Management review / physical countermaneuver 효능 문헌(PMID 8790259)";

// =========================================================
// 3. 조명(밝기) - 신규 Device/CheckItem/MonitoringRule [근거+증류]
//    cap:lightsensor는 시연용 가상 디바이스 - 실제 인벤토리에 없음(사용자 승인 하에 추가)
// =========================================================
CREATE (:Device {device_id: "cap:lightsensor", name: "AmbientLightSensor", status: "idle"});
CREATE (:CheckItem {check_item_id: "ci:ambient_light", name: "실내 조도 측정", default_action_type: "OBSERVE", sensor_type: "lux_meter"});
MATCH (d:Device {device_id: "cap:lightsensor"}), (c:CheckItem {check_item_id: "ci:ambient_light"}) CREATE (d)-[:MONITORS]->(c);

CREATE (:MonitoringRule {rule_id: "mr_cf5_low_light_living", check_item_id: "ci:ambient_light", axis: "Comfort", severity: "MILD", condition_value: "생활공간 50 lux 미만(주간/저녁 활동시간)", condition_qualifier: "illuminance_lux_below_living", threshold_lux: 50, uses_baseline: false, target_setpoint_lux: 150, setpoint_rationale: "IES(조명공학회) 거실 일반조명 권장 최소치는 50lux, 독서 등 작업시에는 150lux를 권장한다. 50lux 미만이면 조명을 켜서 150lux(작업 가능 수준)를 목표로 한다 - 노인은 시력저하로 젊은층보다 더 밝은 조도가 필요하다는 IES 노인 대상 별도 권고(Lighting and the Visual Environment for Older Adults)와도 부합.", rationale: "생활공간이 너무 어두우면 낙상·독서/식사 등 일상활동 어려움으로 이어진다. 50lux는 IES가 제시하는 거실 일반조명의 최소 기준.", source: "IES(Illuminating Engineering Society) Residential Recommended Lighting Levels / IES RP - Lighting and the Visual Environment for Older Adults and the Visually Impaired"});

CREATE (:MonitoringRule {rule_id: "mr_cf6_dark_hallway_night", check_item_id: "ci:ambient_light", axis: "Safety", severity: "CONCERN", condition_value: "야간 통로/복도 50 lux 미만", condition_qualifier: "illuminance_lux_below_hallway_night", threshold_lux: 50, time_context: "night", location: "hallway", uses_baseline: false, target_setpoint_lux: 100, setpoint_rationale: "IES 복도/통로 권장 조도는 바닥면 기준 약 100lux. 야간 낙상은 어두운 통로·화장실 이동 중 흔히 발생하므로, 50lux 미만 감지시 100lux를 목표로 조명을 켠다 - 다만 수면 방해를 피하기 위해 과도하게 밝히지 않고 100lux 선에서 멈춘다(300lux 이상 밝은 백색광은 야간 안전조명 권고와 배치됨).", rationale: "노인 낙상의 상당수가 야간 화장실·통로 이동 중 발생한다. Safety축으로 분류한 이유는 어두운 통로 자체가 낙상 위험 요인이라 Comfort(쾌적함)보다 안전 문제에 가깝기 때문.", source: "IES Residential Recommended Lighting Levels(복도 100lux) / 야간 낙상방지 조명 관행(저조도 웜톤 야간등, 최대 300lux 이내 권고)"});

MATCH (r:MonitoringRule) WHERE r.rule_id IN ["mr_cf5_low_light_living", "mr_cf6_dark_hallway_night"]
MATCH (c:CheckItem {check_item_id: r.check_item_id})
CREATE (r)-[:EVALUATES]->(c);

// 관측 정책에 편입 + 대응 정책에 조명 액추에이터 연결(이건 실제 액추에이터가 있어서 냉방과 달리 진짜 조치 가능)
MATCH (p:ObservationSelectionPolicy {policy_id: "obs_comfort_default"}), (c:CheckItem {check_item_id: "ci:ambient_light"}) CREATE (p)-[:SELECTS {priority: 2}]->(c);
MATCH (p:ResponseSelectionPolicy {policy_id: "resp_comfort_mild"}), (c:CheckItem {check_item_id: "ci:light_control"}) CREATE (p)-[:SELECTS {priority: 1}]->(c);
// 기존 call_caregiver는 priority 1로 만들어졌었는데(냉난방 액추에이터가 없어 그게 유일한 대응이던 시절 흔적),
// 조명은 실제 액추에이터가 있으니 우선순위를 넘겨준다 - call_caregiver는 2순위(조명으로도 해결 안 될 때)로 재조정.
MATCH (p:ResponseSelectionPolicy {policy_id: "resp_comfort_mild"})-[s:SELECTS]->(c:CheckItem {check_item_id: "ci:call_caregiver"}) SET s.priority = 2;

// =========================================================
// 검증
// =========================================================
MATCH (r:MonitoringRule) WHERE r.response_protocol IS NOT NULL RETURN r.rule_id, r.response_protocol_source;
MATCH (r:MonitoringRule) WHERE r.target_setpoint_lux IS NOT NULL RETURN r.rule_id, r.condition_value, r.target_setpoint_lux;
