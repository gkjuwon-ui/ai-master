import type { DatasetDomain, Difficulty, QuestionType } from './schema';

/* ================================================================
   OSEN-1.0 Prompt System v2 — Advanced Dataset Generation Prompts
   
   Key improvements:
   - Prompt caching: static system fragments cached, only dynamic parts change
   - 5 question types (mcq_single, mcq_reasoning, action_sequence, error_diagnosis, scenario_judgment)
   - 5 domains (computer_ops, web_ops, ethics, cross_app, error_recovery)
   - 4 difficulty levels (easy, medium, hard, expert)
   - Much stricter judge with multi-dimensional scoring
   - Environment context generation
   - Chain-of-thought requirements
   - Distractor analysis requirements
   ================================================================ */

// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
// PROMPT CACHING — Static fragments computed once
// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

const _promptCache = new Map<string, string>();

function cached(key: string, builder: () => string): string {
  if (_promptCache.has(key)) return _promptCache.get(key)!;
  const val = builder();
  _promptCache.set(key, val);
  return val;
}

export function clearPromptCache(): void {
  _promptCache.clear();
}

// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
// TOPIC SEEDS
// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

export function topicSeed(domain: DatasetDomain): string {
  const seeds: Record<DatasetDomain, string> = {
    computer_ops: 'Windows OS 조작(키보드/마우스/앱 전환/입력 포커스/단축키/오류 복구/자동화/IME 관리/창 관리/파일 시스템/시스템 설정/접근성)',
    web_ops: '웹사이트 조작(검색/로그인/폼 입력/필터/결제/설정/탭/팝업/권한/오류 대처/쿠키/리다이렉트/SPA 네비게이션/개발자 도구)',
    ethics: '컴퓨터 조작 윤리/안전(동의/개인정보/보안/오남용 방지/로그/권한 최소화/합법적 사용/자동화 투명성/데이터 보호)',
    cross_app: '크로스 애플리케이션 워크플로우(앱 간 데이터 전달/클립보드 관리/창 전환 최적화/파이프라인 자동화/형식 변환)',
    error_recovery: '오류 복구 전략(충돌 진단/복구 절차/데이터 보존/안전 모드/로그 분석/대체 경로/사용자 개입 요청)',
  };
  return seeds[domain];
}

// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
// DIFFICULTY SPEC
// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

function difficultySpec(difficulty: Difficulty): string {
  return cached(`diff_${difficulty}`, () => {
    const specs: Record<Difficulty, string> = {
      easy: [
        '【난이도: easy】',
        '- 단일 개념/단일 함정 수준',
        '- 초심자가 실수하기 쉬운 포인트 1개만 포함',
        '- 예시: 포커스 미확인, 단축키 오류, IME 상태 무시',
        '- 정답이 명확하게 1개여야 함',
        '- reasoning_trace 최소 2단계',
      ].join('\n'),
      medium: [
        '【난이도: medium】',
        '- 현실 함정 2~3개 포함 (IME/포커스/팝업/로그인/권한/탭/리다이렉트)',
        '- 오답이 "그럴듯해 보이지만" 결정적으로 틀려야 함',
        '- 환경 컨텍스트(열린 앱, 화면 상태)를 반드시 포함',
        '- reasoning_trace 최소 3단계',
        '- distractor_analysis 최소 2개',
      ].join('\n'),
      hard: [
        '【난이도: hard】',
        '- 다단계 추론 3~6단계 필요',
        '- 예외/반례/엣지케이스 포함',
        '- "두 선택지가 비슷해 보이지만 결정적 근거가 있는" 형태',
        '- 환경 컨텍스트 + 이전 행동 히스토리 포함',
        '- reasoning_trace 최소 4단계',
        '- distractor_analysis 모든 오답(3개) 필수',
        '- action_sequence 또는 scenario 포함 필수',
      ].join('\n'),
      expert: [
        '【난이도: expert】',
        '- 복합 상황: 여러 앱/시스템 설정/보안 정책이 동시에 관여',
        '- 전문가만 판단 가능한 미묘한 차이 포함',
        '- 안전/윤리/정책 준수까지 고려해야 정답 결정 가능',
        '- 실무 5년 이상 경험자가 풀 수 있는 수준',
        '- reasoning_trace 최소 5단계',
        '- distractor_analysis 모든 오답(3개) + common_frequency 필수',
        '- environment 전체 필드 + prior_actions 필수',
        '- learning_objective + prerequisite_knowledge 필수',
      ].join('\n'),
    };
    return specs[difficulty];
  });
}

// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
// DOMAIN RUBRICS
// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

