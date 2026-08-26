# API 스펙 — MCP tool

> **HTTP API는 없다.** 이 시스템의 유일한 외부 인터페이스는 MCP tool이다.
> 정본: `worker_ai_agent/limo-MCP/MCP_server/MCP_server.py` (`@mcp.tool()` 데코레이터)
> 이 문서를 고치면 반드시 코드와 대조한다. 반대도 마찬가지다.

## 접속

| 항목 | 값 |
|---|---|
| 트랜스포트 | **stdio** (`mcp.run(transport="stdio")`) |
| 서버 이름 | `limo-worker` |
| SDK | `from mcp.server.mcpserver import Image, MCPServer` — **mcp ≥ 2.0 전용** |
| 기동 | 클라이언트가 `MCP_server.py`를 서브프로세스로 실행 (`StdioServerParameters`) |

> ⚠️ **mcp 1.x에는 `mcp.server.mcpserver` 모듈이 없다** (1.x는 `mcp.server.fastmcp`).
> `requirements.txt`에 하한이 없어 1.x가 잡히면 서버가 import 단계에서 죽는다.
> 하한 고정 필요: `mcp[cli]>=2.0,<3`.

## tool 19종 (현재 노출된 전부)

### `plan_and_navigate(x: float, y: float, frame: str = "map", yaw_deg: float = None) -> dict`

목표 좌표까지 경로를 계획하고 이동을 시작한다. **비동기** — 즉시 반환하고 `get_status`로 폴링한다.

```json
{"started": true}
{"started": false, "reason": "invalid goal"}
```

- `_plan_fn`은 목표를 **검증만** 하고 그대로 웨이포인트 1개로 돌려준다. 실제 전역 경로계획은
  Nav2의 `NavigateToPose`가 내부적으로 수행한다.
- ⚠️ 웨이포인트가 1개이므로 `prev_xy`가 없어 **`yaw_deg`를 생략하면 항상 0도(맵 +x축)를 보고 정지**한다.
- ⚠️ 시그니처가 `float = None`이라 생성 스키마가 `{"type":"number","default":null}`인 자기모순이다.
  LLM이 `yaw_deg: null`을 명시하면 ValidationError로 호출 전체가 실패한다. `Optional[float]`로 수정 필요.

### `navigate_waypoints(waypoints: list) -> dict`

웨이포인트 리스트를 순서대로 이동한다. **순찰 시나리오의 진입점.**

```python
[{"x": 1.0, "y": 0.0, "frame": "map", "yaw_deg": 90.0}, ...]   # frame·yaw_deg 선택
```

- `yaw_deg` 생략 시 이전 → 현재 방향으로 자동 계산. 첫 점은 0.0.
- ⚠️ **`list` bare 어노테이션이라 아이템 검증이 전혀 없다.** `[{"x": 1, "y": 0}]`처럼 **정수**를 주면
  rosidl의 `assert isinstance(value, float)`가 시퀀스 스레드 안에서 터지고, 그 스레드에 `try/except`가
  없어 **조용히 죽는다.** 이후 `get_status`는 영원히 진행 중으로 보고한다. → pydantic 모델로 교체 필요.

### `get_status() -> dict`

```json
{
  "status": "navigating",
  "last_goal": {"x": 1.0, "y": 0.0, "frame": "map", "yaw_deg": 0.0},
  "sequence_progress": {"index": 0, "total": 1},
  "sequence_result": {"completed": 1, "total": 1, "interrupted": false}
}
```

**`status` 열거값 6종**: `idle` · `navigating` · `rejected` · `cancelled` · `succeeded` · `failed`

> ⚠️ `Scenarios/send_goal.py`는 `succeeded`/`failed` **2종만** 탈출 조건으로 검사한다.
> Nav2 미기동(`idle`) · goal 거부(`rejected`) · 120초 초과(`navigating` 유지) 시 **에러 없이 무한 루프**한다.

### `get_camera_snapshot() -> list | dict`

최신 프레임을 JPEG으로 반환한다.

```python
[ '{"frame_id": "f_47", "stamp": 1234.5}', Image(data=..., format="jpeg") ]   # 성공
{"image": None, "reason": "no frame available yet"}                           # 실패
```

- 최대 512px로 리사이즈(`CROP_MAX_PX`), JPEG quality 85.
- ⚠️ **성공과 실패의 반환 타입이 다르다**(list vs dict). `capture_and_detect.py`가 실패를 감지하지 못하고
  파일을 안 만든 채 exit 0으로 끝난다.
- ⚠️ **프레임 신선도 검사가 없다.** 카메라가 죽어도 마지막 프레임을 무기한 "최신"으로 반환한다.

### `detect_objects(min_conf: float = 0.4) -> dict`

최신 프레임에서 YOLO 검출.

```json
{"frame_id": "f_47", "detections": [{"class": "person", "conf": 0.87, "bbox": [x1,y1,x2,y2]}]}
{"detections": [], "reason": "no frame available yet"}
```

