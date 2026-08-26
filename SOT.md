# SOT — AI-Care 저장소 구조·명명 정본

> **이 문서는 저장소 구조의 정본(Source of Truth)이다.**
> 설계의 정본은 `docs/spec/AI-Care_Unified_Architecture_Spec_v0.2.md`이고,
> 이 문서는 그 **§2(정규화된 컴포넌트)** 와 **§3(인터페이스 카탈로그)** 를 디렉터리로 사상(寫像)한 규범이다.
>
> | 문서 | 관할 |
> |---|---|
> | `docs/spec/…_v0.2.md` | **설계** — 무엇을 만드는가, 용어, 스키마, 인터페이스 의미 |
> | **`SOT.md` (이 문서)** | **구조** — 어디에 두는가, 디렉터리 이름, 배치 규칙 |
> | `sot_audit.py` | **집행** — 위 규범을 기계 검사 |
>
> 셋이 어긋나면 우선순위는 **spec > SOT > 코드**다. 코드가 앞서면 SOT를 고치고, SOT가 앞서면 spec에 반영한다.

**작성일**: 2026-08-06 · **기준 스펙**: v0.2 · **상태**: Draft

---

## 1. 명명 규칙 (Normative)

| ID | 규칙 |
|---|---|
| **N-1** | 컴포넌트 디렉터리 이름은 **스펙 §2의 정식 명칭을 그대로** 쓴다. 문맥에 기댄 축약(`core/`, `analyzer/`, `mgmt_system/`)을 쓰지 않는다. 파일 하나만 열어도 어느 컴포넌트인지 알 수 있어야 한다. |
| **N-2** | 표기는 **snake_case**. 공백·하이픈·대문자를 쓰지 않는다. 파이썬 패키지·ROS2 경로·셸 스크립트에서 그대로 식별자로 쓸 수 있어야 한다. (`Manager AI Core` → `manager_ai_core`) |
| **N-3** | 약칭(MAC/MAA/MAMS/WAC/WAA/WAMS/KG/IAD/PF/RF/AF)은 **문서 안에서만** 쓴다. 디렉터리 이름으로 쓰지 않는다. |
| **N-4** | 인터페이스 디렉터리는 `if<NN>_<snake_name>` 형식. 번호를 붙여 스펙 §3의 표 순서와 정렬을 강제한다. |
| **N-5** | 비컴포넌트(`docs/` `tools/` `contracts/` `interfaces/`)는 저장소 루트에 둔다. **`sim/`은 존재하지 않으며 금지 경로다** — 시뮬레이션은 `worker_ai_agent/limo-MCP/Simulation/`에 있고 이는 D-14 보존 대상 내부이므로 이 규칙의 예외다 (F-13 잔여 정정). |

---

## 2. 정규 디렉터리 구조 (Normative)

