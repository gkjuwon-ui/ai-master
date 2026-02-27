'use client';

import { useState, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import Link from 'next/link';
import { motion } from 'framer-motion';
import { Eye, EyeOff, ArrowRight } from 'lucide-react';
import { useAuthStore } from '@/store/authStore';
import { Button } from '@/components/common/Button';
import { OgentiLogo } from '@/components/common/OgentiLogo';
import toast from 'react-hot-toast';

export default function LoginPage() {
  const router = useRouter();
  const { login, isAuthenticated, pendingVerificationEmail } = useAuthStore();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [loading, setLoading] = useState(false);

  // Redirect if already authenticated
  useEffect(() => {
    if (isAuthenticated) {
      router.replace('/workspace');
    }
  }, [isAuthenticated, router]);

  // If pending verification (set by login when EMAIL_NOT_VERIFIED), redirect to verify page
  useEffect(() => {
    if (pendingVerificationEmail) {
      router.replace(`/auth/verify-email?email=${encodeURIComponent(pendingVerificationEmail)}`);
    }
  }, [pendingVerificationEmail, router]);

  // ESC key to go back
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        e.preventDefault();
        router.push('/');
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [router]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!email || !password) { toast.error('Fill in all fields'); return; }
    setLoading(true);
    try {
      await login(email, password);
      toast.success('Welcome back!');
      router.replace('/workspace');
    } catch (err: any) {
      // If email not verified, the store already sets pendingVerificationEmail
      // and the useEffect will redirect to the verification page
      if (err.code === 'EMAIL_NOT_VERIFIED') {
        toast('Email verification required. Redirecting to verification page.', { icon: '📧' });
      } else {
        toast.error(err.message || 'Login failed');
      }
    } finally {
      setLoading(false);
    }
  };

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
          <h1 className="text-2xl font-bold mb-2">Sign In</h1>
          <p className="text-sm text-text-secondary">
            Access your workspace and agents
          </p>
        </div>

        <form onSubmit={handleSubmit} className="card p-6 space-y-4">
          <div>
            <label className="block text-xs font-medium text-text-secondary mb-1.5">Email</label>
            <input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="input-field w-full"
              placeholder="you@example.com"
              autoFocus
            />
          </div>

          <div>
            <label className="block text-xs font-medium text-text-secondary mb-1.5">Password</label>
            <div className="relative">
              <input
                type={showPassword ? 'text' : 'password'}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className="input-field w-full pr-10"
                placeholder="••••••••"
              />
              <button
                type="button"
                onClick={() => setShowPassword(!showPassword)}
                className="absolute right-3 top-1/2 -translate-y-1/2 text-text-tertiary hover:text-text-primary"
              >
                {showPassword ? <EyeOff size={16} /> : <Eye size={16} />}
              </button>
            </div>
          </div>

          <Button type="submit" loading={loading} className="w-full" icon={<ArrowRight size={16} />}>
            Sign In
          </Button>

          <p className="text-center text-xs text-text-tertiary">
            Don&apos;t have an account?{' '}
            <Link href="/auth/register" className="text-accent hover:underline">
              Create one
            </Link>
          </p>
        </form>

        {/* Demo credentials hint — development only */}
        {process.env.NODE_ENV !== 'production' && (
          <div className="mt-4 p-3 rounded-lg bg-bg-secondary border border-border-primary space-y-1">
            <p className="text-[11px] text-text-tertiary text-center font-semibold mb-1">Demo Accounts</p>
            <button
              onClick={() => { setEmail('admin@ogenti.app'); setPassword('admin123456'); }}
              className="block w-full text-[11px] text-text-tertiary text-center hover:text-accent transition-colors"
            >
              Admin: admin@ogenti.app / admin123456
            </button>
            <button
              onClick={() => { setEmail('dev@ogenti.app'); setPassword('developer123'); }}
              className="block w-full text-[11px] text-text-tertiary text-center hover:text-accent transition-colors"
            >
              Developer: dev@ogenti.app / developer123
            </button>
          </div>
        )}
      </motion.div>
    </div>
  );
}
