import { useEffect, useState } from "react";
import {
  Box,
  IconButton,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Typography,
} from "@mui/material";
import ArrowBackIcon from "@mui/icons-material/ArrowBack";
import { useNavigate, useParams } from "react-router-dom";
import { calendarApi } from "../api/calendar";
import type { StrategyYearView } from "../api/types";
import { colorForValue } from "../utils/colors";

const MONTH_ABBR = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
const DAYS = Array.from({ length: 31 }, (_, i) => i + 1);
const WEEKDAY_LABELS = ["Mon", "Tue", "Wed", "Thu", "Fri"];

const CELL_SX = { py: 0.25, px: 1, fontSize: "0.75rem" };

function fmtCell(v: number | undefined, key: string | number) {
  if (!v) return <TableCell key={key} align="right" sx={{ ...CELL_SX, color: "text.disabled" }}>—</TableCell>;
  return (
    <TableCell key={key} align="right" sx={{ ...CELL_SX, color: colorForValue(v), fontVariantNumeric: "tabular-nums" }}>
      {v < 0 ? "-" : ""}${Math.abs(v).toLocaleString(undefined, { maximumFractionDigits: 0 })}
    </TableCell>
  );
}

interface StrategyYearPageProps {
  /** When set, overrides the URL :sheet param and fetches an aggregate view instead of a single strategy. */
  kind?: "total" | "all-bics";
}

export default function StrategyYearPage({ kind }: StrategyYearPageProps = {}) {
  const navigate = useNavigate();
  const { year, sheet } = useParams<{ year: string; sheet: string }>();
  const [data, setData] = useState<StrategyYearView | null>(null);
  const sheetName = sheet ? decodeURIComponent(sheet) : "";
  const title = kind === "total" ? "Total" : kind === "all-bics" ? "All BICs" : sheetName;

  useEffect(() => {
    if (!year) return;
    if (kind === "total") {
      calendarApi.totalYearView(Number(year)).then(setData);
    } else if (kind === "all-bics") {
      calendarApi.allBicsYearView(Number(year)).then(setData);
    } else if (sheet) {
      calendarApi.strategyYearView(Number(year), sheetName).then(setData);
    }
  }, [year, sheet, sheetName, kind]);

  return (
    <Box sx={{ maxWidth: 1600, mx: "auto", px: 3, pb: 4 }}>
      <Box sx={{ display: "flex", alignItems: "center", gap: 1, mb: 2 }}>
        <IconButton onClick={() => navigate(`/year-view`)} size="small">
          <ArrowBackIcon fontSize="small" />
        </IconButton>
        <Typography variant="h6" sx={{ fontWeight: 600 }}>
          {title} — {year}
        </Typography>
      </Box>

      {data && (
        <TableContainer sx={{ border: "1px solid rgba(255,255,255,0.10)", borderRadius: "12px" }}>
          <Table size="small">
            <TableHead>
              <TableRow sx={{ bgcolor: "background.paper" }}>
                <TableCell sx={{ ...CELL_SX, fontWeight: 600 }}>Day</TableCell>
                {MONTH_ABBR.map((m) => (
                  <TableCell key={m} align="right" sx={{ ...CELL_SX, color: "text.secondary" }}>
                    {m}
                  </TableCell>
                ))}
                <TableCell align="right" sx={{ ...CELL_SX, color: "text.secondary" }}>
                  Grand Total
                </TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {DAYS.map((day) => {
                const dayRow = data.days[String(day)] ?? {};
                const hasAny = MONTH_ABBR.some((_, i) => dayRow[String(i + 1)] !== undefined);
                if (!hasAny) return null;
                return (
                  <TableRow key={day}>
                    <TableCell sx={{ ...CELL_SX, fontWeight: 600, color: "text.secondary" }}>{day}</TableCell>
                    {MONTH_ABBR.map((_, i) => fmtCell(dayRow[String(i + 1)], i))}
                    <TableCell sx={CELL_SX} />
                  </TableRow>
                );
              })}
              {(() => {
                const colTotals = MONTH_ABBR.map((_, i) =>
                  DAYS.reduce((sum, d) => sum + (data.days[String(d)]?.[String(i + 1)] ?? 0), 0)
                );
                const grand = colTotals.reduce((a, b) => a + b, 0);
                return (
                  <TableRow sx={{ "& td": { ...CELL_SX, fontWeight: 700, borderTop: "2px solid rgba(255,255,255,0.2)", bgcolor: "background.paper" } }}>
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

      {data && (
        <>
          <TableContainer sx={{ mt: 3, border: "1px solid rgba(255,255,255,0.10)", borderRadius: "12px", maxWidth: 560 }}>
            <Table size="small">
              <TableHead>
                <TableRow sx={{ bgcolor: "background.paper" }}>
                  {WEEKDAY_LABELS.map((w) => (
                    <TableCell key={w} align="right" sx={{ ...CELL_SX, color: "text.secondary" }}>
                      {w}
                    </TableCell>
                  ))}
                </TableRow>
              </TableHead>
              <TableBody>
                <TableRow>
                  {WEEKDAY_LABELS.map((_, i) => fmtCell(data.weekday[String(i)]?.total, `wd-total-${i}`))}
                </TableRow>
                <TableRow>
                  {WEEKDAY_LABELS.map((_, i) => {
                    const wd = data.weekday[String(i)];
                    const avg = wd && wd.count ? wd.total / wd.count : undefined;
                    return (
                      <TableCell key={i} align="right" sx={{ ...CELL_SX, color: "text.disabled" }}>
                        {avg !== undefined ? `avg ${avg < 0 ? "-" : ""}$${Math.abs(avg).toLocaleString(undefined, { maximumFractionDigits: 0 })}` : "—"}
                      </TableCell>
                    );
                  })}
                </TableRow>
              </TableBody>
            </Table>
          </TableContainer>
        </>
      )}
    </Box>
  );
}
