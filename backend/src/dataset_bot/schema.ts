import { z } from 'zod';

/* ================================================================
   OSEN-1.0 Dataset Schema v2 - LLaMA Fine-Tuning Native Format
   
   Output: multi-turn conversation for direct LLaMA chat training.
   Enhancements: CoT reasoning, environment context, action sequences,
   distractor analysis, cross-reference validation.
   ================================================================ */

export const DatasetDomainSchema = z.enum(['computer_ops', 'web_ops', 'ethics', 'cross_app', 'error_recovery']);
export type DatasetDomain = z.infer<typeof DatasetDomainSchema>;

export const DifficultySchema = z.enum(['easy', 'medium', 'hard', 'expert']);
export type Difficulty = z.infer<typeof DifficultySchema>;

export const ChoiceKeySchema = z.enum(['A', 'B', 'C', 'D']);

export const QuestionTypeSchema = z.enum([
  'mcq_single',
  'mcq_reasoning',
  'action_sequence',
  'error_diagnosis',
  'scenario_judgment',
]);
export type QuestionType = z.infer<typeof QuestionTypeSchema>;

export const EnvironmentContextSchema = z.object({
  os: z.string().default('Windows 11'),
  open_apps: z.array(z.string()).default([]),
  active_window: z.string().optional(),
  screen_description: z.string().optional(),
  ime_state: z.enum(['korean', 'english', 'unknown']).optional(),
  network_status: z.enum(['connected', 'disconnected', 'limited']).optional(),
  user_permissions: z.enum(['standard', 'admin']).optional(),
  prior_actions: z.array(z.string()).default([]),
});
export type EnvironmentContext = z.infer<typeof EnvironmentContextSchema>;

export const DistractorAnalysisSchema = z.object({
  key: ChoiceKeySchema,
  trap_type: z.enum([
    'common_mistake', 'partial_solution', 'dangerous_action',
    'outdated_method', 'wrong_order', 'missing_prerequisite',
    'environment_dependent', 'social_engineering',
    'unreliable_method', 'inefficient_workflow', 'incomplete_action',
    'overcomplicated', 'conceptual_error', 'scope_mismatch',
  ]),
  why_wrong: z.string().min(20),
  common_frequency: z.number().min(0).max(1).optional(),
});
export type DistractorAnalysis = z.infer<typeof DistractorAnalysisSchema>;

export const ReasoningTraceSchema = z.object({
  step: z.number().min(1),
  thought: z.string().min(10),
  observation: z.string().optional(),
  conclusion: z.string().optional(),
});
export type ReasoningTrace = z.infer<typeof ReasoningTraceSchema>;

export const ActionStepSchema = z.object({
  order: z.number().min(1),
  action: z.string().min(5),
  target: z.string().optional(),
  expected_result: z.string().optional(),
  precondition: z.string().optional(),
});
export type ActionStep = z.infer<typeof ActionStepSchema>;

export const DatasetSampleSchema = z.object({
  id: z.string().min(8),
  domain: DatasetDomainSchema,
  difficulty: DifficultySchema,
  question_type: QuestionTypeSchema,
  environment: EnvironmentContextSchema.optional(),
  question: z.string().min(20),
  scenario: z.string().optional(),
  choices: z.array(z.object({ key: ChoiceKeySchema, text: z.string().min(1) })).length(4),
  answer: z.object({ key: ChoiceKeySchema }),
  explanation: z.string().min(60),
  reasoning_trace: z.array(ReasoningTraceSchema).optional(),
  action_sequence: z.array(ActionStepSchema).optional(),
  distractor_analysis: z.array(DistractorAnalysisSchema).optional(),
  tags: z.array(z.string()).max(20).default([]),
  learning_objective: z.string().optional(),
  prerequisite_knowledge: z.array(z.string()).default([]),
  related_topics: z.array(z.string()).default([]),
  // v3 enriched fields
  cognitive_load: z.enum(['low', 'medium', 'high']).optional(),
  real_world_frequency: z.enum(['rare', 'occasional', 'common', 'daily']).optional(),
  risk_if_wrong: z.enum(['none', 'low', 'medium', 'high', 'critical']).optional(),
  time_pressure: z.enum(['none', 'low', 'moderate', 'high', 'extreme']).optional(),
  common_mistakes: z.array(z.object({
    mistake: z.string().min(5),
    frequency: z.number().min(0).max(1),
    consequence: z.string().min(5),
  })).optional(),
  recovery_options: z.array(z.string()).optional(),
  os_version_constraints: z.array(z.string()).optional(),
  source: z.object({
    method: z.literal('discord_debate'),
    models: z.object({
      debater_a: z.string().min(1),
      debater_b: z.string().min(1),
      judge: z.string().min(1),
    }),
    created_at: z.string().min(8),
    version: z.string().default('2.0'),
    discord: z.object({
      guild_id: z.string().optional(),
      channel_id: z.string().optional(),
      message_ids: z.array(z.string()).optional(),
    }).optional(),
  }),
  quality: z.object({
    judge_score: z.number().min(0).max(1),
    reasoning_depth_score: z.number().min(0).max(1).optional(),
    distractor_quality_score: z.number().min(0).max(1).optional(),
    practical_relevance_score: z.number().min(0).max(1).optional(),
    checks: z.record(z.boolean()).default({}),
  }).optional(),
});

