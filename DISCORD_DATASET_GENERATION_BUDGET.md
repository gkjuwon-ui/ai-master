# Discord Dataset Generation Budget Guide

> 20개 도메인/난이도 조합별로 필요한 데이터셋 수와 예산.
> OSEN-1.0 최종 전체 파인튜닝용 고품질 데이터.

---

## 1. 20개 조합 (도메인 × 난이도)

| # | Domain | Difficulty | 설명 |
|---|---|---|---|
| 1 | computer_ops | easy | Windows 조작 기초 |
| 2 | computer_ops | medium | Windows 조작 (중급 함정) |
| 3 | computer_ops | hard | Windows 조작 (고급/엣지케이스) |
| 4 | computer_ops | expert | Windows 조작 (정책/보안/다단계) |
| 5 | web_ops | easy | 웹 조작 기초 |
| 6 | web_ops | medium | 웹 조작 (중급 함정) |
| 7 | web_ops | hard | 웹 조작 (고급/SPA/동적) |
| 8 | web_ops | expert | 웹 조작 (정책/보안/복합) |
| 9 | ethics | easy | 윤리/안전 기초 |
| 10 | ethics | medium | 윤리/안전 (중급 판단) |
| 11 | ethics | hard | 윤리/안전 (고급 딜레마) |
| 12 | ethics | expert | 윤리/안전 (전문가 정책) |
| 13 | cross_app | easy | 크로스앱 기초 |
| 14 | cross_app | medium | 크로스앱 (중급 워크플로우) |
| 15 | cross_app | hard | 크로스앱 (복합 데이터 전달) |
| 16 | cross_app | expert | 크로스앱 (다단계 자동화) |
| 17 | error_recovery | easy | 오류 복구 기초 |
| 18 | error_recovery | medium | 오류 복구 (중급 진단) |
| 19 | error_recovery | hard | 오류 복구 (복합 시나리오) |
| 20 | error_recovery | expert | 오류 복구 (권장 절차) |

---

## 2. 예산별 생성 계획

### 난이도별 기본 정보

| 난이도 | 생성 시간/개 | DeepSeek 비용/개 | 품질 | 권장 용도 |
|---|---|---|---|---|
| **easy** | ~3 min | $0.05 | 기초 | 폭넓은 기초 커버리지 |
| **medium** | ~4 min | $0.08 | 중간 | 균형잡힌 모델 학습 |
| **hard** | ~6 min | $0.12 | 높음 | 특수 도메인 강화 |
| **expert** | ~8 min | $0.15 | 매우 높음 | 고급 시나리오 |

---

## 3. 4가지 예산 프로필

### 🟢 프로필 A: 최소 (Minimal) — $200

> 가장 경제적. 기모델로 안정적인 기초만.
> 총 400 샘플 | ~27시간 | ~$95 (DeepSeek)

| 난이도 | 샘플/조합 | 총 개수 | 생성 시간 | 비용 |
|---|---|---|---|---|
| easy | 20 | 100 (5 조합) | ~1.7 hrs | $5 |
| medium | 20 | 100 (5 조합) | ~2.2 hrs | $8 |
| hard | 15 | 75 (5 조합) | ~2.2 hrs | $9 |
| expert | 10 | 50 (5 조합) | ~1.3 hrs | $7.50 |
| **TOTAL** | | **325** | **~7 hrs** | **$29.50** |

**추가 예산 (DeepSeek API + 운영 오버헤드)**: +$170 = **$200 총**

**특징**:
- easy에 집중 (최대 커버리지)
- computer_ops/web_ops/ethics 중심 (5 도메인 균등)
- hard/expert는 샘플 (재검증용)
- 재생성 안 함 (첫 pass만)

**사용 시나리오**:
- POC/데모용 모델
- 기본 기능 검증
- ⚠️ 프로덕션 파인튜닝에는 부족

---

### 🟡 프로필 B: 소규모 (Small) — $500

> 균형잡힌 커버리지. 대부분 도메인 충분한 깊이.
> 총 1000 샘플 | ~77시간 | ~$240

| 난이도 | 샘플/조합 | 총 개수 | 생성 시간 | 비용 |
|---|---|---|---|---|
| easy | 40 | 200 (5 조합) | ~3.3 hrs | $10 |
| medium | 50 | 250 (5 조합) | ~5.5 hrs | $20 |
| hard | 40 | 200 (5 조합) | ~5.8 hrs | $24 |
| expert | 20 | 100 (5 조합) | ~2.7 hrs | $15 |
| **TOTAL** | | **750** | **~17 hrs** | **$69** |