- 모델 `yolov8n.pt`, 첫 호출 전 서버 기동 시 워밍업.
- ⚠️ 신선도 검사 없음 — **카메라가 죽어도 옛 프레임에서 사람을 계속 검출**한다.
  돌봄 로봇에서 가장 위험한 무음 실패 경로.

### `cancel() -> dict`

진행 중인 목표/시퀀스를 취소한다.

```json
{"cancelled": true}
{"cancelled": false, "reason": "no active goal"}
```

- ⚠️ **goal 수락이 5초를 넘으면 `_goal_handle`이 비어 있어 취소할 수 없다.** 그런데 Nav2는 목표를
  수락했으므로 **로봇은 실제로 달린다.** RTF 0.04 환경에서 상시 발생하는 경로다. **안전 결함.**

### `resolve_location(name: str) -> dict`

장소·디바이스 이름을 좌표로 해소한다. `manager_ai_agent/knowledge_graph/`의 Phase 0 JSON
룩업(`entities.json`, D-6)을 Worker Reasoning이 **직접 import**해서 쓴다 — 정식 아키텍처상
IF-1(Manager AI Core 경유)이어야 하지만 Manager AI Core의 IF-1 adapter가 아직 없어 임시로 이렇게
배선했다(근거: `docs/decisions/2026-08-10-worker-side-kg-lookup-phase0.md`).

```json
{"resolved": true, "name": "dining_area", "x": 8.10, "y": 1.71, "frame": "map", "yaw_deg": 0.0}
{"resolved": false, "name": "air_conditioner", "reason": "unknown location: 'air_conditioner'"}
```

- `entities.json`에 등록된 것은 지금 **3건**이다: `dining_area`·`upper_left_room`(실측 좌표),
  `air_conditioner`(`AirconditionerB`가 속한 구역의 접근점 — `tools/limo-patrol-viz/WORLD.md` §2,
  가구 좌표 자체는 아님). 그 외 이름은 좌표를 지어내지 않고 `resolved: false`를 돌려준다 —
  침실의 `AirconditionerA`가 그 예다(맵이 침실을 미탐색이라 등록 보류).
- `Scenarios/turn_on_air_conditioner.json`의 첫 스텝이 이 tool을 호출한다.

### `pathplanning(x: float, y: float, frame: str = "map") -> dict`

A*로 마지막 위치(`ActionModule.last_sim_pose`, 첫 호출 시 스폰 `(3.5, 1.0)`)에서 목표 좌표까지
경로를 계산한다. **Nav2도 Gazebo도 필요 없다** — `Reasonings.astar_plan`이
`tools/limo-patrol-viz/maps/map.pgm` 점유격자에서 직접 계산한다 (`patrol_sim.py`와 같은
알고리즘·같은 맵). `frame`은 `"map"`만 지원.

```json
{"waypoints": [{"x": 3.5, "y": 1.0}, {"x": 3.14, "y": 0.9}, ..., {"x": -0.8, "y": -3.05}]}
{"waypoints": null, "reason": "no path found"}
```

### `moving_path(waypoints: list) -> dict`

`pathplanning`이 계산한 웨이포인트를 따라 이동한다. **실물 로봇·Gazebo·Nav2 없이 운동학만
소프트웨어로 적분**한다(`patrol_sim.py`의 `advance_to`와 같은 모델, 실시간 페이싱 — 회전
0.50 rad/s, 직진 0.22 m/s). 비동기 — 즉시 `{"started": true}`를 반환하고 `get_path_status`로
폴링한다. `LimoGatewayNode.viz`(`Visualization.PoseVisualizer`)가 매 틱마다 TF(`map` →
`base_footprint`)·`/joint_states`·`/trail`·`/map_walls`·`/patrol_points`를 퍼블리시해서
`tools/limo-patrol-viz/patrol.rviz`로 실시간 확인 가능하다.

```json
{"started": true}
{"started": false, "reason": "empty waypoint list"}
```

### `get_path_status() -> dict`

```json
{"status": "moving", "pose": {"x": 1.2, "y": 0.3, "yaw": -0.4}, "progress": {"index": 3, "total": 15}, "result": null}
```

`status` 열거값: `idle` · `moving` · `succeeded` · `failed` · `cancelled`.

### `cancel_path() -> dict`

진행 중인 `moving_path`를 취소한다.

```json
{"cancelled": true}
{"cancelled": false, "reason": "no path motion in progress"}
```

### `send_ir_signal(device: str, command: str, value: Optional[float] = None, unit: Optional[str] = None) -> dict`

**(스텁)** 리모컨으로 `device`에 IR 신호를 보냈다고 가정하고 `ActionModule.send_signal`이 ROS2 로거에
로그만 남긴다. 실제 IR 송신 하드웨어는 미구현 — 항상 `{"sent": true, ...}`를 반환한다.

```json
{"sent": true, "device": "air_conditioner", "command": "set_temperature", "value": 24, "unit": "celsius"}
```

