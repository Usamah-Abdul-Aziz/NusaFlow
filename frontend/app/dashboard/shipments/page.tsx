'use client';

import Link from 'next/link';
import { useEffect, useMemo, useState } from 'react';
import { fetchJson, type ShipmentItem, type ShipmentStatus } from '@/lib/api';
import { ErrorState, LoadingState, PageHeader, ShipmentStatusBadge } from '@/components/ui';

const STATUS_FILTERS: { label: string; value: ShipmentStatus | 'all' }[] = [
  { label: 'All', value: 'all' },
  { label: 'Pending', value: 'pending' },
  { label: 'In transit', value: 'in_transit' },
  { label: 'Delayed', value: 'delayed' },
  { label: 'Delivered', value: 'delivered' },
  { label: 'Cancelled', value: 'cancelled' },
];

export default function ShipmentsPage() {
  const [shipments, setShipments] = useState<ShipmentItem[]>([]);
  const [statusFilter, setStatusFilter] = useState<ShipmentStatus | 'all'>('all');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchJson<ShipmentItem[]>('/api/v1/shipments')
      .then(setShipments)
      .catch((err) => setError(err instanceof Error ? err.message : 'Failed to load shipments'))
      .finally(() => setLoading(false));
  }, []);

  const filtered = useMemo(
    () => (statusFilter === 'all' ? shipments : shipments.filter((s) => s.status === statusFilter)),
    [shipments, statusFilter]
  );

  const counts = useMemo(() => {
    const c: Record<string, number> = { all: shipments.length };
    for (const s of shipments) c[s.status] = (c[s.status] ?? 0) + 1;
    return c;
  }, [shipments]);

  if (loading) return <LoadingState label="Loading shipments" />;
  if (error) return <div className="p-8"><ErrorState message={error} /></div>;

  return (
    <main className="p-6">
      <div className="mx-auto max-w-7xl">
        <PageHeader eyebrow="Phase 3" title="Real-Time Shipment Monitoring" />

        <div className="mb-6 flex flex-wrap gap-2">
          {STATUS_FILTERS.map((f) => (
            <button
              key={f.value}
              onClick={() => setStatusFilter(f.value)}
              className={`rounded-full border px-3 py-1.5 text-sm font-medium transition-colors ${
                statusFilter === f.value ? 'border-sky-300 bg-sky-100 text-sky-900' : 'border-slate-200 bg-white text-slate-600 hover:bg-slate-50'
              }`}
            >
              {f.label} <span className="ml-1 text-xs opacity-60">{counts[f.value] ?? 0}</span>
            </button>
          ))}
        </div>

        <div className="card overflow-hidden">
          <div className="overflow-x-auto">
          <table className="min-w-full divide-y divide-slate-200 text-left text-sm">
            <thead className="bg-slate-50 text-slate-700">
              <tr>
                <th className="px-4 py-3 font-semibold">Shipment</th>
                <th className="px-4 py-3 font-semibold">Product</th>
                <th className="px-4 py-3 font-semibold">Warehouse</th>
                <th className="px-4 py-3 font-semibold">Supplier</th>
                <th className="px-4 py-3 font-semibold">Qty</th>
                <th className="px-4 py-3 font-semibold">ETA</th>
                <th className="px-4 py-3 font-semibold">Delay</th>
                <th className="px-4 py-3 font-semibold">Status</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-200 bg-white">
              {filtered.map((s) => (
                <tr key={s.id} className="cursor-pointer hover:bg-slate-50">
                  <td className="px-4 py-3">
                    <Link href={`/dashboard/shipments/${s.id}`} className="font-medium text-sky-700 hover:underline">
                      {s.shipment_number}
                    </Link>
                  </td>
                  <td className="px-4 py-3 text-slate-600">{s.product}</td>
                  <td className="px-4 py-3">{s.warehouse}</td>
                  <td className="px-4 py-3 text-slate-600">{s.supplier}</td>
                  <td className="px-4 py-3">{s.quantity}</td>
                  <td className="px-4 py-3">{s.eta_date}</td>
                  <td className="px-4 py-3">
                    {s.delay_days > 0 ? <span className="font-medium text-rose-700">{s.delay_days}d</span> : '—'}
                  </td>
                  <td className="px-4 py-3"><ShipmentStatusBadge status={s.status} /></td>
                </tr>
              ))}
              {filtered.length === 0 && (
                <tr><td colSpan={8} className="px-4 py-8 text-center text-slate-500">No shipments match this filter.</td></tr>
              )}
            </tbody>
          </table>
          </div>
        </div>
      </div>
    </main>
  );
}
