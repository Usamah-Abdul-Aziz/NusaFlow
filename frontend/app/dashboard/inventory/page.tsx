'use client';

import Link from 'next/link';
import { useEffect, useState } from 'react';
import {
  ApiError,
  fetchJson,
  type ForecastSummary,
  type InventoryAnalysisResponse,
  type InventoryItem,
  type ProductRecord,
  type QuickEstimateResponse,
  type ReplenishmentRecommendation,
  type WarehouseRecord,
} from '@/lib/api';
import { EstimatedDataBadge, ErrorState, LoadingState, PageHeader } from '@/components/ui';

type RawInventoryRow = { sku: string; warehouse: string };
type FormKind = 'warehouse' | 'product' | 'stock' | 'estimate' | null;

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
  const [deletingId, setDeletingId] = useState<number | null>(null);

  const [activeForm, setActiveForm] = useState<FormKind>(null);
  const [warehouses, setWarehouses] = useState<WarehouseRecord[]>([]);
  const [products, setProducts] = useState<ProductRecord[]>([]);
  // Every stocked pair in the workspace — the estimate form picks from these
  // (you can only estimate demand for a pair you actually hold stock of).
  const [pairs, setPairs] = useState<RawInventoryRow[]>([]);

  function loadFilterOptions() {
    fetchJson<RawInventoryRow[]>('/api/v1/inventory')
      .then((rows) => {
        setPairs(rows);
        setSkuOptions(Array.from(new Set(rows.map((r) => r.sku))).sort());
        setWarehouseOptions(Array.from(new Set(rows.map((r) => r.warehouse))).sort());
      })
      .catch(() => { /* filters are a nice-to-have; a failure here shouldn't block the table itself */ });
  }
  function loadMasterData() {
    fetchJson<WarehouseRecord[]>('/api/v1/warehouses').then(setWarehouses).catch(() => {});
    fetchJson<ProductRecord[]>('/api/v1/products').then(setProducts).catch(() => {});
  }
  useEffect(() => { loadFilterOptions(); loadMasterData(); }, []);

  function loadTable() {
    setLoading(true);
    const params = new URLSearchParams({ page: String(page), page_size: String(pageSize) });
    if (skuFilter) params.set('sku', skuFilter);
    if (warehouseFilter) params.set('warehouse', warehouseFilter);
    fetchJson<InventoryAnalysisResponse>(`/api/v1/inventory/analysis?${params}`)
      .then((data) => { setItems(data.items); setTotalPages(data.pagination.total_pages); setTotal(data.pagination.total); })
      .catch((err) => setError(err instanceof Error ? err.message : 'Failed to load inventory'))
      .finally(() => setLoading(false));
  }
  useEffect(loadTable, [page, pageSize, skuFilter, warehouseFilter]);

  function refreshEverything() {
    loadTable();
    loadFilterOptions();
    loadMasterData();
  }

  async function handleDeleteInventory(item: InventoryItem) {
    if (!window.confirm(`Remove the stock record for ${item.sku} at ${item.warehouse}?`)) return;
    setDeletingId(item.id);
    try {
      await fetchJson(`/api/v1/inventory/${item.id}`, { method: 'DELETE' });
      refreshEverything();
    } catch (err) {
      window.alert(err instanceof ApiError ? err.message : 'Failed to remove stock record');
    } finally {
      setDeletingId(null);
    }
  }

  return (
    <main className="p-6">
      <div className="mx-auto max-w-7xl">
        <PageHeader
          eyebrow="Inventory"
          title="Inventory Intelligence"
          action={
            <div className="flex flex-wrap gap-2">
              <FormToggleButton label="+ Add warehouse" active={activeForm === 'warehouse'} onClick={() => setActiveForm(activeForm === 'warehouse' ? null : 'warehouse')} />
              <FormToggleButton label="+ Add product" active={activeForm === 'product'} onClick={() => setActiveForm(activeForm === 'product' ? null : 'product')} />
              <FormToggleButton label="+ Add stock" active={activeForm === 'stock'} onClick={() => setActiveForm(activeForm === 'stock' ? null : 'stock')} />
              <FormToggleButton label="+ Estimate demand" active={activeForm === 'estimate'} onClick={() => setActiveForm(activeForm === 'estimate' ? null : 'estimate')} />
            </div>
          }
        />

        {activeForm === 'warehouse' && <AddWarehouseForm onDone={() => { setActiveForm(null); refreshEverything(); }} />}
        {activeForm === 'product' && <AddProductForm onDone={() => { setActiveForm(null); refreshEverything(); }} />}
        {activeForm === 'stock' && (
          <AddStockForm warehouses={warehouses} products={products} onDone={() => { setActiveForm(null); refreshEverything(); }} />
        )}
        {activeForm === 'estimate' && (
          <EstimateDemandForm
            pairs={pairs}
            onSaved={refreshEverything}
            onDone={() => { setActiveForm(null); refreshEverything(); }}
          />
        )}

        <div className="card mb-6 flex flex-wrap items-end gap-4 p-4">
          <div>
            <label className="mb-1 block text-xs font-semibold uppercase tracking-wide text-slate-500">SKU</label>
            <select value={skuFilter} onChange={(e) => { setSkuFilter(e.target.value); setPage(1); }} className="rounded-md border border-slate-300 px-3 py-1.5 text-sm">
              <option value="">All SKUs</option>
              {skuOptions.map((sku) => <option key={sku} value={sku}>{sku}</option>)}
            </select>
          </div>
          <div>
            <label className="mb-1 block text-xs font-semibold uppercase tracking-wide text-slate-500">Warehouse</label>
            <select value={warehouseFilter} onChange={(e) => { setWarehouseFilter(e.target.value); setPage(1); }} className="rounded-md border border-slate-300 px-3 py-1.5 text-sm">
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
                    <th className="px-4 py-3 font-semibold"></th>
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
                      <td className="px-4 py-3 text-right">
                        <button
                          onClick={() => handleDeleteInventory(item)}
                          disabled={deletingId === item.id}
                          className="text-xs font-medium text-rose-600 hover:underline disabled:opacity-50"
                        >
                          {deletingId === item.id ? 'Removing…' : 'Remove'}
                        </button>
                      </td>
                    </tr>
                  ))}
                  {items.length === 0 && (
                    <tr><td colSpan={10} className="px-4 py-8 text-center text-slate-500">No stock records yet — use "Add stock" above once you have a warehouse and a product.</td></tr>
                  )}
                </tbody>
              </table>
            </div>

            <div className="flex items-center justify-between border-t border-slate-200 p-4">
              <div className="text-sm text-slate-600">Page {page} of {totalPages}</div>
              <div className="flex items-center gap-2">
                <select value={pageSize} onChange={(e) => { setPageSize(Number(e.target.value)); setPage(1); }} className="rounded-md border px-2 py-1 text-sm">
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