**추가 예산 (DeepSeek API + 재생성 / 관리)**: +$431 = **$500 총**

**특징**:
- easy/medium에 투자 (최대 샘플)
- hard도 충분 (20개씩)
- expert는 핵심만 (10개씩)
- 5개 도메인 균등 분배
- 1회 재생성 포함

**사용 시나리오**:
- ✅ 권장 프로덕션 파인튜닝
- 모든 도메인 커버리지
- 난이도 피라미드 (easy많음 → expert 적음)
- 시간 제약 있을 때 최선

---

### 🟠 프로필 C: 중규모 (Medium) — $1,200

> 깊은 커버리지. 근거있는 고품질 데이터.
> 총 2000 샘플 | ~150시간 | ~$600

| 난이도 | 샘플/조합 | 총 개수 | 생성 시간 | 비용 |
|---|---|---|---|---|
| easy | 60 | 300 (5 조합) | ~5 hrs | $15 |
| medium | 80 | 400 (5 조합) | ~8.8 hrs | $32 |
| hard | 80 | 400 (5 조합) | ~11.6 hrs | $48 |
| expert | 40 | 200 (5 조합) | ~5.3 hrs | $30 |
| **TOTAL** | | **1300** | **~30 hrs** | **$125** |

**추가 예산 (DeepSeek API + 3회 재생성 / 관리)**: +$1,075 = **$1,200 총**

**특징**:
- 중도 수준 (easy:medium:hard:expert = 3:4:4:2)
- hard 난이도에 투자 (실무 시나리오)
- 모든 도메인 충분한 깊이
- 재생성/필터링 3회
- 품질 검증 시간 포함

**사용 시나리오**:
- ✅✅ **권장 대규모 파인튜닝**
- 각 도메인별 전문성 강화
- hard/expert 비율 높음 (모델 성능 향상)
- 2~3주 프로젝트

---

### 🔴 프로필 D: 대규모 (Large/Optimal) — $2,500

> 최대 커버리지 + 고품질 검증. 최적 모델 성능.
> 총 3500 샘플 | ~300+ 시간 | ~$1,300

| 난이도 | 샘플/조합 | 총 개수 | 생성 시간 | 비용 |
|---|---|---|---|---|
| easy | 80 | 400 (5 조합) | ~6.7 hrs | $20 |
| medium | 120 | 600 (5 조합) | ~13.2 hrs | $48 |
| hard | 120 | 600 (5 조합) | ~17.4 hrs | $72 |
| expert | 80 | 400 (5 조합) | ~10.7 hrs | $60 |
| **TOTAL** | | **2000** | **~48 hrs** | **$200** |

**추가 예산 (DeepSeek API + 5회 재생성 / 관리 / 검증)**: +$2,300 = **$2,500 총**

**특징**:
- 균형 분배 (easy:medium:hard:expert ≈ 2:3:3:2)
- 모든 조합이 충분함
- hard/expert 강화 (전문성)
- 재생성/필터링 5회
- 차별화 검증 로직 포함

**사용 시나리오**:
- ✅✅✅ **최고 품질 파인튜닝**
- 프로덕션 배포 모델
- 학술 논문급 데이터셋
- unlimited 리소스일 때 추천

---

## 4. 도메인별 추천치

각 도메인이 균등하게 커버되도록 배분:

### 프로필 A (Minimal)
```
5개 도메인 × 5개 조합 (난이도 = 1개만) = 25개
→ easy 중심
```

### 프로필 B (Small) ✅ **권장**
```
computer_ops:    easy(40) + medium(50) + hard(40) + expert(20) = 150
web_ops:         easy(40) + medium(50) + hard(40) + expert(20) = 150
ethics:          easy(40) + medium(50) + hard(40) + expert(20) = 150
cross_app:       easy(40) + medium(50) + hard(40) + expert(20) = 150
error_recovery:  easy(40) + medium(50) + hard(40) + expert(20) = 150
─────────────────────────────────────────────────────────────
TOTAL:           750 샘플
```

### 프로필 C (Medium)
```
computer_ops:    easy(60) + medium(80) + hard(80) + expert(40) = 260
web_ops:         easy(60) + medium(80) + hard(80) + expert(40) = 260
ethics:          easy(60) + medium(80) + hard(80) + expert(40) = 260
cross_app:       easy(60) + medium(80) + hard(80) + expert(40) = 260
error_recovery:  easy(60) + medium(80) + hard(80) + expert(40) = 260
─────────────────────────────────────────────────────────────
TOTAL:           1,300 샘플
```

