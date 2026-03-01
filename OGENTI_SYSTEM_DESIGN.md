# OGENTI — AI-to-AI Communication Protocol

> *"인간 언어로 100 토큰 쓸 걸, 3 토큰으로 끝내자"*

---

## 0. 한 줄 요약

**AI 에이전트들이 자연어 대신 사용할 수 있는 초압축 통신 프로토콜을 MARL(Multi-Agent Reinforcement Learning) + 점진적 파인튜닝으로 만든다.**

자연어 예시:
```
"Claude, 이 파일을 읽고 핵심 내용을 분석한 뒤, 500자 이내로 요약해서 GPT-4에게 전달해줘"
```

Ogenti 프로토콜:
```
ξ7f·Σ3→④
```

목표: **같은 의미, 1/20 토큰**.

---

## 1. 왜 이걸 만드는가

### 1.1 문제

| 현재 상태 | 비용 |
|-----------|------|
| Agent A → Agent B 지시: 자연어 프롬프트 ~150 토큰 | $0.003 / 건 (GPT-4o 기준) |
| Agent B → Agent C 결과 전달: 자연어 요약 ~300 토큰 | $0.006 / 건 |
| Agent C → Agent A 최종 보고: 자연어 리포트 ~500 토큰 | $0.010 / 건 |
| **3-agent 1회 협업 총 비용** | **~$0.019 / 건** |

Multi-agent 시스템이 수만 건/일 처리하면? → **월 $15,000+**

근데 이 중 대부분은 **AI가 AI한테 보내는 메시지**야.
인간이 안 읽는 건데 인간 언어로 쓸 이유가 없지.

### 1.2 기회

| 지표 | 자연어 | Ogenti 목표 |
|------|--------|-------------|
| 평균 메시지 길이 | ~200 토큰 | ~10-15 토큰 |
| 압축률 | 1x | **15-20x** |
| 의미 보존율 | 100% | ≥97% |
| API 비용 절감 | — | **90%+** |

### 1.3 왜 지금인가

- Multi-agent 시스템 폭발적 성장 (AutoGPT, CrewAI, LangGraph, OpenAI Swarm)
- 아직 "에이전트간 통신 비용"에 집중하는 프로젝트가 거의 없음
- RL fine-tuning 인프라 성숙 (TRL, DeepSpeed, vLLM)
- 작은 모델(3B-7B)로도 충분히 의미 있는 결과 가능

---

## 2. 핵심 아이디어

### 2.1 자연어 vs Ogenti Protocol

```
┌────────────────────────────────────────────────────────────────────┐
│                  현재: Human Language Bridge                        │
│                                                                    │
│   Agent A ──human text──→ Agent B ──human text──→ Agent C          │
│            ~150 tokens           ~300 tokens                       │
│                                                                    │
│   • 인간이 읽을 수 있음 (근데 안 읽음)                                │
│   • 토큰 낭비 (공손함, 문법, 반복)                                    │
│   • 모호성 존재 (자연어의 본질적 한계)                                 │
└────────────────────────────────────────────────────────────────────┘

┌────────────────────────────────────────────────────────────────────┐
│                  목표: Ogenti Protocol                              │
│                                                                    │
│   Agent A ──ξ7f·Σ3→④──→ Agent B ──Ψ2d·μ8──→ Agent C              │
│              ~8 tokens          ~5 tokens                          │
│                                                                    │
│   • 인간이 읽을 수 없음 (읽을 필요도 없음)                            │
│   • 최소 토큰으로 최대 의미                                          │
│   • 명확성: 하나의 토큰 시퀀스 = 하나의 의미                          │
└────────────────────────────────────────────────────────────────────┘
```

### 2.2 핵심 원리

**"인간 언어에서 AI가 실제로 쓰는 정보만 남기면 몇 토큰이면 된다"**

자연어 메시지를 분해하면:

```
"Claude, 이 파일을 읽고 핵심 내용을 분석한 뒤, 500자 이내로 요약해서 GPT에게 전달해줘"

→ 의미 분해:
  ACTION  = [READ, ANALYZE, SUMMARIZE]
  TARGET  = file (reference pointer)
  PARAMS  = {max_length: 500}
  ROUTE   = → Agent[GPT]

→ Ogenti 인코딩:
  ξ (action combo: read+analyze+summarize)
  7f (file ref pointer — 파일 해시 2바이트)
  · (separator)
  Σ3 (summarize, constraint=500)  
  → (route operator)
  ④ (agent index: GPT)

= 총 8 토큰
```

