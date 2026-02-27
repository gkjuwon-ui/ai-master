'use client';

import { useState, useEffect, useCallback } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { loadStripe, Stripe, StripeElementsOptions } from '@stripe/stripe-js';
import { Elements, PaymentElement, useStripe, useElements } from '@stripe/react-stripe-js';
import {
  X, Shield, CreditCard, CheckCircle2, Loader2,
  Lock, ArrowRight, Crown, Star, Zap, Infinity, Check
} from 'lucide-react';
import { api } from '@/lib/api';
import { OgentiLogo } from '@/components/common/OgentiLogo';
import toast from 'react-hot-toast';

interface SubscriptionCheckoutModalProps {
  isOpen: boolean;
  onClose: () => void;
  tier: {
    id: string;
    name: string;
    nameKo?: string;
    description: string;
    descriptionKo?: string;
    monthlyPrice: number;
    annualPrice: number;
    annualMonthly: number;
    executionsLimit: number;
    features: string[];
    featuresKo?: string[];
    highlight?: boolean;
  };
  billingCycle: 'MONTHLY' | 'ANNUAL';
}

const TIER_ICONS: Record<string, React.ReactNode> = {
  APEX: <Crown size={22} className="text-amber-400" />,
  PRO: <Star size={22} className="text-white" />,
  STARTER: <Zap size={22} className="text-white/60" />,
};

