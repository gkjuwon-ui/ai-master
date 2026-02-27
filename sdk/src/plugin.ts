/**
 * Agent Plugin - Base class and context for building agent plugins.
 */

import {
  AgentManifestConfig,
  AgentCapability,
  AgentCategory,
  OSAction,
  LLMMessage,
  LLMResponse,
} from './types';

/**
 * Manifest for an agent plugin.
 */
export class AgentManifest {
  private config: Partial<AgentManifestConfig> = {};

  name(name: string): this { this.config.name = name; return this; }
  slug(slug: string): this { this.config.slug = slug; return this; }
  version(version: string): this { this.config.version = version; return this; }
  description(desc: string): this { this.config.description = desc; return this; }
  shortDescription(desc: string): this { this.config.shortDescription = desc; return this; }
  category(cat: AgentCategory): this { this.config.category = cat; return this; }
  capabilities(...caps: AgentCapability[]): this { this.config.capabilities = caps; return this; }
  free(): this { this.config.pricingModel = 'FREE'; this.config.price = 0; return this; }
  price(amount: number, model: 'ONE_TIME' | 'SUBSCRIPTION_MONTHLY' | 'SUBSCRIPTION_YEARLY' | 'PAY_PER_USE' = 'ONE_TIME'): this {
    this.config.pricingModel = model;
    this.config.price = amount;
    return this;
  }
  tags(...tags: string[]): this { this.config.tags = tags; return this; }
  entrypoint(file: string): this { this.config.entrypoint = file; return this; }
  runtime(rt: 'python' | 'node'): this { this.config.runtime = rt; return this; }

  build(): AgentManifestConfig {
    const required = ['name', 'slug', 'version', 'description', 'category', 'entrypoint', 'runtime'];
    for (const field of required) {
      if (!(this.config as any)[field]) {
        throw new Error(`Manifest field '${field}' is required`);
      }
    }
    return {
      pricingModel: 'FREE',
      price: 0,
      capabilities: [],
      ...this.config,
    } as AgentManifestConfig;
  }

  toJSON(): string {
    return JSON.stringify(this.build(), null, 2);
  }
}

/**
 * Context available to agents during execution.
 * Mirrors the Python AgentContext API for consistency.
 */
export interface AgentContext {
  // Logging
  log(message: string, level?: 'INFO' | 'WARN' | 'ERROR' | 'DEBUG'): Promise<void>;

  // LLM
  askLLM(messages: LLMMessage[], options?: { screenshot?: boolean }): Promise<string>;

  // OS Control
  click(x: number, y: number, button?: 'left' | 'right'): void;
  doubleClick(x: number, y: number): void;
  typeText(text: string): void;
  pressKey(key: string): void;
  hotkey(...keys: string[]): void;
  moveMouse(x: number, y: number): void;
  scroll(clicks: number): void;
  drag(startX: number, startY: number, endX: number, endY: number): void;
  openApp(name: string): void;
  runCommand(command: string): Promise<string>;

  // Screen
  sendScreenshot(): Promise<void>;
  getMousePosition(): { x: number; y: number };
  getScreenSize(): { width: number; height: number };

  // Clipboard
  clipboardCopy(text: string): void;
  clipboardPaste(): void;
  clipboardGet(): Promise<string>;
}

/**
 * Base class for agent plugins (TypeScript).
 */
export abstract class AgentPlugin {
  abstract readonly name: string;
  abstract readonly description: string;
  abstract readonly version: string;
  abstract readonly capabilities: AgentCapability[];

  /**
   * Execute the agent's task.
   */
  abstract execute(ctx: AgentContext, prompt: string, config: Record<string, any>): Promise<void>;
}
