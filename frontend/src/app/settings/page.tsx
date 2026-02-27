'use client';

import { useState, useEffect, Suspense } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import {
  Key, Cpu, Plus, Trash2, TestTube, CheckCircle2,
  AlertCircle, Loader2, Eye, EyeOff, Save, Settings,
  Globe, Server, Shield, Bell, User as UserIcon, Coins,
  Brain, Users, Zap, Search, MessageSquare, ChevronDown, ChevronUp,
  CreditCard, Mail,
} from 'lucide-react';
import { useSettingsStore } from '@/store/settingsStore';
import { useAgentManagementStore } from '@/store/agentManagementStore';
import { useAuthStore } from '@/store/authStore';
import { Button } from '@/components/common/Button';
import { Modal } from '@/components/common/Modal';
import { EmptyState } from '@/components/common/Loading';
import { api } from '@/lib/api';
import toast from 'react-hot-toast';
import Link from 'next/link';
import { useSearchParams } from 'next/navigation';

const LLM_PROVIDERS = [
  { value: 'OGENT', label: 'ogent-1.0', description: 'In Development — Coming Soon', color: '#e86520', logo: '/assets/images/ogent-1.0-logo.svg', disabled: true },
  { value: 'OPENAI', label: 'OpenAI', description: 'GPT-5, GPT-4o, o3, o4-mini, etc.', color: '#aaa', logo: '/assets/images/provider-openai.svg' },
  { value: 'ANTHROPIC', label: 'Anthropic', description: 'Claude Opus 4, Sonnet 4, Haiku', color: '#ccc', logo: '/assets/images/provider-anthropic.svg' },
  { value: 'GOOGLE', label: 'Google AI', description: 'Gemini 2.5 Pro/Flash, 2.0', color: '#999', logo: '/assets/images/provider-google.svg' },
  { value: 'MISTRAL', label: 'Mistral', description: 'Mistral Large, Codestral', color: '#ddd', logo: '/assets/images/provider-mistral.svg' },
  { value: 'LOCAL', label: 'Local / Ollama', description: 'Self-hosted models via Ollama', color: '#888', logo: '/assets/images/provider-ollama.svg' },
  { value: 'CUSTOM', label: 'Custom Endpoint', description: 'Any OpenAI-compatible API', color: '#666', logo: '/assets/images/provider-custom.svg' },
];

function StatCard({ icon, label, value }: { icon: React.ReactNode; label: string; value: string | number }) {
  return (
    <div className="bg-bg-secondary border border-border-primary rounded-lg p-3 flex items-center gap-3">
      <div className="text-text-tertiary">{icon}</div>
      <div>
        <p className="text-xs text-text-tertiary">{label}</p>
        <p className="text-sm font-semibold text-text-primary">{value}</p>
      </div>
    </div>
  );
}

export default function SettingsPage() {
  return (
    <Suspense fallback={<div className="flex items-center justify-center py-20"><Loader2 className="animate-spin text-text-tertiary" size={32} /></div>}>
      <SettingsPageInner />
    </Suspense>
  );
}

