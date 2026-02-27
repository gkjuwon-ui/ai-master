'use client';

import { useState, useEffect, useRef } from 'react';
import { motion } from 'framer-motion';
import {
  Code2, Package, Key, DollarSign, Plus, Trash2,
  Copy, Eye, EyeOff, Upload, TrendingUp, Download,
  Star, Users, ArrowRight, Shield, CheckCircle2,
  BarChart3, ExternalLink, FileCode, Terminal
} from 'lucide-react';
import { useAuthStore } from '@/store/authStore';
import { Button } from '@/components/common/Button';
import { Modal } from '@/components/common/Modal';
import { Loading, EmptyState } from '@/components/common/Loading';
import { api } from '@/lib/api';
import { formatPrice, formatNumber, formatDate, getCategoryLabel } from '@/lib/utils';
import Link from 'next/link';
import toast from 'react-hot-toast';

export default function DeveloperPage() {
  const { user, isAuthenticated } = useAuthStore();
  const [activeTab, setActiveTab] = useState<'overview' | 'agents' | 'api-keys' | 'earnings'>('overview');
  const [stats, setStats] = useState<any>(null);
  const [agents, setAgents] = useState<any[]>([]);
  const [apiKeys, setApiKeys] = useState<any[]>([]);
  const [earnings, setEarnings] = useState<any>(null);
  const [loading, setLoading] = useState(true);

  const isDeveloper = user?.role === 'DEVELOPER' || user?.role === 'ADMIN';

  useEffect(() => {
    if (isAuthenticated && isDeveloper) {
      loadData();
    } else {
      setLoading(false);
    }
  }, [isAuthenticated, isDeveloper]);

  const loadData = async () => {
    setLoading(true);
    try {
      const [statsRes, agentsRes, keysRes, earningsRes] = await Promise.all([
        api.developer.getStats().catch(() => null),
        api.developer.getAgents().catch(() => []),
        api.developer.getApiKeys().catch(() => []),
        api.developer.getEarnings().catch(() => null),
      ]);
      setStats(statsRes);
      setAgents(agentsRes || []);
      setApiKeys(keysRes || []);
      setEarnings(earningsRes);
    } finally {
      setLoading(false);
    }
  };

  if (!isAuthenticated) {
    return (
      <div className="flex items-center justify-center h-full">
        <EmptyState
          icon={<Code2 size={48} />}
          title="Sign in to access developer portal"
          action={{ label: 'Sign In', onClick: () => window.location.href = '/auth/login' }}
        />
      </div>
    );
  }

  if (!isDeveloper) {
    return (
      <div className="max-w-lg mx-auto mt-20 text-center space-y-6">
        <Code2 size={48} className="text-text-tertiary mx-auto" />
        <h1 className="text-2xl font-bold">Developer Portal</h1>
        <p className="text-text-secondary">
          Upgrade to a developer account to publish agents, earn from sales, and access the SDK.
        </p>
        <Link href="/settings">
          <Button icon={<Shield size={14} />}>Upgrade Account</Button>
        </Link>
      </div>
    );
  }

  if (loading) return <Loading />;

  return (
    <div className="max-w-6xl mx-auto space-y-6 px-6 py-12">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold">Developer Portal</h1>
          <p className="text-text-secondary mt-1">Manage agents, API keys, and earnings</p>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="secondary" icon={<Terminal size={14} />} onClick={() => window.location.href = '/developer/ide'}>
            Open IDE
          </Button>
          <Button icon={<Plus size={14} />} onClick={() => window.location.href = '/developer/create'}>
            Create Agent
          </Button>
        </div>
      </div>

      {/* Tabs */}
      <div className="flex gap-1 border-b border-border-primary">
        {[
          { key: 'overview', label: 'Overview', icon: <BarChart3 size={14} /> },
          { key: 'agents', label: 'My Agents', icon: <Package size={14} /> },
          { key: 'api-keys', label: 'API Keys', icon: <Key size={14} /> },
          { key: 'earnings', label: 'Earnings', icon: <DollarSign size={14} /> },
        ].map((tab) => (
          <button
            key={tab.key}
            onClick={() => setActiveTab(tab.key as any)}
            className={`flex items-center gap-2 px-4 py-2.5 text-sm font-medium transition-all border-b-2 -mb-px ${
              activeTab === tab.key
                ? 'text-white border-white'
                : 'text-text-tertiary border-transparent hover:text-text-secondary'
            }`}
          >
            {tab.icon}
            {tab.label}
          </button>
        ))}
      </div>

      {/* Overview */}
      {activeTab === 'overview' && (
        <DevOverview stats={stats} agents={agents} earnings={earnings} />
      )}

      {/* Agents */}
      {activeTab === 'agents' && (
        <DevAgents agents={agents} onRefresh={loadData} />
      )}

      {/* API Keys */}
      {activeTab === 'api-keys' && (
        <DevApiKeys apiKeys={apiKeys} onRefresh={loadData} />
      )}

      {/* Earnings */}
      {activeTab === 'earnings' && (
        <DevEarnings earnings={earnings} />
      )}
    </div>
  );
}

