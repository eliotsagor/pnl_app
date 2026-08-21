import { useEffect, useState } from "react";
import {
  Alert,
  Box,
  Button,
  Checkbox,
  Chip,
  CircularProgress,
  FormControlLabel,
  MenuItem,
  Select,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  TextField,
  Typography,
} from "@mui/material";
import RefreshIcon from "@mui/icons-material/Refresh";
import SaveIcon from "@mui/icons-material/Save";
import { tradestewardApi, type SnapshotMeta } from "../api/tradesteward";
import { useAutoRefreshJob } from "../hooks/useAutoRefreshJob";
import { useResizableSplit } from "../hooks/useResizableSplit";
import type { StrikeRow, SpxQuote, ExpectedMove, NetGreeks, Position } from "../api/types";
import { aggregateShortStrikes, netGreeksFor } from "../utils/strikeAggregation";
import { COLOR_GOOD, COLOR_CRITICAL, COLOR_WARNING } from "../theme";

function isOther(p: Position) {
  return !p.is_bic && !p.is_elmo;
}

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

// Red: strike sits within today's expected move (spot could plausibly reach
// it). Yellow: just outside, close enough to still watch. Green: comfortably
// beyond the expected move. Distance is measured in EM-widths, so the bands
// scale with how much the market is expected to move today rather than a
// fixed point/percent cutoff.
function bandTint(strike: number, spot: number, expectedMove: number | null): string {
  if (!expectedMove) return `${COLOR_GOOD}1f`;
  const emWidths = Math.abs(strike - spot) / expectedMove;
  if (emWidths <= 1) return `${COLOR_CRITICAL}1f`;
  if (emWidths <= 1.5) return `${COLOR_WARNING}1f`;
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
  greeks: NetGreeks;
  positions: Position[];
}

function fmtSigned(v: number, digits = 0) {
  const sign = v >= 0 ? "+" : "";
  return `${sign}${v.toFixed(digits)}`;
}

function evColor(v: number): string {
  return v >= 0 ? COLOR_GOOD : COLOR_CRITICAL;
}