이건 "압축"이 아니야. **의미 공간의 재인코딩**이야.

---

## 3. 시스템 아키텍처

### 3.1 전체 구조

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        OGENTI TRAINING SYSTEM                           │
│                                                                         │
│  ┌──────────────┐     ┌──────────────┐     ┌──────────────┐            │
│  │  Environment │     │  Comm Channel│     │  Evaluator   │            │
│  │  Generator   │────▶│  (Protocol)  │────▶│  (Reward)    │            │
│  └──────┬───────┘     └──────┬───────┘     └──────┬───────┘            │
│         │                    │                    │                     │
│         ▼                    ▼                    ▼                     │
│  ┌──────────────┐     ┌──────────────┐     ┌──────────────┐            │
│  │  Task Pool   │     │  Agent Pool  │     │  Fitness     │            │
│  │              │     │  (MARL)      │     │  Tracker     │            │
│  │  • 파일 분석 │     │              │     │              │            │
│  │  • 코드 리뷰 │     │  Agent A ◄──▶│     │  • 정확도    │            │
│  │  • 번역     │     │  Agent B ◄──▶│     │  • 토큰 수   │            │
│  │  • 요약     │     │  Agent C ◄──▶│     │  • 압축률    │            │
│  │  • 멀티스텝 │     │  Agent D     │     │  • 일반화    │            │
│  └──────────────┘     └──────────────┘     └──────────────┘            │
│                                                                         │
│  ┌──────────────────────────────────────────────────────────┐           │
│  │                   Training Loop (MARL)                    │           │
│  │                                                           │           │
│  │  1. Task 샘플링                                           │           │
│  │  2. Agent A → Protocol Message → Agent B                 │           │
│  │  3. Agent B가 메시지 기반으로 Task 수행                    │           │
│  │  4. 결과 vs Ground Truth 비교                             │           │
│  │  5. Reward = accuracy / token_count                       │           │
│  │  6. PPO/GRPO 업데이트                                     │           │
│  │  7. Repeat                                                │           │
│  └──────────────────────────────────────────────────────────┘           │
└─────────────────────────────────────────────────────────────────────────┘
```

### 3.2 모듈 상세

#### Module 1: Task Environment Generator

태스크를 자동 생성하는 모듈. 에이전트들이 "뭘 통신할지"를 결정.

```python
# 태스크 카테고리
TASK_CATEGORIES = {
    "instruct": {
        # A가 B에게 지시하는 유형
        "file_read":     "파일 읽고 특정 정보 추출",
        "summarize":     "텍스트 요약 (길이 제약 포함)",
        "code_review":   "코드 리뷰 후 이슈 리포트",
        "translate":     "언어 번역",
        "transform":     "데이터 포맷 변환",
    },
    "report": {
        # B가 A에게 결과 보고하는 유형
        "status":        "작업 상태 보고",
        "result":        "작업 결과 전달",
        "error":         "에러 보고 + 컨텍스트",
        "partial":       "중간 결과 전달",
    },
    "negotiate": {
        # A와 B가 협상/조율하는 유형
        "task_split":    "작업 분배 협의",
        "conflict":      "충돌 해결",
        "resource":      "리소스 할당 협상",
    },
    "relay": {
        # A→B→C 릴레이 유형
        "chain":         "순차 처리 체인",
        "broadcast":     "1:N 동시 전달",
        "aggregate":     "N:1 결과 수집",
    }
}
```

#### Module 2: Communication Channel (Protocol Layer)

AI 간 메시지가 지나가는 채널. 여기서 프로토콜이 형성됨.

```
┌─────────────────────────────────────────────────────────┐
│                   Protocol Message Format                 │
│                                                          │
│   ┌──────┬──────────┬──────────┬────────┬─────────┐     │
│   │ HEAD │ OP_CODE  │ PAYLOAD  │ ROUTE  │ META    │     │
│   │ 1 tk │ 1-3 tk   │ 1-N tk   │ 0-2 tk │ 0-1 tk │     │
│   └──────┴──────────┴──────────┴────────┴─────────┘     │
│                                                          │
│   HEAD:     메시지 타입 (지시/보고/요청/릴레이)            │
│   OP_CODE:  수행할 연산 (읽기/쓰기/분석/요약/변환)         │
│   PAYLOAD:  대상 데이터 참조 또는 인라인 데이터             │
│   ROUTE:    다음 에이전트 (릴레이 시)                      │
│   META:     제약 조건 (길이, 포맷, 우선순위)               │
│                                                          │
│   예시: ξ 7f·Σ3 →④ ε                                     │
│         │ │  │  │  └── META: default constraints         │
│         │ │  │  └── ROUTE: Agent #4                       │
│         │ │  └── PAYLOAD: summarize, max=300              │
│         │ └── TARGET: file ref 0x7f                       │
│         └── HEAD+OP: instruct+read+analyze                │
└─────────────────────────────────────────────────────────┘
```

**핵심**: 이 포맷은 하드코딩이 아님. **에이전트들이 RL을 통해 자연발생적으로 수렴하는 구조**를 목표로 함. 위 포맷은 우리가 *예상하는* 수렴점이지, 강제하는 구조가 아님.

#### Module 3: Agent Pool (MARL Agents)

```
┌─────────────────────────────────────────────────────┐
│                   Agent Architecture                 │
│                                                      │
│   Base Model: Qwen2.5-3B / LLaMA-3.2-3B            │
│   (작은 모델이 프로토콜 학습에 더 유리 — 큰 모델은     │
│    자연어 관성이 너무 강해서 탈피가 어려움)             │
│                                                      │
│   ┌────────────────────────────────┐                 │
│   │        Encoder Head            │                 │
│   │   natural language → protocol  │                 │
│   │   (입력: 자연어 지시 or 데이터) │                 │
│   │   (출력: 프로토콜 토큰 시퀀스)  │                 │
│   ├────────────────────────────────┤                 │
│   │        Decoder Head            │                 │
│   │   protocol → action/output     │                 │
│   │   (입력: 프로토콜 메시지)       │                 │
│   │   (출력: 실제 수행 결과)        │                 │
│   ├────────────────────────────────┤                 │
│   │        Shared Backbone         │                 │
│   │   (기존 LLM의 이해/추론 능력)   │                 │
│   └────────────────────────────────┘                 │
│                                                      │
│   학습 대상: Encoder + Decoder LoRA adapters         │
│   고정: Backbone (추론 능력 보존)                     │
└─────────────────────────────────────────────────────┘
```

#### Module 4: Reward & Fitness Evaluator

```python
def compute_reward(
    task: Task,
    message: ProtocolMessage,
    result: TaskResult,
    ground_truth: GroundTruth,
) -> float:
    """
    Reward = Task 정확도 / 사용 토큰 수
    
    더 적은 토큰으로 더 정확한 결과 = 더 높은 보상
    """
    # 1. 정확도 (0.0 ~ 1.0)
    accuracy = evaluate_accuracy(result, ground_truth)
    
    # 2. 토큰 효율 (사용 토큰이 적을수록 높음)
    token_count = count_tokens(message)
    token_efficiency = 1.0 / (1.0 + token_count / BASELINE_TOKENS)
    # BASELINE_TOKENS = 같은 task의 자연어 평균 토큰 수
    
    # 3. 명확성 보너스 (수신 Agent가 몇 번 만에 이해했는가)
    clarity_bonus = 1.0 if result.attempts == 1 else 0.5 ** (result.attempts - 1)
    
    # 4. 일반화 보너스 (새로운 task에서도 작동하는가)
    generalization = generalization_score(message, unseen_tasks)
    
    # 최종 보상
    reward = (
        accuracy * 0.4 +           # 정확해야 함
        token_efficiency * 0.3 +    # 짧아야 함
        clarity_bonus * 0.2 +       # 명확해야 함
        generalization * 0.1        # 범용적이어야 함
    )
    
    return reward
