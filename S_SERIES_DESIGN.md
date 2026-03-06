# S-SER1ES: Neural Surgery Engine

## "멍청한 뉴런을 찾아서 갈아끼운다"

> **목표**: LLaMA 3 8B → GPT-4o급 지능으로 끌어올리기 (어댑터 기반)
> **방법론**: Selective Reinforcement Learning (수술법 C)
> **출력 포맷**: `.srs` (Surgery adapter file)

---

## 1. 왜 이게 가능한가? — 근거

### 1.1 파라미터 효율성의 비밀

GPT-4o는 ~1.8T 파라미터 추정, LLaMA 3 8B는 8B.
크기 차이 225배인데, 실제 벤치마크 차이는 그렇게 크지 않음.

| 벤치마크 | LLaMA 3 8B | GPT-4o | 차이 |
|----------|-----------|--------|------|
| MMLU | 68.4% | 88.7% | 20.3%p |
| HumanEval | 62.2% | 90.2% | 28.0%p |
| GSM8K | 79.6% | 95.8% | 16.2%p |
| ARC-C | 78.6% | 96.4% | 17.8%p |

**핵심 인사이트**: 225배 큰 모델이 20~28%p밖에 안 이김.
→ LLaMA 3 8B의 대부분 뉴런은 이미 충분히 똑똑함
→ **일부 멍청한 뉴런만 고치면** 격차를 대폭 줄일 수 있음

### 1.2 Lottery Ticket Hypothesis 근거

"큰 네트워크 안에는 작은 서브넷이 있고, 그 서브넷만으로도 전체 성능을 낼 수 있다"
— Frankle & Carlin, 2019

역으로: **LLaMA 8B 안에도 GPT-4o급 서브넷이 잠재적으로 존재**
→ 멍청한 뉴런이 방해하고 있을 뿐
→ 방해하는 놈만 재교육시키면 됨

### 1.3 왜 전체 파인튜닝 대신 Selective RL인가?

| 방식 | 문제 |
|------|------|
| Full Fine-tuning | 8B 전체 업데이트 → 이미 똑똑한 뉴런까지 건드림 → catastrophic forgetting |
| LoRA | 전체에 low-rank 씌움 → 멍청한 놈이 어딘지 모르고 무차별 적용 |
| **S-SER1ES** | 멍청한 놈만 정확히 찾아서 그 놈만 RL → 외과적 정밀 수술 |

---

## 2. 전체 아키텍처

```
┌─────────────────────────────────────────────────────────────────┐
│                    S-SER1ES Pipeline                            │
│                                                                 │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐         │
│  │  PHASE 1    │    │  PHASE 2    │    │  PHASE 3    │         │
│  │  DIAGNOSE   │ →  │  SURGERY    │ →  │  VERIFY     │         │
│  │             │    │             │    │             │         │
│  │ "누가 바보?" │    │ "갈아끼우자"│    │ "성공했나?" │         │
│  └─────────────┘    └─────────────┘    └─────────────┘         │
│        │                  │                  │                  │
│        ▼                  ▼                  ▼                  │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐         │
│  │ Blame Map   │    │ Surgery     │    │ Surgery     │         │
│  │ (.blame)    │    │ Adapter     │    │ Report      │         │
│  │             │    │ (.srs)      │    │ (.srr)      │         │
│  └─────────────┘    └─────────────┘    └─────────────┘         │
│                                                                 │
│  ┌─────────────────────────────────────────────────────┐       │
│  │            Iterative Surgery Loop                    │       │
│  │  Diagnose → Surgery → Verify → Re-diagnose → ...    │       │
│  │  (점수가 목표에 도달할 때까지 반복)                   │       │
│  └─────────────────────────────────────────────────────┘       │
└─────────────────────────────────────────────────────────────────┘
```

---

## 3. PHASE 1: DIAGNOSE — 멍청한 뉴런 찾기

### 3.1 입력 데이터: Surgery Test Suite

