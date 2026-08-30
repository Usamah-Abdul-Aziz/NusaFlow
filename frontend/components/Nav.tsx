'use client';

import Link from 'next/link';
import { useRouter, usePathname } from 'next/navigation';
import { useEffect, useState } from 'react';
import { fetchJson, type MeResponse } from '@/lib/api';
import { clearToken } from '@/lib/auth';

const LINKS = [
  { href: '/dashboard', label: 'Overview' },
  { href: '/dashboard/inventory', label: 'Inventory' },
  { href: '/dashboard/shipments', label: 'Shipments' },
  { href: '/dashboard/suppliers', label: 'Suppliers' },
  { href: '/dashboard/forecast', label: 'Forecast' },
  { href: '/dashboard/replenishment', label: 'Replenishment' },
  { href: '/dashboard/simulation', label: 'Simulation' },
  { href: '/dashboard/alerts', label: 'Alerts' },
];

export default function Nav() {
  const pathname = usePathname();
  const router = useRouter();
  const [me, setMe] = useState<MeResponse | null>(null);

  useEffect(() => {
    fetchJson<MeResponse>('/api/v1/auth/me')
      .then(setMe)
      .catch(() => {
        /* fetchJson already redirects to /login on 401; nothing else to do here */
      });
  }, []);

  function handleLogout() {
    clearToken();
    router.push('/');
  }

  return (
    <nav className="flex w-full shrink-0 flex-col border-b border-slate-200 bg-white md:h-screen md:w-56 md:border-b-0 md:border-r">
      <div className="px-5 py-5">
        <Link href="/dashboard" className="text-lg font-bold text-slate-900">NusaFlow</Link>
        <p className="truncate text-xs text-slate-500" title={me?.workspace.name}>
          {me?.workspace.name ?? 'Supply Chain Control Tower'}
        </p>
        {me?.workspace.is_demo && (
          <span className="mt-1 inline-flex items-center rounded-full bg-amber-100 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-amber-800">
            Demo workspace
          </span>
        )}
      </div>
      <ul className="flex gap-1 overflow-x-auto px-3 pb-3 md:flex-col md:overflow-visible md:pb-0">
        {LINKS.map((link) => {
          const active = link.href === '/dashboard' ? pathname === '/dashboard' : pathname?.startsWith(link.href);
          return (
            <li key={link.href} className="shrink-0">
              <Link
                href={link.href}
                className={`block whitespace-nowrap rounded-lg px-3 py-2 text-sm font-medium transition-colors ${
                  active ? 'bg-sky-100 text-sky-900' : 'text-slate-600 hover:bg-slate-100'
                }`}
              >
                {link.label}
              </Link>
            </li>
          );
        })}
      </ul>

      <div className="mt-auto border-t border-slate-200 px-5 py-4">
        {me && (
          <p className="mb-2 truncate text-sm font-medium text-slate-700" title={me.user.email}>
            {me.user.display_name}
          </p>
        )}
        <button
          onClick={handleLogout}
          className="text-xs font-medium text-slate-500 hover:text-slate-800 hover:underline"
        >
          Log out
        </button>
      </div>
    </nav>
  );
}