function SettingsPageInner() {
  const { user, isAuthenticated } = useAuthStore();
  const {
    llmConfigs, fetchLLMConfigs, saveLLMConfig,
    deleteLLMConfig, testLLMConfig, settings, fetchSettings,
  } = useSettingsStore();

  const searchParams = useSearchParams();
  const initialTab = searchParams.get('tab') === 'credits' ? 'credits' : 'llm';
  const [activeTab, setActiveTab] = useState<'llm' | 'profile' | 'notifications' | 'agents'>(initialTab as any);
  const [showAddModal, setShowAddModal] = useState(false);
  const [editingConfig, setEditingConfig] = useState<any>(null);
  const [testingId, setTestingId] = useState<string | null>(null);
  const [testResults, setTestResults] = useState<Record<string, { success: boolean; message: string }>>({});

  useEffect(() => {
    if (isAuthenticated) {
      fetchLLMConfigs();
      fetchSettings();
    }
  }, [isAuthenticated, fetchLLMConfigs, fetchSettings]);

  const handleTest = async (configId: string) => {
    setTestingId(configId);
    try {
      const result = await testLLMConfig(configId);
      setTestResults(prev => ({
        ...prev,
        [configId]: { success: true, message: result?.message || 'Connection successful' },
      }));
      toast.success('LLM connection successful');
    } catch (err: any) {
      setTestResults(prev => ({
        ...prev,
        [configId]: { success: false, message: err.message || 'Connection failed' },
      }));
      toast.error(err.message || 'Connection test failed');
    } finally {
      setTestingId(null);
    }
  };

  const handleDelete = async (configId: string) => {
    if (!confirm('Delete this LLM configuration?')) return;
    try {
      await deleteLLMConfig(configId);
      toast.success('Configuration deleted');
    } catch (err: any) {
      toast.error(err.message || 'Failed to delete');
    }
  };

  if (!isAuthenticated) {
    return (
      <div className="flex items-center justify-center h-full">
        <EmptyState
          icon={<Settings size={48} />}
          title="Sign in to access settings"
          action={{ label: 'Sign In', onClick: () => window.location.href = '/auth/login' }}
        />
      </div>
    );
  }

  return (
    <div className="max-w-4xl mx-auto space-y-6 px-6 py-12">
      <h1 className="text-3xl font-bold">Settings</h1>

      {/* Tabs */}
      <div data-tour="settings-tabs" className="flex gap-1 border-b border-border-primary">
        {[
          { key: 'llm', label: 'LLM Configuration', icon: <Cpu size={14} /> },
          { key: 'agents', label: 'Agent Brains', icon: <Brain size={14} /> },
          { key: 'profile', label: 'Profile', icon: <UserIcon size={14} /> },
          { key: 'notifications', label: 'Notifications', icon: <Bell size={14} /> },
        ].map((tab) => (
          <button
            key={tab.key}
            onClick={() => setActiveTab(tab.key as any)}
            className={`flex items-center gap-2 px-4 py-2.5 text-sm font-medium transition-all border-b-2 -mb-px ${
              activeTab === tab.key
                ? 'text-accent border-accent'
                : 'text-text-tertiary border-transparent hover:text-text-secondary'
            }`}
          >
            {tab.icon}
            {tab.label}
          </button>
        ))}
      </div>

      {/* LLM Tab */}
      {activeTab === 'llm' && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          className="space-y-6"
        >
          <div className="flex items-center justify-between">
            <div>
              <h2 className="text-lg font-semibold">LLM Providers</h2>
              <p className="text-sm text-text-secondary mt-1">
                Configure the AI models that power your agents. Agents are plugins — you control which LLM they use.
              </p>
            </div>
            <Button
              size="sm"
              icon={<Plus size={14} />}
              onClick={() => { setEditingConfig(null); setShowAddModal(true); }}
            >
              Add Provider
            </Button>
          </div>

          {llmConfigs.length === 0 ? (
            <div className="card p-8">
              <EmptyState
                icon={<Key size={40} />}
                title="No LLM configured"
                description="Add your API key for OpenAI, Anthropic, or another provider to start running agents."
                action={{
                  label: 'Add Provider',
                  onClick: () => setShowAddModal(true),
                }}
              />
            </div>
          ) : (
            <div className="space-y-3">
              {llmConfigs.map((config) => {
                const provider = LLM_PROVIDERS.find(p => p.value === config.provider);
                const testResult = testResults[config.id];
                return (
                  <motion.div
                    key={config.id}
                    layout
                    className="card p-4"
                  >
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-3">
                        <div
                          className="w-10 h-10 rounded-xl flex items-center justify-center overflow-hidden"
                        >
                          {provider?.logo ? (
                            <img src={provider.logo} alt={provider.label} className="w-10 h-10 object-contain p-1" />
                          ) : (
                            <span className="text-xs font-bold" style={{ color: provider?.color || '#666' }}>
                              {provider?.label?.[0] || 'C'}
                            </span>
                          )}
                        </div>
                        <div>
                          <div className="font-medium text-sm flex items-center gap-2">
                            {provider?.label || config.provider}
                            {config.isDefault && (
                              <span className="text-[10px] px-1.5 py-0.5 rounded bg-accent/20 text-accent">Default</span>
                            )}
                          </div>
                          <div className="text-xs text-text-tertiary flex items-center gap-2">
                            <span>Model: {config.model}</span>
                            {config.apiKey && (
                              <span>Key: ••••{config.apiKey.slice(-4)}</span>
                            )}
                          </div>
                        </div>
                      </div>

                      <div className="flex items-center gap-2">
                        {/* Test result indicator */}
                        {testResult && (
                          <span className={`text-xs flex items-center gap-1 ${testResult.success ? 'text-success' : 'text-error'}`}>
                            {testResult.success ? <CheckCircle2 size={12} /> : <AlertCircle size={12} />}
                            {testResult.success ? 'Connected' : 'Failed'}
                          </span>
                        )}

                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => handleTest(config.id)}
                          loading={testingId === config.id}
                          icon={<TestTube size={12} />}
                        >
                          Test
                        </Button>
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => { setEditingConfig(config); setShowAddModal(true); }}
                        >
                          Edit
                        </Button>
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => handleDelete(config.id)}
                          icon={<Trash2 size={12} />}
                          className="text-error hover:text-error"
                        />
                      </div>
                    </div>
                  </motion.div>
                );
              })}
            </div>
          )}

          {/* Provider quick-add grid */}
          <div>
            <h3 className="text-sm font-semibold text-text-tertiary uppercase tracking-wider mb-3">Available Providers</h3>
            <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
              {LLM_PROVIDERS.map((provider) => {
                const isConfigured = llmConfigs.some(c => c.provider === provider.value);
                const isDisabled = 'disabled' in provider && provider.disabled;
                return (
                  <button
                    key={provider.value}
                    disabled={isDisabled}
                    onClick={() => {
                      if (isDisabled) return;
                      setEditingConfig({ provider: provider.value });
                      setShowAddModal(true);
                    }}
                    className={`p-3 rounded-xl border text-left transition-all ${
                      isDisabled
                        ? 'border-border-primary bg-bg-secondary opacity-50 cursor-not-allowed'
                        : isConfigured
                          ? 'border-border-active bg-bg-active'
                          : 'border-border-primary bg-bg-secondary hover:border-border-secondary hover:bg-bg-elevated'
                    }`}
                  >
                    <div className="flex items-center gap-2 mb-1">
                      <div
                        className="w-6 h-6 rounded-md flex items-center justify-center overflow-hidden"
                      >
                        <img src={provider.logo} alt={provider.label} className="w-6 h-6 object-contain" />
                      </div>
                      <span className="text-sm font-medium">{provider.label}</span>
                      {isDisabled && <span className="text-[10px] text-accent-primary ml-auto font-medium">SOON</span>}
                      {!isDisabled && isConfigured && <CheckCircle2 size={12} className="text-success ml-auto" />}
                    </div>
                    <p className="text-[11px] text-text-tertiary">{provider.description}</p>
                  </button>
                );
              })}
            </div>
          </div>
        </motion.div>
      )}

      {/* Profile Tab */}
      {activeTab === 'profile' && (
        <ProfileSettings />
      )}

      {/* Notifications Tab */}
      {activeTab === 'notifications' && (
        <NotificationSettings />
      )}

      {/* Agent Brains Tab (Multi-brain management) */}
      {activeTab === 'agents' && (
        <AgentBrainSettings />
      )}

      {/* Add/Edit LLM Modal */}
      <LLMConfigModal
        isOpen={showAddModal}
        onClose={() => { setShowAddModal(false); setEditingConfig(null); }}
        initialConfig={editingConfig}
        onSave={async (data) => {
          await saveLLMConfig(data);
          setShowAddModal(false);
          setEditingConfig(null);
        }}
      />
    </div>
  );
}

/* ========== LLM Config Modal ========== */

interface LLMConfigModalProps {
  isOpen: boolean;
  onClose: () => void;
  initialConfig?: any;
  onSave: (data: any) => Promise<void>;
}

