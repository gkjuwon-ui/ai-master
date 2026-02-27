'use client';

import { cn } from '@/lib/utils';
import { Loader2 } from 'lucide-react';

interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: 'primary' | 'secondary' | 'ghost' | 'danger';
  size?: 'sm' | 'md' | 'lg';
  loading?: boolean;
  icon?: React.ReactNode;
}

export function Button({
  variant = 'primary',
  size = 'md',
  loading = false,
  icon,
  children,
  className,
  disabled,
  ...props
}: ButtonProps) {
  const variants = {
    primary: 'text-white font-medium',  // gradient bg applied via style
    secondary: 'bg-bg-elevated text-text-primary border border-border-primary hover:bg-bg-hover hover:border-border-secondary',
    ghost: 'text-text-secondary hover:text-text-primary hover:bg-bg-elevated',
    danger: 'bg-black/5 text-gray-400 border border-black/10 hover:bg-black/10',
  };

  const sizes = {
    sm: 'px-3 py-1.5 text-xs',
    md: 'px-4 py-2 text-sm',
    lg: 'px-6 py-3 text-base',
  };

  return (
    <button
      className={cn(
        'inline-flex items-center justify-center gap-2 rounded-lg transition-all duration-150 active:scale-[0.98] disabled:opacity-50 disabled:pointer-events-none',
        variants[variant],
        sizes[size],
        className
      )}
      style={variant === 'primary' ? { background: 'linear-gradient(135deg, #f08535 0%, #c04510 100%)' } : undefined}
      disabled={disabled || loading}
      {...props}
    >
      {loading ? <Loader2 size={16} className="animate-spin" /> : icon}
      {children}
    </button>
  );
}