GPT-4o급으로 올리려면, GPT-4o가 맞추고 LLaMA가 틀리는 문제만 모아야 함.

```python
SURGERY_TEST_SUITE = {
    "reasoning": [
        # GPT-4o: 정답 / LLaMA 3 8B: 오답인 문제들
        # 복잡한 다단계 추론, 수학, 논리
    ],
    "instruction_following": [
        # 복잡한 지시사항 정확히 따르기
        # "3번째 문장은 반드시 질문형으로, 5문장 이내, 각 문장 15단어 이하"
    ],
    "knowledge": [
        # 세계 지식, 팩트 정확도
    ],
    "coding": [
        # 코드 생성, 디버깅
    ],
    "safety": [
        # 유해 요청 거부, 편향 방지
    ]
}
```

### 3.2 Blame Attribution Algorithm

```
Algorithm: NeuronBlame(model, test_cases)
─────────────────────────────────────────
Input:  model (LLaMA 3 8B), test_cases (GPT-4o가 맞추고 LLaMA가 틀린 것)
Output: blame_map {parameter_id → blame_score}

1. FOR each test_case in test_cases:
   a. correct_answer = test_case.expected  (GPT-4o의 정답)
   b. model_answer = model.generate(test_case.prompt)
   c. IF model_answer ≈ correct_answer: SKIP  (이미 잘하는 건 패스)
   
   d. loss = CrossEntropyLoss(model_logits, correct_tokens)
   e. loss.backward()  # 역전파
   
   f. FOR each parameter p in model.parameters():
      gradient = p.grad
      blame = compute_blame(p, gradient)
      blame_map[p.id] += blame

2. NORMALIZE blame_map
3. RETURN blame_map
```

### 3.3 Blame Score 계산 — 3가지 지표

#### A. Gradient Blame (40%)
```
blame_gradient(p) = |grad(p)| × sign_alignment(grad(p), p)
```
- gradient 크기가 크면 → 이 파라미터가 loss에 큰 영향
- gradient 방향이 현재 값과 반대면 → "이 뉴런 방향이 틀렸다"
- **높을수록 멍청함**

#### B. Activation Anomaly (30%)
```
blame_activation(p) = entropy(activations_of_neuron(p))
```
- 뉴런의 activation 분포가 비정상적인지 확인
- Dead neuron (항상 0) → 쓸모없음 → blame 높음
- Saturated neuron (항상 max) → 구별력 없음 → blame 높음
- 적절한 분포 → 정상 → blame 낮음

#### C. Cross-task Consistency (30%)
```
blame_consistency(p) = stdev(blame_scores_across_tasks(p)) / mean(...)
```
- 여러 테스트에서 **일관되게** 멍청한 놈이 진짜 멍청한 놈
- 한 테스트에서만 blame 높은 건 우연일 수 있음
- **variation coefficient 낮고 mean 높으면** → 확실한 범인

#### 최종 Blame Score
```
blame_total(p) = 0.4 × blame_gradient(p) 
               + 0.3 × blame_activation(p)
               + 0.3 × blame_consistency(p)
```

### 3.4 Blame Map 구조

```json
{
  "model": "meta-llama/Meta-Llama-3-8B-Instruct",
  "total_parameters": 8030000000,
  "diagnosed_parameters": 8030000000,
  "blame_threshold": 0.85,
  "surgery_candidates": 80300000,
  "surgery_ratio": "1.0%",
  "layers": {
    "model.layers.0.self_attn.q_proj": {
      "total_params": 16777216,
      "blamed_params": 12543,
      "blame_scores": {
        "indices": [1024, 2048, 3071, ...],
        "scores": [0.95, 0.92, 0.91, ...]
      }
    },
    "model.layers.0.self_attn.k_proj": { ... },
    "model.layers.31.mlp.down_proj": { ... }
  },
  "blame_distribution": {
    "top_1pct_contribution": 0.34,
    "top_5pct_contribution": 0.67,
    "top_10pct_contribution": 0.82
  }
}
```