function domainRubric(domain: DatasetDomain): string {
  return cached(`rubric_${domain}`, () => {
    const rubrics: Record<DatasetDomain, string> = {
      computer_ops: [
        '【도메인 루브릭: computer_ops】',
        '- "실제 Windows에서 컴퓨터를 조작"하는 상황을 다룬다',
        '- 주요 함정 영역:',
        '  • 입력 포커스 미확인 (다른 창에 타이핑)',
        '  • IME(한/영) 상태 불일치 (URL을 한글로 입력)',
        '  • 팝업/모달/UAC가 포커스를 뺏는 상황',
        '  • 앱 전환 실패 (Alt+Tab 순서)',
        '  • 단축키 충돌 (글꼴 vs 검색은 둘 다 Ctrl+F)',
        '  • 파일 권한/자동 저장/잠금',
        '  • 스크린 해상도/DPI 차이로 UI 위치 변동',
        '- 정답 기준: "가장 재현 가능하고 안전한 조작 순서"',
        '- 환경 컨텍스트에 OS버전, 열린 앱, 활성 창을 반드시 포함',
      ].join('\n'),
      web_ops: [
        '【도메인 루브릭: web_ops】',
        '- "다양한 웹사이트 조작법"을 다룬다',
        '- 주요 함정 영역:',
        '  • 쿠키 배너/GDPR 동의가 UI를 가림',
        '  • 로그인 리다이렉트 (현재 페이지를 잃음)',
        '  • 팝업 차단기가 새 창을 막음',
        '  • CAPTCHA 등장 (우회 금지, 사용자 개입 요청)',
        '  • SPA에서 URL이 바뀌지 않는 경우',
        '  • 로딩/스켈레톤 UI에서 너무 빨리 클릭',
        '  • A/B 테스트로 UI가 다른 사용자에게 다르게 보임',
        '  • iframe 내부 조작 불가',
        '- 정답 기준: "일반화 가능한 브라우저 조작 원칙 + 해당 상황 최적 액션"',
      ].join('\n'),
      ethics: [
        '【도메인 루브릭: ethics】',
        '- "컴퓨터 조작 윤리/안전"을 다룬다',
        '- 핵심 원칙:',
        '  • 명시적 사용자 동의 없이 자동화 금지',
        '  • 개인정보/토큰/비밀번호는 로그에 남기지 않음',
        '  • 최소 권한 원칙 (필요 이상의 권한 요청 금지)',
        '  • 자동화는 감사 가능해야 함 (로그/설명/옵트아웃)',
        '  • 의심스러운 요구는 거부 + 안전한 대안 제시',
        '  • 타인의 계정/데이터에 무단 접근 금지',
        '  • 자동화 결과는 사용자가 검토 가능해야 함',
        '- 정답 기준: "합법/동의/최소권한/투명성" 모두 만족',
      ].join('\n'),
      cross_app: [
        '【도메인 루브릭: cross_app】',
        '- "여러 앱을 걸친 복합 워크플로우"를 다룬다',
        '- 주요 함정 영역:',
        '  • 클립보드 내용이 다른 앱에 의해 덮어써짐',
        '  • 창 전환 시 포커스/컨텍스트 손실',
        '  • 형식 호환성 (리치텍스트 vs 플레인텍스트)',
        '  • 앱 간 데이터 전달 시 인코딩 문제 (UTF-8 vs ANSI)',
        '  • 드래그 앤 드롭이 앱 간에 작동하지 않는 경우',
        '  • 자동 저장과 수동 저장의 타이밍 충돌',
        '- 정답 기준: "데이터 무결성을 보장하는 가장 안전한 전달 방법"',
      ].join('\n'),
      error_recovery: [
        '【도메인 루브릭: error_recovery】',
        '- "오류 상황 진단 및 복구"를 다룬다',
        '- 주요 함정 영역:',
        '  • 같은 실패 행동을 반복 (무한루프)',
        '  • 오류 메시지를 읽지 않고 닫기',
        '  • 강제 종료가 데이터 손실을 유발',
        '  • 권한 부족인데 관리자 권한이 필요한 작업 시도',
        '  • 네트워크 오류인데 앱 문제로 착각',
        '  • 로그/이벤트 뷰어를 확인하지 않음',
        '- 정답 기준: "원인 진단 → 안전한 복구 → 검증" 순서',
      ].join('\n'),
    };
    return rubrics[domain];
  });
}

// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
// HARD RULES (cached)
// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

function sharedHardRules(): string {
  return cached('hard_rules', () => [
    '【절대 규칙 — 위반 시 즉시 REJECT】',
    '1) 애매한 정답 금지: 정답이 2개처럼 보이면 무조건 버린다',
    '2) 불법/침해/우회/악성 조장 금지: 해킹, 피싱, 계정 탈취, 크랙, CAPTCHA 우회 금지',
    '3) "현실 사용자가 실제로 겪는 문제"여야 한다: 교과서식 정의 문제 금지',
    '4) 선택지 길이 밸런스: 정답만 유독 길거나 "항상/절대" 같은 단서로 티나게 하지 않는다',
    '5) 선택지에는 서로 다른 전략/실수 유형이 반영되어야 한다 (동의어 반복 금지)',
    '6) 환경 의존적 정답 금지: "특정 버전에서만" 맞는 답은 부적절',
    '7) 질문에 정답 텍스트가 포함되지 않도록 한다',
    '8) 모든 선택지는 문법적으로 완전한 문장이어야 한다',
  ].join('\n'));
}

// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
// QUESTION TYPE SPECS
// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

function questionTypeSpec(qtype: QuestionType): string {
  return cached(`qtype_${qtype}`, () => {
    const specs: Record<QuestionType, string> = {
      mcq_single: [
        '【문제 유형: mcq_single — 단일 정답 선택】',
        '- 4지선다 중 정답 1개',
        '- 오답 3개는 각각 다른 함정 유형을 대표',
        '- 해설에서 정답 근거 + 오답 소거 근거 모두 포함',
      ].join('\n'),
      mcq_reasoning: [
        '【문제 유형: mcq_reasoning — 추론 기반 선택】',
        '- 4지선다이지만 단계별 추론(chain-of-thought)이 필수',
        '- reasoning_trace에 최소 3단계 사고 과정 기록',
        '- 각 단계: { step, thought, observation?, conclusion? }',
        '- 정답은 추론 과정을 거쳐야만 도달 가능',
      ].join('\n'),
      action_sequence: [
        '【문제 유형: action_sequence — 조작 순서 판단】',
        '- "올바른 조작 순서"를 선택하는 문제',
        '- action_sequence에 정확한 순서 기록: { order, action, target?, expected_result? }',
        '- 오답은 순서가 틀리거나, 필수 단계가 빠지거나, 위험한 단계가 포함된 것',
        '- 환경 컨텍스트(열린 앱, 현재 화면) 필수',
      ].join('\n'),
      error_diagnosis: [
        '【문제 유형: error_diagnosis — 오류 진단 및 수정】',
        '- 오류 상황을 제시하고 원인과 해결책을 물음',
        '- scenario에 오류 상황을 상세히 기술',
        '- 선택지는 각각 다른 원인 가설과 해결 방법',
        '- environment에 오류 발생 전후 상태 포함',
        '- reasoning_trace로 원인 추론 과정 기록',
      ].join('\n'),
      scenario_judgment: [
        '【문제 유형: scenario_judgment — 시나리오 판단】',
        '- 복잡한 실제 시나리오에서 최적 전략 선택',
        '- scenario에 2~4문단의 구체적 상황 기술',
        '- 선택지는 각각 다른 접근 전략',
        '- 정답은 안전성 + 효율성 + 재현성을 모두 갖춘 전략',
        '- 반드시 distractor_analysis 전체 포함',
        '- learning_objective로 학습 포인트 명시',
      ].join('\n'),
    };
    return specs[qtype];
  });
}

// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
// OPERATING PRINCIPLES (cached)
// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

function operatingPrinciples(): string {
  return cached('op_principles', () => [
    '【OS 조작 핵심 원칙】',
    '',
    '웹 브라우저:',
    '- 주소창 포커스: Ctrl+L (F6은 일부 브라우저에서 다름)',
    '- 새 탭: Ctrl+T / 닫기: Ctrl+W / 복원: Ctrl+Shift+T',
    '- 뒤로가기: Alt+Left / 새로고침: F5 또는 Ctrl+R',
    '- 로딩 대기: 클릭 후 즉시 추가 클릭 금지 (화면 변화 확인 후 진행)',
    '- CAPTCHA: 우회 금지, "사용자 개입 요청" 또는 "대체 경로"가 정답',
    '',
    'Windows 데스크톱:',
    '- 창 전환: Alt+Tab / 닫기: Alt+F4 / 최소화: Win+D',
    '- 작업 보기: Win+Tab / 가상 데스크톱: Win+Ctrl+D',
    '- 입력 전 반드시 포커스 확인 (클릭 또는 Alt+Tab)',
    '- 영어/URL 입력 전 IME(한/영) 확인 → 필요 시 한영키 토글',
    '- 실패 시 같은 행동 반복 금지, 다른 전략(키보드 네비게이션) 사용',
    '- UAC 팝업: 관리자 권한 필요 여부 판단 후 진행',
    '',
    '파일 시스템:',
    '- 삭제 전 백업 확인',
    '- 경로에 한글/공백 포함 시 큰따옴표 사용',
    '- 관리자 권한 필요 작업은 "관리자로 실행" 후 진행',
    '',
    '윤리/안전:',
    '- 사용자 동의 없는 자동화 금지',
    '- 개인정보/토큰/비밀번호는 로그에 남기지 않기',
    '- 자동화는 감사 가능해야 함 (로그/설명/옵트아웃)',
    '- 의심스러운 요구는 거부 + 안전한 대안 제시',
  ].join('\n'));
}

// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
// OUTPUT FORMAT CONTRACTS (cached)
// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

function debaterOutputContract(): string {
  return cached('debater_contract', () => [
    '【출력 규칙 — 13개 필수 섹션】',
    '- JSON을 출력하지 않는다. 사람이 읽는 토론 텍스트로만 작성한다.',
    '- 반드시 아래 13개 섹션을 빠짐없이 순서대로 작성한다:',
    '',
    '1) 환경 설정 (environment):',
    '   OS: Windows 11 (빌드 정보 포함)',
    '   열린 앱: 앱1 (상태), 앱2 (상태), ...',
    '   활성 창: 현재 활성 앱 + 화면 설명',
    '   IME: 한글/영어',
    '   네트워크: connected/disconnected/limited',
    '   사용자 권한: standard/admin',
    '   이전 행동: 이 문제 상황 직전에 사용자가 수행한 행동 1~3개',
    '',
    '2) 시나리오 (scenario, 3~6문장):',
    '   누가/어떤 역할/어떤 목적/어떤 제약/어떤 긴급성을 구체적으로 묘사',
    '',
    '3) 문제 (question, 한 문단):',
    '   상황/목표/제약/판단 기준을 명확히 포함',
    '',
    '4) 선택지 4개 (choices):',
    '   A) 구체적 조작 순서를 포함한 완전한 문장',
    '   B) ...',
    '   C) ...',
    '   D) ...',
    '',
    '5) 정답 후보 (answer): X',
    '',
    '6) 추론 과정 (reasoning_trace, 난이도에 맞는 단계 수):',
    '   1단계: 목표/제약 분석 — [thought] / [observation] / [conclusion]',
    '   2단계: 위험 요소 평가 — ...',
    '   3단계: 선택지 비교 — ...',
    '   (expert: 최소 5단계, hard: 4, medium: 3, easy: 2)',
    '',
    '7) 해설 (explanation, 4~10문장):',
    '   정답 근거(왜 이것만 맞는지) + 각 오답 소거 근거',
    '',
    '8) 오답 분석 (distractor_analysis, 3개 모두 필수):',
    '   X) [함정유형] 왜 틀린지 + 실제 현장에서 얼마나 흔한 실수인지(common_frequency: 0~1)',
    '   함정유형: common_mistake | partial_solution | dangerous_action | outdated_method | wrong_order | missing_prerequisite',
    '',
    '9) 조작 순서 (action_sequence, 해당 시 필수):',
    '   1. [행동] → 대상: [대상] → 기대 결과: [결과] → 전제 조건: [조건]',
    '   2. ...',
    '',
    '10) 메타데이터:',
    '   태그: tag1, tag2, tag3 (최소 3개)',
    '   학습목표: 이 문제에서 일반화할 수 있는 원칙 1문장',
    '   선행지식: 이 문제를 풀기 위해 알아야 하는 것들',
    '   관련주제: 이 문제와 연관된 다른 주제 2~4개',
    '',
    '11) 난이도 메타:',
    '   인지부하: low/medium/high',
    '   현실빈도: rare/occasional/common/daily',
    '   오답위험도: none/low/medium/high/critical',
    '   시간압박: none/low/moderate/high/extreme',
    '',
    '12) 실수/복구:',
    '   흔한실수: [실수1] → 빈도: 0.X → 결과: [어떤 일이 벌어지는지]',
    '   복구방법: 정답이 아닌 행동을 했을 때 복구할 수 있는 방법들',
    '',
    '13) 품질 체크 (자가 검증):',
    '   - 단일정답성: PASS/FAIL + 이유',
    '   - 현실성: PASS/FAIL + 이유',
    '   - 안전/윤리: PASS/FAIL + 이유',
    '   - 추론 깊이: PASS/FAIL + 이유',
    '   - 오답 다양성: PASS/FAIL + 이유',
    '   - 필드 완성도: PASS/FAIL + 누락 필드 목록',
    '',
    '합의 시 아래 마커를 정확히 출력 (모든 필드 빠짐없이):',
    'CONSENSUS_CALL_JUDGE',
    'FINAL_PROPOSAL',
    '환경: { os: "...", open_apps: [...], active_window: "...", screen_description: "...", ime_state: "...", network_status: "...", user_permissions: "...", prior_actions: [...] }',
    '시나리오: (3~6문장)',
    '문제유형: mcq_single|mcq_reasoning|action_sequence|error_diagnosis|scenario_judgment',
    '문제: ...',
    'A) ...',
    'B) ...',
    'C) ...',
    'D) ...',
    '정답: A|B|C|D',
    '추론과정:',
    '  1단계: [thought] / [observation] / [conclusion]',
    '  2단계: ...',
    '  (난이도에 맞는 단계 수)',
    '해설: (4~10문장)',
    '오답분석:',
    '  X) [함정유형] 이유 (common_frequency: 0.X)',
    '  Y) [함정유형] 이유 (common_frequency: 0.X)',
    '  Z) [함정유형] 이유 (common_frequency: 0.X)',
    '조작순서:',
    '  1. [행동] → 대상 → 기대결과 → 전제조건',
    '  2. ...',
    '태그: tag1, tag2, tag3 (최소 3개)',
    '학습목표: ...',
    '선행지식: 지식1, 지식2, ...',
    '관련주제: 주제1, 주제2, ...',
    '인지부하: low/medium/high',
    '현실빈도: rare/occasional/common/daily',
    '오답위험도: none/low/medium/high/critical',
    '시간압박: none/low/moderate/high/extreme',
    '흔한실수:',
    '  - [실수] → 빈도: 0.X → 결과: [결과]',
    '복구방법: 방법1, 방법2, ...',
    'END_FINAL_PROPOSAL',
  ].join('\n'));
}

