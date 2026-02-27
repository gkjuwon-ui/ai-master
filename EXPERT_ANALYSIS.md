# OSEN-1.0 MoE Expert Analysis Report

> **Model**: OSEN-1.0 (Llama 4 Scout 17B-16E-Instruct → 20 Experts)  
> **Architecture**: Mixture-of-Experts, top-1 routing per token, 48 layers  
> **Expert Dimensions**: gate_proj/up_proj [8192×5120], down_proj [5120×8192]  
> **Generated**: 2026-02-14

---

## 1. Executive Summary

OSEN-1.0은 Meta의 Llama 4 Scout 17B-16E-Instruct를 기반으로 16개 범용 MoE 전문가에서 **20개 전문가로 확장**한 OS 자동화 특화 모델이다.

### 핵심 판정

| 항목 | 결과 |
|------|------|
| 신규 4 전문가가 가우시안 노이즈인가? | **❌ 아님** — SVD 회전 + SV 변조 + rank-32 구조적 섭동 + 교차 직교화 적용 |
| NF4 양자화 후에도 차이가 유지되는가? | **✅ 유지됨** — 변환 크기 15-25% (NF4 노이즈 ~1-2% 대비 10배↑) |
| 도메인 특화 지식이 가중치에 있는가? | **⚠️ 아님** — 기하학적 변환만 적용, 도메인 지식은 파인튜닝에 의존 |
| 기존 전문가 선정 근거는 타당한가? | **⚠️ 부분적** — stride-4 패턴으로 균등 분산, 의미 기반 선정은 아님 |
| 라우터 학습은 적절한가? | **✅ 적절** — 6-component loss (특화/대조/다양성/증류/부하균형/커리큘럼) |
| 학습 데이터는 충실한가? | **✅ 충실** — 전문가별 500+ 특화 대화 + 한국어 변형 포함 |

---

## 2. 기존 16개 전문가 상세 분석 (Llama 4 Scout Original)

> ⚠️ **중요**: Llama 4 Scout의 원본 16 전문가는 사전학습 과정에서 **자동으로 특화가 형성**된 것이다.
> 아래 매핑은 OSEN-1.0에서 **부여한 역할**이며, 실제 가중치에 해당 도메인 지식이 있다는 보장은 없다.
> MoE에서 전문가 특화는 학습 중 라우팅 확률로 자연 발생하며, 번호와 의미의 1:1 대응은 아키텍처적으로 보장되지 않는다.

### 전문가별 특성 표