### 3.5 Blame Visualization

```
Layer-by-Layer Blame Heatmap:
Layer  0: ░░░░░░░░░░░░░░░░░░░░ (blame: 0.12) — 건강
Layer  1: ░░░░░░░░░░░░░░░░░░░░ (blame: 0.15) — 건강
Layer  2: ░░░░░░██░░░░░░░░░░░░ (blame: 0.31) — 주의
...
Layer 14: ░░░░████████░░░░░░░░ (blame: 0.62) — 수술 필요!
Layer 15: ░░██████████████░░░░ (blame: 0.78) — 심각!
Layer 16: ░░░░████████░░░░░░░░ (blame: 0.58) — 수술 필요!
...
Layer 31: ░░░░░░░░░░░░░░░░░░░░ (blame: 0.18) — 건강

>> Layer 14-16 MLP 영역에 멍청한 뉴런 집중 발견!
>> 전체 파라미터의 1.2%가 오답의 67%를 담당
```

---

## 4. PHASE 2: SURGERY — Selective RL로 갈아끼우기

### 4.1 수술 대상 선정

```
Algorithm: SelectSurgeryTargets(blame_map, budget)
─────────────────────────────────────────────────
Input:  blame_map, surgery_budget (전체의 몇 % 수술할지)
Output: surgery_mask (어떤 파라미터를 수술할지 boolean mask)

1. ranked = SORT blame_map BY blame_score DESC
2. threshold = ranked[int(len(ranked) * budget)]
3. surgery_mask = {p: blame_score(p) > threshold}
4. RETURN surgery_mask
```

**수술 예산 전략**:
| 라운드 | 수술 범위 | 이유 |
|--------|----------|------|
| Round 1 | 상위 0.5% | 가장 확실한 범인만 먼저 |
| Round 2 | 상위 1.0% | 1차 수술 결과 보고 확대 |
| Round 3 | 상위 2.0% | 점진적 확대 |
| Round N | 최대 5.0% | 부작용 없는 범위 내 최대 |

### 4.2 Selective RL 엔진 — 핵심

#### 기본 원리: Frozen Majority + Trainable Minority

```python
# 수술 핵심 코드 컨셉
for name, param in model.named_parameters():
    if name in surgery_mask:
        param.requires_grad = True   # 수술 대상: 학습 ON
    else:
        param.requires_grad = False  # 멀쩡한 놈: 절대 건드리지 마

# 전체 8B 중 0.5~5%만 requires_grad = True
# → GPU 메모리 극적 절약
# → 멀쩡한 뉴런 보호 (catastrophic forgetting 방지)
```

#### RL 알고리즘: Modified DPO (Direct Preference Optimization)

풀 PPO는 critic 모델까지 필요해서 무겁고, DPO가 더 가벼움.
근데 일반 DPO도 전체 파라미터를 건드리니까, **Masked DPO** 사용:

```
Algorithm: MaskedDPO(model, surgery_mask, preference_data)
──────────────────────────────────────────────────────────
Input:  model, surgery_mask, preference_pairs [(chosen, rejected)]
Output: surgically_updated_model

1. FREEZE all parameters where surgery_mask[p] == False
2. FOR each batch in preference_data:
   a. chosen_logps = model.log_prob(batch.chosen)
   b. rejected_logps = model.log_prob(batch.rejected)
   c. ref_chosen_logps = ref_model.log_prob(batch.chosen)  # 수술 전 모델 (frozen copy)
   d. ref_rejected_logps = ref_model.log_prob(batch.rejected)
   
   e. loss_dpo = -log(σ(β × ((chosen_logps - ref_chosen_logps) 
                             - (rejected_logps - ref_rejected_logps))))
   
   f. loss_dpo.backward()
   
   g. # 핵심: surgery_mask에 해당하는 파라미터만 gradient 적용
   h. FOR each param in model.parameters():
        IF param NOT IN surgery_mask:
            param.grad = None  # 이중 안전장치
   
   i. optimizer.step()

3. RETURN model
```

