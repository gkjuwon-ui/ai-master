'use client';

import { useState, useEffect, useCallback } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { loadStripe, Stripe, StripeElementsOptions } from '@stripe/stripe-js';
import { Elements, PaymentElement, useStripe, useElements } from '@stripe/react-stripe-js';
import {
  X, Shield, CreditCard, CheckCircle2, Loader2,
  Lock, ArrowRight, ShoppingCart, Sparkles
} from 'lucide-react';
import { api } from '@/lib/api';
import { formatPrice } from '@/lib/utils';
import { OgentiLogo } from '@/components/common/OgentiLogo';
import toast from 'react-hot-toast';

interface CheckoutModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSuccess: () => void;
  agent: {
    id: string;
    name: string;
    description: string;
    price: number;
    currency?: string;
    category: string;
    developer?: {
      displayName?: string;
      name?: string;
    };
    pricingModel?: string;
  };
  /** Original price before subscription discount (optional) */
  originalPrice?: number;
  /** Whether user has active subscription */
  hasSubscription?: boolean;
}

// Inner payment form component
function PaymentForm({
  agent,
  onSuccess,
  onClose,
}: {
  agent: CheckoutModalProps['agent'];
  onSuccess: () => void;
  onClose: () => void;
}) {
  const stripe = useStripe();
  const elements = useElements();
  const [processing, setProcessing] = useState(false);
  const [succeeded, setSucceeded] = useState(false);
  const [error, setError] = useState<string | null>(null);

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
          return_url: `${window.location.origin}/marketplace/${agent.id}?purchased=true`,
        },
      });

      if (submitError) {
        setError(submitError.message || 'Payment failed');
        setProcessing(false);
        return;
      }

      if (paymentIntent && paymentIntent.status === 'succeeded') {
        // Confirm purchase on backend
        try {
          await api.stripe.confirmCredit(paymentIntent.id, agent.price || 0);
        } catch {
          // Even if this fails, payment succeeded — webhook will handle it
        }
        setSucceeded(true);
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
        <h3 className="text-lg font-bold text-white">Payment Successful!</h3>
        <p className="text-sm text-[#a0a0a0] text-center">
          You now have access to <span className="text-white font-medium">{agent.name}</span>
        </p>
      </motion.div>
    );
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-5">
      {/* Agent summary */}
      <div className="flex items-center gap-3 p-3.5 rounded-xl bg-[#111111] border border-[#222222]">
        <div className="w-11 h-11 rounded-lg bg-[#1a1a1a] flex items-center justify-center shrink-0">
          <Sparkles size={18} className="text-[#555]" />
        </div>
        <div className="flex-1 min-w-0">
          <div className="font-semibold text-sm text-white truncate">{agent.name}</div>
          <div className="text-xs text-[#666] truncate">
            by {agent.developer?.displayName || agent.developer?.name || 'Unknown'}
          </div>
        </div>
        <div className="text-lg font-bold text-white shrink-0">
          {formatPrice(agent.price, agent.currency)}
        </div>
      </div>

      {/* Order breakdown */}
      <div className="space-y-2 px-1">
        <div className="flex items-center justify-between text-sm">
          <span className="text-[#888]">Agent license</span>
          <span className="text-[#ccc]">{formatPrice(agent.price, agent.currency)}</span>
        </div>
        {agent.pricingModel?.includes('SUBSCRIPTION') && (
          <div className="flex items-center justify-between text-sm">
            <span className="text-[#888]">Billing</span>
            <span className="text-[#ccc]">
              {agent.pricingModel === 'SUBSCRIPTION_MONTHLY' ? 'Monthly' : 'Yearly'}
            </span>
          </div>
        )}
        <div className="border-t border-[#222] my-2" />
        <div className="flex items-center justify-between">
          <span className="text-sm font-semibold text-white">Total</span>
          <span className="text-lg font-bold text-white">{formatPrice(agent.price, agent.currency)}</span>
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
            Pay {formatPrice(agent.price, agent.currency)}
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
    </form>
  );
}

