/**
 * Agent Tester - Local testing utilities for agent plugins.
 * Allows developers to validate and test their agents before publishing.
 */

import { AgentManifestConfig, TestResult, OSAction } from './types';
import { AgentPlugin, AgentContext } from './plugin';
import * as fs from 'fs';
import * as path from 'path';

interface MockAction {
  type: string;
  params: Record<string, any>;
  timestamp: number;
}

interface MockLog {
  level: string;
  message: string;
  timestamp: number;
}

/**
 * Mock AgentContext for local testing.
 * Records all actions and LLM calls for assertion.
 */
class MockAgentContext implements AgentContext {
  readonly actions: MockAction[] = [];
  readonly logs: MockLog[] = [];
  readonly llmCalls: { messages: any[]; response: string }[] = [];
  readonly screenshots: number[] = [];

  private llmResponses: string[] = [];
  private llmResponseIndex = 0;

  constructor(options?: { llmResponses?: string[] }) {
    this.llmResponses = options?.llmResponses || [
      'I will help you with that task. ACTION:click PARAMS:{"x":500,"y":300}',
    ];
  }

  private recordAction(type: string, params: Record<string, any> = {}) {
    this.actions.push({ type, params, timestamp: Date.now() });
  }

  async log(message: string, level: string = 'INFO'): Promise<void> {
    this.logs.push({ level, message, timestamp: Date.now() });
    if (process.env.OGENTI_TEST_VERBOSE === '1') {
      console.log(`  [${level}] ${message}`);
    }
  }

  async askLLM(messages: any[], options?: { screenshot?: boolean }): Promise<string> {
    const response = this.llmResponses[this.llmResponseIndex % this.llmResponses.length];
    this.llmResponseIndex++;
    this.llmCalls.push({ messages, response });
    return response;
  }

  click(x: number, y: number, button?: string): void {
    this.recordAction('click', { x, y, button: button || 'left' });
  }

  doubleClick(x: number, y: number): void {
    this.recordAction('double_click', { x, y });
  }

  typeText(text: string): void {
    this.recordAction('type_text', { text });
  }

  pressKey(key: string): void {
    this.recordAction('press_key', { key });
  }

  hotkey(...keys: string[]): void {
    this.recordAction('hotkey', { keys });
  }

  moveMouse(x: number, y: number): void {
    this.recordAction('move_mouse', { x, y });
  }

  scroll(clicks: number): void {
    this.recordAction('scroll', { clicks });
  }

  drag(startX: number, startY: number, endX: number, endY: number): void {
    this.recordAction('drag', { startX, startY, endX, endY });
  }

  openApp(name: string): void {
    this.recordAction('open_app', { name });
  }

  async runCommand(command: string): Promise<string> {
    this.recordAction('run_command', { command });
    return `[mock] Command executed: ${command}`;
  }

  async sendScreenshot(): Promise<void> {
    this.screenshots.push(Date.now());
    this.recordAction('screenshot', {});
  }

  getMousePosition(): { x: number; y: number } {
    return { x: 960, y: 540 };
  }

  getScreenSize(): { width: number; height: number } {
    return { width: 1920, height: 1080 };
  }

  clipboardCopy(text: string): void {
    this.recordAction('clipboard_copy', { text });
  }

  clipboardPaste(): void {
    this.recordAction('clipboard_paste', {});
  }

  async clipboardGet(): Promise<string> {
    this.recordAction('clipboard_get', {});
    return '[mock] clipboard content';
  }
}

/**
 * Assertion helpers for test results.
 */
class TestAssertions {
  private ctx: MockAgentContext;
  private failures: string[] = [];

  constructor(ctx: MockAgentContext) {
    this.ctx = ctx;
  }

  actionCount(expected: number): this {
    if (this.ctx.actions.length !== expected) {
      this.failures.push(
        `Expected ${expected} actions, got ${this.ctx.actions.length}`
      );
    }
    return this;
  }

  actionCountAtLeast(min: number): this {
    if (this.ctx.actions.length < min) {
      this.failures.push(
        `Expected at least ${min} actions, got ${this.ctx.actions.length}`
      );
    }
    return this;
  }

  hasAction(type: string, params?: Record<string, any>): this {
    const found = this.ctx.actions.find((a) => {
      if (a.type !== type) return false;
      if (params) {
        return Object.entries(params).every(
          ([k, v]) => a.params[k] === v
        );
      }
      return true;
    });
    if (!found) {
      this.failures.push(
        `Expected action '${type}'${params ? ` with params ${JSON.stringify(params)}` : ''} not found`
      );
    }
    return this;
  }

  noAction(type: string): this {
    const found = this.ctx.actions.find((a) => a.type === type);
    if (found) {
      this.failures.push(`Unexpected action '${type}' was performed`);
    }
    return this;
  }

  logContains(text: string, level?: string): this {
    const found = this.ctx.logs.find((l) => {
      if (level && l.level !== level) return false;
      return l.message.includes(text);
    });
    if (!found) {
      this.failures.push(`Expected log containing '${text}' not found`);
    }
    return this;
  }