### 4.3 Preference Data 생성 — GPT-4o를 Teacher로

LLaMA 3 8B를 GPT-4o급으로 올리려면, GPT-4o의 답변을 "정답"으로 써야 함:

```
Preference Pair 생성:

prompt: "삼각형의 내각의 합이 180도가 아닌 경우를 설명해주세요"

chosen (GPT-4o의 답):
"유클리드 기하학에서는 삼각형의 내각의 합이 항상 180°이지만,
 비유클리드 기하학에서는 다릅니다. 구면 기하학에서는 180°보다 크고,
 쌍곡 기하학에서는 180°보다 작습니다..."

rejected (LLaMA 3 8B의 답):
"삼각형의 내각의 합은 항상 180도입니다. 이것은 수학적으로
 증명된 사실이며..."

→ 이 pair를 Masked DPO에 넣으면,
  멍청한 뉴런이 "아 삼각형 내각 합 항상 180도 아니구나" 학습
  멀쩡한 뉴런은 건드리지 않음
```

### 4.4 Surgery-Aware Learning Rate

멍청한 정도에 따라 학습률 차등 적용:

```python
def get_surgery_lr(param_id, blame_score, base_lr=2e-5):
    """
    blame_score 높을수록 → 더 세게 교정
    낮을수록 → 살살 건드림
    """
    # blame 0.85~0.90: 살살 (0.5x)
    # blame 0.90~0.95: 보통 (1.0x)
    # blame 0.95~1.00: 세게 (2.0x)
    
    if blame_score >= 0.95:
        return base_lr * 2.0   # 확실한 바보 → 세게 교정
    elif blame_score >= 0.90:
        return base_lr * 1.0   # 좀 바보 → 보통
    else:
        return base_lr * 0.5   # 약간 바보 → 살살
```

### 4.5 Anti-Forgetting Guard

수술 중 멀쩡한 기능이 망가지지 않게 하는 안전장치:

```
Guard 1: KL Divergence Monitoring
→ 수술 전 모델과 수술 후 모델의 출력 분포 차이 모니터링
→ KL > threshold이면 수술 중단
→ "이 수술이 다른 영역까지 영향을 미치고 있다" 경고

Guard 2: Anchor Test Suite
→ LLaMA가 이미 잘하는 문제 100개를 수술 전에 저장
→ 매 수술 step마다 anchor 점수 체크
→ anchor 점수 2%p 이상 떨어지면 rollback

Guard 3: Parameter Distance Limit
→ 각 수술 대상 파라미터의 원래 값에서 최대 이동 거리 제한
→ ||p_new - p_original|| < max_distance
→ 너무 멀리 가면 클리핑
```

---

## 5. PHASE 3: VERIFY — 수술 검증

### 5.1 Multi-Dimensional Verification

```
┌──────────────────────────────────────────────────────┐
│           Surgery Verification Suite                  │
├──────────────────────────────────────────────────────┤
│                                                      │
│  1. TARGET IMPROVEMENT TEST                          │
│     └─ 수술 목표였던 영역에서 실제로 개선됐나?        │
│     └─ GPT-4o와의 격차가 줄었나?                     │
│                                                      │
│  2. SIDE EFFECT TEST                                 │
│     └─ 수술 안 한 영역에서 성능 하락은 없나?          │
│     └─ Anchor 테스트 통과?                           │
│                                                      │
│  3. CONSISTENCY TEST                                 │
│     └─ 같은 질문 10번 해서 답이 일관적인가?           │
│     └─ temperature 0.0~1.0 스펙트럼 테스트           │
│                                                      │
│  4. STRESS TEST                                      │
│     └─ 극한 입력 (문장 2048토큰, 다국어, 특수문자)    │
│     └─ 수술 전보다 견고한가?                         │
│                                                      │
│  5. HEAD-TO-HEAD vs GPT-4o                           │
│     └─ 동일 프롬프트로 둘 다 답변                    │
│     └─ blind evaluation (어느게 GPT-4o인지 모르고 평가)│
│                                                      │
└──────────────────────────────────────────────────────┘
```

