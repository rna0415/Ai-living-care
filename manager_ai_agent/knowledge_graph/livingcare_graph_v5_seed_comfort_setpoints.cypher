// ============================================================
// v5 seed 위에 얹는 Comfort 온도 setpoint 지식 (2026-09-04) [근거]
// livingcare_graph_v5_seed_runtime_examples.cypher 다음 실행.
//
// mr_cf1/cf3/cf4는 "언제 문제인지"(알람 임계값)만 갖고 있었다 - "너무 더워"에
// 대응해서 로봇/액추에이터가 실제로 몇 도로 맞춰야 하는지(setpoint)는 없었음.
// LLM이 갖고 있지 않은 지식(실내 온열쾌적 연구 기반 목표 온도)이라 신규 조사.
//
// target_setpoint_celsius: 이 규칙이 발동해 대응(response)을 실행할 때 목표로 삼을 온도.
// vulnerable_target_setpoint_celsius: is_vulnerable=true 대상 별도 목표(있을 때만).
// ============================================================

MATCH (r:MonitoringRule {rule_id: "mr_cf4_temp_too_high"})
SET r.target_setpoint_celsius = 25,
    r.setpoint_rationale = "28°C 초과로 CONCERN이 뜨면 25°C를 목표로 냉방한다. ASHRAE 55 냉방모드 쾌적범위(23.5~25.5°C)의 상단에 가깝게 잡아 과냉방(에너지 낭비, 노인 저체온 역효과)을 피하면서도, WHO/영국 Heatwave Plan이 폭염기 취약군 '쿨룸' 상한으로 쓰는 26°C보다는 확실히 낮게 유지한다.",
    r.setpoint_source = "ASHRAE 55(냉방모드 23.5~25.5°C) / WHO Housing and Health Guidelines·영국 Heatwave Plan(취약군 쿨룸 상한 26°C) / 노인 대상 연구 - 22~26°C 구간은 심혈관 부담·세포스트레스 변화 미미, 26°C 초과부터 증가 및 장점막 보호기능 손상 보고";

MATCH (r:MonitoringRule {rule_id: "mr_cf1_temp_too_low"})
SET r.target_setpoint_celsius = 21,
    r.vulnerable_target_setpoint_celsius = 22,
    r.setpoint_rationale = "18°C 미만(일반군) 또는 20°C 미만(취약군)으로 CONCERN이 뜨면, 일반군은 21°C·취약군은 22°C를 목표로 난방한다. WHO 권장 최소치(일반 18°C·취약군 20°C)보다 1~2°C 여유를 둬서, 난방이 딱 최소기준에 걸치는 대신 안정적으로 최소기준 위에 머물게 한다. ASHRAE 55 난방모드 쾌적범위(20.5~24.5°C) 하단과도 정합적이다.", r.setpoint_source = "WHO Housing and Health Guidelines(일반 18°C·취약군 20°C 최소권장) / ASHRAE 55 난방모드 쾌적범위(20.5~24.5°C)";

MATCH (r:MonitoringRule {rule_id: "mr_cf3_temp_too_low_night"})
SET r.target_setpoint_celsius = 20,
    r.setpoint_rationale = "야간 18°C 미만으로 CONCERN이 뜨면 20°C를 목표로 난방한다. 주간 목표(21°C)보다 1°C 낮게 잡은 이유는 수면 중에는 약간 서늘한 온도가 정상 범위로 다뤄지기 때문 - 다만 England Cold Weather Plan이 강조하는 야간 최소 유지선(18°C)보다는 확실히 위에 머물게 한다.", r.setpoint_source = "England Cold Weather Plan(2016, 야간 최소 18°C 유지 강조) / ASHRAE 55 난방모드 하단(20.5°C) 근방으로 보수적 설정";

// =========================================================
// 검증
// =========================================================
MATCH (r:MonitoringRule) WHERE r.target_setpoint_celsius IS NOT NULL
RETURN r.rule_id, r.condition_value, r.target_setpoint_celsius, r.vulnerable_target_setpoint_celsius ORDER BY r.rule_id;
