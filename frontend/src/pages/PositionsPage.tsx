import { useEffect, useRef, useState } from "react";
import {
  Alert,
  Box,
  Button,
  Chip,
  CircularProgress,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Typography,
} from "@mui/material";
import RefreshIcon from "@mui/icons-material/Refresh";
import { tradestewardApi } from "../api/tradesteward";
import { useJobPolling } from "../hooks/useJobPolling";
import type { Position } from "../api/types";
import { COLOR_GOOD, COLOR_CRITICAL } from "../theme";

function styleColor(style: string) {
  if (style === "profit") return COLOR_GOOD;
  if (style === "loss") return COLOR_CRITICAL;
  return "text.primary";
}

// openPrice comes as an HTML fragment ("Open:&#10;$1.30 Credit<p ...>Current:&#10;$1.73 Debit").
// Split into plain-text lines for display without dumping raw HTML into the DOM.
function openPriceLines(html: string): string[] {
  const text = html
    .replace(/<[^>]+>/g, " ")
    .replace(/&#10;/g, " ")
    .replace(/&nbsp;/g, " ")
    .replace(/\s+/g, " ")
    .trim();
  return text.split(/(?=Current:)/).map((s) => s.trim());
}

export default function PositionsPage() {
  const [jobId, setJobId] = useState<string | null>(null);
  const [starting, setStarting] = useState(false);
  const [startError, setStartError] = useState<string | null>(null);
  const [positions, setPositions] = useState<Position[] | null>(null);
  const { job, pollError } = useJobPolling(jobId);
  const notifiedDone = useRef<string | null>(null);

  useEffect(() => {
    if (job?.status === "done" && jobId && notifiedDone.current !== jobId) {
      notifiedDone.current = jobId;
      const result = job.result as { positions: Position[] } | null;
      setPositions(result?.positions ?? []);
    }
  }, [job?.status, jobId, job?.result]);

  const start = async () => {
    setStarting(true);
    setStartError(null);
    try {
      const { job_id } = await tradestewardApi.fetchPositions();
      setJobId(job_id);
    } catch (e) {
      setStartError((e as Error).message);
    } finally {
      setStarting(false);
    }
  };

  const isActive = job && !["done", "error", "cancelled"].includes(job.status);

  return (
    <Box sx={{ maxWidth: 1600, mx: "auto", px: 3, pb: 4 }}>
      <Box sx={{ display: "flex", alignItems: "center", gap: 2, mb: 2 }}>
        <Typography variant="h6">Current Bot Positions</Typography>
        <Button
          variant="contained"
          size="small"
          startIcon={<RefreshIcon />}
          onClick={start}
          disabled={starting || !!isActive}
        >
          {starting ? "Starting…" : positions ? "Refresh" : "Load positions"}
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

      {positions && positions.length === 0 && (
        <Typography color="text.secondary">No open positions right now.</Typography>
      )}

      {positions && positions.length > 0 && (
        <TableContainer sx={{ border: "1px solid rgba(255,255,255,0.10)", borderRadius: "12px" }}>
          <Table size="small">
            <TableHead>
              <TableRow sx={{ bgcolor: "background.paper" }}>
                <TableCell sx={{ fontWeight: 600 }}>Open Time</TableCell>
                <TableCell sx={{ fontWeight: 600 }}>Bot</TableCell>
                <TableCell sx={{ fontWeight: 600 }}>Symbol</TableCell>
                <TableCell sx={{ fontWeight: 600 }}>Account</TableCell>
                <TableCell sx={{ fontWeight: 600 }}>Position</TableCell>
                <TableCell sx={{ fontWeight: 600 }}>Stop Target</TableCell>
                <TableCell sx={{ fontWeight: 600 }}>Profit Target</TableCell>
                <TableCell sx={{ fontWeight: 600 }}>Open / Current</TableCell>
                <TableCell align="right" sx={{ fontWeight: 600 }}>
                  Profit %
                </TableCell>
                <TableCell align="right" sx={{ fontWeight: 600 }}>
                  Profit $
                </TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {positions.map((p) => (
                <TableRow key={p.serial} hover>
                  <TableCell sx={{ whiteSpace: "nowrap" }}>
                    <Typography variant="body2">{p.open_time}</Typography>
                    {p.days_in_trade != null && (
                      <Chip
                        size="small"
                        label={`${p.days_in_trade} Days In Trade`}
                        sx={{ mt: 0.5, height: 18, fontSize: "0.65rem" }}
                      />
                    )}
                  </TableCell>
                  <TableCell>
                    <Typography variant="body2">{p.strategy}</Typography>
                    <Typography variant="caption" color="text.secondary">
                      {p.bot_name}
                    </Typography>
                  </TableCell>
                  <TableCell>{p.symbol}</TableCell>
                  <TableCell>{p.account}</TableCell>
                  <TableCell>
                    {p.legs.map((leg, i) => (
                      <Typography key={i} variant="caption" sx={{ display: "block", fontFamily: "monospace" }}>
                        {leg}
                      </Typography>
                    ))}
                  </TableCell>
                  <TableCell>{p.stop_target}</TableCell>
                  <TableCell>{p.profit_target || "None"}</TableCell>
                  <TableCell>
                    {openPriceLines(p.open_price).map((line, i) => (
                      <Typography key={i} variant="caption" sx={{ display: "block" }}>
                        {line}
                      </Typography>
                    ))}
                  </TableCell>
                  <TableCell align="right" sx={{ color: styleColor(p.profit_pct_style), fontVariantNumeric: "tabular-nums" }}>
                    {p.profit_pct}
                  </TableCell>
                  <TableCell
                    align="right"
                    sx={{ color: styleColor(p.profit_dollars_style), fontVariantNumeric: "tabular-nums" }}
                  >
                    {p.profit_dollars}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </TableContainer>
      )}
    </Box>
  );
}
