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

export interface SnapshotMeta {
  id: string;
  label: string;
  saved_at: string;
}

export interface SchwabLoginBegin {
  authorization_url: string;
  callback_url: string;
  state: string;
}

export const schwabApi = {
  beginLogin: () => api.post<SchwabLoginBegin>("/schwab/login/begin", {}),
  completeLogin: (receivedUrl: string, state: string) =>
    api.post<{ ok: boolean }>("/schwab/login/complete", { received_url: receivedUrl, state }),
};

export const tradestewardApi = {
  fetchDay: (tradeDate: string) => api.post<{ job_id: string }>("/tradesteward/fetch-day", { trade_date: tradeDate }),
  backfill: (start: string, end?: string) =>
    api.post<{ job_id: string }>("/tradesteward/backfill", { start, end: end ?? null }),
  fetchPositions: () => api.post<{ job_id: string }>("/tradesteward/positions", {}),
  fetchRisk: () => api.post<{ job_id: string }>("/tradesteward/risk", {}),
  jobStatus: (jobId: string) => api.get<Job>(`/jobs/${jobId}`),
  cancelJob: (jobId: string) => api.post<{ ok: boolean }>(`/jobs/${jobId}/cancel`),
  saveRiskSnapshot: (jobId: string, label: string) =>
    api.post<SnapshotMeta>("/tradesteward/risk/snapshots", { job_id: jobId, label }),
  listRiskSnapshots: () => api.get<SnapshotMeta[]>("/tradesteward/risk/snapshots"),
  loadRiskSnapshot: <T>(snapshotId: string) => api.get<T>(`/tradesteward/risk/snapshots/${snapshotId}`),
  deleteRiskSnapshot: (snapshotId: string) => api.del<{ ok: boolean }>(`/tradesteward/risk/snapshots/${snapshotId}`),
};
