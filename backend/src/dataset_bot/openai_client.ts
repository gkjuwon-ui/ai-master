export type ChatRole = 'system' | 'user' | 'assistant';
export interface ChatMessage {
  role: ChatRole;
  content: string;
}

export interface OpenAIClientOptions {
  apiKey: string;
  baseUrl?: string;
}

type StreamDeltaHandler = (deltaText: string) => void;

async function getFetch(): Promise<typeof fetch> {
  const f = (globalThis as any).fetch;
  if (typeof f === 'function') return f as typeof fetch;
  // @ts-ignore
  const mod: any = await import('node-fetch');
  return (mod.default || mod) as typeof fetch;
}

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function timeoutReject(ms: number, message: string): Promise<never> {
  return new Promise((_, reject) => {
    setTimeout(() => reject(new Error(message)), ms);
  });
}

export class OpenAIClient {
  private apiKey: string;
  private baseUrl: string;

  constructor(opts: OpenAIClientOptions) {
    this.apiKey = opts.apiKey;
    this.baseUrl = (opts.baseUrl || 'https://api.openai.com').replace(/\/$/, '');
  }

  async chatStream(params: {
    model: string;
    messages: ChatMessage[];
    temperature?: number;
    max_tokens?: number;
    onDelta: StreamDeltaHandler;
  }): Promise<{ text: string; finishReason?: string }>{
    const url = `${this.baseUrl}/v1/chat/completions`;

    const fetchFn = await getFetch();

    const payload = {
      model: params.model,
      messages: params.messages,
      temperature: params.temperature ?? 0.2,
      max_tokens: params.max_tokens ?? 1200,
      stream: true,
    };

    const requestTimeoutMs = Math.max(15000, Number(process.env.OPENAI_REQUEST_TIMEOUT_MS || '120000'));
    const streamIdleTimeoutMs = Math.max(5000, Number(process.env.OPENAI_STREAM_IDLE_TIMEOUT_MS || '45000'));

    let resp: any;
    let lastErrText = '';
    const maxAttempts = 4;
    for (let attempt = 1; attempt <= maxAttempts; attempt++) {
      const controller = new AbortController();
      const reqTimer = setTimeout(() => controller.abort(), requestTimeoutMs);
      resp = await fetchFn(url, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${this.apiKey}`,
        },
        body: JSON.stringify(payload),
        signal: controller.signal,
      }).catch((e: any) => {
        throw new Error(`OpenAI network error: ${e?.message || String(e)}`);
      }).finally(() => {
        clearTimeout(reqTimer);
      });

      if (resp?.ok && resp.body) break;

      const status = resp?.status;
      lastErrText = await resp?.text?.().catch(() => '') ?? '';

      const retryable = status === 429 || (typeof status === 'number' && status >= 500);
      if (!retryable || attempt === maxAttempts) {
        throw new Error(`OpenAI stream failed: ${status} ${lastErrText}`);
      }

      const backoffMs = Math.min(8000, 500 * Math.pow(2, attempt - 1));
      await sleep(backoffMs);
    }

    const stream = resp.body;
    if (!stream) throw new Error('No response body');

    const reader = stream.getReader();
    const decoder = new TextDecoder('utf-8');

    let buffer = '';
    let fullText = '';
    let lastDeltaTime = Date.now();
    let finishReason: string | undefined;

    while (true) {
      const { done, value } = await Promise.race([
        reader.read(),
        timeoutReject(streamIdleTimeoutMs, `OpenAI stream idle timeout (${streamIdleTimeoutMs}ms)`),
      ]);
      if (done) break;

      buffer += decoder.decode(value, { stream: true });

      while (true) {
        const idx = buffer.indexOf('\n\n');
        if (idx === -1) break;
        const rawEvent = buffer.slice(0, idx);
        buffer = buffer.slice(idx + 2);

        const lines = rawEvent.split('\n').map((l) => l.trim());
        for (const line of lines) {
          if (!line.startsWith('data:')) continue;
          const data = line.slice('data:'.length).trim();
          if (!data) continue;
          if (data === '[DONE]') {
            console.log('[OpenAI] Received [DONE], ending stream.');
            return { text: fullText, finishReason };
          }
          try {
            const json = JSON.parse(data);
            const delta = json?.choices?.[0]?.delta?.content;
            const chunkFinishReason = json?.choices?.[0]?.finish_reason;
            if (typeof chunkFinishReason === 'string' && chunkFinishReason.length > 0) {
              finishReason = chunkFinishReason;
            }
            if (typeof delta === 'string' && delta.length) {
              fullText += delta;
              params.onDelta(delta);
              lastDeltaTime = Date.now();
            }
          } catch {
            // ignore malformed JSON
          }
        }
      }
    }

    reader.releaseLock();

    return { text: fullText, finishReason };
  }

  async chatOnce(params: {
    model: string;
    messages: ChatMessage[];
    temperature?: number;
    max_tokens?: number;
  }): Promise<{ text: string }>{
    const url = `${this.baseUrl}/v1/chat/completions`;
    const fetchFn = await getFetch();

    const payload = {
      model: params.model,
      messages: params.messages,
      temperature: params.temperature ?? 0.2,
      max_tokens: params.max_tokens ?? 1200,
      stream: false,
    };

    const requestTimeoutMs = Math.max(15000, Number(process.env.OPENAI_REQUEST_TIMEOUT_MS || '120000'));
    const maxAttempts = 4;
    let lastErrText = '';

    for (let attempt = 1; attempt <= maxAttempts; attempt++) {
      const controller = new AbortController();
      const reqTimer = setTimeout(() => controller.abort(), requestTimeoutMs);

      const resp: any = await fetchFn(url, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${this.apiKey}`,
        },
        body: JSON.stringify(payload),
        signal: controller.signal,
      }).catch((e: any) => {
        throw new Error(`OpenAI network error: ${e?.message || String(e)}`);
      }).finally(() => {
        clearTimeout(reqTimer);
      });

      if (!resp?.ok) {
        const status = resp?.status;
        lastErrText = await resp?.text?.().catch(() => '') ?? '';
        const retryable = status === 429 || (typeof status === 'number' && status >= 500);
        if (!retryable || attempt === maxAttempts) {
          throw new Error(`OpenAI chatOnce failed: ${status} ${lastErrText}`);
        }
        const backoffMs = Math.min(8000, 500 * Math.pow(2, attempt - 1));
        await sleep(backoffMs);
        continue;
      }

      const json = await resp.json().catch(() => null);
      const text = json?.choices?.[0]?.message?.content;
      if (typeof text !== 'string' || text.length === 0) {
        throw new Error('OpenAI chatOnce returned empty content');
      }
      return { text };
    }

    throw new Error(`OpenAI chatOnce failed: ${lastErrText}`);
  }
}
