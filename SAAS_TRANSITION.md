# 🎮 Ogenti SaaS 전환 가이드

> **오픈소스에서 유료 SaaS 플랫폼으로** — AI-to-AI 커뮤니케이션 트레이닝, 이제 클릭 몇 번이면 끝.

---

## 📌 뭐가 달라졌나?

### Before (오픈소스)
- GitHub 레포 공개, 누구나 clone해서 사용
- 직접 환경 세팅 + GPU 확보 + 코드 수정 필요
- 서포트? 이슈 탭에 올리고 기다리세요~

### After (SaaS 플랫폼)
- **ogenti.com/platform** 에서 회원가입하고 바로 시작
- 크레딧 충전 → 모델 고르고 → 데이터셋 선택 → 트레이닝 런치 🚀
- 대시보드에서 실시간 진행률 확인
- API 키 발급해서 외부 연동까지

---

## 💰 크레딧 패키지 (상세 가격)

크레딧으로 모든 게 돌아감. 충전하고 쓰는 구조.

| 패키지 | 크레딧 | 가격 | 크레딧당 단가 |
|--------|--------|------|--------------|
| **Starter** | 1,000 | **$5** | $0.005 |
| **Builder** | 5,000 | **$20** | $0.004 |
| **Pro** | 20,000 | **$60** | $0.003 |
| **Enterprise** | 100,000 | **$250** | $0.0025 |

> 💡 **많이 살수록 싸다.** Enterprise는 Starter 대비 크레딧당 50% 할인.

---

## 🤖 모델별 트레이닝 비용

에피소드(episode) 하나 돌릴 때마다 크레딧 차감.

| 모델 | 에피소드당 크레딧 | VRAM | 속도 | 한줄평 |
|------|-------------------|------|------|--------|
| **Qwen2.5-3B** | 1 cr | 8GB | ⚡ Fast | 가볍고 빠름. 입문용 최고 |
| **LLaMA-3.2-3B** | 1 cr | 8GB | ⚡ Fast | Meta의 경량 모델. 실험 최적 |
| **Qwen2.5-7B** | 3 cr | 16GB | 🔄 Medium | 밸런스 갑. 성능↑ 속도 적당 |
| **Mistral-7B** | 3 cr | 16GB | 🔄 Medium | 유럽발 강자. 범용성 좋음 |
| **LLaMA-3.2-8B** | 4 cr | 20GB | 🔄 Medium | 중급 퍼포머. 확실한 결과 |
| **Qwen2.5-14B** | 8 cr | 32GB | 🐢 Slow | 풀파워. 최고 품질 원하면 이것 |
| **Custom (사용자)** | 2 cr | Varies | Varies | 내 모델 올려서 트레이닝 |

---

## 🏷️ 티어 시스템

가입하면 **Free 티어** 자동 적용. 크레딧 충전하면 티어 업.

| 티어 | 월 크레딧 | 최대 에피소드/월 | 사용 가능 모델 | 진입 조건 |
|------|-----------|-----------------|---------------|-----------|
| **Free** | 100 | 500 | Qwen2.5-3B만 | 회원가입하면 자동 |
| **Starter** | 1,000 | 5,000 | Qwen2.5-3B, LLaMA-3.2-3B | $5 이상 충전 |
| **Pro** | 5,000 | 30,000 | 전체 모델 | $60 이상 충전 |
| **Enterprise** | 50,000 | 100,000 | 전체 모델 + 우선 큐 | $250 이상 충전 |

> 🎁 **Free 티어**: 가입만 하면 매달 100 크레딧 + Qwen2.5-3B로 최대 500 에피소드. 무료로 맛보기 가능!

---

## 📊 비용 시뮬레이션

실제로 얼마 드는지 계산해봄:

### 시나리오 1: 가볍게 시작
- **모델**: Qwen2.5-3B (1 cr/ep)
- **에피소드**: 100회
- **필요 크레딧**: 100 cr
- **💸 비용**: **무료** (Free 티어에 포함!)

### 시나리오 2: 본격 트레이닝
- **모델**: Qwen2.5-7B (3 cr/ep)
- **에피소드**: 1,000회
- **필요 크레딧**: 3,000 cr
- **💸 비용**: **$20** (Builder 패키지, 2,000 cr 남음)

### 시나리오 3: 풀 스케일
- **모델**: Qwen2.5-14B (8 cr/ep)
- **에피소드**: 10,000회
- **필요 크레딧**: 80,000 cr
- **💸 비용**: **$250** (Enterprise 패키지, 20,000 cr 남음)

### 시나리오 4: 가성비 최적화
- **모델**: Mistral-7B (3 cr/ep)
- **에피소드**: 5,000회
- **필요 크레딧**: 15,000 cr
- **💸 비용**: **$60** (Pro 패키지, 5,000 cr 남음)

---

## 🔧 플랫폼 기능 상세

### 1. 인증 시스템
- 이메일 회원가입 → 6자리 인증코드 발송 (Resend API)
- JWT 기반 로그인 (토큰 7일 유효)
- 인증 완료 시 API 키 자동 발급

