'use client';

import { useState, useEffect, useCallback } from 'react';
import { Crown, Clock, AlertTriangle, Sparkles, ArrowRight, Loader2, X, Shield } from 'lucide-react';
import { useAuthStore } from '@/store/authStore';
import { api } from '@/lib/api';
import toast from 'react-hot-toast';
import Link from 'next/link';

// ============================================
// Trial Banner — Endowment Effect + Loss Aversion
// ============================================
// Psychology:
// 1. Before trial: "Try Apex FREE for 3 days" (low commitment framing)
// 2. During trial: Show usage stats to build attachment
// 3. < 24 hours: "Your AI assistant is about to lose everything" (loss aversion)
// 4. Expired: "Your capable AI assistants are gone" (emphasize loss, not cost)
// The CTA always nudges toward Pro ($29.99) — the decoy target.

interface TrialStatus {
  id: string;
  tier: string;
  tierInfo: any;
  status: 'ACTIVE' | 'EXPIRED' | 'CONVERTED';
  startedAt: string;
  expiresAt: string;
  hoursRemaining: number;
  executionsUsed: number;
  agentsUsed: string[];
  agentsUsedCount: number;
  message: {
    title: string;
    titleKo: string;
    body: string;
    bodyKo: string;
    urgency: 'info' | 'warning' | 'critical';
  } | null;
  recommendedTier: any;
}

interface TrialBannerProps {
  /** 'dashboard' = full card, 'marketplace' = compact inline, 'modal' = centered overlay */
  variant?: 'dashboard' | 'marketplace' | 'modal';
  className?: string;
  onConvert?: () => void;
}