```
<repo root>/
├── SOT.md                              ← 이 문서
├── CLAUDE.md
├── requirements.txt
│
├── manager_ai_agent/                   Manager AI Agent
│   ├── manager_ai_core/                MAC
│   │   ├── intent_extraction/
│   │   ├── kg_mapping/
│   │   ├── query_composing/
│   │   ├── policy_generation/
│   │   └── session_key_manager/
│   ├── manager_ai_analyzer/            MAA
│   │   ├── report_interpreter/
│   │   └── assurance_loop/
│   ├── manager_ai_management_system/   MAMS  (Agent Registry 겸함)
│   │   ├── agent_registry/
│   │   └── worker_selector/
│   ├── knowledge_graph/                KG
│   ├── intent_audit_database/          IAD
│   └── mcp_client/                     A2A Client — IF-4 Manager 측 종단점
│
├── worker_ai_agent/                    Worker AI Agent
│   ├── worker_ai_core/                 WAC
│   │   ├── policy_translator/
│   │   └── session_key_handler/
│   ├── worker_ai_analyzer/             WAA
│   ├── worker_ai_management_system/    WAMS
│   │   └── agent_card/
│   ├── perception/                     PF
│   ├── reasoning/                      RF
│   ├── action/                         AF
│   ├── mcp_server/                     A2A Server + Agent Executor — IF-4 Worker 측 종단점
│   └── limo-MCP/                       ★ 원본 보존 (D-14) — LIMO Worker 구현체
│       ├── Worker_functions/           PF·RF·AF 구현 (Perceptions/Reasonings/Actions.py)
│       ├── MCP_server/                 MCP stdio 서버 진입점
│       ├── Simulation/                 Gazebo 브링업
│       └── Scenarios/                  MCP 왕복 클라이언트
│
├── interfaces/                         IF-1 ~ IF-8 (스펙 §3)
│   ├── if01_database/
│   ├── if02_analytics/
│   ├── if03_registration/
│   ├── if04_secure_a2a_channel/        A2A-over-MCP 바인딩 정의
│   ├── if05_sf_facing/
│   ├── if06_agent_monitoring/
│   ├── if07_ams_facing/
│   └── if08_analyzer_facing/
│
├── contracts/                          계층 간 페이로드 스키마
│   ├── intent_query/                   L1
│   ├── high_level_policy/              L2
│   ├── low_level_policy/               L3
│   └── worker_report/
│
├── tools/                              검증·시연 도구 (비컴포넌트)
│   └── limo-patrol-viz/                ★ 원본 보존 (D-14)
└── docs/                               문서 (비컴포넌트)
    ├── spec/ context/ handoff/ audit/ slides/
    ├── standards/                   I-D · 기고문 원고 (S-* 는 spec §11.1 이 정본)
    └── papers/                      매거진 논문 원고
```

### 2.1 컴포넌트 ↔ 디렉터리 대응 (스펙 §2)

| 스펙 §2 정식 명칭 | 약칭 | 디렉터리 | 주 인터페이스 | Phase | 현재 코드 |
|---|---|---|---|---|---|
| Manager AI Core | MAC | `manager_ai_agent/manager_ai_core/` | IF-1·IF-2·IF-3·**IF-4** | 0 | `graph_inference.py` 지원 코어 + 시나리오 2 규칙 정책 (부분) |
| Manager AI Analyzer | MAA | `manager_ai_agent/manager_ai_analyzer/` | IF-2·IF-1·IF-8 | 0 | 없음 |
| Manager AI Management System | MAMS | `manager_ai_agent/manager_ai_management_system/` | IF-3·**IF-7** | 0→2 | 없음 |
| Knowledge Graph | KG | `manager_ai_agent/knowledge_graph/` | IF-1 | 0 | `kg.py` JSON 장소 룩업 (부분, G-6) |
| Intent Audit Database | IAD | `manager_ai_agent/intent_audit_database/` | IF-1 | 1 | 없음 |
| Worker AI Core | WAC | `worker_ai_agent/worker_ai_core/` | **IF-4**·IF-5·IF-3 | 0 | 없음 |
| Worker AI Analyzer | WAA | `worker_ai_agent/worker_ai_analyzer/` | IF-6·IF-2·IF-8 | 0 | 없음 |
| Worker AI Management System | WAMS | `worker_ai_agent/worker_ai_management_system/` | IF-3·**IF-7** | 1 | 없음 |
| Perception Function | PF | `worker_ai_agent/perception/` | IF-5·IF-6 | 0 | `Perceptions.py` |
| Reasoning Function | RF | `worker_ai_agent/reasoning/` | IF-5·IF-6 | 0 | `Reasonings.py` |
| Action Function | AF | `worker_ai_agent/action/` | IF-5·IF-6 | 0 | `Actions.py` |
| A2A Client | — | `manager_ai_agent/mcp_client/` | **IF-4** | 0 | 없음 |
| A2A Server + Agent Executor | — | `worker_ai_agent/mcp_server/` | **IF-4** | 0 | `MCP_server.py` (구현은 `limo-MCP/`) |

> **PF/RF/AF의 정식 명칭은 "…Function"이지만 디렉터리는 `perception/`·`reasoning/`·`action/`으로 한다** (D-11).
> `_function` 접미사가 모든 경로에 반복되어 가독성을 해치고, 상위 `worker_ai_agent/`가 이미 문맥을 준다.
> **N-1의 유일한 예외이며 여기 명시적으로 기록한다.**

