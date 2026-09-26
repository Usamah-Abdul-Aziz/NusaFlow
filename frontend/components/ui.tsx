import type { ReactNode } from 'react';
import { AlertCircle, AlertTriangle, CheckCircle2, Circle, Loader2, type LucideIcon } from 'lucide-react';
import type { AlertSeverity, AlertStatus, ShipmentStatus } from '@/lib/api';

export function PageHeader({ eyebrow, title, action }: { eyebrow: string; title: string; action?: React.ReactNode }) {
  return (
    <header className="mb-8 flex flex-wrap items-center justify-between gap-4">
      <div>
        <p className="text-xs font-semibold uppercase tracking-[0.2em] text-sky-700">{eyebrow}</p>
        <h1 className="mt-1.5 text-3xl font-bold tracking-tight text-slate-900">{title}</h1>
      </div>
      {action}
    </header>
  );
}

const BUTTON_VARIANTS = {
  primary: 'bg-sky-700 text-white hover:bg-sky-800 disabled:bg-slate-300',
  secondary: 'border border-slate-300 bg-white text-slate-700 hover:bg-slate-50 disabled:opacity-50',
  danger: 'bg-rose-600 text-white hover:bg-rose-700 disabled:bg-slate-300',
  ghost: 'text-slate-500 hover:text-slate-800 hover:underline',
} as const;

export function Button({
  children,
  variant = 'primary',
  size = 'md',
  loading = false,
  icon: Icon,
  className = '',
  ...rest
}: {
  children: ReactNode;
  variant?: keyof typeof BUTTON_VARIANTS;
  size?: 'sm' | 'md';
  loading?: boolean;
  icon?: LucideIcon;
  className?: string;
} & React.ButtonHTMLAttributes<HTMLButtonElement>) {
  const sizeClass = size === 'sm' ? 'px-3 py-1.5 text-xs' : 'px-4 py-2 text-sm';
  return (
    <button
      className={`inline-flex shrink-0 items-center justify-center gap-1.5 rounded-lg font-semibold transition-colors disabled:cursor-not-allowed ${sizeClass} ${BUTTON_VARIANTS[variant]} ${className}`}
      disabled={loading || rest.disabled}
      {...rest}
    >
      {loading ? <Loader2 size={14} className="animate-spin" /> : Icon ? <Icon size={14} /> : null}
      {children}
    </button>
  );
}

const METRIC_TONE: Record<string, { bg: string; text: string; icon: string }> = {
  sky: { bg: 'bg-sky-50', text: 'text-sky-900', icon: 'text-sky-500' },
  amber: { bg: 'bg-amber-50', text: 'text-amber-900', icon: 'text-amber-500' },
  rose: { bg: 'bg-rose-50', text: 'text-rose-900', icon: 'text-rose-500' },
  orange: { bg: 'bg-orange-50', text: 'text-orange-900', icon: 'text-orange-500' },
  emerald: { bg: 'bg-emerald-50', text: 'text-emerald-900', icon: 'text-emerald-500' },
};

export function MetricCard({
  title,
  value,
  tone = 'sky',
  icon: Icon,
}: {
  title: string;
  value: string;
  tone?: keyof typeof METRIC_TONE;
  icon?: LucideIcon;
}) {
  const t = METRIC_TONE[tone];
  return (
    <div className={`rounded-2xl border border-slate-200 p-5 ${t.bg} ${t.text}`}>
      <div className="flex items-center justify-between">
        <p className="text-sm font-medium opacity-80">{title}</p>
        {Icon && <Icon size={18} className={t.icon} />}
      </div>
      <p className="mt-3 text-3xl font-bold tracking-tight">{value}</p>
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
    <span className={`inline-flex items-center gap-1 rounded-full px-2.5 py-1 text-xs font-semibold uppercase tracking-wide ${SHIPMENT_STATUS_STYLE[status]}`}>
      <Circle size={6} fill="currentColor" strokeWidth={0} />
      {status.replace('_', ' ')}
    </span>
  );
}

const SEVERITY_STYLE: Record<AlertSeverity, string> = {
  CRITICAL: 'bg-rose-100 text-rose-800 border-rose-200',
  WARNING: 'bg-amber-100 text-amber-800 border-amber-200',
  INFO: 'bg-sky-100 text-sky-800 border-sky-200',
};

const SEVERITY_ICON: Record<AlertSeverity, LucideIcon> = {
  CRITICAL: AlertCircle,
  WARNING: AlertTriangle,
  INFO: Circle,
};

export function SeverityBadge({ severity }: { severity: AlertSeverity }) {
  const Icon = SEVERITY_ICON[severity];
  return (
    <span className={`inline-flex items-center gap-1 rounded-full border px-2.5 py-1 text-xs font-semibold ${SEVERITY_STYLE[severity]}`}>
      <Icon size={12} />
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
  return (
    <div className="flex items-center gap-2 p-8 text-slate-500">
      <Loader2 size={16} className="animate-spin" />
      {label}…
    </div>
  );
}

export function ErrorState({ message }: { message: string }) {
  return (
    <div className="flex items-start gap-2 rounded-xl border border-rose-200 bg-rose-50 p-4 text-sm text-rose-700">
      <AlertCircle size={16} className="mt-0.5 shrink-0" />
      <span>Error: {message}</span>
    </div>
  );
}

export function SuccessNote({ message }: { message: string }) {
  return (
    <div className="flex items-center gap-2 rounded-lg bg-emerald-50 px-3 py-2 text-sm text-emerald-700">
      <CheckCircle2 size={14} />
      {message}
    </div>
  );
}

// Amber on purpose (see CLAUDE.md §5.1): the warning tone is already the
// established "caution" colour in this app, so an estimated pair can never
// read as a real-data result at a glance. Green/blue mean measured here.
export function EstimatedDataBadge({ className = '' }: { className?: string }) {
  return (
    <span
      title="The demand history behind this number was generated from a manual quick-estimate, not recorded sales."
      className={`inline-flex items-center gap-1 rounded-full border border-amber-200 bg-amber-100 px-2.5 py-1 text-xs font-semibold text-amber-800 ${className}`}
    >
      <AlertTriangle size={12} />
      Estimasi, bukan data historis asli
    </span>
  );
}