export function TrialBanner({ variant = 'dashboard', className = '', onConvert }: TrialBannerProps) {
  const { isAuthenticated } = useAuthStore();
  const [trialStatus, setTrialStatus] = useState<TrialStatus | null>(null);
  const [currentSub, setCurrentSub] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [actionLoading, setActionLoading] = useState(false);
  const [dismissed, setDismissed] = useState(false);

  const loadTrialStatus = useCallback(async () => {
    if (!isAuthenticated) { setLoading(false); return; }
    try {
      const [trialRes, subRes] = await Promise.all([
        api.get('/api/subscriptions/trial-status').catch(() => null),
        api.subscriptions.getCurrent().catch(() => null),
      ]);
      setTrialStatus(trialRes || null);
      setCurrentSub(subRes || null);
    } catch {}
    setLoading(false);
  }, [isAuthenticated]);

  useEffect(() => { loadTrialStatus(); }, [loadTrialStatus]);

  const handleStartTrial = async () => {
    if (!isAuthenticated) { window.location.href = '/auth/login'; return; }
    setActionLoading(true);
    try {
      const result = await api.post('/api/subscriptions/start-trial');
      if (result) {
        setTrialStatus(result);
        toast.success('🎉 Apex 체험이 시작되었습니다! 3일간 모든 기능을 자유롭게 사용하세요.');
        loadTrialStatus();
      }
    } catch (err: any) {
      toast.error(err.message || '체험 시작에 실패했습니다.');
    }
    setActionLoading(false);
  };

  const handleSubscribe = async () => {
    setActionLoading(true);
    try {
      // Always nudge to PRO — the real target tier
      const result = await api.subscriptions.subscribe('PRO');
      if (result?.url) {
        window.open(result.url, '_blank');
        toast.success('결제 페이지로 이동합니다...');
        onConvert?.();
      }
    } catch (err: any) {
      toast.error(err.message || '구독 생성에 실패했습니다.');
    }
    setActionLoading(false);
  };

  if (loading || dismissed) return null;
  // Already subscribed — no need to show trial CTA
  if (currentSub?.status === 'ACTIVE') return null;
  // Trial was converted — no need
  if (trialStatus?.status === 'CONVERTED') return null;

  // ── No trial yet: Show "Start Free Trial" CTA ──
  if (!trialStatus) {
    return (
      <div className={`rounded-2xl border overflow-hidden ${className} ${
        variant === 'modal'
          ? 'max-w-lg mx-auto bg-gradient-to-br from-[#0a0a0a] to-[#111] border-white/[0.1] shadow-2xl'
          : 'bg-gradient-to-r from-white/[0.03] to-white/[0.01] border-white/[0.08]'
      }`}>
        <div className="p-6">
          <div className="flex items-start gap-4">
            <div className="w-12 h-12 rounded-xl bg-gradient-to-br from-amber-500/20 to-orange-500/10 border border-amber-500/20 flex items-center justify-center shrink-0">
              <Crown size={22} className="text-amber-400/80" />
            </div>
            <div className="flex-1 min-w-0">
              <h3 className="font-bold text-white text-base">
                Apex를 3일간 무료로 체험하세요
              </h3>
              <p className="text-white/40 text-sm mt-1">
                모든 프리미엄 에이전트, 무제한 실행, 최고 우선순위 큐를 무료로 경험하세요.
                에이전트가 당신의 작업 패턴을 학습합니다.
              </p>
              <div className="flex items-center gap-3 mt-4">
                <button
                  onClick={handleStartTrial}
                  disabled={actionLoading}
                  className="flex items-center gap-2 bg-gradient-to-r from-amber-500/90 to-orange-500/80 text-black text-sm font-bold px-5 py-2.5 rounded-xl hover:from-amber-400 hover:to-orange-400 transition-all disabled:opacity-50 shadow-lg shadow-amber-500/10"
                >
                  {actionLoading ? (
                    <Loader2 size={14} className="animate-spin" />
                  ) : (
                    <><Sparkles size={14} /> 무료 체험 시작</>
                  )}
                </button>
                <span className="text-xs text-white/20">카드 정보 불필요 · 자동 결제 없음</span>
              </div>
            </div>
          </div>
        </div>
      </div>
    );
  }

  // ── Active trial ──
  if (trialStatus.status === 'ACTIVE') {
    const isCritical = trialStatus.hoursRemaining <= 24;
    const progressPercent = Math.max(0, Math.min(100, ((72 - trialStatus.hoursRemaining) / 72) * 100));

    return (
      <div className={`rounded-2xl border overflow-hidden ${className} ${
        isCritical
          ? 'bg-gradient-to-r from-red-500/[0.06] to-orange-500/[0.03] border-red-500/20 animate-pulse-subtle'
          : 'bg-gradient-to-r from-amber-500/[0.04] to-white/[0.02] border-amber-500/10'
      }`}>
        <div className="p-5">
          <div className="flex items-start justify-between gap-4">
            <div className="flex items-start gap-3 flex-1">
              <div className={`w-10 h-10 rounded-xl flex items-center justify-center shrink-0 ${
                isCritical
                  ? 'bg-red-500/15 border border-red-500/20'
                  : 'bg-amber-500/15 border border-amber-500/15'
              }`}>
                {isCritical ? (
                  <AlertTriangle size={18} className="text-red-400" />
                ) : (
                  <Crown size={18} className="text-amber-400/80" />
                )}
              </div>
              <div className="flex-1">
                <h3 className={`font-bold text-sm ${isCritical ? 'text-red-300' : 'text-white'}`}>
                  {trialStatus.message?.titleKo || 'Apex 체험 진행 중'}
                </h3>
                <p className="text-white/40 text-xs mt-1 leading-relaxed">
                  {trialStatus.message?.bodyKo || `${Math.ceil(trialStatus.hoursRemaining)}시간 남음`}
                </p>

                {/* Usage stats — builds attachment / sunk cost */}
                <div className="flex items-center gap-4 mt-3 text-xs text-white/30">
                  <span>에이전트 {trialStatus.agentsUsedCount}개 사용</span>
                  <span>·</span>
                  <span>실행 {trialStatus.executionsUsed}회 완료</span>
                </div>

                {/* Progress bar showing time consumed */}
                <div className="mt-3 w-full bg-white/[0.06] rounded-full h-1.5 overflow-hidden">
                  <div
                    className={`h-full rounded-full transition-all duration-1000 ${
                      isCritical ? 'bg-red-500/60' : 'bg-amber-500/40'
                    }`}
                    style={{ width: `${progressPercent}%` }}
                  />
                </div>

                {/* CTA — always nudge to Pro (the REAL target) */}
                {isCritical && (
                  <div className="mt-4 flex items-center gap-3">
                    <button
                      onClick={handleSubscribe}
                      disabled={actionLoading}
                      className="flex items-center gap-2 bg-white text-black text-xs font-bold px-4 py-2 rounded-xl hover:bg-white/90 transition-all disabled:opacity-50"
                    >
                      {actionLoading ? (
                        <Loader2 size={12} className="animate-spin" />
                      ) : (
                        <>
                          <Shield size={12} />
                          Pro로 보호하기 — $29.99/월
                        </>
                      )}
                    </button>
                    <span className="text-[10px] text-white/20">설정과 학습 데이터가 보존됩니다</span>
                  </div>
                )}
              </div>
            </div>

            <div className="flex items-center gap-2 shrink-0">
              <div className={`text-right ${isCritical ? 'text-red-400' : 'text-amber-400/70'}`}>
                <div className="text-lg font-bold tabular-nums">{Math.ceil(trialStatus.hoursRemaining)}h</div>
                <div className="text-[10px] text-white/30">남음</div>
              </div>
            </div>
          </div>
        </div>
      </div>
    );
  }

  // ── Expired trial — MAXIMUM loss aversion ──
  if (trialStatus.status === 'EXPIRED') {
    return (
      <div className={`rounded-2xl border overflow-hidden ${className} bg-gradient-to-r from-red-500/[0.04] to-transparent border-white/[0.08]`}>
        <div className="p-6">
          <div className="flex items-start justify-between gap-4">
            <div className="flex items-start gap-4 flex-1">
              <div className="w-12 h-12 rounded-xl bg-red-500/10 border border-red-500/15 flex items-center justify-center shrink-0">
                <AlertTriangle size={22} className="text-red-400/70" />
              </div>
              <div className="flex-1">
                <h3 className="font-bold text-white text-base">
                  {trialStatus.message?.titleKo || '유능한 AI 비서가 떠났습니다'}
                </h3>
                <p className="text-white/40 text-sm mt-1.5 leading-relaxed">
                  {trialStatus.message?.bodyKo || `체험 기간 동안 ${trialStatus.agentsUsedCount}개 에이전트를 사용하고 ${trialStatus.executionsUsed}건의 작업을 완료하셨습니다. 학습 데이터와 설정이 보관 중입니다.`}
                </p>

                {/* Show what they accomplished — amplify loss */}
                {trialStatus.agentsUsedCount > 0 && (
                  <div className="mt-3 p-3 rounded-lg bg-white/[0.02] border border-white/[0.05]">
                    <div className="text-xs text-white/30 mb-1">체험 중 이용한 프리미엄 기능</div>
                    <div className="flex items-center gap-4 text-sm text-white/50">
                      <span>🤖 에이전트 {trialStatus.agentsUsedCount}개</span>
                      <span>⚡ 실행 {trialStatus.executionsUsed}회</span>
                      <span>📊 학습 데이터 보관 중</span>
                    </div>
                  </div>
                )}

                <div className="flex items-center gap-3 mt-4">
                  <button
                    onClick={handleSubscribe}
                    disabled={actionLoading}
                    className="flex items-center gap-2 bg-white text-black text-sm font-bold px-5 py-2.5 rounded-xl hover:bg-white/90 transition-all disabled:opacity-50 shadow-lg"
                  >
                    {actionLoading ? (
                      <Loader2 size={14} className="animate-spin" />
                    ) : (
                      <>
                        <ArrowRight size={14} />
                        Pro 구독으로 즉시 복원 — $29.99/월
                      </>
                    )}
                  </button>
                  <button
                    onClick={() => setDismissed(true)}
                    className="text-white/20 hover:text-white/40 transition-colors"
                  >
                    <X size={16} />
                  </button>
                </div>

                {/* Comparison anchor — show how cheap Pro is vs Apex */}
                <div className="mt-3 text-[11px] text-white/20">
                  <span className="line-through">Apex $99.99/월</span>
                  <span className="mx-2">→</span>
                  <span className="text-white/50 font-semibold">Pro $29.99/월로 핵심 기능 모두 이용</span>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    );
  }

  return null;
}