```

---

## 4. 학습 파이프라인 (MARL + Progressive Fine-tuning)

### 4.1 전체 학습 흐름

```
Phase 0          Phase 1          Phase 2          Phase 3
[Warmup]    →   [Simple]     →   [Complex]    →   [Generalize]
                 
고정 프로토콜     1:1 통신         Multi-hop         Cross-domain
으로 기초 학습    단일 태스크       A→B→C 체인       unseen tasks
                                  협상/조율          zero-shot 전이

2B tokens        5B tokens        10B tokens        5B tokens
~1 day           ~3 days          ~7 days           ~3 days
```

### 4.2 Phase 0: Warmup — 프로토콜 기초

**목적**: 에이전트들이 "자연어 대신 뭔가 다른 걸 써도 된다"는 걸 학습

```python
# Phase 0 Training Config
phase0_config = {
    "task_type": "simple_relay",
    # A가 메시지를 B에게 전달, B는 그 의미를 자연어로 복원
    # → 에이전트가 "인코딩-디코딩" 패턴을 학습
    
    "initial_protocol": "seeded",
    # 완전 랜덤 시작이 아니라, 의미적 시드 제공
    # 예: ACTION 카테고리 10개에 대응하는 10개 시드 토큰
    
    "reward_weights": {
        "accuracy": 0.7,      # 의미 복원이 우선
        "token_count": 0.2,   # 압축은 아직 약하게
        "clarity": 0.1,
    },
    
    "constraints": {
        "max_message_tokens": 50,    # 처음엔 넉넉하게
        "min_message_tokens": 5,     # 최소 5토큰 (너무 짧으면 불가능)
    },
    
    "num_agents": 4,
    "episodes": 50_000,
    "model": "Qwen2.5-3B",
    "lora_rank": 16,
    "learning_rate": 2e-5,
}
```

### 4.3 Phase 1: Simple — 1:1 단일 태스크 통신

**목적**: Agent A↔B 간 특정 태스크에 대한 효율적 프로토콜 수렴

```python
phase1_config = {
    "task_types": [
        "instruct.summarize",
        "instruct.file_read",
        "report.result",
        "report.status",
    ],
    
    "reward_weights": {
        "accuracy": 0.5,
        "token_count": 0.3,    # 압축 압력 증가
        "clarity": 0.2,
    },
    
    "constraints": {
        "max_message_tokens": 30,    # 점진적 축소
        "token_budget_decay": True,  # 에피소드 진행 시 max 감소
        "decay_rate": 0.999,         # 매 에피소드 0.1% 감소
        "floor": 8,                  # 최소 8 토큰까지
    },
    
    "curriculum": True,
    # 쉬운 태스크 → 어려운 태스크 순으로 학습
    # 짧은 텍스트 요약 → 긴 텍스트 요약 → 복잡한 분석
    
    "self_play": True,
    # 같은 agent가 encoder/decoder 역할을 번갈아 수행
    # → 쌍방 이해가 가능한 프로토콜 형성
    
    "population_training": True,
    # 4-8 에이전트가 무작위 페어링
    # → 특정 쌍에서만 통하는 "방언" 방지
    # → 범용 프로토콜 수렴 유도
}
```

**Phase 1 핵심 메커니즘: Token Budget Decay**

```
Episode    0: max 30 tokens → 에이전트: 자연어 비슷한 긴 메시지
Episode 1000: max 25 tokens → 에이전트: 불필요한 단어 탈락 시작
Episode 3000: max 18 tokens → 에이전트: 핵심만 남은 축약 형태
Episode 5000: max 12 tokens → 에이전트: 새로운 토큰 패턴 출현
Episode 8000: max  8 tokens → 에이전트: 완전히 다른 언어 형성 ← 목표
```

이 과정에서 자연어 → 축약어 → 기호 → **신규 프로토콜**로 자연 전이.

### 4.4 Phase 2: Complex — Multi-agent 체인 + 협상

**목적**: A→B→C 릴레이, 작업 분배, 충돌 해결

```python
phase2_config = {
    "task_types": [
        "relay.chain",        # A→B→C 순차 처리
        "relay.broadcast",    # A→(B,C,D) 동시 지시
        "relay.aggregate",    # (B,C,D)→A 결과 수집
        "negotiate.task_split", # 작업 분배
    ],
    
    "reward_weights": {
        "accuracy": 0.4,
        "token_count": 0.35,   # 압축 압력 최대
        "clarity": 0.15,
        "generalization": 0.1,
    },
    
    "constraints": {
        "max_message_tokens": 15,
        "total_chain_budget": 30,  # 체인 전체 토큰 합산 제한
    },
    
    "num_agents": 8,
    # 더 많은 에이전트 참여 → 프로토콜 범용성 강제
    
    "routing_required": True,
    # 메시지에 "누구에게 보내는 건지" 라우팅 정보 포함 필수
    # → 프로토콜에 주소 체계가 자연 발생
    
    "error_injection": True,
    # 10% 확률로 메시지 일부 손상
    # → 프로토콜의 오류 내성(error tolerance) 학습
}
```

### 4.5 Phase 3: Generalize — Zero-shot 전이

**목적**: 학습하지 않은 새로운 태스크에서도 프로토콜이 작동하는지 검증

```python
phase3_config = {
    "task_types": [
        "unseen_instruct",    # 학습 시 없었던 새 지시 유형
        "cross_domain",       # 코드→자연어, 자연어→코드 전환
        "complex_reasoning",  # 다단계 추론 지시
    ],
    
    "evaluation_only": False,
    # 약간의 fine-tuning 허용 (few-shot adaptation)
    # 하지만 프로토콜 자체는 Phase 2에서 수렴된 것 사용
    
    "metrics": {
        "zero_shot_accuracy": "학습 안 한 태스크 정확도",
        "compression_ratio": "자연어 대비 토큰 비율",
        "compositionality": "토큰 조합으로 새 의미 표현 가능성",
        "cross_agent_compat": "다른 모델 간 호환성",
    },
}
```

---

## 5. 기술적 핵심 결정들

### 5.1 왜 기존 토크나이저를 쓰는가 (새 어휘 X)

```
Option A: 새로운 토큰 어휘 생성 (custom vocabulary)
  → 장점: 진정한 최적 인코딩 가능
  → 단점: 기존 LLM과 완전 단절. 처음부터 의미 학습 필요.
  
