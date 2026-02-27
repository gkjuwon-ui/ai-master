'use client';

import { useState, useEffect, useRef, Suspense } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { motion } from 'framer-motion';
import { Mail, ArrowRight, RefreshCw, CheckCircle } from 'lucide-react';
import { useAuthStore } from '@/store/authStore';
import { Button } from '@/components/common/Button';
import { OgentiLogo } from '@/components/common/OgentiLogo';
import toast from 'react-hot-toast';

function VerifyEmailContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const email = searchParams.get('email') || '';
  const { verifyEmail, resendVerification, isAuthenticated, pendingVerificationCode } = useAuthStore();

  const [code, setCode] = useState(['', '', '', '', '', '']);
  const [loading, setLoading] = useState(false);
  const [resending, setResending] = useState(false);
  const [resendCooldown, setResendCooldown] = useState(0);
  const [verified, setVerified] = useState(false);
  const [displayCode, setDisplayCode] = useState<string | null>(pendingVerificationCode);
  const inputRefs = useRef<(HTMLInputElement | null)[]>([]);

  // Redirect if already authenticated
  useEffect(() => {
    if (isAuthenticated) router.replace('/workspace');
  }, [isAuthenticated, router]);

  // Redirect if no email
  useEffect(() => {
    if (!email) router.replace('/auth/register');
  }, [email, router]);

  // ESC key to go back
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        e.preventDefault();
        router.push('/auth/register');
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [router]);

  // Resend cooldown timer
  useEffect(() => {
    if (resendCooldown <= 0) return;
    const timer = setInterval(() => setResendCooldown((c) => c - 1), 1000);
    return () => clearInterval(timer);
  }, [resendCooldown]);

  const handleInputChange = (index: number, value: string) => {
    if (!/^\d*$/.test(value)) return; // Only allow digits
    const newCode = [...code];
    newCode[index] = value.slice(-1); // Only keep last digit
    setCode(newCode);

    // Auto-focus next input
    if (value && index < 5) {
      inputRefs.current[index + 1]?.focus();
    }
  };

  const handleKeyDown = (index: number, e: React.KeyboardEvent) => {
    if (e.key === 'Backspace' && !code[index] && index > 0) {
      inputRefs.current[index - 1]?.focus();
    }
  };

  const handlePaste = (e: React.ClipboardEvent) => {
    e.preventDefault();
    const pasted = e.clipboardData.getData('text').replace(/\D/g, '').slice(0, 6);
    if (pasted.length === 6) {
      const newCode = pasted.split('');
      setCode(newCode);
      inputRefs.current[5]?.focus();
    }
  };

  const handleVerify = async () => {
    const fullCode = code.join('');
    if (fullCode.length !== 6) {
      toast.error('Please enter the 6-digit verification code.');
      return;
    }

    setLoading(true);
    try {
      await verifyEmail(email, fullCode);
      setVerified(true);
      toast.success('Email verified successfully!');
      setTimeout(() => router.replace('/workspace'), 1500);
    } catch (err: any) {
      toast.error(err.message || 'Verification failed.');
      setCode(['', '', '', '', '', '']);
      inputRefs.current[0]?.focus();
    } finally {
      setLoading(false);
    }
  };

  // Auto-submit when all 6 digits entered
  useEffect(() => {
    const fullCode = code.join('');
    if (fullCode.length === 6 && !loading) {
      handleVerify();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [code]);

  const handleResend = async () => {
    if (resendCooldown > 0) return;
    setResending(true);
    try {
      const newCode = await resendVerification(email);
      if (newCode) setDisplayCode(newCode);
      toast.success('Verification code has been resent.');
      setResendCooldown(60);
    } catch (err: any) {
      toast.error(err.message || 'Failed to resend code.');
    } finally {
      setResending(false);
    }
  };

  if (!email) return null;

  return (
    <div className="min-h-full flex items-center justify-center px-4">
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        className="w-full max-w-sm"
      >
        <div className="text-center mb-8">
          <div className="flex justify-center mb-4">
            <OgentiLogo size={40} variant="dark" />
          </div>
          {verified ? (
            <motion.div
              initial={{ scale: 0.8, opacity: 0 }}
              animate={{ scale: 1, opacity: 1 }}
              className="flex flex-col items-center"
            >
              <CheckCircle size={48} className="text-white mb-4" />
              <h1 className="text-2xl font-bold mb-2">Verified!</h1>
              <p className="text-sm text-text-secondary">
                Redirecting to workspace...
              </p>
            </motion.div>
          ) : (
            <>
              <div className="w-14 h-14 rounded-2xl bg-black/[0.05] border border-white/[0.08] flex items-center justify-center text-black/40 mx-auto mb-5">
                <Mail size={26} />
              </div>
              <h1 className="text-2xl font-bold mb-2">Email Verification</h1>
              <p className="text-sm text-text-secondary">
                Enter the 6-digit code sent to
                <br /><span className="text-black/70 font-medium">{email}</span>
              </p>

              {/* Show verification code when SMTP is not configured (desktop mode) */}
              {displayCode && (
                <div className="mt-4 p-4 rounded-xl bg-black/5 border border-black/10">
                  <p className="text-xs text-black/50 mb-1.5 uppercase tracking-wider font-medium">Verification Code</p>
                  <p className="text-2xl font-mono font-bold text-white tracking-[0.3em] text-center">
                    {displayCode}
                  </p>
                  <p className="text-[11px] text-black/40 mt-2 text-center">
                    Desktop mode: Code displayed directly without email delivery
                  </p>
                </div>
              )}
            </>
          )}
        </div>

        {!verified && (
          <div className="card p-6 space-y-6">
            {/* 6-digit code input */}
            <div className="flex justify-center gap-2.5" onPaste={handlePaste}>
              {code.map((digit, index) => (
                <input
                  key={index}
                  ref={(el) => { inputRefs.current[index] = el; }}
                  type="text"
                  inputMode="numeric"
                  maxLength={1}
                  value={digit}
                  onChange={(e) => handleInputChange(index, e.target.value)}
                  onKeyDown={(e) => handleKeyDown(index, e)}
                  autoFocus={index === 0}
                  className="w-12 h-14 text-center text-xl font-mono font-bold rounded-xl 
                    border border-white/[0.1] bg-black/[0.03] text-white
                    focus:border-black/30 focus:bg-black/[0.06] focus:outline-none focus:ring-1 focus:ring-white/20
                    transition-all duration-200 placeholder-white/20"
                  placeholder="·"
                />
              ))}
            </div>

            {/* Verify button */}
            <Button
              type="button"
              loading={loading}
              className="w-full"
              onClick={handleVerify}
              icon={<ArrowRight size={16} />}
            >
              Verify
            </Button>

            {/* Resend */}
            <div className="text-center space-y-2">
              <p className="text-xs text-text-tertiary">
                Didn't receive the code?
              </p>
              <button
                type="button"
                onClick={handleResend}
                disabled={resendCooldown > 0 || resending}
                className="inline-flex items-center gap-1.5 text-xs text-accent hover:underline disabled:opacity-40 disabled:cursor-not-allowed disabled:no-underline"
              >
                <RefreshCw size={12} className={resending ? 'animate-spin' : ''} />
                {resendCooldown > 0 ? `Resend (${resendCooldown}s)` : 'Resend verification code'}
              </button>
            </div>

            {/* Back to register */}
            <p className="text-center text-xs text-text-tertiary pt-2 border-t border-white/[0.06]">
              <button
                type="button"
                onClick={() => router.push('/auth/register')}
                className="text-accent hover:underline"
              >
                ← Back to sign up
              </button>
            </p>
          </div>
        )}
      </motion.div>
    </div>
  );
}

export default function VerifyEmailPage() {
  return (
    <Suspense fallback={
      <div className="min-h-full flex items-center justify-center px-4">
        <div className="text-black/40">Loading...</div>
      </div>
    }>
      <VerifyEmailContent />
    </Suspense>
  );
}
