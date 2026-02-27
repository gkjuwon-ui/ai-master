# OSEN-1.0 Dataset Budget Plan

> 디스코드 데이터셋 제너레이터 (DeepSeek V3 토론 + R1 심판) 기반
> 5 도메인 × 4 난이도 = **20가지 조합**별 목표 수량 & 예산 산정

---

## 도메인 × 난이도 매트릭스

|  | `easy` | `medium` | `hard` | `expert` |
|---|---|---|---|---|
| `computer_ops` | ✅ | ✅ | ✅ | ✅ |
| `web_ops` | ✅ | ✅ | ✅ | ✅ |
| `ethics` | ✅ | ✅ | ✅ | ✅ |
| `cross_app` | ✅ | ✅ | ✅ | ✅ |
| `error_recovery` | ✅ | ✅ | ✅ | ✅ |

---

## 1. 샘플당 비용 산정

### DeepSeek API 가격 (2025–2026 기준)

| 모델 | 용도 | Input | Output |
|---|---|---|---|
| DeepSeek V3 (`deepseek-chat`) | Debater A, B | $0.27/M tokens | $1.10/M tokens |
| DeepSeek R1 (`deepseek-reasoner`) | Mediator, Judge | $0.55/M tokens | $2.19/M tokens |

### 난이도별 샘플당 예상 토큰 / 비용

| 난이도 | 토론 턴수 | V3 출력 (A+B) | R1 출력 (Med+Judge) | 총 입력 | **샘플당 비용** |
|---|---|---|---|---|---|
| `easy` | 4–6턴 | ~12K tok | ~5K tok | ~20K tok | **~$0.04** |
| `medium` | 6–8턴 | ~16K tok | ~6K tok | ~30K tok | **~$0.06** |
| `hard` | 8–12턴 | ~22K tok | ~8K tok | ~45K tok | **~$0.09** |
| `expert` | 10–14턴 | ~28K tok | ~10K tok | ~60K tok | **~$0.12** |

> ⚠️ Pass rate ~60–80% 예상. REJECT 시 재시도 비용 포함하면 **실제 비용 = 위 금액 × 1.5~2배**.

### 실제 수용 비용 (재시도 포함)

| 난이도 | Pass Rate | 재시도 포함 **실제 비용/샘플** |
|---|---|---|
| `easy` | ~80% | **~$0.05** |
| `medium` | ~70% | **~$0.09** |
| `hard` | ~60% | **~$0.15** |
| `expert` | ~50% | **~$0.24** |

---

## 2. 예산별 데이터셋 수량 계획

### 🟢 Tier 1: 최소 — $30 (테스트/프로토타입)

> 모델 성능: 기본 동작 확인 수준. 프로덕션 부적합.

| 도메인 | easy | medium | hard | expert | 소계 |
|---|---|---|---|---|---|
| `computer_ops` | 15 | 20 | 10 | 5 | **50** |
| `web_ops` | 15 | 20 | 10 | 5 | **50** |
| `ethics` | 10 | 15 | 8 | 3 | **36** |
| `cross_app` | 10 | 15 | 8 | 3 | **36** |
| `error_recovery` | 10 | 15 | 8 | 3 | **36** |
| **합계** | **60** | **85** | **44** | **19** | **208** |

| 항목 | 값 |
|---|---|
| 총 샘플 | 208 |
| 예상 비용 | ~$20–30 |
| 생성 시간 | ~3–4시간 |
| 용도 | 파이프라인 테스트, 빠른 검증 |

---

### 🔵 Tier 2: 표준 — $100 (최소 실용)

> 모델 성능: 기본 과제 수행 가능. 엣지케이스 취약.

| 도메인 | easy | medium | hard | expert | 소계 |
|---|---|---|---|---|---|
| `computer_ops` | 40 | 60 | 40 | 15 | **155** |
| `web_ops` | 40 | 60 | 40 | 15 | **155** |
| `ethics` | 25 | 40 | 25 | 10 | **100** |
| `cross_app` | 25 | 40 | 25 | 10 | **100** |
| `error_recovery` | 25 | 40 | 25 | 10 | **100** |
| **합계** | **155** | **240** | **155** | **60** | **610** |

| 항목 | 값 |
|---|---|
| 총 샘플 | 610 |
| 예상 비용 | ~$70–100 |
| 생성 시간 | ~8–12시간 |
| 용도 | 소규모 배포, MVP |