export type DatasetSample = z.infer<typeof DatasetSampleSchema>;

/* ================================================================
   LLaMA Conversation Format Converter
   ================================================================ */

export interface LlamaConversation {
  id: string;
  conversations: Array<{ role: 'system' | 'user' | 'assistant'; content: string }>;
  metadata: { domain: string; difficulty: string; question_type: string; tags: string[]; quality_score: number };
}

function buildSystemPrompt(domain: DatasetDomain): string {
  const base = `�ʴ� osen-1.0, ��ǻ�͸� ���� �����ϴ� AI ������Ʈ��. ȭ���� ����, ���콺�� �����̰�, Ű���带 �Է��Ͽ� ������� ��û�� �����Ѵ�. �׻� �����ϰ� ȿ������ ����� �����ϸ�, ��Ȯ���� ��Ȳ������ ����ڿ��� Ȯ���� ��û�Ѵ�.`;
  const ctx: Record<DatasetDomain, string> = {
    computer_ops: '���� Windows OS ȯ�濡�� ����ũ�� ���� �۾��� ���� ���̴�. �Է� ��Ŀ��, IME ����, â ����, ����Ű, ���� �ý��� ���ۿ� Ư�� �����Ѵ�.',
    web_ops: '���� �� ���������� ������Ʈ ���� �۾��� ���� ���̴�. �� ����, �� �Է�, �˾� ó��, �ε� ���, ��Ű ����, CAPTCHA ��ó�� �����Ѵ�.',
    ethics: '��ǻ�� ������ ������/���� ������ �Ǵ��ؾ� �Ѵ�. ����� ����, �������� ��ȣ, �ּ� ���� ��Ģ, ���� ���ɼ�, �չ����� �ֿ켱���� �����Ѵ�.',
    cross_app: '���� ���ø����̼��� �����ϴ� ���� �۾��� ���� ���̴�. Ŭ������ ����, â ��ȯ ����, ������ ���Ἲ, �� �� ������ ���޿� �����Ѵ�.',
    error_recovery: '���� ��Ȳ���� ���� �۾��� ���� ���̴�. ���� ���� ����, ������ ���� ��� ����, ������ ����, �ݺ� ���� ������ �����Ѵ�.',
  };
  return `${base}\n\n${ctx[domain]}`;
}

function buildUserMessage(sample: DatasetSample): string {
  const parts: string[] = [];
  if (sample.environment) {
    const env = sample.environment;
    parts.push('[���� ȯ��]');
    parts.push(`OS: ${env.os}`);
    if (env.open_apps.length > 0) parts.push(`���� ��: ${env.open_apps.join(', ')}`);
    if (env.active_window) parts.push(`Ȱ�� â: ${env.active_window}`);
    if (env.screen_description) parts.push(`ȭ�� ����: ${env.screen_description}`);
    if (env.ime_state) parts.push(`IME: ${env.ime_state === 'korean' ? '�ѱ�' : env.ime_state === 'english' ? '����' : '�Ҹ�'}`);
    if (env.network_status) parts.push(`��Ʈ��ũ: ${env.network_status}`);
    if (env.user_permissions) parts.push(`����: ${env.user_permissions}`);
    if (env.prior_actions.length > 0) {
      parts.push('���� �ൿ:');
      env.prior_actions.forEach((a, i) => parts.push(`  ${i + 1}. ${a}`));
    }
    parts.push('');
  }
  if (sample.scenario) { parts.push('[��Ȳ]'); parts.push(sample.scenario); parts.push(''); }
  parts.push('[����]');
  parts.push(sample.question);
  parts.push('');
  parts.push('[������]');
  for (const c of sample.choices) parts.push(`${c.key}) ${c.text}`);
  return parts.join('\n');
}

