'use client';

import Link from 'next/link';
import { useState } from 'react';
import { fetchJson, type AuthResponse } from '@/lib/api';
import { setToken } from '@/lib/auth';

export default function LandingPage() {
  const [loadingDemo, setLoadingDemo] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleExploreDemo() {
    setLoadingDemo(true);
    setError(null);
    try {
      const result = await fetchJson<AuthResponse>('/api/v1/auth/demo', { method: 'POST' });
      setToken(result.access_token);
      window.location.href = '/dashboard';
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not start the demo right now');
      setLoadingDemo(false);
    }
  }

  return (
    <main className="flex min-h-screen items-center justify-center bg-slate-950 px-6">
      <div className="w-full max-w-lg text-center">
        <p className="mb-3 text-sm font-semibold uppercase tracking-[0.3em] text-sky-400">Welcome to</p>
        <h1 className="mb-3 text-5xl font-bold text-white">NusaFlow</h1>
        <p className="mb-2 text-lg font-medium text-slate-300">Supply Chain Control Tower</p>
        <p className="mx-auto mb-10 max-w-md text-sm leading-relaxed text-slate-400">
          Monitor inventory, shipments, and risks. Forecast demand, get replenishment
          recommendations, and simulate supply scenarios before they happen.
        </p>

        <div className="flex flex-col items-center gap-3">
          <button
            onClick={handleExploreDemo}
            disabled={loadingDemo}
            className="w-full max-w-xs rounded-lg bg-sky-600 px-6 py-3 text-sm font-semibold text-white transition-colors hover:bg-sky-500 disabled:cursor-not-allowed disabled:opacity-60"
          >
            {loadingDemo ? 'Loading demo…' : 'Explore Demo'}
          </button>
          <Link
            href="/signup"
            className="w-full max-w-xs rounded-lg border border-slate-700 px-6 py-3 text-sm font-semibold text-slate-200 transition-colors hover:border-slate-500 hover:bg-slate-900"
          >
            Create Workspace
          </Link>
        </div>

        {error && <p className="mt-4 text-sm text-rose-400">{error}</p>}

        <p className="mt-8 text-sm text-slate-500">
          Already have a workspace?{' '}
          <Link href="/login" className="font-medium text-sky-400 hover:underline">Log in</Link>
        </p>
      </div>
    </main>
  );
}