| # | 이름 | 도메인 | 라우팅 바이어스 | 핵심 학습 초점 | 설명 |
|---|------|--------|----------------|---------------|------|
| 0 | `os_action_planner` | OS 액션 시퀀스 계획 | 0.15 | action_sequencing, shortcut_planning, window_management, app_workflow, multi_step_orchestration | 다단계 OS 작업 분해: 클릭 시퀀스, 키보드 단축키, 창 관리, 앱 런치. 사용자 의도→원자적 GUI 액션 변환 |
| 1 | `screen_understanding` | 시각적 화면 상태 이해 | 0.15 | screenshot_analysis, ui_layout_parsing, ocr_interpretation, visual_state_classification, element_detection | 스크린샷, UI 레이아웃, 요소 위치, 화면 텍스트, 다이얼로그, 에러 메시지, 로딩 상태 해석 |
| 2 | `error_recovery` | 에러 감지/진단/복구 | 0.12 | error_classification, crash_recovery, permission_handling, network_error_mitigation, stuck_detection, fallback_planning | 에러 상태 식별(크래시, 권한 거부, 네트워크 실패, UAC), 원인 진단, 복구 액션 생성 |
| 3 | `web_navigation` | 브라우저/웹 상호작용 | 0.12 | browser_control, form_interaction, tab_management, popup_handling, search_strategy, content_extraction | 브라우저 자동화: URL, 폼, 탭, 쿠키/팝업, CAPTCHA 감지, 로그인 흐름, 콘텐츠 추출 |
| 4 | `code_generation` | 코드 작성/디버깅/실행 | 0.08 | code_writing, debugging, terminal_commands, ide_interaction, build_systems, testing | Python, JS, PowerShell, 배치 스크립트 생성. IDE 상호작용, 빌드/테스트 사이클 |
| 5 | `file_system` | 파일/디렉토리 조작 | 0.08 | file_operations, directory_management, permission_handling, search_utilities, compression, path_resolution | 파일 CRUD, 권한 변경, 압축, 디렉토리 탐색 (Windows/Linux/macOS) |
| 6 | `natural_language_understanding` | 의도 파싱/다국어 이해 | 0.10 | intent_classification, parameter_extraction, ambiguity_resolution, korean_nlp, command_mapping | 자연어 명령 파싱 (한국어/영어/혼합), 모호성 해소, 파라미터 추출, OS 작업 매핑 |
| 7 | `safety_ethics` | 안전 가드레일/윤리 | 0.10 | safety_validation, permission_checking, malware_detection, consent_verification, audit_logging, ethical_boundaries | 악성 명령 차단, 데이터 파괴 방지, 동의 검증, 소셜 엔지니어링 탐지, 감사 로그 |
| 8 | `data_analysis` | 데이터 처리/분석/시각화 | 0.06 | data_processing, statistical_analysis, visualization, spreadsheet_ops, database_queries, report_generation | 스프레드시트, 데이터 클리닝, 통계 분석, 차트, CSV/JSON, DB 쿼리, 보고서 |
| 9 | `system_administration` | OS 설정/시스템 관리 | 0.08 | system_config, service_management, registry_ops, network_config, hardware_diagnostics, task_scheduling | 시스템 설정, 서비스 제어, 레지스트리, 환경변수, 네트워크, 드라이버, 스케줄링 |
| 10 | `text_composition` | 문서 작성/텍스트 편집 | 0.05 | document_writing, email_composition, report_structuring, presentation_creation, formatting | 문서/이메일/보고서/프레젠테이션 작성, 서식, 문법 검사 |
| 11 | `visual_design` | 그래픽/UI 디자인/이미지 편집 | 0.05 | image_editing, layout_design, color_management, typography, asset_creation | Paint/PPT/디자인 도구로 이미지 편집, 색상/레이아웃/타이포/에셋 관리 |
| 12 | `memory_context` | 작업 메모리/컨텍스트 추적 | 0.06 | context_tracking, state_persistence, spatial_memory, progress_tracking, episodic_recall | 대화 컨텍스트 유지, 다단계 진행 추적, UI 요소 위치 기억, 에피소드 회상 |
| 13 | `planning_strategy` | 고수준 태스크 계획/분해 | 0.08 | task_decomposition, dependency_analysis, time_estimation, replanning, execution_optimization | 복잡 목표→하위작업 분해, 시간/단계 예측, 재계획, 의존성 분석, 실행 최적화 |
| 14 | `input_method` | 키보드/마우스/IME/접근성 입력 | 0.10 | ime_management, shortcut_execution, mouse_targeting, drag_drop, scroll_control, accessibility_input | 정밀 입력: IME 상태(한/영 전환), 마우스 좌표, 드래그앤드롭, 스크롤, 접근성 |
| 15 | `app_specific` | 앱별 상호작용 패턴 | 0.06 | chrome_patterns, vscode_patterns, office_patterns, terminal_patterns, explorer_patterns, settings_patterns | Chrome, VS Code, MS Office, Paint, Terminal, 파일 탐색기 등 앱별 UI 패턴/워크플로 |

### 라우팅 바이어스 분포

```
Expert 0  (os_action_planner)      ████████████████  0.15  ★ Primary
Expert 1  (screen_understanding)   ████████████████  0.15  ★ Primary
Expert 2  (error_recovery)         █████████████     0.12
Expert 3  (web_navigation)         █████████████     0.12
Expert 4  (code_generation)        █████████         0.08
Expert 5  (file_system)            █████████         0.08
Expert 6  (natural_language)       ███████████       0.10
Expert 7  (safety_ethics)          ███████████       0.10
Expert 8  (data_analysis)          ███████           0.06
Expert 9  (system_admin)           █████████         0.08
Expert 10 (text_composition)       ██████            0.05
Expert 11 (visual_design)          ██████            0.05
Expert 12 (memory_context)         ███████           0.06
Expert 13 (planning_strategy)      █████████         0.08
Expert 14 (input_method)           ███████████       0.10
Expert 15 (app_specific)           ███████           0.06
```