// Free agent payment form — looks identical to Stripe form but calls claimFreeAgent
function FreePaymentForm({
  agent,
  onSuccess,
  onClose,
  originalPrice,
  hasSubscription,
}: {
  agent: CheckoutModalProps['agent'];
  onSuccess: () => void;
  onClose: () => void;
  originalPrice?: number;
  hasSubscription?: boolean;
}) {
  const [processing, setProcessing] = useState(false);
  const [succeeded, setSucceeded] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setProcessing(true);
    setError(null);

    try {
      await api.claimFreeAgent(agent.id);
      setSucceeded(true);
      setTimeout(() => {
        onSuccess();
      }, 2000);
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
        <h3 className="text-lg font-bold text-white">Purchase Successful!</h3>
        <p className="text-sm text-[#a0a0a0] text-center">
          You now have access to <span className="text-white font-medium">{agent.name}</span>
        </p>
      </motion.div>
    );
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-5">
      {/* Agent summary */}
      <div className="flex items-center gap-3 p-3.5 rounded-xl bg-[#111111] border border-[#222222]">
        <div className="w-11 h-11 rounded-lg bg-[#1a1a1a] flex items-center justify-center shrink-0">
          <Sparkles size={18} className="text-[#555]" />
        </div>
        <div className="flex-1 min-w-0">
          <div className="font-semibold text-sm text-white truncate">{agent.name}</div>
          <div className="text-xs text-[#666] truncate">
            by {agent.developer?.displayName || agent.developer?.name || 'Unknown'}
          </div>
        </div>
        <div className="text-lg font-bold text-white shrink-0">
          {formatPrice(agent.price, agent.currency)}
        </div>
      </div>

      {/* Order breakdown */}
      <div className="space-y-2 px-1">
        <div className="flex items-center justify-between text-sm">
          <span className="text-[#888]">Agent license</span>
          <span className="text-[#ccc]">{formatPrice(agent.price, agent.currency)}</span>
        </div>
        <div className="border-t border-[#222] my-2" />
        <div className="flex items-center justify-between">
          <span className="text-sm font-semibold text-white">Total</span>
          <span className="text-lg font-bold text-white">{formatPrice(agent.price, agent.currency)}</span>
        </div>
      </div>

      {/* Free notice */}
      <div className="flex items-center gap-2.5 p-3.5 rounded-xl bg-emerald-500/5 border border-emerald-500/15">
        <CheckCircle2 size={16} className="text-emerald-400 shrink-0" />
        <p className="text-xs text-emerald-300/80">
          {hasSubscription && originalPrice && originalPrice > 0
            ? `Included in your subscription plan. Original price: ${formatPrice(originalPrice, agent.currency)} → $0`
            : 'This agent is free. No payment will be charged.'}
        </p>
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
        disabled={processing}
        className="w-full flex items-center justify-center gap-2 bg-white text-black font-semibold py-3 px-6 rounded-xl hover:bg-gray-200 transition-all duration-150 active:scale-[0.98] disabled:opacity-50 disabled:pointer-events-none"
      >
        {processing ? (
          <Loader2 size={18} className="animate-spin" />
        ) : (
          <>
            <Lock size={14} />
            Confirm Purchase — {formatPrice(agent.price, agent.currency)}
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
    </form>
  );
}

// Main modal wrapper
export function CheckoutModal({ isOpen, onClose, onSuccess, agent, originalPrice, hasSubscription }: CheckoutModalProps) {
  const [clientSecret, setClientSecret] = useState<string | null>(null);
  const [stripePromise, setStripePromise] = useState<Promise<Stripe | null> | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const isFreeAgent = agent?.price === 0;

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
    if (!isOpen || !agent || isFreeAgent) return;

    const initPayment = async () => {
      setLoading(true);
      setError(null);
      setClientSecret(null);
      try {
        const res = await api.stripe.createPaymentIntent(agent.price || 0);
        const { clientSecret: cs, publishableKey: pk } = res ?? {};
        setClientSecret(cs);
        setStripePromise(loadStripe(pk));
      } catch (err: any) {
        setError(err.message || 'Failed to initialize payment');
      } finally {
        setLoading(false);
      }
    };

    initPayment();
  }, [isOpen, agent, isFreeAgent]);

  if (!isOpen) return null;

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
                <h2 className="text-base font-semibold text-white">Checkout</h2>
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
              {isFreeAgent ? (
                <FreePaymentForm agent={agent} onSuccess={onSuccess} onClose={onClose} originalPrice={originalPrice} hasSubscription={hasSubscription} />
              ) : loading ? (
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
              ) : clientSecret && stripePromise ? (
                <Elements stripe={stripePromise} options={elementsOptions}>
                  <PaymentForm agent={agent} onSuccess={onSuccess} onClose={onClose} />
                </Elements>
              ) : null}
            </div>
          </motion.div>
        </div>
      )}
    </AnimatePresence>
  );
}
