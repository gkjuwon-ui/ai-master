#!/usr/bin/env node
/**
 * ogenti CLI — developer tool for creating, testing, and publishing agents.
 *
 * Commands:
 *   init       Scaffold a new agent project
 *   validate   Validate agent manifest
 *   test       Run agent test suite
 *   scan       Security self-check before publishing
 *   build      Bundle agent for upload
 *   publish    Publish agent to marketplace
 *   login      Authenticate with API key
 *   whoami     Show current developer info
 *   list       List your published agents
 */

import { Command } from 'commander';
import * as fs from 'fs';
import * as path from 'path';
import chalk from 'chalk';
import { AgentSDK } from './AgentSDK';
import { AgentTester } from './testing';
import { scanDirectory } from './security';
import { AgentManifestConfig } from './types';

const VERSION = '1.0.0';
const CONFIG_DIR = path.join(
  process.env.HOME || process.env.USERPROFILE || '.',
  '.ogenti'
);
const CONFIG_FILE = path.join(CONFIG_DIR, 'config.json');

// ── Helpers ───────────────────────────────────────────────────────────

function loadConfig(): { apiKey?: string; apiUrl?: string } {
  try {
    if (fs.existsSync(CONFIG_FILE)) {
      return JSON.parse(fs.readFileSync(CONFIG_FILE, 'utf-8'));
    }
  } catch { /* ignore */ }
  return {};
}

function saveConfig(data: Record<string, any>) {
  if (!fs.existsSync(CONFIG_DIR)) {
    fs.mkdirSync(CONFIG_DIR, { recursive: true });
  }
  fs.writeFileSync(CONFIG_FILE, JSON.stringify(data, null, 2));
}

function getSDK(): AgentSDK {
  const config = loadConfig();
  if (!config.apiKey) {
    console.error(chalk.red('Not authenticated. Run `ogenti login` first.'));
    process.exit(1);
  }
  return new AgentSDK({
    apiKey: config.apiKey,
    baseUrl: config.apiUrl || 'http://localhost:3001',
  });
}

function success(msg: string) { console.log(chalk.green('✓'), msg); }
function info(msg: string) { console.log(chalk.blue('ℹ'), msg); }
function warn(msg: string) { console.log(chalk.yellow('⚠'), msg); }
function error(msg: string) { console.log(chalk.red('✗'), msg); }

// ── Program ───────────────────────────────────────────────────────────

const program = new Command();

program
  .name('ogenti')
  .description('ogenti Agent SDK — CLI tools for agent developers')
  .version(VERSION);

// ─── init ─────────────────────────────────────────────────────────────