### 기능 클러스터 분류

| 클러스터 | 전문가 | 역할 |
|----------|--------|------|
| **지각/인식** (Perception) | 1, 14 | 화면 이해 + 입력 | 
| **계획/추론** (Planning) | 0, 13 | 액션 계획 + 태스크 분해 |
| **실행/행동** (Execution) | 3, 4, 5, 9 | 웹/코드/파일/시스템 조작 |
| **안전/검증** (Safety) | 2, 7 | 에러 복구 + 안전 가드레일 |
| **언어/생성** (Language) | 6, 10 | NLU + 문서 작성 |
| **메모리/컨텍스트** (Memory) | 12 | 상태 추적 + 기억 |
| **창의/시각** (Creative) | 8, 11 | 데이터 분석 + 디자인 |
| **지식/패턴** (Knowledge) | 15 | 앱별 전문 지식 |

---

## 3. 신규 4개 전문가 상세 분석

### 전문가별 구성

| # | 이름 | 도메인 | 바이어스 | 도너 (기존) | 블렌드 가중치 |
|---|------|--------|----------|-------------|---------------|
| 16 | `visual_grounding` | 픽셀 정밀 UI 요소 위치 특정 | 0.15 | 0, 4, 8, 12 | 0.35, 0.25, 0.25, 0.15 |
| 17 | `workflow_orchestrator` | 크로스앱 워크플로 실행 | 0.12 | 1, 5, 9, 13 | 0.20, 0.30, 0.30, 0.20 |
| 18 | `verification_oracle` | 액션 검증 및 결과 확인 | 0.13 | 2, 6, 10, 14 | 0.20, 0.25, 0.30, 0.25 |
| 19 | `adaptive_retry` | 지능형 실패 복구 및 대안 전략 | 0.10 | 3, 7, 11, 15 | 0.25, 0.25, 0.25, 0.25 |

### SVD 변환 파라미터

| # | SVD 회전각 | SV 변조 강도 | SV 변조 위상 | Rank-r 섭동 크기 | Rank |
|---|-----------|-------------|-------------|-----------------|------|
| 16 | 30° | 0.25 | 0 | 18% | 32 |
| 17 | 25° | 0.20 | π/4 | 15% | 32 |
| 18 | 35° | 0.30 | π/2 | 20% | 32 |
| 19 | 22° | 0.22 | 3π/4 | 16% | 32 |

### 깊이 보정 (depth_factor)

```
depth_factor = 1.0 - 0.4 × (layer_idx / 47)

Layer 0  (가장 얕은 층): depth_factor = 1.00 → 풀 스트렝스
Layer 12 (1/4 지점):     depth_factor = 0.90
Layer 24 (중간):         depth_factor = 0.80
Layer 36 (3/4 지점):     depth_factor = 0.69
Layer 47 (가장 깊은 층): depth_factor = 0.60 → 40% 감쇄
```

원리: 깊은 층은 더 추상적인 특징을 인코딩하므로 같은 크기의 섭동에도 더 민감 → 크기 축소

### 도너 선정 분석 (정당성 평가)

