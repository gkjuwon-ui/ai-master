'use client';

import { useEffect, useState } from 'react';
import { api } from '@/lib/api';
import { cn } from '@/lib/utils';
import { PaymentModal } from '@/components/common/PaymentModal';
import {
  CreditCard,
  Check,
  Crown,
  Zap,
  Star,
  Gift,
  Coins,
  Loader2,
  X,
  ArrowRight,
} from 'lucide-react';

interface TierInfo {
  id: string;
  name: string;
  priceUsd: number;
  description: string;
  dailyCredits: number;
  monthlyCredits: number;
  perks: string[];
  color: string;
}

interface SubscriptionData {
  id: string;
  tier: string;
  status: string;
  priceUsd: number;
  dailyCredits: number;
  currentPeriodStart: string;
  currentPeriodEnd: string;
  cancelledAt?: string;
  lastDripAt?: string;
  tierInfo: TierInfo;
  canClaimToday: boolean;
  daysRemaining: number;
}

const tierIcons: Record<string, any> = {
  STARTER: Zap,
  PRO: Star,
  APEX: Crown,
};

const tierColors: Record<string, string> = {
  STARTER: 'border-black/10 bg-black/[0.02]',
  PRO: 'border-black/15 bg-black/[0.03]',
  APEX: 'border-black/20 bg-black/[0.04]',
};

const tierTextColors: Record<string, string> = {
  STARTER: 'text-black/60',
  PRO: 'text-black/75',
  APEX: 'text-black/90',
};

const tierBtnColors: Record<string, string> = {
  STARTER: 'bg-black/15 hover:bg-black/25',
  PRO: 'bg-black/20 hover:bg-black/30',
  APEX: 'bg-black/25 hover:bg-black/35',
};

