import fs from 'fs';
import { salvageMalformedJudgeRaw } from '../src/dataset_bot/recovery_helpers';
import { DatasetSampleSchema } from '../src/dataset_bot/schema';

const rejectedPath = (process.env.DATASET_OUT_DIR || 'datasets') + '/rejected.jsonl';
const lines = fs.readFileSync(rejectedPath, 'utf8').split(/\r?\n/).filter(Boolean);
for (const line of lines) {
  try {
    const obj = JSON.parse(line);
    if (obj.type === 'judge_invalid_json' && obj.raw && obj.raw.trim()) {
      const parsed = salvageMalformedJudgeRaw(obj.raw);
      if (!parsed) continue;
      const scoreVal = typeof parsed.score === 'number' ? parsed.score : Number(parsed.score);
      const sample = {
        id: `debug-${Date.now()}-${Math.random().toString(36).slice(2,8)}`,
        domain: parsed.sample.domain,
        difficulty: parsed.sample.difficulty,
        question_type: 'mcq_single',
        question: parsed.sample.question,
        choices: parsed.sample.choices,
        answer: parsed.sample.answer,
        explanation: parsed.sample.explanation,
        tags: parsed.sample.tags || [],
        source: { method: 'recovered_judge_invalid' },
        quality: { judge_score: scoreVal, checks: { judge_pass: true } },
      };
      const parsedSchema = DatasetSampleSchema.safeParse(sample as any);
      console.log('--- VALIDATION ---');
      console.log('scoreVal=', scoreVal);
      if (!parsedSchema.success) {
        console.log('validation failed:', JSON.stringify(parsedSchema.error.errors, null, 2));
      } else {
        console.log('validation succeeded for sample id', sample.id);
      }
    }
  } catch (e) {
    console.warn('line parse failed', e.message);
  }
}
