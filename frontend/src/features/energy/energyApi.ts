import { request } from "../../lib/api";

export interface MeterDetail {
  id: string;
  site_id: string;
  meter_type: string;
  vendor?: string | null;
  external_meter_ref?: string | null;
  verification_level: string;
  active: boolean;
}

export interface EnergyAssetDetail {
  id: string;
  site_id: string;
  asset_type: string;
  capacity_kw: string | number;
  status: string;
}

export interface SiteDetailResponse {
  id: string;
  name: string;
  owner_id: string;
  grid_node_id?: string | null;
  latitude?: number | null;
  longitude?: number | null;
  meters: MeterDetail[];
  energy_assets: EnergyAssetDetail[];
}

export interface TelemetryReadingResponse {
  id: string;
  meter_id: string;
  energy_asset_id?: string | null;
  timestamp: string;
  interval_start: string;
  interval_end: string;
  generation_kw: string | number | null;
  load_kw: string | number | null;
  grid_import_kw?: string | number | null;
  grid_export_kw?: string | number | null;
  energy_kwh?: string | number | null;
  battery_soc?: string | number | null;
  quality_status: string;
  source: string;
}

export interface TelemetrySeriesResponse {
  site_id: string;
  start: string;
  end: string;
  resolution_seconds?: number | null;
  count: number;
  readings: TelemetryReadingResponse[];
}

export interface SurplusPoint {
  interval_start: string;
  interval_end: string;
  generation_kw: string | number | null;
  load_kw: string | number | null;
  surplus_kw: string | number | null;
  exportable_kw: string | number;
}

export interface SurplusResponse {
  site_id: string;
  start: string;
  end: string;
  total_exportable_kwh: string | number;
  has_exportable_energy: boolean;
  points: SurplusPoint[];
}

export interface UserResponse {
  id: string;
  display_name: string;
  role: string;
  status: string;
  email?: string | null;
  created_at: string;
  updated_at: string;
}

export interface UserEligibilityResponse {
  user_id: string;
  can_buy: boolean;
  can_sell: boolean;
  can_trade: boolean;
  trust_level: string;
  reasons: string[];
  evaluated_at: string;
}

/**
 * Fetches site and connected equipment registry.
 */
export async function fetchSiteDetail(
  siteId: string,
  userId = "",
  signal?: AbortSignal,
): Promise<SiteDetailResponse> {
  return request<SiteDetailResponse>(`/api/v1/sites/${siteId}`, userId, signal);
}

/**
 * Fetches latest telemetry reading for a site.
 * Retains nullable values (null is never converted to zero).
 */
export async function fetchLatestTelemetry(
  siteId: string,
  userId = "",
  signal?: AbortSignal,
): Promise<TelemetryReadingResponse> {
  return request<TelemetryReadingResponse>(
    `/api/v1/sites/${siteId}/telemetry/latest`,
    userId,
    signal,
  );
}

/**
 * Fetches historical telemetry series for a site.
 */
export async function fetchSiteTelemetrySeries(
  siteId: string,
  userId = "",
  signal?: AbortSignal,
): Promise<TelemetrySeriesResponse> {
  return request<TelemetrySeriesResponse>(
    `/api/v1/sites/${siteId}/telemetry`,
    userId,
    signal,
  );
}

/**
 * Fetches exportable surplus schedule for a site.
 */
export async function fetchSiteSurplus(
  siteId: string,
  userId = "",
  signal?: AbortSignal,
): Promise<SurplusResponse> {
  return request<SurplusResponse>(
    `/api/v1/sites/${siteId}/surplus`,
    userId,
    signal,
  );
}

export interface ForecastPointResponse {
  id: string;
  forecast_run_id: string;
  site_id: string;
  interval_start: string;
  interval_end: string;
  expected_kw: number | string;
  p10_kw?: number | string | null;
  p90_kw?: number | string | null;
  confidence_score?: number | string | null;
}

export interface ForecastSeriesResponse {
  site_id: string;
  start: string;
  end: string;
  count: number;
  points: ForecastPointResponse[];
}

/**
 * Fetches time-series forecast points for a site.
 * Maps to GET /api/v1/sites/{site_id}/forecasts
 */
export async function fetchSiteForecasts(
  siteId: string,
  userId = "",
  signal?: AbortSignal,
): Promise<ForecastSeriesResponse> {
  return request<ForecastSeriesResponse>(
    `/api/v1/sites/${siteId}/forecasts`,
    userId,
    signal,
  );
}

/**
 * Fetches user profile by ID.
 */
export async function fetchUserById(
  userId: string,
  signal?: AbortSignal,
): Promise<UserResponse> {
  return request<UserResponse>(`/api/v1/users/${userId}`, userId, signal);
}

/**
 * Fetches user trading eligibility.
 */
export async function fetchUserEligibility(
  userId: string,
  signal?: AbortSignal,
): Promise<UserEligibilityResponse> {
  return request<UserEligibilityResponse>(
    `/api/v1/users/${userId}/eligibility`,
    userId,
    signal,
  );
}
