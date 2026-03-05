# Series Platform — 확장 비전 & 로드맵

> **플랫폼명**: Series  
> **핵심 원칙**: 모든 시리즈는 **명확한 페인포인트**를 해결하는 LoRA 어댑터를 생성한다.  
> **출력물**: 암호화된 자체 확장자 파일 (AES-256-GCM)  
> **학습 방식**: MAPPO (Multi-Agent PPO)  
> **배포**: RunPod Serverless → 플랫폼 다운로드  

---

## 네이밍 규칙

| 규칙 | 예시 |
|------|------|
| 세상에 존재하지 않는 조어 | OGENTI, OVISEN |
| 같은 알파벳으로 시작하면 같은 시리즈 | O로 시작 → O-Series |
| 발음 쉬울 것 (3음절 이내) | 오젠티, 오비전 |
| 6자 내외 | OGENTI(6), OVISEN(6) |

---

## 확정 시리즈

### O-Series — AI 통신 압축 (구현 완료)

**페인포인트**: AI끼리 통신할 때 사람 말(자연어)로 대화하면 토큰 낭비가 미친듯이 심하다. GPT-4 API 호출 한 번에 수천 토큰 쓰는데, 실제 정보량은 몇십 토큰이면 충분함.

| 제품 | 기능 | 확장자 | 상태 |
|------|------|--------|------|
| **OGENTI** (오젠티) | 텍스트 통신 압축 — NL↔프로토콜 토큰 변환 | `.ogt` | ✅ 코어 완성, 학습 중 |
| **OVISEN** (오비전) | 이미지 압축 — 이미지↔압축 임베딩 변환 | `.oge` | ✅ 코어 완성 |

**기술 스택 (이미 구현됨)**:
- 백본: Qwen2.5-3B (텍스트) / CLIP·DINOv2·SigLIP (이미지)
- Encoder: 입력 → 5~30개 프로토콜 토큰 (목표 15× 압축)
- Decoder: 프로토콜 토큰 → 원본 복원
- 리워드: accuracy(0.4) + efficiency(0.3) + clarity(0.2) + generalization(0.1)
- 코드: `ogenti_core/` (~2,238 LOC), `ovisen_core/` (~735 LOC)

---

### P-Series — 할루시네이션 방지 (다음 개발 대상)

**페인포인트**: LLM이 헛소리를 한다. 자신감 넘치는 목소리로 틀린 말을 한다. 기업들이 LLM 도입을 망설이는 1번 이유. 2025년 기준 GPT-4조차 TruthfulQA에서 60%대 정확도. 의료/법률/금융에서 할루시네이션 = 소송감.

**제품명**: **PHIREN** (파이렌)

| 항목 | 내용 |
|------|------|
| 이름 | PHIREN (파이렌) |
| 시리즈 | P-Series |
| 확장자 | `.phr` |
| 매직바이트 | `PHR\x01` |
| 한 줄 설명 | "어댑터 하나 붙이면 LLM이 헛소리를 안 합니다" |

#### 작동 원리

```
[사용자 질문] 
    → Encoder: 질문 분석 → 사실 검증 프로토콜 토큰 생성
        - "이 주장의 근거가 있는가?"
        - "확실도 레벨은?"
        - "출처 추적 가능한가?"
    → Channel: 검증 토큰 전달
    → Decoder: 프로토콜 토큰 기반으로 답변 생성 시 "근거 없는 내용" 억제
        - 확실하지 않으면 "잘 모르겠습니다" 출력 유도
        - 확실한 부분만 답변에 포함

[출력] 사용자의 기존 LLM에 .phr 어댑터 로드 → 할루시네이션 감소
```

#### ogenti_core 패턴과의 매핑

| O-Series (OGENTI) | P-Series (PHIREN) |
|--------------------|--------------------|
| 자연어 → 압축 토큰 | 질문 → 사실검증 토큰 |
| 압축 토큰 → 자연어 복원 | 사실검증 토큰 → 근거 기반 답변 생성 |
| 압축률 리워드 | 사실 정확도 리워드 |
| ProtocolMessage (토큰 ID 시퀀스) | VerificationMessage (확신도 + 근거플래그) |
| 노이즈 주입 (채널 로버스트니스) | 적대적 질문 주입 (함정 질문 로버스트니스) |

#### 기술 스택

| 컴포넌트 | 선택 | 이유 |
|----------|------|------|
| 백본 모델 | Qwen2.5-3B 또는 Llama-3.1-8B | O-Series와 동일 LoRA 패턴 적용 가능 |
| LoRA 설정 | r=16, alpha=32, q/k/v/o | O-Series 동일 |
| 학습 데이터 | TruthfulQA + FEVER + HaluEval + 자체 생성 | 사실/거짓 쌍으로 구성 |
| Encoder | 질문+컨텍스트 → 확신도 프로토콜 토큰 | 새로 설계 |
| Decoder | 확신도 토큰 → 답변 필터링/생성 | 새로 설계 |
| 리워드 | factuality(0.45) + calibration(0.25) + helpfulness(0.20) + robustness(0.10) | 아래 상세 |
| 암호화 | AES-256-GCM, `PHR\x01` 매직 | O-Series 패턴 복사 |

