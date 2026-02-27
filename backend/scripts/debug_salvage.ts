import fs from 'fs';
import { salvageMalformedJudgeRaw } from '../src/dataset_bot/recovery_helpers';

const rejectedPath = (process.env.DATASET_OUT_DIR || 'datasets') + '/rejected.jsonl';
const lines = fs.readFileSync(rejectedPath, 'utf8').split(/\r?\n/).filter(Boolean);
for (const line of lines) {
  try {
    const obj = JSON.parse(line);
    if (obj.type === 'judge_invalid_json' && obj.raw && obj.raw.trim()) {
      const parsed = salvageMalformedJudgeRaw(obj.raw);
      console.log('--- ENTRY ---');
      console.log('original-type:', obj.type);
      console.log('salvage-result:', parsed ? JSON.stringify({verdict: parsed.verdict, score: parsed.score, sampleKeys: parsed.sample ? Object.keys(parsed.sample) : null}, null, 2) : 'null');
      if (parsed && parsed.sample) console.log('sample:', JSON.stringify(parsed.sample, null, 2));
    }
  } catch (e) {
    console.warn('line parse failed', e.message);
  }
}