### 5.2 Surgery Report (.srr)

```json
{
  "surgery_id": "SRS-20260306-001",
  "model": "meta-llama/Meta-Llama-3-8B-Instruct",
  "target": "GPT-4o parity",
  "surgery_method": "Masked DPO (Selective RL)",
  
  "diagnosis": {
    "total_blamed_params": 80300000,
    "surgery_ratio": "1.0%",
    "top_blame_layers": ["layer.14.mlp", "layer.15.mlp", "layer.16.attn"],
    "blame_categories": {
      "reasoning": 45,
      "knowledge": 30,
      "instruction_following": 15,
      "coding": 10
    }
  },
  
  "surgery_result": {
    "rounds_performed": 3,
    "total_preference_pairs": 5000,
    "training_steps": 1500,
    "gpu_hours": 4.2,
    
    "before_vs_after": {
      "MMLU":      { "before": 68.4, "after": 78.2, "delta": "+9.8",  "gpt4o": 88.7 },
      "HumanEval": { "before": 62.2, "after": 76.8, "delta": "+14.6", "gpt4o": 90.2 },
      "GSM8K":     { "before": 79.6, "after": 88.1, "delta": "+8.5",  "gpt4o": 95.8 },
      "ARC-C":     { "before": 78.6, "after": 87.3, "delta": "+8.7",  "gpt4o": 96.4 }
    },
    
    "side_effects": {
      "anchor_score_change": "-0.3%",
      "kl_divergence": 0.012,
      "verdict": "SAFE"
    }
  },
  
  "adapter_file": "adapter_model.srs",
  "adapter_size_mb": 82.5,
  "compatibility": "PEFT-compatible"
}
```

---

## 6. Iterative Surgery Loop — 반복 수술

한 번에 GPT-4o급은 안 됨. 여러 라운드 반복:

```
Round 1: "추론력 수술"
─────────────────────
  Target: reasoning 영역 멍청한 뉴런
  Data: GSM8K, ARC, MATH에서 GPT-4o가 맞추고 LLaMA가 틀린 문제
  Surgery budget: 0.5%
  Expected gain: MMLU +3~5%p

Round 2: "코딩 수술"  
─────────────────────
  Target: coding 영역 멍청한 뉴런 (Round 1에서 수술한 뉴런은 제외)
  Data: HumanEval, MBPP에서 차이나는 문제
  Surgery budget: 0.5% (누적 1.0%)
  Expected gain: HumanEval +5~8%p

Round 3: "지식 수술"
─────────────────────
  Target: knowledge 영역
  Data: TriviaQA, NaturalQuestions 차이나는 문제
  Surgery budget: 0.5% (누적 1.5%)
  Expected gain: MMLU +2~3%p 추가

Round 4: "지시 따르기 수술"
─────────────────────────
  Target: instruction following
  Data: IFEval, MT-Bench 차이나는 문제  
  Surgery budget: 0.5% (누적 2.0%)
  Expected gain: MT-Bench +0.5~1.0

Round 5+: "미세 조정 수술"
─────────────────────────
  Target: 이전 라운드에서 개선 안 된 영역 재진단
  Surgery budget: 점진적 확대
  종료 조건: GPT-4o 대비 5%p 이내 도달 OR 더이상 개선 없음
```

### 6.1 Surgery Stack (.srs 누적)

```
base_model (LLaMA 3 8B)
    ↓
  + surgery_round1.srs (추론력 수술)
    ↓
  + surgery_round2.srs (코딩 수술)
    ↓
  + surgery_round3.srs (지식 수술)
    ↓
  + surgery_round4.srs (지시 수술)
    ↓
  = S-SER1ES Enhanced LLaMA 3 8B
    (GPT-4o급 지능 어댑터 스택)
```