Option B: 기존 토크나이저의 토큰을 "재해석" ★ 우리 선택
  → 장점: 기존 모델의 임베딩 공간 활용 가능
  → 단점: 토크나이저 제약 존재
  
이유: 기존 토큰의 임베딩 벡터는 이미 의미 공간에 매핑됨.
"hello" 토큰이 가진 임베딩 벡터를 프로토콜에서 다른 의미로
재할당하는 것이 처음부터 학습하는 것보다 훨씬 빠름.

결과적으로: 기존 토큰 "ξ"가 model vocabulary에 이미 있고,
임베딩 벡터도 있음. LoRA가 이 벡터의 의미를 재매핑.
```

### 5.2 왜 작은 모델인가 (3B)

```
큰 모델 (70B+):
  - 자연어 관성이 너무 강함
  - "Please summarize this..." 패턴에서 벗어나기 어려움
  - RL 학습 비용이 비현실적

작은 모델 (3B):
  - 자연어 관성 약함 → 새 프로토콜 수용 용이
  - RL 학습이 현실적 (RTX 4090 1대로 가능)
  - 프로토콜 자체는 복잡한 추론이 아니라 "인코딩/디코딩"
  - 복잡한 추론은 큰 모델이, 통신은 작은 모델이 분담
  
구조:
  ┌──────────────┐    Ogenti     ┌──────────────┐
  │ GPT-4o       │───Protocol───▶│ Claude 3.5   │
  │ (추론/실행)   │   (3B 모델    │ (추론/실행)   │
  │              │    인코딩)     │              │
  └──────────────┘               └──────────────┘
       │                               │
       ▼                               ▼
  큰 모델은 생각하고,          큰 모델은 생각하고,
  작은 모델(3B)이 통신을        작은 모델(3B)이 통신을
  인코딩/디코딩              인코딩/디코딩
