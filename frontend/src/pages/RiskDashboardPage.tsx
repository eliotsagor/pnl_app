import { useEffect, useRef, useState } from "react";
import { Alert, Box, Button, CircularProgress, Table, TableBody, TableCell, TableContainer, TableHead, TableRow, Typography } from "@mui/material";
import RefreshIcon from "@mui/icons-material/Refresh";
import { tradestewardApi } from "../api/tradesteward";
import { useJobPolling } from "../hooks/useJobPolling";
import type { StrikeRow, SpxQuote } from "../api/types";
import { COLOR_GOOD, COLOR_CRITICAL } from "../theme";

function fmtMoney(v: number) {
  return `$${Math.round(Math.abs(v)).toLocaleString()}`;
}

function fmtPrice(v: number) {
  return v.toLocaleString(undefined, { minimumFractionDigits: 1, maximumFractionDigits: 1 });
}

interface RiskResult {
  strikes: StrikeRow[];
  quote: SpxQuote;
}

export default function RiskDashboardPage() {
  const [jobId, setJobId] = useState<string | null>(null);
  const [starting, setStarting] = useState(false);
  const [startError, setStartError] = useState<string | null>(null);
  const [data, setData] = useState<RiskResult | null>(null);
  const { job, pollError } = useJobPolling(jobId);
  const notifiedDone = useRef<string | null>(null);

  useEffect(() => {
    if (job?.status === "done" && jobId && notifiedDone.current !== jobId) {
      notifiedDone.current = jobId;
      setData(job.result as RiskResult);
    }
  }, [job?.status, jobId, job?.result]);

  const start = async () => {
    setStarting(true);
    setStartError(null);
    try {
      const { job_id } = await tradestewardApi.fetchRisk();
      setJobId(job_id);
    } catch (e) {
      setStartError((e as Error).message);
    } finally {
      setStarting(false);
    }
  };

  const isActive = job && !["done", "error", "cancelled"].includes(job.status);

  const calls = (data?.strikes ?? []).filter((r) => r.type === "C").sort((a, b) => a.strike - b.strike);
  const puts = (data?.strikes ?? []).filter((r) => r.type === "P").sort((a, b) => b.strike - a.strike);

  const sum = (rows: StrikeRow[], key: "capture" | "at_risk") => rows.reduce((s, r) => s + r[key], 0);

  const quote = data?.quote;
  const hasQuote = quote && quote.price != null;
  const changeColor = quote?.change != null ? (quote.change >= 0 ? COLOR_GOOD : COLOR_CRITICAL) : "text.secondary";

  return (
    <Box sx={{ maxWidth: 1200, mx: "auto", px: 3, pb: 4 }}>
      <Box sx={{ display: "flex", alignItems: "baseline", gap: 2, mb: 2 }}>
        <Typography variant="h5" sx={{ fontWeight: 700 }}>
          {hasQuote ? `SPX ${fmtPrice(quote!.price!)}` : "SPX —"}
        </Typography>
        {quote?.change != null && (
          <Typography variant="h6" sx={{ color: changeColor, fontWeight: 600 }}>
            {quote.change >= 0 ? "+" : ""}
            {quote.change.toFixed(1)}
          </Typography>
        )}
        <Button
          variant="contained"
          size="small"
          startIcon={<RefreshIcon />}
          onClick={start}
          disabled={starting || !!isActive}
          sx={{ ml: "auto" }}
        >
          {starting ? "Starting…" : data ? "Refresh" : "Load positions"}
        </Button>
      </Box>

      {startError && (
        <Alert severity="error" sx={{ mb: 2 }}>
          {startError}
        </Alert>
      )}
      {pollError && (
        <Alert severity="error" sx={{ mb: 2 }}>
          {pollError}
        </Alert>
      )}
      {job?.status === "awaiting_login" && (
        <Alert severity="info" icon={<CircularProgress size={18} />} sx={{ mb: 2 }}>
          A TradeSteward sign-in window opened on your desktop — if a Windows Security passkey prompt appears, click
          Cancel on it. Login then completes automatically. Waiting…
        </Alert>
      )}
      {job?.status === "running" && (
        <Box sx={{ display: "flex", alignItems: "center", gap: 1, mb: 2 }}>
          <CircularProgress size={18} />
          <Typography variant="body2">Fetching open positions…</Typography>
        </Box>
      )}
      {job?.status === "error" && (
        <Alert severity="error" sx={{ mb: 2 }}>
          {job.error}
        </Alert>
      )}
      {data && !hasQuote && (
        <Alert severity="warning" sx={{ mb: 2 }}>
          Couldn't load a live SPX quote — showing positions without spot price context.
        </Alert>
      )}

      {data && calls.length === 0 && puts.length === 0 && (
        <Typography color="text.secondary">No short options open right now.</Typography>
      )}

      {data && (calls.length > 0 || puts.length > 0) && (
        <TableContainer sx={{ border: "1px solid rgba(255,255,255,0.10)", borderRadius: "12px" }}>
          <Table size="small">
            <TableHead>
              <TableRow sx={{ bgcolor: "background.paper" }}>
                <TableCell sx={{ fontWeight: 600 }}>Strike</TableCell>
                <TableCell align="right" sx={{ fontWeight: 600 }}>
                  Qty
                </TableCell>
                <TableCell align="right" sx={{ fontWeight: 600 }}>
                  Capture
                </TableCell>
                <TableCell align="right" sx={{ fontWeight: 600 }}>
                  At risk
                </TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {calls.map((r) => (
                <TableRow key={`C${r.strike}`} hover>
                  <TableCell sx={{ fontVariantNumeric: "tabular-nums" }}>{r.strike.toLocaleString()} C</TableCell>
                  <TableCell align="right" sx={{ fontVariantNumeric: "tabular-nums" }}>
                    {r.qty}
                  </TableCell>
                  <TableCell align="right" sx={{ color: COLOR_GOOD, fontVariantNumeric: "tabular-nums" }}>
                    {fmtMoney(r.capture)}
                  </TableCell>
                  <TableCell align="right" sx={{ color: COLOR_CRITICAL, fontVariantNumeric: "tabular-nums" }}>
                    {fmtMoney(r.at_risk)}
                  </TableCell>
                </TableRow>
              ))}

              {hasQuote && (
                <TableRow>
                  <TableCell
                    colSpan={4}
                    align="center"
                    sx={{ color: "text.secondary", borderTop: "1px dashed rgba(255,255,255,0.2)", borderBottom: "1px dashed rgba(255,255,255,0.2)", py: 0.5 }}
                  >
                    — spot {fmtPrice(quote!.price!)} —
                  </TableCell>
                </TableRow>
              )}

              {puts.map((r) => (
                <TableRow key={`P${r.strike}`} hover>
                  <TableCell sx={{ fontVariantNumeric: "tabular-nums" }}>{r.strike.toLocaleString()} P</TableCell>
                  <TableCell align="right" sx={{ fontVariantNumeric: "tabular-nums" }}>
                    {r.qty}
                  </TableCell>
                  <TableCell align="right" sx={{ color: COLOR_GOOD, fontVariantNumeric: "tabular-nums" }}>
                    {fmtMoney(r.capture)}
                  </TableCell>
                  <TableCell align="right" sx={{ color: COLOR_CRITICAL, fontVariantNumeric: "tabular-nums" }}>
                    {fmtMoney(r.at_risk)}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </TableContainer>
      )}

      {data && (calls.length > 0 || puts.length > 0) && (
        <Box sx={{ display: "flex", gap: 2, mt: 2 }}>
          <Box sx={{ flex: 1, p: 2, borderRadius: "12px", border: "1px solid rgba(255,255,255,0.10)" }}>
            <Typography variant="subtitle2" sx={{ mb: 1 }}>
              Call side
            </Typography>
            <Box sx={{ display: "flex", justifyContent: "space-between" }}>
              <Typography variant="body2" color="text.secondary">
                capture
              </Typography>
              <Typography variant="body2" sx={{ color: COLOR_GOOD }}>
                {fmtMoney(sum(calls, "capture"))}
              </Typography>
            </Box>
            <Box sx={{ display: "flex", justifyContent: "space-between" }}>
              <Typography variant="body2" color="text.secondary">
                at risk
              </Typography>
              <Typography variant="body2" sx={{ color: COLOR_CRITICAL }}>
                {fmtMoney(sum(calls, "at_risk"))}
              </Typography>
            </Box>
          </Box>
          <Box sx={{ flex: 1, p: 2, borderRadius: "12px", border: `1px solid ${COLOR_CRITICAL}55`, bgcolor: `${COLOR_CRITICAL}14` }}>
            <Typography variant="subtitle2" sx={{ mb: 1 }}>
              Put side
            </Typography>
            <Box sx={{ display: "flex", justifyContent: "space-between" }}>
              <Typography variant="body2" color="text.secondary">
                capture
              </Typography>
              <Typography variant="body2" sx={{ color: COLOR_GOOD }}>
                {fmtMoney(sum(puts, "capture"))}
              </Typography>
            </Box>
            <Box sx={{ display: "flex", justifyContent: "space-between" }}>
              <Typography variant="body2" color="text.secondary">
                at risk
              </Typography>
              <Typography variant="body2" sx={{ color: COLOR_CRITICAL }}>
                {fmtMoney(sum(puts, "at_risk"))}
              </Typography>
            </Box>
          </Box>
        </Box>
      )}
    </Box>
  );
}