/* ========== Overview ========== */
function DevOverview({ stats, agents, earnings }: { stats: any; agents: any[]; earnings: any }) {
  return (
    <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="space-y-6">
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <StatCard icon={<Package size={20} />} label="Published Agents" value={stats?.agentCount || agents.length} />
        <StatCard icon={<Download size={20} />} label="Total Downloads" value={stats?.totalDownloads || 0} />
        <StatCard icon={<Star size={20} />} label="Avg Rating" value={stats?.avgRating?.toFixed(1) || '0.0'} isString />
        <StatCard icon={<DollarSign size={20} />} label="Total Earnings" value={`$${(earnings?.totalEarnings || 0).toFixed(2)}`} isString />
      </div>

      {/* Quick actions */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div className="card p-5 group hover:border-accent-primary/30 transition-colors cursor-pointer" onClick={() => window.location.href = '/developer/ide'}>
          <h3 className="font-semibold mb-3 flex items-center gap-2">
            <Code2 size={16} className="text-accent-primary" />
            Developer IDE
            <ArrowRight size={14} className="ml-auto text-text-tertiary group-hover:text-accent-primary transition-colors" />
          </h3>
          <p className="text-sm text-text-secondary mb-4">
            Build agents visually with our in-app IDE. Monaco editor, sandbox preview, imitation learning, and AI code generation.
          </p>
          <div className="flex gap-2">
            <span className="text-[10px] px-2 py-0.5 rounded-full bg-accent-primary/10 text-accent-primary">Monaco Editor</span>
            <span className="text-[10px] px-2 py-0.5 rounded-full bg-green-500/10 text-green-400">Live Sandbox</span>
            <span className="text-[10px] px-2 py-0.5 rounded-full bg-purple-500/10 text-purple-400">AI Assist</span>
          </div>
        </div>
        <div className="card p-5">
          <h3 className="font-semibold mb-3 flex items-center gap-2">
            <Upload size={16} className="text-text-tertiary" />
            Publish Agent
          </h3>
          <p className="text-sm text-text-secondary mb-4">
            Package and upload your agent. Set pricing, add descriptions, and publish to the marketplace.
          </p>
          <Link href="/developer/create">
            <Button size="sm" icon={<Plus size={12} />}>Create New Agent</Button>
          </Link>
        </div>
      </div>
    </motion.div>
  );
}

function StatCard({ icon, label, value, isString }: { icon: React.ReactNode; label: string; value: number | string; isString?: boolean }) {
  return (
    <div className="card p-4">
      <div className="flex items-center gap-3">
        <div className="text-text-tertiary">{icon}</div>
        <div>
          <div className="text-2xl font-bold">{isString ? value : formatNumber(value as number)}</div>
          <div className="text-xs text-text-tertiary">{label}</div>
        </div>
      </div>
    </div>
  );
}

/* ========== Agents Tab ========== */
function DevAgents({ agents, onRefresh }: { agents: any[]; onRefresh: () => void }) {
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [uploadingId, setUploadingId] = useState<string | null>(null);

  const handlePublish = async (id: string) => {
    try {
      await api.agents.publish(id);
      toast.success('Agent published');
      onRefresh();
    } catch (err: any) {
      toast.error(err.message || 'Failed to publish');
    }
  };

  const handleUnpublish = async (id: string) => {
    try {
      await api.agents.unpublish(id);
      toast.success('Agent unpublished');
      onRefresh();
    } catch (err: any) {
      toast.error(err.message || 'Failed');
    }
  };

  const handleDelete = async (id: string) => {
    if (!confirm('Delete this agent permanently?')) return;
    try {
      await api.agents.delete(id);
      toast.success('Agent deleted');
      onRefresh();
    } catch (err: any) {
      toast.error(err.message || 'Failed to delete');
    }
  };

  const handleUploadBundle = (agentId: string) => {
    setUploadingId(agentId);
    fileInputRef.current?.click();
  };

  const handleFileSelected = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file || !uploadingId) return;
    
    const maxSize = 50 * 1024 * 1024; // 50MB
    if (file.size > maxSize) {
      toast.error('Bundle exceeds 50MB limit');
      return;
    }

    try {
      toast.loading('Uploading bundle...', { id: 'upload' });
      await api.developer.uploadBundle(uploadingId, file);
      toast.success('Bundle uploaded successfully', { id: 'upload' });
      onRefresh();
    } catch (err: any) {
      toast.error(err.message || 'Upload failed', { id: 'upload' });
    } finally {
      setUploadingId(null);
      e.target.value = '';
    }
  };

  return (
    <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="space-y-4">
      {/* Hidden file input for bundle upload */}
      <input
        ref={fileInputRef}
        type="file"
        accept=".zip,.tar.gz,.tgz"
        onChange={handleFileSelected}
        className="hidden"
      />

      {agents.length === 0 ? (
        <div className="card p-8">
          <EmptyState
            icon={<Package size={40} />}
            title="No agents yet"
            description="Create your first agent and publish it to the marketplace."
            action={{ label: 'Create Agent', onClick: () => window.location.href = '/developer/create' }}
          />
        </div>
      ) : (
        agents.map((agent) => (
          <div key={agent.id} className="card p-4 flex items-center gap-4">
            <div className="w-12 h-12 rounded-xl bg-bg-elevated flex items-center justify-center text-text-tertiary">
              <Package size={20} />
            </div>
            <div className="flex-1 min-w-0">
              <div className="font-medium flex items-center gap-2">
                {agent.name}
                <span className={`text-[10px] px-1.5 py-0.5 rounded ${
                  agent.status === 'PUBLISHED' ? 'bg-success/20 text-success' :
                  agent.status === 'DRAFT' ? 'bg-warning/20 text-warning' :
                  'bg-bg-elevated text-text-tertiary'
                }`}>
                  {agent.status}
                </span>
              </div>
              <div className="text-xs text-text-tertiary flex items-center gap-3 mt-0.5">
                <span>{getCategoryLabel(agent.category)}</span>
                <span>{formatPrice(agent.price)}</span>
                <span>{formatNumber(agent.downloadCount || 0)} downloads</span>
                <span>v{agent.version || '1.0.0'}</span>
              </div>
            </div>
            <div className="flex items-center gap-2">
              <Button variant="secondary" size="sm" onClick={() => handleUploadBundle(agent.id)} icon={<Upload size={12} />}>Upload</Button>
              {agent.status === 'DRAFT' ? (
                <Button variant="secondary" size="sm" onClick={() => handlePublish(agent.id)}>Publish</Button>
              ) : (
                <Button variant="ghost" size="sm" onClick={() => handleUnpublish(agent.id)}>Unpublish</Button>
              )}
              <Button variant="ghost" size="sm" onClick={() => handleDelete(agent.id)} icon={<Trash2 size={12} />} className="text-error hover:text-error" />
            </div>
          </div>
        ))
      )}
    </motion.div>
  );
}

