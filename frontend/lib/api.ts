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

// --- Forecasts (Phase 5) ---

export type ForecastSummary = {
  id: number;
  product: string;
  warehouse: string;
  method: 'moving_average' | 'weekday_seasonal';
  horizon_days: number;
  mae: number | null;
  mape: number | null;
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
