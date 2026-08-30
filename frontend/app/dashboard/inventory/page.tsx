'use client';

import { useEffect, useState } from 'react';
import { fetchJson, type InventoryAnalysisResponse, type InventoryItem } from '@/lib/api';
import { ErrorState, LoadingState, PageHeader } from '@/components/ui';

type RawInventoryRow = { sku: string; warehouse: string };

export default function InventoryPage() {
  const [items, setItems] = useState<InventoryItem[]>([]);
  const [totalPages, setTotalPages] = useState(1);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);
  const [skuFilter, setSkuFilter] = useState('');
  const [warehouseFilter, setWarehouseFilter] = useState('');
  const [skuOptions, setSkuOptions] = useState<string[]>([]);
  const [warehouseOptions, setWarehouseOptions] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Filter dropdown options — /inventory/analysis matches sku/warehouse
  // exactly (not "contains"), so a free-text box would silently return
  // nothing for anything not typed exactly right. A dropdown of real
  // values is both more accurate and easier to use.
  useEffect(() => {
    fetchJson<RawInventoryRow[]>('/api/v1/inventory')
      .then((rows) => {
        setSkuOptions(Array.from(new Set(rows.map((r) => r.sku))).sort());
        setWarehouseOptions(Array.from(new Set(rows.map((r) => r.warehouse))).sort());
      })
      .catch(() => {
        /* filters are a nice-to-have; a failure here shouldn't block the table itself */
      });
  }, []);

  useEffect(() => {
    async function load() {
      try {
        setLoading(true);
        const params = new URLSearchParams({ page: String(page), page_size: String(pageSize) });
        if (skuFilter) params.set('sku', skuFilter);
        if (warehouseFilter) params.set('warehouse', warehouseFilter);
        const data = await fetchJson<InventoryAnalysisResponse>(`/api/v1/inventory/analysis?${params}`);
        setItems(data.items);
        setTotalPages(data.pagination.total_pages);
        setTotal(data.pagination.total);
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to load inventory');
      } finally {
        setLoading(false);
      }
    }
    load();
  }, [page, pageSize, skuFilter, warehouseFilter]);

  return (
    <main className="p-6">
      <div className="mx-auto max-w-7xl">
        <PageHeader eyebrow="Phase 2" title="Inventory Intelligence" />

        <div className="card mb-6 flex flex-wrap items-end gap-4 p-4">
          <div>
            <label className="mb-1 block text-xs font-semibold uppercase tracking-wide text-slate-500">SKU</label>
            <select
              value={skuFilter}
              onChange={(e) => { setSkuFilter(e.target.value); setPage(1); }}
              className="rounded-md border border-slate-300 px-3 py-1.5 text-sm"
            >
              <option value="">All SKUs</option>
              {skuOptions.map((sku) => <option key={sku} value={sku}>{sku}</option>)}
            </select>
          </div>
          <div>
            <label className="mb-1 block text-xs font-semibold uppercase tracking-wide text-slate-500">Warehouse</label>
            <select
              value={warehouseFilter}
              onChange={(e) => { setWarehouseFilter(e.target.value); setPage(1); }}
              className="rounded-md border border-slate-300 px-3 py-1.5 text-sm"
            >
              <option value="">All warehouses</option>
              {warehouseOptions.map((wh) => <option key={wh} value={wh}>{wh}</option>)}
            </select>
          </div>
          <div className="ml-auto text-sm text-slate-500">{total} product-warehouse pairs</div>
        </div>

        {error && <ErrorState message={error} />}
        {loading ? (
          <LoadingState label="Loading inventory" />
        ) : (
          <div className="card overflow-hidden">
            <div className="overflow-x-auto">
              <table className="min-w-full divide-y divide-slate-200 text-left text-sm">
                <thead className="bg-slate-50 text-slate-700">
                  <tr>
                    <th className="px-4 py-3 font-semibold">SKU</th>
                    <th className="px-4 py-3 font-semibold">Product</th>
                    <th className="px-4 py-3 font-semibold">Warehouse</th>
                    <th className="px-4 py-3 font-semibold">On hand</th>
                    <th className="px-4 py-3 font-semibold">Safety stock</th>
                    <th className="px-4 py-3 font-semibold">Incoming</th>
                    <th className="px-4 py-3 font-semibold">Avg daily demand</th>
                    <th className="px-4 py-3 font-semibold">Days of inventory</th>
                    <th className="px-4 py-3 font-semibold">Risk</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-200 bg-white">
                  {items.map((item) => (
                    <tr key={item.id} className={item.stockout_risk ? 'bg-rose-50' : ''}>
                      <td className="px-4 py-3 font-medium text-slate-800">{item.sku}</td>
                      <td className="px-4 py-3 text-slate-600">{item.product}</td>
                      <td className="px-4 py-3">{item.warehouse}</td>
                      <td className="px-4 py-3">{item.on_hand}</td>
                      <td className="px-4 py-3">{item.safety_stock}</td>
                      <td className="px-4 py-3">{item.incoming_qty}</td>
                      <td className="px-4 py-3">{item.avg_daily_demand?.toFixed(1) ?? '—'}</td>
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

            <div className="flex items-center justify-between border-t border-slate-200 p-4">
              <div className="text-sm text-slate-600">Page {page} of {totalPages}</div>
              <div className="flex items-center gap-2">
                <select
                  value={pageSize}
                  onChange={(e) => { setPageSize(Number(e.target.value)); setPage(1); }}
                  className="rounded-md border px-2 py-1 text-sm"
                >
                  <option value={10}>10</option>
                  <option value={20}>20</option>
                  <option value={50}>50</option>
                </select>
                <button onClick={() => setPage((p) => Math.max(1, p - 1))} disabled={page <= 1} className="rounded-md border px-3 py-1 text-sm disabled:opacity-40">Prev</button>
                <button onClick={() => setPage((p) => Math.min(totalPages, p + 1))} disabled={page >= totalPages} className="rounded-md border px-3 py-1 text-sm disabled:opacity-40">Next</button>
              </div>
            </div>
          </div>
        )}
      </div>
    </main>
  );
}
