import { useCallback, useEffect, useRef, useState } from "react";
import { useJobPolling } from "./useJobPolling";

const DEFAULT_INTERVAL_MS = 30_000;

/** Starts a TradeSteward job immediately on mount, then re-starts it every
 * `intervalMs` after each completion (not a fixed clock -- avoids piling up
 * overlapping jobs if one run takes longer than the interval). The last
 * successful result stays visible across refreshes instead of being
 * cleared while the next job runs, so the page doesn't flash to a loading
 * state every cycle -- only the first load shows the full "starting up"
 * UI. Auth prompts (a signed-out TradeSteward session) still surface via
 * `job`, since those need a human either way.
 */
export function useAutoRefreshJob<T>(
  startJob: () => Promise<{ job_id: string }>,
  intervalMs = DEFAULT_INTERVAL_MS
) {
  const [jobId, setJobId] = useState<string | null>(null);
  const [data, setData] = useState<T | null>(null);
  const [startError, setStartError] = useState<string | null>(null);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);
  const { job, pollError } = useJobPolling(jobId);
  const notifiedDone = useRef<string | null>(null);
  const timerRef = useRef<number | null>(null);
  const startJobRef = useRef(startJob);
  startJobRef.current = startJob;

  const start = useCallback(async () => {
    setStartError(null);
    try {
      const { job_id } = await startJobRef.current();
      setJobId(job_id);
    } catch (e) {
      setStartError((e as Error).message);
    }
  }, []);

  // Kick off the first load on mount.
  useEffect(() => {
    start();
    return () => {
      if (timerRef.current) window.clearTimeout(timerRef.current);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // On each completion, capture the result (keeping stale data visible on
  // error/cancel rather than clearing it) and schedule the next run.
  useEffect(() => {
    if (job?.status === "done" && jobId && notifiedDone.current !== jobId) {
      notifiedDone.current = jobId;
      setData(job.result as T);
      setLastUpdated(new Date());
      timerRef.current = window.setTimeout(start, intervalMs);
    } else if ((job?.status === "error" || job?.status === "cancelled") && jobId && notifiedDone.current !== jobId) {
      notifiedDone.current = jobId;
      timerRef.current = window.setTimeout(start, intervalMs);
    }
  }, [job?.status, jobId, job?.result, intervalMs, start]);

  const isActive = job != null && !["done", "error", "cancelled"].includes(job.status);

  return { job, data, startError, pollError, isActive, lastUpdated, refreshNow: start };
}
