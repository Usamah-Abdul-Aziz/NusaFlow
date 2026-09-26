'use client';

import Link from 'next/link';
import { useEffect, useMemo, useState } from 'react';
import {
  fetchJson,
  type ProductRecord,
  type ShipmentCreatePayload,
  type ShipmentItem,
  type ShipmentStatus,
  type Supplier,
  type WarehouseRecord,
} from '@/lib/api';
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
  const [showAddForm, setShowAddForm] = useState(false);
  const [products, setProducts] = useState<ProductRecord[]>([]);
  const [warehouses, setWarehouses] = useState<WarehouseRecord[]>([]);
  const [suppliers, setSuppliers] = useState<Supplier[]>([]);

  function loadShipments() {
    setLoading(true);
    fetchJson<ShipmentItem[]>('/api/v1/shipments')
      .then(setShipments)
      .catch((err) => setError(err instanceof Error ? err.message : 'Failed to load shipments'))
      .finally(() => setLoading(false));
  }

  function loadMasterData() {
    fetchJson<ProductRecord[]>('/api/v1/products').then(setProducts).catch(() => {});
    fetchJson<WarehouseRecord[]>('/api/v1/warehouses').then(setWarehouses).catch(() => {});
    fetchJson<Supplier[]>('/api/v1/suppliers').then(setSuppliers).catch(() => {});
  }

  useEffect(() => {
    loadShipments();
    loadMasterData();
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
        <PageHeader
          eyebrow="Logistics"
          title="Real-Time Shipment Monitoring"
          action={
            <button
              onClick={() => setShowAddForm((v) => !v)}
              className={`rounded-lg px-4 py-2 text-sm font-semibold transition-colors ${
                showAddForm ? 'bg-slate-700 text-white' : 'bg-sky-700 text-white hover:bg-sky-800'
              }`}
            >
              {showAddForm ? 'Cancel' : '+ Tambah Shipment'}
            </button>
          }
        />

        {showAddForm && (
          <AddShipmentForm
            products={products}
            warehouses={warehouses}
            suppliers={suppliers}
            onDone={() => { setShowAddForm(false); loadShipments(); }}
          />
        )}

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
                <tr><td colSpan={8} className="px-4 py-8 text-center text-slate-500">No shipments match this filter{shipments.length === 0 ? ' — use "+ Tambah Shipment" to create one.' : '.'}</td></tr>
              )}
            </tbody>
          </table>
          </div>
        </div>
      </div>
    </main>
  );
}

function AddShipmentForm({
  products,
  warehouses,
  suppliers,
  onDone,
}: {
  products: ProductRecord[];
  warehouses: WarehouseRecord[];
  suppliers: Supplier[];
  onDone: () => void;
}) {
  const [productId, setProductId] = useState('');
  const [warehouseId, setWarehouseId] = useState('');
  const [supplierId, setSupplierId] = useState('');
  const [quantity, setQuantity] = useState('10');
  // The backend takes exactly one of the two; the toggle picks which.
  const [arrivalMode, setArrivalMode] = useState<'transit_days' | 'eta_date'>('transit_days');
  const [transitDays, setTransitDays] = useState('5');
  const [etaDate, setEtaDate] = useState('');
  const [status, setStatus] = useState<ShipmentStatus>('pending');
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!productId || !warehouseId || !supplierId) {
      setError('Choose a product, a warehouse and a supplier.');
      return;
    }
    setSaving(true);
    setError(null);
    try {
      const payload: ShipmentCreatePayload = {
        product_id: Number(productId),
        warehouse_id: Number(warehouseId),
        supplier_id: Number(supplierId),
        quantity: Number(quantity),
        status,
      };
      if (arrivalMode === 'transit_days') payload.transit_days = Number(transitDays);
      else payload.eta_date = etaDate;

      await fetchJson<ShipmentItem>('/api/v1/shipments', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
      onDone();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to create shipment');
      setSaving(false);
    }
  }

  if (warehouses.length === 0 || products.length === 0 || suppliers.length === 0) {
    return (
      <div className="card mb-6 p-5 text-sm text-slate-600">
        A shipment links a supplier shipment of a product to a warehouse — add at least one of each in Inventory and Suppliers first.
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
      <div className="sm:col-span-2">
        <label className="mb-1 block text-xs font-semibold uppercase tracking-wide text-slate-500">Supplier</label>
        <select required value={supplierId} onChange={(e) => setSupplierId(e.target.value)} className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm">
          <option value="">Choose…</option>
          {suppliers.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
        </select>
      </div>
      <Field label="Quantity" value={quantity} onChange={setQuantity} type="number" min={1} />
      <div>
        <label className="mb-1 block text-xs font-semibold uppercase tracking-wide text-slate-500">Arrival</label>
        <div className="flex rounded-md border border-slate-300 p-0.5 text-xs">
          <button
            type="button"
            onClick={() => setArrivalMode('transit_days')}
            className={`flex-1 rounded px-2 py-1.5 font-medium ${arrivalMode === 'transit_days' ? 'bg-sky-100 text-sky-900' : 'text-slate-600'}`}
          >
            Transit days
          </button>
          <button
            type="button"
            onClick={() => setArrivalMode('eta_date')}
            className={`flex-1 rounded px-2 py-1.5 font-medium ${arrivalMode === 'eta_date' ? 'bg-sky-100 text-sky-900' : 'text-slate-600'}`}
          >
            Exact date
          </button>
        </div>
      </div>
      {arrivalMode === 'transit_days' ? (
        <Field label="Transit days" value={transitDays} onChange={setTransitDays} type="number" min={1} max={180} />
      ) : (
        <Field label="ETA date" value={etaDate} onChange={setEtaDate} type="date" />
      )}
      <div>
        <label className="mb-1 block text-xs font-semibold uppercase tracking-wide text-slate-500">Starts as</label>
        <select value={status} onChange={(e) => setStatus(e.target.value as ShipmentStatus)} className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm">
          <option value="pending">Pending</option>
          <option value="in_transit">In transit</option>
        </select>
      </div>
      {error && <p className="text-sm text-rose-600 sm:col-span-6">{error}</p>}
      <div className="sm:col-span-6">
        <button type="submit" disabled={saving} className="rounded-lg bg-sky-700 px-4 py-2 text-sm font-semibold text-white hover:bg-sky-800 disabled:opacity-50">
          {saving ? 'Creating…' : 'Create shipment'}
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
