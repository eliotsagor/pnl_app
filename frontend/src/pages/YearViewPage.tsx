import { useEffect, useState } from "react";
import { Box, MenuItem, Select, Table, TableBody, TableCell, TableContainer, TableHead, TableRow, Typography } from "@mui/material";
import { calendarApi } from "../api/calendar";
import type { YearView } from "../api/types";
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

export default function YearViewPage() {
  const [years, setYears] = useState<number[]>([]);
  const [year, setYear] = useState<number | null>(null);
  const [data, setData] = useState<YearView | null>(null);

  useEffect(() => {
    calendarApi.years().then((ys) => {
      setYears(ys);
      if (ys.length) setYear(ys[ys.length - 1]);
    });
  }, []);

  useEffect(() => {
    if (year) calendarApi.yearView(year).then(setData);
  }, [year]);

  if (!years.length) {
    return (
      <Box sx={{ maxWidth: 1600, mx: "auto", px: 3 }}>
        <Typography color="text.secondary">No data yet.</Typography>
      </Box>
    );
  }

  return (
    <Box sx={{ maxWidth: 1600, mx: "auto", px: 3, pb: 4 }}>
      <Typography variant="body2" sx={{ mb: 1 }}>
        Year
      </Typography>
      <Select
        size="small"
        value={year ?? ""}
        onChange={(e) => setYear(Number(e.target.value))}
        sx={{ mb: 2, minWidth: 120 }}
      >
        {[...years].reverse().map((y) => (
          <MenuItem key={y} value={y}>
            {y}
          </MenuItem>
        ))}
      </Select>

      {data && (
        <TableContainer sx={{ border: "1px solid rgba(255,255,255,0.10)", borderRadius: "12px" }}>
          <Table size="small">
            <TableHead>
              <TableRow sx={{ bgcolor: "background.paper" }}>
                <TableCell sx={{ fontWeight: 600 }}>Strategy</TableCell>
                {MONTH_ABBR.map((m) => (
                  <TableCell key={m} align="right" sx={{ color: "text.secondary" }}>
                    {m}
                  </TableCell>
                ))}
                <TableCell align="right" sx={{ color: "text.secondary" }}>
                  YTD
                </TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {data.sheets.map((sheet) => {
                const row = data.matrix[sheet] ?? {};
                let ytd = 0;
                return (
                  <TableRow key={sheet}>
                    <TableCell sx={{ fontWeight: 600 }}>{sheet}</TableCell>
                    {MONTH_ABBR.map((_, i) => {
                      const v = row[String(i + 1)];
                      if (v) ytd += v;
                      return fmtCell(v, i);
                    })}
                    {fmtCell(ytd, "ytd")}
                  </TableRow>
                );
              })}
              {(() => {
                const colTotals = MONTH_ABBR.map((_, i) =>
                  data.sheets.reduce((sum, s) => sum + (data.matrix[s]?.[String(i + 1)] ?? 0), 0)
                );
                const grand = colTotals.reduce((a, b) => a + b, 0);
                return (
                  <TableRow sx={{ "& td": { fontWeight: 700, borderTop: "2px solid rgba(255,255,255,0.2)", bgcolor: "background.paper" } }}>
                    <TableCell>TOTAL</TableCell>
                    {colTotals.map((v, i) => fmtCell(v, i))}
                    {fmtCell(grand, "grand")}
                  </TableRow>
                );
              })()}
            </TableBody>
          </Table>
        </TableContainer>
      )}
    </Box>
  );
}
