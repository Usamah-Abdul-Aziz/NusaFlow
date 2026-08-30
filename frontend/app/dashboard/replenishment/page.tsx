'use client';

import { useEffect, useMemo, useState } from 'react';
import { fetchJson, type ReplenishmentRecommendation } from '@/lib/api';
import { ErrorState, LoadingState, PageHeader } from '@/components/ui';

export default function ReplenishmentPage() {
  const [recommendations, setRecommendations] = useState<ReplenishmentRecommendation[]>([]);
  const [needsReorderOnly, setNeedsReorderOnly] = useState(true);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [regenerating, setRegenerating] = useState(false);

  async function load() {
    try {
      setLoading(true);
      const data = await fetchJson<ReplenishmentRecommendation[]>('/api/v1/replenishment');
      setRecommendations(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load replenishment recommendations');
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { load(); }, []);

  const visible = useMemo(
    () => (needsReorderOnly ? recommendations.filter((r) => r.recommended_quantity > 0) : recommendations),
    [recommendations, needsReorderOnly]
  );

  const selected = recommendations.find((r) => r.id === selectedId) ?? null;

  async function handleRegenerate() {
    setRegenerating(true);
    try {
      await fetchJson('/api/v1/replenishment/generate', { method: 'POST' });
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to re-run replenishment engine');
    } finally {
      setRegenerating(false);
    }
  }

  if (loading) return <LoadingState label="Loading replenishment recommendations" />;
  if (error && recommendations.length === 0) return <div className="p-8"><ErrorState message={error} /></div>;

  const needCount = recommendations.filter((r) => r.recommended_quantity > 0).length;

  return (
    <main className="p-6">
      <div className="mx-auto max-w-7xl">
        <PageHeader
          eyebrow="Phase 6"
          title="Replenishment Recommendation"
          action={
            <button
              onClick={handleRegenerate}
              disabled={regenerating}
              className="rounded-lg border border-slate-300 bg-white px-4 py-2 text-sm font-semibold text-slate-700 transition-colors hover:bg-slate-50 disabled:opacity-50"
            >
              {regenerating ? 'Running…' : 'Re-run replenishment engine'}
            </button>
          }
        />

        {error && <div className="mb-4"><ErrorState message={error} /></div>}

        <div className="mb-6 flex flex-wrap items-center gap-3">
          <button
            onClick={() => setNeedsReorderOnly(true)}
            className={`rounded-full border px-3 py-1.5 text-sm font-medium ${
              needsReorderOnly ? 'border-sky-300 bg-sky-100 text-sky-900' : 'border-slate-200 bg-white text-slate-600 hover:bg-slate-50'
            }`}
          >
            Needs reorder <span className="ml-1 text-xs opacity-60">{needCount}</span>
          </button>
          <button
            onClick={() => setNeedsReorderOnly(false)}
            className={`rounded-full border px-3 py-1.5 text-sm font-medium ${
              !needsReorderOnly ? 'border-sky-300 bg-sky-100 text-sky-900' : 'border-slate-200 bg-white text-slate-600 hover:bg-slate-50'
            }`}
          >
            All pairs <span className="ml-1 text-xs opacity-60">{recommendations.length}</span>
          </button>
        </div>

        <div className="grid gap-6 xl:grid-cols-[1.4fr_1fr]">
          <div className="card min-w-0 overflow-hidden">
            <div className="overflow-x-auto">
              <table className="min-w-full divide-y divide-slate-200 text-left text-sm">
                <thead className="bg-slate-50 text-slate-700">
                  <tr>
                    <th className="px-4 py-3 font-semibold">SKU</th>
                    <th className="px-4 py-3 font-semibold">Warehouse</th>
                    <th className="px-4 py-3 font-semibold">Lead time</th>
                    <th className="px-4 py-3 font-semibold">On hand</th>
                    <th className="px-4 py-3 font-semibold">Incoming</th>
                    <th className="px-4 py-3 font-semibold">Forecast demand</th>
                    <th className="px-4 py-3 font-semibold">Safety stock</th>
                    <th className="px-4 py-3 font-semibold">Recommended</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-200 bg-white">
                  {visible.map((r) => (
                    <tr
                      key={r.id}
                      onClick={() => setSelectedId(r.id)}
                      className={`cursor-pointer ${selectedId === r.id ? 'bg-sky-50' : r.recommended_quantity > 0 ? 'bg-amber-50/50 hover:bg-amber-50' : 'hover:bg-slate-50'}`}
                    >
                      <td className="px-4 py-3 font-medium text-slate-800">{r.product}</td>
                      <td className="px-4 py-3">{r.warehouse}</td>
                      <td className="px-4 py-3">{r.lead_time_days}d</td>
                      <td className="px-4 py-3">{r.current_stock}</td>
                      <td className="px-4 py-3">{r.incoming_stock}</td>
                      <td className="px-4 py-3">{r.forecast_demand.toFixed(1)}</td>
                      <td className="px-4 py-3">{r.safety_stock}</td>
                      <td className="px-4 py-3">
                        {r.recommended_quantity > 0 ? (
                          <span className="font-semibold text-amber-800">{r.recommended_quantity.toFixed(0)}</span>
                        ) : (
                          <span className="text-slate-400">—</span>
                        )}
                      </td>
                    </tr>
                  ))}
                  {visible.length === 0 && (
                    <tr><td colSpan={8} className="px-4 py-8 text-center text-slate-500">Nothing needs reordering right now.</td></tr>
                  )}
                </tbody>
              </table>
            </div>
          </div>

          <div className="card min-w-0 p-6">
            <h2 className="mb-3 text-lg font-semibold text-slate-800">Why this number?</h2>
            {selected ? (
              <>
                <p className="mb-4 text-sm font-medium text-slate-700">{selected.product} · {selected.warehouse}</p>
                <p className="text-sm leading-relaxed text-slate-600">{selected.explanation}</p>
                <dl className="mt-5 grid grid-cols-2 gap-3 text-sm">
                  <Row label="Lead time" value={`${selected.lead_time_days} day(s)`} />
                  <Row label="Forecast demand" value={selected.forecast_demand.toFixed(1)} />
                  <Row label="Safety stock" value={String(selected.safety_stock)} />
                  <Row label="On hand" value={String(selected.current_stock)} />
                  <Row label="Incoming" value={String(selected.incoming_stock)} />
                  <Row label="Recommended order" value={selected.recommended_quantity.toFixed(1)} strong />
                </dl>
              </>
            ) : (
              <p className="text-sm text-slate-500">Click a row on the left to see how its recommendation was calculated.</p>
            )}
          </div>
        </div>
      </div>
    </main>
  );
}

function Row({ label, value, strong }: { label: string; value: string; strong?: boolean }) {
  return (
    <div>
      <dt className="text-xs font-semibold uppercase tracking-wide text-slate-400">{label}</dt>
      <dd className={strong ? 'font-semibold text-amber-800' : 'text-slate-700'}>{value}</dd>
    </div>
  );
}
