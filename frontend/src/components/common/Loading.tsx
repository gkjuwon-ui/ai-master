'use client';

import { cn } from '@/lib/utils';

export function Loading({ className, text = 'Loading...' }: { className?: string; text?: string }) {
  return (
    <div className={cn('flex flex-col items-center justify-center py-12', className)}>
      <div className="relative w-10 h-10">
        <div className="absolute inset-0 border-2 border-border-primary rounded-full" />
        <div className="absolute inset-0 border-2 border-white border-t-transparent rounded-full animate-spin" />
      </div>
      <p className="mt-4 text-sm text-text-tertiary">{text}</p>
    </div>
  );
}

export function LoadingSkeleton({ count = 3 }: { count?: number }) {
  return (
    <div className="space-y-4">
      {Array.from({ length: count }).map((_, i) => (
        <div key={i} className="card p-4 space-y-3">
          <div className="h-4 bg-bg-elevated rounded w-3/4 animate-pulse" />
          <div className="h-3 bg-bg-elevated rounded w-1/2 animate-pulse" />
          <div className="h-3 bg-bg-elevated rounded w-5/6 animate-pulse" />
        </div>
      ))}
    </div>
  );
}

export function EmptyState({
  icon,
  title,
  description,
  action,
}: {
  icon?: React.ReactNode;
  title: string;
  description?: string;
  action?: React.ReactNode | { label: string; onClick: () => void };
}) {
  let actionNode: React.ReactNode = null;
  if (action) {
    if (typeof action === 'object' && action !== null && 'label' in action) {
      const { label, onClick } = action as { label: string; onClick: () => void };
      actionNode = (
        <button onClick={onClick} className="px-4 py-2 text-white rounded-lg text-sm font-medium transition-colors" style={{ background: 'linear-gradient(135deg, #f08535 0%, #c04510 100%)' }}>
          {label}
        </button>
      );
    } else {
      actionNode = action as React.ReactNode;
    }
  }

  return (
    <div className="flex flex-col items-center justify-center py-16 text-center">
      {icon && <div className="mb-4 text-text-tertiary">{icon}</div>}
      <h3 className="text-lg font-medium text-text-primary mb-2">{title}</h3>
      {description && <p className="text-sm text-text-tertiary max-w-md">{description}</p>}
      {actionNode && <div className="mt-6">{actionNode}</div>}
    </div>
  );
}
