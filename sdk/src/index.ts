/**
 * ogenti SDK
 * Build and publish OS-controlling AI agents
 *
 * Quick start:
 *   import { defineAgent } from '@ogenti/sdk';
 *
 *   export default defineAgent({
 *     name: 'My Agent',
 *     slug: 'my-agent',
 *     description: 'Does cool stuff',
 *     category: 'AUTOMATION',
 *     async run(ctx, prompt) {
 *       await ctx.sendScreenshot();
 *       ctx.typeText('Hello!');
 *     }
 *   });
 */

// Core
export { AgentSDK } from './AgentSDK';

// Plugin development
export { AgentPlugin, AgentContext, AgentManifest } from './plugin';
export { defineAgent } from './define';
export type { AgentDef } from './define';

// Testing
export { AgentTester } from './testing';
export type { TestCase } from './testing';

// Security self-check
export { scanCode, scanFile, scanDirectory } from './security';
export type { ScanResult, Finding, Severity } from './security';

// Types
export * from './types';
