# Ogenti 크레딧 시세 계산법

## 개요

시세(환율)는 **"1달러에 크레딧 몇 개를 주는가"** 를 나타냅니다.
- 기본 시세: `10 cr/$1` (1크레딧 = $0.10)
- 시세가 올라가면 → 크레딧 가치 하락 → 에이전트 크레딧 가격 상승
- 시세가 내려가면 → 크레딧 가치 상승 → 에이전트 크레딧 가격 하락

시세는 세 가지 요인으로 결정됩니다.

---

## 최종 공식

```
rate = baseRate × (1 − demandDeviation + supplyDeviation + issuanceDeviation)
```

`rate`는 `[5, 30]` 범위로 클램핑됩니다.

---

## Factor 1: 수요 압력 (Demand Pressure)

**24시간 내 환전소 매수/매도 볼륨 비율**

| 변수 | 설명 |
|------|------|
| `bought` | 24h 내 매수(BUY) 크레딧 + 구독 드립 크레딧 |
| `sold` | 24h 내 매도(SELL) 크레딧 |
| `totalVolume` | `bought + sold` |
| `buyPressure` | `(bought − sold) / totalVolume` → **-1 ~ +1** |
| `demandDeviation` | `buyPressure × 0.20` → **±20%** |

**효과:**
- 매수가 매도보다 많으면 → `demandDeviation > 0` → 시세 ↓ (크레딧 달러가 비싸짐)
- 매도가 매수보다 많으면 → `demandDeviation < 0` → 시세 ↑ (크레딧 달러가 싸짐)

없으면 0 (영향 없음).

---

## Factor 2: 공급 인플레이션 (Supply Inflation)

**전체 유저 크레딧 잔고 합 vs 유저당 기준치**

| 변수 | 설명 |
|------|------|
| `circulating` | 모든 유저의 크레딧 잔고 합 |
| `users` | 총 유저 수 |
| `baselineSupply` | `max(users × 100, 1000)` — 유저당 100cr이 "정상" |
| `supplyRatio` | `max(1, circulating / baselineSupply)` |
| `supplyInflation` | `log₂(supplyRatio)` |
| `supplyDeviation` | `min(supplyInflation × 0.15, 0.50)` → **0% ~ +50%** |

**효과:**
- 유저당 평균 100cr → `supplyRatio = 1` → deviation = 0%
- 유저당 평균 200cr → `supplyRatio = 2` → log₂ = 1 → +15%
- 유저당 평균 400cr → `supplyRatio = 4` → log₂ = 2 → +30%
- 유저당 평균 800cr → `supplyRatio = 8` → log₂ = 3 → +45%
- 그 이상 → **+50% 캡**

**왜 필요한가:**
유저가 많아서 업보트가 9000개씩 박히면 크레딧이 대량으로 풀린다.
그런데 시세가 안 변하면 에이전트가 25크레딧으로 고정돼서 말도 안 됨.
공급 인플레이션은 **전체 유통량**을 보고 시세를 올려서 에이전트 가격이 따라가게 한다.

---

## Factor 3: 발행 속도 (Issuance Velocity)

**24시간 내 새로 발행된 크레딧 vs 유저당 예상 기준치**

| 변수 | 설명 |
|------|------|
| `issued` | 24h 내 발행된 크레딧 (SIGNUP_BONUS, UPVOTE, SUBSCRIPTION_DRIP) |
| `issuanceBaseline` | `max(users × 5, 50)` — 유저당 하루 5cr이 "정상" |
| `issuanceRatio` | `max(1, issued / issuanceBaseline)` |
| `issuanceDeviation` | `min(log₂(issuanceRatio) × 0.10, 0.20)` → **0% ~ +20%** |

**효과:**
- 하루 발행량이 정상 → deviation = 0%
- 2× 정상 → +10%
- 4× 정상 → +20% (캡)

**왜 필요한가:**
공급 인플레이션(Factor 2)이 잔고 총합을 보는 **거시적** 지표라면,
발행 속도는 **지금 당장** 크레딧이 마구 풀리고 있는지 감지하는 **단기** 지표.

---

## 시나리오 예시

### 시나리오 A: 초기 서비스 (유저 50명, 조용한 날)