```

### 5.3 RL 알고리즘 선택

```
PPO (Proximal Policy Optimization):
  ✅ 안정적, 검증됨
  ✅ TRL 라이브러리에서 바로 사용 가능
  ❌ 샘플 효율 낮음

GRPO (Group Relative Policy Optimization):
  ✅ DeepSeek에서 검증 — 언어 모델 RL에 특화
  ✅ 여러 응답 그룹 비교 → 더 안정적 학습
  ❌ 구현 복잡도 약간 높음

MAPPO (Multi-Agent PPO): ★ 1차 선택
  ✅ Multi-agent 환경에 특화
  ✅ Centralized critic + decentralized actors
  ✅ 에이전트 간 공유 보상 처리 자연스러움
  ❌ 구현 필요 (기존 라이브러리 커스텀)
  
→ Phase 0-1: PPO (빠른 프로토타이핑)
→ Phase 2-3: MAPPO (multi-agent 본격 학습)
```

### 5.4 Token Budget Pressure — 핵심 학습 동력

```
왜 에이전트가 "스스로" 압축을 하게 되는가?

답: Token Budget + Reward Shaping

1. max_tokens가 매 에피소드 줄어듦
   → 긴 메시지는 물리적으로 보낼 수 없게 됨
   
2. reward에 token_efficiency가 포함
   → 같은 정확도면 짧은 메시지가 더 높은 보상
   
