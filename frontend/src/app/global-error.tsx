'use client';

import { useEffect } from 'react';

/**
 * Global error boundary ??catches errors in the ROOT LAYOUT
 * (AuthProvider, Sidebar, Header, etc.) that error.tsx cannot catch.
 *
 * Without this file, any error in the root layout shows the generic
 * "Application error: a client-side exception has occurred" message.
 */
export default function GlobalError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    console.error('[GlobalError] Root layout error:', error);
  }, [error]);

  return (
    <html lang="en" className="dark">
      <body style={{ backgroundColor: '#000', color: '#fff', margin: 0, fontFamily: 'system-ui, sans-serif' }}>
        <div style={{ minHeight: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center', padding: '2rem' }}>
          <div style={{ textAlign: 'center', maxWidth: '28rem' }}>
            <div style={{
              width: '4rem', height: '4rem', borderRadius: '50%',
              background: 'rgba(255,255,255,0.05)', display: 'flex',
              alignItems: 'center', justifyContent: 'center', margin: '0 auto 1.5rem',
            }}>
              <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="#888" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-2.5L13.732 4c-.77-.833-1.964-.833-2.732 0L4.082 16.5c-.77.833.192 2.5 1.732 2.5z" />
              </svg>
            </div>
            <h2 style={{ fontSize: '1.25rem', fontWeight: 600, marginBottom: '0.5rem' }}>
              Something went wrong
            </h2>
            <p style={{ fontSize: '0.875rem', color: '#a0a0a0', marginBottom: '1.5rem' }}>
              {error.message || 'An unexpected error occurred in the application layout.'}
            </p>
            <button
              onClick={reset}
              style={{
                padding: '0.5rem 1.5rem', color: '#fff', fontSize: '0.875rem',
                borderRadius: '0.5rem', border: 'none', cursor: 'pointer',
                background: 'linear-gradient(135deg, #f08535 0%, #c04510 100%)',
              }}
            >
              Try Again
            </button>
          </div>
        </div>
      </body>
    </html>
  );
}