| Factor | 값 | 시세 영향 |
|--------|-----|-----------|
| 수요: 볼륨 0 | 0 | ±0% |
| 공급: 5,000cr / baseline 5,000 | ratio 1.0 | +0% |
| 발행: 250cr / baseline 250 | ratio 1.0 | +0% |
| **최종 시세** | **10.00 cr/$1** | 기본 시세 |

에이전트 $2.50 → **25 cr**

### 시나리오 B: 핫한 날 (유저 100명, 인기 글에 업보트 9,000개)

| Factor | 값 | 시세 영향 |
|--------|-----|-----------|
| 수요: 매수 500, 매도 100 | buyPressure=0.67 | −13.3% |
| 공급: 19,000cr / baseline 10,000 | ratio=1.9, log₂=0.93 | +14.0% |
| 발행: 9,000cr / baseline 500 | ratio=18, log₂=4.17 | +20.0% (캡) |
| **최종 시세** | **10 × (1 − 0.133 + 0.14 + 0.20) = 12.07 cr/$1** | |

에이전트 $2.50 → **30 cr** (기존 25 대비 +20%)

### 시나리오 C: 대규모 서비스 (유저 1,000명, 일일 업보트 50,000개)

| Factor | 값 | 시세 영향 |
|--------|-----|-----------|
| 수요: 매수 10K, 매도 3K | buyPressure=0.54 | −10.8% |
| 공급: 500,000cr / baseline 100,000 | ratio=5, log₂=2.32 | +34.8% |
| 발행: 50,000cr / baseline 5,000 | ratio=10, log₂=3.32 | +20.0% (캡) |
| **최종 시세** | **10 × (1 − 0.108 + 0.348 + 0.20) = 14.40 cr/$1** | |

에이전트 $2.50 → **36 cr** (기존 25 대비 +44%)

### 시나리오 D: 극단적 인플레이션 (유저 1,000명, 유저당 평균 800cr)

| Factor | 값 | 시세 영향 |
|--------|-----|-----------|
| 수요: 볼륨 0 | 0 | ±0% |
| 공급: 800,000cr / baseline 100,000 | ratio=8, log₂=3 | +45.0% |
| 발행: 극단적 | — | +20.0% (캡) |
| **최종 시세** | **10 × (1 + 0.45 + 0.20) = 16.50 cr/$1** | |

에이전트 $2.50 → **41 cr** (기존 25 대비 +64%)

---

## 에이전트 가격 공식

```
creditCost = Math.round(dollarPrice × exchangeRate)
```

시세가 올라가면 에이전트의 크레딧 가격도 자동으로 올라감.

---

## 구독 가격 공식

```
subscriptionPriceUsd = (monthlyCredits / exchangeRate) × 1.25
```

- 구독은 시세 기반 가격에 **25% 편의 프리미엄** 부과
- 구독은 편리하지만 크레딧 단가가 직접 환전보다 비쌈
- 직접 환전이 경쟁력을 유지하도록 설계

---

## 설정 상수

| 상수 | 값 | 설명 |
|------|-----|------|
| `baseRate` | 10 | 기본 시세 (cr/$1) |
| `feeRate` | 0.05 (5%) | 환전 수수료 |
| `maxRateDeviation` | 0.20 (±20%) | 수요 압력 최대 편차 |
| `maxSupplyDeviation` | 0.50 (+50%) | 공급 인플레이션 최대 |
| `maxIssuanceDeviation` | 0.20 (+20%) | 발행 속도 최대 |
| `supplyBaselinePerUser` | 100 cr | 유저당 정상 잔고 |
| `dailyIssuancePerUser` | 5 cr | 유저당 일일 정상 발행량 |
| `absoluteMinRate` | 5 | 절대 최저 시세 |
| `absoluteMaxRate` | 30 | 절대 최고 시세 |
| `SUBSCRIPTION_PREMIUM` | 0.25 (25%) | 구독 편의 프리미엄 |

---

## 요약

> 시세 = 기본시세 × (1 − 수요압력 + 공급인플레 + 발행속도)
>
> 크레딧이 많이 풀리면 시세가 올라가고 → 에이전트가 더 비싸지고 → 경제 균형 유지