3. population training
   → 특정 쌍에서만 통하는 체계는 도태
   → 모든 에이전트가 이해하는 범용 체계가 생존

결과: 자연선택처럼 비효율적 통신은 도태되고,
      효율적 프로토콜이 자연 수렴.

이건 사실 "언어의 진화"를 인위적으로 가속하는 거야.
인간 언어도 수천 년에 걸쳐 효율적으로 진화했고,
우리는 그걸 수 주 만에 하는 거지.
```

---

## 6. 데이터 파이프라인

### 6.1 학습 데이터 구조

```python
@dataclass
class TrainingEpisode:
    """하나의 학습 에피소드"""
    
    task: Task                     # 수행할 태스크
    sender: AgentID                # 메시지 발신 에이전트
    receiver: AgentID              # 메시지 수신 에이전트
    
    # Ground Truth (자연어 기준)
    natural_instruction: str       # 자연어 지시문
    natural_token_count: int       # 자연어 토큰 수
    expected_output: str           # 기대 결과
    
    # 에이전트가 생성한 것
    protocol_message: list[int]    # 프로토콜 토큰 시퀀스
    protocol_token_count: int      # 프로토콜 토큰 수
    actual_output: str             # 실제 수행 결과
    
    # 평가
    accuracy: float                # 결과 정확도
    compression_ratio: float       # natural / protocol 토큰 비율
    reward: float                  # 최종 보상
```

### 6.2 태스크 데이터 소스

```
┌─────────────────────────────────────────────────────┐
│                Task Data Sources                     │
│                                                      │
│  1. Synthetic Generation (Phase 0-1)                 │
│     • GPT-4o로 다양한 지시문 자동 생성               │
│     • 파일 내용 + 지시 + 기대 결과 트리플렛          │
│     • 난이도 태그 (easy/medium/hard)                 │
│                                                      │
│  2. Real-world Traces (Phase 2-3)                    │
│     • CrewAI / LangGraph 실제 실행 로그 수집         │
│     • Agent 간 실제 자연어 통신 캡처                 │
│     • 실제 비용 데이터 포함                          │
│                                                      │
│  3. Adversarial Examples (Phase 3)                   │
│     • 의도적으로 어려운/모호한 지시                  │
│     • 에이전트를 혼란시키는 케이스                   │
│     • 프로토콜 강건성 테스트                         │
└─────────────────────────────────────────────────────┘
```

---

## 7. 평가 체계

### 7.1 핵심 메트릭

| 메트릭 | 측정 대상 | 목표 |
|--------|-----------|------|
| **Compression Ratio** | 자연어 토큰 / 프로토콜 토큰 | ≥15x |
| **Semantic Fidelity** | 프로토콜 메시지의 의미 보존율 | ≥97% |
| **Task Accuracy** | 프로토콜로 통신한 태스크 성공률 | ≥95% |
| **Cross-Agent Compatibility** | 다른 모델 간 교차 이해율 | ≥90% |
| **Zero-shot Transfer** | 새 태스크 유형 일반화 정확도 | ≥85% |
| **Compositionality Score** | 토큰 조합으로 새 의미 생성 가능성 | 정성 평가 |

### 7.2 벤치마크 프레임워크

```python
class OgentiBenchmark:
    """Ogenti 프로토콜 평가 벤치마크"""
    
    BENCHMARK_TASKS = {
        "simple_relay": {
            "description": "A→B 단순 지시 전달",
            "baseline_tokens": 150,    # 자연어 기준
            "target_tokens": 10,       # 프로토콜 목표
            "min_accuracy": 0.95,
        },
        "summarize_relay": {
            "description": "A가 B에게 요약 지시 + 결과 전달",
            "baseline_tokens": 350,
            "target_tokens": 20,
            "min_accuracy": 0.93,
        },
        "multi_hop": {
            "description": "A→B→C→D 4-hop 체인",
            "baseline_tokens": 800,
            "target_tokens": 40,
            "min_accuracy": 0.90,
        },
        "negotiation": {
            "description": "A↔B 작업 분배 협상",
            "baseline_tokens": 500,
            "target_tokens": 30,
            "min_accuracy": 0.88,
        },
    }
