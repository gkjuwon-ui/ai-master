'use client';

import { Toaster } from 'react-hot-toast';

export function ToastProvider() {
  return (
    <Toaster
      position="bottom-right"
      toastOptions={{
        duration: 4000,
        style: {
          background: '#1a1a1a',
          color: '#ffffff',
          border: '1px solid #333333',
          borderRadius: '12px',
          fontSize: '14px',
        },
        success: {
          iconTheme: {
            primary: '#ffffff',
            secondary: '#000000',
          },
        },
        error: {
          iconTheme: {
            primary: '#888888',
            secondary: '#000000',
          },
        },
      }}
    />
  );
}
