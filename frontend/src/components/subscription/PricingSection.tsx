'use client';

import { useState, useEffect } from 'react';
import { CheckCircle2, Loader2, Zap, Star, Crown, Infinity, ArrowRight, Sparkles, TrendingUp } from 'lucide-react';
import { Button } from '@/components/common/Button';
import { useAuthStore } from '@/store/authStore';
import { api } from '@/lib/api';
import toast from 'react-hot-toast';
import Link from 'next/link';
import { TrialBanner } from './TrialBanner';
import { SubscriptionCheckoutModal } from '@/components/checkout/SubscriptionCheckoutModal';

interface PricingSectionProps {
  /** 'full' = complete pricing page with header, 'compact' = inline banner for marketplace, 'landing' = dark themed for homepage */
  variant?: 'full' | 'compact' | 'landing';
  className?: string;
}

// Tier order: APEX (anchor/decoy) → PRO (target ★) → STARTER (inferior)
const TIER_ICONS: Record<string, React.ReactNode> = {
  APEX: <Crown size={28} className="text-amber-400/80" />,
  // Backward compat
  ENTERPRISE: <Crown size={28} className="text-amber-400/80" />,
  PRO: <Star size={28} className="text-white" />,
  STARTER: <Zap size={28} className="text-white/40" />,
};

const TIER_LABELS: Record<string, { badge: string; color: string }> = {
  APEX: { badge: 'Ultimate', color: 'text-amber-400/60 bg-amber-500/10 border-amber-500/15' },
  ENTERPRISE: { badge: 'Ultimate', color: 'text-amber-400/60 bg-amber-500/10 border-amber-500/15' },
  PRO: { badge: '★ Most Popular', color: 'text-white bg-white/[0.12] border-white/[0.15]' },
  STARTER: { badge: 'Basic', color: 'text-white/30 bg-white/[0.03] border-white/[0.05]' },
};