---

### 🟡 Tier 3: 권장 — $300 (실전 배포)

> 모델 성능: 대부분의 시나리오에서 안정적 동작. 권장 최소선.

| 도메인 | easy | medium | hard | expert | 소계 |
|---|---|---|---|---|---|
| `computer_ops` | 80 | 150 | 100 | 40 | **370** |
| `web_ops` | 80 | 150 | 100 | 40 | **370** |
| `ethics` | 50 | 100 | 70 | 25 | **245** |
| `cross_app` | 50 | 100 | 70 | 25 | **245** |
| `error_recovery` | 50 | 100 | 70 | 25 | **245** |
| **합계** | **310** | **600** | **410** | **155** | **1,475** |

| 항목 | 값 |
|---|---|
| 총 샘플 | 1,475 |
| 예상 비용 | ~$200–300 |
| 생성 시간 | ~24–36시간 |
| 용도 | **프로덕션 권장 최소선** |

---

### 🟠 Tier 4: 고급 — $600 (견고한 프로덕션)

> 모델 성능: 엣지케이스 포함 안정적. 대부분의 사용자 시나리오 커버.

| 도메인 | easy | medium | hard | expert | 소계 |
|---|---|---|---|---|---|
| `computer_ops` | 150 | 300 | 200 | 80 | **730** |
| `web_ops` | 150 | 300 | 200 | 80 | **730** |
| `ethics` | 100 | 200 | 140 | 50 | **490** |
| `cross_app` | 100 | 200 | 140 | 50 | **490** |
| `error_recovery` | 100 | 200 | 140 | 50 | **490** |
| **합계** | **600** | **1,200** | **820** | **310** | **2,930** |

| 항목 | 값 |
|---|---|
| 총 샘플 | 2,930 |
| 예상 비용 | ~$400–600 |
| 생성 시간 | ~48–72시간 |
| 용도 | **안정적 프로덕션 배포** |

---

### 🔴 Tier 5: 최대 — $1,500+ (최고 품질)

> 모델 성능: 최고 수준. 전문가 수준 판단까지 커버.

| 도메인 | easy | medium | hard | expert | 소계 |
|---|---|---|---|---|---|
| `computer_ops` | 300 | 600 | 450 | 200 | **1,550** |
| `web_ops` | 300 | 600 | 450 | 200 | **1,550** |
| `ethics` | 200 | 400 | 300 | 120 | **1,020** |
| `cross_app` | 200 | 400 | 300 | 120 | **1,020** |
| `error_recovery` | 200 | 400 | 300 | 120 | **1,020** |
| **합계** | **1,200** | **2,400** | **1,800** | **760** | **6,160** |

| 항목 | 값 |
|---|---|
| 총 샘플 | 6,160 |
| 예상 비용 | ~$1,000–1,500 |
| 생성 시간 | ~5–7일 |
| 용도 | **최고 품질, 상용 서비스** |

---

## 3. 난이도 비중 근거

```
easy    : 20%  — 기초 패턴 학습. 빠르고 저렴. 과적합 방지용 기본 데이터.
medium  : 40%  — 핵심. 실사용자가 가장 많이 겪는 상황. 최다 비중.
hard    : 27%  — 복합 추론, 엣지케이스. 모델 차별화의 핵심.
expert  : 13%  — 최고 난이도. 비싸지만 소량으로도 성능 향상 큼.
```

### 도메인 비중 근거

```
computer_ops   : 25%  — 핵심 OS 조작. 가장 빈번하게 사용.
web_ops        : 25%  — 웹 자동화. computer_ops와 함께 메인.
ethics         : 17%  — 안전/윤리. 필수이나 상황 다양성이 적음.
cross_app      : 17%  — 앱 간 연동. 실무에서 자주 발생.
error_recovery : 17%  — 오류 복구. 강건성의 핵심.
```

---

## 4. 디스코드 명령어 예시

### Tier 3 (권장) 실행 예시