function FormToggleButton({ label, active, onClick }: { label: string; active: boolean; onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      className={`rounded-lg px-4 py-2 text-sm font-semibold transition-colors ${
        active ? 'bg-slate-700 text-white' : 'bg-sky-700 text-white hover:bg-sky-800'
      }`}
    >
      {active ? 'Cancel' : label}
    </button>
  );
}

function AddWarehouseForm({ onDone }: { onDone: () => void }) {
  const [code, setCode] = useState('');
  const [name, setName] = useState('');
  const [city, setCity] = useState('');
  const [region, setRegion] = useState('');
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setSaving(true);
    setError(null);
    try {
      await fetchJson('/api/v1/warehouses', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ code, name, city, region }),
      });
      onDone();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to add warehouse');
      setSaving(false);
    }
  }

  return (
    <form onSubmit={handleSubmit} className="card mb-6 grid gap-4 p-5 sm:grid-cols-4">
      <Field label="Code" value={code} onChange={setCode} placeholder="e.g. WH-SMR" />
      <Field label="Name" value={name} onChange={setName} placeholder="e.g. Semarang DC" />
      <Field label="City" value={city} onChange={setCity} />
      <Field label="Region" value={region} onChange={setRegion} />
      {error && <p className="text-sm text-rose-600 sm:col-span-4">{error}</p>}
      <div className="sm:col-span-4">
        <button type="submit" disabled={saving} className="rounded-lg bg-sky-700 px-4 py-2 text-sm font-semibold text-white hover:bg-sky-800 disabled:opacity-50">
          {saving ? 'Adding…' : 'Add warehouse'}
        </button>
      </div>
    </form>
  );
}

function AddProductForm({ onDone }: { onDone: () => void }) {
  const [sku, setSku] = useState('');
  const [name, setName] = useState('');
  const [category, setCategory] = useState('');
  const [unitCost, setUnitCost] = useState('10');
  const [leadTime, setLeadTime] = useState('5');
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setSaving(true);
    setError(null);
    try {
      await fetchJson('/api/v1/products', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ sku, name, category, unit_cost: Number(unitCost), lead_time_days: Number(leadTime) }),
      });
      onDone();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to add product');
      setSaving(false);
    }
  }

  return (
    <form onSubmit={handleSubmit} className="card mb-6 grid gap-4 p-5 sm:grid-cols-5">
      <Field label="SKU" value={sku} onChange={setSku} placeholder="e.g. SKU-201" />
      <Field label="Name" value={name} onChange={setName} className="sm:col-span-2" />
      <Field label="Category" value={category} onChange={setCategory} />
      <Field label="Unit cost" value={unitCost} onChange={setUnitCost} type="number" step="0.01" min={0} />
      <Field label="Lead time (days)" value={leadTime} onChange={setLeadTime} type="number" min={1} max={180} />
      {error && <p className="text-sm text-rose-600 sm:col-span-5">{error}</p>}
      <div className="sm:col-span-5">
        <button type="submit" disabled={saving} className="rounded-lg bg-sky-700 px-4 py-2 text-sm font-semibold text-white hover:bg-sky-800 disabled:opacity-50">
          {saving ? 'Adding…' : 'Add product'}
        </button>
      </div>
    </form>
  );
}

