# Dataset Discord Bot (GPT-4o Mixed Strategy)

## 개요
- **Debater A**: GPT-4o-mini (빠른 토론자)
- **Debater B**: GPT-4o-mini (빠른 토론자)
- **Mediator**: GPT-4o (강력한 중재자)
- **Judge**: GPT-4o (정확한 품질 평가)

Discord 스레드에서 메시지를 주기적으로 edit 하면서 스트리밍처럼 토론이 흘러가고,
Judge가 PASS한 샘플만 `datasets/dataset.jsonl`에 저장됩니다.

코드 위치:
- `backend/src/dataset_bot/*`

실행 스크립트:
- `npm run dataset:bot`

## 필수 환경변수
`.env`에 아래 값을 추가하세요.

### 환경변수 값 얻는 방법
#### Discord
1) **DISCORD_BOT_TOKEN**
   - Discord Developer Portal: https://discord.com/developers/applications
   - `New Application` → `Bot` → `Add Bot`
   - `Reset Token` → 복사해서 `.env`에 붙여넣기

2) **DISCORD_CLIENT_ID**
   - 같은 앱의 `General Information` → `Application ID` 복사

3) **DISCORD_GUILD_ID** (권장)
   - Discord에서 개발자 모드 활성화(Settings → Advanced → Developer Mode)
   - 서버 우클릭 → `Copy Server ID`

#### OpenAI
1) **OPENAI_API_KEY**
   - OpenAI Platform: https://platform.openai.com/
   - 로그인 → `API keys` → `Create new secret key` → 복사

#### 선택 항목
- `DISCORD_CHANNEL_ID`: 개발자 모드 → 채널 우클릭 → `Copy Channel ID`
- `OPENAI_BASE_URL`: 기본값 `https://api.openai.com` (변경 필요 없음)
- `OPENAI_DEBATER_A_MODEL`: 기본값 `gpt-4o-mini` (빠른 토론자 A)
- `OPENAI_DEBATER_B_MODEL`: 기본값 `gpt-4o-mini` (빠른 토론자 B)
- `OPENAI_MEDIATOR_MODEL`: 기본값 `gpt-4o` (강력한 중재자)
- `OPENAI_JUDGE_MODEL`: 기본값 `gpt-4o` (정확한 심판)
- `DATASET_OUT_DIR`: 기본값 `datasets` (상대 경로)
- `DATASET_MAX_TURNS`: 기본값 12 (토론 최대 턴 수)

#### .env 예시
```env
DISCORD_BOT_TOKEN=MTIzNDU2Nzg5MA.xxxxx.xxxxx
DISCORD_CLIENT_ID=1234567890
OPENAI_API_KEY=sk-proj-xxxxxxxxxxxxxx
DISCORD_GUILD_ID=9876543210
DISCORD_CHANNEL_ID=123456789012345678
OPENAI_BASE_URL=https://api.openai.com
OPENAI_DEBATER_A_MODEL=gpt-4o-mini
OPENAI_DEBATER_B_MODEL=gpt-4o-mini
OPENAI_MEDIATOR_MODEL=gpt-4o
OPENAI_JUDGE_MODEL=gpt-4o
DATASET_OUT_DIR=datasets
DATASET_MAX_TURNS=12
```

## 사용법
1) 백엔드 디렉토리에서 봇 실행
- `npm run dataset:bot`

2) Discord에서 `/gen` 실행
- `domain`: `computer_ops` | `web_ops` | `ethics`
- `difficulty`: `easy` | `medium` | `hard`
- `count`: 생성 시도 개수(기본 1)

3) 출력 파일
- 합격: `backend/datasets/dataset.jsonl`
- 탈락/에러: `backend/datasets/rejected.jsonl`
- 중복 방지 인덱스: `backend/datasets/index.json`

## 설계 메모
- **혼합 전략**: 두 Debater는 gpt-4o-mini (빠르고 저렴), Mediator와 Judge는 gpt-4o (강력하고 정확)로 비용 대비 품질 최적화
- Mediator가 3턴마다 개입하여 토론 방향 조율
- GPT-4o Judge가 최종 품질 평가 수행
- Webhook은 수신이 불가해서, 토론/검수 오케스트레이션은 Discord Bot이 담당합니다.
- 메시지 스트리밍은 700ms 주기로 message edit을 수행합니다.
- Judge JSON이 파싱 실패하거나 score<0.85 이면 저장하지 않습니다.
