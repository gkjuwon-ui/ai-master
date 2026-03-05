# M-Series 신제품 설계서 — Lost-in-the-Middle 해결

> **시리즈**: M-Series (신규)  
> **상태**: 설계 단계  
> **핵심 키워드**: 위치 무관 기억 (Position-Agnostic Recall)  

---

## 1. 페인포인트

### 문제 정의 (한 문장)

**LLM은 컨텍스트 윈도우가 200K여도 양 끝 5%만 기억하고 가운데 90%를 날린다.**

### 상세 설명

"Lost in the Middle" 현상 (Liu et al., 2023):

```
       기억도 (Recall Accuracy)
  100% │■■■                                          ■■■
       │  ■■                                      ■■
   80% │    ■                                    ■
       │     ■                                  ■
   60% │      ■                                ■
       │       ■■                            ■■
   40% │         ■■■                      ■■■
       │            ■■■■            ■■■■■
   20% │                ■■■■■■■■■■■■
       │
    0% └───────────────────────────────────────────
       위치1   위치25%    위치50%    위치75%   위치100%
       (시작)                                  (끝)

       전형적인 U-shaped recall curve
       → 시작과 끝만 기억, 가운데는 거의 무시
```

### 실제 피해 사례

| 상황 | 문제 | 결과 |
|------|------|------|
| **RAG 시스템** | 검색된 문서 10개 중 5번째(가운데)에 정답이 있으면 무시 | 정답이 있는데도 "모르겠습니다" |
| **긴 문서 요약** | 논문 50페이지 → 서론과 결론만 요약, Body 날아감 | 핵심 실험 결과 누락 |
| **멀티턴 대화** | 20턴 대화에서 턴 8~12 내용 소실 | "아까 말씀하셨잖아요" → "무슨 말씀이셨죠?" |
| **코드 분석** | 1000줄 파일에서 300~700번째 줄 함수 무시 | 중간에 있는 버그를 못 찾음 |
| **법률 문서 검토** | 계약서 중간 조항(핵심 약관) 누락 | 중요한 조건 놓침 |

### 왜 컨텍스트 윈도우를 키우는 것으로 해결 안 되는가

```
128K 윈도우   → 가운데 90K 날림
256K 윈도우   → 가운데 230K 날림  
1M 윈도우     → 가운데 900K 날림

윈도우가 커질수록 날리는 양도 비례해서 증가
→ 윈도우 크기 문제 ✗, 주의력(Attention) 분포 문제 ✓
```

### 근본 원인: Attention의 위치 편향

1. **Primacy Bias**: Transformer 아키텍처에서 앞쪽 토큰이 attention sink 역할 → 뒤의 토큰들이 앞쪽을 과도하게 참조
2. **Recency Bias**: Auto-regressive 생성 시 최근 토큰에 더 높은 attention → 끝부분 과대 반영
3. **학습 데이터 편향**: 웹 텍스트에서 중요 정보가 서두/결론에 몰려 있는 경향 → 모델이 "가운데는 덜 중요하다" 학습

---

## 2. 솔루션 전략

### 접근법: Attention Redistribution via Adversarial Training

컨텍스트 윈도우를 늘리는 게 아니라, **기존 윈도우 안에서 주의력(Attention)을 균등하게 재분배**하는 LoRA 어댑터.

### MARL 구조

```
┌──────────────────────────────────────────────────┐
│              Adversarial Co-Evolution            │
│                                                  │
│  ┌───────────────┐       ┌───────────────┐       │
│  │   Scrambler   │       │   Retainer    │       │
│  │  (Red Team)   │ ────▶ │  (Blue Team)  │       │
│  │               │       │               │       │
│  │ 목표:         │       │ 목표:         │       │
│  │ 중요 정보를   │       │ 위치에 관계   │       │
│  │ 가장 기억     │       │ 없이 모든     │       │
│  │ 못하는 위치에 │       │ 정보를 균등   │       │
│  │ 매장하라      │       │ 하게 기억     │       │
│  └───────────────┘       └───────────────┘       │
│                                                  │
│  Scrambler가 교묘해질수록 Retainer도 강해짐      │
│  → 결국 position-agnostic recall 달성            │
└──────────────────────────────────────────────────┘
```

#### Scrambler Agent (Red Team)