/* ========== API Keys Tab ========== */
function DevApiKeys({ apiKeys, onRefresh }: { apiKeys: any[]; onRefresh: () => void }) {
  const [showCreate, setShowCreate] = useState(false);
  const [keyName, setKeyName] = useState('');
  const [newKey, setNewKey] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);

  const handleCreate = async () => {
    if (!keyName.trim()) return;
    setCreating(true);
    try {
      const res = await api.developer.createApiKey(keyName.trim());
      setNewKey(res?.key);
      toast.success('API key created');
      onRefresh();
    } catch (err: any) {
      toast.error(err.message || 'Failed to create key');
    } finally {
      setCreating(false);
    }
  };

  const handleDelete = async (id: string) => {
    if (!confirm('Revoke this API key?')) return;
    try {
      await api.developer.deleteApiKey(id);
      toast.success('API key revoked');
      onRefresh();
    } catch (err: any) {
      toast.error(err.message || 'Failed');
    }
  };

  const copyKey = (key: string) => {
    navigator.clipboard.writeText(key);
    toast.success('Copied to clipboard');
  };

  return (
    <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="space-y-4">
      <div className="flex items-center justify-between">
        <p className="text-sm text-text-secondary">
          API keys for programmatic access to the platform
        </p>
        <Button size="sm" icon={<Plus size={14} />} onClick={() => setShowCreate(true)}>
          Create Key
        </Button>
      </div>

      {/* Newly created key warning */}
      {newKey && (
        <div className="card p-4 border-warning/30 bg-warning/5">
          <div className="flex items-center gap-2 mb-2">
            <Key size={14} className="text-warning" />
            <span className="text-sm font-semibold text-warning">Save your API key now</span>
          </div>
          <p className="text-xs text-text-secondary mb-3">
            This key will only be shown once. Copy it and store it securely.
          </p>
          <div className="flex items-center gap-2">
            <code className="flex-1 bg-bg-primary px-3 py-2 rounded-lg text-xs font-mono text-text-primary break-all">
              {newKey}
            </code>
            <Button variant="secondary" size="sm" icon={<Copy size={12} />} onClick={() => copyKey(newKey)}>
              Copy
            </Button>
          </div>
        </div>
      )}

      {apiKeys.length === 0 && !newKey ? (
        <div className="card p-8">
          <EmptyState
            icon={<Key size={40} />}
            title="No API keys"
            description="Create an API key for programmatic access."
            action={{ label: 'Create Key', onClick: () => setShowCreate(true) }}
          />
        </div>
      ) : (
        <div className="space-y-2">
          {apiKeys.map((key) => (
            <div key={key.id} className="card p-4 flex items-center justify-between">
              <div>
                <div className="text-sm font-medium">{key.name}</div>
                <div className="text-xs text-text-tertiary">
                  Created {formatDate(key.createdAt)}
                  {key.lastUsedAt && ` · Last used ${formatDate(key.lastUsedAt)}`}
                </div>
              </div>
              <Button variant="ghost" size="sm" onClick={() => handleDelete(key.id)} icon={<Trash2 size={12} />} className="text-error hover:text-error">
                Revoke
              </Button>
            </div>
          ))}
        </div>
      )}

      {/* Create key modal */}
      <Modal isOpen={showCreate} onClose={() => { setShowCreate(false); setKeyName(''); }} title="Create API Key" size="sm">
        <div className="space-y-4">
          <div>
            <label className="block text-xs font-medium text-text-secondary mb-1.5">Key Name</label>
            <input
              value={keyName}
              onChange={e => setKeyName(e.target.value)}
              className="input-field w-full"
              placeholder="e.g., Production, Development"
              autoFocus
            />
          </div>
          <div className="flex justify-end gap-2">
            <Button variant="secondary" onClick={() => setShowCreate(false)}>Cancel</Button>
            <Button onClick={handleCreate} loading={creating} disabled={!keyName.trim()}>Create</Button>
          </div>
        </div>
      </Modal>
    </motion.div>
  );
}

/* ========== Earnings Tab ========== */
function DevEarnings({ earnings }: { earnings: any }) {
  return (
    <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="space-y-6">
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div className="card p-5">
          <div className="text-xs text-text-tertiary mb-1">Total Credits Earned</div>
          <div className="text-2xl font-bold">{earnings?.totalEarnings || 0}</div>
        </div>
        <div className="card p-5">
          <div className="text-xs text-text-tertiary mb-1">From Agent Sales</div>
          <div className="text-2xl font-bold">{earnings?.agentSales || 0}</div>
        </div>
        <div className="card p-5">
          <div className="text-xs text-text-tertiary mb-1">From Community</div>
          <div className="text-2xl font-bold text-success">{earnings?.communityEarnings || 0}</div>
        </div>
      </div>

      <div className="card p-5 space-y-3">
        <h3 className="font-semibold">Credit Economy</h3>
        <p className="text-sm text-text-secondary">
          You earn credits when users purchase your agents (you receive 85% of the sale price).
          Spend credits to purchase other agents from the marketplace.
        </p>
        <Link href="/credits" className="inline-flex items-center gap-2 text-sm text-accent hover:underline">
          View Credit Dashboard →
        </Link>
      </div>
    </motion.div>
  );
}
