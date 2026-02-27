/**
 * defineAgent — One-liner agent definition for rapid plugin development.
 *
 * @example
 * ```ts
 * import { defineAgent } from '@ogenti/sdk';
 *
 * export default defineAgent({
 *   name: 'My Agent',
 *   slug: 'my-agent',
 *   description: 'Does cool stuff',
 *   category: 'AUTOMATION',
 *   async run(ctx, prompt) {
 *     await ctx.sendScreenshot();
 *     const plan = await ctx.askLLM([
 *       { role: 'user', content: prompt }
 *     ]);
 *     ctx.typeText(plan);
 *   }
 * });
 * ```
 */

import { AgentPlugin, AgentContext } from './plugin';
import { AgentCapability, AgentCategory } from './types';

export interface AgentDef {
  /** Display name */
  name: string;
  /** URL-safe slug (lowercase, hyphens only) */
  slug: string;
  /** What this agent does */
  description: string;
  /** Marketplace category */
  category: AgentCategory;
  /** Version string (default: '1.0.0') */
  version?: string;
  /** OS capabilities used (default: all standard ones) */
  capabilities?: AgentCapability[];
  /** The agent's main logic */
  run: (ctx: AgentContext, prompt: string, config: Record<string, any>) => Promise<void>;
}

const DEFAULT_CAPS: AgentCapability[] = [
  'MOUSE_CONTROL',
  'KEYBOARD_INPUT',
  'SCREEN_CAPTURE',
  'SCREENSHOT_ANALYSIS',
];

/**
 * Define an agent in a single call.
 * Returns a class that extends AgentPlugin.
 */
export function defineAgent(def: AgentDef): typeof AgentPlugin & { new(): AgentPlugin } {
  const caps = def.capabilities ?? DEFAULT_CAPS;
  const ver = def.version ?? '1.0.0';
  const runFn = def.run;

  // Create a concrete class dynamically
  const AgentClass = class extends AgentPlugin {
    readonly name = def.name;
    readonly description = def.description;
    readonly version = ver;
    readonly capabilities = caps;

    async execute(ctx: AgentContext, prompt: string, config: Record<string, any>): Promise<void> {
      return runFn(ctx, prompt, config);
    }
  };

  // Set a readable class name for debugging
  Object.defineProperty(AgentClass, 'name', { value: def.slug.replace(/-/g, '_') + '_Agent' });

  return AgentClass as any;
}
