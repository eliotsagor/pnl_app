import { useEffect, useRef, useState } from "react";
import { Alert, Box, Button, CircularProgress, Table, TableBody, TableCell, TableContainer, TableHead, TableRow, Typography } from "@mui/material";
import RefreshIcon from "@mui/icons-material/Refresh";
import { tradestewardApi } from "../api/tradesteward";
import { useJobPolling } from "../hooks/useJobPolling";
import type { StrikeRow, SpxQuote, ExpectedMove } from "../api/types";
import { COLOR_GOOD, COLOR_CRITICAL, COLOR_WARNING } from "../theme";

function fmtMoney(v: number) {
  return `$${Math.round(Math.abs(v)).toLocaleString()}`;
}

function fmtPrice(v: number) {
  return v.toLocaleString(undefined, { minimumFractionDigits: 1, maximumFractionDigits: 1 });
}

function fmtDistance(strike: number, spot: number) {
  const pts = strike - spot;
  const pct = (pts / spot) * 100;
  const sign = pts >= 0 ? "+" : "";
  return `${sign}${pts.toFixed(1)} (${sign}${pct.toFixed(1)}%)`;
}

// Closer to spot = more gamma risk = red; comfortably away = green.
function bandTint(strike: number, spot: number): string {
  const absPct = Math.abs((strike - spot) / spot) * 100;
  if (absPct < 0.3) return `${COLOR_CRITICAL}1f`;
  if (absPct < 0.7) return `${COLOR_WARNING}1f`;
  return `${COLOR_GOOD}1f`;
}

function stopProbColor(p: number | undefined): string {
  if (p == null) return "text.secondary";
  if (p >= 0.5) return COLOR_CRITICAL;
  if (p >= 0.2) return COLOR_WARNING;
  return COLOR_GOOD;
}

interface RiskResult {
  strikes: StrikeRow[];
  quote: SpxQuote;
  expected_move: ExpectedMove;
}