| 신규 전문가 | 도너 | 도너 이름 | 의미적 관련성 |
|------------|------|----------|-------------|
| **16 (visual_grounding)** | 0 | os_action_planner | ✅ 좋음 — 액션 계획에서 UI 요소 식별 필요 |
| | 4 | code_generation | ⚠️ 약함 — 코드 생성과 시각 그라운딩 관련성 낮음 |
| | 8 | data_analysis | ⚠️ 약함 — 데이터 분석과 UI 위치 특정 관련성 낮음 |
| | 12 | memory_context | ✅ 좋음 — 공간 메모리가 요소 위치 추적에 도움 |
| **17 (workflow_orchestrator)** | 1 | screen_understanding | ✅ 좋음 — 워크플로에서 화면 상태 파악 필요 |
| | 5 | file_system | ✅ 좋음 — 크로스앱 워크플로에 파일 전송 포함 |
| | 9 | system_administration | ✅ 좋음 — 시스템 수준 조작 포함 |
| | 13 | planning_strategy | ✅ 매우 좋음 — 워크플로 계획 = 태스크 분해 |
| **18 (verification_oracle)** | 2 | error_recovery | ✅ 매우 좋음 — 에러 감지 = 검증 실패 감지 |
| | 6 | natural_language_understanding | ⚠️ 보통 — NLU가 검증 결과 해석에 도움 |
| | 10 | text_composition | ❌ 약함 — 문서 작성과 액션 검증 무관 |
| | 14 | input_method | ✅ 좋음 — 입력 결과 검증에 도움 |
| **19 (adaptive_retry)** | 3 | web_navigation | ✅ 좋음 — 웹에서 대안 경로 탐색 |
| | 7 | safety_ethics | ✅ 좋음 — 안전 제약 하 재시도 의사결정 |
| | 11 | visual_design | ❌ 약함 — 디자인과 실패 복구 무관 |
| | 15 | app_specific | ✅ 매우 좋음 — 앱별 대안 전략 필요 |

### 도너 선정 문제점

현재 도너 매핑은 **stride-4 패턴** (0,4,8,12 / 1,5,9,13 / ...)을 사용한다:
- **장점**: 16개 전문가 인덱스 공간에서 균등 분산, 가중치 다양성 최대화
- **단점**: 의미적 관련성이 아닌 인덱스 간격 기반 — 일부 도너-수혜 관계가 부적절
- **특히 문제가 되는 조합**:
  - Expert 16 ← Expert 4 (code_generation): 코드 생성과 visual grounding 무관
  - Expert 18 ← Expert 10 (text_composition): 문서 작성과 verification 무관
  - Expert 19 ← Expert 11 (visual_design): 디자인과 adaptive retry 무관

---

## 4. 의미 기반 최적 도너 매핑 (권장 변경)

현재 stride-4 패턴의 약점을 보완하여, **의미적 관련성에 기반한 도너 매핑**을 제안한다:

### 제안: 개선된 DONOR_MAP

| 신규 전문가 | 현재 도너 | 제안 도너 | 근거 |
|------------|----------|----------|------|
| **16 (visual_grounding)** | 0, 4, 8, 12 | **0, 1, 14, 12** | 0(액션계획)+1(화면이해)+14(입력방법/좌표)+12(공간메모리) |
| **17 (workflow_orchestrator)** | 1, 5, 9, 13 | **13, 0, 5, 15** | 13(태스크분해)+0(액션계획)+5(파일시스템)+15(앱별패턴) |
| **18 (verification_oracle)** | 2, 6, 10, 14 | **2, 1, 7, 12** | 2(에러감지)+1(화면이해)+7(안전검증)+12(상태추적) |
| **19 (adaptive_retry)** | 3, 7, 11, 15 | **2, 3, 7, 15** | 2(에러복구)+3(웹탐색)+7(안전)+15(앱별대안) |

### 제안: 개선된 블렌드 가중치

```python
OPTIMAL_DONOR_MAP = {
    16: {  # visual_grounding — 화면 요소 위치 특정
        "name": "visual_grounding",
        "donors": [0, 1, 14, 12],
        "blend_weights": [0.25, 0.35, 0.25, 0.15],  # screen_understanding 주력
        "routing_bias": 0.15,
    },
    17: {  # workflow_orchestrator — 크로스앱 조율
        "name": "workflow_orchestrator",
        "donors": [13, 0, 5, 15],
        "blend_weights": [0.30, 0.25, 0.25, 0.20],  # planning_strategy 주력
        "routing_bias": 0.12,
    },
    18: {  # verification_oracle — 검증/확인
        "name": "verification_oracle",
        "donors": [2, 1, 7, 12],
        "blend_weights": [0.30, 0.30, 0.20, 0.20],  # error_detection + screen_check
        "routing_bias": 0.13,
    },
    19: {  # adaptive_retry — 지능형 재시도
        "name": "adaptive_retry",
        "donors": [2, 3, 7, 15],
        "blend_weights": [0.30, 0.25, 0.25, 0.20],  # error_recovery 주력
        "routing_bias": 0.10,
    },
}
```

