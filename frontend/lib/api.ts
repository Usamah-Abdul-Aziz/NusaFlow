// Shared types + fetch helper for the NusaFlow dashboard.
//
// All requests go through the relative `/api/*` path, which
// frontend/next.config.mjs rewrites to BACKEND_URL server-side — see that
// file for why it's not read from a NEXT_PUBLIC_* var.

import { clearToken, getToken } from '@/lib/auth';

export class ApiError extends Error {
  status: number;
  constructor(message: string, status: number) {
    super(message);
    this.status = status;
  }
}

export async function fetchJson<T>(path: string, init?: RequestInit): Promise<T> {
  const token = getToken();
  const headers = new Headers(init?.headers);
  if (token) headers.set('Authorization', `Bearer ${token}`);

  const res = await fetch(path, { ...init, headers });

  if (res.status === 401) {
    // Token missing/expired/invalid — the backend is the source of truth
    // on validity (middleware.ts only checks the cookie's *presence*, not
    // whether it still verifies). Clear it and bounce to login rather
    // than let every page independently guess how to handle this.
    clearToken();
    if (typeof window !== 'undefined' && !window.location.pathname.startsWith('/login')) {
      window.location.href = '/login';
    }
    throw new ApiError('Session expired', 401);
  }

  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      if (body?.detail) detail = typeof body.detail === 'string' ? body.detail : JSON.stringify(body.detail);
    } catch {
      // response wasn't JSON — fall back to statusText
    }
    throw new ApiError(detail, res.status);
  }
  return res.json() as Promise<T>;
}

// Same job as fetchJson<MeResponse>('/api/v1/auth/me'), but for public
// pages (landing, login, signup) that want to know whether a visitor
// already has a session without the side effects fetchJson applies on 401.
//
// fetchJson redirects to /login when a token is missing or invalid — the
// right thing inside /dashboard, but wrong on the landing page, where an
// anonymous visitor with a stale cookie would get hauled into the login
// flow for no reason. Here a 401 just means "no session": drop the stale
// cookie so middleware stops gating on it, and return null.
export async function getSession(): Promise<MeResponse | null> {
  const token = getToken();
  if (!token) return null;

  try {
    const res = await fetch('/api/v1/auth/me', { headers: { Authorization: `Bearer ${token}` } });
    if (!res.ok) {
      if (res.status === 401) clearToken();
      return null;
    }
    return (await res.json()) as MeResponse;
  } catch {
    // Network/backend-down — treat as no session rather than crashing the page.
    return null;
  }
}

// --- Overview ---

export type Overview = {
  inventory_health: number;
  active_shipments: number;
  stockout_risk: number;
  delayed_shipments: number;
  supplier_quality: number;
  generated_on: string;
};

// --- Inventory (Phase 2) ---

export type InventoryItem = {
  id: number;
  sku: string;
  product: string;
  warehouse: string;
  on_hand: number;
  safety_stock: number;
  reorder_point: number;
  incoming_qty: number;
  avg_daily_demand?: number;
  days_of_inventory?: number | null;
  stockout_risk?: boolean;
};

// --- Master data (full records, for Add/Delete forms) ---

export type WarehouseRecord = { id: number; code: string; name: string; city: string; region: string };
export type ProductRecord = { id: number; sku: string; name: string; category: string; unit_cost: number; lead_time_days: number };

export type InventoryAnalysisResponse = {
  items: InventoryItem[];
  pagination: { total: number; page: number; page_size: number; total_pages: number };
};

// --- Shipments (Phase 3) ---

export type ShipmentStatus = 'pending' | 'in_transit' | 'delayed' | 'delivered' | 'cancelled';

export type ShipmentItem = {
  id: number;
  shipment_number: string;
  product: string;
  warehouse: string;
  supplier: string;
  quantity: number;
  status: ShipmentStatus;
  eta_date: string;
  actual_delivery_date: string | null;
  delay_days: number;
};