```bash
# computer_ops (370개)
/gen domain:computer_ops difficulty:easy count:80
/gen domain:computer_ops difficulty:medium count:150
/gen domain:computer_ops difficulty:hard count:100
/gen domain:computer_ops difficulty:expert count:40

# web_ops (370개)
/gen domain:web_ops difficulty:easy count:80
/gen domain:web_ops difficulty:medium count:150
/gen domain:web_ops difficulty:hard count:100
/gen domain:web_ops difficulty:expert count:40

# ethics (245개)
/gen domain:ethics difficulty:easy count:50
/gen domain:ethics difficulty:medium count:100
/gen domain:ethics difficulty:hard count:70
/gen domain:ethics difficulty:expert count:25

# cross_app (245개)
/gen domain:cross_app difficulty:easy count:50
/gen domain:cross_app difficulty:medium count:100
/gen domain:cross_app difficulty:hard count:70
/gen domain:cross_app difficulty:expert count:25

# error_recovery (245개)
/gen domain:error_recovery difficulty:easy count:50
/gen domain:error_recovery difficulty:medium count:100
/gen domain:error_recovery difficulty:hard count:70
/gen domain:error_recovery difficulty:expert count:25
```

> 💡 한 번에 너무 큰 count를 주면 디코 타임아웃 가능. **count:50 이하** 단위로 나눠서 실행 권장.

---

## 5. 전체 파인튜닝 파이프라인

```
┌──────────────────────────────────┐
│ 1. 4-Expert MoE 트레이닝         │  ← osen_expert_config 기반
│    (Phase 1→2→3→4)               │     expert-specific 데이터
│    scripts/moe_surgery/          │
│    generate_training_data.py     │
└──────────┬───────────────────────┘
           │ OSEN-1.0 (4-expert 완료)
           ▼
┌──────────────────────────────────┐
│ 2. 전체 파인튜닝 (General SFT)   │  ← 이 문서의 데이터셋
│    디코봇 debate 데이터           │     20개 조합 전체
│    datasets/training.jsonl       │
│                                  │
│    python finetune_osen.py       │
│      --phase 3                   │     Phase 3: 전체 프로젝션 LoRA
│      --dataset datasets/         │
│        training.jsonl            │
│      --merge                     │
└──────────┬───────────────────────┘
           │ OSEN-1.0 (최종)
           ▼
        배포 준비 완료
```

### 전체 파인튜닝 설정

| 파라미터 | 값 | 비고 |
|---|---|---|
| Phase | 3 (Full fine-tune) 또는 별도 Phase 5 | 4-expert 트레이닝 후 추가 SFT |
| Learning Rate | 2e-6 ~ 5e-6 | 이미 fine-tuned이므로 낮게 |
| Epochs | 2–3 | 과적합 방지 |
| LoRA rank | 64 | 전체 프로젝션 |
| LoRA targets | q,k,v,o,gate,up,down_proj | 전체 |
| Batch size | 1 × grad_accum 16 | effective 16 |
| 데이터 형식 | LLaMA conversation JSONL | 디코봇 자동 생성 |

---

## 6. 예산 요약 비교

| Tier | 총 샘플 | API 비용 | GPU 학습 비용* | **총 예산** | 권장 대상 |
|---|---|---|---|---|---|
| 🟢 최소 | 208 | ~$25 | ~$15 | **~$40** | 테스트/검증 |
| 🔵 표준 | 610 | ~$85 | ~$15 | **~$100** | MVP/소규모 |
| 🟡 권장 | 1,475 | ~$250 | ~$20 | **~$270** | **프로덕션 최소** |
| 🟠 고급 | 2,930 | ~$500 | ~$25 | **~$525** | 안정적 상용 |
| 🔴 최대 | 6,160 | ~$1,250 | ~$40 | **~$1,290** | 최고 품질 |

> *GPU 학습 비용: A100 80GB RunPod 기준 ($1.64/hr × 학습 시간)

---

## 7. 추천

| 상황 | 추천 Tier |
|---|---|
| "일단 돌아가는지 보고 싶다" | 🟢 Tier 1 ($40) |
| "MVP 데모용" | 🔵 Tier 2 ($100) |
| "실제 서비스에 쓸 거다" | 🟡 **Tier 3 ($270)** |
| "품질 타협 없이 제대로" | 🟠 Tier 4 ($525) |
| "경쟁 AI 제품이다" | 🔴 Tier 5 ($1,290) |

> 💡 **Tier 3 (1,475개 / ~$270)가 가성비 최적점.** medium 600개가 핵심 → 여기서 모델 성능의 60%가 결정됨.

---

*OSEN-1.0 Dataset Budget Plan v1.0*
