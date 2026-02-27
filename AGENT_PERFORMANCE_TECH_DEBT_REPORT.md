# 에이전트 성능 기술부채 보고서

- 작성일: 2026-02-12
- 범위: `agent-runtime`, `backend`
- 목적: "추론이 약함 / 화면을 못 봄 / 쓸데없는 행동 반복"의 구조적 원인 진단 및 개선 우선순위 제시

## 1) 결론 요약

현재 성능 저하의 핵심은 단일 문제가 아니라, 다음 3개 축의 복합 부채다.

1. 아키텍처 불일치: 에이전트 카탈로그와 실제 실행 플러그인이 구조적으로 어긋나 특화 동작이 거의 발동되지 않는다.
2. 인지/행동 루프 품질 부족: SoM fallback, 성공 판정, 파서 강건성 문제로 잘못된 행동이 누적된다.
3. 품질 거버넌스 부재: 성능 추적기/실행 설정 일부가 런타임 루프에 충분히 연결되지 않아 회귀를 조기 탐지하기 어렵다.

## 2) 사용자 증상 기준 원인 매핑

| 사용자 체감 증상 | 1차 원인 | 코드 근거 | 영향 |
|---|---|---|---|
| "에이전트가 다 비슷하게 멍청함" | 등록 에이전트 대비 실제 플러그인 구현 부족 + 매핑 불일치 | `agent-runtime/core/agent_registry.py` (프로파일 다수), `agent-runtime/plugins` (실제 5개), `agent-runtime/core/engine.py:983`, `agent-runtime/core/plugin_loader.py:62` | 특화 전략 대신 generic 경로 사용 증가 |
| "추론을 제대로 못함" | tier 미스매치로 고성능 옵션이 F-tier로 강등 가능 | `agent-runtime/core/agent_registry.py:347`, `agent-runtime/core/tier_config.py:454`, `agent-runtime/core/tier_config.py:76` | vision/SoM/planning/memory 비활성화 가능 |
| "화면을 제대로 못봄" | OCR/요소검출이 엣지 기반 휴리스틱 중심, provider에 따라 비전 미지원 | `agent-runtime/core/som_engine.py:181`, `agent-runtime/core/vision_engine.py:284`, `agent-runtime/core/llm_client.py:249` | 실제 UI 의미 이해 실패, 요소 오탐 증가 |
| "쓸데없는 행동 반복" | element fallback이 좌표 없는 click으로 전환, 성공 판정이 느슨함 | `agent-runtime/core/engine.py:2227`, `agent-runtime/core/os_controller.py:555`, `agent-runtime/core/os_controller.py:545` | 실패를 성공으로 오인, 루프 품질 악화 |

## 3) 상세 기술부채 진단

### A. 치명: 에이전트-플러그인 매핑 불일치

- 정적 프로파일 수: 50개 (`agent-runtime/core/agent_registry.py`, `AgentProfile(` 카운트)
- 실제 플러그인 파일: 5개 (`agent-runtime/plugins`)
- slug 매칭 점검 결과: registry slug 49개 vs plugin key 5개, 교집합 0개 (로컬 스캔 결과)
- 플러그인 키 예시: `apex_coder`, `omniscient_agent` (`agent-runtime/plugins/apex_coder_agent.py:214`, `agent-runtime/plugins/omniscient_agent.py:37`)
- 레지스트리 slug 예시: `apex-coder`, `omniscient` (`agent-runtime/core/agent_registry.py:71`, `agent-runtime/core/agent_registry.py:62`)
- plugin lookup은 사실상 exact 매칭 위주 (`agent-runtime/core/plugin_loader.py:62`)
- 미매칭 시 generic fallback (`agent-runtime/core/engine.py:983`)

평가:
- 특화 에이전트가 있어도 실행 시 generic로 흘러 "에이전트별 지능 차이 체감"이 사라진다.

### B. 치명: Tier enum 불일치로 성능 강등

- 정의된 tier: `F, B-, C, B, A, S, S+` (`agent-runtime/core/tier_config.py:75`)
- 레지스트리 사용 tier: `E, D, C+, B+, A+` 포함 (`agent-runtime/core/agent_registry.py:347`, `agent-runtime/core/agent_registry.py:387`, `agent-runtime/core/agent_registry.py:427`, `agent-runtime/core/agent_registry.py:467`, `agent-runtime/core/agent_registry.py:507`)
- 미정의 tier 엔트리: 총 19개 (로컬 스캔 결과)
- 미정의 tier fallback: F (`agent-runtime/core/tier_config.py:454`)
- F-tier는 vision/SoM/planning/memory off (`agent-runtime/core/tier_config.py:80`, `agent-runtime/core/tier_config.py:82`, `agent-runtime/core/tier_config.py:83`, `agent-runtime/core/tier_config.py:84`)