function AddStockForm({ warehouses, products, onDone }: { warehouses: WarehouseRecord[]; products: ProductRecord[]; onDone: () => void }) {
  const [productId, setProductId] = useState('');
  const [warehouseId, setWarehouseId] = useState('');
  const [onHand, setOnHand] = useState('0');
  const [safetyStock, setSafetyStock] = useState('20');
  const [reorderPoint, setReorderPoint] = useState('30');
  const [incoming, setIncoming] = useState('0');
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!productId || !warehouseId) {
      setError('Choose a product and a warehouse.');
      return;
    }
    setSaving(true);
    setError(null);
    try {
      await fetchJson('/api/v1/inventory', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          product_id: Number(productId),
          warehouse_id: Number(warehouseId),
          on_hand: Number(onHand),
          safety_stock: Number(safetyStock),
          reorder_point: Number(reorderPoint),
          incoming_qty: Number(incoming),
        }),
      });
      onDone();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to add stock record');
      setSaving(false);
    }
  }

  if (warehouses.length === 0 || products.length === 0) {
    return (
      <div className="card mb-6 p-5 text-sm text-slate-600">
        Add at least one warehouse and one product first — stock records link an existing product to an existing warehouse.
      </div>
    );
  }

  return (
    <form onSubmit={handleSubmit} className="card mb-6 grid gap-4 p-5 sm:grid-cols-6">
      <div className="sm:col-span-2">
        <label className="mb-1 block text-xs font-semibold uppercase tracking-wide text-slate-500">Product</label>
        <select required value={productId} onChange={(e) => setProductId(e.target.value)} className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm">
          <option value="">Choose…</option>
          {products.map((p) => <option key={p.id} value={p.id}>{p.sku} — {p.name}</option>)}
        </select>
      </div>
      <div className="sm:col-span-2">
        <label className="mb-1 block text-xs font-semibold uppercase tracking-wide text-slate-500">Warehouse</label>
        <select required value={warehouseId} onChange={(e) => setWarehouseId(e.target.value)} className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm">
          <option value="">Choose…</option>
          {warehouses.map((w) => <option key={w.id} value={w.id}>{w.code} — {w.name}</option>)}
        </select>
      </div>
      <Field label="On hand" value={onHand} onChange={setOnHand} type="number" min={0} />
      <Field label="Incoming" value={incoming} onChange={setIncoming} type="number" min={0} />
      <Field label="Safety stock" value={safetyStock} onChange={setSafetyStock} type="number" min={0} />
      <Field label="Reorder point" value={reorderPoint} onChange={setReorderPoint} type="number" min={0} />
      {error && <p className="text-sm text-rose-600 sm:col-span-6">{error}</p>}
      <div className="sm:col-span-6">
        <button type="submit" disabled={saving} className="rounded-lg bg-sky-700 px-4 py-2 text-sm font-semibold text-white hover:bg-sky-800 disabled:opacity-50">
          {saving ? 'Adding…' : 'Add stock record'}
        </button>
      </div>
    </form>
  );
}

