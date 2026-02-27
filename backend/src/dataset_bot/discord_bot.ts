import {
  Client,
  GatewayIntentBits,
  Routes,
  ChatInputCommandInteraction,
  TextChannel,
  EmbedBuilder,
} from 'discord.js';

const { REST, SlashCommandBuilder } = require('discord.js') as any;

import { config } from '../config';
import { OpenAIClient } from './openai_client';
import { JsonlStorage } from './storage';
import { DatasetOrchestrator } from './orchestrator';
import { DatasetDomainSchema, DifficultySchema } from './schema';

/* ================================================================
   Discord Bot v2  Webhook-based Real Profile Messages
   
   Key changes from v1:
   - No more threads: all messages in main channel
   - Each bot role (Debater A, B, Mediator, Judge) has its own
     webhook with a distinct name and avatar
   - Messages split seamlessly without visible page numbers
   - Rich embeds for results (PASS/REJECT)
   ================================================================ */

// Webhook profiles for each role
const WEBHOOK_PROFILES: Record<string, { name: string; avatar: string }> = {
  A: {
    name: 'Debater A \u2694\uFE0F',
    avatar: 'https://cdn.discordapp.com/embed/avatars/0.png',
  },
  B: {
    name: 'Debater B \uD83D\uDD0D',
    avatar: 'https://cdn.discordapp.com/embed/avatars/1.png',
  },
  Mediator: {
    name: 'Mediator \u2696\uFE0F',
    avatar: 'https://cdn.discordapp.com/embed/avatars/2.png',
  },
  Judge: {
    name: 'Judge \uD83D\uDC51',
    avatar: 'https://cdn.discordapp.com/embed/avatars/4.png',
  },
  System: {
    name: 'Dataset Engine \u2699\uFE0F',
    avatar: 'https://cdn.discordapp.com/embed/avatars/3.png',
  },
};

function env(name: string): string {
  const v = process.env[name];
  if (!v) throw new Error(`Missing env: ${name}`);
  return v;
}

function nowIso(): string {
  return new Date().toISOString();
}

// Webhook management: create or reuse a channel webhook
const webhookCache = new Map<string, any>();

async function getOrCreateWebhook(channel: TextChannel, role: string): Promise<any> {
  const cacheKey = `${channel.id}_${role}`;
  if (webhookCache.has(cacheKey)) return webhookCache.get(cacheKey)!;

  const profile = WEBHOOK_PROFILES[role] ?? WEBHOOK_PROFILES['System'];
  const existingWebhooks = await channel.fetchWebhooks();
  let webhook = existingWebhooks.find((w) => w.name === profile.name && w.owner?.id === channel.client.user?.id);

  if (!webhook) {
    webhook = await channel.createWebhook({
      name: profile.name,
      avatar: profile.avatar,
      reason: `Dataset generation bot - ${role}`,
    });
  }

  webhookCache.set(cacheKey, webhook);
  return webhook;
}

// Send message via webhook with seamless splitting (no page numbers)
async function sendAsRole(channel: TextChannel, role: string, text: string): Promise<void> {
  const webhook = await getOrCreateWebhook(channel, role);
  const profile = WEBHOOK_PROFILES[role] ?? WEBHOOK_PROFILES['System'];
  const maxChunkSize = 1950;
  const normalized = text.replace(/\r\n/g, '\n');

  if (normalized.length <= maxChunkSize) {
    await webhook.send({
      content: normalized,
      username: profile.name,
      avatarURL: profile.avatar,
    });
    return;
  }

  // Split seamlessly  no page indicators
  const chunks: string[] = [];
  let cursor = 0;
  while (cursor < normalized.length) {
    const remaining = normalized.length - cursor;
    if (remaining <= maxChunkSize) {
      chunks.push(normalized.slice(cursor));
      break;
    }

    const window = normalized.slice(cursor, cursor + maxChunkSize);
    // Find best split point: paragraph break > line break > space
    let splitAt = window.lastIndexOf('\n\n');
    if (splitAt < Math.floor(maxChunkSize * 0.4)) {
      splitAt = window.lastIndexOf('\n');
    }
    if (splitAt < Math.floor(maxChunkSize * 0.3)) {
      // Fall back to space
      splitAt = window.lastIndexOf(' ');
    }
    if (splitAt < Math.floor(maxChunkSize * 0.3)) {
      splitAt = maxChunkSize;
    }

    const chunk = normalized.slice(cursor, cursor + splitAt).trimEnd();
    if (chunk.length > 0) {
      chunks.push(chunk);
    }
    cursor += splitAt;
    // Skip leading whitespace/newlines in next chunk
    while (cursor < normalized.length && normalized[cursor] === '\n') {
      cursor += 1;
    }
  }

  for (let i = 0; i < chunks.length; i++) {
    await webhook.send({
      content: chunks[i],
      username: profile.name,
      avatarURL: profile.avatar,
    });
    if (i < chunks.length - 1) {
      await new Promise((resolve) => setTimeout(resolve, 300));
    }
  }
}