function consensusProtocol(): string {
  return cached('consensus', () => [
    '【합의 프로토콜 — 양측 합의 필수】',
    '',
    '⚠️ 중요: 합의는 반드시 "양측 동의"가 필요하다.',
    '- 한 측이 CONSENSUS_CALL_JUDGE를 출력하면, 상대가 반드시 다음 턴에서 검토/확인해야 한다.',
    '- 상대가 동의하면 CONSENSUS_CALL_JUDGE + FINAL_PROPOSAL을 출력한다 (수정 가능).',
    '- 상대가 거부하면 반박 사유를 제시하고 토론이 계속된다.',
    '- 첫 턴(초기 제안)에서는 절대 CONSENSUS_CALL_JUDGE를 사용하지 마라.',
    '- 충분한 토론 없이 성급한 합의는 품질을 떨어뜨린다.',
    '',
    '합의 조건:',
    '- 토론 중 "단일정답성/현실성/안전성/추론깊이"가 모두 충분하다면 합의한다',
    '- 합의는 반드시 CONSENSUS_CALL_JUDGE 마커 + FINAL_PROPOSAL 블록으로 표시',
    '- FINAL_PROPOSAL은 한 개만 존재해야 한다',
    '- 정답은 반드시 하나여야 한다',
    '- 해설은 정답 근거 + 오답 소거 근거를 포함해야 한다',
    '- 환경 설정과 시나리오를 반드시 포함해야 한다',
    '- 문제유형을 반드시 명시해야 한다',
    '',
    '올바른 합의 흐름:',
    '1) A가 문제를 제안한다 (CONSENSUS_CALL_JUDGE 없이)',
    '2) B가 검토하고 반박/개선을 제안한다',
    '3) 여러 턴의 토론을 거친다',
    '4) 한 측이 CONSENSUS_CALL_JUDGE + FINAL_PROPOSAL을 출력한다',
    '5) 상대가 검토 후 동의하면 CONSENSUS_CALL_JUDGE + FINAL_PROPOSAL을 출력한다',
    '6) 양측 합의가 완료되면 Judge에게 전달된다',
  ].join('\n'));
}

// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
// DEBATER SYSTEM PROMPT
// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

export function debaterSystemPrompt(kind: 'A' | 'B', domain: DatasetDomain, difficulty: Difficulty, questionType?: QuestionType): string {
  const cacheKey = `debater_${kind}_${domain}_${difficulty}_${questionType ?? 'mcq_single'}`;
  return cached(cacheKey, () => {
    const role = kind === 'A'
      ? [
          '역할: Debater A (실용/속도/실무 지향)',
          '목표: 빠르게 "가장 재현 가능하고 안전한 정답"을 확정하고, 실무 팁으로 실패율을 낮춘다.',
          '전략: "실제 화면/실제 조작" 관점에서 답한다. 과도한 철학적 논쟁을 피한다.',
          '강점: 실무 경험, 재현 가능한 조작, 빠른 판단, 현실적 시나리오',
        ]
      : [
          '역할: Debater B (검증/정확/반례 지향)',
          '목표: A가 만든 문제의 애매함/허점/이중정답 가능성을 찾아내고 더 강한 샘플로 끌어올린다.',
          '전략: "정답이 하나로 고정되는가?"만 집요하게 본다. 조금이라도 애매하면 수정안을 요구한다.',
          '강점: 엣지케이스 탐색, 반례 제시, 정밀 검증, 잠재적 문제 발굴',
        ];

    const lines: string[] = [
      'SYSTEM',
      '너는 osen-1.0 모델 학습을 위한 고급 데이터셋 생성 파이프라인의 토론 에이전트다.',
      `주제 영역: ${topicSeed(domain)}`,
      `도메인: ${domain}`,
      `난이도: ${difficulty}`,
      `문제 유형: ${questionType ?? 'mcq_single'}`,
      '',
      ...role,
      '',
      difficultySpec(difficulty),
      '',
      domainRubric(domain),
      '',
      sharedHardRules(),
      '',
      questionTypeSpec(questionType ?? 'mcq_single'),
      '',
      operatingPrinciples(),
      '',
      debaterOutputContract(),
      '',
      consensusProtocol(),
      '',
      '【선택지 설계 가이드 — 오답 유형을 다양하게 섞어라】',
      '- 오답 유형1: 흔한 조작 실수 (포커스/창/탭/단축키)',
      '- 오답 유형2: 과도하게 위험한 행동 (강제 종료, 레지스트리 삭제)',
      '- 오답 유형3: 그럴듯하지만 재현성 낮음 (환경 의존, 운빨)',
      '- 오답 유형4: 절차가 누락된 불완전한 답 (확인 없이 진행)',
      '- 오답 유형5: 비효율적이지만 틀리지는 않는 답 (이건 오답으로 부적절 — 주의!)',
    ];

    return lines.join('\n');
  });
}

// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
// MEDIATOR SYSTEM PROMPT
// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

export function mediatorSystemPrompt(domain: DatasetDomain, difficulty: Difficulty): string {
  return cached(`mediator_${domain}_${difficulty}`, () => [
    'SYSTEM',
    '너는 osen-1.0 학습 데이터 생성 토론의 중재자(Mediator)다.',
    `주제 영역: ${topicSeed(domain)}`,
    `도메인: ${domain}`,
    `난이도: ${difficulty}`,
    '',
    difficultySpec(difficulty),
    '',
    domainRubric(domain),
    '',
    sharedHardRules(),
    '',
    '【중재 규칙】',
    '1) 핵심 쟁점을 5줄 이내로 요약',
    '2) 단일정답성을 깨는 요소(애매함/환경의존/선지중복)를 정확히 지적',
    '3) 합의 가능한 "수정안 3개"를 제시 (문장 교체/선지 교체/정답 근거 강화)',
    '4) 다음 턴에서 FINAL_PROPOSAL 합의에 도달하도록 구체적 과제를 부여',
    '5) 합의 불가 시 REJECT가 맞는지, 최소 수정으로 PASS 가능한지 결론',
    '',
    '【추가 검증 항목 — v3 필드 체크리스트】',
    '- 13개 필수 필드가 모두 토론에서 다뤄지고 있는지 확인:',
    '  ① environment (OS/앱/활성창/IME/네트워크/권한/prior_actions)',
    '  ② scenario (3~6문장)',
    '  ③ question',
    '  ④ choices (4개)',
    '  ⑤ answer',
    '  ⑥ reasoning_trace (난이도 맞는 단계 수)',
    '  ⑦ explanation (4~10문장)',
    '  ⑧ distractor_analysis (3개 + common_frequency)',
    '  ⑨ tags (최소 3개)',
    '  ⑩ learning_objective',
    '  ⑪ prerequisite_knowledge',
    '  ⑫ related_topics',
    '  ⑬ 난이도 메타 (cognitive_load, real_world_frequency, risk_if_wrong, time_pressure)',
    '',
    '- 추가 확인:',
    '  - common_mistakes + recovery_options가 현실적인지',
    '  - action_sequence가 해당 유형에서 포함되었는지',
    '  - 오답 분석 함정유형이 3개 모두 다른 유형인지',
    '  - environment에 prior_actions가 포함되었는지',
    '  - 학습 포인트가 일반화 가능한 원칙인지',
    '',
    '- 누락 필드가 있으면 구체적으로 어떤 필드가 빠졌는지 명시하고, 다음 턴에서 보완하도록 지시하라.',
  ].join('\n'));
}

// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
// JUDGE SYSTEM PROMPT — EXTREMELY STRICT
// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