| 항목 | 내용 |
|------|------|
| **역할** | 문맥을 재배열하거나 노이즈를 삽입해서, 중요 정보를 Retainer가 가장 놓치기 쉬운 위치에 배치 |
| **학습 대상** | 어떤 위치, 어떤 주변 맥락, 어떤 정보 밀도에서 Retainer가 가장 약한지 학습 |
| **능력** | 정보 위치 조작, 산만한 문맥(distractor) 삽입, 핵심 정보 분산 배치, 유사 정보로 혼동 유발 |
| **보상** | Retainer가 중요 정보를 놓치면 +reward |
| **LoRA** | 내부 전용 (배포 안 함) |

#### Retainer Agent (Blue Team)

| 항목 | 내용 |
|------|------|
| **역할** | 컨텍스트 내 어떤 위치에 있든 중요 정보를 균등하게 인식하고 활용 |
| **학습 대상** | 위치 편향 극복. U-curve → 일직선으로 recall curve 평탄화 |
| **핵심 능력** | (1) 전체 위치 균등 주의 (2) 다중 위치 정보 종합 (3) distractor 무시 |
| **보상** | 위치 무관하게 정보 회수 시 +reward. 특히 mid-region(30~70%) 회수 시 가산점 |
| **LoRA** | **이것이 배포용 어댑터** |

### 핵심 통찰: 위치가 아닌 중요도로 Attend

```
  현재 LLM의 Attention 패턴:           목표 Attention 패턴:
  ┌─────────────────────┐             ┌─────────────────────┐
  │ ████████  (위치 1)  │             │ ███  (관련도 높음)  │
  │ ██████   (위치 2)   │             │ █    (관련도 낮음)  │
  │ ███     (위치 3)    │             │ ████ (관련도 높음)  │
  │ █      (위치 50)    │             │ ██   (관련도 중간)  │
  │ █      (위치 51)    │  ────────▶  │ ████ (관련도 높음)  │
  │ ███     (위치 98)   │             │ █    (관련도 낮음)  │
  │ ██████   (위치 99)  │             │ ███  (관련도 높음)  │
  │ ████████  (위치100) │             │ █    (관련도 낮음)  │
  └─────────────────────┘             └─────────────────────┘
  위치 기반 → 편향 심함                중요도 기반 → 균등
```

---

## 3. 리워드 함수

### 총 리워드

$$R_{total} = 0.35 \cdot R_{recall} + 0.30 \cdot R_{uniformity} + 0.20 \cdot R_{synthesis} + 0.15 \cdot R_{robustness}$$

### 개별 컴포넌트

| 컴포넌트 | 비중 | 측정 방법 | 왜 이 비중인가 |
|----------|------|-----------|----------------|
| **R_recall** | 0.35 | 모든 위치의 핵심 정보 회수 정확도. F1 score | 기본 능력. 정보를 찾아야 함 |
| **R_uniformity** | 0.30 | Recall의 위치별 표준편차 → 0에 가까울수록 보상 | 핵심 목표. U-curve 평탄화 |
| **R_synthesis** | 0.20 | 분산된 정보(위치 10% + 50% + 80%)를 종합한 답변의 정확도 | 단순 회수가 아닌 종합 활용 능력 |
| **R_robustness** | 0.15 | 컨텍스트 길이 변화(1K→8K→32K→128K) 시 성능 유지 정도 | 범용성 |

### 패널티 설계

| 상황 | 패널티 | 이유 |
|------|--------|------|
| 가운데 위치(30~70%) 정보 완전 누락 | -1.0 | 제품 존재 이유 |
| 시작/끝만 활용한 답변 생성 | -0.8 | 기존 LLM과 다를 바 없음 |
| Distractor를 핵심 정보로 오인 | -0.5 | 노이즈 필터링 실패 |
| 길이 증가 시 급격한 성능 저하 | -0.3 | 범용성 부족 |

### R_uniformity 상세 — 킬러 메트릭

이 메트릭이 이 제품의 핵심.

```python
def compute_uniformity(recall_by_position: dict[str, float]) -> float:
    """
    위치별 recall 정확도의 균등성 측정.
    
    recall_by_position = {
        "0-10%":  0.95,   # 시작 부분
        "10-20%": 0.88,
        "20-30%": 0.72,
        "30-40%": 0.45,   # 죽음의 구간
        "40-50%": 0.38,   # 죽음의 구간
        "50-60%": 0.42,   # 죽음의 구간
        "60-70%": 0.48,   # 죽음의 구간
        "70-80%": 0.75,
        "80-90%": 0.89,
        "90-100%": 0.93   # 끝 부분
    }
    → std_dev = 0.22, 불균등  → 낮은 점수
    
    이상적 결과:
        모든 구간: 0.85~0.90
    → std_dev ≈ 0.02, 균등   → 높은 점수
    """
    values = list(recall_by_position.values())
    mean = sum(values) / len(values)
    std_dev = (sum((v - mean) ** 2 for v in values) / len(values)) ** 0.5
    
    # std_dev가 0에 가까울수록 균등 → 높은 보상
    uniformity_score = max(0.0, 1.0 - (std_dev / 0.3))
    
    # 가운데 구간(30-70%) 평균이 양 끝 평균보다 낮으면 추가 패널티
    mid_avg = mean  # 30-70% 구간 평균
    edge_avg = mean  # 0-30% + 70-100% 평균
    if mid_avg < edge_avg * 0.8:
        uniformity_score *= 0.7  # 30% 감점
    
    return uniformity_score
```