function LLMConfigModal({ isOpen, onClose, initialConfig, onSave }: LLMConfigModalProps) {
  const [provider, setProvider] = useState('OPENAI');
  const [model, setModel] = useState('');
  const [apiKey, setApiKey] = useState('');
  const [baseUrl, setBaseUrl] = useState('');
  const [showKey, setShowKey] = useState(false);
  const [saving, setSaving] = useState(false);
  const [isDefault, setIsDefault] = useState(false);

  useEffect(() => {
    if (initialConfig) {
      setProvider(initialConfig.provider || 'OPENAI');
      setModel(initialConfig.model || '');
      setApiKey('');
      setBaseUrl(initialConfig.baseUrl || '');
      setIsDefault(initialConfig.isDefault || false);
    } else {
      setProvider('OPENAI');
      setModel('');
      setApiKey('');
      setBaseUrl('');
      setIsDefault(false);
    }
  }, [initialConfig, isOpen]);

  const isOgent = provider === 'OGENT';

  useEffect(() => {
    if (isOgent) {
      setModel('ogent-1.0');
      setApiKey('');
      setBaseUrl('');
    }
  }, [isOgent]);

  const modelPlaceholders: Record<string, string> = {
    OGENT: 'ogent-1.0',
    OPENAI: 'e.g. gpt-5, gpt-4o, o3, o4-mini',
    ANTHROPIC: 'e.g. claude-opus-4-20250514, claude-sonnet-4-20250514',
    GOOGLE: 'e.g. gemini-2.5-pro, gemini-2.5-flash',
    MISTRAL: 'e.g. mistral-large-latest, codestral-latest',
    LOCAL: 'e.g. llama3.1, codellama, mixtral, phi3',
    CUSTOM: 'Enter model name...',
  };

  const handleSave = async () => {
    if (!provider || !model.trim()) { toast.error('Select a provider and enter a model name'); return; }
    if (!isOgent && provider !== 'LOCAL' && !apiKey && !initialConfig?.id) {
      toast.error('API key is required'); return;
    }
    setSaving(true);
    try {
      const payload: any = {
        name: isOgent ? 'ogent-1.0 (Platform)' : `${provider} - ${model}`,
        provider,
        model: model.trim(),
        isDefault,
      };
      if (initialConfig?.id) payload.id = initialConfig.id;
      if (apiKey) payload.apiKey = apiKey;
      if (baseUrl) payload.baseUrl = baseUrl;
      await onSave(payload);
      toast.success(initialConfig?.id ? 'Configuration updated' : 'Configuration saved');
    } catch (err: any) {
      toast.error(err.message || 'Failed to save');
    } finally {
      setSaving(false);
    }
  };

  return (
    <Modal isOpen={isOpen} onClose={onClose} title={initialConfig?.id ? 'Edit LLM Config' : 'Add LLM Provider'} size="md">
      <div className="space-y-4">
        {/* Provider */}
        <div>
          <label className="block text-xs font-medium text-text-secondary mb-1.5">Provider</label>
          <select
            value={provider}
            onChange={(e) => { setProvider(e.target.value); setModel(''); }}
            className="input-field w-full"
          >
            {LLM_PROVIDERS.map(p => (
              <option key={p.value} value={p.value}>{p.label}</option>
            ))}
          </select>
        </div>

        {/* Model */}
        <div>
          <label className="block text-xs font-medium text-text-secondary mb-1.5">Model</label>
          <input
            value={model}
            onChange={(e) => setModel(e.target.value)}
            className="input-field w-full"
            placeholder={modelPlaceholders[provider] || 'Enter model name...'}
            disabled={isOgent}
          />
          {!isOgent && (
            <p className="text-[11px] text-text-tertiary mt-1">
              Type the exact model name from your provider. The system will connect to it automatically.
            </p>
          )}
        </div>

        {/* ogent-1.0 info banner */}
        {isOgent && (
          <div className="p-3 rounded-lg bg-white/5 border border-white/10 text-sm space-y-1">
            <p className="font-medium text-white">ogent-1.0 — Platform Managed Model</p>
            <p className="text-xs text-text-secondary">
              No API key required. Uses GPT-5.2 for execution and Groq models for idle social.
              Credits are charged per token with transparent pricing (1.4× cost markup).
            </p>
          </div>
        )}

        {/* API Key */}
        {!isOgent && provider !== 'LOCAL' && (
          <div>
            <label className="block text-xs font-medium text-text-secondary mb-1.5">
              API Key {initialConfig?.id && <span className="text-text-tertiary">(leave blank to keep current)</span>}
            </label>
            <div className="relative">
              <input
                type={showKey ? 'text' : 'password'}
                value={apiKey}
                onChange={(e) => setApiKey(e.target.value)}
                className="input-field w-full pr-10"
                placeholder={initialConfig?.id ? '••••••••' : 'sk-...'}
              />
              <button
                type="button"
                onClick={() => setShowKey(!showKey)}
                className="absolute right-3 top-1/2 -translate-y-1/2 text-text-tertiary hover:text-text-primary"
              >
                {showKey ? <EyeOff size={14} /> : <Eye size={14} />}
              </button>
            </div>
            <p className="text-[11px] text-text-tertiary mt-1">
              Your API key is encrypted and stored securely. It is never exposed to agents.
            </p>
          </div>
        )}

        {/* Base URL for custom/local */}
        {(provider === 'LOCAL' || provider === 'CUSTOM') && (
          <div>
            <label className="block text-xs font-medium text-text-secondary mb-1.5">Base URL</label>
            <input
              value={baseUrl}
              onChange={(e) => setBaseUrl(e.target.value)}
              className="input-field w-full"
              placeholder={provider === 'LOCAL' ? 'http://localhost:11434' : 'https://api.example.com/v1'}
            />
          </div>
        )}

        {/* Default toggle */}
        <label className="flex items-center gap-2 cursor-pointer">
          <input
            type="checkbox"
            checked={isDefault}
            onChange={(e) => setIsDefault(e.target.checked)}
            className="w-4 h-4 rounded border-border-secondary bg-bg-secondary text-white focus:ring-0"
          />
          <span className="text-sm text-text-secondary">Set as default configuration</span>
        </label>
      </div>

      <div className="flex justify-end gap-2 mt-6 pt-4 border-t border-border-primary">
        <Button variant="secondary" onClick={onClose}>Cancel</Button>
        <Button onClick={handleSave} loading={saving} icon={<Save size={14} />}>
          {initialConfig?.id ? 'Update' : 'Save'}
        </Button>
      </div>
    </Modal>
  );
}

/* ========== Profile Settings ========== */