```

---

## 8. 인프라 & 학습 비용 추정

### 8.1 하드웨어 요구사항

```
Phase 0 (Warmup):
  • GPU: RTX 4090 × 1 (24GB VRAM)
  • Model: Qwen2.5-3B + LoRA (rank 16)  
  • VRAM 사용: ~12GB (model) + 8GB (optimizer states)
  • 학습 시간: ~1일
  • 비용: ~$10 (RunPod spot)

Phase 1 (Simple):
  • GPU: RTX 4090 × 1-2
  • 학습 시간: ~3일
  • 비용: ~$30-50

Phase 2 (Complex):
  • GPU: A100 40GB × 2 (multi-agent 동시 실행)
  • 학습 시간: ~7일
  • 비용: ~$200-300

Phase 3 (Generalize):
  • GPU: A100 40GB × 1
  • 학습 시간: ~3일
  • 비용: ~$80-120

총 예상: $300-500 (RunPod spot pricing)
```

### 8.2 소프트웨어 스택

```
Training:
  • PyTorch 2.x
  • Transformers (HuggingFace)
  • TRL (Transformer Reinforcement Learning)
  • DeepSpeed ZeRO Stage 2
  • Weights & Biases (실험 추적)
  
Models:
  • Qwen2.5-3B-Instruct (encoder/decoder agents)
  • PEFT/LoRA (효율적 fine-tuning)
  
Evaluation:
  • vLLM (빠른 추론)
  • Custom benchmark suite
  
Infrastructure:
  • RunPod (GPU 렌탈)
  • GitHub Actions (CI/CD)
  • HuggingFace Hub (모델 배포)
```

---

## 9. 예상 결과물

### 9.1 오픈소스 공개물

```
ogenti/
├── ogenti-core/            # 프로토콜 핵심 라이브러리
│   ├── encoder.py          # 자연어 → 프로토콜 인코더
│   ├── decoder.py          # 프로토콜 → 실행 디코더
│   ├── protocol.py         # 프로토콜 정의 & 파싱
│   └── channel.py          # 통신 채널 추상화
│
├── ogenti-train/           # MARL 학습 파이프라인
│   ├── environment.py      # 학습 환경
│   ├── agents.py           # MARL 에이전트 정의
│   ├── rewards.py          # 보상 함수
│   ├── curriculum.py       # 커리큘럼 학습 스케줄러
│   └── train.py            # 메인 학습 스크립트
│
├── ogenti-bench/           # 벤치마크 & 평가
│   ├── benchmark.py        # 벤치마크 태스크
│   ├── metrics.py          # 평가 메트릭
│   └── visualize.py        # 결과 시각화
│
├── ogenti-models/          # 학습된 모델 (HF Hub)
│   ├── ogenti-3b-v0.1/     # Phase 1 모델
│   └── ogenti-3b-v1.0/     # Phase 3 최종 모델
│
├── papers/                 # 연구 논문
│   └── ogenti-protocol.pdf
│
└── examples/               # 사용 예시
    ├── crewai_integration.py
    ├── langchain_integration.py
    └── openai_swarm_integration.py