### 2.2 A2A 종단점 배치 근거

`docs/context/AI-Care_A2A_Core_Context(2).md` §4의 컴포넌트 표가 배치를 이미 정하고 있다.

| 그 문서가 정한 위치 | 컴포넌트 | → SOT 디렉터리 |
|---|---|---|
| **Manager AI Agent** | A2A Client | `manager_ai_agent/mcp_client/` |
| **Worker AI Agent** | A2A Server | `worker_ai_agent/mcp_server/` |
| **Worker AI Agent** | Agent Executor | `worker_ai_agent/mcp_server/` |
| **Worker AI Core** | Policy Handler | `worker_ai_agent/worker_ai_core/policy_translator/` |
| Worker AI Management System | Agent Card | `worker_ai_agent/worker_ai_management_system/agent_card/` |
| Manager AI Management System | Agent Registry | `manager_ai_agent/manager_ai_management_system/agent_registry/` |
| Worker AI Analyzer | Task/Artifact 변환 | `worker_ai_agent/worker_ai_analyzer/` |

**A2A 컴포넌트는 전부 Manager 또는 Worker 안에 배정되어 있다. 최상위 `a2a/` 디렉터리는 두 문서 어디에도 근거가 없다.**
스펙 §10.1도 `MCP_server.py`를 **"Worker AI Core (WAC) / A2A 종단점"** 으로 매핑한다.

공유 자산인 **바인딩 정의(A2A 객체 ↔ MCP 매핑)** 만은 어느 한쪽 소유가 아니므로 `interfaces/if04_secure_a2a_channel/`에 둔다.

---

## 3. 인터페이스 카탈로그 배치 (스펙 §3)

스펙은 *"각 인터페이스가 곧 표준화 문서의 한 절이 된다"* 고 적고 있다.
**IF-1~IF-8은 표준화 산출물(S-6)이므로 물리적 자리를 갖는다.**

| 디렉터리 | 인터페이스 | 종단점 | 담는 것 | Phase |
|---|---|---|---|---|
| `if01_database/` | Database Interface | MAC ↔ KG/IAD, MAA ↔ IAD | `resolve()` 계약, 감사 레코드 스키마 | 0 |
| `if02_analytics/` | Analytics Interface | MAC ↔ MAA, WAC ↔ WAA | 해석 결과·판정 메시지 | 0 |
| `if03_registration/` | Registration Interface | MAC ↔ MAMS, WAC ↔ WAMS | 등록·조회·상태 | 0 |
| `if04_secure_a2a_channel/` | **Secure A2A Channel** | MAC ↔ WAC | **A2A-over-MCP 바인딩 정의, TaskState 정렬, 세션 키** | 0 |
| `if05_sf_facing/` | SF-Facing Interface | WAC → PF/RF/AF | L3 저수준 정책 전달 규약 | 0 |
| `if06_agent_monitoring/` | Agent Monitoring Interface | PF/RF/AF → WAA | 실행 상태·관측값 | 0 |
| `if07_ams_facing/` | AMS-Facing Interface | MAMS ↔ WAMS | 능력·**실시간 자원 상태** 공시 | 2 |
| `if08_analyzer_facing/` | Analyzer-Facing Interface | MAA ↔ WAA | 상세 진단·이상 이벤트 | 2 |

### `interfaces/` 와 `contracts/` 의 차이

혼동하기 쉬우므로 명시한다.

- **`interfaces/`** = **누가 누구에게 어떻게 말하는가.** 종단점·호출 규약·전송·수명주기.
- **`contracts/`** = **무엇을 말하는가.** 그 위를 흐르는 페이로드 스키마(L1·L2·L3·Report).

예: IF-4는 "MAC이 WAC에 `tools/call execute_policy`로 보내고 `tasks/get`으로 폴링한다"를 정하고,
`contracts/high_level_policy/`는 "그 안에 실리는 `<living-care-policy>`가 어떤 필드를 갖는가"를 정한다.

---

## 4. 배치 규칙 (Normative)