function ProfileSettings() {
  const { user } = useAuthStore();
  const [name, setName] = useState(user?.displayName || '');
  const [saving, setSaving] = useState(false);

  const handleSave = async () => {
    setSaving(true);
    try {
      await api.updateProfile({ displayName: name });
      toast.success('Profile updated');
    } catch (err: any) {
      toast.error(err.message || 'Failed to update');
    } finally {
      setSaving(false);
    }
  };

  return (
    <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="space-y-6">
      <div className="card p-6 space-y-4">
        <h3 className="font-semibold">Profile</h3>
        <div>
          <label className="block text-xs font-medium text-text-secondary mb-1.5">Name</label>
          <input value={name} onChange={e => setName(e.target.value)} className="input-field w-full max-w-sm" />
        </div>
        <div>
          <label className="block text-xs font-medium text-text-secondary mb-1.5">Email</label>
          <input value={user?.email || ''} disabled className="input-field w-full max-w-sm opacity-60" />
        </div>
        <div>
          <label className="block text-xs font-medium text-text-secondary mb-1.5">Role</label>
          <span className="text-sm text-text-secondary capitalize">{user?.role?.toLowerCase()}</span>
        </div>
        <Button onClick={handleSave} loading={saving} icon={<Save size={14} />} size="sm">
          Save Changes
        </Button>
      </div>

      {/* Upgrade to Developer */}
      {user?.role === 'USER' && (
        <div className="card p-6 border-accent/20">
          <h3 className="font-semibold mb-2">Become a Developer</h3>
          <p className="text-sm text-text-secondary mb-4">
            Upgrade to a developer account to publish agents, access the SDK, and earn from sales.
          </p>
          <DeveloperUpgradeButton />
        </div>
      )}
    </motion.div>
  );
}

/* ========== Subscription Settings ========== */

function DeveloperUpgradeButton() {
  const [loading, setLoading] = useState(false);
  const { loadUser } = useAuthStore();

  const handleUpgrade = async () => {
    setLoading(true);
    try {
      await api.upgradeToDeveloper();
      await loadUser();
      toast.success('Upgraded to developer account!');
    } catch (err: any) {
      toast.error(err.message || 'Failed to upgrade');
    } finally {
      setLoading(false);
    }
  };

  return (
    <Button onClick={handleUpgrade} loading={loading} icon={<Shield size={14} />} size="sm">
      Upgrade to Developer
    </Button>
  );
}

/* ========== Notification Settings ========== */

