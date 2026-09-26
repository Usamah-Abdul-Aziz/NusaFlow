'use client';

import Link from 'next/link';
import { useRouter, useSearchParams } from 'next/navigation';
import { Suspense, useState } from 'react';
import { fetchJson, type AuthResponse } from '@/lib/api';
import { setToken } from '@/lib/auth';
import ActiveSessionNotice from '@/components/ActiveSessionNotice';

function LoginForm() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      const result = await fetchJson<AuthResponse>('/api/v1/auth/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email, password }),
      });
      setToken(result.access_token);
      router.push(searchParams.get('next') || '/dashboard');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Login failed');
      setSubmitting(false);
    }
  }

  return (
    <main className="flex min-h-screen items-center justify-center bg-slate-100 px-6">
      <div className="w-full max-w-sm">
        <Link href="/" className="mb-8 block text-center text-lg font-bold text-slate-900">NusaFlow</Link>
        <div className="card p-6">
          <h1 className="mb-1 text-xl font-bold text-slate-900">Log in</h1>
          <p className="mb-6 text-sm text-slate-500">Access your workspace.</p>

          <ActiveSessionNotice />

          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label className="mb-1 block text-xs font-semibold uppercase tracking-wide text-slate-500">Email</label>
              <input
                type="email"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm"
              />
            </div>
            <div>
              <label className="mb-1 block text-xs font-semibold uppercase tracking-wide text-slate-500">Password</label>
              <input
                type="password"
                required
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm"
              />
            </div>

            {error && <p className="text-sm text-rose-600">{error}</p>}

            <button
              type="submit"
              disabled={submitting}
              className="w-full rounded-lg bg-sky-700 px-4 py-2 text-sm font-semibold text-white transition-colors hover:bg-sky-800 disabled:cursor-not-allowed disabled:bg-slate-300"
            >
              {submitting ? 'Logging in…' : 'Log in'}
            </button>
          </form>

          <p className="mt-6 text-center text-sm text-slate-500">
            No workspace yet?{' '}
            <Link href="/signup" className="font-medium text-sky-700 hover:underline">Create one</Link>
          </p>
        </div>
      </div>
    </main>
  );
}

export default function LoginPage() {
  // useSearchParams() requires a Suspense boundary in the App Router.
  return (
    <Suspense>
      <LoginForm />
    </Suspense>
  );
}
