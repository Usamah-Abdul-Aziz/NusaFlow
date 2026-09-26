'use client';

import { useEffect, useMemo, useState } from 'react';
import { CheckCircle2, RefreshCw } from 'lucide-react';
import { fetchJson, type Alert, type AlertStatus } from '@/lib/api';
import { AlertStatusBadge, Button, ErrorState, LoadingState, PageHeader, SeverityBadge } from '@/components/ui';

const STATUS_FILTERS: { label: string; value: AlertStatus | 'all' }[] = [
  { label: 'Open', value: 'OPEN' },
  { label: 'Acknowledged', value: 'ACKNOWLEDGED' },
  { label: 'Resolved', value: 'RESOLVED' },
  { label: 'All', value: 'all' },
];

export default function AlertsPage() {
  const [alerts, setAlerts] = useState<Alert[]>([]);
  const [statusFilter, setStatusFilter] = useState<AlertStatus | 'all'>('OPEN');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [regenerating, setRegenerating] = useState(false);
  const [busyId, setBusyId] = useState<number | null>(null);

  async function load() {
    try {
      setLoading(true);
      const data = await fetchJson<Alert[]>('/api/v1/alerts');
      setAlerts(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load alerts');
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { load(); }, []);

  const severityOrder: Record<string, number> = { CRITICAL: 0, WARNING: 1, INFO: 2 };
  const filtered = useMemo(() => {
    const list = statusFilter === 'all' ? alerts : alerts.filter((a) => a.status === statusFilter);
    return [...list].sort((a, b) => severityOrder[a.severity] - severityOrder[b.severity]);
  }, [alerts, statusFilter]);

  const counts = useMemo(() => {
    const c: Record<string, number> = { all: alerts.length };
    for (const a of alerts) c[a.status] = (c[a.status] ?? 0) + 1;
    return c;
  }, [alerts]);

  async function handleRegenerate() {
    setRegenerating(true);
    try {
      await fetchJson('/api/v1/alerts/generate', { method: 'POST' });
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to re-run alert engine');
    } finally {
      setRegenerating(false);
    }
  }

  async function updateStatus(alert: Alert, status: AlertStatus) {
    setBusyId(alert.id);
    try {
      const updated = await fetchJson<Alert>(`/api/v1/alerts/${alert.id}?status=${status}`, { method: 'PATCH' });
      setAlerts((prev) => prev.map((a) => (a.id === updated.id ? updated : a)));
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to update alert');
    } finally {
      setBusyId(null);
    }
  }

  if (loading) return <LoadingState label="Loading alerts" />;

  return (
    <main className="p-6">
      <div className="mx-auto max-w-5xl">
        <PageHeader
          eyebrow="Monitoring"
          title="Alert Engine"
          action={
            <Button onClick={handleRegenerate} loading={regenerating} variant="secondary" icon={RefreshCw}>
              {regenerating ? 'Running…' : 'Re-run alert engine'}
            </Button>
          }
        />

        {error && <div className="mb-4"><ErrorState message={error} /></div>}

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

        <div className="space-y-3">
          {filtered.map((alert) => (
            <div key={alert.id} className="card p-5">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <div className="mb-1 flex items-center gap-2">
                    <SeverityBadge severity={alert.severity} />
                    <span className="text-xs font-semibold uppercase tracking-wide text-slate-400">{alert.alert_type}</span>
                  </div>
                  <p className="font-semibold text-slate-800">{alert.title}</p>
                  <p className="mt-1 text-sm text-slate-600">{alert.description}</p>
                  <p className="mt-2 text-xs text-slate-400">
                    Opened {new Date(alert.created_at).toLocaleString()}
                    {alert.resolved_at && ` · Resolved ${new Date(alert.resolved_at).toLocaleString()}`}
                  </p>
                </div>
                <div className="flex shrink-0 items-center gap-2">
                  <AlertStatusBadge status={alert.status} />
                  {alert.status === 'OPEN' && (
                    <Button onClick={() => updateStatus(alert, 'ACKNOWLEDGED')} loading={busyId === alert.id} variant="secondary" size="sm">
                      Acknowledge
                    </Button>
                  )}
                  {alert.status !== 'RESOLVED' && (
                    <Button onClick={() => updateStatus(alert, 'RESOLVED')} loading={busyId === alert.id} variant="primary" size="sm" icon={CheckCircle2}>
                      Resolve
                    </Button>
                  )}
                </div>
              </div>
            </div>
          ))}
          {filtered.length === 0 && (
            <div className="rounded-md border border-slate-200 bg-slate-50 p-6 text-center text-sm text-slate-600">
              No alerts in this view.
            </div>
          )}
        </div>
      </div>
    </main>
  );
}
