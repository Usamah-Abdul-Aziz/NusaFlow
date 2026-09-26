'use client';

import { useEffect, useMemo, useState } from 'react';
import {
  Area,
  CartesianGrid,
  ComposedChart,
  Legend,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import { fetchJson, type ForecastDetail, type ForecastSummary } from '@/lib/api';
import { EstimatedDataBadge, ErrorState, LoadingState, PageHeader } from '@/components/ui';

const HORIZONS = [7, 14, 30] as const;

type ChartPoint = {
  date: string;
  actual?: number;
  estimated_demand?: number;
  band?: [number, number]; // Recharts Area range: [lower, upper]
};

function buildChartData(detail: ForecastDetail): ChartPoint[] {
  const points: Record<string, ChartPoint> = {};
  for (const h of detail.historical_demand) {
    points[h.date] = { date: h.date, actual: h.demand_qty };
  }
  for (const f of detail.forecast) {
    points[f.date] = {
      ...points[f.date],
      date: f.date,
      estimated_demand: f.estimated_demand,
      band: [f.lower_bound, f.upper_bound],
    };
  }
  return Object.values(points).sort((a, b) => a.date.localeCompare(b.date));
}

export default function ForecastPage() {
  const [summaries, setSummaries] = useState<ForecastSummary[]>([]);
  const [selected, setSelected] = useState<{ sku: string; warehouse: string } | null>(null);
  const [detail, setDetail] = useState<ForecastDetail | null>(null);
  const [horizon, setHorizon] = useState<(typeof HORIZONS)[number]>(14);
  const [search, setSearch] = useState('');
  const [loadingSummary, setLoadingSummary] = useState(true);
  const [loadingDetail, setLoadingDetail] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchJson<ForecastSummary[]>('/api/v1/forecasts')
      .then((data) => {
        setSummaries(data);
        if (data.length > 0) setSelected({ sku: data[0].product, warehouse: data[0].warehouse });
      })
      .catch((err) => setError(err instanceof Error ? err.message : 'Failed to load forecasts'))
      .finally(() => setLoadingSummary(false));
  }, []);

  useEffect(() => {
    if (!selected) return;
    setLoadingDetail(true);
    fetchJson<ForecastDetail>(`/api/v1/forecasts?sku=${selected.sku}&warehouse=${selected.warehouse}&horizon_days=${horizon}`)
      .then(setDetail)
      .catch((err) => setError(err instanceof Error ? err.message : 'Failed to load forecast detail'))
      .finally(() => setLoadingDetail(false));
  }, [selected, horizon]);

  const filteredSummaries = useMemo(() => {
    if (!search) return summaries;
    const q = search.toLowerCase();
    return summaries.filter((s) => s.product.toLowerCase().includes(q) || s.warehouse.toLowerCase().includes(q));
  }, [summaries, search]);

  const chartData = useMemo(() => (detail ? buildChartData(detail) : []), [detail]);

  if (loadingSummary) return <LoadingState label="Loading forecasts" />;
  if (error && summaries.length === 0) return <div className="p-8"><ErrorState message={error} /></div>;

  return (
    <main className="p-6">
      <div className="mx-auto max-w-7xl">
        <PageHeader eyebrow="Analytics" title="Demand Forecasting" />

        <div className="grid gap-6 xl:grid-cols-[1fr_1.3fr]">
          <div className="card min-w-0 overflow-hidden">
            <div className="border-b border-slate-200 p-4">
              <input
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="Search SKU or warehouse…"
                className="w-full rounded-md border border-slate-300 px-3 py-1.5 text-sm"
              />
            </div>
            <div className="max-h-[32rem] overflow-auto">
              <table className="min-w-full divide-y divide-slate-200 text-left text-sm">
                <thead className="sticky top-0 bg-slate-50 text-slate-700">
                  <tr>
                    <th className="px-4 py-3 font-semibold">SKU</th>
                    <th className="px-4 py-3 font-semibold">Warehouse</th>
                    <th className="px-4 py-3 font-semibold">Method</th>
                    <th className="px-4 py-3 font-semibold">MAE</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-200 bg-white">
                  {filteredSummaries.map((f) => {
                    const isSelected = selected?.sku === f.product && selected?.warehouse === f.warehouse;
                    return (
                      <tr
                        key={f.id}
                        onClick={() => setSelected({ sku: f.product, warehouse: f.warehouse })}
                        className={`cursor-pointer ${isSelected ? 'bg-sky-50' : 'hover:bg-slate-50'}`}
                      >
                        <td className="px-4 py-3 font-medium text-slate-800">
                          <span className="flex items-center gap-2">
                            {f.product}
                            {f.is_estimated && <EstimatedDataBadge />}
                          </span>
                        </td>
                        <td className="px-4 py-3">{f.warehouse}</td>
                        <td className="px-4 py-3 text-xs">
                          <span className="rounded-full bg-slate-100 px-2 py-1 font-medium text-slate-600">
                            {f.method === 'weekday_seasonal' ? 'Weekday-seasonal' : 'Moving average'}
                          </span>
                        </td>
                        <td className="px-4 py-3">{f.mae !== null ? f.mae.toFixed(1) : '—'}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </div>

          <div className="card min-w-0 p-6">
            {loadingDetail || !detail ? (
              <LoadingState label="Loading forecast detail" />
            ) : (
              <>
                <div className="mb-1 flex flex-wrap items-center justify-between gap-3">
                  <h2 className="flex flex-wrap items-center gap-2 text-lg font-semibold text-slate-800">
                    {detail.product} · {detail.warehouse}
                    {detail.is_estimated && <EstimatedDataBadge />}
                  </h2>
                  <div className="flex gap-1">
                    {HORIZONS.map((h) => (
                      <button
                        key={h}
                        onClick={() => setHorizon(h)}
                        className={`rounded-full border px-3 py-1 text-xs font-medium ${
                          horizon === h ? 'border-sky-300 bg-sky-100 text-sky-900' : 'border-slate-200 text-slate-600 hover:bg-slate-50'
                        }`}
                      >
                        {h}d
                      </button>
                    ))}
                  </div>
                </div>
                <p className="mb-4 text-xs text-slate-500">
                  MAE {detail.mae?.toFixed(1) ?? '—'}
                  {detail.mape !== null && ` · MAPE ${detail.mape.toFixed(0)}%`} on a 14-day backtest ·{' '}
                  {detail.method === 'weekday_seasonal' ? 'weekday-seasonal' : 'moving average'} model
                </p>

                <ResponsiveContainer width="100%" height={320}>
                  {/* An estimated pair draws in amber instead of sky blue so the
                      whole chart reads as caution, matching the badge above —
                      never the colours real-data forecasts use. */}
                  {(() => {
                    const series = detail.is_estimated ? '#d97706' : '#0ea5e9';
                    return (
                  <ComposedChart data={chartData} margin={{ top: 5, right: 10, left: -10, bottom: 5 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
                    <XAxis dataKey="date" tick={{ fontSize: 11 }} minTickGap={30} />
                    <YAxis tick={{ fontSize: 11 }} />
                    <Tooltip
                      contentStyle={{ fontSize: 12, borderRadius: 8, borderColor: '#e2e8f0' }}
                      formatter={(value: unknown) => (typeof value === 'number' ? value.toFixed(1) : String(value ?? ''))}
                    />
                    <Legend wrapperStyle={{ fontSize: 12 }} />
                    <Area
                      type="monotone"
                      dataKey="band"
                      name="Uncertainty band"
                      stroke="none"
                      fill={series}
                      fillOpacity={0.12}
                      connectNulls
                    />
                    <Line type="monotone" dataKey="actual" name="Historical demand" stroke="#0f172a" dot={false} strokeWidth={2} connectNulls={false} />
                    <Line
                      type="monotone"
                      dataKey="estimated_demand"
                      name="Estimated demand"
                      stroke={series}
                      strokeDasharray="5 3"
                      dot={false}
                      strokeWidth={2}
                      connectNulls={false}
                    />
                  </ComposedChart>
                    );
                  })()}
                </ResponsiveContainer>

                <p className="mt-3 text-xs italic text-slate-400">{detail.methodology}</p>
              </>
            )}
          </div>
        </div>
      </div>
    </main>
  );
}