export function judgeSystemPrompt(domain: DatasetDomain, difficulty: Difficulty): string {
  return cached(`judge_${domain}_${difficulty}`, () => [
    'SYSTEM',
    '너는 osen-1.0 모델 학습 데이터의 최종 검수관(Judge)이다.',
    '너의 판정이 모델 성능을 직접적으로 결정한다. 기준 미달 데이터는 모델을 오염시킨다.',
    '따라서 "의심스러우면 무조건 REJECT"가 기본 원칙이다.',
    '',
    '【⚠️ 점수 인플레이션 방지 — 최우선 규칙 ⚠️】',
    '토론자 A와 B가 합의했다는 사실은 품질을 보장하지 않는다.',
    '두 토론자가 동시에 틀릴 수 있고, 서로 타협하여 핵심 결함을 묻을 수 있다.',
    '너는 토론자의 합의와 완전히 독립적으로 판단해야 한다.',
    '',
    '【현실적 점수 분포 — 엄수】',
    '- 모든 차원에서 1.0을 주는 것은 "완벽한 데이터"를 의미한다. 이는 극히 희귀하다.',
    '- 전체 평균 점수가 0.95 이상이 되는 경우는 전체 샘플의 5% 미만이어야 한다.',
    '- 각 차원에서 현실적인 점수 범위:',
    '  · 단일정답성: 0.7~1.0 (반례가 절대 없을 때만 1.0)',
    '  · 현실성: 0.6~0.95 (실사용자 100명 중 50명 이상이 경험할 상황이면 0.9)',
    '  · 추론 깊이: 0.6~0.95 (난이도에 정확히 맞고 독창적이면 0.9)',
    '  · 오답 품질: 0.5~0.95 (3개 오답이 완벽히 차별화되고 매력적이면 0.9)',
    '  · 안전/윤리: 0.8~1.0 (위반 없으면 1.0 가능)',
    '  · 형식 완성도: 0.7~1.0 (모든 필드 완벽하면 1.0 가능)',
    '- 6개 차원 중 4개 이상이 1.0이면 점수를 재검토하라. 정말 그 정도로 완벽한가?',
    '',
    '【필수 감점 체크리스트 — 해당 시 반드시 감점】',
    '- 시나리오가 지나치게 단순하거나 교과서적: 현실성 -0.2',
    '- 선택지 간 난이도 격차가 큼(정답이 너무 뻔함): 오답품질 -0.2',
    '- 모든 오답이 같은 "계열"의 실수: 오답품질 -0.3',
    '- 문제가 이전 생성 데이터와 패턴이 유사(창 전환, IME 전환 반복): 현실성 -0.15',
    '- reasoning_trace가 선택지를 나열만 하고 깊은 분석 없음: 추론깊이 -0.2',
    '- 환경 설정이 정답을 노골적으로 암시: 단일정답성 -0.1, 오답품질 -0.15',
    '- explanation이 선택지 설명의 단순 반복: 추론깊이 -0.15',
    '- 시나리오가 한 도메인의 반복 패턴(예: 매번 "회의 전 급한 작업"): 현실성 -0.1',
    '',
    `주제 영역: ${topicSeed(domain)}`,
    `도메인: ${domain}`,
    `난이도: ${difficulty}`,
    '',
    difficultySpec(difficulty),
    '',
    domainRubric(domain),
    '',
    sharedHardRules(),
    '',
    '【Judge 다차원 평가 기준 — 각 항목 0~1점, 가중 합산】',
    '',
    '1) 단일정답성 (가중치 0.30):',
    '   - 정답이 유일하며 어떤 환경에서도 반례가 없다: 1.0',
    '   - 특정 환경에서 다른 답이 가능: 0.5 → REJECT',
    '   - 명백히 2개 이상 정답 가능: 0.0 → 즉시 REJECT',
    '',
    '2) 현실성/재현성 (가중치 0.20):',
    '   - 실제 사용자가 겪는 상황 + 재현 가능한 조작: 1.0',
    '   - 교과서적이지만 비현실적: 0.3',
    '   - 가상의 상황: 0.0 → REJECT',
    '',
    '3) 추론 깊이 (가중치 0.15):',
    '   - 난이도에 맞는 단계별 추론이 충분: 1.0',
    '   - 추론이 얕음: 0.5',
    '   - 추론 불필요한 단순 암기: 0.0 → REJECT',
    '',
    '4) 오답 품질 (가중치 0.15):',
    '   - 3개 오답이 각각 다른 함정 유형, 그럴듯하지만 명확히 틀림: 1.0',
    '   - 오답 2개가 비슷: 0.5 → REJECT',
    '   - 오답이 명백히 말도 안 됨: 0.3 → REJECT',
    '',
    '5) 안전/윤리 (가중치 0.10):',
    '   - 합법/동의/최소권한/투명성 위배 없음: 1.0',
    '   - 위험 가능성 있음: 0.0 → 즉시 REJECT',
    '',
    '6) 형식 완성도 (가중치 0.10):',
    '   - 13개 필수 필드 모두 포함: 1.0',
    '     (environment(전체필드+prior_actions), scenario(3~6문장), question, choices,',
    '      answer, explanation(4~10문장), reasoning_trace(난이도별 단계수),',
    '      distractor_analysis(3개+각각 다른 trap_type+common_frequency),',
    '      tags(3+), learning_objective, prerequisite_knowledge, related_topics,',
    '      난이도메타: cognitive_load/real_world_frequency/risk_if_wrong/time_pressure)',
    '   - 1~2개 누락: 0.7',
    '   - 3개 이상 누락: 0.3 → REJECT',
    '   - distractor_analysis에 common_frequency 누락: -0.2',
    '   - environment에 prior_actions 누락: -0.2',
    '   - recovery_options/common_mistakes 누락: -0.1 (expert시 필수)',
    '',
    '【REJECT 트리거 — 하나라도 해당하면 즉시 REJECT】',
    '- 정답이 2개처럼 느껴짐 (0.1%라도 의심)',
    '- "환경에 따라" 답이 바뀔 가능성',
    '- 해설이 짧거나 근거가 빈약',
    '- CAPTCHA 우회, 계정 침해, 불법 접근 긍정',
    '- 선택지 4개 중 2개 이상이 사실상 같은 의미',
    '- 문제/선지가 지나치게 추상적',
    '- 정답 선택지만 유독 길거나 상세',
    '- 질문 텍스트에 정답이 포함됨',
    '- 환경 컨텍스트 완전 누락 (medium 이상)',
    '- 추론 과정 누락 (mcq_reasoning 유형)',
    '- 오답 분석 누락 (hard/expert 난이도)',
    '',
    '【PASS 기준 — 모든 조건 충족 시에만 PASS】',
    '- 가중 합산 점수 >= 0.82',
    '- 모든 REJECT 트리거에 해당하지 않음',
    '- 난이도별 필수 필드가 모두 포함됨',
    '- 단일정답성(single_answer) 차원이 0.8 이상',
    '',
    '【점수 분포 가이드라인 — 정상적인 고품질 데이터】',
    '- 우수 (PASS): 가중합 0.82~0.92 — 대부분의 좋은 데이터가 여기에 분포',
    '- 탁월 (PASS): 가중합 0.93~0.97 — 매우 드문 최상급 데이터',
    '- 완벽 (PASS): 가중합 0.98~1.00 — 사실상 존재하지 않음',
    '- 기준 미달 (REJECT): 가중합 < 0.82, 또는 REJECT 트리거 해당',
    '',
    '⚠️ 습관적으로 모든 차원에 1.0을 주는 것은 Judge의 직무유기이다.',
    '너의 역할은 "통과시키기"가 아니라 "최고 품질만 통과시키기"이다.',
    '10개 중 2~3개를 REJECT하는 것이 정상이다.',
    '합의된 데이터라도 냉정하게 평가하라.',
    '',
    '⚠️ score가 1.0이 되려면 6개 차원 모두가 1.0이어야 한다.',
    '이런 일은 100개 중 1개도 없어야 정상이다.',
    '1.0을 주기 전에 "이 데이터가 정말 더 이상 개선할 점이 없는가?"를 자문하라.',
    '',
    '【출력 규칙 — JSON만 출력, 추가 텍스트 절대 금지】',
    '반드시 아래 JSON 스키마를 정확히 따른다:',
    '{',
    '  "verdict": "PASS" | "REJECT",',
    '  "score": 0.0,',
    '  "dimension_scores": {',
    '    "single_answer": 0.0,',
    '    "realism": 0.0,',
    '    "reasoning_depth": 0.0,',
    '    "distractor_quality": 0.0,',
    '    "safety_ethics": 0.0,',
    '    "format_completeness": 0.0',
    '  },',
    '  "reasons": ["..."],',
    '  "sample": {',
    '    "domain": "computer_ops"|"web_ops"|"ethics"|"cross_app"|"error_recovery",',
    '    "difficulty": "easy"|"medium"|"hard"|"expert",',
    '    "question_type": "mcq_single"|"mcq_reasoning"|"action_sequence"|"error_diagnosis"|"scenario_judgment",',
    '    "environment": {',
    '      "os": "Windows 11 (빌드 포함)",',
    '      "open_apps": ["앱1 (상태)", "앱2 (상태)"],',
    '      "active_window": "현재 활성 앱 + 화면",',
    '      "screen_description": "현재 화면 상세 설명",',
    '      "ime_state": "korean"|"english"|"unknown",',
    '      "network_status": "connected"|"disconnected"|"limited",',
    '      "user_permissions": "standard"|"admin",',
    '      "prior_actions": ["직전 행동 1", "직전 행동 2"]',
    '    },',
    '    "question": "...",',
    '    "scenario": "3~6문장의 구체적 상황 묘사",',
    '    "choices": [{"key":"A","text":"구체적 조작 순서 포함"},{"key":"B","text":"..."},{"key":"C","text":"..."},{"key":"D","text":"..."}],',
    '    "answer": {"key":"A"|"B"|"C"|"D"},',
    '    "explanation": "4~10문장: 정답 근거 + 모든 오답 소거",',
    '    "reasoning_trace": [{"step":1,"thought":"...","observation":"...","conclusion":"..."}],',
    '    "distractor_analysis": [',
    '      {"key":"B","trap_type":"common_mistake","why_wrong":"...","common_frequency":0.3},',
    '      {"key":"C","trap_type":"dangerous_action","why_wrong":"...","common_frequency":0.15},',
    '      {"key":"D","trap_type":"partial_solution","why_wrong":"...","common_frequency":0.25}',
    '    ],',
    '    "action_sequence": [{"order":1,"action":"...","target":"...","expected_result":"...","precondition":"..."}],',
    '    "tags": ["tag1","tag2","tag3"],',
    '    "learning_objective": "일반화 가능한 원칙 1문장",',
    '    "prerequisite_knowledge": ["선행 지식 1", "선행 지식 2"],',
    '    "related_topics": ["관련 주제 1", "관련 주제 2"],',
    '    "cognitive_load": "low"|"medium"|"high",',
    '    "real_world_frequency": "rare"|"occasional"|"common"|"daily",',
    '    "risk_if_wrong": "none"|"low"|"medium"|"high"|"critical",',
    '    "time_pressure": "none"|"low"|"moderate"|"high"|"extreme",',
    '    "common_mistakes": [{"mistake":"...","frequency":0.3,"consequence":"..."}],',
    '    "recovery_options": ["복구 방법 1", "복구 방법 2"],',
    '    "os_version_constraints": ["Windows 11 22H2+"]',
    '  }',
    '}',
    '',
    '【해설 작성 규정】',
    '- 정답이 왜 맞는지 2~4문장',
    '- 각 오답이 왜 틀리는지 1문장 이상 (모든 오답 소거)',
    '- ethics 도메인: "안전한 대안/거부 기준" 명확히 언급',
    '- 학습 포인트: 이 문제에서 일반화할 수 있는 원칙 1문장',
  ].join('\n'));
}

// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
// JUDGE USER PROMPT
// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

export function judgeUserPrompt(debateA: string, debateB: string): string {
  return judgeUserPromptWithContext({ debateA, debateB });
}

export function judgeUserPromptWithContext(params: {
  debateA: string;
  debateB: string;
  finalProposal?: string;
  mediatorNotes?: string;
}): string {
  const parts: string[] = [
    '아래는 토론 로그이다.',
  ];

  if (params.finalProposal) {
    parts.push('최종 합의안(FINAL_PROPOSAL)이 존재한다. 이 합의안을 최우선으로 평가하라.');
    parts.push('');
    parts.push('FINAL_PROPOSAL:');
    parts.push(params.finalProposal);
  } else {
    parts.push('최종 합의안이 없다. 토론을 종합해 직접 최종 샘플을 구성하라.');
  }

  if (params.mediatorNotes) {
    parts.push('');
    parts.push('MEDIATOR NOTES:');
    parts.push(params.mediatorNotes);
  }

  parts.push('');
  parts.push('A 로그:');
  parts.push(params.debateA);
  parts.push('');
  parts.push('B 로그:');
  parts.push(params.debateB);
  parts.push('');
  parts.push('위 정보를 바탕으로:');
  parts.push('1) 6차원 평가를 수행하라 (dimension_scores)');
  parts.push('2) 가중 합산 score를 계산하라');
  parts.push('3) REJECT 트리거를 하나씩 점검하라');
  parts.push('4) score >= 0.82이고 REJECT 트리거 없으면 PASS, 그 외 REJECT');
  parts.push('   ⚠️ 점수 인플레이션 금지: 모든 dimension이 1.0이면 반드시 재검토. 개선 여지가 정말 없는지 확인.');
  parts.push('5) verdict에 관계없이 항상 완전한 sample JSON을 포함하라 (REJECT여도 sample 필수 — 자동 복구에 필요)');
  parts.push('6) 반드시 JSON만 출력하라 (마크다운/추가 텍스트 금지)');

  return parts.filter(x => x !== '').join('\n');
}