### 차이점 요약

| 변경 | 현재 | 제안 | 효과 |
|------|------|------|------|
| Expert 16 도너 | 4(code), 8(data) | 1(screen), 14(input) | 시각적 위치 특정에 더 적합한 기반 |
| Expert 17 도너 | 1(screen) | 0(action), 15(app) | 워크플로 계획+앱 전환에 최적화 |
| Expert 18 도너 | 6(NLU), 10(text) | 1(screen), 7(safety) | 화면 비교+안전 검증에 최적화 |
| Expert 19 도너 | 11(design) | 2(error) | 에러 복구 경험 활용 |

> **주의**: 도너 매핑 변경 시 `inject_experts.py` 재실행 + 모든 safetensors 재생성 필요.
> 이미 NF4 양자화된 상태라면 원본 bf16 가중치에서부터 재수술해야 함.

---

## 5. 변환 수학 상세

### 5단계 파이프라인 수식

$$W_{\text{new}} = \text{orthogonalize}\left( U_{\text{rot}} \cdot \text{diag}(S_{\text{mod}}) \cdot V^H + A \cdot B \cdot \frac{\alpha \|W_{\text{blend}}\|}{\|AB\|} \right)$$

여기서:

| 기호 | 정의 |
|------|------|
| $W_{\text{blend}} = \sum_i w_i \cdot W_{\text{donor}_i}$ | 가중 도너 혼합 |
| $U, S, V^H = \text{SVD}(W_{\text{blend}})$ | 특이값 분해 |
| $U_{\text{rot}}$ | 상위 64개 특이벡터 쌍에 Givens 회전 적용 |
| $S_{\text{mod}[j]} = S_j \cdot \max(1 + m \cdot \sin(\frac{2\pi j}{k} + \phi), 0.3)$ | 사인파 특이값 변조 |
| $A \in \mathbb{R}^{d_1 \times 32}, B \in \mathbb{R}^{32 \times d_2}$ | 결정론적 rank-32 섭동 |
| $\alpha$ | 가중치 노름의 15-20% 목표 크기 |
| orthogonalize | 4개 신규 전문가 간 Gram-Schmidt 직교화 |

### NF4 양자화 노이즈 대비 변환 크기

```
NF4 노이즈 하한:  ████  ~1-2% (양자화 오차)
─────────────────────────────────────────────
Expert 16 변환:   ████████████████████████████████████  ~25% (30°회전 + 18%섭동 + 25%변조)
Expert 17 변환:   ██████████████████████████████       ~21% (25°회전 + 15%섭동 + 20%변조)
Expert 18 변환:   ████████████████████████████████████████  ~30% (35°회전 + 20%섭동 + 30%변조)
Expert 19 변환:   ██████████████████████████████       ~22% (22°회전 + 16%섭동 + 22%변조)
```

모든 변환이 NF4 노이즈 바닥보다 **10배 이상** 크므로, 양자화 후에도 전문가 고유성이 유지된다.

### 예상 코사인 유사도

| 비교 대상 | 예상 유사도 | 평가 |
|----------|-----------|------|
| 신규 전문가 ↔ 도너 블렌드 | 0.85 – 0.95 | ✅ 충분한 차이 |
| 신규 전문가 ↔ 신규 전문가 | 0.75 – 0.90 | ✅ 상호 직교화로 다양성 보장 |
| NF4 양자화 ↔ 원본 bf16 | > 0.98 | 양자화 오차 |
| v1 노이즈 방식 (폐기) | > 0.999 | ❌ 기능적 동일 → NF4에 흡수 |

---