  llmCallCount(expected: number): this {
    if (this.ctx.llmCalls.length !== expected) {
      this.failures.push(
        `Expected ${expected} LLM calls, got ${this.ctx.llmCalls.length}`
      );
    }
    return this;
  }

  llmCallCountAtLeast(min: number): this {
    if (this.ctx.llmCalls.length < min) {
      this.failures.push(
        `Expected at least ${min} LLM calls, got ${this.ctx.llmCalls.length}`
      );
    }
    return this;
  }

  screenshotsTaken(expected: number): this {
    if (this.ctx.screenshots.length !== expected) {
      this.failures.push(
        `Expected ${expected} screenshots, got ${this.ctx.screenshots.length}`
      );
    }
    return this;
  }

  custom(name: string, predicate: (ctx: MockAgentContext) => boolean): this {
    if (!predicate(this.ctx)) {
      this.failures.push(`Custom assertion '${name}' failed`);
    }
    return this;
  }

  getFailures(): string[] {
    return [...this.failures];
  }
}

/**
 * Test case definition for use with AgentTester.
 */
export interface TestCase {
  name: string;
  prompt: string;
  config?: Record<string, any>;
  llmResponses?: string[];
  timeout?: number;
  assert: (assertions: TestAssertions) => void;
}

/**
 * AgentTester - comprehensive testing utility for agent plugins.
 */
export class AgentTester {
  private manifestPath?: string;
  private pluginInstance?: AgentPlugin;
  private verbose: boolean;

  constructor(options: {
    manifestPath?: string;
    plugin?: AgentPlugin;
    verbose?: boolean;
  } = {}) {
    this.manifestPath = options.manifestPath;
    this.pluginInstance = options.plugin;
    this.verbose = options.verbose ?? false;
    if (this.verbose) {
      process.env.OGENTI_TEST_VERBOSE = '1';
    }
  }

  /**
   * Validate an agent manifest file.
   */
  async validateManifest(): Promise<TestResult> {
    const startTime = Date.now();
    const errors: string[] = [];
    const warnings: string[] = [];

    try {
      const manifestFile = this.manifestPath || path.join(process.cwd(), 'agent.json');

      if (!fs.existsSync(manifestFile)) {
        return {
          passed: false,
          totalTests: 1,
          passedTests: 0,
          failedTests: 1,
          errors: [`Manifest file not found: ${manifestFile}`],
          warnings: [],
          duration: Date.now() - startTime,
        };
      }

      const raw = fs.readFileSync(manifestFile, 'utf-8');
      let manifest: any;
      try {
        manifest = JSON.parse(raw);
      } catch {
        return {
          passed: false,
          totalTests: 1,
          passedTests: 0,
          failedTests: 1,
          errors: ['Invalid JSON in manifest file'],
          warnings: [],
          duration: Date.now() - startTime,
        };
      }

      // Required fields
      const requiredFields = ['name', 'slug', 'version', 'description', 'category', 'entrypoint', 'runtime'];
      for (const field of requiredFields) {
        if (!manifest[field]) {
          errors.push(`Missing required field: ${field}`);
        }
      }

      // Validate slug format
      if (manifest.slug && !/^[a-z0-9-]+$/.test(manifest.slug)) {
        errors.push('Slug must contain only lowercase letters, numbers, and hyphens');
      }

      // Validate version format (semver)
      if (manifest.version && !/^\d+\.\d+\.\d+(-[a-zA-Z0-9.]+)?$/.test(manifest.version)) {
        errors.push('Version must follow semver format (e.g., 1.0.0)');
      }

      // Validate category
      const validCategories = [
        'CODING', 'RESEARCH', 'DATA_ANALYSIS', 'DESIGN', 'WRITING',
        'AUTOMATION', 'TESTING', 'DEVOPS', 'COMMUNICATION', 'OTHER',
      ];
      if (manifest.category && !validCategories.includes(manifest.category)) {
        errors.push(`Invalid category: ${manifest.category}. Must be one of: ${validCategories.join(', ')}`);
      }

      // Validate capabilities
      const validCapabilities = [
        'MOUSE_CONTROL', 'KEYBOARD_INPUT', 'SCREENSHOT_ANALYSIS',
        'FILE_MANAGEMENT', 'BROWSER_AUTOMATION', 'TERMINAL_ACCESS',
        'CLIPBOARD_ACCESS', 'WINDOW_MANAGEMENT', 'PROCESS_MANAGEMENT',
        'NETWORK_ACCESS', 'AUDIO_VIDEO',
      ];
      if (manifest.capabilities) {
        for (const cap of manifest.capabilities) {
          if (!validCapabilities.includes(cap)) {
            warnings.push(`Unknown capability: ${cap}`);
          }
        }
      }

      // Validate entrypoint exists
      if (manifest.entrypoint) {
        const entryDir = this.manifestPath
          ? path.dirname(this.manifestPath)
          : process.cwd();
        const entryPath = path.join(entryDir, manifest.entrypoint);
        if (!fs.existsSync(entryPath)) {
          errors.push(`Entrypoint file not found: ${manifest.entrypoint}`);
        }
      }

      // Validate pricing
      if (manifest.pricingModel === 'FREE' && manifest.price && manifest.price > 0) {
        warnings.push('Free agents should have price 0 or undefined');
      }
      if (['ONE_TIME', 'SUBSCRIPTION_MONTHLY', 'SUBSCRIPTION_YEARLY', 'PAY_PER_USE'].includes(manifest.pricingModel) && (!manifest.price || manifest.price <= 0)) {
        errors.push('Paid agents must have a price greater than 0');
      }

      // Validate description length
      if (manifest.description && manifest.description.length < 20) {
        warnings.push('Description is very short. Consider adding more detail.');
      }
      if (manifest.description && manifest.description.length > 5000) {
        errors.push('Description exceeds 5000 character limit');
      }

      // Validate name length
      if (manifest.name && manifest.name.length < 3) {
        errors.push('Name must be at least 3 characters');
      }
      if (manifest.name && manifest.name.length > 100) {
        errors.push('Name exceeds 100 character limit');
      }

      // Runtime validation
      if (manifest.runtime && !['python', 'node'].includes(manifest.runtime)) {
        errors.push(`Invalid runtime: ${manifest.runtime}. Must be 'python' or 'node'`);
      }

      const passed = errors.length === 0;
      return {
        passed,
        totalTests: 1,
        passedTests: passed ? 1 : 0,
        failedTests: passed ? 0 : 1,
        errors,
        warnings,
        duration: Date.now() - startTime,
      };
    } catch (err: any) {
      return {
        passed: false,
        totalTests: 1,
        passedTests: 0,
        failedTests: 1,
        errors: [`Validation error: ${err.message}`],
        warnings,
        duration: Date.now() - startTime,
      };
    }
  }