평가:
- 가격/포지셔닝과 실제 capability가 불일치할 수 있고, 추론/시각 인식이 급격히 약해질 수 있다.

### C. 높음: 시각 인지 파이프라인의 의미 인식 한계

- 스크린샷은 max width 1920으로 정규화 (`agent-runtime/core/screenshot.py:33`, `agent-runtime/core/screenshot.py:79`)
- SoM은 edge-grid-clustering 중심 (`agent-runtime/core/som_engine.py:181`, `agent-runtime/core/som_engine.py:186`, `agent-runtime/core/som_engine.py:197`)
- 텍스트 추출도 edge-density 기반 (`agent-runtime/core/vision_engine.py:286`, `agent-runtime/core/vision_engine.py:300`, `agent-runtime/core/vision_engine.py:314`)
- Mistral 경로는 스크린샷 미사용 (`agent-runtime/core/llm_client.py:249`)

평가:
- "화면을 본다"가 semantic OCR/VLM 이해가 아니라 구조 추정에 가까워 복잡 UI에서 실패율이 높다.

### D. 높음: 행동 성공 판정이 너무 관대함

- `execute_action`은 handler 예외가 없으면 성공 반환 (`agent-runtime/core/os_controller.py:545`)
- `run_command`는 비정상 종료도 문자열로 반환 (`agent-runtime/core/os_controller.py:807`)
- 상위 루프는 `result.success`에 의존 (`agent-runtime/core/engine.py:1451`)

평가:
- `Exit 1` 같은 실패를 성공으로 간주할 수 있어, 잘못된 계획이 강화된다.

### E. 높음: SoM fallback이 무의미 클릭 유발

- element 해석 실패 시 `_element` suffix 제거 (`agent-runtime/core/engine.py:2227`)
- `id` 제거 후 좌표 없으면 click 기본값 `(0,0)` (`agent-runtime/core/os_controller.py:555`)
- 다른 경로에서는 중심점 fallback도 존재 (`agent-runtime/core/os_controller.py:533`)

평가:
- 랜덤/무의미 클릭이 발생하고, 이후 단계도 연쇄 오염된다.

### F. 중간: 파서 포맷 의존도 과다

- `ACTION:` 다음 줄 `PARAMS:` 형식 가정 (`agent-runtime/core/engine.py:2100`, `agent-runtime/core/engine.py:2106`)
- plugin parser도 동일한 라인 기반 제약 (`agent-runtime/plugins/base_plugin.py:790`, `agent-runtime/plugins/base_plugin.py:795`)
- no-action 3회면 종료 (`agent-runtime/core/engine.py:1373`)

평가:
- 모델 출력이 조금만 흔들려도 실행 액션이 0개가 되며, 실제 작업 완료 전에 종료될 수 있다.

### G. 중간: completion 검증이 행위량 중심

- min actions, typed 여부 중심 (`agent-runtime/core/engine.py:726`, `agent-runtime/core/engine.py:1340`, `agent-runtime/plugins/base_plugin.py:466`)

평가:
- "정답 달성 여부"가 아니라 "행동 수"를 만족하면 통과/거절되는 오판이 가능하다.

### H. 중간: 프롬프트/컨텍스트 예산 압박

- prompt budget 초과 시 잘라냄 (`agent-runtime/plugins/base_plugin.py:656`)
- history trimming 후 요약 삽입 (`agent-runtime/core/engine.py:1712`)

평가:
- 장기 태스크에서 중요한 맥락 유실 가능성이 있다.

### I. 중간: 실행 설정 연결 불완전

- backend는 `maxExecutionTime`, `screenshotInterval` 전달 (`backend/src/services/executionService.ts:471`, `backend/src/services/executionService.ts:472`)
- 협업 엔진은 `maxExecutionTime` 사용 (`agent-runtime/core/collaboration_engine.py:535`)
- 단일 generic 루프는 step 기반 제한 중심 (`agent-runtime/core/engine.py:1059`, `agent-runtime/core/engine.py:1151`)

평가:
- 경로별로 실행 제한/주기 정책이 일관되지 않다.

### J. 중간: 성능 추적기 미통합

- `PerformanceTracker` 정의만 존재 (`agent-runtime/core/performance_tracker.py:55`)
- 주요 실행 루프 참조 부재 (`agent-runtime/core/engine.py`, `agent-runtime/core/collaboration_engine.py` 검색 기준)

