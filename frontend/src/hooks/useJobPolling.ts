import { useEffect, useRef, useState } from "react";
import { tradestewardApi, type Job } from "../api/tradesteward";

const TERMINAL: Job["status"][] = ["done", "error", "cancelled"];

export function useJobPolling(jobId: string | null, intervalMs = 1500) {
  const [job, setJob] = useState<Job | null>(null);
  const [pollError, setPollError] = useState<string | null>(null);
  const timerRef = useRef<number | null>(null);

  useEffect(() => {
    if (!jobId) {
      setJob(null);
      return;
    }

    let cancelled = false;
    const poll = async () => {
      try {
        const j = await tradestewardApi.jobStatus(jobId);
        if (cancelled) return;
        setJob(j);
        if (!TERMINAL.includes(j.status)) {
          timerRef.current = window.setTimeout(poll, intervalMs);
        }
      } catch (e) {
        if (!cancelled) setPollError((e as Error).message);
      }
    };
    poll();

    return () => {
      cancelled = true;
      if (timerRef.current) window.clearTimeout(timerRef.current);
    };
  }, [jobId, intervalMs]);

  return { job, pollError };
}