// Send rich embed result
async function sendResult(channel: TextChannel, accepted: boolean, score: number, sampleId?: string, reasons?: string[]): Promise<void> {
  const webhook = await getOrCreateWebhook(channel, 'System');
  const profile = WEBHOOK_PROFILES['System'];

  const embed = (new EmbedBuilder() as any)
    .setTitle(accepted ? '\u2705 PASS' : '\u274C REJECT')
    .setColor(accepted ? 0x00ff00 : 0xff0000)
    .addFields(
      { name: 'Score', value: `${(score * 100).toFixed(1)}%`, inline: true },
      { name: 'Threshold', value: '90.0%', inline: true },
    )
    .setTimestamp();

  if (sampleId) {
    embed.addFields({ name: 'Sample ID', value: sampleId, inline: false });
  }
  if (reasons && reasons.length > 0) {
    // Show [REJECT_REASON] items first so the actual rejection cause is visible
    const rejectReasons = reasons.filter(r => r.startsWith('[REJECT_REASON]'));
    const judgeReasons = reasons.filter(r => !r.startsWith('[REJECT_REASON]'));
    const ordered = [...rejectReasons, ...judgeReasons];
    // Show up to 10 reasons (Discord field limit is 1024 chars)
    const text = ordered.slice(0, 10).join('\n').slice(0, 1024);
    embed.addFields({ name: 'Reasons', value: text, inline: false });
  }

  await webhook.send({
    embeds: [embed],
    username: profile.name,
    avatarURL: profile.avatar,
  });
}