function EstimateDemandForm({
  pairs,
  onSaved,
  onDone,
}: {
  pairs: RawInventoryRow[];
  onSaved: () => void;
  onDone: () => void;
}) {
  const [pairKey, setPairKey] = useState('');
  const [avgPerDay, setAvgPerDay] = useState('20');
  const [daysBack, setDaysBack] = useState('90');
  const [saving, setSaving] = useState(false);
  const [progress, setProgress] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<QuickEstimateResponse | null>(null);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    const pair = pairs.find((p) => `${p.sku}|${p.warehouse}` === pairKey);
    if (!pair) {
      setError('Choose a product-warehouse pair.');
      return;
    }
    setSaving(true);
    setError(null);
    setResult(null);
    const qs = `sku=${encodeURIComponent(pair.sku)}&warehouse=${encodeURIComponent(pair.warehouse)}`;
    try {
      // Step 1: expand the rough number into a realistic daily series.
      setProgress('Generating estimated demand history…');
      const estimate = await fetchJson<QuickEstimateResponse>('/api/v1/demand/quick-estimate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          sku: pair.sku,
          warehouse: pair.warehouse,
          avg_units_per_day: Number(avgPerDay),
          days_back: Number(daysBack),
        }),
      });

      // Steps 2 and 3: the estimate alone doesn't make Forecast and
      // Replenishment usable — they only run once history exists, and a
      // user who doesn't know about those two endpoints would land back on
      // "not enough demand history yet". Run them here, in dependency
      // order, so "generate" on this form means "open the feature".
      setProgress('Forecasting from the new history…');
      await fetchJson<ForecastSummary>(`/api/v1/forecasts/generate?${qs}`, { method: 'POST' });

      setProgress('Calculating replenishment…');
      await fetchJson<ReplenishmentRecommendation>(`/api/v1/replenishment/generate?${qs}`, { method: 'POST' });

      setResult(estimate);
      onSaved();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to generate estimate');
    } finally {
      setSaving(false);
      setProgress('');
    }
  }

  if (pairs.length === 0) {
    return (
      <div className="card mb-6 p-5 text-sm text-slate-600">
        Add stock for at least one product-warehouse pair first — demand is estimated for stock you actually hold.
      </div>
    );
  }

  if (result) {
    // The banner the UI shows on Forecast/Replenishment lives there; here we
    // just confirm exactly what got written and where to see the results.
    return (
      <div className="card mb-6 p-5">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <div className="flex flex-wrap items-center gap-2">
              <h3 className="text-base font-semibold text-slate-800">Estimate generated</h3>
              <EstimatedDataBadge />
            </div>
            <p className="mt-2 text-sm text-slate-600">
              {result.days_generated} day(s) of estimated demand for {result.product} · {result.warehouse}
              {' '}({result.start_date} → {result.end_date}).
              {result.days_skipped_existing > 0 && ` ${result.days_skipped_existing} day(s) already had data and were left untouched.`}
            </p>
            <p className="mt-1 text-xs text-slate-500">
              Forecasts and replenishment for this pair were (re)generated and are flagged as estimated.
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
            <Link href="/dashboard/forecast" className="rounded-lg bg-sky-700 px-4 py-2 text-sm font-semibold text-white hover:bg-sky-800">
              Open Forecast
            </Link>
            <Link href="/dashboard/replenishment" className="rounded-lg border border-slate-300 bg-white px-4 py-2 text-sm font-semibold text-slate-700 hover:bg-slate-50">
              Open Replenishment
            </Link>
            <button onClick={onDone} className="rounded-lg px-4 py-2 text-sm font-medium text-slate-500 hover:text-slate-800">
              Done
            </button>
          </div>
        </div>
      </div>
    );
  }

  return (
    <form onSubmit={handleSubmit} className="card mb-6 grid gap-4 p-5 sm:grid-cols-4">
      <div className="sm:col-span-2">
        <label className="mb-1 block text-xs font-semibold uppercase tracking-wide text-slate-500">Product · warehouse</label>
        <select required value={pairKey} onChange={(e) => setPairKey(e.target.value)} className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm">
          <option value="">Choose…</option>
          {pairs.map((p) => (
            <option key={`${p.sku}|${p.warehouse}`} value={`${p.sku}|${p.warehouse}`}>
              {p.sku} @ {p.warehouse}
            </option>
          ))}
        </select>
      </div>
      <Field label="Units per day (approx.)" value={avgPerDay} onChange={setAvgPerDay} type="number" min={1} step="0.1" />
      <Field label="Days of history" value={daysBack} onChange={setDaysBack} type="number" min={30} max={400} />
      {error && <p className="text-sm text-rose-600 sm:col-span-4">{error}</p>}
      {progress && <p className="text-sm text-slate-500 sm:col-span-4">{progress}</p>}
      <div className="sm:col-span-4">
        <button type="submit" disabled={saving} className="rounded-lg bg-sky-700 px-4 py-2 text-sm font-semibold text-white hover:bg-sky-800 disabled:opacity-50">
          {saving ? 'Generating…' : 'Generate estimasi & buka Forecast'}
        </button>
      </div>
    </form>
  );
}

function Field({
  label, value, onChange, type = 'text', className, ...rest
}: { label: string; value: string; onChange: (v: string) => void; type?: string; className?: string } & Record<string, unknown>) {
  return (
    <div className={className}>
      <label className="mb-1 block text-xs font-semibold uppercase tracking-wide text-slate-500">{label}</label>
      <input
        required
        type={type}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm"
        {...rest}
      />
    </div>
  );
}
