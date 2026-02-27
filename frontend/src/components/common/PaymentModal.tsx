'use client';

import { useState, useEffect, useCallback } from 'react';
import { api } from '@/lib/api';
import { loadStripe, Stripe, StripeElements } from '@stripe/stripe-js';
import {
  Elements,
  PaymentElement,
  useStripe,
  useElements,
} from '@stripe/react-stripe-js';
import {
  X,
  Loader2,
  Shield,
  Check,
  CreditCard,
  Zap,
  Star,
  Crown,
  AlertCircle,
} from 'lucide-react';

/* --- Types --- */

interface TierInfo {
  id: string;
  name: string;
  priceUsd: number;
  dailyCredits: number;
  monthlyCredits: number;
  description: string;
}

interface PaymentModalProps {
  isOpen: boolean;
  onClose: () => void;
  tier: TierInfo | null;
  onSuccess: () => void;
}

/* --- Stripe promise cache --- */

let stripePromiseCache: Promise<Stripe | null> | null = null;

function getStripePromise(publishableKey: string) {
  if (!stripePromiseCache) {
    stripePromiseCache = loadStripe(publishableKey);
  }
  return stripePromiseCache;
}

/* --- Tier icons --- */

const tierIcons: Record<string, any> = {
  STARTER: Zap,
  PRO: Star,
  APEX: Crown,
};

/* --- Inner checkout form (uses Stripe hooks) --- */

function CheckoutForm({
  tier,
  clientSecret,
  paymentIntentId,
  amount,
  onSuccess,
  onClose,
}: {
  tier: TierInfo;
  clientSecret: string;
  paymentIntentId: string;
  amount: number;
  onSuccess: () => void;
  onClose: () => void;
}) {
  const stripe = useStripe();
  const elements = useElements();
  const [paying, setPaying] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!stripe || !elements) return;

    setPaying(true);
    setError(null);

    try {
      const { error: stripeError, paymentIntent } = await stripe.confirmPayment({
        elements,
        confirmParams: {
          return_url: window.location.href,
        },
        redirect: 'if_required',
      });

      if (stripeError) {
        setError(stripeError.message || 'Payment failed. Please try again.');
        setPaying(false);
        return;
      }

      if (paymentIntent && paymentIntent.status === 'succeeded') {
        try {
          await api.subscriptions.confirm(tier.id, paymentIntentId);
        } catch {
          // Webhook will handle it as fallback
        }
        setSuccess(true);
        setTimeout(() => {
          onSuccess();
        }, 1500);
      }
    } catch (err: any) {
      setError(err.message || 'Unexpected error');
      setPaying(false);
    }
  };

  if (success) {
    return (
      <div className="flex flex-col items-center justify-center py-12 gap-4">
        <div className="w-16 h-16 rounded-full bg-green-500/20 flex items-center justify-center">
          <Check size={32} className="text-green-400" />
        </div>
        <h3 className="text-xl font-bold text-white">Payment Complete!</h3>
        <p className="text-sm text-white/60">Activating your subscription...</p>
      </div>
    );
  }

  const Icon = tierIcons[tier.id] || Star;

  return (
    <form onSubmit={handleSubmit} className="space-y-5">
      {/* Tier summary */}
      <div className="bg-white/[0.03] border border-white/10 rounded-xl p-4">
        <div className="flex items-center gap-3 mb-2">
          <div className="w-10 h-10 rounded-xl flex items-center justify-center"
            style={{ background: 'linear-gradient(135deg, #f08535 0%, #c04510 100%)' }}>
            <Icon size={20} className="text-white" />
          </div>
          <div className="flex-1">
            <h4 className="font-semibold text-white">{tier.name}</h4>
            <p className="text-xs text-white/50">{tier.dailyCredits} credits/day · ~{tier.monthlyCredits}/month</p>
          </div>
          <div className="text-right">
            <p className="text-xl font-bold text-white">${amount.toFixed(2)}</p>
            <p className="text-[10px] text-white/40 uppercase">per month</p>
          </div>
        </div>
      </div>

      {/* Stripe PaymentElement */}
      <div className="rounded-xl border border-white/10 bg-white/[0.02] p-4">
        <PaymentElement
          options={{
            layout: 'tabs',
            defaultValues: {
              billingDetails: {
                address: { country: 'KR' },
              },
            },
          }}
        />
      </div>

      {/* Error */}
      {error && (
        <div className="flex items-center gap-2 text-sm text-red-400 bg-red-400/10 border border-red-400/20 rounded-lg px-3 py-2">
          <AlertCircle size={14} className="shrink-0" />
          <span>{error}</span>
        </div>
      )}

      {/* Submit */}
      <button
        type="submit"
        disabled={!stripe || paying}
        className="w-full py-3.5 rounded-xl font-semibold text-white text-sm transition-all disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2"
        style={{ background: 'linear-gradient(135deg, #f08535 0%, #c04510 100%)' }}
      >
        {paying ? (
          <>
            <Loader2 size={16} className="animate-spin" />
            Processing...
          </>
        ) : (
          <>
            <CreditCard size={16} />
            Pay ${amount.toFixed(2)}
          </>
        )}
      </button>

      {/* Security badge */}
      <div className="flex items-center justify-center gap-2 text-[11px] text-white/30">
        <Shield size={12} />
        <span>Secured by Stripe | Card info is never stored by Ogenti</span>
      </div>
    </form>
  );
}

/* --- Main Payment Modal --- */