export async function startDatasetBot() {
  const token = env('DISCORD_BOT_TOKEN');
  const clientId = env('DISCORD_CLIENT_ID');
  const guildId = process.env.DISCORD_GUILD_ID;
  const allowChannelId = process.env.DISCORD_CHANNEL_ID;

  const openaiKey = env('OPENAI_API_KEY');
  const openaiBaseUrl = process.env.OPENAI_BASE_URL || 'https://api.openai.com';

  // Mixed strategy: gpt-4o-mini (fast debaters) + gpt-4o (strong mediator & judge)
  const modelDebaterA = process.env.OPENAI_DEBATER_A_MODEL || 'gpt-4o-mini';
  const modelDebaterB = process.env.OPENAI_DEBATER_B_MODEL || 'gpt-4o-mini';
  const modelMediator = process.env.OPENAI_MEDIATOR_MODEL || 'gpt-4o';
  const modelJudge = process.env.OPENAI_JUDGE_MODEL || 'gpt-4o';

  const outDir = process.env.DATASET_OUT_DIR || 'datasets';

  const llm = new OpenAIClient({ apiKey: openaiKey, baseUrl: openaiBaseUrl });
  const storage = new JsonlStorage({ outDir });
  const orchestrator = new DatasetOrchestrator(llm, storage);

  const commands = [
    new SlashCommandBuilder()
      .setName('gen')
      .setDescription('Generate high-quality osen-1.0 training samples via debate pipeline')
      .addStringOption((o: any) =>
        o
          .setName('domain')
          .setDescription('Domain')
          .setRequired(true)
          .addChoices(
            { name: 'computer_ops', value: 'computer_ops' },
            { name: 'web_ops', value: 'web_ops' },
            { name: 'ethics', value: 'ethics' },
            { name: 'cross_app', value: 'cross_app' },
            { name: 'error_recovery', value: 'error_recovery' },
          ),
      )
      .addStringOption((o: any) =>
        o
          .setName('difficulty')
          .setDescription('Difficulty level')
          .setRequired(true)
          .addChoices(
            { name: 'easy', value: 'easy' },
            { name: 'medium', value: 'medium' },
            { name: 'hard', value: 'hard' },
            { name: 'expert', value: 'expert' },
          ),
      )
      .addIntegerOption((o: any) =>
        o.setName('count').setDescription('How many samples to attempt').setRequired(false).setMinValue(1).setMaxValue(10000),
      ),
    new SlashCommandBuilder()
      .setName('stats')
      .setDescription('Show dataset generation statistics'),
  ].map((c) => c.toJSON());

  const rest = new REST({ version: '10' }).setToken(token);
  if (guildId) {
    await rest.put(Routes.applicationGuildCommands(clientId, guildId), { body: commands });
  } else {
    await rest.put(Routes.applicationCommands(clientId), { body: commands });
  }

  const client = new Client({ intents: [GatewayIntentBits.Guilds] });

  client.on('interactionCreate', async (interaction) => {
    if (!interaction.isChatInputCommand()) return;

    const i = interaction as ChatInputCommandInteraction;

    // /stats command
    if (i.commandName === 'stats') {
      const stats = storage.getStats();
      const embed = (new EmbedBuilder() as any)
        .setTitle('\uD83D\uDCCA Dataset Generation Statistics')
        .setColor(0x3498db)
        .addFields(
          { name: 'Total Attempted', value: `${stats.total_attempted}`, inline: true },
          { name: 'Accepted', value: `${stats.total_accepted}`, inline: true },
          { name: 'Rejected', value: `${stats.total_rejected}`, inline: true },
          { name: 'Avg Score', value: `${(stats.avg_quality_score * 100).toFixed(1)}%`, inline: true },
          { name: 'Pass Rate', value: stats.total_attempted > 0 ? `${((stats.total_accepted / stats.total_attempted) * 100).toFixed(1)}%` : 'N/A', inline: true },
        )
        .setTimestamp();
      await i.reply({ embeds: [embed] });
      return;
    }

    if (i.commandName !== 'gen') return;

    if (allowChannelId && i.channelId !== allowChannelId) {
      await i.reply({ content: `This bot is restricted to channel ${allowChannelId}.`, ephemeral: true });
      return;
    }

    const domainRaw = i.options.getString('domain', true);
    const diffRaw = i.options.getString('difficulty', true);
    const count = i.options.getInteger('count') ?? 1;

    const domainParsed = DatasetDomainSchema.safeParse(domainRaw);
    const diffParsed = DifficultySchema.safeParse(diffRaw);

    if (!domainParsed.success || !diffParsed.success) {
      await i.reply({ content: 'Invalid domain/difficulty', ephemeral: true });
      return;
    }

    await i.deferReply({ ephemeral: false });

    const ch = i.channel;
    if (!ch || !(ch instanceof TextChannel)) {
      await i.editReply('This command must be used in a guild text channel.');
      return;
    }

    await i.editReply(`\u2699\uFE0F Generating ${count} accepted sample(s) | domain=\`${domainRaw}\` difficulty=\`${diffRaw}\`  messages will appear below.`);

    let acceptedCount = 0;
    let attemptCount = 0;
    const maxAttempts = count * 5; // Safety: max 5x attempts to prevent infinite loop
    const previousQuestions: string[] = []; // Track generated questions to prevent duplicates

    while (acceptedCount < count && attemptCount < maxAttempts) {
      attemptCount++;
      // Announce sample start via System webhook
      await sendAsRole(ch, 'System', `\u2500\u2500\u2500 Attempt ${attemptCount} | Accepted ${acceptedCount}/${count} | ${domainRaw} | ${diffRaw} \u2500\u2500\u2500`);

      try {
        console.log('[Discord] Starting orchestrator.generateOne');
        const res = await orchestrator.generateOne(
          {
            domain: domainParsed.data,
            difficulty: diffParsed.data,
            models: {
              debaterA: modelDebaterA,
              debaterB: modelDebaterB,
              mediator: modelMediator,
              judge: modelJudge,
            },
            createdAtIso: nowIso(),
            discord: {
              guild_id: i.guildId ?? undefined,
              channel_id: i.channelId,
              message_ids: [],
            },
          },
          {
            onDebaterDelta: () => {},
            onMediatorDelta: () => {},
            onJudgeDelta: () => {},
            onTurnFinished: async (who: 'A' | 'B' | 'Mediator' | 'Judge', text: string) => {
              console.log(`[Discord] Sending ${who} message (len=${text.length})`);
              await sendAsRole(ch, who, text);
            },
          },
          previousQuestions,
        );
        console.log('[Discord] orchestrator.generateOne finished');

        if (res.accepted) {
          acceptedCount++;
          // Track the question to prevent duplicates in subsequent iterations
          if (res.sample?.question) {
            previousQuestions.push(res.sample.question);
          }
        } else {
          // Even rejected questions should be tracked to avoid re-generating similar topics
          if (res.envelope?.sample?.question) {
            previousQuestions.push(res.envelope.sample.question);
          }
        }

        await sendResult(
          ch,
          res.accepted,
          res.envelope.score ?? 0,
          res.sample?.id,
          res.envelope.reasons,
        );
      } catch (e: any) {
        console.error('[Discord] orchestrator.generateOne threw:', e);
        await sendAsRole(ch, 'System', `\u274C ERROR: ${e?.message || String(e)}`);
      }
    }

    const summary = acceptedCount >= count
      ? `\u2705 Generation complete. ${acceptedCount}/${count} accepted samples collected (${attemptCount} attempts).`
      : `\u26A0\uFE0F Generation stopped. Only ${acceptedCount}/${count} accepted after ${attemptCount} attempts (max ${maxAttempts}). Try again or adjust difficulty.`;
    await sendAsRole(ch, 'System', summary);
  });

  client.once('ready', () => {
    console.log(`[dataset-bot] ready as ${client.user?.tag}. backend=${config.backendUrl}`);
  });

  await client.login(token);
}
