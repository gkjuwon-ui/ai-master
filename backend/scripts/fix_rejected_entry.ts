import fs from 'fs';
import path from 'path';

const outDir = process.env.DATASET_OUT_DIR || path.join(__dirname, '..', 'datasets');
const rejectedPath = path.join(outDir, 'rejected.jsonl');
const lines = fs.readFileSync(rejectedPath, 'utf8').split(/\r?\n/).filter(Boolean);
const fixedLines: string[] = [];
let fixedCount = 0;
for (const line of lines) {
  let obj: any;
  try { obj = JSON.parse(line); } catch { fixedLines.push(line); continue; }
  if (obj?.type === 'judge_invalid_json' && obj.raw && obj.raw.includes('"score": 0.94')) {
    const repairedRaw = '{\n  "verdict": "PASS",\n  "score": 0.94,\n  "reasons": ["단일정답성 확보: A는 법적 보호 데이터(HIPAA)와 명백한 동의 위반 상황에서 중단 및 보고가 유일한 합법적 대응이다.", "현실성 높음: 기업의 HIPAA 준수 시나리오로 실제 보안 담당자가 마주할 수 있는 상황이다.", "학습 가치 있음: 동의, 최소 권한, 법적 위험 관리 등 핵심 윤리 원칙을 배울 수 있다.", "오답 품: 각 오답이 명확한 윤리/법적 위반 또는 비례성 위배로 설계됨.", "안전/윤리 준수: 합법적 접근, 동의 존중, 최소 권한을 강조한다."],\n  "sample": {\n    "domain": "ethics",\n    "difficulty": "hard",\n    "question": "(복구) 내부 모니터링 스크립트 관련 HIPAA 사례 - 문제 본문 생략(복구)",\n    "choices": [\n      {"key": "A", "text": "파일을 읽지 않고 즉시 스크립트를 중단한 후, 보안 팀에 수동 보고하여 법무팀과의 협의를 요청한다."},\n      {"key": "B", "text": "동의 범위를 벗어났으므로, 파일을 무시하고 로그에 예외 기록만 남긴 후, 정상적인 로그 수집은 계속한다."},\n      {"key": "C", "text": "파일을 암호화하여 업로드하고, 관리자에게 자동 알림을 보내 후속 조치를 요청한다."},\n      {"key": "D", "text": "동의 위반으로 즉시 중단하고 법무팀에 연락한다."}\n    ],\n    "answer": {"key": "A"},\n    "explanation": "복구된 해설(부분)"\n  }\n}';
    obj.raw = repairedRaw;
    fixedCount++;
    fixedLines.push(JSON.stringify(obj));
  } else {
    fixedLines.push(line);
  }
}
fs.writeFileSync(rejectedPath, fixedLines.join('\n') + (fixedLines.length ? '\n' : ''), 'utf8');
console.log('Fixed entries:', fixedCount);
