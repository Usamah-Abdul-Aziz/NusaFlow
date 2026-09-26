'use client';

import Link from 'next/link';
import { useRouter, usePathname } from 'next/navigation';
import { useEffect, useState } from 'react';
import {
  LayoutDashboard,
  Package,
  Truck,
  Users,
  TrendingUp,
  RefreshCw,
  SlidersHorizontal,
  Bell,
  LogOut,
} from 'lucide-react';
import { fetchJson, type AuthResponse, type MeResponse } from '@/lib/api';
import { clearToken, setToken } from '@/lib/auth';

const LINKS = [
  { href: '/dashboard', label: 'Overview', icon: LayoutDashboard },
  { href: '/dashboard/inventory', label: 'Inventory', icon: Package },
  { href: '/dashboard/shipments', label: 'Shipments', icon: Truck },
  { href: '/dashboard/suppliers', label: 'Suppliers', icon: Users },
  { href: '/dashboard/forecast', label: 'Forecast', icon: TrendingUp },
  { href: '/dashboard/replenishment', label: 'Replenishment', icon: RefreshCw },
  { href: '/dashboard/simulation', label: 'Simulation', icon: SlidersHorizontal },
  { href: '/dashboard/alerts', label: 'Alerts', icon: Bell },
];

export default function Nav() {
  const pathname = usePathname();
  const router = useRouter();
  const [me, setMe] = useState<MeResponse | null>(null);
  const [switching, setSwitching] = useState(false);

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

  // Demo and your own workspace are two separate areas. This makes moving
  // between them an explicit action rather than something that happens
  // implicitly because of a leftover cookie.
  async function handleSwitchToDemo() {
    setSwitching(true);
    try {
      const result = await fetchJson<AuthResponse>('/api/v1/auth/demo', { method: 'POST' });
      setToken(result.access_token);
      window.location.href = '/dashboard';
    } catch {
      setSwitching(false);
    }
  }

  return (
    <nav className="flex w-full shrink-0 flex-col border-b border-slate-200 bg-white md:h-screen md:w-60 md:border-b-0 md:border-r">
      <div className="px-5 py-5">
        <Link href="/dashboard" className="text-lg font-bold tracking-tight text-slate-900">NusaFlow</Link>
        <p className="mt-0.5 truncate text-xs text-slate-500" title={me?.workspace.name}>
          {me?.workspace.name ?? 'Supply Chain Control Tower'}
        </p>
        {me?.workspace.is_demo && (
          <span className="mt-1.5 inline-flex items-center rounded-full bg-amber-100 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-amber-800">
            Demo workspace
          </span>
        )}
        <div className="mt-2 text-xs">
          {me?.workspace.is_demo ? (
            <Link href="/login" className="font-medium text-sky-700 hover:underline">
              ← Log in to my workspace
            </Link>
          ) : (
            <button
              onClick={handleSwitchToDemo}
              disabled={switching}
              className="font-medium text-slate-500 hover:text-slate-800 hover:underline disabled:opacity-60"
            >
              {switching ? 'Switching…' : 'Explore demo workspace'}
            </button>
          )}
        </div>
      </div>
      <ul className="flex gap-1 overflow-x-auto px-3 pb-3 md:flex-col md:overflow-visible md:pb-0">
        {LINKS.map((link) => {
          const active = link.href === '/dashboard' ? pathname === '/dashboard' : pathname?.startsWith(link.href);
          const Icon = link.icon;
          return (
            <li key={link.href} className="shrink-0">
              <Link
                href={link.href}
                className={`relative flex items-center gap-2.5 whitespace-nowrap rounded-lg px-3 py-2 text-sm font-medium transition-colors ${
                  active ? 'bg-sky-50 text-sky-900' : 'text-slate-600 hover:bg-slate-50 hover:text-slate-900'
                }`}
              >
                {active && <span className="absolute left-0 top-1/2 h-5 w-1 -translate-y-1/2 rounded-r-full bg-sky-600 md:-left-3" />}
                <Icon size={17} strokeWidth={2} className={active ? 'text-sky-600' : 'text-slate-400'} />
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
          className="flex items-center gap-1.5 text-xs font-medium text-slate-500 hover:text-slate-800 hover:underline"
        >
          <LogOut size={13} />
          Log out
        </button>
      </div>
    </nav>
  );
}
