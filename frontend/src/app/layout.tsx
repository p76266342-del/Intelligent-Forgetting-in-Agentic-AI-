import type { Metadata } from 'next';
import './globals.css';
import { AuthProvider } from '@/lib/auth-context';
import { AppShell } from '@/components/AppShell';

export const metadata: Metadata = {
  title: 'Intelligent Forgetting in Agentic AI | Next.js + FastAPI Workspace',
  description:
    'A multi-user agentic AI memory-management platform featuring mathematical retention scoring, Qdrant semantic recall, cognitive forgetting, and reinforcement learning.',
  keywords: [
    'Agentic AI',
    'Intelligent Forgetting',
    'Memory Management',
    'Cognitive Architecture',
    'FastAPI',
    'Next.js',
    'Qdrant',
    'Google Gemini',
  ],
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body className="min-h-screen bg-slate-50 text-slate-900 antialiased selection:bg-indigo-500/20 selection:text-indigo-900">
        <AuthProvider>
          <AppShell>{children}</AppShell>
        </AuthProvider>
      </body>
    </html>
  );
}
