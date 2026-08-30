'use client';

import Link from 'next/link';
import { useEffect, useState } from 'react';
import { ApiError, fetchJson, type ShipmentEvent, type ShipmentItem } from '@/lib/api';
import { ErrorState, LoadingState, PageHeader, ShipmentStatusBadge } from '@/components/ui';

const TERMINAL_STATUSES = new Set(['delivered', 'cancelled']);

export default function ShipmentDetailPage({ params }: { params: { id: string } }) {
  const [shipment, setShipment] = useState<ShipmentItem | null>(null);
  const [events, setEvents] = useState<ShipmentEvent[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [advancing, setAdvancing] = useState(false);
  const [advanceMessage, setAdvanceMessage] = useState<string | null>(null);

  async function load() {
    try {
      setLoading(true);
      const [shipmentData, eventsData] = await Promise.all([
        fetchJson<ShipmentItem>(`/api/v1/shipments/${params.id}`),
        fetchJson<ShipmentEvent[]>(`/api/v1/shipments/${params.id}/events`),
      ]);
      setShipment(shipmentData);
      setEvents(eventsData);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load shipment');
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [params.id]);

  async function handleAdvance() {
    setAdvancing(true);
    setAdvanceMessage(null);
    try {
      const result = await fetchJson<{ shipment: ShipmentItem; new_event: ShipmentEvent }>(
        `/api/v1/shipments/${params.id}/simulate/advance`,
        { method: 'POST' }
      );
      setShipment(result.shipment);
      setEvents((prev) => [...prev, result.new_event]);
      setAdvanceMessage(`Advanced: ${result.new_event.event_type}`);
    } catch (err) {
      if (err instanceof ApiError && err.status === 409) {
        setAdvanceMessage('This shipment has already reached a terminal state.');
      } else {
        setAdvanceMessage(err instanceof Error ? err.message : 'Failed to advance shipment');
      }
    } finally {
      setAdvancing(false);
    }
  }

  if (loading) return <LoadingState label="Loading shipment" />;
  if (error || !shipment) return <div className="p-8"><ErrorState message={error ?? 'Shipment not found'} /></div>;

  const isTerminal = TERMINAL_STATUSES.has(shipment.status);

  return (
    <main className="p-6">
      <div className="mx-auto max-w-3xl">
        <Link href="/dashboard/shipments" className="mb-4 inline-block text-sm font-medium text-sky-700 hover:underline">← Back to shipments</Link>
        <PageHeader eyebrow="Phase 3 · Shipment" title={shipment.shipment_number} />

        <div className="card mb-6 grid grid-cols-2 gap-4 p-6 sm:grid-cols-3">
          <Field label="Status"><ShipmentStatusBadge status={shipment.status} /></Field>
          <Field label="Product" value={shipment.product} />
          <Field label="Warehouse" value={shipment.warehouse} />
          <Field label="Supplier" value={shipment.supplier} />
          <Field label="Quantity" value={String(shipment.quantity)} />
          <Field label="ETA" value={shipment.eta_date} />
          <Field label="Delivered" value={shipment.actual_delivery_date ?? '—'} />
          <Field
            label="Delay"
            value={shipment.delay_days > 0 ? `${shipment.delay_days} day(s)` : 'On time'}
            tone={shipment.delay_days > 0 ? 'text-rose-700' : undefined}
          />
        </div>

        <div className="card mb-6 p-6">
          <div className="mb-4 flex items-center justify-between">
            <h2 className="text-lg font-semibold text-slate-800">Simulate lifecycle</h2>
          </div>
          <p className="mb-3 text-sm text-slate-600">
            There's no background scheduler running here on purpose (see README) — click below to
            advance this shipment one step: Created → Departed → Checkpoint/Delay → Delivered.
          </p>
          <button
            onClick={handleAdvance}
            disabled={advancing || isTerminal}
            className="rounded-lg bg-sky-700 px-4 py-2 text-sm font-semibold text-white transition-colors hover:bg-sky-800 disabled:cursor-not-allowed disabled:bg-slate-300"
          >
            {isTerminal ? 'Shipment complete' : advancing ? 'Advancing…' : 'Simulate next step'}
          </button>
          {advanceMessage && <p className="mt-3 text-sm text-slate-600">{advanceMessage}</p>}
        </div>

        <div className="card p-6">
          <h2 className="mb-4 text-lg font-semibold text-slate-800">Event timeline</h2>
          <ol className="space-y-4">
            {events.map((event, i) => (
              <li key={event.id} className="relative pl-6">
                <span className={`absolute left-0 top-1.5 h-2.5 w-2.5 rounded-full ${i === events.length - 1 ? 'bg-sky-600' : 'bg-slate-300'}`} />
                {i < events.length - 1 && <span className="absolute left-[4.5px] top-4 h-full w-px bg-slate-200" />}
                <p className="font-medium text-slate-800">{event.event_type}</p>
                <p className="text-xs text-slate-500">{new Date(event.event_time).toLocaleString()}</p>
                {event.details && <p className="mt-1 text-sm text-slate-600">{event.details}</p>}
              </li>
            ))}
          </ol>
        </div>
      </div>
    </main>
  );
}

function Field({ label, value, tone, children }: { label: string; value?: string; tone?: string; children?: React.ReactNode }) {
  return (
    <div>
      <p className="text-xs font-semibold uppercase tracking-wide text-slate-400">{label}</p>
      {children ?? <p className={`mt-1 font-medium text-slate-800 ${tone ?? ''}`}>{value}</p>}
    </div>
  );
}