각 `.srs`는 독립적 어댑터 → 필요에 따라 선택적 적용 가능:
- 코딩만 강화하고 싶으면: base + round2.srs
- 전체 강화: base + round1~4.srs 전부 스택

---

## 7. 기술 스택 & 리소스 요구사항

### 7.1 필수 라이브러리

```
torch >= 2.1
transformers >= 4.40
peft >= 0.10
trl >= 0.8 (DPO trainer)
bitsandbytes >= 0.43 (8bit/4bit quantization)
accelerate >= 0.28
datasets >= 2.18
wandb (학습 모니터링)
```

### 7.2 하드웨어 요구사항

| 단계 | 최소 | 권장 |
|------|------|------|
| Diagnosis (Blame Map) | 1× A100 40GB | 1× A100 80GB |
| Surgery (Masked DPO) | 1× A100 40GB | 2× A100 80GB |
| Verification | 1× A100 40GB | 1× A100 40GB |
| **전체 파이프라인** | **1× A100 40GB** | **2× A100 80GB** |

**LLaMA 3 8B 메모리 추정**:
- FP16 모델 로드: ~16GB
- Gradient (수술 대상 1%만): ~0.16GB (vs 전체 16GB)
- Reference 모델 (DPO용): ~16GB (8bit 양자화 시 ~8GB)
- Activations & Optimizer: ~8GB
- **총합: ~40GB** (A100 40GB에 딱 맞음)

### 7.3 CPU 모드 (개발/테스트용)

```
LLaMA 3 8B는 CPU에서 돌리면 추론 1건당 1~5분...
→ 풀 Surgery는 GPU 필수
→ 단, Blame Map의 프로토타입은 Qwen2.5-0.5B로 CPU 테스트 가능
```

**개발 순서**:
1. Qwen2.5-0.5B + CPU로 파이프라인 검증 (현재 환경)
2. 검증 후 A100 서버에서 LLaMA 3 8B에 적용

---

## 8. Preference Data 수집 전략

### 8.1 GPT-4o를 Teacher로 쓰는 방법

```
Step 1: 고품질 프롬프트 수집
  └─ MMLU, HumanEval, GSM8K, ARC, MT-Bench 등에서 추출
  └─ 난이도: LLaMA가 50~70% 맞추는 수준 (너무 쉽거나 어려우면 의미 없음)

Step 2: LLaMA 3 8B로 답변 생성
  └─ 각 프롬프트에 대해 temperature=0.7로 3개 답변 생성

Step 3: GPT-4o로 답변 생성
  └─ 같은 프롬프트에 대해 GPT-4o 답변 획득

Step 4: Preference Pair 구성
  └─ chosen: GPT-4o 답변 (또는 LLaMA가 우연히 잘한 답변)
  └─ rejected: LLaMA가 틀린/열등한 답변

Step 5: 카테고리별 분류
  └─ reasoning / knowledge / coding / instruction / safety
  └─ 카테고리별 1000개, 총 5000개 preference pairs 목표
```

### 8.2 자체 데이터 증폭

```
GPT-4o API 비용 절감 전략:

1. Seed Expansion
   └─ GPT-4o 답변 100개 → 패턴 분석 → 유사 답변 자동 생성 900개
   
2. Rejection Sampling
   └─ LLaMA로 100번 답변 → 가장 좋은 것 = chosen, 가장 나쁜 것 = rejected
   └─ GPT-4o 없이도 self-improvement pair 생성 가능

3. Difficulty Curriculum
   └─ 쉬운 문제부터 어려운 문제까지 순차적 수술
   └─ 쉬운 문제: LLaMA가 40~60% 맞추는 것 (1라운드)
   └─ 어려운 문제: LLaMA가 10~40% 맞추는 것 (후반 라운드)
```

---

## 9. .srs 어댑터 파일 규격