program
  .command('init')
  .description('Scaffold a new agent project')
  .argument('[name]', 'Agent name', 'my-agent')
  .option('-r, --runtime <runtime>', 'Runtime: python or node', 'python')
  .option('-c, --category <category>', 'Agent category', 'OTHER')
  .option('-d, --dir <directory>', 'Output directory')
  .action((name: string, opts: any) => {
    const slug = name.toLowerCase().replace(/[^a-z0-9-]/g, '-').replace(/-+/g, '-');
    const dir = opts.dir || slug;
    const runtime: 'python' | 'node' = opts.runtime;
    const category = opts.category.toUpperCase();

    if (fs.existsSync(dir)) {
      error(`Directory '${dir}' already exists`);
      process.exit(1);
    }

    info(`Scaffolding agent: ${name} (${runtime})`);

    // Create directory structure
    fs.mkdirSync(path.join(dir, 'tests'), { recursive: true });

    // agent.json manifest
    const manifest: Partial<AgentManifestConfig> = {
      name,
      slug,
      version: '0.1.0',
      description: `${name} — an ogenti agent`,
      shortDescription: `${name} agent`,
      category: category as any,
      capabilities: ['MOUSE_CONTROL', 'KEYBOARD_INPUT', 'SCREENSHOT_ANALYSIS'],
      pricingModel: 'FREE',
      price: 0,
      tags: ['agent'],
      entrypoint: runtime === 'python' ? 'agent.py' : 'agent.ts',
      runtime,
    };
    fs.writeFileSync(
      path.join(dir, 'agent.json'),
      JSON.stringify(manifest, null, 2)
    );

    if (runtime === 'python') {
      // Python agent template (simplified)
      fs.writeFileSync(
        path.join(dir, 'agent.py'),
        `"""${name} — ogenti Agent Plugin."""

from agent_runtime.plugins.base_plugin import BasePlugin


class ${toPascalCase(slug)}Agent(BasePlugin):
    name = "${name}"
    description = "${name} agent"
    version = "0.1.0"
    slug = "${slug}"
    capabilities = ["MOUSE_CONTROL", "KEYBOARD_INPUT", "SCREENSHOT_ANALYSIS"]

    async def execute(self, ctx, prompt: str, config: dict) -> None:
        """Main agent logic. ctx gives you full OS control."""
        await ctx.send_screenshot()

        response = await ctx.ask_llm([
            {"role": "system", "content": "You are an OS automation agent."},
            {"role": "user", "content": prompt},
        ], screenshot=True)

        await ctx.log(f"LLM: {response}")
        # ctx.click(x, y)  |  ctx.type_text("hi")  |  ctx.press_key("enter")
        # ctx.hotkey("ctrl", "c")  |  ctx.open_app("notepad")
`
      );

      // requirements.txt
      fs.writeFileSync(
        path.join(dir, 'requirements.txt'),
        '# Add your agent dependencies here\n'
      );

      // Test file
      fs.writeFileSync(
        path.join(dir, 'tests', 'test_agent.py'),
        `"""Tests for ${name} agent."""

import pytest

# TODO: Add your agent tests here

def test_agent_has_name():
    from agent import ${toPascalCase(slug)}Agent
    agent = ${toPascalCase(slug)}Agent()
    assert agent.name == "${name}"

def test_agent_has_capabilities():
    from agent import ${toPascalCase(slug)}Agent
    agent = ${toPascalCase(slug)}Agent()
    assert len(agent.capabilities) > 0
`
      );
    } else {
      // Node/TypeScript agent template (simplified with defineAgent)
      fs.writeFileSync(
        path.join(dir, 'agent.ts'),
        `import { defineAgent } from '@ogenti/sdk';

export default defineAgent({
  name: '${name}',
  slug: '${slug}',
  description: '${name} agent',
  category: '${category}' as any,

  async run(ctx, prompt) {
    await ctx.sendScreenshot();

    const plan = await ctx.askLLM([
      { role: 'system', content: 'You are an OS automation agent.' },
      { role: 'user', content: prompt },
    ], { screenshot: true });

    await ctx.log(plan);
    // ctx.click(x, y)  |  ctx.typeText('hi')  |  ctx.pressKey('enter')
    // ctx.hotkey('ctrl', 'c')  |  ctx.openApp('notepad')
  },
});
`
      );

      // package.json for Node agents
      fs.writeFileSync(
        path.join(dir, 'package.json'),
        JSON.stringify(
          {
            name: `@ogenti-agents/${slug}`,
            version: '0.1.0',
            private: true,
            dependencies: {
              '@ogenti/sdk': '^1.0.0',
            },
            devDependencies: {
              typescript: '^5.3.0',
            },
          },
          null,
          2
        )
      );

      // tsconfig.json
      fs.writeFileSync(
        path.join(dir, 'tsconfig.json'),
        JSON.stringify(
          {
            compilerOptions: {
              target: 'ES2022',
              module: 'commonjs',
              strict: true,
              esModuleInterop: true,
              outDir: './dist',
              declaration: true,
            },
            include: ['*.ts'],
            exclude: ['node_modules', 'dist'],
          },
          null,
          2
        )
      );
    }

    // .gitignore
    fs.writeFileSync(
      path.join(dir, '.gitignore'),
      `node_modules/
dist/
__pycache__/
*.pyc
.env
*.bundle.zip
`
    );

    // README.md
    fs.writeFileSync(
      path.join(dir, 'README.md'),
      `# ${name}

An ogenti agent plugin.

## Development

\`\`\`bash
# Validate manifest
ogenti validate

# Run tests
ogenti test

# Build for publishing
ogenti build

# Publish to marketplace
ogenti publish
\`\`\`

## Capabilities

- Mouse control
- Keyboard input
- Screenshot analysis

## License

MIT
`
    );

    success(`Agent project created in ./${dir}/`);
    console.log('');
    console.log(`  ${chalk.dim('cd')} ${dir}`);
    console.log(`  ${chalk.dim('ogenti validate')}  — validate manifest`);
    console.log(`  ${chalk.dim('ogenti test')}      — run tests`);
    console.log(`  ${chalk.dim('ogenti publish')}   — publish to marketplace`);
    console.log('');
  });

// ─── validate ─────────────────────────────────────────────────────────

program
  .command('validate')
  .description('Validate agent manifest and project structure')
  .option('-f, --file <path>', 'Path to agent.json', 'agent.json')
  .action(async (opts: any) => {
    info('Validating agent manifest...');
    const tester = new AgentTester({ manifestPath: opts.file });
    const result = await tester.validateManifest();

    if (result.passed) {
      success('Manifest is valid');
    } else {
      error('Manifest validation failed');
    }

    for (const err of result.errors) {
      console.log(`  ${chalk.red('✗')} ${err}`);
    }
    for (const w of result.warnings) {
      console.log(`  ${chalk.yellow('⚠')} ${w}`);
    }

    process.exit(result.passed ? 0 : 1);
  });

