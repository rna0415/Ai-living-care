# 코딩 컨벤션

> **코드에서 실제로 관찰된 것만 적는다.** 지켜지지 않는 규칙은 "관찰됨/위반됨"으로 표시한다.
> 미확인 항목은 `TODO(확인 필요)`.

## 1. 파일·디렉터리 명명

| 대상 | 관찰된 규칙 | 예 |
|---|---|---|
| 컴포넌트 디렉터리 | snake_case, 정식 명칭 전체 (`SOT.md` N-1/N-2) | `manager_ai_core/`, `worker_ai_management_system/` |
| 인터페이스 디렉터리 | `if<NN>_<snake_name>` | `if04_secure_a2a_channel/` |
| Worker 구현 모듈 | **PascalCase 복수형 `.py`** — 원본 보존 대상이라 유지 | `Perceptions.py`, `Reasonings.py`, `Actions.py` |
| 원본 보존 디렉터리 | 원본 이름 그대로 (D-14) | `limo-MCP/`, `limo-patrol-viz/`, 내부 `Worker_functions/` |
| 저장소 관리 스크립트 | `sot_*.py`, 루트에 위치 | `sot_audit.py` |

> **모듈명이 두 규약을 오간다.** 컴포넌트는 snake_case인데 구현 파일은 PascalCase다. D-14로 원본을
> 보존하기로 했으므로 `limo-MCP/` 내부는 손대지 않는다. **신규 코드는 snake_case를 쓴다.**

## 2. 의존성 주입 — 이 저장소의 핵심 패턴

`Reasonings.py`가 기준이다. **ROS2에 의존하지 않는 순수 로직**으로, 백엔드를 생성자로 주입받고
미주입 시 no-op으로 동작해 로봇 없이 단독 테스트가 된다.

```python
DetectFn    = Callable[[object], list]          # frame -> [{"class","conf","bbox"}]
PlanFn      = Callable[[dict, dict], list]      # start, goal -> [{"x","y","yaw"}]
CropFn      = Callable[[object, list], bytes]   # frame, bbox -> jpeg bytes
FrameSource = Callable[..., Optional[dict]]     # (frame_id=None) -> {"frame_id","frame","stamp","pose"}

def _no_op_detect(_frame) -> list: return []
```

**신규 컴포넌트를 만들 때 이 패턴을 따른다.** ROS2·하드웨어·외부 서비스 의존은 전부 주입 대상으로 뺀다.

> ⚠️ `PlanFn` 주석은 `{"x","y","yaw"}`인데 소비자 `_goal_xy_yaw`는 **`yaw_deg` 키만 읽는다.**
> 주석대로 `yaw`를 채우면 조용히 무시되고 방향이 0도가 된다. **계약 불일치 — 수정 대상.**

## 3. 무거운 의존성은 함수 안에서 import

```python
def yolo_detect(frame) -> list:
    from ultralytics import YOLO      # 모듈 import만으로 torch를 물지 않게
```

`Reasonings.py`, `MCP_server.py`의 `_encode_jpeg`(PIL)가 이 규약을 따른다. **최상단으로 올리지 말 것.**

## 4. 에러 처리 — 현재 패턴과 그 결함

관찰된 세 가지 패턴:

| 패턴 | 위치 | 평가 |
|---|---|---|
| `{"결과": None, "reason": "..."}` 반환 | `ReasoningModule.detect_objects`, `plan_path`, `check_object_state` | ✅ 권장. 예외 대신 사유를 담은 dict |
| `{"started": False, "reason": "..."}` | `ActionModule.send_goal_sequence`, `send_goal` | ✅ 권장 |
| 예외를 삼키고 계속 | `PersonScan._run`의 `except Exception → self._error` | ⚠️ 조건부. 루프는 살리되 상태로 노출해야 함 |

**반드시 지킬 규칙 (포렌식에서 위반 확인됨):**

1. **`except`는 넓게 잡는다.** `ReasoningModule`은 `except FutureTimeoutError`만 잡아서
   ultralytics `ImportError`·CUDA 에러가 선언된 dict 계약을 뚫고 MCP 프로토콜 에러로 나간다.
2. **콜백에서 예외를 내보내지 않는다.** rclpy는 콜백 예외를 재전파해 `rclpy.spin()` 스레드를 죽인다.
   `Perceptions._on_image`의 무검증 `reshape`가 이 경로다 — **카메라뿐 아니라 Nav2 액션 콜백까지 전부 정지한다.**
3. **스레드 본문 전체를 `try/except`로 감싼다.** `ActionModule.send_goal_sequence`의 `run()`이
   보호되지 않아 잘못된 입력 하나로 스레드가 죽고 `get_status`가 영원히 거짓말한다.
4. **성공/실패의 반환 타입을 같게 한다.** `get_camera_snapshot`은 성공 시 `list`, 실패 시 `dict`를 반환해
   호출자가 실패를 감지하지 못한다.

## 5. 상태 열거값은 소비자와 함께 정의한다

`ActionModule.status`는 `idle / navigating / rejected / cancelled / succeeded / failed` 6종인데
`Scenarios/send_goal.py`의 탈출 조건은 `succeeded`/`failed` **2종만** 검사한다 → 나머지 4종에서 무한 루프.

**규칙: 상태 문자열을 추가하면 그 값을 읽는 모든 소비자를 함께 갱신한다.** 가능하면 `Enum`으로 승격한다.

## 6. 동시성

