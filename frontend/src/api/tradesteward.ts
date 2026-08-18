import { api } from "./client";

export type JobStatus = "queued" | "awaiting_login" | "running" | "done" | "error" | "cancelled";

export interface Job {
  id: string;
  kind: string;
  status: JobStatus;
  progress: Record<string, unknown>;
  log: string[];
  result: unknown;
  error: string | null;
}

export const tradestewardApi = {
  fetchDay: (tradeDate: string) => api.post<{ job_id: string }>("/tradesteward/fetch-day", { trade_date: tradeDate }),
  backfill: (start: string, end?: string) =>
    api.post<{ job_id: string }>("/tradesteward/backfill", { start, end: end ?? null }),
  fetchPositions: () => api.post<{ job_id: string }>("/tradesteward/positions", {}),
  fetchRisk: () => api.post<{ job_id: string }>("/tradesteward/risk", {}),
  jobStatus: (jobId: string) => api.get<Job>(`/jobs/${jobId}`),
  cancelJob: (jobId: string) => api.post<{ ok: boolean }>(`/jobs/${jobId}/cancel`),
};