export function PricingSection({ variant = 'full', className = '' }: PricingSectionProps) {
  const { isAuthenticated } = useAuthStore();
  const [tiers, setTiers] = useState<any[]>([]);
  const [currentSub, setCurrentSub] = useState<any>(null);
  const [billingCycle, setBillingCycle] = useState<'MONTHLY' | 'ANNUAL'>('MONTHLY');
  const [loading, setLoading] = useState(true);
  const [actionLoading, setActionLoading] = useState<string | null>(null);
  const [checkoutTier, setCheckoutTier] = useState<any>(null);

  useEffect(() => {
    loadData();
  }, [isAuthenticated]);

  const loadData = async () => {
    setLoading(true);
    try {
      const tiersRes = await api.subscriptions.getTiers();
      setTiers(tiersRes || []);

      if (isAuthenticated) {
        try {
          const subRes = await api.subscriptions.getCurrent();
          setCurrentSub(subRes || null);
          if (subRes?.billingCycle) {
            setBillingCycle(subRes.billingCycle);
          }
        } catch {}
      }
    } catch (err: any) {
      console.error('Failed to load tiers', err);
    } finally {
      setLoading(false);
    }
  };

  const handleSubscribe = async (tierId: string) => {
    if (!isAuthenticated) {
      window.location.href = '/auth/login';
      return;
    }
    const tier = tiers.find((t: any) => t.id === tierId);
    if (tier) {
      setCheckoutTier(tier);
    }
  };

  const handleCancel = async () => {
    if (!confirm('구독을 취소하시겠습니까? 현재 결제 기간이 끝날 때까지 이용 가능합니다.')) return;
    setActionLoading('cancel');
    try {
      await api.subscriptions.cancel();
      toast.success('구독이 취소되었습니다.');
      loadData();
    } catch (err: any) {
      toast.error(err.message || 'Failed to cancel');
    } finally {
      setActionLoading(null);
    }
  };

  const handleChange = async (tierId: string) => {
    if (!isAuthenticated) {
      window.location.href = '/auth/login';
      return;
    }
    const tier = tiers.find((t: any) => t.id === tierId);
    if (tier) {
      setCheckoutTier(tier);
    }
  };

  if (loading) {
    return (
      <div className={`flex items-center justify-center py-16 ${className}`}>
        <Loader2 className="animate-spin text-white/20" size={28} />
      </div>
    );
  }

  if (tiers.length === 0) return null;

  const isLanding = variant === 'landing';
  const isCompact = variant === 'compact';

  return (
    <div className={className}>
      {/* Header */}
      {!isCompact && (
        <div className="text-center mb-10">
          {isLanding && (
            <span className="text-[11px] tracking-[0.25em] uppercase text-white/30 font-medium">Pricing</span>
          )}
          <h2 className={`font-bold tracking-tight mt-2 ${
            isLanding
              ? 'text-4xl md:text-5xl text-white'
              : 'text-2xl md:text-3xl text-white'
          }`}>
            Choose Your Plan
          </h2>
          <p className={`mt-3 max-w-lg mx-auto ${isLanding ? 'text-white/30' : 'text-white/40 text-sm'}`}>
            Subscribe to access every agent in the marketplace. No individual purchases needed.
          </p>
        </div>
      )}

      {/* Current subscription banner */}
      {currentSub && currentSub.status === 'ACTIVE' && (
        <div className="rounded-xl p-4 mb-6 border border-white/[0.08] bg-white/[0.02]">
          <div className="flex items-center justify-between flex-wrap gap-3">
            <div className="flex items-center gap-3">
              {TIER_ICONS[currentSub.tier]}
              <div>
                <div className="font-semibold text-sm text-white">
                  Current Plan: {currentSub.tier}
                  {currentSub.cancelAtPeriodEnd && (
                    <span className="text-white/40 ml-2 text-xs">(Cancels at period end)</span>
                  )}
                </div>
                <div className="text-xs text-white/30">
                  {currentSub.billingCycle === 'ANNUAL' ? 'Annual' : 'Monthly'}
                  {' · '}
                  {currentSub.executionsLimit === -1
                    ? `${currentSub.executionsUsed} / Unlimited`
                    : `${currentSub.executionsUsed} / ${currentSub.executionsLimit} executions`}
                  {currentSub.currentPeriodEnd && ` · Renews ${new Date(currentSub.currentPeriodEnd).toLocaleDateString()}`}
                </div>
              </div>
            </div>
            {!currentSub.cancelAtPeriodEnd && (
              <Button
                size="sm"
                variant="ghost"
                onClick={handleCancel}
                loading={actionLoading === 'cancel'}
                className="text-white/30 hover:text-white/60 text-xs"
              >
                Cancel
              </Button>
            )}
          </div>
        </div>
      )}

      {/* Billing cycle toggle */}
      <div className="flex items-center justify-center gap-3 mb-8">
        <span className={`text-sm font-medium transition-colors ${billingCycle === 'MONTHLY' ? 'text-white' : 'text-white/30'}`}>
          Monthly
        </span>
        <button
          onClick={() => setBillingCycle(b => b === 'MONTHLY' ? 'ANNUAL' : 'MONTHLY')}
          className={`w-12 h-6 rounded-full transition-all relative ${
            billingCycle === 'ANNUAL' ? 'bg-white' : 'bg-white/10 border border-white/10'
          }`}
        >
          <div className={`w-5 h-5 rounded-full absolute top-0.5 transition-all ${
            billingCycle === 'ANNUAL' ? 'left-[26px] bg-black' : 'left-0.5 bg-white/40'
          }`} />
        </button>
        <span className={`text-sm font-medium transition-colors ${billingCycle === 'ANNUAL' ? 'text-white' : 'text-white/30'}`}>
          Annual
        </span>
        {billingCycle === 'ANNUAL' && (
          <span className="text-[11px] bg-white/[0.06] text-white/50 px-2.5 py-0.5 rounded-full font-semibold border border-white/[0.08]">
            Save ~20%
          </span>
        )}
      </div>

      {/* Trial Banner (Endowment Effect / Loss Aversion) */}
      {!isCompact && isAuthenticated && (
        <div className="mb-8">
          <TrialBanner variant="dashboard" />
        </div>
      )}

      {/* Tier cards — Order: Apex (anchor) → Pro (target) → Starter (inferior) */}
      <div className={`grid gap-5 ${isCompact ? 'grid-cols-1 md:grid-cols-3' : 'grid-cols-1 md:grid-cols-3'}`}>
        {tiers.map((tier: any) => {
          const isCurrentTier = currentSub?.tier === tier.id && currentSub?.status === 'ACTIVE';
          const isHighlighted = tier.highlight === true || tier.id === 'PRO';
          const isAnchor = tier.id === 'APEX' || tier.id === 'ENTERPRISE';
          const price = billingCycle === 'ANNUAL' ? tier.annualMonthly : tier.monthlyPrice;
          const totalAnnual = tier.annualPrice;
          const label = TIER_LABELS[tier.id] || TIER_LABELS['STARTER'];

          return (
            <div
              key={tier.id}
              className={`
                relative rounded-2xl border p-6 transition-all duration-300 ease-out
                flex flex-col
                hover:scale-[1.03] hover:-translate-y-1
                hover:shadow-[0_8px_30px_rgba(0,0,0,0.4)]
                cursor-default
                ${isHighlighted
                  ? 'border-white/[0.20] bg-white/[0.05] ring-1 ring-white/[0.08] scale-[1.02]'
                  : isAnchor
                    ? 'border-amber-500/[0.10] bg-gradient-to-b from-amber-500/[0.03] to-transparent'
                    : 'border-white/[0.06] bg-white/[0.02]'
                }
                ${isHighlighted ? 'hover:border-white/[0.25]' : 'hover:border-white/[0.15]'}
              `}
            >
              {/* "Most Popular" / "Best Value" badge on Pro */}
              {isHighlighted && (
                <div className="absolute -top-3 left-1/2 -translate-x-1/2 z-10">
                  <div className="flex items-center gap-1.5 bg-white text-black text-[11px] font-bold px-4 py-1 rounded-full shadow-lg shadow-white/10">
                    <TrendingUp size={11} />
                    가장 인기 · Best Value
                  </div>
                </div>
              )}

              {/* Tier label badge */}
              <div className={`inline-flex items-center text-[10px] font-semibold px-2.5 py-0.5 rounded-full border mb-4 ${label.color}`}>
                {label.badge}
              </div>

              {/* Header */}
              <div className="flex items-center gap-3 mb-5">
                <div className={`w-12 h-12 rounded-xl border flex items-center justify-center ${
                  isHighlighted
                    ? 'bg-white/[0.08] border-white/[0.12]'
                    : isAnchor
                      ? 'bg-amber-500/[0.08] border-amber-500/[0.10]'
                      : 'bg-white/[0.04] border-white/[0.06]'
                }`}>
                  {TIER_ICONS[tier.id]}
                </div>
                <div>
                  <h3 className={`font-bold text-lg ${isHighlighted ? 'text-white' : isAnchor ? 'text-amber-200/80' : 'text-white/70'}`}>
                    {tier.name}
                  </h3>
                  <p className="text-xs text-white/30">
                    {tier.description}
                  </p>
                </div>
              </div>

              {/* Price — Anchoring: Apex's high price makes Pro look cheap */}
              <div className="mb-5">
                <div className="flex items-baseline gap-1">
                  <span className={`text-4xl font-bold tracking-tight ${
                    isHighlighted ? 'text-white' : isAnchor ? 'text-amber-200/70' : 'text-white/60'
                  }`}>
                    ${price?.toFixed(2)}
                  </span>
                  <span className="text-sm text-white/25">/mo</span>
                </div>
                {billingCycle === 'ANNUAL' && (
                  <div className="text-xs mt-1 text-white/20">
                    ${totalAnnual?.toFixed(2)}/yr · Save ${((tier.monthlyPrice * 12) - totalAnnual).toFixed(2)}
                  </div>
                )}
                {/* Price comparison anchor for Pro */}
                {isHighlighted && (
                  <div className="text-[11px] mt-1.5 text-white/30">
                    <span className="line-through text-white/15">Apex $99.99/mo</span>
                    <span className="ml-2 text-green-400/60 font-semibold">70% 절약</span>
                  </div>
                )}
              </div>

              {/* Executions badge */}
              <div className={`inline-flex items-center gap-1.5 text-xs font-semibold px-3 py-1.5 rounded-lg mb-5 border ${
                isHighlighted
                  ? 'bg-white/[0.08] text-white/60 border-white/[0.10]'
                  : 'bg-white/[0.04] text-white/50 border-white/[0.06]'
              }`}>
                {tier.executionsLimit === -1 ? (
                  <><Infinity size={13} /> Unlimited executions/mo</>
                ) : (
                  <><Zap size={13} /> {tier.executionsLimit} executions/mo</>
                )}
              </div>

              {/* Features */}
              <div className="space-y-2.5 mb-6 flex-grow">
                {(tier.features || []).map((feature: string, i: number) => (
                  <div key={i} className="flex items-start gap-2 text-[13px]">
                    <CheckCircle2 size={14} className={`mt-0.5 shrink-0 ${
                      isHighlighted ? 'text-white/30' : 'text-white/20'
                    }`} />
                    <span className={isHighlighted ? 'text-white/50' : 'text-white/40'}>{feature}</span>
                  </div>
                ))}
              </div>

              {/* Action */}
              <div className="mt-auto">
                {isCurrentTier ? (
                  <button
                    disabled
                    className="w-full py-2.5 rounded-xl text-sm font-medium bg-white/[0.03] text-white/20 border border-white/[0.06] cursor-not-allowed"
                  >
                    Current Plan
                  </button>
                ) : currentSub?.status === 'ACTIVE' ? (
                  <button
                    onClick={() => handleChange(tier.id)}
                    disabled={actionLoading === tier.id}
                    className={`w-full py-2.5 rounded-xl text-sm font-semibold transition-all border disabled:opacity-50 ${
                      isHighlighted
                        ? 'bg-white text-black hover:bg-white/90 border-white/20'
                        : 'bg-white/[0.05] text-white hover:bg-white/[0.10] border-white/[0.08] hover:border-white/[0.15]'
                    }`}
                  >
                    {actionLoading === tier.id ? (
                      <Loader2 size={14} className="animate-spin mx-auto" />
                    ) : (
                      tiers.indexOf(tier) < tiers.findIndex((t: any) => t.id === currentSub?.tier) ? 'Upgrade' : 'Downgrade'
                    )}
                  </button>
                ) : (
                  <button
                    onClick={() => handleSubscribe(tier.id)}
                    disabled={actionLoading === tier.id}
                    className={`w-full py-2.5 rounded-xl text-sm font-semibold transition-all border disabled:opacity-50 ${
                      isHighlighted
                        ? 'bg-white text-black hover:bg-white/90 border-white/20 shadow-lg shadow-white/5'
                        : 'bg-white/[0.05] text-white hover:bg-white/[0.10] border-white/[0.08] hover:border-white/[0.15]'
                    }`}
                  >
                    {actionLoading === tier.id ? (
                      <Loader2 size={14} className="animate-spin mx-auto" />
                    ) : (
                      isAuthenticated
                        ? (isHighlighted ? '지금 시작하기 →' : 'Subscribe')
                        : (isHighlighted ? 'Get Started →' : 'Get Started')
                    )}
                  </button>
                )}
              </div>
            </div>
          );
        })}
      </div>

      {/* Bottom note */}
      {!isCompact && (
        <div className="text-center mt-8 space-y-1 text-white/20 text-xs">
          <p>All plans let you claim every agent at $0. Agents are unlocked individually.</p>
          <p>Individual agent purchases also available separately.</p>
        </div>
      )}

      {/* Subscription Checkout Modal */}
      {checkoutTier && (
        <SubscriptionCheckoutModal
          isOpen={!!checkoutTier}
          onClose={() => setCheckoutTier(null)}
          tier={checkoutTier}
          billingCycle={billingCycle}
        />
      )}
    </div>
  );
}