---

## 4. 학습 데이터

### 데이터셋 구성

| 데이터셋 | 용도 | 크기 (예상) | 출처 |
|----------|------|-------------|------|
| **Multi-Needle** | 여러 정보를 다양한 위치에 매장 → 전부 찾기 | ~15K | 자체 생성 |
| **Position-Shuffle QA** | 같은 QA 쌍을 위치만 바꿔서 테스트 | ~25K | NQ/SQuAD 기반 변환 |
| **Long-Doc Comprehension** | 긴 문서에서 중간 단락 대상 질문 | ~10K | SCROLLS, QuALITY 기반 |
| **Cross-Position Reasoning** | 시작+중간+끝 정보를 종합해야 답 가능 | ~15K | 자체 생성 |
| **Distractor Injection** | 핵심 정보 주변에 유사하지만 다른 정보 삽입 | ~10K | 자체 생성 |

### Multi-Needle 데이터 예시 (핵심 데이터셋)

```json
{
  "context_length": 32000,
  "needles": [
    {"fact": "프로젝트 예산은 5억원이다", "position": "8%",  "id": "needle_1"},
    {"fact": "마감일은 12월 15일이다",    "position": "35%", "id": "needle_2"},
    {"fact": "담당자는 김철수 부장이다",   "position": "52%", "id": "needle_3"},
    {"fact": "승인 조건은 3명 이상 동의",  "position": "71%", "id": "needle_4"},
    {"fact": "위약금은 계약금의 20%이다",  "position": "89%", "id": "needle_5"}
  ],
  "haystack": "사업 계획서 전문 (비즈니스 관련 일반 텍스트로 채움)",
  "questions": [
    {"q": "프로젝트 예산은?",    "a": "5억원",           "target_needle": "needle_1"},
    {"q": "마감일은?",          "a": "12월 15일",       "target_needle": "needle_2"},
    {"q": "총 필요 동의 인원?",  "a": "3명 이상",        "target_needle": "needle_4"},
    {"q": "예산 대비 위약금은?",  "a": "1억원 (5억의 20%)", "target_needle": ["needle_1", "needle_5"], "type": "cross-position"}
  ],
  "scoring": "5개 중 5개 정황 → 1.0, 양 끝만 맞추면 ~0.4 (가운데 3개 못 맞추니까)"
}
```

### Position-Shuffle QA 예시

```json
{
  "base_qa": {
    "question": "수도의 인구는?",
    "answer": "약 970만명",
    "source_sentence": "서울의 인구는 약 970만명이다."
  },
  "shuffled_versions": [
    {"position": "5%",  "context": "[answer at start...32K text]"},
    {"position": "25%", "context": "[...answer at 25%...32K text]"},
    {"position": "50%", "context": "[...answer at middle...32K text]"},
    {"position": "75%", "context": "[...answer at 75%...32K text]"},
    {"position": "95%", "context": "[32K text...answer at end]"}
  ],
  "expected": "5개 위치 모두에서 동일한 정확도로 '약 970만명' 답변",
  "current_reality": "5%와 95% 위치: ~95% 정답률, 50% 위치: ~40% 정답률"
}
```

### Cross-Position Reasoning 예시

```json
{
  "context_length": 64000,
  "distributed_facts": [
    {"position": "12%", "fact": "회사 A의 2024년 매출은 100억원"},
    {"position": "47%", "fact": "회사 A의 영업이익률은 15%"},
    {"position": "83%", "fact": "회사 A의 부채비율은 120%"}
  ],
  "question": "회사 A의 영업이익과 재무 건전성을 종합 평가하시오",
  "expected_answer": "매출 100억 × 영업이익률 15% = 영업이익 15억. 부채비율 120%로 다소 높음. 영업이익은 양호하나 재무구조 개선 필요.",
  "why_hard": "세 가지 정보가 12%, 47%, 83%에 분산 → 특히 47%의 영업이익률을 놓치면 계산 불가"
}
```