### 9.1 파일 구조

```
srs_adapters/
├── adapter_model.srs          # 수술된 파라미터 가중치 (safetensors 기반)
├── adapter_config.json        # 수술 설정
├── blame_map.json             # 진단 결과 (어떤 뉴런이 수술받았는지)
├── surgery_report.srr         # 수술 결과 리포트
├── tokenizer.json             # 토크나이저
└── tokenizer_config.json
```

### 9.2 adapter_config.json

```json
{
  "ser1es_format": "S-SER1ES",
  "ser1es_product": "S-SER1ES",
  "surgery_method": "masked_dpo",
  "base_model": "meta-llama/Meta-Llama-3-8B-Instruct",
  "target_model": "GPT-4o",
  "surgery_round": 1,
  "surgery_budget_pct": 1.0,
  "total_surgery_params": 80300000,
  "total_model_params": 8030000000,
  "blame_threshold": 0.85,
  "dpo_beta": 0.1,
  "learning_rate": 2e-5,
  "max_param_distance": 0.5,
  "anti_forgetting_kl_limit": 0.05,
  
  "surgery_layers": {
    "model.layers.14.mlp.gate_proj": {"blamed_pct": 3.2, "surgery_applied": true},
    "model.layers.14.mlp.up_proj":   {"blamed_pct": 2.8, "surgery_applied": true},
    "model.layers.15.self_attn.q_proj": {"blamed_pct": 1.9, "surgery_applied": true},
    "model.layers.15.mlp.gate_proj": {"blamed_pct": 4.1, "surgery_applied": true},
    "model.layers.16.mlp.down_proj": {"blamed_pct": 2.3, "surgery_applied": true}
  },
  
  "verification": {
    "mmlu_before": 68.4,
    "mmlu_after": 78.2,
    "anchor_score_maintained": true,
    "side_effects_detected": false
  }
}
```

### 9.3 PEFT 호환성

S-SER1ES 어댑터는 PEFT의 **custom adapter** 형태로 저장:
- sparse weight diff만 저장 (수술 안 된 파라미터는 0)
- PEFT `from_pretrained()`으로 로드 가능하도록
- 내부적으로는 `LoraConfig` 대신 `SurgeryConfig` 사용하되, PEFT 호환 유지

---

## 10. 기존 SER1ES 제품과의 관계

```
┌─────────────────────────────────────────────────────┐
│                  SER1ES Ecosystem                    │
│                                                     │
│  ┌─────────┐ ┌─────────┐ ┌─────────┐               │
│  │ MURHEN  │ │ PARHEN  │ │ PHIREN  │  ← 기존 제품   │
│  │ (.mrh)  │ │ (.prh)  │ │ (.phr)  │  (특화 학습)   │
│  └────┬────┘ └────┬────┘ └────┬────┘               │
│       │           │           │                     │
│  ┌─────────┐ ┌─────────┐                           │
│  │ OVISEN  │ │ OGENTI  │        ← 기존 제품         │
│  │ (.oge)  │ │ (.ogt)  │        (특화 학습)         │
│  └────┬────┘ └────┬────┘                           │
│       │           │                                 │
│       ▼           ▼                                 │
│  ┌─────────────────────────────────────┐            │
│  │         S-SER1ES (.srs)             │ ← NEW!     │
│  │    "Neural Surgery Engine"          │            │
│  │                                     │            │
│  │  위 5개 제품 학습 후에도 남아있는     │            │
│  │  "멍청한 뉴런"을 추가로 수술         │            │
│  │                                     │            │
│  │  또는 독립적으로 base model에        │            │
│  │  직접 적용하여 전체 지능 향상         │            │
│  └─────────────────────────────────────┘            │
│                                                     │
│  적용 방식:                                          │
│  A. base + MURHEN(.mrh) + S-SER1ES(.srs) = 이중강화  │
│  B. base + S-SER1ES(.srs) = 범용 지능 강화           │
│  C. base + 5개 전부 + S-SER1ES(.srs) = 풀 스택       │
└─────────────────────────────────────────────────────┘
```