| 관찰 | 위치 |
|---|---|
| `threading.Lock`으로 캐시 보호 | `PerceptionModule._lock`, `PersonScan._lock` |
| `threading.Event`로 인터럽트 | `PersonScan._stop`, `_hit_event`, `ActionModule._sequence_interrupt` |
| 백그라운드 스레드는 `daemon=True` | 전부 |
| **락 없음** | `ActionModule.status` / `last_goal` / `_goal_handle` — 3개 스레드가 무보호 공유 |

**규칙:**
- 여러 스레드가 읽고 쓰는 상태는 **하나의 락으로 묶는다.** check-then-act는 같은 락 안에서 한다.
- 콜백이 상태를 덮어쓰기 전에 **세대 토큰(goal id)을 대조**한다. 없으면 stale 콜백이 새 작업을 파괴한다.
- 전역 lazy 초기화(`_yolo_model`)에는 락을 건다. 현재 없어서 이중 로딩이 가능하다.

## 7. 경로 해석

**전부 파일 기준 상대경로.** CWD에 의존하지 않는다 — 디렉터리를 통째로 옮겨도 동작한다.

```python
D    = os.path.dirname(os.path.abspath(__file__))       # patrol_sim.py
HERE = os.path.dirname(os.path.abspath(__file__))       # patrol_viz.py
this_dir = os.path.dirname(os.path.abspath(__file__))   # sim_bringup.launch.py
```
```bash
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"    # run_patrol.sh, fetch_meshes.sh
```

**`abspath`를 반드시 쓴다.** `sim_bringup.launch.py`가 주석으로 사유를 남겼다 — 상대 `__file__`이
`GZ_SIM_RESOURCE_PATH`에 이중 결합돼 메시 로드가 깨진 실화가 있다.
`MCP_server.py:23`만 `abspath`가 빠져 있다(현재는 우연히 동작).

## 8. stdio MCP 서버의 stdout 규약

stdio 트랜스포트는 **stdout을 JSON-RPC 전용**으로 쓴다. 초기화 중 stdout에 쓰는 라이브러리가 있으면
프로토콜이 깨진다. `MCP_server.py`가 YOLO 가중치 다운로드를 이렇게 막는다:

```python
with contextlib.redirect_stdout(sys.stderr):
    yolo_detect(np.zeros((32, 32, 3), dtype=np.uint8))   # 워밍업
```

**규칙: 서버 코드에 `print`를 쓰지 않는다.** 로그는 `sys.stderr` 또는 ROS2 logger로.
현재 방어는 워밍업 1회에만 걸려 있어 이후 `print` 한 줄이면 깨진다.

## 9. 주석

**"왜"를 적는다.** 이 저장소의 좋은 예:

```python
# 카메라 SDF가 R8G8B8(=rgb8)로 정의돼 있어 그 가정으로 바로 reshape한다.
# 새 프레임이 없으면 같은 이미지를 두 번 돌리지 않는다
# 대기 중인 wait_for_person을 깨운다
```

`sim_bringup.launch.py`의 docstring은 실패 경험(cmd_vel 타입 불일치, 상대경로 이중결합, X11 연결 실패)을
사유와 함께 기록한다 — **이 수준을 기준으로 삼는다.**

## 10. 테스트

표준 라이브러리 `unittest`로 Manager graph-inference 17건과 시나리오 2 테스트 4건이 있다.
graph-inference 17건은 ROS2·DB·LLM 없이 통과한다. 시나리오 2는 Windows에 `tzdata`가 없으면 2건이
오류난다. 린터 설정은 없고, GitHub Actions는 앵커·구조·구문과 graph-inference 회귀를 실행한다.

포렌식이 확인한 테스트 가능성:

| 모듈 | 즉시 테스트 가능? |
|---|---|
| `Reasonings.py` | ✅ **가능** — 주입만으로 전 경로 검증됨. 회귀 방어선으로 삼을 것 |
| `manager_ai_core/graph_inference.py` | ✅ **검증 중** — scorer·context·관측값 주입과 fail-closed 경계 17건 회귀 |
| `Actions.py::_goal_xy_yaw` | ⚠️ ROS2 import 스텁 필요 |
| `Perceptions.py::_on_image` | ⚠️ `sensor_msgs.msg.Image` 스텁 필요 |
| `MCP_server.py` | ❌ 모듈 최상위에서 `rclpy.init()` + YOLO 다운로드 — `main()` 분리 선행 필요 |
| `patrol_sim.py` / `patrol_viz.py` | ❌ `if __name__` 가드 없이 모듈 레벨 실행 |

**신규 코드 규칙: 모듈 최상위에 부작용을 두지 않는다.** `if __name__ == "__main__":` 안으로 넣는다.

## 11. 문서

- 모든 컴포넌트·인터페이스 디렉터리에 `CLAUDE.md`를 둔다 (`SOT.md` SP-5).
- 헤더는 구조 정본(`SOT.md`)과 설계 정본(spec)을 **모두** 참조한다.
- **스펙 참조는 저장소 루트 기준 경로 하나로 통일한다** — `docs/spec/AI-Care_Unified_Architecture_Spec_v0.2.md`.
  현재 42개 중 39개가 `../` 없이 적어 링크로서 깨져 있다.
- **경로 축약은 저장소 안에서 유일하게 해석될 때만 쓴다.** `limo-MCP/Scenarios/send_goal.py` 처럼
  앞을 생략해도 좋지만, 같은 꼬리를 가진 파일이 둘 이상이면 전체 경로를 적는다 — 읽는 사람이
  어느 파일인지 알 수 없다. `anchor.py` A7 이 실재와 유일성을 함께 본다.
- **수치를 적을 때 출처와 한정어를 함께 적는다.** "커버리지 93.6%"가 아니라
  "기하 시뮬레이션 기준 93.6%(2 m² 이상 사각지대 0)".
