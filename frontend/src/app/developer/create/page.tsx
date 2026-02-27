'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { motion } from 'framer-motion';
import {
  ArrowLeft, Save, Upload, Plus, X, Info
} from 'lucide-react';
import { Button } from '@/components/common/Button';
import { api } from '@/lib/api';
import { getCategoryLabel } from '@/lib/utils';
import Link from 'next/link';
import toast from 'react-hot-toast';

const CATEGORIES = [
  'CODING', 'DESIGN', 'RESEARCH', 'DATA_ANALYSIS', 'WRITING',
  'AUTOMATION', 'SYSTEM', 'PRODUCTIVITY', 'MONITORING', 'OTHER',
];

const CAPABILITIES = [
  'MOUSE_CONTROL', 'KEYBOARD_INPUT', 'SCREEN_CAPTURE', 'APP_MANAGEMENT',
  'FILE_SYSTEM', 'BROWSER_CONTROL', 'CLIPBOARD', 'SYSTEM_COMMANDS',
  'WINDOW_MANAGEMENT', 'AUDIO_CONTROL', 'NETWORK',
];

const PRICING_MODELS = [
  { value: 'FREE', label: 'Free' },
  { value: 'ONE_TIME', label: 'One-Time Purchase' },
  { value: 'SUBSCRIPTION', label: 'Monthly Subscription' },
  { value: 'USAGE', label: 'Per Execution' },
];

