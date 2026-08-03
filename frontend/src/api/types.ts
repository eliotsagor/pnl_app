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