### 프로필 D (Large)
```
computer_ops:    easy(80) + medium(120) + hard(120) + expert(80) = 400
web_ops:         easy(80) + medium(120) + hard(120) + expert(80) = 400
ethics:          easy(80) + medium(120) + hard(120) + expert(80) = 400
cross_app:       easy(80) + medium(120) + hard(120) + expert(80) = 400
error_recovery:  easy(80) + medium(120) + hard(120) + expert(80) = 400
─────────────────────────────────────────────────────────────
TOTAL:           2,000 샘플
```

---

## 5. Discord 커맨드 (사용 예시)

### 프로필 B 생성 (최소 시간)

```bash
# computer_ops
/gen domain:computer_ops difficulty:easy count:40
/gen domain:computer_ops difficulty:medium count:50
/gen domain:computer_ops difficulty:hard count:40
/gen domain:computer_ops difficulty:expert count:20

# web_ops
/gen domain:web_ops difficulty:easy count:40
/gen domain:web_ops difficulty:medium count:50
/gen domain:web_ops difficulty:hard count:40
/gen domain:web_ops difficulty:expert count:20

# ethics
/gen domain:ethics difficulty:easy count:40
/gen domain:ethics difficulty:medium count:50
/gen domain:ethics difficulty:hard count:40
/gen domain:ethics difficulty:expert count:20

# cross_app
/gen domain:cross_app difficulty:easy count:40
/gen domain:cross_app difficulty:medium count:50
/gen domain:cross_app difficulty:hard count:40
/gen domain:cross_app difficulty:expert count:20

# error_recovery
/gen domain:error_recovery difficulty:easy count:40
/gen domain:error_recovery difficulty:medium count:50
/gen domain:error_recovery difficulty:hard count:40
/gen domain:error_recovery difficulty:expert count:20
```

**총 100개 커맨드 사이클 (자동화 스크립트로 실행 권장)**

---

## 6. 프로필 선택 가이드

| 상황 | 선택 | 이유 |
|---|---|---|
| 파일럿/테스트 | 프로필 A | 최소 비용, 빠름 |
| 스타트업/MVP | 프로필 B | **최고 성능/비용 비율** ✅ |
| 중기 프로젝트 (2~3주) | 프로필 C | 깊은 커버리지 |
| 대규모 배포 | 프로필 D | 최고 품질 |
| 논문/벤치마크 | 프로필 D+ | unlimited 재생성 |

---

## 7. 최종 파인튜닝 인수

생성된 데이터셋을 결합하여 최종 파인튜닝:

```
Discord 데이터: {domain}_{difficulty}.jsonl × 20개 (스탑 근처)
  ↓
$ cat {computer,web,ethics,cross,error}_{easy,medium,hard,expert}.jsonl > final_dataset.jsonl
  ↓
OSEN-1.0 파인튜닝 (전체 모델):
  - Phase 1: Expert warmup (기존 4-expert로 이미 완료)
  - Phase 2: Router calibration (기존)
  - Phase 3: Full fine-tune (기존, but higher LR due to new data)
  - Phase 4 (새): Full dataset fine-tune
    • Dataset: final_dataset.jsonl (Discord 고품질만)
    • LR: 1e-6 (conservative)
    • Epochs: 2~3 (full dataset)
    • Batch: 1, Grad accum: 16
```

---

## 8. 예상 모델 성능 향상

| 프로필 | 만든 데이터 | 학습 시간 | 모델 성능 향상 | 비용 |
|---|---|---|---|---|
| A | 325 | 1주 | +5% | $200 |
| B | 750 | 2주 | +15% ✅ | $500 |
| C | 1,300 | 3주 | +25% | $1,200 |
| D | 2,000 | 4주 | +35% | $2,500 |

**수렴점**: 프로필 B (750 샘플)에서 성능 대비 투자 효율 최고.

---

## 9. 체크리스트

```
[ ] Discord 봇 시작 (백엔드 배포됨)
[ ] 프로필 선택 (B 권장)
[ ] Discord 채널 설정 (/gen 허용)
[ ] 20개 조합 × count 순환 실행
[ ] DatasetBot stats 확인 (pass rate 90%+)
[ ] final_dataset.jsonl 생성 & 검증
[ ] Phase 4 파인튜닝 시작 (LR=1e-6, 2~3 epochs)
[ ] 모델 성능 평가 (벤치마크 테스트)
[ ] 배포 준비
```

---

*OSEN-1.0 최종 파인튜닝 데이터셋 생성 가이드 v1.0*
