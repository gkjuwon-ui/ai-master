import crypto from 'crypto';
import type { DatasetDomain, Difficulty, DatasetSample, QuestionType } from './schema';
import { DatasetSampleSchema, validateSingleCorrect } from './schema';
import { OpenAIClient } from './openai_client';
import type { ChatMessage } from './openai_client';
import { debaterSystemPrompt, judgeSystemPrompt, judgeUserPromptWithContext, mediatorSystemPrompt, selectQuestionType, revisionDebaterPrompt } from './prompts';
import type { JsonlStorage } from './storage';
import { salvageMalformedJudgeRaw } from './recovery_helpers';

export interface DebateModels {
  debaterA: string;
  debaterB: string;
  mediator: string;
  judge: string;
}

export interface GenerateParams {
  domain: DatasetDomain;
  difficulty: Difficulty;
  models: DebateModels;
  createdAtIso: string;
  discord?: {
    guild_id?: string;
    channel_id?: string;
    thread_id?: string;
    message_ids?: string[];
  };
}

export interface JudgeEnvelope {
  verdict: 'PASS' | 'REJECT';
  score: number;
  dimension_scores?: {
    single_answer?: number;
    realism?: number;
    reasoning_depth?: number;
    distractor_quality?: number;
    safety_ethics?: number;
    format_completeness?: number;
  };
  reasons: string[];
  sample?: {
    domain: DatasetDomain;
    difficulty: Difficulty;
    question_type?: string;
    environment?: any;
    question: string;
    scenario?: string;
    choices: { key: 'A' | 'B' | 'C' | 'D'; text: string }[];
    answer: { key: 'A' | 'B' | 'C' | 'D' };
    explanation: string;
    reasoning_trace?: any[];
    action_sequence?: any[];
    distractor_analysis?: any[];
    tags?: string[];
    learning_objective?: string;
    prerequisite_knowledge?: string[];
    related_topics?: string[];
    // v3 enriched fields
    cognitive_load?: 'low' | 'medium' | 'high';
    real_world_frequency?: 'rare' | 'occasional' | 'common' | 'daily';
    risk_if_wrong?: 'none' | 'low' | 'medium' | 'high' | 'critical';
    time_pressure?: 'none' | 'low' | 'moderate' | 'high' | 'extreme';
    recovery_options?: string[];
    common_mistakes?: { mistake: string; frequency: number; consequence: string }[];
    os_version_constraints?: string[];
  };
}

export class DatasetOrchestrator {
  constructor(
    private llm: OpenAIClient,
    private storage: JsonlStorage,
  ) {}

  private extractFirstJsonObject(text: string): string | null {
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
    return null; // incomplete
  }

  private async repairJudgeJson(params: GenerateParams, raw: string): Promise<JudgeEnvelope | null> {
    // 1) quick-extract any JSON-like substring and try parsing
    try {
      const extracted = this.extractFirstJsonObject(raw || '');
      if (extracted) {
        try {
          const parsed = JSON.parse(extracted);
          console.log('[Orchestrator] repairJudgeJson: extracted JSON parsed directly');
          return parsed as JudgeEnvelope;
        } catch (e) {
          // fall through to LLM repair
          console.log('[Orchestrator] repairJudgeJson: extracted JSON parse failed, will attempt LLM repair');
        }
      }
    } catch (e) {
      console.warn('[Orchestrator] repairJudgeJson: extraction error', e);
    }

    // 2) ask LLM to convert the raw into a single valid JSON object
    try {
      const repaired = await this.llm.chatOnce({
        model: params.models.judge,
        messages: [
          { role: 'system', content: judgeSystemPrompt(params.domain, params.difficulty) },
          {
            role: 'user',
            content:
              'You must output ONLY a single valid JSON object that matches the required schema. No markdown. No extra text.\n' +
              'The previous output was invalid JSON. Convert it into valid JSON while preserving the intent.\n\n' +
              raw,
          },
        ],
        temperature: 0.0,
        max_tokens: 1200,
      });

      // sometimes the LLM still returns extra text; extract first JSON object
      const extracted = this.extractFirstJsonObject(repaired.text || '');
      const candidate = extracted ? extracted : repaired.text;
      return JSON.parse(candidate.trim()) as JudgeEnvelope;
    } catch (e) {
      console.warn('[Orchestrator] repairJudgeJson failed to repair judge output:', (e as any)?.message || e);
      return null;
    }
  }

  private async streamWithContinuation(params: {
    model: string;
    messages: ChatMessage[];
    temperature: number;
    max_tokens: number;
    onDelta?: (delta: string) => void;
    maxContinuations?: number;
  }): Promise<{ text: string; finishReason?: string }> {
    const maxContinuations = Math.max(0, params.maxContinuations ?? 2);

    let allText = '';
    let currentMessages = [...params.messages];

    for (let attempt = 0; attempt <= maxContinuations; attempt++) {
      let res: { text: string; finishReason?: string };
      try {
        res = await this.llm.chatStream({
          model: params.model,
          messages: currentMessages,
          temperature: params.temperature,
          max_tokens: params.max_tokens,
          onDelta: (d) => {
            allText += d;
            params.onDelta?.(d);
          },
        });
      } catch (e: any) {
        console.warn(`[Orchestrator] streamWithContinuation fallback to chatOnce: ${(e as any)?.message || String(e)}`);
        const fallback = await this.llm.chatOnce({
          model: params.model,
          messages: currentMessages,
          temperature: params.temperature,
          max_tokens: params.max_tokens,
        });
        allText += fallback.text;
        params.onDelta?.(fallback.text);
        return { text: allText, finishReason: undefined };
      }

      const isLengthStop = res.finishReason === 'length';
      if (!isLengthStop || attempt === maxContinuations) {
        return { text: allText, finishReason: res.finishReason };
      }

      currentMessages = [
        ...currentMessages,
        { role: 'assistant', content: res.text },
        {
          role: 'user',
          content:
            'Continue exactly from where you stopped. Do not repeat any previous text. Output only the continuation.',
        },
      ];
    }

    return { text: allText };
  }

