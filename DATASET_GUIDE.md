# ◆ Ogenti Training Dataset Guide

> *AI끼리 대화하는 법을 가르치려면, 먼저 "무엇에 대해" 대화할지를 정해줘야 한다.*

---

## 목차

- [이게 뭔데?](#-이게-뭔데)
- [왜 필요한데?](#-왜-필요한데)
- [구조 뜯어보기](#-구조-뜯어보기)
- [카테고리 전체 맵](#-카테고리-전체-맵)
- [커리큘럼과 난이도 설계](#-커리큘럼과-난이도-설계)
- [데이터 하나 뜯어보기](#-데이터-하나-뜯어보기)
- [가동법](#-가동법)
- [커스텀 태스크 추가하기](#-커스텀-태스크-추가하기)
- [프로덕션 학습이랑 어떻게 연결되는데?](#-프로덕션-학습이랑-어떻게-연결되는데)
- [통계](#-현재-데이터셋-통계)

---

## ◆ 이게 뭔데?

**`generate_dataset.py`** 는 Ogenti 프로토콜 학습에 쓰이는 **태스크 데이터셋을 자동 생성**하는 스크립트다.

Ogenti가 하는 일을 한 줄로 요약하면:

> **Encoder AI가 자연어를 초압축 프로토콜로 인코딩 → Channel을 통해 전송 → Decoder AI가 복원**

이 과정을 학습시키려면, AI한테 "이 문장을 압축해봐"라고 과제를 줘야 한다. 그 **과제(Task)** 를 만드는 게 바로 이 스크립트.

```
┌─────────────────────────────────────────────────────────┐
│                                                         │
│   generate_dataset.py                                   │
│                                                         │
│   "Summarize: Docker is a platform for..."              │
│        ↓                                                │
│   instruction (인코더 입력)                               │
│        +                                                │
│   reference  (정답 — 디코더가 이걸 복원해야 함)              │
│        +                                                │
│   category   (요약? 번역? QA? 코드리뷰?)                   │
│        +                                                │
│   difficulty (0.0 쉬움 ~ 1.0 극악)                       │
│        ↓                                                │
│   data/train.jsonl  (93개 태스크)                         │
│   data/eval.jsonl   (17개 태스크)                         │
│                                                         │
└─────────────────────────────────────────────────────────┘
```

쉽게 말하면, **AI 학원의 문제집**을 만드는 도구다.

---

## ◆ 왜 필요한데?

Ogenti의 학습은 **5개 Phase 커리큘럼**으로 구성되어 있다:

| Phase | 이름 | 뭐 하는 단계? |
|-------|------|-------------|
| 0 | **Warmup** | 기초반 — "사과는 빨갛다" 수준의 단순 요약/번역/QA |
| 1 | **Simple** | 초급반 — 코드리뷰, 데이터분석 등 실용 태스크 추가 |
| 2 | **Complex** | 중급반 — 멀티홉! 체이닝! AI 3마리가 릴레이! |
| 3 | **Generalize** | 심화반 — 모든 카테고리 다 섞어서 노이즈까지 |
| 4 | **Universalize** | 졸업반 — Knowledge Distillation → 범용 어댑터 추출 |

각 Phase마다 **허용되는 카테고리**가 다르다. Phase 0에서는 요약/번역/QA만, Phase 2부터는 멀티홉 태스크가 풀린다. 이 구조에 맞게 난이도별 태스크를 미리 생성해두는 것.

**데이터셋 없이도 학습은 가능하다** — `environment.py`에 14개 합성 태스크가 내장되어 있다. 하지만 14개로 5만 에피소드를 돌리면? AI가 문제를 외워버린다. 그래서 이 스크립트로 **110개 다양한 태스크**를 미리 뽑아두는 거다.

---

## ◆ 구조 뜯어보기

### 파일 위치

```
ai_master/
├── scripts/
│   └── generate_dataset.py    ← 이 스크립트
├── data/
│   ├── train.jsonl            ← 생성된 학습 데이터 (93개)
│   └── eval.jsonl             ← 생성된 평가 데이터 (17개)
├── configs/
│   └── production.json        ← "dataset_path": "data/train.jsonl"
└── ogenti_train/
    └── environment.py         ← TaskGenerator가 여기서 JSONL을 로드함
```

### JSONL이 뭔데?

**JSON Lines** — 한 줄에 JSON 하나. 파일 전체가 하나의 JSON 배열이 아니라, **각 줄이 독립적인 JSON 객체**다. 이 포맷의 장점:

- 한 줄씩 스트리밍 가능 (메모리에 전부 올리지 않아도 됨)
- append가 쉽다 (새 태스크 추가 = 파일 끝에 한 줄 추가)
- git diff가 깔끔하다

```jsonl
{"task_id": "qa_0042", "category": "qa", "instruction": "What is the capital of France?", "reference": "Paris", "difficulty": 0.2, "num_agents": 2}
{"task_id": "code_review_0050", "category": "code_review", "instruction": "Review this code:\ndef divide(a, b):\n    return a / b", "reference": "Missing division by zero check.", "difficulty": 0.5, "num_agents": 2}
```

---

## ◆ 카테고리 전체 맵

12개 카테고리, 각각의 목적이 다르다:

### Phase 0 — 기초 3종 세트

| 카테고리 | 무엇을? | 예시 | 난이도 |
|---------|--------|------|--------|
| `summarize` | 긴 글 → 핵심만 | "Docker is a platform for..." → "Docker packages apps in containers" | 0.3 |
| `translate` | 스타일/언어 변환 | 구어체 → 격식체, 기술문서 → 쉬운말 | 0.4 |
| `qa` | 질문 → 정답 | "What port does HTTPS use?" → "443" | 0.2 |

> 이 3개부터 시작하는 이유: **프로토콜의 본질이 "정보 압축"**이니까. 요약은 말 그대로 압축, QA는 핵심 추출, 번역은 형태 변환. 프로토콜 학습의 워밍업으로 완벽하다.

### Phase 1 — 실용 업무 태스크

| 카테고리 | 무엇을? | 예시 | 난이도 |
|---------|--------|------|--------|
| `code_review` | 코드 → 버그/개선점 | SQL 인젝션 발견, O(n³) → O(n) 최적화 | 0.5 |
| `data_analysis` | 데이터 → 인사이트 | "Q1=$100K, Q2=$150K..." → 트렌드 분석 | 0.6 |
| `instruction_following` | 지시 → 정확한 수행 | "List exactly 3 benefits" → 정확히 3개 | 0.3 |

> 여기서부터 **RL(강화학습)이 켜진다**. PPO로 프로토콜을 최적화하기 시작.

### Phase 2 — 멀티홉 (복합 추론)

| 카테고리 | 무엇을? | 예시 | 난이도 |
|---------|--------|------|--------|
| `chain_summarize` | 읽기→요약→정제 | 에러로그 분석 → 패턴 정리 → 해결책 제안 | 0.7 |
| `relay_translate` | A→B→C 릴레이 번역 | 기술영어 → 쉬운영어 → 한국어 | 0.7 |
| `multi_step_qa` | 다단계 추론 | 사실 3개 조합 → 결론 도출 | 0.8 |
| `reasoning` | 논리/수학 추론 | 기차 속도 문제, 서버 가용성 계산 | 0.8 |

> **Agent 3마리**가 등장! `num_agents=3`인 태스크는 AI가 릴레이로 메시지를 전달해야 한다. A→B→C. 진짜 "프로토콜"이 필요해지는 순간.

### Phase 3 — 전카테고리 + 창작/수학

| 카테고리 | 무엇을? | 예시 | 난이도 |
|---------|--------|------|--------|
| `creative_writing` | 창작 텍스트 생성 | 제품 설명, 하이쿠, git 커밋 메시지 | 0.6 |
| `math` | 수학/계산 | LoRA 파라미터 수 계산, FLOPs 산출 | 0.7 |

> Phase 3에서는 **모든 12개 카테고리가 전부 풀린다**. 노이즈도 15%로 올라간다. 여기서 프로토콜이 진짜 robust해져야 한다.

---

## ◆ 커리큘럼과 난이도 설계

```
난이도(difficulty)
1.0 ┤
    │                              ■ reasoning (0.8)
0.8 ┤                              ■ multi_step_qa (0.8)
    │                      ■ chain_summarize (0.7)
0.7 ┤                      ■ relay_translate (0.7)
    │                                          ■ math (0.7)
0.6 ┤              ■ data_analysis (0.6)       ■ creative (0.6)
    │
0.5 ┤              ■ code_review (0.5)
    │
0.4 ┤      ■ translate (0.4)
    │
0.3 ┤      ■ summarize (0.3)
    │      ■ instruction (0.3)
0.2 ┤      ■ qa (0.2)
    │
0.0 ┼──────┬──────────────┬────────────────┬───────────
    Phase 0   Phase 1       Phase 2          Phase 3/4
    (기초)    (실용)        (복합)           (전체)
```

**핵심 설계 원칙:**

1. **쉬운 것부터** — Phase 0은 난이도 0.2~0.4. "사과는 빨갛다" 수준부터 시작
2. **점진적 확장** — 카테고리가 Phase마다 늘어남 (3 → 6 → 10 → 12)
3. **멀티홉은 중반부터** — Agent 3마리 릴레이는 Phase 2에서야 등장
4. **Phase 4는 전체** — 특별한 제한 없음 (다만 이때는 Knowledge Distillation이라 데이터보다 teacher 모델이 중요)

---

## ◆ 데이터 하나 뜯어보기

```json
{
  "task_id": "code_review_0050",
  "category": "code_review",
  "instruction": "Review for security:\nquery = f\"SELECT * FROM users WHERE name = '{user_input}'\"",
  "reference": "SQL injection vulnerability. Use parameterized queries: cursor.execute('SELECT * FROM users WHERE name = ?', (user_input,)).",
  "difficulty": 0.5,
  "num_agents": 2,
  "metadata": {}
}
```

| 필드 | 설명 |
|------|------|
| `task_id` | 유니크 ID — `{카테고리}_{순번}` |
| `category` | 12개 카테고리 중 하나 |
| `instruction` | **인코더 입력** — 이 자연어를 프로토콜로 압축해야 함 |
| `reference` | **정답** — 디코더가 복원해야 하는 텍스트. 리워드 계산 기준 |
| `difficulty` | 난이도 0.0~1.0 — 커리큘럼 스케줄링에 활용 |
| `num_agents` | 이 태스크에 필요한 에이전트 수 (2=직통, 3=릴레이) |
| `metadata` | 추가 메타데이터 (확장용, 현재는 비어있음) |

### 학습 과정에서 이 데이터가 쓰이는 흐름

```
train.jsonl의 한 줄
     │
     ▼
TaskGenerator.load_dataset("data/train.jsonl")
     │
     ▼
환경(OgentiEnvironment)이 Phase에 맞는 태스크를 샘플링
     │
     ▼
┌─────────── 1 Episode ───────────┐
│                                 │
│  Encoder: instruction 수신      │
│     ↓                           │
│  "SELECT * FROM users..."       │
│     ↓  encode()                 │
│  ξ·REVIEW·SQL·INJECT·◊          │  ← 프로토콜 메시지 (5토큰!)
│     ↓  channel.send()           │
│  [noise injection 확률적]       │
│     ↓  decode()                 │
│  Decoder: "SQL injection..."    │
│     ↓                           │
│  reward = similarity(복원, reference)
│  = similarity("SQL injection...", "SQL injection vulnerability...")
│  = 0.87  ← 꽤 잘했네                │
│                                 │
│  PPO update → 프로토콜 개선      │
└─────────────────────────────────┘
```

핵심은 **instruction이 얼마나 적은 토큰으로 압축되면서도, reference를 정확히 복원할 수 있느냐**. 이게 Ogenti의 전부다.

---

## ◆ 가동법

### 1. 기본 실행 — 데이터셋 생성

```bash
python scripts/generate_dataset.py
```

끝. 이러면:
- `data/train.jsonl` — 93개 학습 태스크 생성
- `data/eval.jsonl` — 17개 평가 태스크 생성

### 2. 생성된 데이터 확인

```bash
# 첫 번째 태스크 보기
head -1 data/train.jsonl | python -m json.tool

# 카테고리별 개수 세기
python -c "
import json
from collections import Counter
tasks = [json.loads(l) for l in open('data/train.jsonl')]
for cat, n in Counter(t['category'] for t in tasks).most_common():
    print(f'  {cat}: {n}')
"

# 총 태스크 수
wc -l data/train.jsonl data/eval.jsonl
```

### 3. 프로덕션 학습에 연결

```bash
# 방법 1: 자동 감지 (run_production.py가 data/train.jsonl을 자동으로 찾음)
python run_production.py

# 방법 2: 명시적 지정
python run_production.py --dataset data/train.jsonl

# 방법 3: config에서 지정 (configs/production.json)
{
  "dataset_path": "data/train.jsonl",
  "eval_dataset_path": "data/eval.jsonl"
}
```

### 4. Quick Test (100에피소드 짧은 테스트)

```bash
python run_production.py --quick
```

이러면 100 에피소드만 돌리면서 전체 파이프라인이 잘 작동하는지 확인. 태스크도 자동으로 로드됨.

### 5. RunPod / GPU 서버에서

```bash
# 1) 서버 셋업 (원커맨드)
bash scripts/setup_runpod.sh

# 2) 학습 시작 (대시보드 포함)
python run_production.py

# 3) 브라우저에서 http://<서버IP>:8000 접속
#    → 실시간 학습 모니터링 대시보드
```

---

## ◆ 커스텀 태스크 추가하기

`generate_dataset.py`에 새 태스크를 추가하는 건 초간단:

### 한 줄 추가

```python
add("카테고리", "instruction 텍스트", "reference 정답", difficulty=0.5)
```

### 실전 예시

```python
# 한국어 요약 태스크 추가
add("summarize",
    "요약해줘: 트랜스포머 아키텍처는 셀프 어텐션을 사용해 시퀀스 데이터를 병렬 처리한다.",
    "트랜스포머는 셀프 어텐션으로 시퀀스를 병렬 처리하는 아키텍처.",
    difficulty=0.3)

# 멀티홉 릴레이 태스크 추가
add("relay_translate",
    "3단계 릴레이: Python 코드 → 의사코드 → 한국어 설명: 'sorted(data, key=lambda x: x[1])'",
    "데이터를 두 번째 요소 기준으로 정렬하는 코드. 각 항목의 [1]번 인덱스 값을 비교해서 오름차순 배열.",
    difficulty=0.7,
    num_agents=3)
```

### 외부 JSONL 직접 추가도 가능

`data/train.jsonl` 파일 끝에 직접 한 줄 추가:

```bash
echo '{"task_id":"custom_001","category":"qa","instruction":"Ogenti가 뭐야?","reference":"AI끼리 소통하는 압축 프로토콜","difficulty":0.3,"num_agents":2,"metadata":{}}' >> data/train.jsonl
```

### 지원하는 카테고리 목록

```
summarize           요약
translate           번역/스타일 변환
qa                  질의응답
code_review         코드 리뷰
data_analysis       데이터 분석
instruction_following  지시 수행
creative_writing    창작
math                수학/계산
reasoning           논리 추론
chain_summarize     체이닝 요약 (멀티홉)
relay_translate     릴레이 번역 (멀티홉)
multi_step_qa       다단계 QA (멀티홉)
```

---

## ◆ 프로덕션 학습이랑 어떻게 연결되는데?

전체 데이터 흐름을 그림으로 보면:

```
generate_dataset.py
        │
        ▼
  data/train.jsonl  (93 tasks)
  data/eval.jsonl   (17 tasks)
        │
        ▼
  ┌── run_production.py ──────────────────────────────┐
  │                                                   │
  │  TrainConfig.load("configs/production.json")      │
  │    └─ dataset_path = "data/train.jsonl"           │
  │                                                   │
  │  OgentiTrainer(config, bridge)                    │
  │    ├─ TaskGenerator.load_dataset(train.jsonl)     │
  │    ├─ OgentiEnvironment(task_generator)           │
  │    │                                              │
  │    ├─ Phase 0: warmup (5K episodes)               │
  │    │   └─ summarize, translate, qa만 샘플링        │
  │    │                                              │
  │    ├─ Phase 1: simple (15K episodes)              │
  │    │   └─ + code_review, data_analysis 추가        │
  │    │                                              │
  │    ├─ Phase 2: complex (20K episodes)             │
  │    │   └─ + chain, relay, multi_step 추가          │
  │    │   └─ num_agents=3인 태스크 활성화              │
  │    │                                              │
  │    ├─ Phase 3: generalize (10K episodes)          │
  │    │   └─ 전체 12개 카테고리 + 노이즈 15%           │
  │    │                                              │
  │    └─ Phase 4: universalize (8K episodes)         │
  │        └─ Knowledge Distillation                  │
  │        └─ Qwen LoRA → Universal Adapter 추출       │
  │                                                   │
  │  TrainerBridge → WebSocket → 대시보드 실시간 전송    │
  │                                                   │
  └───────────────────────────────────────────────────┘
        │
        ▼
  checkpoints/universal_adapter/
    ├── adapter_config.json
    ├── protocol_vocab.json
    ├── pph_weights.safetensors    (Protocol Projection Head)
    └── prh_weights.safetensors    (Protocol Reconstruction Head)
        │
        ▼
  어떤 LLM이든 .attach(model, tokenizer) → AI-to-AI 통신 가능
```

---

## ◆ 현재 데이터셋 통계

```
╔══════════════════════════════════════════╗
║       Ogenti Dataset v1.0               ║
╠══════════════════════════════════════════╣
║                                         ║
║  Total Tasks:    110                    ║
║  Train Split:    93  (85%)              ║
║  Eval Split:     17  (15%)              ║
║                                         ║
║  Categories:     12                     ║
║  Difficulty:     0.2 ~ 0.8             ║
║  Avg Difficulty: 0.45                  ║
║                                         ║
║  2-Agent Tasks:  101                   ║
║  3-Agent Tasks:  9   (멀티홉 전용)      ║
║                                         ║
╠══════════════════════════════════════════╣
║  Category Breakdown:                    ║
║                                         ║
║  qa                    25  ████████████ ║
║  summarize             18  █████████    ║
║  instruction_following 10  █████        ║
║  code_review           10  █████        ║
║  translate             10  █████        ║
║  math                   6  ███          ║
║  reasoning              6  ███          ║
║  creative_writing       6  ███          ║
║  data_analysis          5  ██           ║
║  chain_summarize        5  ██           ║
║  multi_step_qa          5  ██           ║
║  relay_translate        4  ██           ║
║                                         ║
╚══════════════════════════════════════════╝
```

### 왜 QA가 제일 많아?

의도적이다. QA는 **정답이 짧고 명확**하다 ("Paris", "8", "O(log n)"). 프로토콜 학습 초기에 "이 긴 질문을 어떻게 짧게 압축하면 정답을 복원할 수 있을까?"를 배우는 데 QA만한 게 없다. 일종의 **프로토콜 발견의 마중물** 역할.

### 110개면 좀 적지 않아?

맞다. 하지만:

1. **Ogenti 학습은 페어링 기반** — 같은 태스크를 수만 번 반복하면서 프로토콜을 "발명"하는 구조. 자연어 이해 학습이 아니라 **프로토콜 최적화** 학습이라 태스크 다양성보다 **반복 학습**이 더 중요
2. **5만 에피소드에 110개면 각 태스크 평균 ~450회 반복** — 이게 의도된 수치. 같은 문제를 다른 프로토콜로 계속 풀어보면서 최적의 압축 방식을 찾아가는 것
3. **확장은 쉽다** — `add()` 한 줄이면 태스크 추가. HuggingFace Datasets에서 알파카 데이터셋 같은 걸 변환해서 쏟아넣을 수도 있음

### 나중에 스케일업하려면?

```python
# datasets 라이브러리로 대규모 데이터 로드
from datasets import load_dataset
ds = load_dataset("tatsu-lab/alpaca", split="train")

for row in ds:
    add("instruction_following",
        row["instruction"],
        row["output"],
        difficulty=0.5)
```

이러면 5만개+ 태스크로 확장 가능. 하지만 현재 110개로도 프로토콜 발견에는 충분하다.

---

## ◆ TL;DR

| 항목 | 내용 |
|------|------|
| **뭐임?** | Ogenti 학습용 태스크 데이터셋 생성기 |
| **파일** | `scripts/generate_dataset.py` |
| **출력** | `data/train.jsonl` + `data/eval.jsonl` |
| **태스크 수** | 110개 (93 train + 17 eval) |
| **카테고리** | 12종 (QA, 요약, 번역, 코드리뷰, 추론, ...) |
| **난이도** | 0.2 ~ 0.8, Phase별 커리큘럼 대응 |
| **실행법** | `python scripts/generate_dataset.py` |
| **학습 연결** | `python run_production.py` → 자동 로드 |

```bash
# 한 줄 요약:
python scripts/generate_dataset.py && python run_production.py
# 끝. 데이터 생성 → 학습 시작. 대시보드는 http://localhost:8000
```

---

*Built for Ogenti — where AI talks to AI, and we just watch the compression ratio go brrr 📉*