| ID | 규칙 |
|---|---|
| **SP-1** | 컴포넌트 디렉터리에는 **그 컴포넌트의 구현만** 둔다. 다른 컴포넌트가 쓰는 공용 코드는 `contracts/`나 `interfaces/`로 올린다. |
| **SP-2** | **컴포넌트 경계를 넘는 직접 호출을 만들지 않는다.** 반드시 IF-1~IF-8을 경유한다. 경유하지 않는 호출이 필요하면 인터페이스를 새로 정의하고 스펙 §3에 추가한다. |
| **SP-3** | `sim/` `tools/`에 **비즈니스 로직을 두지 않는다.** 컴포넌트를 호출만 한다. |
| **SP-4** | 스키마 변경은 **`contracts/` 먼저 → 스펙 반영 → 코드** 순서. 코드가 스펙을 앞서면 SOT가 깨진다. |
| **SP-5** | 모든 컴포넌트·인터페이스 디렉터리에 **`CLAUDE.md`가 있어야 한다.** 없으면 그 디렉터리는 미정의 상태로 간주한다. |
| **SP-6** | 각 `CLAUDE.md` 헤더는 **SOT와 스펙을 모두 참조**해야 한다. |

---

## 5. 감사 규칙 (`sot_audit.py` — **구조를 바꿀 때만** 실행한다)

| ID | 검사 |
|---|---|
| **AR-1** | §2.1의 컴포넌트 디렉터리 11개 + A2A 종단점 2개가 정확한 이름으로 존재 |
| **AR-2** | 금지 별칭 디렉터리 부재 — `manager/` `worker/` `a2a/` `*/core` `*/analyzer` `*/mgmt_system` `*/service_functions` `*/intent_audit_db` |
| **AR-3** | `interfaces/if01_…`~`if08_…` 8개 존재 |
| **AR-4** | 모든 컴포넌트·인터페이스 디렉터리에 `CLAUDE.md` 존재 (SP-5) |
| **AR-5** | 코드 파일이 SOT가 정한 위치에 존재 |
| **AR-6** | 비컴포넌트 3종(`docs` `tools` `contracts`)이 루트에 존재. **`sim/`은 금지 경로다** — 시뮬레이션은 `worker_ai_agent/limo-MCP/Simulation/`에 있다 (F-13 해소) |
| **AR-7** | 경로 참조 무결성 — `mcp_server`의 `sys.path`가 실재 디렉터리를 가리키고, scenarios의 `SERVER_PATH`가 실재 파일을 가리킴 |
| **AR-8** | `CLAUDE.md`가 SOT를 참조 (SP-6) |
| **AR-10** | D-14 원본 보존 대상이 존재하고 내부 구조가 원형인지 |
| **AR-9** | 컴포넌트 디렉터리 밖에 떠도는 `.py` 부재. 루트 허용은 `sot_audit.py` · `anchor.py` 둘뿐 (`sot_migrate.py` · `sot_preserve.py`는 **폐기** — 실행하면 42개 `CLAUDE.md`를 되돌린다) |

```bash
python3 sot_audit.py          # 구조 검사 (AR-1~AR-10)
python3 sot_audit.py --plan   # 위반 해소용 git mv 계획 출력
python3 anchor.py             # 앵커 누락만 확인 (수 초)
```

---

## 6. 결정 기록