export default function CreateAgentPage() {
  const router = useRouter();
  const [saving, setSaving] = useState(false);
  const [form, setForm] = useState({
    name: '',
    description: '',
    shortDescription: '',
    category: 'CODING',
    pricingModel: 'FREE',
    price: 0,
    version: '1.0.0',
    capabilities: [] as string[],
    tags: [] as string[],
    repository: '',
    documentation: '',
  });
  const [tagInput, setTagInput] = useState('');

  const updateForm = (field: string, value: any) => {
    setForm(prev => ({ ...prev, [field]: value }));
  };

  const toggleCapability = (cap: string) => {
    const caps = form.capabilities.includes(cap)
      ? form.capabilities.filter(c => c !== cap)
      : [...form.capabilities, cap];
    updateForm('capabilities', caps);
  };

  const addTag = () => {
    const tag = tagInput.trim().toLowerCase();
    if (tag && !form.tags.includes(tag)) {
      updateForm('tags', [...form.tags, tag]);
      setTagInput('');
    }
  };

  const removeTag = (tag: string) => {
    updateForm('tags', form.tags.filter(t => t !== tag));
  };

  const handleSubmit = async () => {
    if (!form.name.trim()) { toast.error('Name is required'); return; }
    if (!form.description.trim()) { toast.error('Description is required'); return; }
    if (form.pricingModel !== 'FREE' && form.price <= 0) { toast.error('Set a valid price'); return; }

    setSaving(true);
    try {
      const res = await api.agents.create({
        name: form.name,
        description: form.shortDescription || form.description.slice(0, 500),
        longDescription: form.description,
        category: form.category,
        pricingModel: form.pricingModel === 'SUBSCRIPTION' ? 'SUBSCRIPTION_MONTHLY'
          : form.pricingModel === 'USAGE' ? 'PAY_PER_USE'
          : form.pricingModel,
        price: form.pricingModel === 'FREE' ? 0 : form.price,
        tags: form.tags,
        capabilities: form.capabilities,
        permissions: form.capabilities,
        runtime: 'python',
        entryPoint: 'main.py',
      });
      toast.success('Agent created!');
      router.push('/developer');
    } catch (err: any) {
      toast.error(err.message || 'Failed to create agent');
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="max-w-3xl mx-auto space-y-6">
      <Link href="/developer" className="inline-flex items-center gap-2 text-sm text-text-tertiary hover:text-text-primary transition-colors">
        <ArrowLeft size={16} /> Back to Developer Portal
      </Link>

      <h1 className="text-2xl font-bold">Create New Agent</h1>

      <div className="space-y-6">
        {/* Basic Info */}
        <Section title="Basic Information">
          <div className="space-y-4">
            <Field label="Name" required>
              <input value={form.name} onChange={e => updateForm('name', e.target.value)} className="input-field w-full" placeholder="My Awesome Agent" />
            </Field>
            <Field label="Short Description" required>
              <input value={form.shortDescription} onChange={e => updateForm('shortDescription', e.target.value)} className="input-field w-full" placeholder="Brief one-line description" maxLength={120} />
              <span className="text-[10px] text-text-tertiary">{form.shortDescription.length}/120</span>
            </Field>
            <Field label="Full Description" required>
              <textarea value={form.description} onChange={e => updateForm('description', e.target.value)} className="input-field w-full h-32 resize-y" placeholder="Detailed description of what this agent does, how it works, and its features..." />
            </Field>
            <div className="grid grid-cols-2 gap-4">
              <Field label="Category">
                <select value={form.category} onChange={e => updateForm('category', e.target.value)} className="input-field w-full">
                  {CATEGORIES.map(c => <option key={c} value={c}>{getCategoryLabel(c)}</option>)}
                </select>
              </Field>
              <Field label="Version">
                <input value={form.version} onChange={e => updateForm('version', e.target.value)} className="input-field w-full" placeholder="1.0.0" />
              </Field>
            </div>
          </div>
        </Section>

        {/* Pricing */}
        <Section title="Pricing">
          <div className="space-y-4">
            <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
              {PRICING_MODELS.map(pm => (
                <button
                  key={pm.value}
                  onClick={() => updateForm('pricingModel', pm.value)}
                  className={`p-3 rounded-xl text-center text-sm transition-all border ${
                    form.pricingModel === pm.value
                      ? 'bg-accent text-white border-accent'
                      : 'bg-bg-secondary border-border-primary hover:border-border-secondary text-text-secondary'
                  }`}
                >
                  {pm.label}
                </button>
              ))}
            </div>
            {form.pricingModel !== 'FREE' && (
              <Field label={`Price (USD)${form.pricingModel === 'SUBSCRIPTION' ? ' / month' : form.pricingModel === 'USAGE' ? ' / run' : ''}`}>
                <div className="relative">
                  <span className="absolute left-3 top-1/2 -translate-y-1/2 text-text-tertiary">$</span>
                  <input
                    type="number"
                    value={form.price}
                    onChange={e => updateForm('price', parseFloat(e.target.value) || 0)}
                    className="input-field w-full pl-7"
                    placeholder="9.99"
                    min="0"
                    step="0.01"
                  />
                </div>
              </Field>
            )}
          </div>
        </Section>

        {/* Capabilities */}
        <Section title="OS Capabilities" hint="Select what OS controls this agent needs">
          <div className="grid grid-cols-2 md:grid-cols-3 gap-2">
            {CAPABILITIES.map(cap => (
              <button
                key={cap}
                onClick={() => toggleCapability(cap)}
                className={`px-3 py-2 rounded-lg text-xs text-left transition-all border ${
                  form.capabilities.includes(cap)
                    ? 'bg-bg-active border-border-active text-text-primary'
                    : 'bg-bg-secondary border-border-primary text-text-secondary hover:border-border-secondary'
                }`}
              >
                {cap.replace(/_/g, ' ')}
              </button>
            ))}
          </div>
        </Section>

        {/* Tags */}
        <Section title="Tags">
          <div className="flex flex-wrap gap-2 mb-3">
            {form.tags.map(tag => (
              <span key={tag} className="inline-flex items-center gap-1 px-2 py-1 rounded-md text-xs bg-bg-elevated border border-border-primary text-text-secondary">
                #{tag}
                <button onClick={() => removeTag(tag)}><X size={10} className="text-text-tertiary hover:text-error" /></button>
              </span>
            ))}
          </div>
          <div className="flex gap-2">
            <input
              value={tagInput}
              onChange={e => setTagInput(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && (e.preventDefault(), addTag())}
              className="input-field flex-1"
              placeholder="Add a tag..."
            />
            <Button variant="secondary" size="sm" onClick={addTag}>Add</Button>
          </div>
        </Section>

        {/* Links */}
        <Section title="Links (Optional)">
          <div className="space-y-4">
            <Field label="Repository URL">
              <input value={form.repository} onChange={e => updateForm('repository', e.target.value)} className="input-field w-full" placeholder="https://github.com/..." />
            </Field>
            <Field label="Documentation URL">
              <input value={form.documentation} onChange={e => updateForm('documentation', e.target.value)} className="input-field w-full" placeholder="https://docs.example.com" />
            </Field>
          </div>
        </Section>

        {/* Submit */}
        <div className="flex items-center justify-between py-6 border-t border-border-primary">
          <p className="text-xs text-text-tertiary">
            Agent will be saved as a draft. Publish from the developer portal.
          </p>
          <div className="flex gap-3">
            <Button variant="secondary" onClick={() => router.push('/developer')}>Cancel</Button>
            <Button onClick={handleSubmit} loading={saving} icon={<Save size={14} />}>Create Agent</Button>
          </div>
        </div>
      </div>
    </div>
  );
}

function Section({ title, hint, children }: { title: string; hint?: string; children: React.ReactNode }) {
  return (
    <div className="card p-5 space-y-4">
      <div>
        <h3 className="font-semibold">{title}</h3>
        {hint && <p className="text-xs text-text-tertiary mt-0.5">{hint}</p>}
      </div>
      {children}
    </div>
  );
}

function Field({ label, required, children }: { label: string; required?: boolean; children: React.ReactNode }) {
  return (
    <div>
      <label className="block text-xs font-medium text-text-secondary mb-1.5">
        {label} {required && <span className="text-error">*</span>}
      </label>
      {children}
    </div>
  );
}