export type ShipmentEvent = {
  id: number;
  event_type: string;
  event_time: string;
  details: string | null;
};

export type ShipmentCreatePayload = {
  product_id: number;
  warehouse_id: number;
  supplier_id: number;
  quantity: number;
  // Give exactly one — the backend turns a lead time into an eta_date.
  eta_date?: string;
  transit_days?: number;
  status?: ShipmentStatus;
};

// --- Suppliers ---

export type Supplier = {
  id: number;
  name: string;
  lead_time_days: number;
  delay_rate: number;
  reliability_score: number;
};

// --- Alerts (Phase 4) ---

export type AlertSeverity = 'INFO' | 'WARNING' | 'CRITICAL';
export type AlertStatus = 'OPEN' | 'ACKNOWLEDGED' | 'RESOLVED';

export type Alert = {
  id: number;
  alert_type: string;
  severity: AlertSeverity;
  title: string;
  description: string;
  related_entity_type: string;
  related_entity_id: number | null;
  related_entity_label: string;
  status: AlertStatus;
  created_at: string;
  updated_at: string;
  resolved_at: string | null;
};

// --- Demand history ---

export type DemandRecord = {
  product: string;
  warehouse: string;
  date: string;
  demand_qty: number;
  is_estimated: boolean;
};

export type QuickEstimateResponse = {
  product: string;
  warehouse: string;
  days_generated: number;
  days_skipped_existing: number;
  start_date: string;
  end_date: string;
  avg_units_per_day: number;
  is_estimated: boolean;
};

// --- Forecasts (Phase 5) ---

export type ForecastSummary = {
  id: number;
  product: string;
  warehouse: string;
  method: 'moving_average' | 'weekday_seasonal';
  horizon_days: number;
  mae: number | null;
  mape: number | null;
  // True when the underlying demand history came from the quick-estimate
  // backfill rather than seeded/recorded data — the UI shows an amber badge
  // so a well-derived guess is never mistaken for a measurement.
  is_estimated?: boolean;
  generated_at: string;
};

export type ForecastPoint = {
  date: string;
  day_offset: number;
  estimated_demand: number;
  lower_bound: number;
  upper_bound: number;
};

export type ForecastDetail = ForecastSummary & {
  methodology: string;
  historical_demand: { date: string; demand_qty: number }[];
  forecast: ForecastPoint[];
};

// --- Replenishment (Phase 6) ---

export type ReplenishmentRecommendation = {
  id: number;
  product: string;
  warehouse: string;
  lead_time_days: number;
  forecast_demand: number;
  safety_stock: number;
  current_stock: number;
  incoming_stock: number;
  recommended_quantity: number;
  explanation: string;
  is_estimated?: boolean;
  generated_at: string;
};

// --- What-If Simulation (Phase 7) ---

export type SimulationParams = {
  demand_change_pct: number;
  lead_time_delta_days: number;
  shipment_delay_delta_days: number;
  safety_stock_change_pct: number;
};

export type SimulationMetrics = {
  stockout_risk_count: number;
  late_shipments_count: number;
  service_level_pct: number;
  inventory_cost: number;
  replenishment_requirement: number;
};

export type SimulationComparison = {
  baseline: SimulationMetrics;
  simulated: SimulationMetrics;
  delta: SimulationMetrics;
};

export type SimulationScenario = SimulationParams & {
  id: number;
  name: string;
  created_at: string;
  baseline: SimulationMetrics | null;
  simulated: SimulationMetrics | null;
};

// --- Auth / Workspace ---

export type AuthUser = { id: number; email: string; display_name: string };
export type Workspace = { id: number; name: string; slug: string; is_demo: boolean };

export type AuthResponse = {
  access_token: string;
  token_type: string;
  user: AuthUser;
  workspace: Workspace;
};

export type MeResponse = { user: AuthUser; workspace: Workspace };
