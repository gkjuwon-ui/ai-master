import fs from 'fs';
import path from 'path';
import { JsonlStorage } from '../src/dataset_bot/storage';
import { DatasetSampleSchema } from '../src/dataset_bot/schema';
import { OpenAIClient } from '../src/dataset_bot/openai_client';
import { judgeSystemPrompt } from '../src/dataset_bot/prompts';

const outDir = process.env.DATASET_OUT_DIR || path.join(__dirname, '..', 'datasets');
const rejectedPath = path.join(outDir, 'rejected.jsonl');
const datasetPath = path.join(outDir, 'dataset.jsonl');
const indexPath = path.join(outDir, 'index.json');

function extractFirstJsonObject(text: string): string | null {
  const start = text.indexOf('{');
  if (start === -1) return null;
  let depth = 0;
  for (let i = start; i < text.length; i++) {
    const ch = text[i];
    if (ch === '{') depth++;
    else if (ch === '}') {
      depth--;
      if (depth === 0) return text.slice(start, i + 1);
    }
  }
  return null;
}

async function main() {
  if (!fs.existsSync(rejectedPath)) {
    console.log('No rejected.jsonl found at', rejectedPath);
    return;
  }

  const storage = new JsonlStorage({ datasetPath, rejectedPath, indexPath });
  const lines = fs.readFileSync(rejectedPath, 'utf8').split(/\r?\n/).filter(Boolean);
  const keep: string[] = [];
  let moved = 0;

  const openaiKey = process.env.OPENAI_API_KEY;
  const openaiBase = process.env.OPENAI_BASE_URL || 'https://api.openai.com';
  const llm = openaiKey ? new OpenAIClient({ apiKey: openaiKey, baseUrl: openaiBase }) : null;

  for (const line of lines) {
    let obj: any;
    try {
      obj = JSON.parse(line);
    } catch {
      keep.push(line);
      continue;
    }

    if (obj?.type === 'judge_invalid_json' && typeof obj.raw === 'string' && obj.raw.trim().length > 0) {
      // try direct extraction first
      const extracted = extractFirstJsonObject(obj.raw);
      let parsed: any = null;

      if (extracted) {
        try { parsed = JSON.parse(extracted); } catch { parsed = null; }
      }

      // if not parsed, try a best-effort (non-LLM) salvage first
      if (!parsed) {
        try {
          const { salvageMalformedJudgeRaw } = await import('../src/dataset_bot/recovery_helpers');
          const salvage = salvageMalformedJudgeRaw(obj.raw);
          if (salvage) {
            parsed = salvage;
            console.log('Best-effort salvage produced JSON.');
          }
        } catch (e) {
          console.warn('Salvage helper failed:', (e as any)?.message || e);
        }
      }

      // if not parsed, try LLM repair when available
      if (!parsed && llm) {
        try {
          console.log('Attempting LLM repair for rejected entry...');
          const repaired = await llm.chatOnce({
            model: process.env.OPENAI_JUDGE_MODEL || 'gpt-4o',
            messages: [
              { role: 'system', content: judgeSystemPrompt(obj.domain || 'ethics', obj.difficulty || 'hard') },
              { role: 'user', content: 'The following judge output is malformed. Extract and return ONLY a single valid JSON object that matches the judge schema.\n\n' + obj.raw },
            ],
            temperature: 0.0,
            max_tokens: 800,
          });
          const candidate = extractFirstJsonObject(repaired.text) || repaired.text;
          parsed = JSON.parse(candidate);
          console.log('LLM repair produced JSON.');
        } catch (e) {
          console.warn('LLM repair failed for rejected entry:', (e as any)?.message || e);
          parsed = null;
        }
      }

      if (parsed && parsed?.verdict === 'PASS' && parsed?.sample) {
        const scoreVal = typeof parsed.score === 'number' ? parsed.score : Number(parsed.score);
        if (!Number.isNaN(scoreVal) && scoreVal >= 0.85) {
          const sample = {
            id: `recovered-${Date.now()}-${Math.random().toString(36).slice(2,8)}`,
            domain: parsed.sample.domain,
            difficulty: parsed.sample.difficulty,
            question_type: 'mcq_single',
            question: parsed.sample.question,
            choices: parsed.sample.choices,
            answer: parsed.sample.answer,
            explanation: parsed.sample.explanation,
            tags: parsed.sample.tags || [],
            source: { method: 'discord_debate', models: { debater_a: 'recovered', debater_b: 'recovered', judge: 'recovered' }, created_at: new Date().toISOString() },
            quality: { judge_score: scoreVal, checks: { judge_pass: true } },
          };
          const valid = DatasetSampleSchema.safeParse(sample);
          if (valid.success) {
            await storage.appendAccepted(sample as any);
            moved++;
            console.log('Recovered and moved to accepted:', sample.id);
            continue; // do not keep this rejected line
          }
        }
      }
    }

    keep.push(line);
  }

  fs.writeFileSync(rejectedPath, keep.join('\n') + (keep.length ? '\n' : ''), 'utf8');
  console.log(`Recovery finished. Moved ${moved} samples to accepted. Rejected file rewritten.`);
}

main().catch((e) => { console.error(e); process.exit(1); });