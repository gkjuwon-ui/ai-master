'use client';

import { useState, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import Link from 'next/link';
import { motion } from 'framer-motion';
import { Eye, EyeOff, ArrowRight, UserPlus } from 'lucide-react';
import { useAuthStore } from '@/store/authStore';
import { Button } from '@/components/common/Button';
import { OgentiLogo } from '@/components/common/OgentiLogo';
import toast from 'react-hot-toast';

export default function RegisterPage() {
  const router = useRouter();
  const { register, isAuthenticated, pendingVerificationEmail } = useAuthStore();
  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [loading, setLoading] = useState(false);

  // Redirect if already authenticated (desktop auto-verify)
  useEffect(() => {
    if (isAuthenticated) {
      router.replace('/workspace');
    }
  }, [isAuthenticated, router]);

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

  // When pendingVerificationEmail is set, redirect to verify page
  useEffect(() => {
    if (pendingVerificationEmail) {
      router.replace(`/auth/verify-email?email=${encodeURIComponent(pendingVerificationEmail)}`);
    }
  }, [pendingVerificationEmail, router]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!name || !email || !password) { toast.error('Fill in all fields'); return; }
    if (password.length < 8) { toast.error('Password must be at least 8 characters'); return; }
    if (password !== confirmPassword) { toast.error('Passwords do not match'); return; }
    setLoading(true);
    try {
      // Auto-generate valid username from email (before @, alphanumeric only)
      const autoUsername = email.split('@')[0].replace(/[^a-zA-Z0-9_-]/g, '').toLowerCase().slice(0, 30) || `user_${Date.now()}`;
      await register({ email, username: autoUsername, password, displayName: name });
      // After register, the store will set pendingVerificationEmail
      // and the useEffect above will redirect
    } catch (err: any) {
      toast.error(err.message || 'Registration failed');
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
          <h1 className="text-2xl font-bold mb-2">Create Account</h1>
          <p className="text-sm text-text-secondary">
            Join ogenti to discover and run agents
          </p>
        </div>

        <form onSubmit={handleSubmit} className="card p-6 space-y-4">
          <div>
            <label className="block text-xs font-medium text-text-secondary mb-1.5">Name</label>
            <input
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              className="input-field w-full"
              placeholder="Your name"
              autoFocus
            />
          </div>

          <div>
            <label className="block text-xs font-medium text-text-secondary mb-1.5">Email</label>
            <input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="input-field w-full"
              placeholder="you@example.com"
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
                placeholder="8+ characters"
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

          <div>
            <label className="block text-xs font-medium text-text-secondary mb-1.5">Confirm Password</label>
            <input
              type="password"
              value={confirmPassword}
              onChange={(e) => setConfirmPassword(e.target.value)}
              className="input-field w-full"
              placeholder="••••••••"
            />
          </div>

          <Button type="submit" loading={loading} className="w-full" icon={<UserPlus size={16} />}>
            Create Account
          </Button>

          <p className="text-center text-xs text-text-tertiary">
            Already have an account?{' '}
            <Link href="/auth/login" className="text-accent hover:underline">
              Sign in
            </Link>
          </p>
        </form>
      </motion.div>
    </div>
  );
}