#### 리워드 설계

| 컴포넌트 | 비중 | 측정 방법 |
|----------|------|-----------|
| **Factuality** | 0.45 | 답변의 각 주장을 ground-truth와 대조. NLI 모델로 entailment/contradiction 판별 |
| **Calibration** | 0.25 | 모델이 "확실하다"고 한 것 중 실제로 맞는 비율 (ECE — Expected Calibration Error 최소화) |
| **Helpfulness** | 0.20 | "모르겠습니다"만 반복하면 안 됨. 아는 것은 확실히 답변해야 함 |
| **Robustness** | 0.10 | 적대적/함정 질문(misleading premise)에 속지 않는 정도 |
| **패널티** | - | 자신있게 틀린 답변: -1.0 / 확인 가능한 사실인데 "모르겠습니다": -0.3 |

#### 학습 데이터 구성

| 데이터셋 | 용도 | 크기 (예상) |
|----------|------|-------------|
| **TruthfulQA** | 사람이 자주 틀리는 질문들 | ~800 질문 |
| **FEVER** | 사실 검증 (Supported/Refuted/NotEnough) | ~185K claims |
| **HaluEval** | LLM 할루시네이션 탐지 벤치마크 | ~35K 샘플 |
| **자체 생성** | GPT-4로 함정 질문 생성 → 사람이 검수 | ~5K (목표) |

#### 파일 구조 (신규 생성)

```
phiren_core/
├── __init__.py          # 모듈 export (lazy loading)
├── protocol.py          # VerificationMessage, ConfidenceLevel, ClaimType
├── encoder.py           # PhirenEncoder — 질문→검증 토큰
├── decoder.py           # PhirenDecoder — 검증 토큰→근거 기반 답변
├── channel.py           # VerificationChannel — 검증 토큰 라우팅
└── adapter.py           # PhirenAdapter — 범용 모델 부착용 (Phase 4)

phiren_train/
├── __init__.py
├── config.py            # PhirenTrainingConfig
├── agents.py            # FactCheckerAgent, GeneratorAgent
├── environment.py       # 사실검증 환경 (질문→답변→검증 루프)
├── rewards.py           # Factuality + Calibration + Helpfulness + Robustness
├── curriculum.py        # 쉬운 사실→어려운 사실→함정→일반화
├── train.py             # MAPPO 학습 루프 (ogenti_train 기반)
└── server.py            # 학습 모니터 WebSocket

ogenti_platform/
├── phr_crypto.py        # .phr 암호화/복호화 (ogt_crypto.py 복사 + 매직바이트 변경)
└── ...                  # 기존 라우터에 P-Series 엔드포인트 추가
```

#### 개발 예상 기간

| 단계 | 기간 | 상세 |
|------|------|------|
| 1. 프로토콜 설계 (`protocol.py`) | 3일 | VerificationMessage, ConfidenceLevel 정의 |
| 2. 코어 모듈 (`encoder.py` + `decoder.py` + `channel.py`) | 2주 | 가장 큰 작업. ogenti_core 패턴을 사실검증 도메인으로 변환 |
| 3. 리워드 함수 (`rewards.py`) | 1주 | NLI 모델 통합, ECE 계산, factuality 스코어링 |
| 4. 학습 파이프라인 (`train.py` + `agents.py` + `environment.py`) | 2주 | MAPPO 루프 적응. 60~70% 기존 코드 재사용 |
| 5. 데이터 수집/전처리 | 1.5주 | TruthfulQA + FEVER + HaluEval 통합, 함정 질문 생성 |
| 6. 학습 실행 + 튜닝 | 2주 | A100 기준. 하이퍼파라미터 튜닝 포함 |
| 7. 범용 어댑터 (`adapter.py`) | 2주 | Phase 4 distillation — 다양한 모델에 붙일 수 있게 |
| 8. 플랫폼 통합 + 암호화 | 3일 | phr_crypto.py + API 엔드포인트 + 대시보드 |
| 9. 테스트 + 벤치마크 | 1주 | TruthfulQA/HaluEval 기준 Before/After 비교 |
| **합계** | **약 10~12주** | 1인 기준. O-Series 경험 있는 개발자 |

#### 마케팅 포인트

- "`.phr` 파일 하나로 당신의 LLM 할루시네이션을 줄입니다"
- Before/After 데모: 같은 질문, 어댑터 On/Off 비교
- TruthfulQA 점수 향상률 (예: 60% → 82%)
- 기업 세일즈: "우리 사내 LLM에 붙이면 법적 리스크 감소"

---

## Series 플랫폼 공통 아키텍처

### 모든 시리즈가 공유하는 것

