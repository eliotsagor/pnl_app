import { api } from "./client";
import type { CalendarMonth, DayDetail, StrategyYearView, YearView } from "./types";

export const calendarApi = {
  month: (year: number, month: number) => api.get<CalendarMonth>(`/calendar/${year}/${month}`),
  day: (isoDate: string) => api.get<DayDetail>(`/day/${isoDate}`),
  deleteDay: (isoDate: string) => api.del<{ ok: boolean }>(`/day/${isoDate}`),
  years: () => api.get<number[]>("/years"),
  datesWithData: () => api.get<string[]>("/dates-with-data"),
  yearView: (year: number) => api.get<YearView>(`/year/${year}`),
  strategyYearView: (year: number, sheetName: string) =>
    api.get<StrategyYearView>(`/strategy-year/${year}/${encodeURIComponent(sheetName)}`),
  totalYearView: (year: number) => api.get<StrategyYearView>(`/total-year/${year}`),
  allBicsYearView: (year: number) => api.get<StrategyYearView>(`/all-bics-year/${year}`),
};