---

## 5. 출력 포맷

### 어댑터 적용 시 모델 출력에 추가되는 메타데이터

```json
{
  "response": "프로젝트 예산은 5억원이며, 마감일은 12월 15일입니다...",
  "retention_guard": {
    "context_coverage": 0.92,
    "position_recall": {
      "0-20%":   {"recall": 0.95, "facts_found": 1, "facts_total": 1},
      "20-40%":  {"recall": 0.90, "facts_found": 1, "facts_total": 1},
      "40-60%":  {"recall": 0.88, "facts_found": 1, "facts_total": 1},
      "60-80%":  {"recall": 0.91, "facts_found": 1, "facts_total": 1},
      "80-100%": {"recall": 0.93, "facts_found": 1, "facts_total": 1}
    },
    "uniformity_score": 0.97,
    "cross_position_synthesis": true,
    "attention_distribution": "UNIFORM"
  }
}
```

### attention_distribution 분류

| 클래스 | 설명 | uniformity_score 범위 |
|--------|------|-----------------------|
| `UNIFORM` | 전 위치 균등 recall | 0.85 ~ 1.0 |
| `MILD_BIAS` | 약간의 위치 편향 존재 | 0.65 ~ 0.85 |
| `U_SHAPED` | 전형적 U-curve (양끝 편향) | 0.35 ~ 0.65 |
| `SEVERE_LOSS` | 가운데 대부분 소실 | 0.0 ~ 0.35 |

---

## 6. 기술 스택

| 컴포넌트 | 선택 | 이유 |
|----------|------|------|
| 백본 모델 | Qwen2.5-3B / Llama-3.1-8B | 전 시리즈 동일 패턴 |
| LoRA | r=16, alpha=32, **attention layers 집중** (q/k/v/o) | Attention 재분배가 목적 → attention LoRA가 핵심 |
| MARL 알고리즘 | MAPPO | 전 시리즈 공통 |
| Recall 측정 | Exact Match + F1 + BERTScore | 위치별 회수 정확도 |
| Uniformity 측정 | 위치별 recall 표준편차 | 핵심 메트릭 |
| 암호화 | AES-256-GCM | 전 시리즈 공통 |

### LoRA 타겟 레이어 전략

```
일반 LoRA: q_proj, k_proj, v_proj, o_proj (모든 레이어 동일)

M-Series LoRA (차별점):
  - 깊은 레이어 (layer 20~32): attention weight 집중 수정
    → 이 레이어들이 long-range dependency 담당
  - 얕은 레이어 (layer 0~10): 건드리지 않음
    → local pattern (문법, 구문)은 이미 잘 작동
  - 중간 레이어 (layer 10~20): 경량 수정
    → 정보 라우팅 보조

결과: 같은 LoRA rank로도 위치 편향 수정에 더 효과적
```

### 학습 파이프라인

```
Phase 1: 단일 Needle 위치 다양화
  └─ 정보 1개를 위치 바꿔가며 → 어디서든 찾아야 함
  └─ 목표: 위치별 recall 편차 < 0.1

Phase 2: Multi-Needle 동시 검색
  └─ 정보 3~5개를 다양한 위치에 → 전부 찾기
  └─ 목표: 5개 중 5개 회수율 > 80%

Phase 3: Cross-Position Reasoning
  └─ 분산된 정보를 종합해서 추론
  └─ 가장 어려운 태스크: 가운데 정보가 빠지면 추론 불가

Phase 4: Distractor 내성
  └─ 핵심 정보 주변에 유사 정보(함정) 삽입
  └─ 진짜 정보만 골라서 활용

Phase 5: 적대적 공진화
  └─ Scrambler가 학습한 최적 매장 전략으로 공격
  └─ 최악의 위치 + 최강의 distractor 조합
  └─ Retainer가 이를 극복 → 범용 position-agnostic 능력
```

---

## 7. 제품명 확정