// ─── test ─────────────────────────────────────────────────────────────

program
  .command('test')
  .description('Run agent test suite locally')
  .option('-v, --verbose', 'Verbose output')
  .option('-f, --file <path>', 'Path to agent.json', 'agent.json')
  .action(async (opts: any) => {
    info('Running agent tests...');

    // First validate manifest
    const tester = new AgentTester({
      manifestPath: opts.file,
      verbose: opts.verbose,
    });

    const manifestResult = await tester.validateManifest();
    if (!manifestResult.passed) {
      error('Manifest validation failed. Fix manifest errors before testing.');
      for (const err of manifestResult.errors) {
        console.log(`  ${chalk.red('✗')} ${err}`);
      }
      process.exit(1);
    }
    success('Manifest valid');

    // Run smoke test
    const smokeResult = await tester.smokeTest();
    if (!smokeResult.passed) {
      error('Smoke test failed');
      for (const err of smokeResult.errors) {
        console.log(`  ${chalk.red('✗')} ${err}`);
      }
    } else {
      success('Smoke test passed');
    }

    process.exit(smokeResult.passed ? 0 : 1);
  });

// ─── build ────────────────────────────────────────────────────────────

program
  .command('build')
  .description('Bundle agent for upload')
  .option('-f, --file <path>', 'Path to agent.json', 'agent.json')
  .option('-o, --output <path>', 'Output bundle path')
  .action(async (opts: any) => {
    info('Building agent bundle...');

    if (!fs.existsSync(opts.file)) {
      error(`Manifest not found: ${opts.file}`);
      process.exit(1);
    }

    const manifest = JSON.parse(fs.readFileSync(opts.file, 'utf-8'));
    const outputPath = opts.output || `${manifest.slug || 'agent'}-${manifest.version || '0.0.0'}.bundle.zip`;

    try {
      const archiver = await import('archiver');
      const output = fs.createWriteStream(outputPath);
      const archive = archiver.default('zip', { zlib: { level: 9 } });

      archive.pipe(output);

      // Add manifest
      archive.file(opts.file, { name: 'agent.json' });

      // Add source files based on runtime
      if (manifest.runtime === 'python') {
        archive.glob('**/*.py', { ignore: ['__pycache__/**', '*.pyc', '.venv/**'] });
        if (fs.existsSync('requirements.txt')) {
          archive.file('requirements.txt', { name: 'requirements.txt' });
        }
      } else {
        archive.glob('**/*.ts', { ignore: ['node_modules/**', 'dist/**'] });
        archive.glob('**/*.js', { ignore: ['node_modules/**', 'dist/**'] });
        if (fs.existsSync('package.json')) {
          archive.file('package.json', { name: 'package.json' });
        }
      }

      // Add README if exists
      if (fs.existsSync('README.md')) {
        archive.file('README.md', { name: 'README.md' });
      }

      await archive.finalize();

      await new Promise<void>((resolve) => output.on('close', resolve));

      const size = fs.statSync(outputPath).size;
      success(`Bundle created: ${outputPath} (${formatBytes(size)})`);

      if (size > 50 * 1024 * 1024) {
        warn('Bundle exceeds 50MB limit. Remove unnecessary files.');
      }
    } catch (err: any) {
      error(`Build failed: ${err.message}`);
      process.exit(1);
    }
  });

// ─── publish ──────────────────────────────────────────────────────────