export function PaymentModal({ isOpen, onClose, tier, onSuccess }: PaymentModalProps) {
  const [clientSecret, setClientSecret] = useState<string | null>(null);
  const [paymentIntentId, setPaymentIntentId] = useState<string | null>(null);
  const [amount, setAmount] = useState<number>(0);
  const [stripePromise, setStripePromise] = useState<Promise<Stripe | null> | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const handleEscape = useCallback(
    (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    },
    [onClose]
  );

  useEffect(() => {
    if (isOpen) {
      document.addEventListener('keydown', handleEscape);
      document.body.style.overflow = 'hidden';
    }
    return () => {
      document.removeEventListener('keydown', handleEscape);
      document.body.style.overflow = '';
    };
  }, [isOpen, handleEscape]);

  useEffect(() => {
    if (!isOpen || !tier) return;

    let cancelled = false;
    setLoading(true);
    setError(null);
    setClientSecret(null);

    (async () => {
      try {
        const pkRes = await api.stripe.getPublishableKey();
        const pk = pkRes?.publishableKey;
        if (!pk) throw new Error('Stripe is not configured');

        if (!cancelled) {
          setStripePromise(getStripePromise(pk));
        }

        const subRes = await api.subscriptions.subscribe(tier.id);
        const data = subRes || {};

        if (!data?.clientSecret) {
          if (!cancelled) {
            onSuccess();
          }
          return;
        }

        if (!cancelled) {
          setClientSecret(data.clientSecret);
          setPaymentIntentId(data.paymentIntentId);
          setAmount(data.amount || 0);
          setLoading(false);
        }
      } catch (err: any) {
        if (!cancelled) {
          setError(err.message || 'Failed to initialize payment');
          setLoading(false);
        }
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [isOpen, tier]);

  if (!isOpen || !tier) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      {/* Backdrop */}
      <div
        className="absolute inset-0 bg-black/70 backdrop-blur-sm"
        onClick={onClose}
      />

      {/* Modal */}
      <div className="relative w-full max-w-md mx-4 bg-[#111111] border border-white/10 rounded-2xl shadow-2xl overflow-hidden flex flex-col"
        style={{ animation: 'slideUp 0.25s ease-out', maxHeight: '90vh' }}>
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-white/10">
          <div className="flex items-center gap-2">
            <CreditCard size={18} className="text-white/60" />
            <h2 className="text-base font-semibold text-white">Subscribe</h2>
          </div>
          <button
            onClick={onClose}
            className="p-1.5 rounded-lg text-white/40 hover:text-white hover:bg-white/10 transition-colors"
          >
            <X size={18} />
          </button>
        </div>

        {/* Body */}
        <div className="px-6 py-5 overflow-y-auto flex-1">
          {loading && (
            <div className="flex flex-col items-center justify-center py-12 gap-3">
              <Loader2 size={28} className="animate-spin text-white/40" />
              <p className="text-sm text-white/50">Preparing payment...</p>
            </div>
          )}

          {error && !loading && (
            <div className="flex flex-col items-center justify-center py-12 gap-3">
              <AlertCircle size={28} className="text-red-400" />
              <p className="text-sm text-red-400">{error}</p>
              <button
                onClick={onClose}
                className="px-4 py-2 text-sm rounded-lg bg-white/10 text-white/70 hover:bg-white/20 transition-colors"
              >
                Close
              </button>
            </div>
          )}

          {!loading && !error && clientSecret && stripePromise && (
            <Elements
              stripe={stripePromise}
              options={{
                clientSecret,
                appearance: {
                  theme: 'night',
                  variables: {
                    colorPrimary: '#e86520',
                    colorBackground: '#111111',
                    colorText: '#ffffff',
                    colorDanger: '#ef4444',
                    fontFamily: 'system-ui, -apple-system, sans-serif',
                    spacingUnit: '4px',
                    borderRadius: '10px',
                    colorTextPlaceholder: '#666666',
                  },
                  rules: {
                    '.Input': {
                      border: '1px solid rgba(255, 255, 255, 0.1)',
                      backgroundColor: 'rgba(255,255,255,0.05)',
                      boxShadow: 'none',
                      color: '#ffffff',
                    },
                    '.Input:focus': {
                      border: '1px solid rgba(232,101,32,0.5)',
                      boxShadow: '0 0 0 1px rgba(232,101,32,0.2)',
                    },
                    '.Tab': {
                      border: '1px solid rgba(255, 255, 255, 0.1)',
                      backgroundColor: 'rgba(255,255,255,0.05)',
                      color: '#ffffff',
                    },
                    '.Tab--selected': {
                      backgroundColor: 'rgba(232,101,32,0.15)',
                      border: '1px solid rgba(232,101,32,0.4)',
                      color: '#ffffff',
                    },
                    '.Tab--selected:hover': {
                      color: '#ffffff',
                    },
                    '.Tab:hover': {
                      color: '#ffffff',
                      backgroundColor: 'rgba(255,255,255,0.08)',
                    },
                    '.TabIcon--selected': {
                      fill: '#ffffff',
                      color: '#ffffff',
                    },
                    '.Label': {
                      color: 'rgba(255,255,255,0.6)',
                      fontSize: '13px',
                    },
                  },
                },
                locale: 'en',
              }}
            >
              <CheckoutForm
                tier={tier}
                clientSecret={clientSecret}
                paymentIntentId={paymentIntentId || ''}
                amount={amount}
                onSuccess={onSuccess}
                onClose={onClose}
              />
            </Elements>
          )}
        </div>
      </div>

      <style jsx>{`
        @keyframes slideUp {
          from { opacity: 0; transform: translateY(16px) scale(0.98); }
          to { opacity: 1; transform: translateY(0) scale(1); }
        }
      `}</style>
    </div>
  );
}
