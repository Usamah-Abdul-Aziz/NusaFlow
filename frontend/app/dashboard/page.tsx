'use client';

import Link from 'next/link';
import { useEffect, useState } from 'react';
import { Boxes, PackageCheck, RotateCcw, ShieldAlert, TimerReset, Truck } from 'lucide-react';
import { fetchJson, type Alert, type InventoryAnalysisResponse, type InventoryItem, type Overview, type ReplenishmentRecommendation, type ShipmentItem } from '@/lib/api';
import { ErrorState, LoadingState, MetricCard, PageHeader, SeverityBadge, ShipmentStatusBadge } from '@/components/ui';

export default function HomePage() {
  const [overview, setOverview] = useState<Overview | null>(null);
  const [inventory, setInventory] = useState<InventoryItem[]>([]);
  const [shipments, setShipments] = useState<ShipmentItem[]>([]);
  const [alerts, setAlerts] = useState<Alert[]>([]);
  const [needsReorderCount, setNeedsReorderCount] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function loadData() {
      try {
        setLoading(true);
        const [overviewData, inventoryData, shipmentData, alertsData, replenishmentData] = await Promise.all([
          fetchJson<Overview>('/api/v1/overview'),
          fetchJson<InventoryAnalysisResponse>('/api/v1/inventory/analysis?page=1&page_size=8'),
          fetchJson<ShipmentItem[]>('/api/v1/shipments'),
          fetchJson<Alert[]>('/api/v1/alerts?status=OPEN'),
          fetchJson<ReplenishmentRecommendation[]>('/api/v1/replenishment?needs_reorder=true'),
        ]);
        setOverview(overviewData);
        setInventory(inventoryData.items);
        setShipments(shipmentData);
        setAlerts(alertsData);
        setNeedsReorderCount(replenishmentData.length);
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Unknown dashboard error');
      } finally {
        setLoading(false);
      }
    }
    loadData();
  }, []);

  if (loading) return <LoadingState label="Loading NusaFlow dashboard" />;
  if (error) return <div className="p-8"><ErrorState message={error} /></div>;

  const severityOrder: Record<string, number> = { CRITICAL: 0, WARNING: 1, INFO: 2 };
  const topAlerts = [...alerts].sort((a, b) => severityOrder[a.severity] - severityOrder[b.severity]).slice(0, 5);
  const watchlist = shipments
    .filter((s) => s.status === 'delayed' || s.status === 'in_transit')
    .sort((a, b) => b.delay_days - a.delay_days)
    .slice(0, 5);

  return (
    <main className="p-6">
      <div className="mx-auto max-w-7xl">
        <PageHeader
          eyebrow="Control Tower"
          title="NusaFlow Overview"
          action={
            <div className="rounded-full bg-sky-100 px-4 py-2 text-sm font-medium text-sky-900">
              Updated {overview?.generated_on}
            </div>
          }
        />

        <section className="mb-8 grid gap-4 md:grid-cols-2 xl:grid-cols-6">
          <MetricCard title="Inventory Health" value={`${overview?.inventory_health ?? 0}%`} tone="sky" icon={Boxes} />
          <MetricCard title="Active Shipments" value={String(overview?.active_shipments ?? 0)} tone="amber" icon={Truck} />
          <MetricCard title="Stockout Risks" value={String(overview?.stockout_risk ?? 0)} tone="rose" icon={ShieldAlert} />
          <MetricCard title="Delayed Shipments" value={String(overview?.delayed_shipments ?? 0)} tone="orange" icon={TimerReset} />
          <MetricCard title="Supplier Quality" value={`${Math.round((overview?.supplier_quality ?? 0) * 100)}%`} tone="emerald" icon={PackageCheck} />
          <Link href="/dashboard/replenishment">
            <MetricCard title="Needs Reorder" value={String(needsReorderCount)} tone={needsReorderCount > 0 ? 'amber' : 'emerald'} icon={RotateCcw} />
          </Link>
        </section>

        <section className="grid gap-6 xl:grid-cols-[1.1fr_0.9fr]">
          <div className="card min-w-0 p-6">
            <div className="mb-4 flex items-center justify-between">
              <h2 className="text-xl font-semibold text-slate-800">Inventory Snapshot</h2>
              <Link href="/dashboard/inventory" className="text-sm font-medium text-sky-700 hover:underline">View all →</Link>
            </div>
            <div className="overflow-hidden rounded-xl border border-slate-200">
              <div className="overflow-x-auto">
                <table className="min-w-full divide-y divide-slate-200 text-left text-sm">
                <thead className="bg-slate-50 text-slate-700">
                  <tr>
                    <th className="px-4 py-3 font-semibold">SKU</th>
                    <th className="px-4 py-3 font-semibold">Warehouse</th>
                    <th className="px-4 py-3 font-semibold">On hand</th>
                    <th className="px-4 py-3 font-semibold">Days</th>
                    <th className="px-4 py-3 font-semibold">Risk</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-200 bg-white">
                  {inventory.map((item) => (
                    <tr key={item.id} className={item.stockout_risk ? 'bg-rose-50' : ''}>
                      <td className="px-4 py-3 font-medium text-slate-800">{item.sku}</td>
                      <td className="px-4 py-3">{item.warehouse}</td>
                      <td className="px-4 py-3">{item.on_hand}</td>
                      <td className="px-4 py-3">{item.days_of_inventory ?? '—'}</td>
                      <td className="px-4 py-3">
                        {item.stockout_risk ? (
                          <span className="inline-flex items-center rounded-full bg-rose-100 px-2 py-1 text-xs font-semibold text-rose-800">At risk</span>
                        ) : (
                          <span className="inline-flex items-center rounded-full bg-slate-100 px-2 py-1 text-xs font-medium text-slate-700">OK</span>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
              </div>
            </div>

            <div className="mb-4 mt-8 flex items-center justify-between">
              <h2 className="text-xl font-semibold text-slate-800">Shipment Watchlist</h2>
              <Link href="/dashboard/shipments" className="text-sm font-medium text-sky-700 hover:underline">View all →</Link>
            </div>
            <div className="space-y-3">
              {watchlist.map((shipment) => (
                <Link
                  key={shipment.id}
                  href={`/dashboard/shipments/${shipment.id}`}
                  className="block rounded-xl border border-slate-200 p-4 transition-colors hover:border-sky-300 hover:bg-sky-50"
                >
                  <div className="flex items-center justify-between">
                    <div>
                      <p className="font-semibold text-slate-800">{shipment.shipment_number}</p>
                      <p className="text-sm text-slate-500">{shipment.product} · {shipment.warehouse}</p>
                    </div>
                    <ShipmentStatusBadge status={shipment.status} />
                  </div>
                  {shipment.delay_days > 0 && (
                    <p className="mt-2 text-sm font-medium text-rose-700">{shipment.delay_days} day(s) past ETA</p>
                  )}
                </Link>
              ))}
              {watchlist.length === 0 && (
                <div className="rounded-md border border-slate-200 bg-slate-50 p-3 text-sm text-slate-700">
                  Nothing in transit or delayed right now.
                </div>
              )}
            </div>
          </div>

          <div className="card min-w-0 p-6">
            <div className="mb-4 flex items-center justify-between">
              <h2 className="text-xl font-semibold text-slate-800">Open Alerts</h2>
              <Link href="/dashboard/alerts" className="text-sm font-medium text-sky-700 hover:underline">View all →</Link>
            </div>
            <div className="space-y-3">
              {topAlerts.map((alert) => (
                <div key={alert.id} className="rounded-xl border border-slate-200 p-4">
                  <div className="flex items-start justify-between gap-3">
                    <p className="font-semibold text-slate-800">{alert.title}</p>
                    <SeverityBadge severity={alert.severity} />
                  </div>
                  <p className="mt-1 text-sm text-slate-600">{alert.description}</p>
                </div>
              ))}
              {topAlerts.length === 0 && (
                <div className="rounded-md border border-slate-200 bg-slate-50 p-3 text-sm text-slate-700">
                  No open alerts. Everything's within normal thresholds.
                </div>
              )}
            </div>
          </div>
        </section>
      </div>
    </main>
  );
}
