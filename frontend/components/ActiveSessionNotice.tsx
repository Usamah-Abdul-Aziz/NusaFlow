'use client';

import Link from 'next/link';
import { useEffect, useState } from 'react';
import { LogOut, ArrowRight } from 'lucide-react';
import { getSession, type MeResponse } from '@/lib/api';
import { clearToken } from '@/lib/auth';

// Shown above the login/signup forms when a visitor already holds a valid
// session. This replaces the old middleware redirect that bounced /login
// and /signup to /dashboard whenever ANY token cookie was present — which
// meant anyone who had once clicked "Explore Demo" could never reach the
// signup form again, because their 7-day demo token dragged them back into
// the demo dashboard. Now the forms stay reachable, and the existing
// session is surfaced as information plus a link, not a forced redirect.
export default function ActiveSessionNotice() {
  const [session, setSession] = useState<MeResponse | null>(null);

  useEffect(() => {
    getSession().then(setSession);
  }, []);

  function handleSignOut() {
    clearToken();
    setSession(null);
  }

  if (!session) return null;

  return (
    <div className="mb-6 rounded-lg border border-sky-200 bg-sky-50 p-4 text-left">
      <p className="text-sm text-sky-900">
        You&rsquo;re already signed in as{' '}
        <span className="font-semibold">{session.user.display_name}</span> in the{' '}
        <span className="font-semibold">{session.workspace.name}</span> workspace
        {session.workspace.is_demo && ' (demo)'}.
      </p>
      <div className="mt-3 flex flex-wrap gap-3">
        <Link
          href="/dashboard"
          className="inline-flex items-center gap-1.5 text-sm font-semibold text-sky-700 hover:underline"
        >
          Go to that dashboard <ArrowRight size={13} />
        </Link>
        <button
          onClick={handleSignOut}
          className="inline-flex items-center gap-1.5 text-sm font-medium text-slate-500 hover:text-slate-800 hover:underline"
        >
          <LogOut size={13} /> Sign out
        </button>
      </div>
      <p className="mt-3 text-xs text-sky-700/80">
        Or continue below to use a different account.
      </p>
    </div>
  );
}
