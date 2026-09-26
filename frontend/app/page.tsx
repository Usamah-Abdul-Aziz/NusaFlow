'use client';

import Link from 'next/link';
import { useEffect, useState } from 'react';
import { fetchJson, getSession, type AuthResponse, type MeResponse } from '@/lib/api';
import { clearToken, setToken } from '@/lib/auth';

export default function LandingPage() {
  const [session, setSession] = useState<MeResponse | null>(null);
  const [loadingDemo, setLoadingDemo] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    // A returning visitor with a valid token gets a direct route into their
    // workspace; an expired token is quietly dropped (getSession clears the
    // cookie) so it can't trap them out of signup later. Until this resolves
    // the anonymous CTAs show (the common first-visit case) and swap in the
    // "Continue to ..." button once a session is confirmed.
    getSession().then(setSession);
  }, []);

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

  function handleSignOut() {
    clearToken();
    setSession(null);
  }

  const workspaceLabel = session?.workspace.name ?? 'your workspace';

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
          {session ? (
            <>
              <Link
                href="/dashboard"
                className="block w-full max-w-xs rounded-lg bg-sky-600 px-6 py-3 text-sm font-semibold text-white transition-colors hover:bg-sky-500"
              >
                Continue to {workspaceLabel}
              </Link>
              {session.workspace.is_demo ? (
                // The path that used to be swallowed by the demo token:
                // make it explicit and prominent here.
                <Link
                  href="/signup"
                  className="w-full max-w-xs rounded-lg border border-slate-700 px-6 py-3 text-sm font-semibold text-slate-200 transition-colors hover:border-slate-500 hover:bg-slate-900"
                >
                  Create my own workspace
                </Link>
              ) : (
                <button
                  onClick={handleExploreDemo}
                  disabled={loadingDemo}
                  className="w-full max-w-xs rounded-lg border border-slate-700 px-6 py-3 text-sm font-semibold text-slate-200 transition-colors hover:border-slate-500 hover:bg-slate-900 disabled:cursor-not-allowed disabled:opacity-60"
                >
                  {loadingDemo ? 'Loading demo…' : 'Explore the demo workspace'}
                </button>
              )}
            </>
          ) : (
            <>
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
            </>
          )}
        </div>

        {error && <p className="mt-4 text-sm text-rose-400">{error}</p>}

        <p className="mt-8 text-sm text-slate-500">
          {session ? (
            <button onClick={handleSignOut} className="font-medium text-sky-400 hover:underline">
              Sign out of {session.workspace.is_demo ? 'the demo' : workspaceLabel}
            </button>
          ) : (
            <>
              Already have a workspace?{' '}
              <Link href="/login" className="font-medium text-sky-400 hover:underline">Log in</Link>
            </>
          )}
        </p>
      </div>
    </main>
  );
}
