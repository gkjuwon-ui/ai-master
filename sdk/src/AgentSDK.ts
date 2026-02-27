/**
 * AgentSDK - Main SDK class for interacting with the ogenti platform.
 */

import axios, { AxiosInstance } from 'axios';
import * as fs from 'fs';
import * as path from 'path';
import FormData from 'form-data';
import {
  SDKConfig,
  UploadResult,
  ValidateResult,
  AgentManifestConfig,
  AgentStats,
  PublishOptions,
} from './types';

const DEFAULT_BASE_URL = 'http://localhost:4000/api';

export class AgentSDK {
  private client: AxiosInstance;
  private apiKey: string;

  constructor(config: SDKConfig) {
    this.apiKey = config.apiKey;
    this.client = axios.create({
      baseURL: config.baseUrl || DEFAULT_BASE_URL,
      timeout: config.timeout || 30000,
      headers: {
        'Authorization': `ApiKey ${config.apiKey}`,
        'Content-Type': 'application/json',
      },
    });
  }

  // === Agent Management ===

  /**
   * Validate an agent manifest and bundle.
   */
  async validate(manifestPath: string): Promise<ValidateResult> {
    const errors: string[] = [];
    const warnings: string[] = [];

    // Check manifest exists
    if (!fs.existsSync(manifestPath)) {
      return { valid: false, errors: ['Manifest file not found'], warnings: [] };
    }

    try {
      const manifest: AgentManifestConfig = JSON.parse(
        fs.readFileSync(manifestPath, 'utf-8')
      );

      // Required fields
      if (!manifest.name) errors.push('name is required');
      if (!manifest.slug) errors.push('slug is required');
      if (!manifest.version) errors.push('version is required');
      if (!manifest.description) errors.push('description is required');
      if (!manifest.category) errors.push('category is required');
      if (!manifest.entrypoint) errors.push('entrypoint is required');
      if (!manifest.runtime) errors.push('runtime is required');
      if (!manifest.capabilities || manifest.capabilities.length === 0) {
        warnings.push('No capabilities specified');
      }

      // Validate slug format
      if (manifest.slug && !/^[a-z0-9_-]+$/.test(manifest.slug)) {
        errors.push('slug must be lowercase alphanumeric with hyphens/underscores');
      }

      // Validate version format
      if (manifest.version && !/^\d+\.\d+\.\d+/.test(manifest.version)) {
        errors.push('version must follow semver (x.y.z)');
      }

      // Check entrypoint exists
      const entrypointPath = path.resolve(path.dirname(manifestPath), manifest.entrypoint);
      if (!fs.existsSync(entrypointPath)) {
        errors.push(`Entrypoint file not found: ${manifest.entrypoint}`);
      }

      // Validate pricing
      if (manifest.pricingModel !== 'FREE' && (!manifest.price || manifest.price <= 0)) {
        errors.push('Price must be > 0 for non-free agents');
      }

      // Warnings
      if (!manifest.shortDescription) {
        warnings.push('shortDescription recommended for marketplace listing');
      }
      if (!manifest.tags || manifest.tags.length === 0) {
        warnings.push('Adding tags improves discoverability');
      }
      if (manifest.description.length < 50) {
        warnings.push('Description should be at least 50 characters');
      }

      return { valid: errors.length === 0, errors, warnings };
    } catch (e: any) {
      return { valid: false, errors: [`Invalid JSON: ${e.message}`], warnings: [] };
    }
  }

  /**
   * Upload an agent bundle to the platform.
   */
  async upload(bundlePath: string, manifestPath: string): Promise<UploadResult> {
    if (!fs.existsSync(bundlePath)) {
      return { success: false, message: 'Bundle file not found' };
    }

    const validation = await this.validate(manifestPath);
    if (!validation.valid) {
      return {
        success: false,
        message: 'Validation failed',
        errors: validation.errors,
      };
    }

    const formData = new FormData();
    formData.append('bundle', fs.createReadStream(bundlePath));
    formData.append('manifest', fs.readFileSync(manifestPath, 'utf-8'));

    try {
      const res = await this.client.post('/developer/upload', formData, {
        headers: formData.getHeaders(),
        maxContentLength: 100 * 1024 * 1024, // 100MB
      });

      return {
        success: true,
        agentId: res.data.data?.agentId,
        version: res.data.data?.version,
        message: 'Upload successful',
      };
    } catch (e: any) {
      return {
        success: false,
        message: e.response?.data?.error?.message || e.message,
      };
    }
  }

  /**
   * Publish a draft agent to the marketplace.
   */
  async publish(agentId: string, options?: PublishOptions): Promise<{ success: boolean; message: string }> {
    try {
      await this.client.post(`/agents/${agentId}/publish`, {
        draft: options?.draft,
        changelog: options?.changelog,
      });
      return { success: true, message: 'Agent published' };
    } catch (e: any) {
      return { success: false, message: e.response?.data?.error?.message || e.message };
    }
  }

  /**
   * Get stats for a developer's agent.
   */
  async getAgentStats(agentId: string): Promise<AgentStats | null> {
    try {
      const res = await this.client.get(`/developer/agents/${agentId}/stats`);
      return res.data.data;
    } catch {
      return null;
    }
  }

  /**
   * Get developer account stats.
   */
  async getDeveloperStats(): Promise<any> {
    try {
      const res = await this.client.get('/developer/stats');
      return res.data.data;
    } catch {
      return null;
    }
  }

  /**
   * List developer's agents.
   */
  async listAgents(): Promise<any[]> {
    try {
      const res = await this.client.get('/developer/agents');
      return res.data.data || [];
    } catch {
      return [];
    }
  }

  /**
   * Get developer earnings.
   */
  async getEarnings(): Promise<any> {
    try {
      const res = await this.client.get('/developer/earnings');
      return res.data.data;
    } catch {
      return null;
    }
  }
}
