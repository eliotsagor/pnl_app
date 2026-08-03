import { api } from "./client";
import type { Mapping } from "./types";

export const mappingsApi = {
  list: () => api.get<Mapping[]>("/mappings"),
  add: (label: string, sheetName: string) =>
    api.post<{ ok: boolean }>("/mappings", { label, sheet_name: sheetName }),
};
