'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { fetchJson, type SimulationComparison, type SimulationParams, type SimulationScenario } from '@/lib/api';
import { ErrorState, LoadingState, PageHeader } from '@/components/ui';

const DEFAULT_PARAMS: SimulationParams = {
  demand_change_pct: 0,
  lead_time_delta_days: 0,
  shipment_delay_delta_days: 0,
  safety_stock_change_pct: 0,
};

const METRIC_META: {
  key: keyof SimulationComparison['baseline'];
  label: string;
  format: (v: number) => string;
  higherIsBetter: boolean;
}[] = [
  { key: 'service_level_pct', label: 'Service Level', format: (v) => `${v}%`, higherIsBetter: true },
  { key: 'stockout_risk_count', label: 'Stockout Risks', format: (v) => String(v), higherIsBetter: false },
  { key: 'late_shipments_count', label: 'Late Shipments', format: (v) => String(v), higherIsBetter: false },
  { key: 'replenishment_requirement', label: 'Replenishment Needed (units)', format: (v) => v.toFixed(0), higherIsBetter: false },
  { key: 'inventory_cost', label: 'Est. Replenishment Cost', format: (v) => `$${v.toLocaleString(undefined, { maximumFractionDigits: 0 })}`, higherIsBetter: false },
];

function Slider({
  label, value, min, max, step, unit, onChange,
}: { label: string; value: number; min: number; max: number; step: number; unit: string; onChange: (v: number) => void }) {
  return (
    <div className="mb-5">
      <div className="mb-1 flex items-center justify-between text-sm">
        <label className="font-medium text-slate-700">{label}</label>
        <span className="font-semibold text-sky-700">{value > 0 ? `+${value}` : value}{unit}</span>
      </div>
      <input
        type="range"
        min={min}
        max={max}
        step={step}
        value={value}
        onChange={(e) => onChange(Number(e.target.value))}
        className="w-full accent-sky-700"
      />
      <div className="mt-1 flex justify-between text-xs text-slate-400">
        <span>{min}{unit}</span>
        <span>{max}{unit}</span>
      </div>
    </div>
  );
}

function MetricComparisonCard({ meta, comparison }: { meta: (typeof METRIC_META)[number]; comparison: SimulationComparison }) {
  const baseline = comparison.baseline[meta.key];
  const simulated = comparison.simulated[meta.key];
  const delta = comparison.delta[meta.key];
  const improved = meta.higherIsBetter ? delta > 0 : delta < 0;
  const worsened = meta.higherIsBetter ? delta < 0 : delta > 0;
  const deltaColor = improved ? 'text-emerald-700' : worsened ? 'text-rose-700' : 'text-slate-400';

  return (
    <div className="rounded-xl border border-slate-200 p-4">
      <p className="text-xs font-semibold uppercase tracking-wide text-slate-400">{meta.label}</p>
      <div className="mt-2 flex items-baseline gap-2">
        <span className="text-sm text-slate-400 line-through decoration-slate-300">{meta.format(baseline)}</span>
        <span className="text-xl font-bold text-slate-800">{meta.format(simulated)}</span>
      </div>
      {delta !== 0 && (
        <p className={`mt-1 text-sm font-medium ${deltaColor}`}>
          {delta > 0 ? '+' : ''}{meta.format(delta).replace(/^\$-/, '-$')} vs. current
        </p>
      )}
    </div>
  );
}

function buildTakeaway(comparison: SimulationComparison): string {
  const { delta } = comparison;
  const parts: string[] = [];
  if (delta.service_level_pct !== 0) {
    parts.push(`service level would ${delta.service_level_pct > 0 ? 'improve' : 'drop'} by ${Math.abs(delta.service_level_pct)} points`);
  }
  if (delta.replenishment_requirement > 0) {
    parts.push(`you'd need to order ~${Math.round(delta.replenishment_requirement)} more units (est. $${Math.round(delta.inventory_cost).toLocaleString()}) to stay covered`);
  } else if (delta.replenishment_requirement < 0) {
    parts.push(`you'd need ~${Math.round(Math.abs(delta.replenishment_requirement))} fewer replenishment units`);
  }
  if (delta.late_shipments_count > 0) {
    parts.push(`${delta.late_shipments_count} more shipment(s) would run late`);
  }
  if (parts.length === 0) return 'This scenario matches current conditions — no meaningful change projected.';
  return `Under this scenario, ${parts.join(', ')}.`;
}