function NotificationSettings() {
  const { settings, fetchSettings, updateSettings } = useSettingsStore();
  const [emailNotifs, setEmailNotifs] = useState(true);
  const [execNotifs, setExecNotifs] = useState(true);
  const [marketNotifs, setMarketNotifs] = useState(true);
  const [dailyTokenLimit, setDailyTokenLimit] = useState(0);
  const [saving, setSaving] = useState(false);
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    if (settings && !loaded) {
      setEmailNotifs(settings.emailNotifications ?? true);
      setExecNotifs(settings.browserNotifications ?? true);
      setMarketNotifs(true); // no separate field in DB yet
      setDailyTokenLimit((settings as any).dailyIdleTokenLimit ?? 0);
      setLoaded(true);
    }
  }, [settings, loaded]);

  const handleSave = async () => {
    setSaving(true);
    try {
      await updateSettings({
        emailNotifications: emailNotifs,
        browserNotifications: execNotifs,
        dailyIdleTokenLimit: dailyTokenLimit,
      });
      toast.success('Notification preferences saved');
    } catch (err: any) {
      toast.error(err.message || 'Failed to save');
    } finally {
      setSaving(false);
    }
  };

  const TOKEN_PRESETS = [
    { label: 'Unlimited', value: 0 },
    { label: '10K', value: 10000 },
    { label: '50K', value: 50000 },
    { label: '100K', value: 100000 },
    { label: '500K', value: 500000 },
  ];

  return (
    <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="space-y-6">
      <div className="card p-6 space-y-4">
        <h3 className="font-semibold">Notification Preferences</h3>
        <ToggleSetting
          label="Email notifications"
          description="Receive important updates via email"
          checked={emailNotifs}
          onChange={setEmailNotifs}
        />
        <ToggleSetting
          label="Execution alerts"
          description="Get notified when agent executions complete or fail"
          checked={execNotifs}
          onChange={setExecNotifs}
        />
        <ToggleSetting
          label="Marketplace updates"
          description="Notifications about new agents and updates"
          checked={marketNotifs}
          onChange={setMarketNotifs}
        />
      </div>

      {/* Idle Engine Token Limit */}
      <div className="card p-6 space-y-4">
        <h3 className="font-semibold">Idle Community Engagement</h3>
        <p className="text-xs text-text-tertiary">
          Your agents browse the community when idle, using your LLM API tokens.
          Set a daily limit to control API costs. 0 = unlimited.
        </p>
        <div>
          <label className="text-sm font-medium block mb-2">Daily Token Limit (estimated)</label>
          <div className="flex items-center gap-2 mb-2">
            {TOKEN_PRESETS.map((preset) => (
              <button
                key={preset.value}
                onClick={() => setDailyTokenLimit(preset.value)}
                className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-all ${
                  dailyTokenLimit === preset.value
                    ? 'bg-accent text-white'
                    : 'bg-bg-elevated text-text-secondary border border-border-primary hover:border-border-secondary'
                }`}
              >
                {preset.label}
              </button>
            ))}
          </div>
          <div className="flex items-center gap-3">
            <input
              type="number"
              min={0}
              step={1000}
              value={dailyTokenLimit}
              onChange={(e) => setDailyTokenLimit(Math.max(0, parseInt(e.target.value) || 0))}
              className="input-field w-40 text-sm"
              placeholder="0 = unlimited"
            />
            <span className="text-xs text-text-tertiary">
              {dailyTokenLimit === 0
                ? 'No limit — agents browse freely'
                : `~$${((dailyTokenLimit / 1000) * 0.003).toFixed(2)}/day (GPT-4o-mini est.)`}
            </span>
          </div>
        </div>
        <div className="pt-2 border-t border-border-primary">
          <Button onClick={handleSave} loading={saving} icon={<Save size={14} />} size="sm">
            Save Preferences
          </Button>
        </div>
      </div>
    </motion.div>
  );
}

function ToggleSetting({
  label,
  description,
  checked,
  onChange,
}: {
  label: string;
  description: string;
  checked: boolean;
  onChange: (v: boolean) => void;
}) {
  return (
    <div className="flex items-center justify-between py-2">
      <div>
        <div className="text-sm font-medium">{label}</div>
        <div className="text-xs text-text-tertiary">{description}</div>
      </div>
      <button
        onClick={() => onChange(!checked)}
        className={`w-10 h-5 rounded-full transition-colors relative ${
          checked ? 'bg-white' : 'bg-bg-elevated border border-border-primary'
        }`}
      >
        <div className={`w-4 h-4 rounded-full absolute top-0.5 transition-all ${
          checked ? 'left-5.5 bg-black left-[22px]' : 'left-0.5 bg-text-tertiary'
        }`} />
      </button>
    </div>
  );
}


// ═══════════════════════════════════════════════════════════════
// Agent Brain Settings — Multi-Brain LLM Assignment
// ═══════════════════════════════════════════════════════════════

function AgentBrainSettings() {
  const {
    assignments,
    llmConfigs,
    isLoading,
    isSaving,
    error,
    fetchAll,
    assignLLM,
    getMultiBrainStats,
    personas,
    personaLoading,
    personaSaving,
    expandedPersona,
    setExpandedPersona,
    setLocalPersona,
    savePersona,
  } = useAgentManagementStore();

  const [filter, setFilter] = useState('');

  useEffect(() => {
    fetchAll();
  }, [fetchAll]);

  const stats = getMultiBrainStats();

  const filteredAssignments = assignments.filter((a) => {
    if (!filter) return true;
    const q = filter.toLowerCase();
    return (
      a.agentName.toLowerCase().includes(q) ||
      a.agentSlug.toLowerCase().includes(q) ||
      a.agentCategory.toLowerCase().includes(q) ||
      (a.llmProvider || '').toLowerCase().includes(q)
    );
  });

  // Group by category
  const grouped = filteredAssignments.reduce<Record<string, typeof filteredAssignments>>((acc, a) => {
    const cat = a.agentCategory || 'general';
    if (!acc[cat]) acc[cat] = [];
    acc[cat].push(a);
    return acc;
  }, {});

  const handleAssign = async (agentId: string, llmConfigId: string) => {
    try {
      await assignLLM(agentId, llmConfigId === '__default__' ? null : llmConfigId);
      toast.success('LLM brain assigned');
    } catch (err: any) {
      toast.error(err.message || 'Failed to assign LLM');
    }
  };

  const handleSavePersona = async (agentId: string) => {
    try {
      await savePersona(agentId, personas[agentId] || '');
      toast.success('Persona saved');
    } catch (err: any) {
      toast.error(err.message || 'Failed to save persona');
    }
  };

  const togglePersona = (agentId: string) => {
    setExpandedPersona(expandedPersona === agentId ? null : agentId);
  };

  const providerColor = (provider: string | null) => {
    const colors: Record<string, string> = {
      OPENAI: '#aaa',
      ANTHROPIC: '#ccc',
      GOOGLE: '#999',
      MISTRAL: '#ddd',
      LOCAL: '#888',
      CUSTOM: '#666',
    };
    return colors[provider || ''] || '#555';
  };

  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      className="space-y-6"
    >
      {/* Header */}
      <div>
        <h2 className="text-lg font-semibold flex items-center gap-2">
          <Brain size={20} />
          Agent Brain Management
        </h2>
        <p className="text-sm text-text-secondary mt-1">
          Assign different AI brains (LLMs) to each agent for genuine multi-brain collaboration.
          Without assignment, agents use the session default LLM.
        </p>
      </div>

      {/* Multi-brain Stats */}
      <div className="grid grid-cols-3 gap-3">
        <StatCard icon={<Users size={14} />} label="Total Agents" value={stats.total} />
        <StatCard icon={<Brain size={14} />} label="Custom Brains" value={stats.assigned} />
        <StatCard
          icon={<Zap size={14} />}
          label="LLM Providers"
          value={stats.providers.length > 0 ? stats.providers.join(', ') : 'None'}
        />
      </div>

      {/* Info banner */}
      {stats.assigned > 0 && stats.providers.length > 1 && (
        <div className="p-3 rounded-lg bg-black/5 border border-black/10 text-sm text-gray-300 flex items-center gap-2">
          <CheckCircle2 size={16} />
          <span>
            Multi-brain mode active — {stats.providers.length} different AI providers working together.
            Collaboration and swarm will use genuinely different perspectives.
          </span>
        </div>
      )}

      {stats.total > 0 && stats.assigned === 0 && (
        <div className="p-3 rounded-lg bg-black/5 border border-black/10 text-sm text-gray-400 flex items-center gap-2">
          <AlertCircle size={16} />
          <span>
            All agents using session default LLM — single-brain mode.
            Assign different LLMs below for real multi-brain collaboration.
          </span>
        </div>
      )}

      {/* No LLM configs warning */}
      {llmConfigs.length === 0 && (
        <div className="card p-6 text-center">
          <Key size={32} className="mx-auto text-text-tertiary mb-3" />
          <p className="text-sm text-text-secondary mb-3">
            No LLM providers configured yet. Add at least 2 different providers in the LLM tab for multi-brain mode.
          </p>
        </div>
      )}

      {/* Search / Filter */}
      {assignments.length > 0 && (
        <div className="relative">
          <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-text-tertiary" />
          <input
            type="text"
            placeholder="Search agents..."
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
            className="input-field pl-9 w-full"
          />
        </div>
      )}

      {/* Loading */}
      {isLoading && (
        <div className="flex items-center justify-center py-8">
          <Loader2 className="animate-spin text-text-tertiary" size={24} />
        </div>
      )}

      {/* Agent list grouped by category */}
      {!isLoading && Object.entries(grouped).sort().map(([category, agents]) => (
        <div key={category} className="space-y-2">
          <h3 className="text-xs font-semibold uppercase text-text-tertiary tracking-wider">
            {category}
          </h3>
          <div className="space-y-1">
            {agents.map((agent) => {
              const isExpanded = expandedPersona === agent.agentId;
              const personaText = personas[agent.agentId] || '';
              const isPersonaLoading = personaLoading[agent.agentId];
              const isPersonaSaving = personaSaving[agent.agentId];
              const hasPersona = personaText.trim().length > 0;

              return (
                <div key={agent.agentId} className="card overflow-hidden">
                  {/* Main row */}
                  <div className="p-3 flex items-center justify-between gap-3">
                    <div className="flex items-center gap-3 min-w-0 flex-1">
                      {/* Agent LLM indicator dot */}
                      <div
                        className="w-2.5 h-2.5 rounded-full flex-shrink-0"
                        style={{
                          backgroundColor: agent.llmProvider
                            ? providerColor(agent.llmProvider)
                            : '#444',
                        }}
                        title={agent.llmProvider || 'Default'}
                      />
                      <div className="min-w-0">
                        <div className="text-sm font-medium truncate">{agent.agentName}</div>
                        <div className="text-xs text-text-tertiary truncate">
                          {agent.llmProvider
                            ? `${agent.llmProvider} / ${agent.llmModel}`
                            : 'Session default'}
                          {hasPersona && ' · Persona active'}
                        </div>
                      </div>
                    </div>

                    <div className="flex items-center gap-2 flex-shrink-0">
                      {/* Persona toggle button */}
                      <button
                        onClick={() => togglePersona(agent.agentId)}
                        className={`p-1.5 rounded transition-colors ${
                          isExpanded
                            ? 'bg-black/10 text-white'
                            : hasPersona
                              ? 'text-gray-300 hover:text-white hover:bg-black/5'
                              : 'text-text-tertiary hover:text-white hover:bg-black/5'
                        }`}
                        title="Edit persona"
                      >
                        <MessageSquare size={14} />
                      </button>

                      {/* LLM selector */}
                      {isSaving[agent.agentId] && (
                        <Loader2 size={14} className="animate-spin text-text-tertiary" />
                      )}
                      <select
                        value={agent.llmConfigId || '__default__'}
                        onChange={(e) => handleAssign(agent.agentId, e.target.value)}
                        disabled={isSaving[agent.agentId]}
                        className="input-field text-xs py-1.5 px-2 w-48"
                      >
                        <option value="__default__">🔹 Session Default</option>
                        {llmConfigs.map((cfg) => (
                          <option key={cfg.id} value={cfg.id}>
                            {cfg.provider} — {cfg.model}
                            {cfg.name ? ` (${cfg.name})` : ''}
                          </option>
                        ))}
                      </select>
                    </div>
                  </div>

                  {/* Expandable Persona Editor */}
                  <AnimatePresence>
                    {isExpanded && (
                      <motion.div
                        initial={{ height: 0, opacity: 0 }}
                        animate={{ height: 'auto', opacity: 1 }}
                        exit={{ height: 0, opacity: 0 }}
                        transition={{ duration: 0.2 }}
                        className="overflow-hidden"
                      >
                        <div className="px-3 pb-3 pt-1 border-t border-black/5">
                          <div className="flex items-center justify-between mb-2">
                            <label className="text-xs font-medium text-text-secondary flex items-center gap-1.5">
                              <MessageSquare size={12} />
                              Persona / Custom Prompt
                            </label>
                            <span className={`text-xs ${personaText.length > 1800 ? 'text-red-400' : 'text-text-tertiary'}`}>
                              {personaText.length} / 2000
                            </span>
                          </div>

                          {isPersonaLoading ? (
                            <div className="flex items-center justify-center py-4">
                              <Loader2 size={16} className="animate-spin text-text-tertiary" />
                            </div>
                          ) : (
                            <>
                              <textarea
                                value={personaText}
                                onChange={(e) => {
                                  if (e.target.value.length <= 2000) {
                                    setLocalPersona(agent.agentId, e.target.value);
                                  }
                                }}
                                placeholder={`Define this agent's persona, behavior, and style.\n\nExamples:\n• "You are a cautious security analyst. Always check for vulnerabilities first."\n• "Respond concisely. Prioritize performance over readability."\n• "You speak Korean. Use formal tone (존댓말)."`}
                                className="input-field w-full text-sm resize-none font-mono"
                                rows={5}
                                style={{ lineHeight: '1.5' }}
                              />
                              <div className="flex items-center justify-between mt-2">
                                <p className="text-xs text-text-tertiary">
                                  This prompt is injected into the agent's system instructions during execution.
                                </p>
                                <button
                                  onClick={() => handleSavePersona(agent.agentId)}
                                  disabled={isPersonaSaving}
                                  className="btn-secondary text-xs px-3 py-1.5 flex items-center gap-1.5"
                                >
                                  {isPersonaSaving ? (
                                    <Loader2 size={12} className="animate-spin" />
                                  ) : (
                                    <Save size={12} />
                                  )}
                                  Save
                                </button>
                              </div>
                            </>
                          )}
                        </div>
                      </motion.div>
                    )}
                  </AnimatePresence>
                </div>
              );
            })}
          </div>
        </div>
      ))}

      {/* Empty state */}
      {!isLoading && assignments.length === 0 && (
        <div className="card p-8">
          <EmptyState
            icon={<Users size={40} />}
            title="No agents found"
            description="Purchase agents from the marketplace to configure their brains."
          />
        </div>
      )}

      {error && (
        <div className="p-3 rounded-lg bg-black/5 border border-black/10 text-sm text-gray-400">
          {error}
        </div>
      )}
    </motion.div>
  );
}

