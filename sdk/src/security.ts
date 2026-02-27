/**
 * Security Scanner — Self-check utilities for agent developers.
 *
 * Run this before publishing to catch issues that the marketplace
 * security review will flag or reject.
 *
 * @example
 * ```ts
 * import { scanFile, scanCode } from '@ogenti/sdk/security';
 *
 * const result = await scanFile('./agent.py');
 * if (!result.safe) {
 *   console.log('Issues:', result.findings);
 * }
 * ```
 */

import * as fs from 'fs';

export type Severity = 'LOW' | 'MEDIUM' | 'HIGH' | 'CRITICAL';

export interface Finding {
  rule: string;
  severity: Severity;
  message: string;
  line?: number;
  snippet?: string;
}

export interface ScanResult {
  safe: boolean;
  findings: Finding[];
  summary: string;
}

// Mirrors the backend review patterns so devs can catch issues locally
const RULES: { pattern: RegExp; rule: string; severity: Severity; message: string }[] = [
  { pattern: /socket\.(socket|connect|bind|listen)/i, rule: 'RAW_SOCKET', severity: 'CRITICAL', message: 'Raw socket usage — will be rejected' },
  { pattern: /(?:open|read)\s*\(\s*["'`](?:\/etc\/passwd|\/etc\/shadow|C:\\Windows\\System32)/i, rule: 'SYSTEM_FILE', severity: 'CRITICAL', message: 'System file access — will be rejected' },
  { pattern: /shutil\.rmtree\s*\(\s*["'`](?:\/|C:\\|~)/i, rule: 'RECURSIVE_DELETE', severity: 'CRITICAL', message: 'Recursive root/home deletion — will be rejected' },
  { pattern: /\.ssh\/|id_rsa|authorized_keys/i, rule: 'SSH_KEYS', severity: 'CRITICAL', message: 'SSH key access — will be rejected' },
  { pattern: /keyring|getpass|win32cred|credential_manager/i, rule: 'CRED_ACCESS', severity: 'CRITICAL', message: 'Credential store access — will be rejected' },
  { pattern: /BROWSER_COOKIE|chrome.*cookies|firefox.*cookies/i, rule: 'COOKIE_THEFT', severity: 'CRITICAL', message: 'Browser cookie access — will be rejected' },
  { pattern: /crontab|schtasks|startup\s*folder|autorun|HKCU.*\\Run/i, rule: 'PERSISTENCE', severity: 'CRITICAL', message: 'Persistence mechanism — will be rejected' },
  { pattern: /stratum\+tcp|cryptonight|xmrig|mining.pool/i, rule: 'CRYPTOMINER', severity: 'CRITICAL', message: 'Crypto mining — will be rejected' },
  { pattern: /\\x[0-9a-f]{2}(?:\\x[0-9a-f]{2}){20,}/i, rule: 'SHELLCODE', severity: 'CRITICAL', message: 'Hex shellcode pattern — will be rejected' },
  { pattern: /\beval\s*\(|\bexec\s*\(/i, rule: 'CODE_INJECTION', severity: 'HIGH', message: 'Dynamic code execution — may be rejected' },
  { pattern: /subprocess\.(call|run|Popen|check_output)|os\.system|os\.popen|child_process/i, rule: 'SHELL_EXEC', severity: 'HIGH', message: 'Shell execution — review carefully, may be rejected if misused' },
  { pattern: /ctypes|cffi|CDLL|windll|kernel32/i, rule: 'NATIVE_CODE', severity: 'HIGH', message: 'Native code / FFI — may be rejected' },
  { pattern: /environ\s*\[\s*["'`](API_KEY|SECRET|TOKEN|PASSWORD)/i, rule: 'ENV_SECRET', severity: 'HIGH', message: 'Reading sensitive env vars — may be rejected' },
  { pattern: /setuid|setgid|sudo\s|runas\s|net\s+user/i, rule: 'PRIV_ESCALATION', severity: 'CRITICAL', message: 'Privilege escalation — will be rejected' },
  { pattern: /requests?\.(get|post|put)\s*\(\s*["'`]https?:\/\//i, rule: 'NETWORK_CALL', severity: 'MEDIUM', message: 'External HTTP request — ensure it\'s not exfiltrating data' },
  { pattern: /base64\.(b64decode|decodebytes)\s*\(\s*["'`][A-Za-z0-9+\/=]{50,}/i, rule: 'ENCODED_PAYLOAD', severity: 'HIGH', message: 'Large encoded payload — may be rejected as obfuscated' },
];

/**
 * Scan a code string for security issues.
 */
export function scanCode(code: string): ScanResult {
  const findings: Finding[] = [];
  const lines = code.split('\n');

  for (const { pattern, rule, severity, message } of RULES) {
    for (let i = 0; i < lines.length; i++) {
      if (pattern.test(lines[i])) {
        findings.push({
          rule,
          severity,
          message,
          line: i + 1,
          snippet: lines[i].trim().slice(0, 100),
        });
      }
    }
  }

  const criticals = findings.filter(f => f.severity === 'CRITICAL').length;
  const highs = findings.filter(f => f.severity === 'HIGH').length;
  const safe = criticals === 0 && highs < 2;

  return {
    safe,
    findings,
    summary: safe
      ? `✓ No blocking issues (${findings.length} info/warning)`
      : `✗ ${criticals} critical, ${highs} high — likely to be rejected`,
  };
}

/**
 * Scan a file for security issues.
 */
export async function scanFile(filePath: string): Promise<ScanResult> {
  if (!fs.existsSync(filePath)) {
    return { safe: false, findings: [{ rule: 'FILE_NOT_FOUND', severity: 'CRITICAL', message: `File not found: ${filePath}` }], summary: 'File not found' };
  }
  const code = fs.readFileSync(filePath, 'utf-8');
  return scanCode(code);
}

/**
 * Scan all agent files in a directory.
 */
export async function scanDirectory(dir: string, extensions = ['.py', '.ts', '.js']): Promise<ScanResult> {
  const allFindings: Finding[] = [];

  function walk(d: string) {
    for (const entry of fs.readdirSync(d, { withFileTypes: true })) {
      const full = `${d}/${entry.name}`;
      if (entry.isDirectory()) {
        if (!['node_modules', '__pycache__', '.venv', 'dist', '.git'].includes(entry.name)) {
          walk(full);
        }
      } else if (extensions.some(ext => entry.name.endsWith(ext))) {
        const result = scanCode(fs.readFileSync(full, 'utf-8'));
        for (const f of result.findings) {
          allFindings.push({ ...f, snippet: `[${entry.name}:${f.line}] ${f.snippet || ''}` });
        }
      }
    }
  }

  if (!fs.existsSync(dir)) {
    return { safe: false, findings: [{ rule: 'DIR_NOT_FOUND', severity: 'CRITICAL', message: `Directory not found: ${dir}` }], summary: 'Directory not found' };
  }

  walk(dir);

  const criticals = allFindings.filter(f => f.severity === 'CRITICAL').length;
  const highs = allFindings.filter(f => f.severity === 'HIGH').length;
  const safe = criticals === 0 && highs < 2;

  return {
    safe,
    findings: allFindings,
    summary: safe
      ? `✓ ${allFindings.length} finding(s), none blocking`
      : `✗ ${criticals} critical, ${highs} high across project`,
  };
}