  async generateOne(
    params: GenerateParams,
    hooks: {
      onDebaterDelta?: (who: 'A' | 'B', delta: string) => void;
      onMediatorDelta?: (delta: string) => void;
      onJudgeDelta?: (delta: string) => void;
      onTurnFinished?: (who: 'A' | 'B' | 'Mediator' | 'Judge', text: string) => Promise<void>;
    } = {},
    previousQuestions: string[] = [],
  ): Promise<{ accepted: boolean; sample?: DatasetSample; envelope: JudgeEnvelope; debateA: string; debateB: string }>{
    const maxTurns = Math.max(6, Math.min(30, Number(process.env.DATASET_MAX_TURNS || '12')));

    const transcriptA: string[] = [];
    const transcriptB: string[] = [];
    const mediatorNotes: string[] = [];

    let finalProposal = '';

    const buildContext = () => {
      const aLog = transcriptA.join('\n\n');
      const bLog = transcriptB.join('\n\n');
      const mLog = mediatorNotes.join('\n\n');
      return { aLog, bLog, mLog };
    };

    const tryExtractFinalProposal = (text: string): string => {
      if (!text.includes('CONSENSUS_CALL_JUDGE')) return '';
      const start = text.indexOf('FINAL_PROPOSAL');
      if (start === -1) {
        const markerPos = text.indexOf('CONSENSUS_CALL_JUDGE');
        const afterMarker = text.slice(markerPos + 'CONSENSUS_CALL_JUDGE'.length).trim();
        if (!afterMarker) return '';
        return ['FINAL_PROPOSAL', afterMarker, 'END_FINAL_PROPOSAL'].join('\n');
      }
      const end = text.indexOf('END_FINAL_PROPOSAL', start);
      if (end === -1) {
        return `${text.slice(start).trim()}\nEND_FINAL_PROPOSAL`;
      }
      return text.slice(start, end + 'END_FINAL_PROPOSAL'.length).trim();
    };

    // Minimum turns before allowing consensus: both debaters must speak at least once,
    // and at least MIN_DEBATE_TURNS total turns must have occurred.
    const MIN_DEBATE_TURNS = Math.max(4, Number(process.env.DATASET_MIN_DEBATE_TURNS || '4'));

    let nextSpeaker: 'A' | 'B' = 'A';
    let consensusRequestedBy: 'A' | 'B' | null = null; // tracks who requested consensus
    let pendingProposal = ''; // proposal awaiting confirmation from the other side

    for (let turn = 1; turn <= maxTurns; turn++) {
      console.log(`[Orchestrator] Turn ${turn}/${maxTurns} | Speaker: ${nextSpeaker}`);
      const { aLog, bLog, mLog } = buildContext();
      const bothHaveSpoken = transcriptA.length > 0 && transcriptB.length > 0;
      // consensus is only allowed after minimum turns AND both debaters have spoken
      const consensusAllowed = bothHaveSpoken && turn >= MIN_DEBATE_TURNS;

      const userPromptParts: string[] = [];
      userPromptParts.push(`Turn ${turn}/${maxTurns}`);
      if (mLog) {
        userPromptParts.push('MEDIATOR NOTES:');
        userPromptParts.push(mLog);
      }
      userPromptParts.push('A LOG:');
      userPromptParts.push(aLog || '(empty)');
      userPromptParts.push('B LOG:');
      userPromptParts.push(bLog || '(empty)');

      const isFirst = transcriptA.length === 0 && transcriptB.length === 0;

      // If the OTHER debater requested consensus, this turn is a confirmation turn
      if (consensusRequestedBy && consensusRequestedBy !== nextSpeaker) {
        userPromptParts.push('');
        userPromptParts.push('상대방이 합의를 요청했습니다. 아래는 상대방의 FINAL_PROPOSAL입니다:');
        userPromptParts.push(pendingProposal);
        userPromptParts.push('');
        userPromptParts.push('검토 후 동의하면 CONSENSUS_CALL_JUDGE + FINAL_PROPOSAL 블록(수정 가능)을 출력하라.');
        userPromptParts.push('동의하지 않으면 반박 사유를 제시하라. (CONSENSUS_CALL_JUDGE를 출력하지 마라.)');
      } else if (isFirst) {
        userPromptParts.push('초기 제안: 현실적인 4지선다 문제 1개를 제안하라.');
        userPromptParts.push('첫 턴에서는 CONSENSUS_CALL_JUDGE를 사용하지 마라. 반드시 상대의 검토를 거쳐야 한다.');
        // Inject diversity: tell debaters about previously generated questions
        if (previousQuestions.length > 0) {
          userPromptParts.push('');
          userPromptParts.push('⚠️ 중복 금지: 아래 문제들은 이미 생성되었다. 완전히 다른 새로운 주제/상황/시나리오로 문제를 만들어라:');
          previousQuestions.forEach((q, i) => {
            userPromptParts.push(`  ${i + 1}) ${q}`);
          });
          userPromptParts.push('위 문제들과 유사한 주제, 상황, 시나리오, 조작 대상을 절대 사용하지 마라.');
        }
      } else if (!consensusAllowed) {
        userPromptParts.push('기존 로그를 바탕으로 문제를 개선하거나 반박하라.');
        userPromptParts.push(`아직 충분한 토론이 이루어지지 않았습니다 (최소 ${MIN_DEBATE_TURNS}턴 필요). CONSENSUS_CALL_JUDGE를 사용하지 마라.`);
      } else {
        userPromptParts.push('기존 로그를 바탕으로 문제를 개선하거나 반박하라.');
        userPromptParts.push('합의가 가능하면 CONSENSUS_CALL_JUDGE + FINAL_PROPOSAL 블록을 출력하라.');
      }

      // Scale token budget based on difficulty
      const debaterMaxTokens = (params.difficulty === 'expert' || params.difficulty === 'hard') ? 2400 : 1600;
      const debaterMaxContinuations = (params.difficulty === 'expert' || params.difficulty === 'hard') ? 4 : 3;

      if (nextSpeaker === 'A') {
        console.log('[Orchestrator] Starting A turn');
        const aTurn = await this.streamWithContinuation({
          model: params.models.debaterA,
          messages: [
            { role: 'system', content: debaterSystemPrompt('A', params.domain, params.difficulty) },
            { role: 'user', content: userPromptParts.join('\n') },
          ],
          temperature: 0.7,
          max_tokens: debaterMaxTokens,
          maxContinuations: debaterMaxContinuations,
          onDelta: (d) => hooks.onDebaterDelta?.('A', d),
        });
        console.log('[Orchestrator] A turn finished');
        transcriptA.push(aTurn.text);

        const extracted = tryExtractFinalProposal(aTurn.text);
        if (extracted && consensusAllowed) {
          if (consensusRequestedBy && consensusRequestedBy !== 'A') {
            // A is confirming B's proposal → real consensus achieved
            finalProposal = extracted;
            console.log('[Orchestrator] A confirmed consensus (proposed by B)');
          } else if (!consensusRequestedBy) {
            // A requests consensus → B must confirm next
            consensusRequestedBy = 'A';
            pendingProposal = extracted;
            console.log('[Orchestrator] A requested consensus, waiting for B confirmation');
          }
        } else if (extracted && !consensusAllowed) {
          console.log(`[Orchestrator] A tried CONSENSUS_CALL_JUDGE too early (turn ${turn}/${MIN_DEBATE_TURNS}), ignoring`);
        }
        // If this was a confirmation turn but A did NOT agree, reset consensus
        if (consensusRequestedBy === 'B' && !extracted) {
          console.log('[Orchestrator] A rejected B\'s consensus proposal, continuing debate');
          consensusRequestedBy = null;
          pendingProposal = '';
        }

        await hooks.onTurnFinished?.('A', aTurn.text);
        nextSpeaker = 'B';
      } else {
        console.log('[Orchestrator] Starting B turn');
        const bTurn = await this.streamWithContinuation({
          model: params.models.debaterB,
          messages: [
            { role: 'system', content: debaterSystemPrompt('B', params.domain, params.difficulty) },
            { role: 'user', content: userPromptParts.join('\n') },
          ],
          temperature: 0.7,
          max_tokens: debaterMaxTokens,
          maxContinuations: debaterMaxContinuations,
          onDelta: (d) => hooks.onDebaterDelta?.('B', d),
        });
        console.log('[Orchestrator] B turn finished');
        transcriptB.push(bTurn.text);

        const extracted = tryExtractFinalProposal(bTurn.text);
        if (extracted && consensusAllowed) {
          if (consensusRequestedBy && consensusRequestedBy !== 'B') {
            // B is confirming A's proposal → real consensus achieved
            finalProposal = extracted;
            console.log('[Orchestrator] B confirmed consensus (proposed by A)');
          } else if (!consensusRequestedBy) {
            // B requests consensus → A must confirm next
            consensusRequestedBy = 'B';
            pendingProposal = extracted;
            console.log('[Orchestrator] B requested consensus, waiting for A confirmation');
          }
        } else if (extracted && !consensusAllowed) {
          console.log(`[Orchestrator] B tried CONSENSUS_CALL_JUDGE too early (turn ${turn}/${MIN_DEBATE_TURNS}), ignoring`);
        }
        // If this was a confirmation turn but B did NOT agree, reset consensus
        if (consensusRequestedBy === 'A' && !extracted) {
          console.log('[Orchestrator] B rejected A\'s consensus proposal, continuing debate');
          consensusRequestedBy = null;
          pendingProposal = '';
        }

        await hooks.onTurnFinished?.('B', bTurn.text);
        nextSpeaker = 'A';
      }

      if (finalProposal) {
        console.log('[Orchestrator] Both debaters agreed on consensus, ending debate');
        break;
      }

      if (turn % 3 === 0) {
        console.log('[Orchestrator] Starting mediator (turn=', turn, ')');
        const { aLog: a2, bLog: b2, mLog: m2 } = buildContext();
        // Scale mediator budget: mediator must analyze full transcript + give detailed 13-field instructions
        const mediatorMaxTokens = (params.difficulty === 'expert' || params.difficulty === 'hard') ? 4096 : 3200;
        const mediatorMaxCont = (params.difficulty === 'expert' || params.difficulty === 'hard') ? 5 : 4;
        const mediator = await this.streamWithContinuation({
          model: params.models.mediator,
          messages: [
            { role: 'system', content: mediatorSystemPrompt(params.domain, params.difficulty) },
            {
              role: 'user',
              content: [
                '지금까지 토론을 중재하라.',
                '출력은 텍스트로만 작성하라.',
                'A/B가 다음 턴에서 FINAL_PROPOSAL 합의에 도달하도록 구체적 지시를 포함하라.',
                '',
                '아래 13개 필수 필드가 모두 토론에서 다뤄지고 있는지 확인하라:',
                '1) environment (환경 컨텍스트 전체: OS/앱/활성창/IME/네트워크/권한/prior_actions)',
                '2) scenario (시나리오 3~6문장)',
                '3) question (문제)',
                '4) choices (선택지 4개)',
                '5) answer (정답)',
                '6) reasoning_trace (추론 과정, 난이도별 단계 수)',
                '7) explanation (해설 4~10문장)',
                '8) distractor_analysis (오답 분석 3개 + 함정유형 + common_frequency)',
                '9) tags (태그 3개 이상)',
                '10) learning_objective (학습 목표)',
                '11) prerequisite_knowledge (선행 지식)',
                '12) related_topics (관련 주제)',
                '13) 난이도 메타 (cognitive_load, real_world_frequency, risk_if_wrong, time_pressure)',
                '',
                '추가 확인: common_mistakes, recovery_options, action_sequence(해당 시)',
                '누락된 필드가 있다면 어떤 필드인지 명시하고 다음 턴에서 보완하도록 지시하라.',
                '',
                'A LOG:',
                a2 || '(empty)',
                '',
                'B LOG:',
                b2 || '(empty)',
                '',
                'MEDIATOR NOTES SO FAR:',
                m2 || '(none)',
              ].join('\n'),
            },
          ],
          temperature: 0.2,
          max_tokens: mediatorMaxTokens,
          maxContinuations: mediatorMaxCont,
          onDelta: (d) => hooks.onMediatorDelta?.(d),
        });
        console.log('[Orchestrator] Mediator finished');
        mediatorNotes.push(mediator.text);
        console.log(`[Orchestrator] Mediator turn done (turn=${turn}).`);
        await hooks.onTurnFinished?.('Mediator', mediator.text);
      }
    }

    let debateACombined = transcriptA.join('\n\n');
    let debateBCombined = transcriptB.join('\n\n');
    const mediatorNotesCombined = mediatorNotes.join('\n\n');

    const MAX_REVISION_ATTEMPTS = Number(process.env.DATASET_MAX_REVISIONS || '3');
    let revisionAttempt = 0;
    let envelope: JudgeEnvelope;

    // ══════════════════════════════════════════════════════════════
    // Judge evaluation loop — with revision retries on REJECT
    // ══════════════════════════════════════════════════════════════
    judgeLoop: while (true) {

    console.log('[Orchestrator] Starting judge' + (revisionAttempt > 0 ? ` (revision ${revisionAttempt}/${MAX_REVISION_ATTEMPTS})` : ''));
    const judge = await this.streamWithContinuation({
      model: params.models.judge,
      messages: [
        { role: 'system', content: judgeSystemPrompt(params.domain, params.difficulty) },
        {
          role: 'user',
          content: judgeUserPromptWithContext({
            debateA: debateACombined,
            debateB: debateBCombined,
            finalProposal: finalProposal || undefined,
            mediatorNotes: mediatorNotesCombined || undefined,
          }),
        },
      ],
      temperature: 0.2,
      // configurable judge token budget (raise if models permit)
      max_tokens: Number(process.env.JUDGE_MAX_TOKENS || '8000'), // increased default token budget (do NOT shorten prompts)
      maxContinuations: Number(process.env.JUDGE_MAX_CONTINUATIONS || '5'),
      onDelta: (d) => hooks.onJudgeDelta?.(d),
    });
    console.log('[Orchestrator] Judge finished (finishReason=' + (judge.finishReason || 'none') + ')');
    await hooks.onTurnFinished?.('Judge', judge.text);

    // use a mutable string — we may force a non-stream regeneration if the stream was truncated
    let judgeText = judge.text.trim();

    // If the stream ended because of length OR the extracted JSON looks incomplete,
    // immediately retry a non-streamed judge call with a larger token budget. This
    // prevents relying on post‑hoc salvage for truncated outputs (root-cause fix).
    try {
      const extracted = this.extractFirstJsonObject(judgeText || '');
      const looksIncomplete = !extracted || extracted.trim().slice(-1) !== '}';
      if (judge.finishReason === 'length' || looksIncomplete) {
        console.warn('[Orchestrator] judge stream looks truncated — performing forced non-stream regeneration');
        try {
          // write truncation diagnostic (separate log) so we can alert/monitor frequency
          try {
            const truncPath = require('path').join(process.env.DATASET_OUT_DIR || 'datasets', 'judge_truncation.log');
            const info = JSON.stringify({ ts: new Date().toISOString(), finishReason: judge.finishReason || null, len: judgeText.length }) + '\n';
            require('fs').appendFileSync(truncPath, info, 'utf8');
          } catch (logErr) {
            /* best-effort */
          }

          const regen = await this.llm.chatOnce({
            model: params.models.judge,
            messages: [
              { role: 'system', content: judgeSystemPrompt(params.domain, params.difficulty) },
              {
                role: 'user',
                content:
                  'IMPORTANT: Output ONLY a single, compact, valid JSON object that exactly matches the schema. ' +
                  'Do NOT include any explanations, markdown, or extra text. Keep `explanation` to 1–2 short sentences.\n\n' +
                  judgeUserPromptWithContext({
                    debateA: debateACombined,
                    debateB: debateBCombined,
                    finalProposal: finalProposal || undefined,
                    mediatorNotes: mediatorNotesCombined || undefined,
                  }),
              },
            ],
            temperature: 0.0,
            max_tokens: Number(process.env.JUDGE_REGEN_MAX_TOKENS || '8000'), // larger regen budget to avoid truncation
          });
          judgeText = (this.extractFirstJsonObject(regen.text) || regen.text).trim();
          console.log('[Orchestrator] forced regeneration returned', judgeText.length, 'chars');
        } catch (e) {
          console.warn('[Orchestrator] forced regeneration failed:', (e as any)?.message || e);
          // fall through to diagnostic/salvage paths
        }
      }
    } catch (e) {
      console.warn('[Orchestrator] pre-parse truncation check failed:', (e as any)?.message || e);
    }

    // Diagnostic logging for malformed/partial judge outputs
    try {
      const diagPath = require('path').join(process.env.DATASET_OUT_DIR || 'datasets', 'judge_diagnostics.log');
      const snippet = judgeText.slice(0, 800).replace(/\n/g, ' ');
      const line = JSON.stringify({ ts: new Date().toISOString(), finishReason: judge.finishReason || null, len: judgeText.length, snippet }) + '\n';
      require('fs').appendFileSync(diagPath, line, 'utf8');
    } catch (e) {
      console.warn('Failed to write judge diagnostics log', (e as any)?.message || e);
    }

    try {
      envelope = JSON.parse(judgeText);
    } catch {
      // First attempt: repair using the repairJudgeJson helper (LLM-based + extraction)
      const repaired = await this.repairJudgeJson(params, judgeText);
      if (repaired) {
        envelope = repaired;
      } else {
        // Second attempt: ask the judge model to re-evaluate the debates and produce the JSON again
        try {
          console.log('[Orchestrator] judge JSON invalid - attempting regeneration via judge model');
          const regen = await this.llm.chatOnce({
            model: params.models.judge,
            messages: [
              { role: 'system', content: judgeSystemPrompt(params.domain, params.difficulty) },
              {
                role: 'user',
                content: judgeUserPromptWithContext({
                  debateA: debateACombined,
                  debateB: debateBCombined,
                  finalProposal: finalProposal || undefined,
                  mediatorNotes: mediatorNotesCombined || undefined,
                }),
              },
            ],
            temperature: 0.0,
            max_tokens: 1600,
          });
          const extracted = this.extractFirstJsonObject(regen.text || '');
          const candidate = extracted ? extracted : regen.text;
          envelope = JSON.parse(candidate.trim()) as JudgeEnvelope;
          console.log('[Orchestrator] judge regeneration succeeded');
        } catch (regenErr) {
          console.warn('[Orchestrator] judge regeneration failed:', (regenErr as any)?.message || regenErr);

          // Defensive salvage attempt BEFORE persisting as `judge_invalid_json`.
          try {
            const salvaged = salvageMalformedJudgeRaw(judgeText || '');
            if (salvaged && salvaged.verdict === 'PASS' && salvaged.sample) {
              // coerce score
              const scoreVal = typeof salvaged.score === 'number' ? salvaged.score : Number(salvaged.score);
                if (!Number.isNaN(scoreVal) && scoreVal >= 0.90) {
                // build DatasetSample same as normal acceptance flow
                const id = crypto.randomUUID();
                const sample = {
                  id,
                  domain: salvaged.sample.domain,
                  difficulty: salvaged.sample.difficulty,
                  question_type: 'mcq_single',
                  question: salvaged.sample.question,
                  choices: salvaged.sample.choices,
                  answer: salvaged.sample.answer,
                  explanation: salvaged.sample.explanation || '',
                  tags: salvaged.sample.tags ?? [],
                  source: {
                    method: 'discord_debate',
                    models: { debater_a: params.models.debaterA, debater_b: params.models.debaterB, judge: params.models.judge },
                    created_at: params.createdAtIso,
                    discord: params.discord,
                  },
                  quality: { judge_score: scoreVal, checks: { judge_pass: true } },
                } as any;

                const parsed = DatasetSampleSchema.safeParse(sample);
                if (parsed.success) {
                  await this.storage.appendAccepted(sample as any);
                  envelope = { verdict: 'PASS', score: scoreVal, reasons: salvaged.reasons || [], sample: salvaged.sample } as any;
                  return { accepted: true, sample, envelope, debateA: debateACombined, debateB: debateBCombined };
                }
              }
            }
          } catch (salvageErr) {
            console.warn('[Orchestrator] salvage-before-reject failed:', (salvageErr as any)?.message || salvageErr);
          }

          // final fallback: persist as invalid JSON (unchanged behavior)
          envelope = { verdict: 'REJECT', score: 0, reasons: ['judge_invalid_json'] };
          await this.storage.appendRejected({
            type: 'judge_invalid_json',
            raw: judgeText,
            domain: params.domain,
            difficulty: params.difficulty,
          });
          return { accepted: false, envelope, debateA: debateACombined, debateB: debateBCombined };
        }
      }
    }

    // ── Normalize score FIRST (before verdict check) ──
    // Judges sometimes return score as string (e.g. "0.92") — coerce to number
    if (typeof envelope.score !== 'number') {
      const coerced = Number((envelope as any).score);
      if (!Number.isNaN(coerced)) {
        console.log('[Orchestrator] Coercing judge score from', typeof (envelope as any).score, 'to number:', coerced);
        (envelope as any).score = coerced;
      }
    }

    // ── Score inflation detection ──
    // If ALL dimension_scores are exactly 1.0, the judge is rubber-stamping.
    // Apply automatic penalty to enforce realistic scoring.
    if (envelope.dimension_scores) {
      const dims = envelope.dimension_scores as Record<string, number>;
      const dimValues = Object.values(dims).filter(v => typeof v === 'number');
      const perfectCount = dimValues.filter(v => v >= 1.0).length;
      const allPerfect = dimValues.length >= 5 && dimValues.every(v => v >= 1.0);
      const nearPerfect = dimValues.length >= 5 && perfectCount >= 5;

      if (allPerfect) {
        console.log(`[Orchestrator] ⚠️ Score inflation detected: ALL ${dimValues.length} dimensions are 1.0 — applying penalty`);
        // Reduce each dimension by a realistic penalty
        const penalties: Record<string, number> = {
          single_answer: 0.05,
          realism: 0.12,
          reasoning_depth: 0.10,
          distractor_quality: 0.13,
          safety_ethics: 0.02,
          format_completeness: 0.03,
        };
        for (const [key, penalty] of Object.entries(penalties)) {
          if (dims[key] !== undefined) {
            dims[key] = Math.round((dims[key] - penalty) * 100) / 100;
          }
        }
        // Recalculate weighted score
        const weights: Record<string, number> = {
          single_answer: 0.30,
          realism: 0.20,
          reasoning_depth: 0.15,
          distractor_quality: 0.15,
          safety_ethics: 0.10,
          format_completeness: 0.10,
        };
        let newScore = 0;
        for (const [key, w] of Object.entries(weights)) {
          newScore += (dims[key] ?? 0.8) * w;
        }
        envelope.score = Math.round(newScore * 100) / 100;
        console.log(`[Orchestrator] Adjusted score: ${envelope.score} (was 1.0), dimensions:`, JSON.stringify(dims));
      } else if (nearPerfect && perfectCount > 3) {
        // Mild penalty: too many perfect dimensions
        const penalty = (perfectCount - 3) * 0.02;
        envelope.score = Math.round(((envelope.score as number) - penalty) * 100) / 100;
        console.log(`[Orchestrator] ⚠️ Near-perfect inflation: ${perfectCount}/${dimValues.length} dims are 1.0, penalty -${penalty}, new score: ${envelope.score}`);
      }
    }

    // ── Score-first acceptance: score is the quantitative signal, verdict is derivative ──
    // If score >= 0.82, force PASS regardless of what the judge said.
    const hasValidScore = typeof envelope.score === 'number' && envelope.score >= 0.82;

    console.log(`[Orchestrator] Judge result: verdict=${envelope.verdict}, score=${envelope.score}, hasSample=${!!envelope.sample}`);

    // Score >= threshold → force PASS
    if (hasValidScore && envelope.verdict !== 'PASS') {
      console.log(`[Orchestrator] Score ${envelope.score} >= 0.82 → forcing verdict to PASS`);
      envelope.verdict = 'PASS';
    }

    // If score >= threshold but sample is missing, regenerate up to 2 times.
    if (hasValidScore && !envelope.sample) {
      console.log(`[Orchestrator] High score but no sample — regenerating...`);
      for (let regenAttempt = 0; regenAttempt < 2 && !envelope.sample; regenAttempt++) {
        try {
          const regenWithSample = await this.llm.chatOnce({
            model: params.models.judge,
            messages: [
              { role: 'system', content: judgeSystemPrompt(params.domain, params.difficulty) },
              {
                role: 'user',
                content:
                  'CRITICAL: 이전 출력에서 sample JSON이 누락되었다.\n' +
                  '반드시 완전한 sample JSON 객체를 포함한 전체 판정 JSON을 다시 출력하라.\n' +
                  '현실적인 점수를 유지하라. 모든 차원 1.0은 금지.\n' +
                  'JSON만 출력. 마크다운 금지.\n\n' +
                  judgeUserPromptWithContext({
                    debateA: debateACombined,
                    debateB: debateBCombined,
                    finalProposal: finalProposal || undefined,
                    mediatorNotes: mediatorNotesCombined || undefined,
                  }),
              },
            ],
            temperature: 0.0,
            max_tokens: Number(process.env.JUDGE_REGEN_MAX_TOKENS || '8000'),
          });
          const regenExtracted = this.extractFirstJsonObject(regenWithSample.text || '');
          const regenCandidate = regenExtracted ? regenExtracted : regenWithSample.text;
          const regenEnvelope = JSON.parse(regenCandidate.trim()) as JudgeEnvelope;
          if (regenEnvelope.sample) {
            console.log(`[Orchestrator] Regen attempt ${regenAttempt + 1} succeeded — got sample`);
            envelope.sample = regenEnvelope.sample;
            envelope.verdict = 'PASS';
          } else {
            console.warn(`[Orchestrator] Regen attempt ${regenAttempt + 1} — still no sample`);
          }
        } catch (e) {
          console.warn(`[Orchestrator] Regen attempt ${regenAttempt + 1} failed:`, (e as any)?.message || e);
        }
      }
    }

    // ── Reject: low score — attempt revision if retries remain ──
    if (typeof envelope.score !== 'number' || envelope.score < 0.82) {
      console.log(`[Orchestrator] REJECTED: low_score=${envelope.score}`);
      envelope.reasons = ['[REJECT_REASON] 점수 미달: ' + envelope.score, ...(envelope.reasons || [])];
      await this.storage.appendRejected({
        type: 'low_score',
        envelope,
        rejectedScore: { value: (envelope as any).score, typeof: typeof (envelope as any).score },
        domain: params.domain,
        difficulty: params.difficulty,
      });

      // ── Revision retry: send judge feedback to debaters for revision ──
      if (revisionAttempt < MAX_REVISION_ATTEMPTS) {
        revisionAttempt++;
        console.log(`[Orchestrator] === Revision Round ${revisionAttempt}/${MAX_REVISION_ATTEMPTS} ===`);

        // Notify via Discord hook
        await hooks.onTurnFinished?.('Judge',
          `🔄 REJECT — 수정 요청 (${revisionAttempt}/${MAX_REVISION_ATTEMPTS})\n` +
          `점수: ${envelope.score}\n` +
          `피드백: ${(envelope.reasons || []).join(', ')}`
        );

        const dimScores = (envelope.dimension_scores ?? {}) as Record<string, number>;

        // Step 1: Ask Debater A to revise based on judge feedback
        console.log(`[Orchestrator] Revision ${revisionAttempt} — asking Debater A to revise`);
        const revisionPromptA = revisionDebaterPrompt({
          kind: 'A',
          revisionAttempt,
          maxRevisions: MAX_REVISION_ATTEMPTS,
          judgeReasons: envelope.reasons || [],
          judgeScore: envelope.score ?? 0,
          dimensionScores: dimScores,
          previousProposal: finalProposal || '(합의안 없음)',
        });

        const debaterMaxTokens = (params.difficulty === 'expert' || params.difficulty === 'hard') ? 2400 : 1600;
        const debaterMaxCont = (params.difficulty === 'expert' || params.difficulty === 'hard') ? 4 : 3;

        const revA = await this.streamWithContinuation({
          model: params.models.debaterA,
          messages: [
            { role: 'system', content: debaterSystemPrompt('A', params.domain, params.difficulty) },
            { role: 'user', content: revisionPromptA },
          ],
          temperature: 0.7,
          max_tokens: debaterMaxTokens,
          maxContinuations: debaterMaxCont,
          onDelta: (d) => hooks.onDebaterDelta?.('A', d),
        });
        console.log(`[Orchestrator] Revision ${revisionAttempt} — Debater A finished`);
        await hooks.onTurnFinished?.('A', revA.text);

        // Step 2: Ask Debater B to review A's revision
        console.log(`[Orchestrator] Revision ${revisionAttempt} — asking Debater B to review`);
        const revisionPromptB = revisionDebaterPrompt({
          kind: 'B',
          revisionAttempt,
          maxRevisions: MAX_REVISION_ATTEMPTS,
          judgeReasons: envelope.reasons || [],
          judgeScore: envelope.score ?? 0,
          dimensionScores: dimScores,
          previousProposal: finalProposal || '(합의안 없음)',
          otherDebaterRevision: revA.text,
        });

        const revB = await this.streamWithContinuation({
          model: params.models.debaterB,
          messages: [
            { role: 'system', content: debaterSystemPrompt('B', params.domain, params.difficulty) },
            { role: 'user', content: revisionPromptB },
          ],
          temperature: 0.7,
          max_tokens: debaterMaxTokens,
          maxContinuations: debaterMaxCont,
          onDelta: (d) => hooks.onDebaterDelta?.('B', d),
        });
        console.log(`[Orchestrator] Revision ${revisionAttempt} — Debater B finished`);
        await hooks.onTurnFinished?.('B', revB.text);

        // Extract revised FINAL_PROPOSAL
        const newProposalB = tryExtractFinalProposal(revB.text);
        const newProposalA = tryExtractFinalProposal(revA.text);
        const newProposal = newProposalB || newProposalA;
        if (newProposal) {
          finalProposal = newProposal;
          console.log(`[Orchestrator] Revision ${revisionAttempt} — new FINAL_PROPOSAL extracted`);
        } else {
          console.log(`[Orchestrator] Revision ${revisionAttempt} — no new FINAL_PROPOSAL, using debater outputs as context`);
        }

        // Append revision logs to combined debate
        debateACombined += `\n\n[REVISION ${revisionAttempt}]\n${revA.text}`;
        debateBCombined += `\n\n[REVISION ${revisionAttempt}]\n${revB.text}`;

        // Continue to re-judge
        continue judgeLoop;
      }

      // No more revision attempts — final reject
      return { accepted: false, envelope, debateA: debateACombined, debateB: debateBCombined };
    }

    // ── Reject: missing sample even after regen ──
    if (!envelope.sample) {
      console.log(`[Orchestrator] REJECTED: sample missing after ${hasValidScore ? '2 regen attempts' : 'no regen'}`);
      envelope.reasons = ['[REJECT_REASON] sample 누락 (judge가 sample JSON을 생성하지 않음)', ...(envelope.reasons || [])];
      await this.storage.appendRejected({
        type: 'sample_missing',
        envelope,
        domain: params.domain,
        difficulty: params.difficulty,
      });
      return { accepted: false, envelope, debateA: debateACombined, debateB: debateBCombined };
    }

    // ── Accepted — break out of judgeLoop ──
    break;
    } // end judgeLoop

    const id = crypto.randomUUID();

    const sample: DatasetSample = {
      id,
      domain: envelope.sample.domain,
      difficulty: envelope.sample.difficulty,
      question_type: (envelope.sample.question_type ?? 'mcq_single') as QuestionType,
      environment: envelope.sample.environment ?? undefined,
      question: envelope.sample.question,
      scenario: envelope.sample.scenario ?? undefined,
      choices: envelope.sample.choices,
      answer: envelope.sample.answer,
      explanation: envelope.sample.explanation,
      reasoning_trace: envelope.sample.reasoning_trace ?? undefined,
      action_sequence: envelope.sample.action_sequence ?? undefined,
      distractor_analysis: envelope.sample.distractor_analysis ?? undefined,
      tags: envelope.sample.tags ?? [],
      learning_objective: envelope.sample.learning_objective ?? undefined,
      prerequisite_knowledge: envelope.sample.prerequisite_knowledge ?? [],
      related_topics: envelope.sample.related_topics ?? [],
      // v3 enriched fields
      cognitive_load: envelope.sample.cognitive_load ?? undefined,
      real_world_frequency: envelope.sample.real_world_frequency ?? undefined,
      risk_if_wrong: envelope.sample.risk_if_wrong ?? undefined,
      time_pressure: envelope.sample.time_pressure ?? undefined,
      common_mistakes: envelope.sample.common_mistakes ?? undefined,
      recovery_options: envelope.sample.recovery_options ?? undefined,
      os_version_constraints: envelope.sample.os_version_constraints ?? undefined,
      source: {
        method: 'discord_debate',
        models: {
          debater_a: params.models.debaterA,
          debater_b: params.models.debaterB,
          judge: params.models.judge,
        },
        created_at: params.createdAtIso,
        version: '3.0',
        discord: params.discord,
      },
      quality: {
        judge_score: envelope.score,
        reasoning_depth_score: envelope.dimension_scores?.reasoning_depth ?? undefined,
        distractor_quality_score: envelope.dimension_scores?.distractor_quality ?? undefined,
        practical_relevance_score: envelope.dimension_scores?.realism ?? undefined,
        checks: {
          judge_pass: true,
        },
      },
    };

    // ── Sanitize ime_state: LLM outputs free text like "한글 (한국어 입력 모드)" instead of enum ──
    if (sample.environment?.ime_state) {
      const raw = (sample.environment.ime_state as string).toLowerCase();
      if (!['korean', 'english', 'unknown'].includes(raw)) {
        const koreanPatterns = /한글|korean|hangul|한국어|kor|ko/i;
        const englishPatterns = /영어|english|eng|영문|en\b/i;
        if (koreanPatterns.test(raw)) {
          console.log(`[Orchestrator] ime_state sanitized: "${sample.environment.ime_state}" → "korean"`);
          (sample.environment as any).ime_state = 'korean';
        } else if (englishPatterns.test(raw)) {
          console.log(`[Orchestrator] ime_state sanitized: "${sample.environment.ime_state}" → "english"`);
          (sample.environment as any).ime_state = 'english';
        } else {
          console.log(`[Orchestrator] ime_state sanitized: "${sample.environment.ime_state}" → "unknown"`);
          (sample.environment as any).ime_state = 'unknown';
        }
      }
    }

    // ── Sanitize trap_type: LLM sometimes outputs compound values like "wrong_order & common_mistake" ──
    const VALID_TRAP_TYPES = new Set([
      'common_mistake', 'partial_solution', 'dangerous_action',
      'outdated_method', 'wrong_order', 'missing_prerequisite',
      'environment_dependent', 'social_engineering',
      'unreliable_method', 'inefficient_workflow', 'incomplete_action',
      'overcomplicated', 'conceptual_error', 'scope_mismatch',
    ]);
    if (sample.distractor_analysis) {
      for (const da of sample.distractor_analysis) {
        if (da.trap_type && !VALID_TRAP_TYPES.has(da.trap_type)) {
          // Try to extract the first valid trap_type from compound like "wrong_order & common_mistake"
          const parts = da.trap_type.split(/\s*[&|,/+]\s*/);
          const found = parts.find((p: string) => VALID_TRAP_TYPES.has(p.trim()));
          if (found) {
            console.log(`[Orchestrator] trap_type sanitized: "${da.trap_type}" → "${found.trim()}"`);
            (da as any).trap_type = found.trim();
          } else {
            // Fallback: map to closest match or default
            console.log(`[Orchestrator] trap_type unknown: "${da.trap_type}" → defaulting to "common_mistake"`);
            (da as any).trap_type = 'common_mistake';
          }
        }
      }
    }

    const parsed = DatasetSampleSchema.safeParse(sample);
    if (!parsed.success) {
      const schemaErrors = parsed.error.errors.map(e => `${e.path.join('.')}: ${e.message}`).join('; ');
      console.log(`[Orchestrator] REJECTED: schema_invalid: ${schemaErrors}`);
      envelope.reasons = [`[REJECT_REASON] 스키마 검증 실패: ${schemaErrors}`, ...(envelope.reasons || [])];
      await this.storage.appendRejected({ type: 'schema_invalid', errors: parsed.error.errors, sample });
      return { accepted: false, envelope, debateA: debateACombined, debateB: debateBCombined };
    }

    const single = validateSingleCorrect(sample);
    if (!single.ok) {
      console.log(`[Orchestrator] REJECTED: validation_failed: ${single.reason}`);
      envelope.reasons = [`[REJECT_REASON] 검증 실패: ${single.reason}`, ...(envelope.reasons || [])];
      await this.storage.appendRejected({ type: 'validation_failed', reason: single.reason, sample });
      return { accepted: false, envelope, debateA: debateACombined, debateB: debateBCombined };
    }

    const hash = this.storage.computeHash(sample);
    if (this.storage.isDuplicate(hash)) {
      console.log(`[Orchestrator] REJECTED: duplicate`);
      envelope.reasons = [`[REJECT_REASON] 중복: 이미 생성된 동일 문제`, ...(envelope.reasons || [])];
      await this.storage.appendRejected({ type: 'duplicate', hash, sample });
      return { accepted: false, envelope, debateA: debateACombined, debateB: debateBCombined };
    }

    console.log(`[Orchestrator] ACCEPTED: score=${envelope.score}, id=${sample.id}`);
    await this.storage.appendAccepted(sample);
    return { accepted: true, sample, envelope, debateA: debateACombined, debateB: debateBCombined };
  }
}