## 6. 라우터 학습 (train_router.py) 분석

### 6-Component Loss Function

$$\mathcal{L}_{\text{total}} = \mathcal{L}_{\text{spec}} + \lambda_{\text{cont}} \mathcal{L}_{\text{contrastive}} + \lambda_{\text{div}} \mathcal{L}_{\text{diversity}} + \lambda_{\text{dist}} \mathcal{L}_{\text{distillation}} + \lambda_{\text{bal}} \mathcal{L}_{\text{balance}} + \mathcal{L}_{\text{curriculum}}$$

| 손실 함수 | 역할 | 가중치 |
|-----------|------|--------|
| Specialization (CE) | 토큰→전문가 정확 매칭 | 1.0 |
| Contrastive | 같은 도메인 토큰끼리 가깝게, 다른 도메인은 멀게 | λ_cont |
| Diversity | 전문가 활성화 균등 분포 강제 | λ_div |
| Distillation (MSE) | 원본 라우터 출력과의 정합성 | λ_dist |
| Load Balance (CoV) | 전문가 부하 변동계수 최소화 | λ_bal |
| Curriculum | 3단계 난이도 증가 (쉬운→중간→어려운 예제) | 자동 |

### 신규 전문가 학습률 스케일링

```
Original experts (0-15): base LR × 1.0
New experts (16-19):     base LR × 3.0  ← 3배 가속
```

목적: 신규 전문가가 라우터에서 충분한 활성화 확률을 획득하도록 가속

---

## 7. 파인튜닝 3단계 스케줄

### Phase 1: Expert Warmup (2 epoch)
```
동결: Expert 0-15 (기존 16개)
학습: Expert 16-19 (신규 4개) + Router (LR × 0.1)
LR: 2e-5
목적: 신규 전문가가 도메인별 특화 학습 데이터로 기초 능력 획득
```

### Phase 2: Router Calibration (1 epoch)
```
동결: Expert 0-19 (전체)
학습: Router만 (LR × 1.0)
LR: 1e-5
목적: 라우터가 20개 전문가에 대한 최적 디스패치 학습
```

### Phase 3: Full Fine-tune (3 epoch)
```
학습: 전체 (Expert 0-19 + Router)
LR: 5e-6, LoRA rank=64, alpha=128
Target: q_proj, k_proj, v_proj, o_proj, gate_proj, up_proj, down_proj
Router LR: × 0.5
목적: End-to-end 최적화, 전문가 간 시너지 극대화
```

---

## 8. 결론 및 권장 사항

### 현재 상태 평가

| 항목 | 점수 | 비고 |
|------|------|------|
| 수술 파이프라인 (코드 품질) | 8/10 | v2.1 SVD 기반 구조적 변환은 견고 |
| NF4 양자화 생존성 | 9/10 | 15-25% 변환 vs 1-2% 노이즈 — 안전 마진 충분 |
| 도너 선정 논리 | 5/10 | stride-4 패턴은 기계적, 의미 기반이 아님 |
| 라우터 학습 설계 | 8/10 | 6-component loss + curriculum은 강력 |
| 학습 데이터 충실도 | 7/10 | 전문가별 특화 데이터 있으나, 양이 제한적 (~500/전문가) |
| 전체 아키텍처 타당성 | 7/10 | 실용적 접근이나, 도너 최적화로 개선 여지 |

### 핵심 권장 사항

1. **도너 매핑 개선** (§4 참조): stride-4 → 의미 기반 매핑으로 변경 시 파인튜닝 효율 개선 예상
2. **학습 데이터 증강**: 전문가별 500→2000+ 예제로 확대 (특히 verification_oracle)
3. **Expert 18 (verification) 강화**: 가장 중요한 전문가 — 에이전트 신뢰성의 핵심
4. **전문가 활성화 모니터링**: 파인튜닝 중 전문가별 활성화 빈도 로깅 추가 필요
5. **A/B 테스트**: stride-4 도너 vs 의미 기반 도너로 양쪽 수술 수행 후 비교 평가

---

*End of Expert Analysis Report*
