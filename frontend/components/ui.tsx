import type { AlertSeverity, AlertStatus, ShipmentStatus } from '@/lib/api';

export function PageHeader({ eyebrow, title, action }: { eyebrow: string; title: string; action?: React.ReactNode }) {
  return (
    <header className="mb-8 flex flex-wrap items-center justify-between gap-4">
      <div>
        <p className="text-sm font-semibold uppercase tracking-[0.2em] text-sky-700">{eyebrow}</p>
        <h1 className="mt-2 text-3xl font-bold text-slate-900">{title}</h1>
      </div>
      {action}
    </header>
  );
}

export function MetricCard({
  title,
  value,
  tone = 'sky',
}: {
  title: string;
  value: string;
  tone?: 'sky' | 'amber' | 'rose' | 'orange' | 'emerald';
}) {
  const toneMap: Record<string, string> = {
    sky: 'bg-sky-50 text-sky-900',
    amber: 'bg-amber-50 text-amber-900',
    rose: 'bg-rose-50 text-rose-900',
    orange: 'bg-orange-50 text-orange-900',
    emerald: 'bg-emerald-50 text-emerald-900',
  };
  return (
    <div className={`rounded-2xl border border-slate-200 p-5 ${toneMap[tone]}`}>
      <p className="text-sm font-medium opacity-80">{title}</p>
      <p className="mt-3 text-3xl font-bold">{value}</p>
    </div>
  );
}

const SHIPMENT_STATUS_STYLE: Record<ShipmentStatus, string> = {
  pending: 'bg-slate-100 text-slate-700',
  in_transit: 'bg-sky-100 text-sky-800',
  delayed: 'bg-rose-100 text-rose-800',
  delivered: 'bg-emerald-100 text-emerald-800',
  cancelled: 'bg-slate-200 text-slate-500 line-through',
};

export function ShipmentStatusBadge({ status }: { status: ShipmentStatus }) {
  return (
    <span className={`inline-flex items-center rounded-full px-2.5 py-1 text-xs font-semibold uppercase tracking-wide ${SHIPMENT_STATUS_STYLE[status]}`}>
      {status.replace('_', ' ')}
    </span>
  );
}

const SEVERITY_STYLE: Record<AlertSeverity, string> = {
  CRITICAL: 'bg-rose-100 text-rose-800 border-rose-200',
  WARNING: 'bg-amber-100 text-amber-800 border-amber-200',
  INFO: 'bg-sky-100 text-sky-800 border-sky-200',
};

export function SeverityBadge({ severity }: { severity: AlertSeverity }) {
  return (
    <span className={`inline-flex items-center rounded-full border px-2.5 py-1 text-xs font-semibold ${SEVERITY_STYLE[severity]}`}>
      {severity}
    </span>
  );
}

const ALERT_STATUS_STYLE: Record<AlertStatus, string> = {
  OPEN: 'bg-rose-50 text-rose-700',
  ACKNOWLEDGED: 'bg-amber-50 text-amber-700',
  RESOLVED: 'bg-emerald-50 text-emerald-700',
};

export function AlertStatusBadge({ status }: { status: AlertStatus }) {
  return (
    <span className={`inline-flex items-center rounded-full px-2.5 py-1 text-xs font-semibold ${ALERT_STATUS_STYLE[status]}`}>
      {status}
    </span>
  );
}

export function LoadingState({ label }: { label: string }) {
  return <div className="p-8 text-slate-500">{label}…</div>;
}

export function ErrorState({ message }: { message: string }) {
  return (
    <div className="rounded-xl border border-rose-200 bg-rose-50 p-4 text-sm text-rose-700">
      Error: {message}
    </div>
  );
}