| ID | 결정 | 근거 |
|---|---|---|
| **D-9** | A2A 종단점을 **최상위가 아니라 각 에이전트 안에** 둔다. `manager_ai_agent/mcp_client/`, `worker_ai_agent/mcp_server/` | A2A_Core_Context §4가 A2A Client를 Manager AI Agent에, A2A Server·Agent Executor를 Worker AI Agent에 배정. 스펙 §10.1도 `MCP_server.py`를 WAC/A2A 종단점으로 매핑 |
| **D-10** | `interfaces/`를 **1급 디렉터리**로 둔다 | 스펙 §3 *"각 인터페이스가 곧 표준화 문서의 한 절이 된다"*. 표준화 항목 S-6의 실체 |
| **D-11** | PF/RF/AF 디렉터리에서 `_function` 접미사를 뺀다 | N-1의 명시적 예외. 상위 `worker_ai_agent/`가 문맥을 주므로 반복이 불필요 |
| **D-12** | `service_functions/` 중간 계층을 **두지 않는다** | 스펙 §2.2에서 "Service Functions"는 컴포넌트가 아니라 **행 레이블**이다. 실제 컴포넌트는 PF/RF/AF 셋. IF-5·IF-6이 이들을 집합으로 지칭하는 것은 `interfaces/if05_sf_facing/`이 문서로 다룬다 |
| **D-14** | **`limo-MCP/` 와 `limo-patrol-viz/` 는 원본을 그대로 보존한다.** 각각 `worker_ai_agent/limo-MCP/`, `tools/limo-patrol-viz/` 에 통째로 배치하고 내부를 분해하지 않는다 | 기존 저장소 작업자가 영향 없이 계속 작업하게 하기 위함. 컴포넌트 디렉터리는 **규범**을 보유하고 코드는 구현체에 둔다 — 규범과 구현의 분리 |
| **D-13** | 컴포넌트 디렉터리에 정식 명칭 전체를 쓴다 (`manager_ai_core`, `core` 아님) | N-1. 파일 하나만 열려 있어도 소속이 드러나야 하고, 축약형은 Manager/Worker 양쪽에서 충돌한다 |
| **D-15** | **배치 규칙은 `SP-*`, 감사 규칙은 `AR-*`, 하네스 로컬 체크는 `H*-`로 접두를 분리한다** | spec §1.2의 설계 원칙 `P-*`, §11.1의 표준화 `S-*`와 충돌하면 "P-4를 지켰나"라는 문장의 의미가 결정되지 않는다 (F-14·F-23). 새 접두는 정의처에 한 번만 정의한다 |
| **D-17** | **소유 경계.** `worker_ai_agent/limo-MCP/**` 와 `tools/limo-patrol-viz/**` 의 **코드는 담당 연구원 소유**다. 생태계·하네스 담당은 이 트리의 파일을 **읽고 결함을 기록할 뿐 고치지 않는다.** 각 트리의 `CLAUDE.md`(우리가 만든 규범)만 예외 | 원본 보존(D-14)은 파일 배치 규칙이 아니라 **역할 경계**다. 2026-08-06 에 생태계 담당이 이 경계를 넘어 8개 파일을 수정했고 전부 되돌렸다. 발견한 결함은 `docs/status.md` 에 ID 로 남기고 담당자에게 넘긴다 |
| **D-18** | **안전 결함의 인계 경로.** 소유 경계(D-17) 때문에 고칠 수 없는 안전 결함은 `docs/safety/` 에 **파일 하나**로 (`# F-NN · 제목` + `> **귀속** `경로``) 적고, 그 컴포넌트 `CLAUDE.md` 의 `> **상태**` 줄에 같은 F-ID 를 박는다. 담당자는 고치고 **실패 경로를 한 번 실행한 뒤** 두 자리를 함께 지운다. 목록은 `make status` 맨 위에 뜬다 | 경계는 「고치지 마라」이지 「묻어라」가 아니다. 기록만 하고 전달 장치가 없으면 F-1~F-3 같은 안전 결함이 조용히 늙는다. 2026-08-08 에 표를 파일로 바꿨다 — 담당자 둘이 각각 결함을 올리면 표가 충돌했다(실측). `상태` 줄은 이미 `make status` 가 수확하므로 **새 장치를 만들지 않고 있는 경로에 얹었다.** `anchor.py` A5 가 두 자리의 짝을 강제한다 — 한쪽만 지우면 커밋이 막힌다 |
| **D-16** | **`SOT.md` §2 트리 · `sot_audit.py` 검사 대상 · 실제 디렉터리는 항상 집합 일치한다** | 셋 중 하나만 고치면 정본이 파생물보다 낡는다 — 실제로 발생했다 (F-20). 구조를 바꾸면 트리도 같이 고친다 |

> **spec §0.2 반영 상태** (2026-08-07 실측): `D-9`~`D-14`·`D-17`·`D-18` 반영 완료.
> **`D-15`·`D-16` 미반영** — 구조 규범 전용이라 spec 에 올릴지는 판단이 필요하다.
> 이 줄은 셀 때마다 다시 재고 고친다. 세지 않은 채로 두면 낡는다.
