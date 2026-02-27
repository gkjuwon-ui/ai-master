import fs from 'fs';
import path from 'path';
import crypto from 'crypto';
import type { DatasetSample } from './schema';
import { sampleToTrainingLine } from './schema';

/* ================================================================
   Storage v2 - Dual-format output (LLaMA training + raw metadata)
   
   Outputs:
   - training.jsonl  : LLaMA conversation format (direct training input)
   - metadata.jsonl  : Full sample with all metadata (for analysis)
   - rejected.jsonl  : Rejected samples with reasons
   - index.json      : SHA-256 dedup index
   - stats.json      : Generation statistics
   ================================================================ */

export interface StorageConfig {
  outDir: string;
}

type IndexFile = { hashes: Record<string, true>; count: number };

interface GenerationStats {
  total_attempted: number;
  total_accepted: number;
  total_rejected: number;
  by_domain: Record<string, { accepted: number; rejected: number }>;
  by_difficulty: Record<string, { accepted: number; rejected: number }>;
  by_question_type: Record<string, number>;
  avg_quality_score: number;
  last_updated: string;
}

export class JsonlStorage {
  private outDir: string;
  private trainingPath: string;
  private metadataPath: string;
  private rejectedPath: string;
  private indexPath: string;
  private statsPath: string;
  private index: IndexFile;
  private stats: GenerationStats;

  constructor(cfg: StorageConfig) {
    this.outDir = cfg.outDir;
    this.ensureDir(cfg.outDir);
    this.trainingPath = path.join(cfg.outDir, 'training.jsonl');
    this.metadataPath = path.join(cfg.outDir, 'metadata.jsonl');
    this.rejectedPath = path.join(cfg.outDir, 'rejected.jsonl');
    this.indexPath = path.join(cfg.outDir, 'index.json');
    this.statsPath = path.join(cfg.outDir, 'stats.json');
    this.index = this.loadIndex();
    this.stats = this.loadStats();
  }

  // Legacy constructor compatibility
  static fromLegacy(cfg: { datasetPath: string; rejectedPath: string; indexPath: string }): JsonlStorage {
    const outDir = path.dirname(cfg.datasetPath);
    return new JsonlStorage({ outDir });
  }

  private ensureDir(dir: string) {
    if (!fs.existsSync(dir)) fs.mkdirSync(dir, { recursive: true });
  }

  private loadIndex(): IndexFile {
    try {
      if (fs.existsSync(this.indexPath)) {
        const raw = fs.readFileSync(this.indexPath, 'utf8');
        const parsed = JSON.parse(raw);
        if (parsed?.hashes) return { hashes: parsed.hashes, count: parsed.count ?? Object.keys(parsed.hashes).length };
      }
    } catch { /* ignore */ }
    return { hashes: {}, count: 0 };
  }

  private loadStats(): GenerationStats {
    try {
      if (fs.existsSync(this.statsPath)) {
        return JSON.parse(fs.readFileSync(this.statsPath, 'utf8'));
      }
    } catch { /* ignore */ }
    return {
      total_attempted: 0, total_accepted: 0, total_rejected: 0,
      by_domain: {}, by_difficulty: {}, by_question_type: {},
      avg_quality_score: 0, last_updated: new Date().toISOString(),
    };
  }

  private persistIndex() {
    fs.writeFileSync(this.indexPath, JSON.stringify(this.index, null, 2), 'utf8');
  }

  private persistStats() {
    this.stats.last_updated = new Date().toISOString();
    fs.writeFileSync(this.statsPath, JSON.stringify(this.stats, null, 2), 'utf8');
  }

  private updateStats(sample: DatasetSample, accepted: boolean) {
    this.stats.total_attempted++;
    if (accepted) {
      this.stats.total_accepted++;
      const d = sample.domain;
      const diff = sample.difficulty;
      const qt = sample.question_type;
      if (!this.stats.by_domain[d]) this.stats.by_domain[d] = { accepted: 0, rejected: 0 };
      this.stats.by_domain[d].accepted++;
      if (!this.stats.by_difficulty[diff]) this.stats.by_difficulty[diff] = { accepted: 0, rejected: 0 };
      this.stats.by_difficulty[diff].accepted++;
      this.stats.by_question_type[qt] = (this.stats.by_question_type[qt] ?? 0) + 1;
      const score = sample.quality?.judge_score ?? 0;
      const prevTotal = this.stats.avg_quality_score * (this.stats.total_accepted - 1);
      this.stats.avg_quality_score = (prevTotal + score) / this.stats.total_accepted;
    } else {
      this.stats.total_rejected++;
      const d = sample.domain;
      const diff = sample.difficulty;
      if (!this.stats.by_domain[d]) this.stats.by_domain[d] = { accepted: 0, rejected: 0 };
      this.stats.by_domain[d].rejected++;
      if (!this.stats.by_difficulty[diff]) this.stats.by_difficulty[diff] = { accepted: 0, rejected: 0 };
      this.stats.by_difficulty[diff].rejected++;
    }
    this.persistStats();
  }

  computeHash(sample: Pick<DatasetSample, 'question' | 'choices' | 'domain' | 'difficulty'>): string {
    const payload = {
      domain: sample.domain,
      difficulty: sample.difficulty,
      question: sample.question.trim().toLowerCase(),
      choices: sample.choices.map((c) => ({ key: c.key, text: c.text.trim().toLowerCase() })),
    };
    return crypto.createHash('sha256').update(JSON.stringify(payload)).digest('hex');
  }

  isDuplicate(hash: string): boolean {
    return Boolean(this.index.hashes[hash]);
  }

  async appendAccepted(sample: DatasetSample): Promise<void> {
    // Write LLaMA training format
    const trainingLine = sampleToTrainingLine(sample);
    await fs.promises.appendFile(this.trainingPath, trainingLine + '\n', 'utf8');

    // Write full metadata
    const metadataLine = JSON.stringify(sample);
    await fs.promises.appendFile(this.metadataPath, metadataLine + '\n', 'utf8');

    // Update index
    const h = this.computeHash(sample);
    this.index.hashes[h] = true;
    this.index.count++;
    this.persistIndex();

    // Update stats
    this.updateStats(sample, true);
  }

  async appendRejected(obj: any): Promise<void> {
    const line = JSON.stringify({ ...obj, rejected_at: new Date().toISOString() });
    await fs.promises.appendFile(this.rejectedPath, line + '\n', 'utf8');
    if (obj.sample || obj.domain) {
      const fakeSample = { domain: obj.domain ?? 'computer_ops', difficulty: obj.difficulty ?? 'medium', question_type: 'mcq_single' } as any;
      this.stats.total_attempted++;
      this.stats.total_rejected++;
      this.persistStats();
    }
  }

  getStats(): GenerationStats {
    return { ...this.stats };
  }

  getAcceptedCount(): number {
    return this.index.count;
  }
}