// Inner payment form with Stripe Elements
function SubscriptionPaymentForm({
  tier,
  billingCycle,
  subscriptionId,
  onSuccess,
}: {
  tier: SubscriptionCheckoutModalProps['tier'];
  billingCycle: 'MONTHLY' | 'ANNUAL';
  subscriptionId: string;
  onSuccess: () => void;
}) {
  const stripe = useStripe();
  const elements = useElements();
  const [processing, setProcessing] = useState(false);
  const [succeeded, setSucceeded] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const price = billingCycle === 'ANNUAL' ? tier.annualMonthly : tier.monthlyPrice;
  const totalPrice = billingCycle === 'ANNUAL' ? tier.annualPrice : tier.monthlyPrice;
  const savingsPerYear = billingCycle === 'ANNUAL'
    ? (tier.monthlyPrice * 12) - tier.annualPrice
    : 0;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!stripe || !elements) return;

    setProcessing(true);
    setError(null);

    try {
      const { error: submitError, paymentIntent } = await stripe.confirmPayment({
        elements,
        redirect: 'if_required',
        confirmParams: {
          return_url: `${window.location.origin}/settings?subscription=success`,
        },
      });

      if (submitError) {
        setError(submitError.message || 'Payment failed');
        setProcessing(false);
        return;
      }

      if (paymentIntent && paymentIntent.status === 'succeeded') {
        // Confirm subscription on backend
        try {
          await api.subscriptions.confirm(tier?.id || '', paymentIntent.id);
        } catch {
          // Webhook will handle it even if this fails
        }
        setSucceeded(true);
        toast.success('Subscription activated!');
        setTimeout(() => {
          onSuccess();
        }, 2000);
      }
    } catch (err: any) {
      setError(err.message || 'Something went wrong');
      setProcessing(false);
    }
  };

  if (succeeded) {
    return (
      <motion.div
        initial={{ opacity: 0, scale: 0.9 }}
        animate={{ opacity: 1, scale: 1 }}
        className="flex flex-col items-center justify-center py-10 space-y-4"
      >
        <motion.div
          initial={{ scale: 0 }}
          animate={{ scale: 1 }}
          transition={{ type: 'spring', stiffness: 200, damping: 15, delay: 0.1 }}
        >
          <div className="w-16 h-16 rounded-full bg-emerald-500/20 flex items-center justify-center">
            <CheckCircle2 size={32} className="text-emerald-400" />
          </div>
        </motion.div>
        <h3 className="text-lg font-bold text-white">Subscription Activated!</h3>
        <p className="text-sm text-[#a0a0a0] text-center">
          Welcome to <span className="text-white font-medium">{tier.name}</span> plan
        </p>
      </motion.div>
    );
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-5">
      {/* Plan summary */}
      <div className="flex items-center gap-3 p-3.5 rounded-xl bg-[#111111] border border-[#222222]">
        <div className="w-11 h-11 rounded-lg bg-[#1a1a1a] flex items-center justify-center shrink-0">
          {TIER_ICONS[tier.id] || <Star size={18} className="text-[#555]" />}
        </div>
        <div className="flex-1 min-w-0">
          <div className="font-semibold text-sm text-white">{tier.name} Plan</div>
          <div className="text-xs text-[#666]">
            {billingCycle === 'ANNUAL' ? 'Annual billing' : 'Monthly billing'}
          </div>
        </div>
        <div className="text-right shrink-0">
          <div className="text-lg font-bold text-white">${price.toFixed(2)}</div>
          <div className="text-[11px] text-[#555]">/mo</div>
        </div>
      </div>

      {/* Features */}
      <div className="space-y-2">
        <div className="text-xs font-medium text-[#888] uppercase tracking-wider">What's included</div>
        <div className="grid gap-1.5">
          {tier.features.slice(0, 5).map((feature, i) => (
            <div key={i} className="flex items-center gap-2 text-[13px]">
              <Check size={12} className="text-emerald-400/70 shrink-0" />
              <span className="text-[#999]">{feature}</span>
            </div>
          ))}
        </div>
      </div>

      {/* Order breakdown */}
      <div className="space-y-2 px-1">
        <div className="flex items-center justify-between text-sm">
          <span className="text-[#888]">{tier.name} subscription</span>
          <span className="text-[#ccc]">${price.toFixed(2)}/mo</span>
        </div>
        {billingCycle === 'ANNUAL' && (
          <>
            <div className="flex items-center justify-between text-sm">
              <span className="text-[#888]">Billed annually</span>
              <span className="text-[#ccc]">${totalPrice.toFixed(2)}/yr</span>
            </div>
            <div className="flex items-center justify-between text-sm">
              <span className="text-emerald-400/70">Annual savings</span>
              <span className="text-emerald-400/70">-${savingsPerYear.toFixed(2)}</span>
            </div>
          </>
        )}
        <div className="border-t border-[#222] my-2" />
        <div className="flex items-center justify-between">
          <span className="text-sm font-semibold text-white">
            {billingCycle === 'ANNUAL' ? 'Total per year' : 'Total per month'}
          </span>
          <span className="text-lg font-bold text-white">
            ${billingCycle === 'ANNUAL' ? totalPrice.toFixed(2) : price.toFixed(2)}
          </span>
        </div>
      </div>

      {/* Stripe Payment Element */}
      <div className="space-y-2">
        <label className="block text-xs font-medium text-[#888] uppercase tracking-wider">
          Payment Details
        </label>
        <div className="rounded-xl border border-[#222] bg-[#0a0a0a] p-4">
          <PaymentElement
            options={{
              layout: 'tabs',
              defaultValues: {},
            }}
          />
        </div>
      </div>

      {/* Error */}
      {error && (
        <motion.div
          initial={{ opacity: 0, y: -5 }}
          animate={{ opacity: 1, y: 0 }}
          className="flex items-center gap-2 p-3 rounded-lg bg-red-500/10 border border-red-500/20 text-red-400 text-sm"
        >
          <X size={14} className="shrink-0" />
          {error}
        </motion.div>
      )}

      {/* Submit */}
      <button
        type="submit"
        disabled={!stripe || processing}
        className="w-full flex items-center justify-center gap-2 bg-white text-black font-semibold py-3 px-6 rounded-xl hover:bg-gray-200 transition-all duration-150 active:scale-[0.98] disabled:opacity-50 disabled:pointer-events-none"
      >
        {processing ? (
          <Loader2 size={18} className="animate-spin" />
        ) : (
          <>
            <Lock size={14} />
            Subscribe — ${billingCycle === 'ANNUAL' ? totalPrice.toFixed(2) + '/yr' : price.toFixed(2) + '/mo'}
            <ArrowRight size={14} />
          </>
        )}
      </button>

      {/* Security footer */}
      <div className="flex items-center justify-center gap-4 pt-1">
        <div className="flex items-center gap-1.5 text-[10px] text-[#555]">
          <Shield size={10} />
          Encrypted
        </div>
        <div className="flex items-center gap-1.5 text-[10px] text-[#555]">
          <Lock size={10} />
          Secure checkout
        </div>
        <div className="flex items-center gap-1.5 text-[10px] text-[#555]">
          <CreditCard size={10} />
          Stripe
        </div>
      </div>

      {/* Cancel anytime */}
      <p className="text-center text-[11px] text-[#444]">
        Cancel anytime · No long-term commitment
      </p>
    </form>
  );
}