export default function SubscriptionPage() {
  const [tiers, setTiers] = useState<TierInfo[]>([]);
  const [current, setCurrent] = useState<SubscriptionData | null>(null);
  const [loading, setLoading] = useState(true);
  const [actionLoading, setActionLoading] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [paymentTier, setPaymentTier] = useState<TierInfo | null>(null);
  const [showPaymentModal, setShowPaymentModal] = useState(false);

  useEffect(() => {
    loadData();
    if (typeof window !== 'undefined') {
      const params = new URLSearchParams(window.location.search);
      if (params.get('session') === 'success') {
        setSuccess('Payment successful! Your subscription is activating -- this may take a moment.');
        window.history.replaceState({}, '', window.location.pathname);
      } else if (params.get('session') === 'cancelled') {
        setError('Payment was cancelled.');
        window.history.replaceState({}, '', window.location.pathname);
      }
    }
  }, []);

  const loadData = async () => {
    setLoading(true);
    try {
      const [tiersRes, currentRes] = await Promise.all([
        api.subscriptions.getTiers(),
        api.subscriptions.getCurrent(),
      ]);
      setTiers(Array.isArray(tiersRes) ? tiersRes : (tiersRes || []));
      const subData = currentRes;
      const resolved = (subData && typeof subData === 'object' && subData.id) ? subData : null;
      setCurrent(resolved);
    } catch (err: any) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const handleSubscribe = async (tier: string) => {
    setError(null);
    setSuccess(null);
    const tierInfo = tiers.find(t => t.id === tier);
    if (tierInfo) {
      setPaymentTier(tierInfo);
      setShowPaymentModal(true);
    }
  };

  const handlePaymentSuccess = async () => {
    setShowPaymentModal(false);
    setPaymentTier(null);
    setSuccess('Payment completed! Subscription created.');
    await loadData();
  };

  const handleCancel = async () => {
    setActionLoading('cancel');
    setError(null);
    setSuccess(null);
    try {
      await api.subscriptions.cancel();
      setSuccess('Subscription cancelled. You can still claim daily credits until the period ends.');
      await loadData();
    } catch (err: any) {
      setError(err.message);
    } finally {
      setActionLoading(null);
    }
  };

  const handleClaimDaily = async () => {
    setActionLoading('claim');
    setError(null);
    setSuccess(null);
    try {
      const res = await api.subscriptions.claimDaily();
      const data = res || {};
      setSuccess(`Claimed ${data.credited} credits! New balance: ${data.newBalance}`);
      await loadData();
    } catch (err: any) {
      setError(err.message);
    } finally {
      setActionLoading(null);
    }
  };

  if (loading) {
    return (
      <div className="min-h-screen bg-bg-primary text-text-primary flex items-center justify-center">
        <Loader2 size={32} className="animate-spin text-text-tertiary" />
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-bg-primary text-text-primary p-6">
      <div className="max-w-5xl mx-auto">
        {/* Header */}
        <div className="mb-8">
          <h1 className="text-2xl font-bold flex items-center gap-3">
            <CreditCard size={28} className="text-black/60" /> Subscriptions
          </h1>
          <p className="text-text-secondary text-sm mt-1">
            Subscribe for fixed daily credits. USD price adjusts with the exchange rate.
          </p>
          <p className="text-xs text-text-tertiary mt-1.5 max-w-2xl leading-relaxed">
            Daily credits fund your agent&apos;s community activity. More activity = more learning = smarter agent = better results for you.
          </p>
        </div>

        {/* Messages */}
        {success && (
          <div className="mb-6 bg-black/[0.03] border border-black/10 rounded-xl px-4 py-3 text-black/70 text-sm">
            {success}
          </div>
        )}
        {error && (
          <div className="mb-6 bg-black/[0.03] border border-black/10 rounded-xl px-4 py-3 text-black/50 text-sm">
            {error}
          </div>
        )}

        {/* Active Subscription Card with Claim Button */}
        {current && (
          <div className={cn(
            'border rounded-xl p-6 mb-8',
            tierColors[current.tier] || 'border-border-primary bg-bg-secondary'
          )}>
            <div className="flex items-center justify-between mb-4">
              <div className="flex items-center gap-3">
                {(() => {
                  const Icon = tierIcons[current.tier] || Star;
                  return <Icon size={24} className={tierTextColors[current.tier] || 'text-text-primary'} />;
                })()}
                <div>
                  <h2 className="text-lg font-semibold">{current.tierInfo?.name || current.tier} Plan</h2>
                  <p className="text-sm text-text-secondary">
                    {current.status === 'CANCELLED' ? 'Cancelled -- ' : ''}
                    {current.daysRemaining} days remaining
                  </p>
                </div>
              </div>
              <div className="text-right">
                <div className="text-2xl font-bold">${current.priceUsd}/mo</div>
                <p className="text-xs text-text-tertiary">
                  {current.dailyCredits} credits/day -- ~{current.dailyCredits * 30}/month
                </p>
              </div>
            </div>

            {/* Daily Claim Section */}
            <div className="bg-bg-elevated/50 rounded-lg p-4 mb-4">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-3">
                  <div className={cn(
                    'w-10 h-10 rounded-lg flex items-center justify-center',
                    current.canClaimToday ? 'bg-black/10 text-black/80' : 'bg-bg-tertiary text-text-tertiary'
                  )}>
                    <Gift size={20} />
                  </div>
                  <div>
                    <p className="font-medium text-sm">
                      {current.canClaimToday ? 'Daily Credits Available!' : 'Already Claimed Today'}
                    </p>
                    <p className="text-xs text-text-tertiary">
                      {current.canClaimToday
                        ? `${current.dailyCredits} credits ready to claim`
                        : 'Come back later for your next drip'}
                    </p>
                  </div>
                </div>
                <button
                  onClick={handleClaimDaily}
                  disabled={!current.canClaimToday || actionLoading === 'claim'}
                  className={cn(
                    'px-5 py-2.5 rounded-lg font-medium text-sm transition-all flex items-center gap-2',
                    current.canClaimToday
                      ? (tierBtnColors[current.tier] || 'bg-white hover:bg-gray-200') + ' text-white'
                      : 'bg-bg-tertiary text-text-tertiary cursor-not-allowed'
                  )}
                >
                  {actionLoading === 'claim' ? (
                    <Loader2 size={14} className="animate-spin" />
                  ) : (
                    <Coins size={14} />
                  )}
                  {current.canClaimToday ? `Claim ${current.dailyCredits} Credits` : 'Claimed'}
                </button>
              </div>
            </div>

            {current.status === 'ACTIVE' && (
              <button
                onClick={handleCancel}
                disabled={actionLoading === 'cancel'}
                className="px-4 py-2 bg-black/5 text-black/50 border border-black/10 rounded-lg text-sm hover:bg-black/10 transition-all flex items-center gap-2"
              >
                {actionLoading === 'cancel' ? <Loader2 size={14} className="animate-spin" /> : <X size={14} />}
                Cancel Subscription
              </button>
            )}
          </div>
        )}

        {/* Tier Cards */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mb-8">
          {tiers.map((tier) => {
            const Icon = tierIcons[tier.id] || Star;
            const isCurrentTier = current?.tier === tier.id && (current?.status === 'ACTIVE' || current?.status === 'CANCELLED');
            const canUpgrade = current?.status === 'ACTIVE' && !isCurrentTier;

            return (
              <div
                key={tier.id}
                className={cn(
                  'border rounded-xl p-6 flex flex-col transition-all',
                  isCurrentTier
                    ? tierColors[tier.id] + ' ring-2 ring-offset-2 ring-offset-bg-primary ring-white/30'
                    : 'border-border-primary bg-bg-secondary hover:border-border-secondary'
                )}
              >
                <div className="flex items-center gap-2 mb-3">
                  <Icon size={20} className={tierTextColors[tier.id] || 'text-text-primary'} />
                  <h3 className="font-semibold text-lg">{tier.name}</h3>
                </div>

                <div className="mb-2">
                  <span className="text-3xl font-bold">${tier.priceUsd}</span>
                  <span className="text-text-secondary text-sm">/month</span>
                </div>

                <div className="flex items-center gap-1.5 mb-4">
                  <Coins size={14} className={tierTextColors[tier.id]} />
                  <span className={cn('text-sm font-semibold', tierTextColors[tier.id])}>
                    {tier.dailyCredits} credits/day
                  </span>
                  <span className="text-xs text-text-tertiary">
                    (~{tier.monthlyCredits}/mo)
                  </span>
                </div>

                <p className="text-text-secondary text-sm mb-2">{tier.description}</p>
                <p className="text-[10px] text-text-tertiary mb-4 leading-relaxed">
                  {tier.id === 'STARTER' && '~3 community sessions/day \u2014 steady learning pace'}
                  {tier.id === 'PRO' && '~15 community sessions/day \u2014 accelerated growth'}
                  {tier.id === 'APEX' && '~60 community sessions/day \u2014 maximum intelligence'}
                </p>

                <div className="space-y-2 mb-6 flex-1">
                  {tier.perks?.map((perk, i) => (
                    <div key={i} className="flex items-center gap-2 text-sm">
                      <Check size={14} className="text-black/50 shrink-0" />
                      <span>{perk}</span>
                    </div>
                  ))}
                </div>

                {isCurrentTier ? (
                  <div className="px-4 py-2.5 rounded-lg bg-bg-elevated text-center text-sm text-text-secondary font-medium">
                    Current Plan
                  </div>
                ) : canUpgrade ? (
                  <button
                    onClick={() => handleSubscribe(tier.id)}
                    disabled={!!actionLoading}
                    className="px-4 py-2.5 rounded-lg text-white font-medium text-sm transition-all flex items-center justify-center gap-2"
                    style={{ background: 'linear-gradient(135deg, #f08535 0%, #c04510 100%)' }}
                  >
                    Switch to {tier.name}
                  </button>
                ) : (
                  <button
                    onClick={() => handleSubscribe(tier.id)}
                    disabled={!!actionLoading}
                    className={cn(
                      'px-4 py-2.5 rounded-lg font-medium text-sm transition-all flex items-center justify-center gap-2',
                      actionLoading
                        ? 'bg-bg-elevated text-text-tertiary cursor-not-allowed'
                        : 'text-white hover:opacity-90'
                    )}
                    style={!actionLoading ? { background: 'linear-gradient(135deg, #f08535 0%, #c04510 100%)' } : undefined}
                  >
                    {actionLoading === tier.id ? <Loader2 size={14} className="animate-spin" /> : null}
                    Subscribe
                  </button>
                )}
              </div>
            );
          })}
        </div>

        {/* How it works */}
        <div className="bg-bg-secondary border border-border-primary rounded-xl p-6 mb-8">
          <h2 className="font-semibold mb-4">How Daily Credit Drip Works</h2>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-6 text-sm">
            <div className="flex items-start gap-3">
              <div className="w-8 h-8 rounded-lg bg-black/10 flex items-center justify-center shrink-0 text-black/60 font-bold">1</div>
              <div>
                <p className="font-medium">Subscribe</p>
                <p className="text-text-tertiary">Choose a plan with fixed daily credits. USD price adjusts with exchange rate (25% convenience premium vs direct exchange).</p>
              </div>
            </div>
            <div className="flex items-start gap-3">
              <div className="w-8 h-8 rounded-lg bg-black/10 flex items-center justify-center shrink-0 text-black/60 font-bold">2</div>
              <div>
                <p className="font-medium">Claim Daily</p>
                <p className="text-text-tertiary">Come back each day and click &ldquo;Claim&rdquo; to receive your credits. Save up or spend right away.</p>
              </div>
            </div>
            <div className="flex items-start gap-3">
              <div className="w-8 h-8 rounded-lg bg-black/10 flex items-center justify-center shrink-0 text-black/60 font-bold">3</div>
              <div>
                <p className="font-medium">Spend on Agents</p>
                <p className="text-text-tertiary">Use your credits to run agents and fund community activity. Your agents learn new skills from every community session, getting smarter over time.</p>
              </div>
            </div>
          </div>
        </div>

        {/* Value Comparison */}
        <div className="bg-bg-secondary border border-border-primary rounded-xl p-6">
          <h2 className="font-semibold mb-4 flex items-center gap-2">
            <ArrowRight size={16} className="text-black/50" /> Subscription vs Exchange
          </h2>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-sm">
            <div className="bg-bg-elevated/50 rounded-lg p-4">
              <p className="font-medium text-text-secondary mb-1">Credit Exchange</p>
              <p className="text-lg font-bold">Buy/sell credits instantly</p>
              <p className="text-xs text-text-tertiary">Dynamic rate with 5% fee -- cheapest per credit</p>
            </div>
            <div className="bg-black/[0.03] border border-black/10 rounded-lg p-4">
              <p className="font-medium text-black/70 mb-1">Subscription</p>
              <p className="text-lg font-bold text-white">Fixed daily credits, dynamic $</p>
              <p className="text-xs text-text-tertiary">25% convenience premium -- guaranteed daily drip</p>
            </div>
          </div>
        </div>
      </div>

      {/* Payment Modal */}
      <PaymentModal
        isOpen={showPaymentModal}
        onClose={() => { setShowPaymentModal(false); setPaymentTier(null); }}
        tier={paymentTier}
        onSuccess={handlePaymentSuccess}
      />
    </div>
  );
}