  /**
   * Run a single test case against the agent plugin.
   */
  async runTest(testCase: TestCase): Promise<{
    name: string;
    passed: boolean;
    errors: string[];
    duration: number;
    actions: MockAction[];
    logs: MockLog[];
    llmCalls: number;
  }> {
    const start = Date.now();
    const ctx = new MockAgentContext({ llmResponses: testCase.llmResponses });

    try {
      if (!this.pluginInstance) {
        throw new Error('No plugin instance provided for testing');
      }

      // Run with timeout
      const timeout = testCase.timeout || 30000;
      await Promise.race([
        this.pluginInstance.execute(ctx, testCase.prompt, testCase.config || {}),
        new Promise((_, reject) =>
          setTimeout(() => reject(new Error(`Test timed out after ${timeout}ms`)), timeout)
        ),
      ]);

      // Run assertions
      const assertions = new TestAssertions(ctx);
      testCase.assert(assertions);
      const failures = assertions.getFailures();

      return {
        name: testCase.name,
        passed: failures.length === 0,
        errors: failures,
        duration: Date.now() - start,
        actions: ctx.actions,
        logs: ctx.logs,
        llmCalls: ctx.llmCalls.length,
      };
    } catch (err: any) {
      return {
        name: testCase.name,
        passed: false,
        errors: [`Execution error: ${err.message}`],
        duration: Date.now() - start,
        actions: ctx.actions,
        logs: ctx.logs,
        llmCalls: ctx.llmCalls.length,
      };
    }
  }

  /**
   * Run a full test suite.
   */
  async runSuite(tests: TestCase[]): Promise<TestResult> {
    const startTime = Date.now();
    const allErrors: string[] = [];
    const warnings: string[] = [];
    let passedCount = 0;

    console.log(`\n  Running ${tests.length} test(s)...\n`);

    for (const test of tests) {
      const result = await this.runTest(test);
      if (result.passed) {
        passedCount++;
        console.log(`  ✓ ${result.name} (${result.duration}ms)`);
      } else {
        console.log(`  ✗ ${result.name} (${result.duration}ms)`);
        for (const err of result.errors) {
          console.log(`    → ${err}`);
          allErrors.push(`[${result.name}] ${err}`);
        }
      }

      if (this.verbose) {
        console.log(`    Actions: ${result.actions.length}, LLM calls: ${result.llmCalls}`);
      }
    }

    const failedCount = tests.length - passedCount;
    console.log(`\n  ${passedCount} passed, ${failedCount} failed (${Date.now() - startTime}ms)\n`);

    return {
      passed: failedCount === 0,
      totalTests: tests.length,
      passedTests: passedCount,
      failedTests: failedCount,
      errors: allErrors,
      warnings,
      duration: Date.now() - startTime,
    };
  }

  /**
   * Quick smoke test — runs the plugin with a simple prompt.
   */
  async smokeTest(prompt: string = 'Test the agent'): Promise<TestResult> {
    return this.runSuite([
      {
        name: 'Smoke Test',
        prompt,
        assert: (a) => a.actionCountAtLeast(0),
      },
    ]);
  }

  /**
   * Create a test context for manual use.
   */
  static createMockContext(options?: {
    llmResponses?: string[];
  }): MockAgentContext & AgentContext {
    return new MockAgentContext(options);
  }
}
