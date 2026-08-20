export interface Strategy {
  id: number;
  sheet_name: string;
  display_order: number;
  include_in_total: number;
  include_in_all_bics: number;
}

export interface Mapping {
  screenshot_label: string;
  sheet_name: string;
  strategy_id: number;
}

export type CalendarMonth = Record<string, number>; // day-of-month (string) -> total
export type DayDetail = Record<string, number>; // sheet_name -> value

export interface YearView {
  sheets: string[];
  matrix: Record<string, Record<string, number>>; // sheet_name -> {month(1-12 as string): total}
}

export interface StrategyYearView {
  days: Record<string, Record<string, number>>; // day(1-31 as string) -> {month(1-12 as string): value}
  weekday: Record<string, { total: number; count: number }>; // weekday(0=Mon..6=Sun as string) -> totals
}

export interface StrikeRow {
  type: "C" | "P";
  strike: number;
  qty: number;
  captured: number;
  remaining: number;
  at_risk: number;
  positions: number;
  stop_probability?: number; // 0-1, probability this strike's stop triggers before close; absent if unknown
  at_risk_in_em?: number; // at_risk * stop_probability -- the portion of max loss realistically in play today
  is_bic: boolean;
  is_elmo: boolean;
}

export interface SpxQuote {
  price?: number;
  change?: number | null;
  change_pct?: number | null;
}

export interface ExpectedMove {
  spot?: number;
  atm_strike?: number;
  straddle_mid?: number;
  expected_move?: number;
}

export interface Position {
  serial: number;
  strategy: string;
  bot_name: string;
  account: string;
  symbol: string;
  open_time: string;
  days_in_trade: number | null;
  legs: string[];
  stop_target: string;
  profit_target: string;
  open_price: string; // HTML string, e.g. "Open:&#10;$1.30 Credit<p...>Current:&#10;$1.73 Debit"
  profit_pct: string;
  profit_pct_style: "profit" | "loss" | "";
  profit_dollars: string;
  profit_dollars_style: "profit" | "loss" | "";
  max_profit: string;
  max_loss: string;
  stop_probability?: number; // 0-1, probability this position's stop triggers before close
  ev?: number; // expected value of continuing to hold, $
  delta?: number; // this position's own net delta (short + long legs), underlying-equivalent shares
  gamma?: number; // this position's own net gamma
  is_bic: boolean;
  is_elmo: boolean;
}

export interface NetGreeks {
  net_delta?: number;
  net_gamma?: number;
  delta_at_minus_10?: number;
  delta_at_plus_10?: number;
}