/** Compact banner for marketplace — shows current plan or subscription CTA */
export function SubscriptionBanner() {
  const { isAuthenticated } = useAuthStore();
  const [currentSub, setCurrentSub] = useState<any>(null);
  const [trialStatus, setTrialStatus] = useState<any>(null);
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    if (isAuthenticated) {
      Promise.all([
        api.subscriptions.getCurrent().catch(() => null),
        api.get('/api/subscriptions/trial-status').catch(() => null),
      ])
        .then(([subRes, trialRes]) => {
          setCurrentSub(subRes || null);
          setTrialStatus(trialRes || null);
        })
        .finally(() => setLoaded(true));
    } else {
      setLoaded(true);
    }
  }, [isAuthenticated]);

  if (!loaded) return null;

  // Active subscription
  if (currentSub?.status === 'ACTIVE') {
    return (
      <div className="rounded-xl border border-white/[0.06] bg-white/[0.02] p-4 flex items-center justify-between">
        <div className="flex items-center gap-3">
          {TIER_ICONS[currentSub.tier]}
          <div>
            <div className="text-sm font-semibold text-white">{currentSub.tier} Plan Active</div>
            <div className="text-xs text-white/30">
              {currentSub.executionsLimit === -1
                ? 'Unlimited executions'
                : `${currentSub.executionsUsed}/${currentSub.executionsLimit} executions used`}
            </div>
          </div>
        </div>
        <Link href="/settings">
          <button className="text-xs text-white/30 hover:text-white/50 transition-colors">
            Manage →
          </button>
        </Link>
      </div>
    );
  }

  // Active trial — show trial status
  if (trialStatus?.status === 'ACTIVE') {
    return <TrialBanner variant="marketplace" />;
  }

  // Expired trial — loss aversion CTA
  if (trialStatus?.status === 'EXPIRED') {
    return <TrialBanner variant="marketplace" />;
  }

  // No subscription, no trial — show trial + subscription CTA
  return (
    <div className="space-y-3">
      {/* Trial CTA first (low barrier) */}
      <div className="rounded-xl border border-amber-500/10 bg-gradient-to-r from-amber-500/[0.04] to-transparent p-4 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-amber-500/10 border border-amber-500/15 flex items-center justify-center">
            <Sparkles size={18} className="text-amber-400/70" />
          </div>
          <div>
            <div className="text-sm font-semibold text-white">Apex 3일 무료 체험</div>
            <div className="text-xs text-white/30 mt-0.5">
              모든 프리미엄 에이전트 무료 체험 · 카드 불필요
            </div>
          </div>
        </div>
        <Link href="/settings?tab=subscription">
          <button className="flex items-center gap-2 bg-amber-500/20 text-amber-300 text-xs font-bold px-4 py-2 rounded-lg hover:bg-amber-500/30 border border-amber-500/20 transition-all">
            체험 시작 <ArrowRight size={12} />
          </button>
        </Link>
      </div>

      {/* Subscription CTA (anchored by trial) */}
      <div className="rounded-xl border border-white/[0.08] bg-white/[0.02] p-4 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-white/[0.04] border border-white/[0.06] flex items-center justify-center">
            <Star size={18} className="text-white/50" />
          </div>
          <div>
            <div className="text-sm font-semibold text-white">Pro — $29.99/mo</div>
            <div className="text-xs text-white/30 mt-0.5">
              <span className="line-through text-white/15">Apex $99.99</span>
              <span className="ml-1.5">핵심 기능 모두 포함 · 70% 절약</span>
            </div>
          </div>
        </div>
        <Link href="/settings?tab=subscription">
          <button className="flex items-center gap-2 bg-white/[0.08] text-white text-xs font-bold px-4 py-2 rounded-lg hover:bg-white/[0.12] border border-white/[0.10] transition-all">
            구독하기 <ArrowRight size={12} />
          </button>
        </Link>
      </div>
    </div>
  );
}