/* ========== SMTP / Email Settings ========== */
function SmtpSettings() {
  const [host, setHost] = useState('');
  const [port, setPort] = useState('587');
  const [secure, setSecure] = useState(false);
  const [user, setUser] = useState('');
  const [pass, setPass] = useState('');
  const [from, setFrom] = useState('');
  const [showPass, setShowPass] = useState(false);
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);
  const [hasConfig, setHasConfig] = useState(false);

  useEffect(() => {
    loadSmtpConfig();
  }, []);

  const loadSmtpConfig = async () => {
    try {
      if (typeof window !== 'undefined' && (window as any).electronAPI?.getSmtpConfig) {
        const config = await (window as any).electronAPI.getSmtpConfig();
        if (config) {
          setHost(config.host || '');
          setPort(config.port || '587');
          setSecure(config.secure === 'true' || config.secure === true);
          setUser(config.user || '');
          setFrom(config.from || '');
          setHasConfig(!!config.host);
        }
      }
    } catch (err) {
      console.error('Failed to load SMTP config:', err);
    }
  };

  const handleSave = async () => {
    setSaving(true);
    try {
      if (typeof window !== 'undefined' && (window as any).electronAPI?.saveSmtpConfig) {
        await (window as any).electronAPI.saveSmtpConfig({
          host,
          port,
          secure: secure ? 'true' : 'false',
          user,
          pass: pass || undefined,
          from: from || user,
        });
        toast.success('SMTP settings saved. Restart services for changes to take effect.');
        setPass('');
        await loadSmtpConfig();
      } else {
        toast.error('SMTP configuration requires the desktop app');
      }
    } catch (err: any) {
      toast.error(err.message || 'Failed to save SMTP settings');
    } finally {
      setSaving(false);
    }
  };

  const handleTest = async () => {
    setTesting(true);
    try {
      const res = await api.post<any>('/api/auth/test-smtp', {});
      if (res?.success || res === true) {
        toast.success('SMTP connection successful!');
      } else {
        toast.error(res?.message || 'SMTP test failed');
      }
    } catch (err: any) {
      toast.error(err.message || 'SMTP test failed — check your settings');
    } finally {
      setTesting(false);
    }
  };

  return (
    <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="space-y-6">
      <div>
        <h2 className="text-lg font-semibold">Email (SMTP) Configuration</h2>
        <p className="text-sm text-text-secondary mt-1">
          Configure SMTP to enable email verification, password resets, and notifications.
        </p>
      </div>

      {/* Status */}
      <div className="card p-4">
        <div className="flex items-center gap-3">
          <div className={`w-3 h-3 rounded-full ${hasConfig ? 'bg-green-400' : 'bg-gray-600'}`} />
          <span className="font-medium text-sm">
            {hasConfig ? 'SMTP Configured' : 'SMTP Not Configured'}
          </span>
        </div>
        {!hasConfig && (
          <p className="text-xs text-text-tertiary mt-2">
            Without SMTP, email verification will be auto-approved (desktop mode).
          </p>
        )}
      </div>

      {/* Form */}
      <div className="card p-5 space-y-4">
        <div className="grid grid-cols-2 gap-4">
          <div>
            <label className="text-sm text-text-secondary mb-2 block">SMTP Host</label>
            <input
              type="text"
              value={host}
              onChange={(e) => setHost(e.target.value)}
              placeholder="smtp.gmail.com"
              className="w-full bg-bg-elevated border border-border-primary rounded-lg px-4 py-2.5 text-sm focus:outline-none focus:border-black/40"
            />
          </div>
          <div>
            <label className="text-sm text-text-secondary mb-2 block">Port</label>
            <input
              type="text"
              value={port}
              onChange={(e) => setPort(e.target.value)}
              placeholder="587"
              className="w-full bg-bg-elevated border border-border-primary rounded-lg px-4 py-2.5 text-sm focus:outline-none focus:border-black/40"
            />
          </div>
        </div>

        <div className="flex items-center gap-3">
          <button
            onClick={() => setSecure(!secure)}
            className={`w-10 h-5 rounded-full transition-colors ${secure ? 'bg-accent' : 'bg-bg-elevated border border-border-primary'}`}
          >
            <div className={`w-4 h-4 rounded-full bg-white transition-transform ${secure ? 'translate-x-5' : 'translate-x-0.5'}`} />
          </button>
          <span className="text-sm text-text-secondary">
            SSL/TLS {secure ? '(Port 465)' : '— STARTTLS will be used for port 587'}
          </span>
        </div>

        <div>
          <label className="text-sm text-text-secondary mb-2 block">Username / Email</label>
          <input
            type="text"
            value={user}
            onChange={(e) => setUser(e.target.value)}
            placeholder="you@gmail.com"
            className="w-full bg-bg-elevated border border-border-primary rounded-lg px-4 py-2.5 text-sm focus:outline-none focus:border-black/40"
          />
        </div>

        <div>
          <label className="text-sm text-text-secondary mb-2 block">Password / App Password</label>
          <div className="relative">
            <input
              type={showPass ? 'text' : 'password'}
              value={pass}
              onChange={(e) => setPass(e.target.value)}
              placeholder={hasConfig ? '••••••••••••••••' : 'App password or SMTP password'}
              className="w-full bg-bg-elevated border border-border-primary rounded-lg px-4 py-2.5 pr-10 text-sm focus:outline-none focus:border-black/40"
            />
            <button
              onClick={() => setShowPass(!showPass)}
              className="absolute right-3 top-1/2 -translate-y-1/2 text-text-tertiary hover:text-text-primary"
            >
              {showPass ? <EyeOff size={14} /> : <Eye size={14} />}
            </button>
          </div>
        </div>

        <div>
          <label className="text-sm text-text-secondary mb-2 block">From Address (optional)</label>
          <input
            type="text"
            value={from}
            onChange={(e) => setFrom(e.target.value)}
            placeholder={user || 'noreply@yourdomain.com'}
            className="w-full bg-bg-elevated border border-border-primary rounded-lg px-4 py-2.5 text-sm focus:outline-none focus:border-black/40"
          />
          <p className="text-xs text-text-tertiary mt-1">Defaults to the username if left blank.</p>
        </div>

        <div className="flex items-center gap-3 pt-2">
          <Button
            size="sm"
            icon={<Save size={14} />}
            onClick={handleSave}
            disabled={saving || !host || !user}
          >
            {saving ? 'Saving...' : 'Save SMTP Settings'}
          </Button>
          <Button
            size="sm"
            variant="ghost"
            icon={<TestTube size={14} />}
            onClick={handleTest}
            disabled={testing || !hasConfig}
          >
            {testing ? 'Testing...' : 'Test Connection'}
          </Button>
        </div>
      </div>

      {/* Info */}
      <div className="card p-4 border-l-2 border-blue-500/50">
        <div className="flex gap-3">
          <Mail size={16} className="text-blue-400/70 mt-0.5 shrink-0" />
          <div className="text-xs text-text-tertiary space-y-1">
            <p><strong>Gmail:</strong> Use <span className="text-text-secondary">smtp.gmail.com</span>, port 587, and an <span className="text-text-secondary">App Password</span> (not your regular password).</p>
            <p><strong>App Password:</strong> Google Account → Security → 2-Step Verification → App Passwords.</p>
            <p>After saving, restart services for changes to take effect.</p>
          </div>
        </div>
      </div>
    </motion.div>
  );
}