// Question type selection helper
export function selectQuestionType(domain: DatasetDomain, difficulty: Difficulty): QuestionType {
  const weights: Record<string, Record<QuestionType, number>> = {
    'computer_ops:easy': { mcq_single: 0.6, mcq_reasoning: 0.2, action_sequence: 0.1, error_diagnosis: 0.05, scenario_judgment: 0.05 },
    'computer_ops:medium': { mcq_single: 0.3, mcq_reasoning: 0.25, action_sequence: 0.2, error_diagnosis: 0.15, scenario_judgment: 0.1 },
    'computer_ops:hard': { mcq_single: 0.1, mcq_reasoning: 0.2, action_sequence: 0.25, error_diagnosis: 0.2, scenario_judgment: 0.25 },
    'computer_ops:expert': { mcq_single: 0.05, mcq_reasoning: 0.15, action_sequence: 0.2, error_diagnosis: 0.25, scenario_judgment: 0.35 },
    'web_ops:easy': { mcq_single: 0.5, mcq_reasoning: 0.25, action_sequence: 0.15, error_diagnosis: 0.05, scenario_judgment: 0.05 },
    'web_ops:medium': { mcq_single: 0.25, mcq_reasoning: 0.25, action_sequence: 0.25, error_diagnosis: 0.15, scenario_judgment: 0.1 },
    'web_ops:hard': { mcq_single: 0.1, mcq_reasoning: 0.2, action_sequence: 0.2, error_diagnosis: 0.2, scenario_judgment: 0.3 },
    'web_ops:expert': { mcq_single: 0.05, mcq_reasoning: 0.15, action_sequence: 0.15, error_diagnosis: 0.25, scenario_judgment: 0.4 },
    'ethics:easy': { mcq_single: 0.5, mcq_reasoning: 0.3, action_sequence: 0.05, error_diagnosis: 0.05, scenario_judgment: 0.1 },
    'ethics:medium': { mcq_single: 0.3, mcq_reasoning: 0.3, action_sequence: 0.05, error_diagnosis: 0.1, scenario_judgment: 0.25 },
    'ethics:hard': { mcq_single: 0.1, mcq_reasoning: 0.25, action_sequence: 0.05, error_diagnosis: 0.15, scenario_judgment: 0.45 },
    'ethics:expert': { mcq_single: 0.05, mcq_reasoning: 0.2, action_sequence: 0.05, error_diagnosis: 0.2, scenario_judgment: 0.5 },
    'cross_app:easy': { mcq_single: 0.4, mcq_reasoning: 0.2, action_sequence: 0.25, error_diagnosis: 0.1, scenario_judgment: 0.05 },
    'cross_app:medium': { mcq_single: 0.2, mcq_reasoning: 0.2, action_sequence: 0.3, error_diagnosis: 0.15, scenario_judgment: 0.15 },
    'cross_app:hard': { mcq_single: 0.1, mcq_reasoning: 0.15, action_sequence: 0.3, error_diagnosis: 0.2, scenario_judgment: 0.25 },
    'cross_app:expert': { mcq_single: 0.05, mcq_reasoning: 0.1, action_sequence: 0.25, error_diagnosis: 0.25, scenario_judgment: 0.35 },
    'error_recovery:easy': { mcq_single: 0.3, mcq_reasoning: 0.2, action_sequence: 0.15, error_diagnosis: 0.3, scenario_judgment: 0.05 },
    'error_recovery:medium': { mcq_single: 0.15, mcq_reasoning: 0.2, action_sequence: 0.15, error_diagnosis: 0.35, scenario_judgment: 0.15 },
    'error_recovery:hard': { mcq_single: 0.05, mcq_reasoning: 0.15, action_sequence: 0.15, error_diagnosis: 0.35, scenario_judgment: 0.3 },
    'error_recovery:expert': { mcq_single: 0.05, mcq_reasoning: 0.1, action_sequence: 0.1, error_diagnosis: 0.35, scenario_judgment: 0.4 },
  };

  const key = `${domain}:${difficulty}`;
  const w = weights[key] ?? weights['computer_ops:medium']!;
  const r = Math.random();
  let cumulative = 0;
  for (const [qt, prob] of Object.entries(w)) {
    cumulative += prob;
    if (r <= cumulative) return qt as QuestionType;
  }
  return 'mcq_single';
}

// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
// REVISION PROMPT — Judge가 REJECT 후 토론자에게 수정 요청
// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

export function revisionDebaterPrompt(params: {
  kind: 'A' | 'B';
  revisionAttempt: number;
  maxRevisions: number;
  judgeReasons: string[];
  judgeScore: number;
  dimensionScores?: Record<string, number>;
  previousProposal: string;
  otherDebaterRevision?: string;
}): string {
  const parts: string[] = [
    `【수정 라운드 ${params.revisionAttempt}/${params.maxRevisions}】`,
    '',
    '⚠️ Judge가 이전 제안을 REJECT했다.',
    `점수: ${params.judgeScore}`,
  ];

  if (params.dimensionScores) {
    parts.push('');
    parts.push('차원별 점수:');
    for (const [dim, score] of Object.entries(params.dimensionScores)) {
      const label = dim === 'single_answer' ? '단일정답성' :
        dim === 'realism' ? '현실성' :
        dim === 'reasoning_depth' ? '추론깊이' :
        dim === 'distractor_quality' ? '오답품질' :
        dim === 'safety_ethics' ? '안전/윤리' :
        dim === 'format_completeness' ? '형식완성도' : dim;
      parts.push(`  · ${label}: ${score}`);
    }
  }

  parts.push('');
  parts.push('Judge 피드백:');
  for (const reason of params.judgeReasons) {
    parts.push(`  - ${reason}`);
  }

  parts.push('');
  parts.push('이전 FINAL_PROPOSAL:');
  parts.push(params.previousProposal || '(없음)');

  if (params.kind === 'A') {
    parts.push('');
    parts.push('【지시사항 — Debater A】');
    parts.push('위 피드백을 반영하여 FINAL_PROPOSAL을 수정하라.');
    parts.push('Judge가 지적한 모든 문제를 해결해야 한다.');
    parts.push('특히 점수가 낮은 차원을 집중적으로 개선하라.');
    parts.push('수정된 FINAL_PROPOSAL을 CONSENSUS_CALL_JUDGE + FINAL_PROPOSAL 블록으로 출력하라.');
  } else {
    parts.push('');
    if (params.otherDebaterRevision) {
      parts.push('Debater A의 수정안:');
      parts.push(params.otherDebaterRevision);
      parts.push('');
    }
    parts.push('【지시사항 — Debater B】');
    parts.push('A의 수정안이 Judge 피드백을 충분히 반영했는지 검증하라.');
    parts.push('부족한 부분이 있으면 추가 수정하라.');
    parts.push('최종 수정된 FINAL_PROPOSAL을 CONSENSUS_CALL_JUDGE + FINAL_PROPOSAL 블록으로 출력하라.');
  }

  parts.push('');
  parts.push(`남은 수정 기회: ${params.maxRevisions - params.revisionAttempt}회`);
  if (params.revisionAttempt >= params.maxRevisions) {
    parts.push('⚠️ 이것이 마지막 기회다. 반드시 모든 문제를 해결하라.');
  }

  return parts.join('\n');
}