function buildAssistantMessage(sample: DatasetSample): string {
  const parts: string[] = [];
  if (sample.reasoning_trace && sample.reasoning_trace.length > 0) {
    parts.push('[��� ����]');
    for (const s of sample.reasoning_trace) {
      parts.push(`${s.step}�ܰ�: ${s.thought}`);
      if (s.observation) parts.push(`  -> ����: ${s.observation}`);
      if (s.conclusion) parts.push(`  -> ���: ${s.conclusion}`);
    }
    parts.push('');
  }
  parts.push(`[����] ${sample.answer.key}`);
  parts.push('');
  parts.push('[�ؼ�]');
  parts.push(sample.explanation);
  if (sample.distractor_analysis && sample.distractor_analysis.length > 0) {
    parts.push('');
    parts.push('[���� �м�]');
    for (const da of sample.distractor_analysis) parts.push(`${da.key}) [${da.trap_type}] ${da.why_wrong}`);
  }
  if (sample.action_sequence && sample.action_sequence.length > 0) {
    parts.push('');
    parts.push('[�ùٸ� ���� ����]');
    for (const s of sample.action_sequence) {
      let line = `${s.order}. ${s.action}`;
      if (s.target) line += ` -> ���: ${s.target}`;
      if (s.expected_result) line += ` -> ���� ���: ${s.expected_result}`;
      parts.push(line);
    }
  }
  if (sample.learning_objective) { parts.push(''); parts.push(`[학습 포인트] ${sample.learning_objective}`); }
  if (sample.prerequisite_knowledge && sample.prerequisite_knowledge.length > 0) {
    parts.push('');
    parts.push(`[선행 지식] ${sample.prerequisite_knowledge.join(', ')}`);
  }
  if (sample.common_mistakes && sample.common_mistakes.length > 0) {
    parts.push('');
    parts.push('[흔한 실수]');
    for (const m of sample.common_mistakes) {
      parts.push(`- ${m.mistake} (빈도: ${(m.frequency * 100).toFixed(0)}%) → ${m.consequence}`);
    }
  }
  if (sample.recovery_options && sample.recovery_options.length > 0) {
    parts.push('');
    parts.push(`[복구 방법] ${sample.recovery_options.join(' / ')}`);
  }
  if (sample.cognitive_load || sample.risk_if_wrong || sample.time_pressure) {
    parts.push('');
    const meta: string[] = [];
    if (sample.cognitive_load) meta.push(`인지부하: ${sample.cognitive_load}`);
    if (sample.risk_if_wrong) meta.push(`오답위험: ${sample.risk_if_wrong}`);
    if (sample.time_pressure) meta.push(`시간압박: ${sample.time_pressure}`);
    parts.push(`[난이도 메타] ${meta.join(' | ')}`);
  }
  return parts.join('\n');
}

export function sampleToLlamaConversation(sample: DatasetSample): LlamaConversation {
  return {
    id: sample.id,
    conversations: [
      { role: 'system', content: buildSystemPrompt(sample.domain) },
      { role: 'user', content: buildUserMessage(sample) },
      { role: 'assistant', content: buildAssistantMessage(sample) },
    ],
    metadata: {
      domain: sample.domain,
      difficulty: sample.difficulty,
      question_type: sample.question_type,
      tags: sample.tags,
      quality_score: sample.quality?.judge_score ?? 0,
    },
  };
}

export function sampleToTrainingLine(sample: DatasetSample): string {
  return JSON.stringify(sampleToLlamaConversation(sample));
}

export function validateSingleCorrect(sample: DatasetSample): { ok: boolean; reason?: string } {
  const keys = new Set(sample.choices.map((c) => c.key));
  if (keys.size !== 4) return { ok: false, reason: 'choices_not_4_unique_keys' };
  const answerKey = sample.answer.key;
  if (!keys.has(answerKey)) return { ok: false, reason: 'answer_not_in_choices' };
  const choiceTexts = sample.choices.map((c) => c.text.trim().toLowerCase());
  if (new Set(choiceTexts).size !== choiceTexts.length) return { ok: false, reason: 'duplicate_choice_texts' };
  const minLen: Record<string, number> = { easy: 60, medium: 100, hard: 150, expert: 200 };
  if (sample.explanation.length < (minLen[sample.difficulty] ?? 60)) return { ok: false, reason: `explanation_too_short_for_${sample.difficulty}` };
  const answerText = sample.choices.find(c => c.key === answerKey)?.text?.toLowerCase() ?? '';
  if (answerText.length > 10 && sample.question.toLowerCase().includes(answerText)) return { ok: false, reason: 'question_contains_answer_text' };
  const lens = sample.choices.map(c => c.text.length);
  if (Math.min(...lens) > 0 && Math.max(...lens) / Math.min(...lens) > 3.5) return { ok: false, reason: 'choice_length_imbalance' };
  if (sample.question_type === 'mcq_reasoning' && (!sample.reasoning_trace || sample.reasoning_trace.length < 2)) return { ok: false, reason: 'mcq_reasoning_requires_reasoning_trace' };
  if (sample.question_type === 'action_sequence' && (!sample.action_sequence || sample.action_sequence.length < 2)) return { ok: false, reason: 'action_sequence_requires_steps' };
  return { ok: true };
}