export default function SimulationPage() {
  const [params, setParams] = useState<SimulationParams>(DEFAULT_PARAMS);
  const [comparison, setComparison] = useState<SimulationComparison | null>(null);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [scenarioName, setScenarioName] = useState('');
  const [saving, setSaving] = useState(false);
  const [saveMessage, setSaveMessage] = useState<string | null>(null);
  const [savedScenarios, setSavedScenarios] = useState<SimulationScenario[]>([]);
  const [loadingSaved, setLoadingSaved] = useState(true);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const runPreview = useCallback(async (nextParams: SimulationParams) => {
    setRunning(true);
    setError(null);
    try {
      const result = await fetchJson<SimulationComparison>('/api/v1/simulations/run', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(nextParams),
      });
      setComparison(result);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to run simulation');
    } finally {
      setRunning(false);
    }
  }, []);

  // Debounced live preview: recompute ~400ms after the user stops moving a slider.
  useEffect(() => {
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => runPreview(params), 400);
    return () => { if (debounceRef.current) clearTimeout(debounceRef.current); };
  }, [params, runPreview]);

  async function loadSaved() {
    try {
      setLoadingSaved(true);
      const data = await fetchJson<SimulationScenario[]>('/api/v1/simulations');
      setSavedScenarios(data);
    } catch {
      // saved-scenario list is secondary; a failure here shouldn't block the live simulator
    } finally {
      setLoadingSaved(false);
    }
  }
  useEffect(() => { loadSaved(); }, []);

  function updateParam(key: keyof SimulationParams, value: number) {
    setParams((prev) => ({ ...prev, [key]: value }));
  }

  async function handleSave() {
    if (!scenarioName.trim()) return;
    setSaving(true);
    setSaveMessage(null);
    try {
      await fetchJson('/api/v1/simulations', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ ...params, name: scenarioName.trim() }),
      });
      setSaveMessage(`Saved "${scenarioName.trim()}"`);
      setScenarioName('');
      await loadSaved();
    } catch (err) {
      setSaveMessage(err instanceof Error ? err.message : 'Failed to save scenario');
    } finally {
      setSaving(false);
    }
  }

  async function handleRerun(id: number) {
    try {
      await fetchJson(`/api/v1/simulations/${id}/run`, { method: 'POST' });
      await loadSaved();
    } catch {
      // non-critical; leave stale row rather than blocking the page
    }
  }

  return (
    <main className="p-6">
      <div className="mx-auto max-w-7xl">
        <PageHeader eyebrow="Analytics" title="What-If Simulation" />
        <p className="mb-6 max-w-3xl text-sm text-slate-600">
          Adjust the sliders to model a hypothetical — nothing here touches real inventory, shipment,
          or forecast data. Every number below is recomputed from a temporary copy of the current
          state each time you move a slider.
        </p>

        <div className="grid gap-6 xl:grid-cols-[0.9fr_1.4fr]">
          <div className="card min-w-0 p-6">
            <h2 className="mb-4 text-lg font-semibold text-slate-800">Scenario controls</h2>
            <Slider label="Demand change" value={params.demand_change_pct} min={-50} max={100} step={5} unit="%" onChange={(v) => updateParam('demand_change_pct', v)} />
            <Slider label="Supplier lead-time change" value={params.lead_time_delta_days} min={-10} max={20} step={1} unit="d" onChange={(v) => updateParam('lead_time_delta_days', v)} />
            <Slider label="Shipment delay" value={params.shipment_delay_delta_days} min={-10} max={20} step={1} unit="d" onChange={(v) => updateParam('shipment_delay_delta_days', v)} />
            <Slider label="Safety stock change" value={params.safety_stock_change_pct} min={-50} max={100} step={5} unit="%" onChange={(v) => updateParam('safety_stock_change_pct', v)} />

            <button
              onClick={() => setParams(DEFAULT_PARAMS)}
              className="mb-4 text-xs font-medium text-slate-500 hover:text-slate-700 hover:underline"
            >
              Reset to current conditions
            </button>

            <div className="mt-4 border-t border-slate-200 pt-4">
              <label className="mb-1 block text-xs font-semibold uppercase tracking-wide text-slate-500">Save this scenario</label>
              <div className="flex gap-2">
                <input
                  value={scenarioName}
                  onChange={(e) => setScenarioName(e.target.value)}
                  placeholder="e.g. Peak season stress test"
                  className="min-w-0 flex-1 rounded-md border border-slate-300 px-3 py-1.5 text-sm"
                />
                <button
                  onClick={handleSave}
                  disabled={saving || !scenarioName.trim()}
                  className="shrink-0 rounded-lg bg-sky-700 px-3 py-1.5 text-sm font-semibold text-white hover:bg-sky-800 disabled:cursor-not-allowed disabled:bg-slate-300"
                >
                  {saving ? 'Saving…' : 'Save'}
                </button>
              </div>
              {saveMessage && <p className="mt-2 text-xs text-slate-500">{saveMessage}</p>}
            </div>
          </div>

          <div className="card min-w-0 p-6">
            <div className="mb-4 flex items-center justify-between">
              <h2 className="text-lg font-semibold text-slate-800">Current vs. simulated</h2>
              {running && <span className="text-xs text-slate-400">Recalculating…</span>}
            </div>

            {error && <ErrorState message={error} />}

            {comparison ? (
              <>
                <p className="mb-4 rounded-lg bg-sky-50 p-3 text-sm text-sky-900">{buildTakeaway(comparison)}</p>
                <div className="grid gap-3 sm:grid-cols-2">
                  {METRIC_META.map((meta) => (
                    <MetricComparisonCard key={meta.key} meta={meta} comparison={comparison} />
                  ))}
                </div>
              </>
            ) : (
              <LoadingState label="Running baseline simulation" />
            )}
          </div>
        </div>

        <div className="card mt-6 min-w-0 overflow-hidden">
          <div className="border-b border-slate-200 p-4">
            <h2 className="text-lg font-semibold text-slate-800">Saved scenarios</h2>
          </div>
          {loadingSaved ? (
            <LoadingState label="Loading saved scenarios" />
          ) : savedScenarios.length === 0 ? (
            <p className="p-6 text-sm text-slate-500">No scenarios saved yet — adjust the sliders above and click Save.</p>
          ) : (
            <div className="overflow-x-auto">
              <table className="min-w-full divide-y divide-slate-200 text-left text-sm">
                <thead className="bg-slate-50 text-slate-700">
                  <tr>
                    <th className="px-4 py-3 font-semibold">Name</th>
                    <th className="px-4 py-3 font-semibold">Demand</th>
                    <th className="px-4 py-3 font-semibold">Lead time</th>
                    <th className="px-4 py-3 font-semibold">Ship. delay</th>
                    <th className="px-4 py-3 font-semibold">Safety stock</th>
                    <th className="px-4 py-3 font-semibold">Service level</th>
                    <th className="px-4 py-3 font-semibold"></th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-200 bg-white">
                  {savedScenarios.map((s) => (
                    <tr key={s.id}>
                      <td className="px-4 py-3 font-medium text-slate-800">{s.name}</td>
                      <td className="px-4 py-3">{s.demand_change_pct > 0 ? '+' : ''}{s.demand_change_pct}%</td>
                      <td className="px-4 py-3">{s.lead_time_delta_days > 0 ? '+' : ''}{s.lead_time_delta_days}d</td>
                      <td className="px-4 py-3">{s.shipment_delay_delta_days > 0 ? '+' : ''}{s.shipment_delay_delta_days}d</td>
                      <td className="px-4 py-3">{s.safety_stock_change_pct > 0 ? '+' : ''}{s.safety_stock_change_pct}%</td>
                      <td className="px-4 py-3">
                        {s.baseline && s.simulated ? `${s.baseline.service_level_pct}% → ${s.simulated.service_level_pct}%` : '—'}
                      </td>
                      <td className="px-4 py-3">
                        <button onClick={() => handleRerun(s.id)} className="text-xs font-medium text-sky-700 hover:underline">
                          Re-run
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>
    </main>
  );
}
