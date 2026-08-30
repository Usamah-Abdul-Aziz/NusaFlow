'use client';

import { useEffect, useState } from 'react';
import { fetchJson, type Supplier } from '@/lib/api';
import { ErrorState, LoadingState, PageHeader } from '@/components/ui';

export default function SuppliersPage() {
  const [suppliers, setSuppliers] = useState<Supplier[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchJson<Supplier[]>('/api/v1/suppliers')
      .then(setSuppliers)
      .catch((err) => setError(err instanceof Error ? err.message : 'Failed to load suppliers'))
      .finally(() => setLoading(false));
  }, []);

  if (loading) return <LoadingState label="Loading suppliers" />;
  if (error) return <div className="p-8"><ErrorState message={error} /></div>;

  return (
    <main className="p-6">
      <div className="mx-auto max-w-5xl">
        <PageHeader eyebrow="Suppliers" title="Supplier Performance" />

        <div className="card overflow-hidden">
          <div className="overflow-x-auto">
          <table className="min-w-full divide-y divide-slate-200 text-left text-sm">
            <thead className="bg-slate-50 text-slate-700">
              <tr>
                <th className="px-4 py-3 font-semibold">Supplier</th>
                <th className="px-4 py-3 font-semibold">Lead time</th>
                <th className="px-4 py-3 font-semibold">Historical delay rate</th>
                <th className="px-4 py-3 font-semibold">Reliability score</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-200 bg-white">
              {suppliers.map((s) => (
                <tr key={s.id}>
                  <td className="px-4 py-3 font-medium text-slate-800">{s.name}</td>
                  <td className="px-4 py-3">{s.lead_time_days} day(s)</td>
                  <td className="px-4 py-3">
                    <span className={s.delay_rate >= 0.3 ? 'font-semibold text-rose-700' : 'text-slate-700'}>
                      {(s.delay_rate * 100).toFixed(0)}%
                    </span>
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex items-center gap-2">
                      <div className="h-2 w-24 overflow-hidden rounded-full bg-slate-100">
                        <div className="h-full bg-emerald-500" style={{ width: `${s.reliability_score * 100}%` }} />
                      </div>
                      <span className="text-slate-600">{(s.reliability_score * 100).toFixed(0)}%</span>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          </div>
        </div>
        <p className="mt-3 text-xs text-slate-400">
          Note: the underlying <code>SUPPLIER_DELAY</code> alert (see Alerts) is based on actual
          delivered-shipment outcomes, not this seeded delay_rate — the two can drift apart, which
          is expected.
        </p>
      </div>
    </main>
  );
}
