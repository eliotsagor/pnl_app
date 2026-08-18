import { useEffect, useRef, useState } from "react";
import { Alert, Box, Button, CircularProgress, List, ListItem, Typography } from "@mui/material";
import LinkIcon from "@mui/icons-material/Link";
import { tradestewardApi } from "../api/tradesteward";
import { useJobPolling } from "../hooks/useJobPolling";

interface Props {
  mode: "fetch-day" | "backfill";
  tradeDate?: string; // for fetch-day
  backfillStart?: string; // for backfill
  backfillEnd?: string;
  buttonLabel: string;
  onDone?: (result: any) => void;
}

export default function TradeStewardJobPanel({
  mode,
  tradeDate,
  backfillStart,
  backfillEnd,
  buttonLabel,
  onDone,
}: Props) {
  const [jobId, setJobId] = useState<string | null>(null);
  const [starting, setStarting] = useState(false);
  const [startError, setStartError] = useState<string | null>(null);
  const { job, pollError } = useJobPolling(jobId);
  const notifiedDone = useRef<string | null>(null);

  useEffect(() => {
    if (job?.status === "done" && jobId && notifiedDone.current !== jobId) {
      notifiedDone.current = jobId;
      onDone?.(job.result);
    }
  }, [job?.status, jobId, onDone]);

  const start = async () => {
    setStarting(true);
    setStartError(null);
    try {
      const { job_id } =
        mode === "fetch-day"
          ? await tradestewardApi.fetchDay(tradeDate!)
          : await tradestewardApi.backfill(backfillStart!, backfillEnd);
      setJobId(job_id);
    } catch (e) {
      setStartError((e as Error).message);
    } finally {
      setStarting(false);
    }
  };

  const isActive = job && !["done", "error", "cancelled"].includes(job.status);

  return (
    <Box>
      {!isActive && (
        <Button variant="contained" startIcon={<LinkIcon />} onClick={start} disabled={starting}>
          {starting ? "Starting…" : buttonLabel}
        </Button>
      )}

      {startError && (
        <Alert severity="error" sx={{ mt: 2 }}>
          {startError}
        </Alert>
      )}
      {pollError && (
        <Alert severity="error" sx={{ mt: 2 }}>
          {pollError}
        </Alert>
      )}

      {job?.status === "awaiting_login" && (
        <Alert severity="info" icon={<CircularProgress size={18} />} sx={{ mt: 2 }}>
          A TradeSteward sign-in window opened on your desktop — if a Windows Security passkey prompt appears, click
          Cancel on it. Login then completes automatically. Waiting…
        </Alert>
      )}

      {job?.status === "running" && (
        <Box sx={{ mt: 2 }}>
          <Box sx={{ display: "flex", alignItems: "center", gap: 1, mb: 1 }}>
            <CircularProgress size={18} />
            <Typography variant="body2">
              {mode === "backfill" && job.progress?.last_day
                ? `Processing… last: ${job.progress.last_day} (${job.progress.days_done ?? 0} done)`
                : "Fetching…"}
            </Typography>
          </Box>
          {job.log.length > 0 && (
            <List dense sx={{ maxHeight: 240, overflow: "auto", bgcolor: "background.paper", borderRadius: 1 }}>
              {job.log.map((line, i) => (
                <ListItem key={i} sx={{ py: 0 }}>
                  <Typography variant="caption" sx={{ fontFamily: "monospace" }}>
                    {line}
                  </Typography>
                </ListItem>
              ))}
            </List>
          )}
        </Box>
      )}

      {job?.status === "error" && (
        <Box sx={{ mt: 2 }}>
          <Alert severity="error">{job.error}</Alert>
          <Button
            sx={{ mt: 1 }}
            onClick={() => {
              setJobId(null);
            }}
          >
            Retry
          </Button>
        </Box>
      )}

      {job?.status === "done" && mode === "backfill" && job.result != null && (
        <Box sx={{ mt: 2 }}>
          {(() => {
            const r = job.result as { saved_days: number; empty_days: number; new_sheets: string[] };
            return (
              <>
                <Alert severity="success">
                  Saved {r.saved_days} days, skipped {r.empty_days} empty/holiday days.
                </Alert>
                {r.new_sheets?.length > 0 && (
                  <Alert severity="warning" sx={{ mt: 1 }}>
                    New sheet(s) auto-created for never-seen labels — add a matching tab to template.xlsx before
                    exporting these:
                    {r.new_sheets.map((s) => (
                      <Typography key={s} variant="body2">
                        • {s}
                      </Typography>
                    ))}
                  </Alert>
                )}
              </>
            );
          })()}
          <Button sx={{ mt: 1 }} onClick={() => setJobId(null)}>
            Run another backfill
          </Button>
        </Box>
      )}
    </Box>
  );
}