```
Series Platform (series.xxx)
│
├── 공통 인프라 (이미 구현됨)
│   ├── 인증: JWT + Stripe 빌링
│   ├── GPU 디스패치: RunPod Serverless
│   ├── 암호화: AES-256-GCM (시리즈별 매직바이트만 다름)
│   ├── 모니터링: WebSocket + REST 폴백
│   └── 대시보드: 16-bit 레트로 UI
│
├── O-Series (통신 압축) ✅ 완성
│   ├── ogenti_core/  → .ogt
│   └── ovisen_core/  → .oge
│
├── P-Series (할루시네이션 방지 + 아첨 방지) 🔨 다음
│   ├── phiren_core/  → .phr (할루시네이션 방지)
│   └── parhen_core/  → .prh (아첨 방지, Anti-Sycophancy)
│
├── M-Series (위치 무관 리콜) 📋 설계 완료
│   └── murhen_core/  → .mrh (Lost-in-the-Middle 해결)
│
└── [미래 시리즈] → 검증 후 추가
```

### 시리즈 추가 레시피 (표준 절차)

새 시리즈 = 아래 체크리스트:

```
□ 1. 페인포인트 정의 (한 문장)
□ 2. 이름 확정 (조어, 6자, 3음절)
□ 3. 확장자 확정 (3자, 매직바이트 4바이트)
□ 4. {name}_core/ 생성
│   ├── protocol.py — 도메인 특화 메시지 타입
│   ├── encoder.py — 입력→압축 표현
│   ├── decoder.py — 압축 표현→출력
│   ├── channel.py — 메시지 라우팅
│   └── adapter.py — 범용 모델 부착 (Phase 4)
□ 5. {name}_train/ 생성
│   ├── rewards.py — 4-컴포넌트 리워드 (도메인 특화)
│   ├── train.py — MAPPO 루프 (70% 재사용)
│   └── ...
□ 6. ogenti_platform/{ext}_crypto.py — 암호화 (매직바이트만 교체)
□ 7. RunPod worker config 추가
□ 8. 대시보드 페이지 추가
□ 9. 벤치마크 Before/After 준비
```

### 매직바이트 레지스트리

| 시리즈 | 확장자 | 매직바이트 | 상태 |
|--------|--------|-----------|------|
| O-Series (OGENTI) | `.ogt` | `OGT\x01` | ✅ 구현 |
| O-Series (OVISEN) | `.oge` | `OGE\x01` | ✅ 구현 |
| P-Series (PHIREN) | `.phr` | `PHR\x01` | 🔨 예정 |
| P-Series (PARHEN) | `.prh` | `PRH\x01` | 📋 설계 |
| M-Series (MURHEN) | `.mrh` | `MRH\x01` | 📋 설계 |

---

## 수익 모델

| 모델 | 설명 |
|------|------|
| **어댑터 단건 판매** | 모델별 `.phr` 파일 — $29~$99/개 |
| **구독** | 월간 업데이트 (최신 데이터로 재학습된 어댑터) — $19~$49/월 |
| **기업용** | 커스텀 학습 (자사 데이터 + MAPPO) — $500~$5,000/건 |
| **API** | 어댑터 생성 API — 토큰/시간 기반 과금 |

---

## 우선순위 로드맵

| 순서 | 시리즈 | 이유 |
|------|--------|------|
| 1️⃣ | O-Series (OGENTI 학습 완료) | 이미 진행 중. A100에서 학습 재개 필요 |
| 2️⃣ | P-Series (PHIREN 개발 시작) | 페인포인트 최강. 시장 즉시 수요. 기술 검증 불필요 (할루시네이션은 누구나 겪음) |
| 3️⃣ | P-Series (PARHEN 설계 완료) | Anti-Sycophancy — LLM이 사용자 의견에 동조하는 문제 해결 |
| 4️⃣ | M-Series (MURHEN 설계 완료) | Lost-in-the-Middle — 긴 컨텍스트 중간 정보 유실 해결 |
| 5️⃣ | 추가 시리즈 검증 | 검증 후 추가 |

---

## 기술 리스크 & 대응

| 리스크 | 영향 | 대응 |
|--------|------|------|
| 할루시네이션 측정 자체가 어려움 | 리워드 함수 부정확 → 학습 실패 | NLI 모델(DeBERTa-v3-large-mnli) 사용 + 사람 검수 병행 |
| Factuality reward가 수렴 안 함 | 학습 불안정 | curriculum: 명확한 사실→애매한 사실→함정 순서로 난이도 조절 |
| 어댑터가 모델을 너무 보수적으로 만듦 | "모르겠습니다"만 반복 → 실용성 0 | Helpfulness 리워드(0.20)로 균형. "아는 건 답해라" 패널티 |
| O-Series 대비 학습 데이터 확보 어려움 | 데이터 부족 | 공개 데이터셋(TruthfulQA+FEVER+HaluEval) + GPT-4 합성 |
| RunPod A100 비용 | 학습 비용 높음 | O-Series와 GPU 시간 공유. 순차 학습 |