program
  .command('publish')
  .description('Publish agent to ogenti marketplace')
  .option('-f, --file <path>', 'Path to agent.json', 'agent.json')
  .option('--dry-run', 'Validate without publishing')
  .action(async (opts: any) => {
    const sdk = getSDK();

    info('Preparing agent for publication...');

    // Validate first
    const tester = new AgentTester({ manifestPath: opts.file });
    const validation = await tester.validateManifest();
    if (!validation.passed) {
      error('Manifest validation failed');
      for (const err of validation.errors) {
        console.log(`  ${chalk.red('✗')} ${err}`);
      }
      process.exit(1);
    }
    success('Manifest valid');

    if (opts.dryRun) {
      info('Dry run — skipping upload');
      return;
    }

    // Upload
    try {
      info('Uploading agent...');
      const manifest = JSON.parse(fs.readFileSync(opts.file, 'utf-8'));
      const uploadResult = await sdk.upload(opts.file, process.cwd());
      if (!uploadResult.agentId) {
        error('Upload failed: no agent ID returned');
        process.exit(1);
      }
      success(`Agent uploaded: ${uploadResult.agentId}`);

      // Publish
      info('Publishing to marketplace...');
      await sdk.publish(uploadResult.agentId, {
        releaseNotes: `v${manifest.version}`,
        listed: true,
      });
      success(`${manifest.name} v${manifest.version} published!`);
      console.log('');
      console.log(`  View: ${chalk.dim(`http://localhost:3000/marketplace/${uploadResult.agentId}`)}`);
      console.log('');
    } catch (err: any) {
      error(`Publish failed: ${err.response?.data?.message || err.message}`);
      process.exit(1);
    }
  });

// ─── scan ─────────────────────────────────────────────────────────

program
  .command('scan')
  .description('Security self-check — find issues before marketplace review')
  .option('-d, --dir <directory>', 'Directory to scan', '.')
  .action(async (opts: any) => {
    info('Running security scan...');
    const result = await scanDirectory(opts.dir);

    if (result.safe) {
      success(result.summary);
    } else {
      error(result.summary);
    }

    for (const f of result.findings) {
      const color = f.severity === 'CRITICAL' ? chalk.red
        : f.severity === 'HIGH' ? chalk.yellow
        : chalk.dim;
      console.log(`  ${color(`[${f.severity}]`)} ${f.rule}: ${f.message}`);
      if (f.snippet) console.log(`    ${chalk.dim(f.snippet)}`);
    }

    if (!result.safe) {
      console.log('');
      warn('Fix the above issues before publishing or your agent will be rejected.');
    }

    process.exit(result.safe ? 0 : 1);
  });

// ─── login ────────────────────────────────────────────────────────────

program
  .command('login')
  .description('Authenticate with your developer API key')
  .argument('<apiKey>', 'Your developer API key')
  .option('-u, --url <url>', 'API base URL', 'http://localhost:3001')
  .action(async (apiKey: string, opts: any) => {
    info('Authenticating...');

    try {
      const sdk = new AgentSDK({ apiKey, baseUrl: opts.url });
      const stats = await sdk.getDeveloperStats();
      saveConfig({ apiKey, apiUrl: opts.url });
      success(`Authenticated as developer (${stats.totalAgents || 0} agents)`);
    } catch (err: any) {
      error(`Authentication failed: ${err.response?.data?.message || err.message}`);
      process.exit(1);
    }
  });

// ─── whoami ───────────────────────────────────────────────────────────

program
  .command('whoami')
  .description('Show current developer info')
  .action(async () => {
    const config = loadConfig();
    if (!config.apiKey) {
      error('Not authenticated. Run `ogenti login <apiKey>` first.');
      process.exit(1);
    }

    try {
      const sdk = getSDK();
      const stats = await sdk.getDeveloperStats();
      console.log('');
      console.log(`  API Key:   ${chalk.dim(config.apiKey.slice(0, 8) + '...')}`);
      console.log(`  Agents:    ${stats.totalAgents || 0}`);
      console.log(`  Downloads: ${stats.totalDownloads || 0}`);
      console.log(`  Revenue:   $${(stats.totalRevenue || 0).toFixed(2)}`);
      console.log('');
    } catch (err: any) {
      error(`Failed to fetch info: ${err.message}`);
      process.exit(1);
    }
  });

// ─── list ─────────────────────────────────────────────────────────────

program
  .command('list')
  .description('List your published agents')
  .action(async () => {
    const sdk = getSDK();

    try {
      const agents = await sdk.listAgents();

      if (agents.length === 0) {
        info('No agents published yet. Run `ogenti init` to get started.');
        return;
      }

      console.log('');
      console.log(`  ${chalk.bold('Your Agents')} (${agents.length})`);
      console.log('  ' + '─'.repeat(60));

      for (const agent of agents) {
        const status = agent.isPublished
          ? chalk.green('published')
          : chalk.yellow('draft');
        console.log(
          `  ${chalk.white(agent.name)} ${chalk.dim(`v${agent.version}`)} [${status}]`
        );
        console.log(
          `    ${chalk.dim(agent.shortDescription || agent.description?.slice(0, 60) || '')}`
        );
        console.log(
          `    Downloads: ${agent.downloads || 0}  Rating: ${agent.rating || '-'}  Price: ${agent.price ? '$' + agent.price.toFixed(2) : 'Free'}`
        );
        console.log('');
      }
    } catch (err: any) {
      error(`Failed to list agents: ${err.message}`);
      process.exit(1);
    }
  });

// ─── Utility functions ────────────────────────────────────────────────

function toPascalCase(str: string): string {
  return str
    .split('-')
    .map((s) => s.charAt(0).toUpperCase() + s.slice(1))
    .join('');
}

function formatBytes(bytes: number): string {
  if (bytes < 1024) return bytes + ' B';
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
  return (bytes / (1024 * 1024)).toFixed(1) + ' MB';
}

// ── Run ───────────────────────────────────────────────────────────────

program.parse(process.argv);

if (!process.argv.slice(2).length) {
  program.outputHelp();
}
