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
  ev?: number; // expected value of continuing to hold this strike's share, $ -- (1-stop_probability)*remaining - stop_probability*at_risk
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
  at_risk?: number; // $ given back from today's value if the stop triggers -- see position_give_back
  remaining?: number; // $ still on the table if this decays to worthless by expiry -- see position_remaining_value
  side_split?: { C?: number; P?: number }; // for a two-sided position, each side's share (0-1) of captured/remaining/at_risk -- see position_side_split_weights
  stop_probability?: number; // 0-1, probability this position's stop triggers before close (max across sides for a two-sided position)
  stop_probability_by_side?: { C?: number; P?: number }; // 0-1, each side's OWN probability -- use this (not stop_probability) when attributing risk to one side's strike, since an independently-stopped two-sided position's sides can differ a lot
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