// A dashed marker row inserted at the point in a sorted-by-strike list where
// a boundary price falls -- same idea as the spot divider, generalized so it
// can also mark the expected-move-up / expected-move-down levels.
function EmMarker({ label, color = COLOR_WARNING }: { label: string; color?: string }) {
  return (
    <TableRow>
      <TableCell
        colSpan={7}
        align="center"
        sx={{
          color,
          borderTop: `1px dotted ${color}`,
          borderBottom: `1px dotted ${color}`,
          py: 0.5,
          fontSize: "0.75rem",
        }}
      >
        {label}
      </TableCell>
    </TableRow>
  );
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

  // Closest-to-spot strikes sit nearest the spot divider on both sides:
  // calls descend toward it from above, puts descend away from it below.
  const calls = (data?.strikes ?? []).filter((r) => r.type === "C").sort((a, b) => b.strike - a.strike);
  const puts = (data?.strikes ?? []).filter((r) => r.type === "P").sort((a, b) => b.strike - a.strike);

  const sum = (rows: StrikeRow[], key: "captured" | "remaining" | "at_risk") => rows.reduce((s, r) => s + r[key], 0);

  const quote = data?.quote;
  const hasQuote = quote && quote.price != null;
  const changeColor = quote?.change != null ? (quote.change >= 0 ? COLOR_GOOD : COLOR_CRITICAL) : "text.secondary";

  const em = data?.expected_move;
  const hasEm = hasQuote && em?.expected_move != null;
  const emUp = hasEm ? quote!.price! + em!.expected_move! : null;
  const emDown = hasEm ? quote!.price! - em!.expected_move! : null;

  // Insert an EM marker into a strike list (already sorted furthest-to-closest
  // relative to spot) right before the first row whose strike has crossed
  // past the boundary, i.e. is now within the expected move.
  function withEmMarker(rows: StrikeRow[], boundary: number | null, side: "up" | "down") {
    if (boundary == null) return rows.map((r) => ({ kind: "row" as const, row: r }));
    const out: ({ kind: "row"; row: StrikeRow } | { kind: "marker" })[] = [];
    let inserted = false;
    for (const r of rows) {
      const crossed = side === "up" ? r.strike <= boundary : r.strike >= boundary;
      if (crossed && !inserted) {
        out.push({ kind: "marker" });
        inserted = true;
      }
      out.push({ kind: "row", row: r });
    }
    if (!inserted) out.push({ kind: "marker" });
    return out;
  }

  const callItems = withEmMarker(calls, emUp, "up");
  const putItems = withEmMarker(puts, emDown, "down");

  const renderRow = (r: StrikeRow) => (
    <TableRow
      key={`${r.type}${r.strike}`}
      hover
      sx={{ bgcolor: hasQuote ? bandTint(r.strike, quote!.price!) : undefined }}
    >
      <TableCell sx={{ fontVariantNumeric: "tabular-nums" }}>
        {r.strike.toLocaleString()} {r.type}
      </TableCell>
      <TableCell align="right" sx={{ fontVariantNumeric: "tabular-nums", color: "text.secondary" }}>
        {hasQuote ? fmtDistance(r.strike, quote!.price!) : "—"}
      </TableCell>
      <TableCell align="right" sx={{ fontVariantNumeric: "tabular-nums", color: stopProbColor(r.stop_probability) }}>
        {r.stop_probability != null ? `${Math.round(r.stop_probability * 100)}%` : "—"}
      </TableCell>
      <TableCell align="right" sx={{ fontVariantNumeric: "tabular-nums" }}>
        {r.qty}
      </TableCell>
      <TableCell align="right" sx={{ color: "text.secondary", fontVariantNumeric: "tabular-nums" }}>
        {fmtMoney(r.captured)}
      </TableCell>
      <TableCell align="right" sx={{ color: COLOR_GOOD, fontVariantNumeric: "tabular-nums" }}>
        {fmtMoney(r.remaining)}
      </TableCell>
      <TableCell align="right" sx={{ color: COLOR_CRITICAL, fontVariantNumeric: "tabular-nums" }}>
        {fmtMoney(r.at_risk)}
      </TableCell>
    </TableRow>
  );

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
        {hasEm && (
          <Typography variant="body2" sx={{ color: COLOR_WARNING }}>
            EM ±{em!.expected_move!.toFixed(1)} ({fmtPrice(emDown!)} – {fmtPrice(emUp!)})
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
                  Distance
                </TableCell>
                <TableCell align="right" sx={{ fontWeight: 600 }}>
                  Stop%
                </TableCell>
                <TableCell align="right" sx={{ fontWeight: 600 }}>
                  Qty
                </TableCell>
                <TableCell align="right" sx={{ fontWeight: 600 }}>
                  Captured
                </TableCell>
                <TableCell align="right" sx={{ fontWeight: 600 }}>
                  Remaining
                </TableCell>
                <TableCell align="right" sx={{ fontWeight: 600 }}>
                  At risk
                </TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {callItems.map((item, i) =>
                item.kind === "row" ? (
                  renderRow(item.row)
                ) : (
                  <EmMarker key={`em-up-${i}`} label={`···· expected move up ${fmtPrice(emUp!)} ····`} />
                )
              )}

              {hasQuote && (
                <TableRow>
                  <TableCell
                    colSpan={7}
                    align="center"
                    sx={{
                      color: "text.secondary",
                      borderTop: "1px dashed rgba(255,255,255,0.2)",
                      borderBottom: "1px dashed rgba(255,255,255,0.2)",
                      py: 0.5,
                    }}
                  >
                    — spot {fmtPrice(quote!.price!)} —
                  </TableCell>
                </TableRow>
              )}

              {putItems.map((item, i) =>
                item.kind === "row" ? (
                  renderRow(item.row)
                ) : (
                  <EmMarker key={`em-down-${i}`} label={`···· expected move down ${fmtPrice(emDown!)} ····`} />
                )
              )}
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
                captured
              </Typography>
              <Typography variant="body2" color="text.secondary">
                {fmtMoney(sum(calls, "captured"))}
              </Typography>
            </Box>
            <Box sx={{ display: "flex", justifyContent: "space-between" }}>
              <Typography variant="body2" color="text.secondary">
                remaining
              </Typography>
              <Typography variant="body2" sx={{ color: COLOR_GOOD }}>
                {fmtMoney(sum(calls, "remaining"))}
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
                captured
              </Typography>
              <Typography variant="body2" color="text.secondary">
                {fmtMoney(sum(puts, "captured"))}
              </Typography>
            </Box>
            <Box sx={{ display: "flex", justifyContent: "space-between" }}>
              <Typography variant="body2" color="text.secondary">
                remaining
              </Typography>
              <Typography variant="body2" sx={{ color: COLOR_GOOD }}>
                {fmtMoney(sum(puts, "remaining"))}
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
