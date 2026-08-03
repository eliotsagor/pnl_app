import { api } from "./client";
import type { DayDetail, Strategy } from "./types";

export const daysApi = {
  strategies: () => api.get<Strategy[]>("/strategies"),
  get: (isoDate: string) => api.get<DayDetail>(`/day/${isoDate}`),
  save: (isoDate: string, sheetValues: Record<string, number>) =>
    api.post<{ ok: boolean }>(`/day/${isoDate}`, { sheet_values: sheetValues }),
  addToStrategy: (isoDate: string, sheetName: string, amount: number) =>
    api.post<{ sheet_name: string; new_total: number; day_total: number }>(`/day/${isoDate}/add-to-strategy`, {
      sheet_name: sheetName,
      amount,
    }),
};