평가:
- 회귀 탐지/비교가 어렵고, 운영 품질 개선 속도가 느리다.

## 4) 우선순위 백로그 (실행 관점)

| 우선순위 | 항목 | 난이도 | 기대효과 |
|---|---|---|---|
| P0 | plugin slug 정규화 매핑 (`-/_/space`, `_agent` suffix normalize) 및 부팅 시 매핑 검증 실패 hard-fail | 중 | 특화 에이전트 실제 활성화 |
| P0 | tier enum 스키마 강제 (registry load 시 미정의 tier 예외) | 하 | silent F-tier 강등 제거 |
| P0 | `run_command` 성공 조건 강화 (returncode==0만 success) | 하 | 실패 행동 재시도/회복 품질 향상 |
| P0 | unresolved `click_element` 차단 (좌표 없으면 실패 처리, fallback click 금지) | 하 | 무의미 클릭 급감 |
| P1 | parser 강건화 (JSON 블록, fenced block, function-call 스타일 지원) | 중 | no-action turn 감소 |
| P1 | provider capability gate (비전 필요 태스크에서 non-vision 모델 차단/경고) | 하 | "화면 못봄" 즉시 완화 |
| P1 | completion 검증에 outcome 기반 체크 추가 (파일 생성/URL 도달/텍스트 검증) | 중 | 조기 TASK_COMPLETE 감소 |
| P2 | screenshot/vision 파이프라인 고도화 (OCR 엔진 + semantic element detector) | 상 | 복잡 UI 인식 정확도 향상 |
| P2 | 성능 지표 수집 파이프라인 통합 (`PerformanceTracker` 실사용) | 중 | 회귀 탐지 자동화 |

## 5) 30/60/90일 개선 로드맵

### 0-30일 (안정화)

1. plugin slug normalization + 매핑 리포트 자동 생성
2. tier enum validation (앱 시작 시 fail fast)
3. action success semantics 정정 (`run_command`, unresolved element)
4. 비전 미지원 모델 사용 시 UI 경고 + 태스크 차단 정책

완료 기준:
- generic fallback 비율 80% 이상 감소
- 무효 클릭율 50% 이상 감소
- non-zero command false positive 0%

### 31-60일 (품질 개선)

1. action parser 다중 포맷 지원
2. outcome-based completion verifier 도입
3. screenshotInterval / execution timeout 정책을 단일/협업 경로에 통합

완료 기준:
- no-action wrap-up 비율 40% 이상 감소
- premature completion 비율 50% 이상 감소

### 61-90일 (지능 고도화)

1. semantic OCR/VLM 기반 요소 인식 계층 도입
2. `PerformanceTracker` 실시간 수집 + 대시보드/알림 연동
3. 회귀 테스트 벤치 (대표 시나리오: browsing/writing/coding/research)

완료 기준:
- task success rate 20%p 개선
- 화면 인식 실패율 40% 이상 감소

## 6) 권장 KPI/SLO

1. `TaskSuccessRate`: 사용자 목표 달성률
2. `InvalidActionRate`: 검증 실패/무효 행동 비율
3. `NoActionTurnRate`: 파서 미검출 turn 비율
4. `ElementResolutionFailureRate`: `*_element` 해석 실패율
5. `FalseSuccessRate`: 실제 실패인데 success로 기록된 비율
6. `PrematureCompletionRate`: 작업 미완료 TASK_COMPLETE 비율
7. `VisionUtilizationRate`: 비전 필요 태스크에서 vision-capable 모델 사용 비율

SLO 초안:
- `FalseSuccessRate < 1%`
- `NoActionTurnRate < 5%`
- `PrematureCompletionRate < 3%`

## 7) 즉시 적용 가능한 정책 변경안

1. `plugin_loader.get_plugin`에 canonical identifier 함수 추가
2. `agent_registry` 로드 시 tier enum validate + 미정의 tier reject
3. `os_controller.execute_action`에서 action별 성공 기준 분리
4. `resolve_som_action` 실패 시 hard-fail + 재관찰 프롬프트 강제
5. 비전 태스크에서 모델 capability 미충족 시 실행 차단

## 8) 비고

- 코드 컴파일 체크 시 경고 1건 확인: `agent-runtime/core/engine.py:2073` (`invalid escape sequence '\>'`)
- 운영 로그는 `logs/combined.log`, `logs/error.log` 중심이며, 성능 전용 구조화 로그가 부족하다.