// A dashed marker row inserted at the point in a sorted-by-strike list where
// a boundary price falls -- same idea as the spot divider, generalized so it
// can also mark the expected-move-up / expected-move-down levels.
function EmMarker({ label, color = COLOR_WARNING }: { label: string; color?: string }) {
  return (
    <TableRow>
      <TableCell
        colSpan={8}
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
  const { job, data, startError, pollError, isActive, lastUpdated, refreshNow, setData, paused, pause, resume, jobId } =
    useAutoRefreshJob<RiskResult>(tradestewardApi.fetchRisk);
  const { width: leftWidth, onDividerMouseDown } = useResizableSplit("risk-split-width", 680, 420, 1200);

  // Snapshots: freeze the current (live) result to disk so the dashboard
  // can still be worked on once the market's closed and TradeSteward/Schwab
  // have nothing live to fetch. Loading a snapshot pauses auto-refresh (it
  // would otherwise silently overwrite the loaded data on its next 30s
  // tick) -- "Back to live" resumes it.
  const [snapshots, setSnapshots] = useState<SnapshotMeta[]>([]);
  const [snapshotLabel, setSnapshotLabel] = useState("");
  const [savingSnapshot, setSavingSnapshot] = useState(false);
  const [snapshotError, setSnapshotError] = useState<string | null>(null);
  const [viewingSnapshotId, setViewingSnapshotId] = useState<string | null>(null);

  const refreshSnapshotList = () => {
    tradestewardApi
      .listRiskSnapshots()
      .then(setSnapshots)
      .catch((e) => setSnapshotError((e as Error).message));
  };

  const saveSnapshot = async () => {
    if (!jobId || !data) return;
    setSavingSnapshot(true);
    setSnapshotError(null);
    try {
      await tradestewardApi.saveRiskSnapshot(jobId, snapshotLabel);
      setSnapshotLabel("");
      refreshSnapshotList();
    } catch (e) {
      setSnapshotError((e as Error).message);
    } finally {
      setSavingSnapshot(false);
    }
  };

  const loadSnapshot = async (snapshotId: string) => {
    setSnapshotError(null);
    try {
      const result = await tradestewardApi.loadRiskSnapshot<RiskResult>(snapshotId);
      pause();
      setData(result);
      setViewingSnapshotId(snapshotId);
    } catch (e) {
      setSnapshotError((e as Error).message);
    }
  };

  const backToLive = () => {
    setViewingSnapshotId(null);
    resume();
  };

  useEffect(() => {
    refreshSnapshotList();
  }, []);

  // Category checkboxes (Elmo/BIC/Other) and per-bot checkboxes both narrow
  // which positions feed the left grid, the net delta/gamma header, and the
  // call/put footers -- independent AND filters, so a bot only shows if
  // both its category and its own checkbox are checked.
  //
  // Per-bot state is a set of *unchecked* bot_names, not checked serials:
  // serial is per-fetch (auto-refresh every 30s gets a fresh set), so
  // tracking by serial meant every refresh silently re-checked everything,
  // wiping out a user's unchecks. bot_name is stable across fetches for
  // the same still-open position, so an unchecked-by-name set survives a
  // refresh; new bots that appear later default to checked (absent from
  // the unchecked set).
  const [showElmo, setShowElmo] = useState(true);
  const [showBic, setShowBic] = useState(true);
  const [showOther, setShowOther] = useState(true);
  const [uncheckedNames, setUncheckedNames] = useState<Set<string>>(new Set());

  const quote = data?.quote;
  const hasQuote = quote && quote.price != null;
  const em = data?.expected_move;
  const hasEm = hasQuote && em?.expected_move != null;
  const emUp = hasEm ? quote!.price! + em!.expected_move! : null;
  const emDown = hasEm ? quote!.price! - em!.expected_move! : null;

  const allPositions = data?.positions ?? [];
  const filteredPositions = allPositions.filter((p) => {
    if (uncheckedNames.has(p.bot_name)) return false;
    if (p.is_elmo && !showElmo) return false;
    if (p.is_bic && !showBic) return false;
    if (isOther(p) && !showOther) return false;
    return true;
  });
  const filteredStrikes = aggregateShortStrikes(filteredPositions);
  const filteredGreeks = netGreeksFor(filteredPositions);

  const checkedCount = allPositions.filter((p) => !uncheckedNames.has(p.bot_name)).length;
  const allChecked = allPositions.length > 0 && checkedCount === allPositions.length;
  const someChecked = checkedCount > 0 && !allChecked;
  const toggleAll = () => {
    setUncheckedNames(allChecked ? new Set(allPositions.map((p) => p.bot_name)) : new Set());
  };
  const toggleOne = (botName: string) => {
    setUncheckedNames((prev) => {
      const next = new Set(prev);
      if (next.has(botName)) next.delete(botName);
      else next.add(botName);
      return next;
    });
  };

  // Closest-to-spot strikes sit nearest the spot divider on both sides:
  // calls descend toward it from above, puts descend away from it below.
  const calls = filteredStrikes.filter((r) => r.type === "C").sort((a, b) => b.strike - a.strike);
  const puts = filteredStrikes.filter((r) => r.type === "P").sort((a, b) => b.strike - a.strike);

  const sum = (rows: StrikeRow[], key: "captured" | "remaining" | "at_risk" | "ev") =>
    rows.reduce((s, r) => s + (r[key] ?? 0), 0);

  const changeColor = quote?.change != null ? (quote.change >= 0 ? COLOR_GOOD : COLOR_CRITICAL) : "text.secondary";

  // Insert an EM marker into a strike list (already sorted furthest-to-closest
  // relative to spot) right before the first row whose strike has crossed
  // past the boundary, i.e. is now within the expected move.
  function withEmMarker(rows: StrikeRow[], boundary: number | null, side: "up" | "down") {
    if (boundary == null) return rows.map((r) => ({ kind: "row" as const, row: r }));
    const out: ({ kind: "row"; row: StrikeRow } | { kind: "marker" })[] = [];
    let inserted = false;
    for (const r of rows) {
      const crossed = side === "up" ? r.strike <= boundary : r.strike < boundary;
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
      sx={{ bgcolor: hasQuote ? bandTint(r.strike, quote!.price!, em?.expected_move ?? null) : undefined }}
    >
      <TableCell sx={{ fontVariantNumeric: "tabular-nums" }}>
        {r.strike.toLocaleString()} {r.type}
        {r.is_elmo && (
          <Chip
            label="Elmo"
            size="small"
            sx={{ ml: 0.75, height: 18, fontSize: "0.65rem", bgcolor: "#3987e5", color: "#fff" }}
          />
        )}
        {r.is_bic && (
          <Chip
            label="BIC"
            size="small"
            sx={{ ml: 0.75, height: 18, fontSize: "0.65rem", bgcolor: COLOR_WARNING, color: "#000" }}
          />
        )}
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
      <TableCell align="right" sx={{ color: r.ev != null ? evColor(r.ev) : "text.secondary", fontVariantNumeric: "tabular-nums" }}>
        {r.ev != null ? `${r.ev >= 0 ? "+" : "-"}$${Math.round(Math.abs(r.ev)).toLocaleString()}` : "—"}
      </TableCell>
    </TableRow>
  );

  return (
    <Box sx={{ maxWidth: 1800, mx: "auto", px: 1.5, pb: 4 }}>
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
        {lastUpdated && !paused && (
          <Typography variant="caption" color="text.secondary">
            updated {lastUpdated.toLocaleTimeString()}
            {isActive ? " · refreshing…" : ""}
          </Typography>
        )}
        {paused && (
          <Chip
            size="small"
            label={`Viewing snapshot${snapshots.find((s) => s.id === viewingSnapshotId)?.label ? `: ${snapshots.find((s) => s.id === viewingSnapshotId)!.label}` : ""}`}
            sx={{ bgcolor: `${COLOR_WARNING}22`, color: COLOR_WARNING }}
          />
        )}
        {paused ? (
          <Button variant="outlined" size="small" onClick={backToLive} sx={{ ml: "auto" }}>
            Back to live
          </Button>
        ) : (
          <Button
            variant="contained"
            size="small"
            startIcon={<RefreshIcon />}
            onClick={refreshNow}
            disabled={isActive}
            sx={{ ml: "auto" }}
          >
            {isActive ? (data ? "Refreshing…" : "Starting…") : data ? "Refresh now" : "Load positions"}
          </Button>
        )}
      </Box>

      <Box sx={{ display: "flex", alignItems: "center", gap: 1.5, mb: 2, flexWrap: "wrap" }}>
        <TextField
          size="small"
          placeholder="Snapshot label (optional)"
          value={snapshotLabel}
          onChange={(e) => setSnapshotLabel(e.target.value)}
          sx={{ minWidth: 220 }}
        />
        <Button
          size="small"
          variant="outlined"
          startIcon={<SaveIcon />}
          onClick={saveSnapshot}
          disabled={!data || paused || savingSnapshot}
        >
          {savingSnapshot ? "Saving…" : "Save snapshot"}
        </Button>
        {snapshots.length > 0 && (
          <Select
            size="small"
            displayEmpty
            value={viewingSnapshotId ?? ""}
            onChange={(e) => e.target.value && loadSnapshot(e.target.value)}
            sx={{ minWidth: 260 }}
          >
            <MenuItem value="">
              <em>Load a saved snapshot…</em>
            </MenuItem>
            {snapshots.map((s) => (
              <MenuItem key={s.id} value={s.id}>
                {(s.label || "snapshot") + " — " + new Date(s.saved_at).toLocaleString()}
              </MenuItem>
            ))}
          </Select>
        )}
        {snapshotError && (
          <Typography variant="caption" color="error">
            {snapshotError}
          </Typography>
        )}
      </Box>

      {filteredGreeks && (
        <Box sx={{ display: "flex", gap: 4, mb: 2, flexWrap: "wrap" }}>
          <Box>
            <Typography variant="caption" color="text.secondary" sx={{ display: "block" }}>
              Net delta
            </Typography>
            <Typography variant="h6" sx={{ fontWeight: 600 }}>
              {fmtSigned(filteredGreeks.net_delta)}
            </Typography>
          </Box>
          <Box>
            <Typography variant="caption" color="text.secondary" sx={{ display: "block" }}>
              Net gamma
            </Typography>
            <Typography variant="h6" sx={{ fontWeight: 600, color: filteredGreeks.net_gamma < 0 ? COLOR_CRITICAL : "text.primary" }}>
              {fmtSigned(filteredGreeks.net_gamma, 1)}
            </Typography>
          </Box>
          <Box>
            <Typography variant="caption" color="text.secondary" sx={{ display: "block" }}>
              δ @ -10pt
            </Typography>
            <Typography variant="h6" sx={{ fontWeight: 600, color: COLOR_WARNING }}>
              {fmtSigned(filteredGreeks.delta_at_minus_10)}
            </Typography>
          </Box>
          <Box>
            <Typography variant="caption" color="text.secondary" sx={{ display: "block" }}>
              δ @ +10pt
            </Typography>
            <Typography variant="h6" sx={{ fontWeight: 600 }}>
              {fmtSigned(filteredGreeks.delta_at_plus_10)}
            </Typography>
          </Box>
        </Box>
      )}

      {data && allPositions.length > 0 && (
        <Box sx={{ display: "flex", gap: 2, mb: 2 }}>
          <FormControlLabel
            control={<Checkbox size="small" checked={showElmo} onChange={(e) => setShowElmo(e.target.checked)} />}
            label={
              <Typography variant="body2" sx={{ color: "#3987e5" }}>
                Elmo
              </Typography>
            }
          />
          <FormControlLabel
            control={<Checkbox size="small" checked={showBic} onChange={(e) => setShowBic(e.target.checked)} />}
            label={
              <Typography variant="body2" sx={{ color: COLOR_WARNING }}>
                BIC
              </Typography>
            }
          />
          <FormControlLabel
            control={<Checkbox size="small" checked={showOther} onChange={(e) => setShowOther(e.target.checked)} />}
            label={
              <Typography variant="body2" color="text.secondary">
                Other
              </Typography>
            }
          />
        </Box>
      )}

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

      {data && allPositions.length === 0 && (
        <Typography color="text.secondary">No short options open right now.</Typography>
      )}

      {data && allPositions.length > 0 && (
      <Box sx={{ display: "flex", alignItems: "flex-start" }}>
        <Box sx={{ flex: `0 0 ${leftWidth}px`, minWidth: 0 }}>
        {calls.length === 0 && puts.length === 0 && (
          <Typography color="text.secondary" sx={{ mb: 2 }}>
            No positions match the current filters.
          </Typography>
        )}
        {(calls.length > 0 || puts.length > 0) && (
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
                <TableCell align="right" sx={{ fontWeight: 600 }}>
                  EV
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
                    colSpan={8}
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
            <Box sx={{ display: "flex", justifyContent: "space-between" }}>
              <Typography variant="body2" color="text.secondary">
                EV
              </Typography>
              <Typography variant="body2" sx={{ color: evColor(sum(calls, "ev")) }}>
                {sum(calls, "ev") >= 0 ? "+" : "-"}${Math.round(Math.abs(sum(calls, "ev"))).toLocaleString()}
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
            <Box sx={{ display: "flex", justifyContent: "space-between" }}>
              <Typography variant="body2" color="text.secondary">
                EV
              </Typography>
              <Typography variant="body2" sx={{ color: evColor(sum(puts, "ev")) }}>
                {sum(puts, "ev") >= 0 ? "+" : "-"}${Math.round(Math.abs(sum(puts, "ev"))).toLocaleString()}
              </Typography>
            </Box>
          </Box>
        </Box>
        </Box>

        <Box
          onMouseDown={onDividerMouseDown}
          sx={{
            flex: "0 0 auto",
            width: "10px",
            alignSelf: "stretch",
            cursor: "col-resize",
            display: "flex",
            justifyContent: "center",
            "&:hover > div, &:active > div": { bgcolor: "primary.main" },
          }}
        >
          <Box sx={{ width: "2px", bgcolor: "rgba(255,255,255,0.15)", borderRadius: "1px" }} />
        </Box>

        {data.positions && data.positions.some((p) => p.ev != null) && (
        <Box sx={{ flex: "1 1 auto", minWidth: 0 }}>
          <Typography variant="subtitle2" sx={{ mb: 1 }}>
            Expected value of holding
          </Typography>
          <TableContainer sx={{ border: "1px solid rgba(255,255,255,0.10)", borderRadius: "12px" }}>
            <Table size="small">
              <TableHead>
                <TableRow sx={{ bgcolor: "background.paper" }}>
                  <TableCell padding="checkbox">
                    <Checkbox
                      size="small"
                      checked={allChecked}
                      indeterminate={someChecked}
                      onChange={toggleAll}
                    />
                  </TableCell>
                  <TableCell sx={{ fontWeight: 600 }}>Bot</TableCell>
                  <TableCell sx={{ fontWeight: 600 }}>Strategy</TableCell>
                  <TableCell align="right" sx={{ fontWeight: 600 }}>
                    Stop%
                  </TableCell>
                  <TableCell align="right" sx={{ fontWeight: 600 }}>
                    Delta
                  </TableCell>
                  <TableCell align="right" sx={{ fontWeight: 600 }}>
                    Gamma
                  </TableCell>
                  <TableCell align="right" sx={{ fontWeight: 600 }}>
                    EV
                  </TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {data.positions
                  .filter((p) => p.ev != null)
                  .sort((a, b) => (a.ev ?? 0) - (b.ev ?? 0))
                  .map((p) => (
                    <TableRow key={p.serial} hover>
                      <TableCell padding="checkbox">
                        <Checkbox
                          size="small"
                          checked={!uncheckedNames.has(p.bot_name)}
                          onChange={() => toggleOne(p.bot_name)}
                        />
                      </TableCell>
                      <TableCell>
                        <Typography variant="body2">{p.bot_name}</Typography>
                      </TableCell>
                      <TableCell>
                        <Typography variant="body2" color="text.secondary">
                          {p.strategy}
                        </Typography>
                      </TableCell>
                      <TableCell align="right" sx={{ color: stopProbColor(p.stop_probability), fontVariantNumeric: "tabular-nums" }}>
                        {p.stop_probability != null ? `${Math.round(p.stop_probability * 100)}%` : "—"}
                      </TableCell>
                      <TableCell align="right" sx={{ fontVariantNumeric: "tabular-nums", color: "text.secondary" }}>
                        {p.delta != null ? fmtSigned(p.delta) : "—"}
                      </TableCell>
                      <TableCell
                        align="right"
                        sx={{ fontVariantNumeric: "tabular-nums", color: (p.gamma ?? 0) < 0 ? COLOR_CRITICAL : "text.secondary" }}
                      >
                        {p.gamma != null ? fmtSigned(p.gamma, 1) : "—"}
                      </TableCell>
                      <TableCell align="right" sx={{ color: evColor(p.ev!), fontVariantNumeric: "tabular-nums" }}>
                        {p.ev! >= 0 ? "+" : "-"}${Math.round(Math.abs(p.ev!)).toLocaleString()}
                      </TableCell>
                    </TableRow>
                  ))}
              </TableBody>
            </Table>
          </TableContainer>
        </Box>
        )}
      </Box>
      )}
    </Box>
  );
}