| 항목 | 내용 |
|------|------|
| **이름** | **MURHEN** (뮤르헨) |
| **유래** | Mur (벽, 장벽을 넘다) + Retention |
| **시리즈** | M-Series |
| **확장자** | `.mrh` |
| **매직바이트** | `MRH\x01` |
| **테마 컬러** | Yellow (#ffff55) |

> ✅ 이름 확정됨.

---

## 8. 파일 구조 (예정)

```
murhen_core/
├── __init__.py
├── protocol.py          # RetentionMessage, PositionMap, CoverageReport
├── scanner.py           # 전체 컨텍스트 스캔 — 위치별 중요도 매핑
├── retainer.py          # Attention 재분배 — 가운데 영역 강화
├── channel.py           # 메시지 라우팅
└── adapter.py           # 범용 모델 부착용

murhen_train/
├── __init__.py
├── config.py            # TrainingConfig
├── agents.py            # Scrambler (Red) + Retainer (Blue)
├── environment.py       # Multi-Needle + Position-Shuffle 환경
├── rewards.py           # recall + uniformity + synthesis + robustness
├── curriculum.py        # 5-phase curriculum
├── train.py             # MAPPO 학습 루프
└── server.py            # RunPod worker
```

---

## 9. 벤치마크 계획

### 기존 벤치마크 활용

| 벤치마크 | 설명 | 타겟 |
|----------|------|------|
| **Needle-in-a-Haystack** | Paul Graham 에세이 + 숨겨진 사실 1개 | 위치별 recall |
| **SCROLLS** | 초장문 문서 이해 | 긴 문서 종합 능력 |
| **QuALITY** | 장문 다지선다 QA | 문서 중간 정보 활용도 |
| **LongBench** | 6개 태스크 (요약/QA/코드 등) | 종합 장문 처리 |
| **InfiniteBench** | 100K+ 토큰 대상 벤치마크 | 초장문 recall |

### 자체 벤치마크 (M-Series 전용)

```
Multi-Needle Recall Test:
  - 5개 정보를 {5%, 25%, 50%, 75%, 95%}에 매장
  - 5개 전부 찾는 비율 측정
  - Before (base model): ~35% (양 끝 2개만 찾음)
  - After (M-adapter):    목표 >85%

Position-Agnostic Score:
  - 같은 QA를 위치 10개에서 테스트
  - recall의 표준편차 계산
  - Before: std_dev ≈ 0.22
  - After:  목표 std_dev < 0.05

Cross-Position Synthesis:
  - 3개 위치의 정보를 합쳐야 답 가능
  - Before: ~25% (가운데 정보 누락으로 추론 실패)
  - After:  목표 >75%
```

---

## 10. 마케팅 포인트

- **한 줄**: "컨텍스트 윈도우 200K인데 10K만 쓰고 있었습니다. 이제 200K 전부 씁니다."
- **데모**: 5-Needle 테스트 — 어댑터 On/Off로 가운데 정보 recall 비교
- **시각화**: U-shaped curve → Flat curve 애니메이션
- **핵심 메시지**: "컨텍스트 윈도우 크기가 문제가 아닙니다. 주의력 분배가 문제입니다."
- **기업 세일즈**: "RAG 파이프라인에 어댑터 하나 붙이면 검색 정확도가 올라갑니다"

---

## 11. 기존 시리즈와의 위치

```
Series Platform
├── O-Series — AI 통신 압축 ✅
│   ├── OGENTI (.ogt) — 텍스트 압축
│   └── OVISEN (.oge) — 이미지 압축
│
├── P-Series — AI 신뢰성 🔨
│   ├── PHIREN (.phr) — 할루시네이션 방지 (사실의 방패)
│   └── [신제품] (.???) — 아첨 방지 (줏대의 방패)
│
└── M-Series — AI 기억력 📋 NEW
    └── [신제품] (.???) — Lost-in-the-Middle 해결 (위치 무관 기억)
```

### P-Series와의 시너지

```
PHIREN:     "이 답변이 사실인가?" (사실 검증)
P-신제품:   "이 답변이 압력에 의해 바뀐 건가?" (줏대 검증)
M-신제품:   "이 답변이 전체 맥락을 반영했는가?" (기억 검증)

세 개 합치면: "사실에 기반하고, 압력에 안 흔들리고, 전체 맥락을 놓치지 않는 AI"
```

---

## 12. 매직바이트 레지스트리 (업데이트)

| 시리즈 | 제품 | 확장자 | 매직바이트 | 상태 |
|--------|------|--------|-----------|------|
| O-Series | OGENTI | `.ogt` | `OGT\x01` | ✅ 구현 |
| O-Series | OVISEN | `.oge` | `OGE\x01` | ✅ 구현 |
| P-Series | PHIREN | `.phr` | `PHR\x01` | 🔨 구현중 |
| P-Series | [미정] | `.???` | `???\x01` | 📋 설계 |
| M-Series | [미정] | `.???` | `???\x01` | 📋 설계 |
