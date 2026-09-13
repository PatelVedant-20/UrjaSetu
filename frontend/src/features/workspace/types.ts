export type Row = { id: string; [field: string]: unknown };
export interface WorkspaceData {
  user: { id: string; name: string; email: string; role: string };
  simulation: {
    clock: string;
    running: boolean;
    scenario: string;
    revision: number;
    source: string;
    model_version: string;
    weather: {
      status?: string;
      current?: Record<string, number | string>;
      fetched_at?: string;
      note?: string;
    };
  };
  sites: Row[];
  readings: Row[];
  forecasts: Row[];
  orders: Row[];
  order_book: Row[];
  trades: Row[];
  prices: Row[];
  market_prices: Row[];
  grid: Row[];
  grid_series: Row[];
  nodes: Row[];
  settlements: Row[];
  receipts: Row[];
  reconciliations: Row[];
  audit: Row[];
  journal: Row[];
  community: { id: string; name: string; role: string }[];
  portfolio: {
    earned_inr: string;
    spent_inr: string;
    traded_kwh: string;
    money_mode: string;
  };
}

export type Period = "hour" | "day" | "week" | "month";
export type Metrics = Record<string, number>;
export interface Setup {
  city: string;
  home_type: string;
  occupants: number;
  monthly_kwh: number;
  ac_count: number;
  has_ev: boolean;
  daytime_home: boolean;
  orientation: string;
  tilt: number;
  retail_rate: number;
  share_stats: boolean;
  avatar: string | null;
  photo: string | null;
}
export interface Member {
  id: string;
  name: string;
  role: string;
  avatar: string | null;
  photo: string | null;
  city: string;
  home_type: string;
  capacity_kw: number;
  node_id: string | null;
  joined_at: string | null;
  sharing: boolean;
  periods: Record<Period, Metrics> | null;
  daily: Daily[];
  live: Metrics | null;
}
export type Daily = { date: string } & Record<string, string | number>;
export interface Experience extends WorkspaceData {
  as_of: string;
  refresh_seconds: number;
  profile: Setup;
  members: Member[];
  periods: Record<Period, Metrics>;
  daily: Daily[];
  live: Metrics | null;
  data_connection: {
    kind: string;
    meter_connected: boolean;
    model_version: string;
  };
}
export type Perform = (
  path: string,
  body: unknown,
  message?: string,
  method?: string,
) => Promise<boolean>;
