'use client';

import { useEffect } from 'react';
import Link from 'next/link';

export default function WorkspaceError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    console.error('[WorkspaceError]', error);
  }, [error]);

  return (
    <div className="min-h-full flex items-center justify-center p-8">
      <div className="text-center space-y-4 max-w-md">
        <div className="w-16 h-16 bg-black/5 rounded-full flex items-center justify-center mx-auto">
          <svg className="w-8 h-8 text-gray-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-2.5L13.732 4c-.77-.833-1.964-.833-2.732 0L4.082 16.5c-.77.833.192 2.5 1.732 2.5z" />
          </svg>
        </div>
        <h2 className="text-lg font-semibold text-text-primary">Workspace Error</h2>
        <p className="text-sm text-text-secondary">{error.message || 'Failed to load workspace'}</p>
        <div className="flex justify-center gap-3">
          <button
            onClick={reset}
            className="px-4 py-2 text-white text-sm rounded-lg transition-colors"
            style={{ background: 'linear-gradient(135deg, #f08535 0%, #c04510 100%)' }}
          >
            Try Again
          </button>
          <Link
            href="/"
            className="px-4 py-2 bg-bg-elevated text-text-primary text-sm rounded-lg hover:bg-bg-hover transition-colors border border-border-primary"
          >
            Go Home
          </Link>
        </div>
      </div>
    </div>
  );
}