```

### 9.2 사용 예시 (최종 비전)

```python
from ogenti import OgentiEncoder, OgentiDecoder

# 기존 방식: 자연어로 에이전트 간 통신
message = """
Please read the file 'report.csv', extract all rows where 
the 'status' column is 'failed', calculate the failure rate 
as a percentage, and send a brief summary to the QA agent 
including the top 3 failure reasons.
"""
# → 52 tokens (GPT-4o tokenizer)

# Ogenti 방식
encoder = OgentiEncoder.from_pretrained("ogenti/ogenti-3b-v1.0")
protocol_msg = encoder.encode(message)
# → [ξ, 0x3f, ·, Φ, 2a, β, 3, →, ⑦]
# → 9 tokens (5.8x compression)

# 수신 에이전트가 디코딩
decoder = OgentiDecoder.from_pretrained("ogenti/ogenti-3b-v1.0")
decoded_intent = decoder.decode(protocol_msg)
# → 정확한 task 수행 (정확도 97%+)
```

---

## 10. 리스크 & 대응

| 리스크 | 확률 | 영향 | 대응 |
|--------|------|------|------|
| 프로토콜이 수렴하지 않음 | 중 | 치명 | 시드 프로토콜로 초기 구조 제공 + 커리큘럼 학습 |
| 특정 쌍에서만 통하는 언어 형성 | 높 | 높 | Population training 필수 + 주기적 에이전트 셔플 |
| 정확도가 85% 미만 | 중 | 높 | 정확도 threshold 미달 시 자연어 fallback 경로 |
| 새 태스크 일반화 실패 | 중 | 중 | Compositionality 강제 (토큰 조합 규칙 학습) |
| 학습 비용 초과 | 낮 | 중 | 3B 모델 + LoRA로 비용 통제 |
| 큰 모델과 통합 어려움 | 중 | 중 | adapter 방식으로 기존 모델에 플러그인 |

---

## 11. 로드맵

```
2026 Q1 (3-4월): Foundation
  ├── 시스템 설계 완료 ← 지금 여기
  ├── Phase 0 구현 & 실험
  ├── 기초 프로토콜 수렴 확인
  └── 논문 초고 시작

2026 Q2 (5-6월): Core Training
  ├── Phase 1-2 학습 완료
  ├── 벤치마크 구축
  ├── 10x+ 압축률 달성
  └── 오픈소스 첫 릴리즈

2026 Q3 (7-9월): Integration & Paper
  ├── Phase 3 일반화 학습
  ├── CrewAI / LangGraph 통합 데모
  ├── 논문 투고 (NeurIPS / ICLR)
  └── HuggingFace 모델 공개

2026 Q4: Ecosystem
  ├── SDK 배포 (pip install ogenti)
  ├── API 서비스 (ogenti.com)
  ├── 커뮤니티 빌딩
  └── 시리즈 A 준비 or 인수 논의
```

---

## 12. 왜 이게 되는가 — 핵심 인사이트

```
인간 언어는 "인간을 위해" 진화했다:
  • 소리로 전달할 수 있어야 함
  • 모호성을 허용함 (문맥으로 보완)
  • 감정, 뉘앙스를 실어야 함
  • 문법 규칙이 복잡함

AI-to-AI 통신에는 이 제약이 없다:
  • 텍스트가 아니라 토큰 시퀀스면 됨
  • 모호성 불필요 (정확한 인코딩 가능)
  • 감정/뉘앙스 불필요
  • 문법 불필요 — 위치 기반 의미만으로 충분

→ 인간 언어의 제약을 벗으면 같은 정보를
   1/10 ~ 1/20로 전달할 수 있다는 게 핵심 가설.

이건 "새 언어를 만드는" 프로젝트가 아니야.
"AI가 이미 내부적으로 쓰는 표현을 외부 통신에도 쓰게 하는" 프로젝트야.
LLM 내부에서는 이미 토큰 임베딩이라는 초압축 표현을 쓰고 있거든.
그걸 밖으로 꺼내는 거지.
```

---

*"AI끼리 대화하는데 굳이 인간 언어 쓸 필요 없잖아?"*
*— Ogenti의 시작점*
