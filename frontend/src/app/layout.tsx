import type { Metadata, Viewport } from 'next';
import './globals.css';
import { Header } from '@/components/layout/Header';
import { Sidebar } from '@/components/layout/Sidebar';
import { ToastProvider } from '@/components/common/Toast';
import { AuthProvider } from '@/components/providers/AuthProvider';
import { OnboardingTutorial } from '@/components/common/OnboardingTutorial';

export const metadata: Metadata = {
  title: 'ogenti',
  description: 'AI agents that control your device — powered by ogenti',
  icons: { icon: '/favicon.ico' },
  appleWebApp: {
    capable: true,
    statusBarStyle: 'black-translucent',
  },
};

export const viewport: Viewport = {
  width: 'device-width',
  initialScale: 1,
  maximumScale: 1,
  userScalable: false,
  viewportFit: 'cover',
  themeColor: '#ffffff',
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body className="bg-bg-primary text-text-primary min-h-screen">
        {/* Critical CSS fallback — ensures links/styles work when external CSS fails to load (e.g. Electron) */}
        <style dangerouslySetInnerHTML={{ __html: `
          a{color:inherit;text-decoration:none}
          a:hover{color:#e86520}
          body{background:#000;color:#fff;margin:0;font-family:Inter,system-ui,sans-serif}
        ` }} />
        <AuthProvider>
          <div className="flex h-screen overflow-hidden">
            <Sidebar />
            <div className="flex-1 flex flex-col overflow-hidden">
              <Header />
              <main className="flex-1 overflow-y-auto">{children}</main>
            </div>
          </div>
          <ToastProvider />
          <OnboardingTutorial />
        </AuthProvider>
      </body>
    </html>
  );
}