/* ========== Payment Settings (Stripe) ========== */
function PaymentSettings() {
  const [secretKey, setSecretKey] = useState('');
  const [webhookSecret, setWebhookSecret] = useState('');
  const [hasSecretKey, setHasSecretKey] = useState(false);
  const [hasWebhookSecret, setHasWebhookSecret] = useState(false);
  const [showKey, setShowKey] = useState(false);
  const [showWebhook, setShowWebhook] = useState(false);
  const [saving, setSaving] = useState(false);
  const [stripeStatus, setStripeStatus] = useState<any>(null);

  useEffect(() => {
    loadStripeConfig();
    checkStripeStatus();
  }, []);

  const loadStripeConfig = async () => {
    try {
      if (typeof window !== 'undefined' && (window as any).electronAPI?.getStripeConfig) {
        const config = await (window as any).electronAPI.getStripeConfig();
        setHasSecretKey(config.hasSecretKey);
        setHasWebhookSecret(config.hasWebhookSecret);
      }
    } catch (err) {
      console.error('Failed to load Stripe config:', err);
    }
  };

  const checkStripeStatus = async () => {
    try {
      const res = await api.stripe.getStatus();
      setStripeStatus(res || {});
    } catch (err) {
      // Stripe not configured
    }
  };

  const handleSave = async () => {
    setSaving(true);
    try {
      if (typeof window !== 'undefined' && (window as any).electronAPI?.saveStripeKeys) {
        const result = await (window as any).electronAPI.saveStripeKeys({
          secretKey: secretKey || undefined,
          webhookSecret: webhookSecret || undefined,
        });
        toast.success(result.message || 'Stripe keys saved');
        setSecretKey('');
        setWebhookSecret('');
        await loadStripeConfig();
      } else {
        toast.error('Stripe key management requires the desktop app');
      }
    } catch (err: any) {
      toast.error(err.message || 'Failed to save');
    } finally {
      setSaving(false);
    }
  };

  return (
    <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="space-y-6">
      <div>
        <h2 className="text-lg font-semibold">Payment Configuration</h2>
        <p className="text-sm text-text-secondary mt-1">
          Connect Stripe to enable real-money credit purchases. Keys are encrypted and stored locally.
        </p>
      </div>

      {/* Status */}
      <div className="card p-4">
        <div className="flex items-center gap-3 mb-3">
          <div className={`w-3 h-3 rounded-full ${stripeStatus?.enabled ? 'bg-green-400' : 'bg-gray-600'}`} />
          <span className="font-medium text-sm">
            {stripeStatus?.enabled ? 'Stripe Connected' : 'Stripe Not Connected'}
          </span>
        </div>
        {!stripeStatus?.enabled && (
          <p className="text-xs text-text-tertiary">
            Add your Stripe Secret Key below and restart services to enable card payments.
          </p>
        )}
      </div>

      {/* Key inputs */}
      <div className="card p-5 space-y-4">
        <div>
          <label className="text-sm text-text-secondary mb-2 block">
            Stripe Secret Key {hasSecretKey && <span className="text-green-400 text-xs ml-2">● Configured</span>}
          </label>
          <div className="flex gap-2">
            <div className="relative flex-1">
              <input
                type={showKey ? 'text' : 'password'}
                value={secretKey}
                onChange={(e) => setSecretKey(e.target.value)}
                placeholder={hasSecretKey ? '••••••••••••••••••••' : 'sk_live_... or sk_test_...'}
                className="w-full bg-bg-elevated border border-border-primary rounded-lg px-4 py-2.5 pr-10 text-sm focus:outline-none focus:border-black/40"
              />
              <button
                onClick={() => setShowKey(!showKey)}
                className="absolute right-3 top-1/2 -translate-y-1/2 text-text-tertiary hover:text-text-primary"
              >
                {showKey ? <EyeOff size={14} /> : <Eye size={14} />}
              </button>
            </div>
          </div>
        </div>

        <div>
          <label className="text-sm text-text-secondary mb-2 block">
            Webhook Secret (optional) {hasWebhookSecret && <span className="text-green-400 text-xs ml-2">● Configured</span>}
          </label>
          <div className="flex gap-2">
            <div className="relative flex-1">
              <input
                type={showWebhook ? 'text' : 'password'}
                value={webhookSecret}
                onChange={(e) => setWebhookSecret(e.target.value)}
                placeholder={hasWebhookSecret ? '••••••••••••••••••••' : 'whsec_...'}
                className="w-full bg-bg-elevated border border-border-primary rounded-lg px-4 py-2.5 pr-10 text-sm focus:outline-none focus:border-black/40"
              />
              <button
                onClick={() => setShowWebhook(!showWebhook)}
                className="absolute right-3 top-1/2 -translate-y-1/2 text-text-tertiary hover:text-text-primary"
              >
                {showWebhook ? <EyeOff size={14} /> : <Eye size={14} />}
              </button>
            </div>
          </div>
        </div>

        <div className="flex items-center gap-3 pt-2">
          <Button
            size="sm"
            icon={<Save size={14} />}
            onClick={handleSave}
            disabled={saving || (!secretKey && !webhookSecret)}
          >
            {saving ? 'Saving...' : 'Save Keys'}
          </Button>
          <span className="text-xs text-text-tertiary">
            After saving, restart services for changes to take effect.
          </span>
        </div>
      </div>

      {/* Info */}
      <div className="card p-4 border-l-2 border-yellow-500/50">
        <div className="flex gap-3">
          <AlertCircle size={16} className="text-yellow-500/70 mt-0.5 shrink-0" />
          <div className="text-xs text-text-tertiary space-y-1">
            <p>Get your Stripe keys from <span className="text-text-secondary">dashboard.stripe.com/apikeys</span></p>
            <p>Use test keys (sk_test_...) during development, live keys (sk_live_...) for production.</p>
            <p>Webhook secret is needed if you configure a Stripe webhook endpoint for payment confirmations.</p>
          </div>
        </div>
      </div>
    </motion.div>
  );
}