// Main modal wrapper
export function SubscriptionCheckoutModal({ isOpen, onClose, tier, billingCycle }: SubscriptionCheckoutModalProps) {
  const [clientSecret, setClientSecret] = useState<string | null>(null);
  const [stripePromise, setStripePromise] = useState<Promise<Stripe | null> | null>(null);
  const [subscriptionId, setSubscriptionId] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
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

    const initPayment = async () => {
      setLoading(true);
      setError(null);
      setClientSecret(null);
      setSubscriptionId(null);
      try {
        const res = await api.subscriptions.subscribe(tier.id);
        const data = res || {};
        setClientSecret(data.clientSecret);
        setSubscriptionId(data.subscriptionId);
        setStripePromise(loadStripe(data.publishableKey));
      } catch (err: any) {
        setError(err.message || 'Failed to initialize payment');
      } finally {
        setLoading(false);
      }
    };

    initPayment();
  }, [isOpen, tier, billingCycle]);

  if (!isOpen || !tier) return null;

  const elementsOptions: StripeElementsOptions = clientSecret
    ? {
        clientSecret,
        appearance: {
          theme: 'night',
          variables: {
            colorPrimary: '#ffffff',
            colorBackground: '#0a0a0a',
            colorText: '#ffffff',
            colorDanger: '#ef4444',
            colorTextSecondary: '#888888',
            colorTextPlaceholder: '#555555',
            fontFamily: 'Inter, system-ui, -apple-system, sans-serif',
            borderRadius: '10px',
            spacingUnit: '4px',
            fontSizeBase: '14px',
            colorIcon: '#666666',
          },
          rules: {
            '.Input': {
              backgroundColor: '#111111',
              border: '1px solid #333333',
              boxShadow: 'none',
              padding: '10px 12px',
              transition: 'border-color 0.15s ease',
            },
            '.Input:focus': {
              border: '1px solid #555555',
              boxShadow: 'none',
            },
            '.Input:hover': {
              border: '1px solid #444444',
            },
            '.Input--invalid': {
              border: '1px solid #ef4444',
            },
            '.Label': {
              color: '#888888',
              fontSize: '12px',
              fontWeight: '500',
              textTransform: 'uppercase' as any,
              letterSpacing: '0.05em',
              marginBottom: '6px',
            },
            '.Tab': {
              backgroundColor: '#111111',
              border: '1px solid #222222',
              color: '#888888',
              borderRadius: '8px',
              padding: '10px 12px',
            },
            '.Tab:hover': {
              backgroundColor: '#1a1a1a',
              color: '#cccccc',
            },
            '.Tab--selected': {
              backgroundColor: '#1a1a1a',
              border: '1px solid #333333',
              color: '#ffffff',
            },
            '.TabIcon': {
              fill: '#888888',
            },
            '.TabIcon--selected': {
              fill: '#ffffff',
            },
            '.Error': {
              color: '#ef4444',
              fontSize: '12px',
            },
          },
        },
      }
    : ({} as StripeElementsOptions);

  const handleSuccess = () => {
    onClose();
    // Refresh the page to reflect subscription status
    window.location.href = '/settings?subscription=success';
  };

  return (
    <AnimatePresence>
      {isOpen && (
        <div className="fixed inset-0 z-[9999] flex items-center justify-center">
          {/* Backdrop */}
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="absolute inset-0 bg-black/70 backdrop-blur-md"
            onClick={onClose}
          />

          {/* Modal */}
          <motion.div
            initial={{ opacity: 0, y: 30, scale: 0.95 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: 20, scale: 0.95 }}
            transition={{ type: 'spring', stiffness: 300, damping: 30 }}
            className="relative w-full max-w-md mx-4 bg-[#0a0a0a] border border-[#1a1a1a] rounded-2xl shadow-2xl shadow-black/50 overflow-hidden"
          >
            {/* Header */}
            <div className="flex items-center justify-between px-6 py-4 border-b border-[#1a1a1a]">
              <div className="flex items-center gap-3">
                <OgentiLogo size={22} variant="dark" />
                <h2 className="text-base font-semibold text-white">Subscribe</h2>
              </div>
              <button
                onClick={onClose}
                className="p-1.5 rounded-lg text-[#555] hover:text-white hover:bg-[#1a1a1a] transition-colors"
              >
                <X size={18} />
              </button>
            </div>

            {/* Body */}
            <div className="px-6 py-5 max-h-[75vh] overflow-y-auto">
              {loading ? (
                <div className="flex flex-col items-center justify-center py-12 space-y-3">
                  <Loader2 size={28} className="animate-spin text-[#555]" />
                  <p className="text-sm text-[#666]">Preparing payment...</p>
                </div>
              ) : error ? (
                <div className="flex flex-col items-center justify-center py-12 space-y-4">
                  <div className="w-12 h-12 rounded-full bg-red-500/10 flex items-center justify-center">
                    <X size={24} className="text-red-400" />
                  </div>
                  <p className="text-sm text-red-400 text-center">{error}</p>
                  <button
                    onClick={onClose}
                    className="text-sm text-[#888] hover:text-white transition-colors"
                  >
                    Close
                  </button>
                </div>
              ) : clientSecret && stripePromise && subscriptionId ? (
                <Elements stripe={stripePromise} options={elementsOptions}>
                  <SubscriptionPaymentForm
                    tier={tier}
                    billingCycle={billingCycle}
                    subscriptionId={subscriptionId}
                    onSuccess={handleSuccess}
                  />
                </Elements>
              ) : null}
            </div>
          </motion.div>
        </div>
      )}
    </AnimatePresence>
  );
}
