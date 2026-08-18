import { useEffect, useMemo, useState } from "react";
import {
  Box,
  MenuItem,
  Select,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  TableSortLabel,
  TextField,
  Typography,
} from "@mui/material";
import { useNavigate } from "react-router-dom";
import { calendarApi } from "../api/calendar";
import { daysApi } from "../api/days";
import type { Strategy, YearView } from "../api/types";
import { colorForValue } from "../utils/colors";

const MONTH_ABBR = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

function fmtCell(v: number | undefined, key: string | number) {
  if (!v) return <TableCell key={key} align="right" sx={{ color: "text.disabled" }}>—</TableCell>;
  return (
    <TableCell key={key} align="right" sx={{ color: colorForValue(v), fontVariantNumeric: "tabular-nums" }}>
      {v < 0 ? "-" : ""}${Math.abs(v).toLocaleString(undefined, { maximumFractionDigits: 0 })}
    </TableCell>
  );
}

type SortKey = "strategy" | "ytd" | number; // number = month index 0-11

export default function YearViewPage() {
  const navigate = useNavigate();
  const [years, setYears] = useState<number[]>([]);
  const [year, setYear] = useState<number | null>(null);
  const [data, setData] = useState<YearView | null>(null);
  const [strategies, setStrategies] = useState<Strategy[]>([]);
  const [filter, setFilter] = useState("");
  const [sortKey, setSortKey] = useState<SortKey>("strategy");
  const [sortDir, setSortDir] = useState<"asc" | "desc">("asc");

  useEffect(() => {
    calendarApi.years().then((ys) => {
      setYears(ys);
      if (ys.length) setYear(ys[ys.length - 1]);
    });
    daysApi.strategies().then(setStrategies);
  }, []);

  useEffect(() => {
    if (year) calendarApi.yearView(year).then(setData);
  }, [year]);

  const rows = useMemo(() => {
    if (!data) return [];
    const withYtd = data.sheets.map((sheet) => {
      const row = data.matrix[sheet] ?? {};
      const ytd = MONTH_ABBR.reduce((sum, _, i) => sum + (row[String(i + 1)] ?? 0), 0);
      return { sheet, row, ytd };
    });
    const filtered = filter
      ? withYtd.filter((r) => r.sheet.toLowerCase().includes(filter.toLowerCase()))
      : withYtd;
    const dir = sortDir === "asc" ? 1 : -1;
    return [...filtered].sort((a, b) => {
      if (sortKey === "strategy") return dir * a.sheet.localeCompare(b.sheet);
      if (sortKey === "ytd") return dir * (a.ytd - b.ytd);
      const av = a.row[String(sortKey + 1)] ?? 0;
      const bv = b.row[String(sortKey + 1)] ?? 0;
      return dir * (av - bv);
    });
  }, [data, filter, sortKey, sortDir]);

  const handleSort = (key: SortKey) => {
    if (sortKey === key) {
      setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    } else {
      setSortKey(key);
      setSortDir(key === "strategy" ? "asc" : "desc");
    }
  };

  if (!years.length) {
    return (
      <Box sx={{ maxWidth: 1600, mx: "auto", px: 3 }}>
        <Typography color="text.secondary">No data yet.</Typography>
      </Box>
    );
  }

  return (
    <Box sx={{ maxWidth: 1600, mx: "auto", px: 3, pb: 4 }}>
      <Box sx={{ display: "flex", gap: 3, alignItems: "flex-end", mb: 2 }}>
        <Box>
          <Typography variant="body2" sx={{ mb: 1 }}>
            Year
          </Typography>
          <Select
            size="small"
            value={year ?? ""}
            onChange={(e) => setYear(Number(e.target.value))}
            sx={{ minWidth: 120 }}
          >
            {[...years].reverse().map((y) => (
              <MenuItem key={y} value={y}>
                {y}
              </MenuItem>
            ))}
          </Select>
        </Box>
        <TextField
          size="small"
          label="Filter strategy"
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
          sx={{ minWidth: 220 }}
        />
      </Box>

      {data && (
        <TableContainer sx={{ border: "1px solid rgba(255,255,255,0.10)", borderRadius: "12px" }}>
          <Table size="small">
            <TableHead>
              <TableRow sx={{ bgcolor: "background.paper" }}>
                <TableCell sx={{ fontWeight: 600 }}>
                  <TableSortLabel
                    active={sortKey === "strategy"}
                    direction={sortKey === "strategy" ? sortDir : "asc"}
                    onClick={() => handleSort("strategy")}
                  >
                    Strategy
                  </TableSortLabel>
                </TableCell>
                {MONTH_ABBR.map((m, i) => (
                  <TableCell key={m} align="right" sx={{ color: "text.secondary" }}>
                    <TableSortLabel
                      active={sortKey === i}
                      direction={sortKey === i ? sortDir : "desc"}
                      onClick={() => handleSort(i)}
                    >
                      {m}
                    </TableSortLabel>
                  </TableCell>
                ))}
                <TableCell align="right" sx={{ color: "text.secondary" }}>
                  <TableSortLabel
                    active={sortKey === "ytd"}
                    direction={sortKey === "ytd" ? sortDir : "desc"}
                    onClick={() => handleSort("ytd")}
                  >
                    YTD
                  </TableSortLabel>
                </TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {rows.map(({ sheet, row, ytd }) => (
                <TableRow
                  key={sheet}
                  hover
                  onClick={() => navigate(`/strategy-year/${year}/${encodeURIComponent(sheet)}`)}
                  sx={{ cursor: "pointer" }}
                >
                  <TableCell sx={{ fontWeight: 600 }}>{sheet}</TableCell>
                  {MONTH_ABBR.map((_, i) => fmtCell(row[String(i + 1)], i))}
                  {fmtCell(ytd, "ytd")}
                </TableRow>
              ))}
              {(() => {
                const allBicsSheets = new Set(
                  strategies.filter((s) => s.include_in_all_bics).map((s) => s.sheet_name)
                );
                const allBicsRows = data.sheets
                  .filter((sheet) => allBicsSheets.has(sheet))
                  .map((sheet) => data.matrix[sheet] ?? {});
                const allBicsColTotals = MONTH_ABBR.map((_, i) =>
                  allBicsRows.reduce((sum, row) => sum + (row[String(i + 1)] ?? 0), 0)
                );
                const allBicsGrand = allBicsColTotals.reduce((a, b) => a + b, 0);

                const includeInTotal = new Set(
                  strategies
                    .filter((s) => s.include_in_total || s.include_in_all_bics)
                    .map((s) => s.sheet_name)
                );
                const totalRows = data.sheets
                  .filter((sheet) => includeInTotal.has(sheet))
                  .map((sheet) => data.matrix[sheet] ?? {});
                const colTotals = MONTH_ABBR.map((_, i) =>
                  totalRows.reduce((sum, row) => sum + (row[String(i + 1)] ?? 0), 0)
                );
                const grand = colTotals.reduce((a, b) => a + b, 0);
                return (
                  <>
                    <TableRow
                      hover
                      onClick={() => navigate(`/all-bics-year/${year}`)}
                      sx={{ cursor: "pointer", "& td": { fontWeight: 600, fontStyle: "italic" } }}
                    >
                      <TableCell>All BICs</TableCell>
                      {allBicsColTotals.map((v, i) => fmtCell(v, i))}
                      {fmtCell(allBicsGrand, "all-bics-grand")}
                    </TableRow>
                    <TableRow
                      hover
                      onClick={() => navigate(`/total-year/${year}`)}
                      sx={{ cursor: "pointer", "& td": { fontWeight: 700, borderTop: "2px solid rgba(255,255,255,0.2)", bgcolor: "background.paper" } }}
                    >
                      <TableCell>TOTAL</TableCell>
                      {colTotals.map((v, i) => fmtCell(v, i))}
                      {fmtCell(grand, "grand")}
                    </TableRow>
                  </>
                );
              })()}
            </TableBody>
          </Table>
        </TableContainer>
      )}
    </Box>
  );
}
