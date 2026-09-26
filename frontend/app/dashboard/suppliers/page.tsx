'use client';

import { useEffect, useState } from 'react';
import { ApiError, fetchJson, type Supplier } from '@/lib/api';
import { ErrorState, LoadingState, PageHeader } from '@/components/ui';

export default function SuppliersPage() {
  const [suppliers, setSuppliers] = useState<Supplier[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [showForm, setShowForm] = useState(false);
  const [name, setName] = useState('');
  const [leadTime, setLeadTime] = useState('5');
  const [reliability, setReliability] = useState('90');
  const [saving, setSaving] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const [deletingId, setDeletingId] = useState<number | null>(null);

  function load() {
    setLoading(true);
    fetchJson<Supplier[]>('/api/v1/suppliers')
      .then(setSuppliers)
      .catch((err) => setError(err instanceof Error ? err.message : 'Failed to load suppliers'))
      .finally(() => setLoading(false));
  }
  useEffect(load, []);

  async function handleAdd(e: React.FormEvent) {
    e.preventDefault();
    setSaving(true);
    setFormError(null);
    try {
      await fetchJson('/api/v1/suppliers', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          name,
          lead_time_days: Number(leadTime),
          reliability_score: Number(reliability) / 100,
        }),
      });
      setName('');
      setLeadTime('5');
      setReliability('90');
      setShowForm(false);
      load();
    } catch (err) {
      setFormError(err instanceof Error ? err.message : 'Failed to add supplier');
    } finally {
      setSaving(false);
    }
  }

  async function handleDelete(supplier: Supplier) {
    if (!window.confirm(`Remove ${supplier.name}?`)) return;
    setDeletingId(supplier.id);
    try {
      await fetchJson(`/api/v1/suppliers/${supplier.id}`, { method: 'DELETE' });
      setSuppliers((prev) => prev.filter((s) => s.id !== supplier.id));
    } catch (err) {
      const message = err instanceof ApiError ? err.message : 'Failed to delete supplier';
      window.alert(message);
    } finally {
      setDeletingId(null);
    }
  }

  if (loading) return <LoadingState label="Loading suppliers" />;
  if (error) return <div className="p-8"><ErrorState message={error} /></div>;

  return (
    <main className="p-6">
      <div className="mx-auto max-w-5xl">
        <PageHeader
          eyebrow="Suppliers"
          title="Supplier Performance"
          action={
            <button
              onClick={() => setShowForm((v) => !v)}
              className="rounded-lg bg-sky-700 px-4 py-2 text-sm font-semibold text-white transition-colors hover:bg-sky-800"
            >
              {showForm ? 'Cancel' : '+ Add supplier'}
            </button>
          }
        />

        {showForm && (
          <form onSubmit={handleAdd} className="card mb-6 grid gap-4 p-5 sm:grid-cols-4">
            <div className="sm:col-span-2">
              <label className="mb-1 block text-xs font-semibold uppercase tracking-wide text-slate-500">Name</label>
              <input required value={name} onChange={(e) => setName(e.target.value)} className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm" />
            </div>
            <div>
              <label className="mb-1 block text-xs font-semibold uppercase tracking-wide text-slate-500">Lead time (days)</label>
              <input required type="number" min={1} max={180} value={leadTime} onChange={(e) => setLeadTime(e.target.value)} className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm" />
            </div>
            <div>
              <label className="mb-1 block text-xs font-semibold uppercase tracking-wide text-slate-500">Reliability (%)</label>
              <input required type="number" min={0} max={100} value={reliability} onChange={(e) => setReliability(e.target.value)} className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm" />
              <p className="mt-1 text-xs text-slate-400">Starting estimate — refined by real delivery data over time.</p>
            </div>
            {formError && <p className="text-sm text-rose-600 sm:col-span-4">{formError}</p>}
            <div className="sm:col-span-4">
              <button type="submit" disabled={saving} className="rounded-lg bg-sky-700 px-4 py-2 text-sm font-semibold text-white hover:bg-sky-800 disabled:opacity-50">
                {saving ? 'Adding…' : 'Add supplier'}
              </button>
            </div>
          </form>
        )}

        <div className="card overflow-hidden">
          <div className="overflow-x-auto">
          <table className="min-w-full divide-y divide-slate-200 text-left text-sm">
            <thead className="bg-slate-50 text-slate-700">
              <tr>
                <th className="px-4 py-3 font-semibold">Supplier</th>
                <th className="px-4 py-3 font-semibold">Lead time</th>
                <th className="px-4 py-3 font-semibold">Historical delay rate</th>
                <th className="px-4 py-3 font-semibold">Reliability score</th>
                <th className="px-4 py-3 font-semibold"></th>
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
                  <td className="px-4 py-3 text-right">
                    <button
                      onClick={() => handleDelete(s)}
                      disabled={deletingId === s.id}
                      className="text-xs font-medium text-rose-600 hover:underline disabled:opacity-50"
                    >
                      {deletingId === s.id ? 'Removing…' : 'Remove'}
                    </button>
                  </td>
                </tr>
              ))}
              {suppliers.length === 0 && (
                <tr><td colSpan={5} className="px-4 py-8 text-center text-slate-500">No suppliers yet — add your first one above.</td></tr>
              )}
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