/** Compact trial CTA for marketplace sidebar */
export function TrialCTA({ className = '' }: { className?: string }) {
  const { isAuthenticated } = useAuthStore();
  const [hasTrial, setHasTrial] = useState<boolean | null>(null);
  const [hasSub, setHasSub] = useState(false);

  useEffect(() => {
    if (!isAuthenticated) return;
    Promise.all([
      api.get('/api/subscriptions/trial-status').catch(() => null),
      api.subscriptions.getCurrent().catch(() => null),
    ]).then(([trial, sub]) => {
      setHasTrial(!!trial);
      setHasSub(sub?.status === 'ACTIVE');
    });
  }, [isAuthenticated]);

  if (!isAuthenticated || hasSub || hasTrial === null) return null;

  if (!hasTrial) {
    return (
      <Link href="/settings?tab=subscription" className={`block ${className}`}>
        <div className="rounded-xl border border-amber-500/15 bg-gradient-to-r from-amber-500/[0.06] to-transparent p-4 hover:border-amber-500/25 transition-all cursor-pointer">
          <div className="flex items-center gap-3">
            <Sparkles size={16} className="text-amber-400/70 shrink-0" />
            <div>
              <div className="text-sm font-semibold text-white">Apex 3일 무료 체험</div>
              <div className="text-xs text-white/30 mt-0.5">카드 불필요 — 지금 바로 시작</div>
            </div>
          </div>
        </div>
      </Link>
    );
  }

  return null;
}