- `Scenarios/turn_on_air_conditioner.json`이 이 tool을 참조한다(전원 ON → 온도 설정 2회 호출).
- ⚠️ 항상 성공만 반환한다 — 실패 경로가 없다. 실제 IR 하드웨어가 붙으면 `sent: false` 경로를 추가해야 한다.

### `pick_object(object_name: str) -> dict`

로봇이 지정한 물체를 들고 있는 상태로 전환한다. 이미 다른 물체를 운반 중이거나 물체가
등록되지 않은 경우 실패를 반환한다. Phase 0에서는 실제 그리퍼가 아닌 상태 기반 시뮬레이션이다.

### `place_object(object_name: str) -> dict`

현재 운반 중인 물체를 로봇의 시뮬레이션 위치에 내려놓는다. 요청한 물체를 들고 있지 않으면
실패를 반환한다. Phase 0에서는 실제 그리퍼가 아닌 상태 기반 시뮬레이션이다.

### `get_carrying_state() -> dict`

현재 운반 중인 물체와 등록된 물체들의 시뮬레이션 위치를 반환한다.

## 미노출 — 구현은 있으나 tool이 아닌 것 (G-3)

`ReasoningModule`에 있으나 `@mcp.tool()`이 붙지 않아 외부에서 호출 불가:

| 메서드 | 용도 |
|---|---|
| `start_person_scan(hz, min_conf, stop_on_hit)` | 1 Hz 배경 사람 탐지 루프 시작 |
| `wait_for_person(timeout)` | 발견까지 블로킹 대기 |
| `get_scan_status()` | 스캔 상태 조회 |
| `stop_person_scan()` | 스캔 정지 |
| `check_object_state(object_class: str = "person", min_conf: float = 0.4)` | 대상 영역 크롭 JPEG 반환 (**증거 이미지**). 프레임은 서버가 `_observe()` 로 고른다 — 실카메라가 있으면 그것, `SIM_PERSON` 이 켜져 있으면 기하 시뮬. ※ `Reasonings.py` 의 모듈 메서드는 인자가 다르다: 두 번째가 `min_conf` 가 아니라 프레임 핸들이다 |

**시나리오 1("할머니 괜찮은지 확인")의 탐색·판정 경로 전체가 여기 있다.**

> ⚠️ 노출 시 주의: `wait_for_person`은 최대 30초 블로킹이다. stdio 서버 tool로 그대로 노출하면
> 서버 루프가 멈춘다. 비동기화 또는 폴링 방식으로 바꿔야 한다.
> `get_scan_status()`는 스캔 유무에 따라 **반환 스키마가 다르다**.

## ~~미구현~~ → 해소 (G-4, 2026-08-11)

`look_around` · `is_looking_around` · `interrupt_look_around` 를 `Actions.py` 에 구현하고
MCP tool 로 노출했다. `check_object_state` 도 노출했다 (G-3 부분 해소).

`Scenarios/check_obj_state.json` 은 **여전히 실행되지 않는다** — 도구가 아니라 그 파일 쪽 문제다.
이동 스텝이 하나도 없어 "제자리 확인" 조각이고, 어느 시나리오도 이 파일을 부르지 않는다.
실행 가능한 시나리오 1은 `Scenarios/check_grandma.json`(48스텝) 이다.
근거: `docs/decisions/2026-08-11-scenario1-on-the-dsl-runner.md`

### 예전 기록 (2026-08-10 시점)

> **이 JSON DSL(`poll_until_match`/`branch`/`$input.x` 치환)을 해석하는 실행기는 이제 있다** —
> `Scenarios/run_scenario.py` (2026-08-10). `call`/`branch`/`poll_until_match` 세 타입과
> `$input.x`/`$step_id.field` 참조, `next`/`on_true`/`on_false` 생략 시 배열 순서 진행,
> `"success"`/`"fail"` sentinel을 지원한다 — 새 시나리오 JSON을 코드 작성 없이 그대로 돌릴 수 있다.
> 다만 이 파일이 참조하는 tool 3종(`look_around`·`is_looking_around`·`interrupt_look_around`)은
> 여전히 없어서, 실행기가 정상 작동해도 이 **시나리오 자체**는 `Unknown tool` 에러로 `fail`한다
> (실행기와 이 파일의 사문서 여부는 별개 — 실측 확인: 2026-08-10, WSL2).
> `check_object_state`에 넘기는 `detections` 인자도 시그니처에 없다.

## Phase 0에 추가되어야 할 A2A 최소 집합

현재 tool 19종은 **전부 L4(함수 호출) 수준**이다. IF-4 종단점이 되려면 L2 정책을 받는 층이 필요하다.

```
server/discover                  → 프로토콜 버전·능력·정체성 (= Agent Card 코어)
resources/read agentcard://self  → 확장 Agent Card
tools/call execute_policy        → L2 정책 수락 → {task_id, accepted, reject_reason?}
tools/call get_task_report       → 상태 + 최종 Report
tools/call cancel_task           → 취소
```

기존 L4 도구는 디버깅·회귀 테스트용으로 남긴다. 상세는 `interfaces/if04_secure_a2a_channel/CLAUDE.md`.