---

## 11. 현실적 예상 결과

### Best Case (낙관)
```
LLaMA 3 8B + S-SER1ES 5라운드 수술 후:
  MMLU:      68.4% → 82.0% (GPT-4o의 92.4%)
  HumanEval: 62.2% → 81.0% (GPT-4o의 89.8%)
  GSM8K:     79.6% → 91.0% (GPT-4o의 95.0%)
  
  → GPT-4o 대비 ~90% 수준 도달
  → 8B 모델로는 역사적 성과
```

### Realistic Case (현실)
```
LLaMA 3 8B + S-SER1ES 5라운드 수술 후:
  MMLU:      68.4% → 76.0% (GPT-4o의 85.7%)
  HumanEval: 62.2% → 73.0% (GPT-4o의 80.9%)
  GSM8K:     79.6% → 87.0% (GPT-4o의 90.8%)
  
  → GPT-4o 대비 ~85% 수준
  → 여전히 LLaMA 3 70B를 이기는 수준 (8B로!)
```

### Worst Case (비관)
```
LLaMA 3 8B + S-SER1ES:
  개선폭: +3~5%p 정도
  → 일반 LoRA와 비슷한 수준
  → 단, 수술 대상 정밀 선택의 가치는 검증됨
```

---

## 12. 개발 로드맵

```
Phase 0: 프로토타입 (현재 환경, Qwen2.5-0.5B, CPU)
────────────────────────────────────────────────────
  □ blame_engine.py — Blame Map 생성기
  □ surgery_engine.py — Masked DPO 엔진
  □ verify_surgery.py — 수술 검증기
  □ Qwen2.5-0.5B로 파이프라인 전체 검증
  
Phase 1: LLaMA 3 8B 적용 (A100 서버)
────────────────────────────────────────────────────
  □ GPT-4o preference data 5000쌍 수집
  □ Round 1 Surgery: reasoning
  □ Round 2 Surgery: coding
  □ Round 3 Surgery: knowledge
  □ 중간 벤치마크 (MMLU, HumanEval, GSM8K)

Phase 2: 반복 & 최적화
────────────────────────────────────────────────────
  □ Round 4-5 Surgery
  □ Surgery Stack 최적화
  □ 최종 벤치마크 & GPT-4o 비교

Phase 3: 제품화
────────────────────────────────────────────────────
  □ .srs 어댑터 패키징
  □ SER1ES 플랫폼 통합
  □ API 엔드포인트 배포
```

---

## 13. 경쟁 우위 & 차별점

| 기존 방법 | S-SER1ES |
|-----------|----------|
| LoRA: 전체에 uniform low-rank | 멍청한 뉴런만 targeted |
| QLoRA: 양자화 + LoRA | 양자화 안 해도 되고 정밀 수술 |
| Full FT: 전체 재학습 | 1~5%만 건드림 → 10~50x 효율 |
| Knowledge Distillation: teacher→student 전체 | 틀린 부분만 teacher에서 배움 |
| RLHF/DPO: 전체 파라미터 대상 | 범인 뉴런만 대상 |

**S-SER1ES만의 유니크 셀링 포인트**:
1. **Blame Map**: 어떤 뉴런이 멍청한지 시각화 가능
2. **Surgical Precision**: 전체의 1~5%만 수정 → 사이드 이펙트 최소화
3. **Surgery Stack**: 영역별 독립 수술 → 선택적 적용
4. **Adapter 크기**: 전체 모델의 1~5% → 수백 MB (vs 수 GB)
5. **오픈소스 전용**: 가중치 공개된 모델에만 적용 가능 → 독점적 가치

---

*S-SER1ES: 멍청한 뉴런을 찾아서, 갈아끼우고, 검증한다.*
*"Every neuron deserves a second chance... or a replacement."*