### 2. 크레딧 & 결제
- Stripe 연동 결제
- 실시간 잔액 확인
- 트랜잭션 히스토리 전체 조회
- 결제 전 비용 예측 (estimate) API

### 3. API 키 관리
- 계정당 최대 5개 키 발급
- 키 이름 지정 가능
- 개별 키 비활성화(revoke)
- 키 목록 조회 + 생성일/상태 확인

### 4. 트레이닝 런처
- 모델 선택 → 데이터셋 선택 → 에피소드 수 입력 → 런치
- 실시간 진행률 추적 (queued → running → completed/failed)
- 각 트레이닝 잡 상세 정보 조회
- 트레이닝 히스토리 전체 관리

### 5. 데이터셋
| 데이터셋 | 태스크 수 | 카테고리 | 설명 |
|----------|-----------|----------|------|
| Ogenti Default | 110 | 12 | 기본 AI-to-AI 통신 태스크 |
| Ogenti Extended | 500 | 12 | 확장판. 더 다양한 시나리오 |
| Alpaca Converted | 10,000 | 8 | 대규모 범용 데이터셋 |
| Custom Upload | JSONL | 사용자 정의 | 내 데이터로 트레이닝 |

---

## 🖥️ 프론트엔드 (레트로 16-bit 스타일)

8개 페이지, 전부 레트로 게임 감성으로 디자인:

| 페이지 | 경로 | 기능 |
|--------|------|------|
| Login | `/platform/login.html` | 로그인 |
| Sign Up | `/platform/signup.html` | 회원가입 |
| Verify | `/platform/verify.html` | 이메일 인증 |
| Account | `/platform/account.html` | 내 계정 + 잔액 |
| API Keys | `/platform/api_keys.html` | 키 관리 |
| Billing | `/platform/billing.html` | 충전 + 결제 |
| Usage | `/platform/usage.html` | 사용량 추적 |
| Training | `/platform/training.html` | 트레이닝 런치 |

---

## 🔌 API 엔드포인트 총정리

### Auth
```
POST /api/auth/signup      → 회원가입
POST /api/auth/verify       → 이메일 인증
POST /api/auth/login        → 로그인 (JWT 반환)
POST /api/auth/resend-code  → 인증코드 재발송
GET  /api/auth/me           → 내 정보 조회
```

### Billing
```
GET  /api/billing/packages     → 크레딧 패키지 목록
GET  /api/billing/models       → 모델 + 비용 목록
GET  /api/billing/tiers        → 티어 정보
POST /api/billing/estimate     → 비용 예측
POST /api/billing/purchase     → 크레딧 구매
GET  /api/billing/balance      → 잔액 조회
GET  /api/billing/transactions → 거래 내역
```

### API Keys
```
GET  /api/keys/list    → 내 키 목록
POST /api/keys/create  → 새 키 발급
POST /api/keys/revoke  → 키 비활성화
```

### Training
```
GET  /api/training/datasets   → 데이터셋 목록
POST /api/training/launch     → 트레이닝 시작
GET  /api/training/jobs       → 내 잡 목록
GET  /api/training/job/{id}   → 잡 상세 정보
```

---

## 🚀 사용 플로우 (처음부터 끝까지)

```
1. ogenti.com → "GET STARTED" 클릭
2. 이메일 + 비밀번호 입력 → 가입
3. 이메일로 온 6자리 코드 입력 → 인증 완료
4. 자동으로 Free 티어 (100 크레딧) 적용
5. Billing 페이지에서 크레딧 충전 (선택)
6. Training 페이지 이동
7. 모델 선택 (e.g. Qwen2.5-7B)
8. 데이터셋 선택 (e.g. Ogenti Extended)
9. 에피소드 수 입력 → 비용 확인
10. "Launch Training" 클릭 → 트레이닝 시작!
11. 실시간 진행률 확인
12. 완료 → 결과 다운로드
```

---

## 🛠️ 기술 스택

| 구분 | 기술 |
|------|------|
| Backend | Python 3.13 + FastAPI + Uvicorn |
| Database | SQLAlchemy + SQLite |
| Auth | JWT (python-jose) + bcrypt 4.x |
| Email | Resend API |
| Payment | Stripe (test mode) |
| Frontend | Vanilla HTML/CSS/JS (레트로 16-bit) |
| Landing | Vercel (ogenti.com) |
| Deploy | Railway (API 서버) |

---

## 📝 변경 이력

| 날짜 | 변경 내용 | 커밋 |
|------|-----------|------|
| 2025-01 | SaaS 플랫폼 백엔드 + 프론트엔드 구축 | `ea18809` |
| 2025-01 | 랜딩페이지 GitHub → Platform 링크 전환 | `cd15af2` |

---

## ⚠️ 남은 할 일

- [ ] GitHub 레포 Private 전환 (Settings → Danger Zone)
- [ ] Stripe Live 키 연동 (test → production)
- [ ] Resend API 키 교체 (test → production)
- [ ] Railway 배포 환경변수 설정
- [ ] 커스텀 도메인 SSL 설정
- [ ] 실제 GPU 클러스터 연동 (트레이닝 잡 실행)

---

> **Ogenti** — AI가 AI를 가르치는 세상. 이제 시작이야. 🎮
