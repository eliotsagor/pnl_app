import { useEffect, useState } from "react";
import { Box, IconButton, Typography } from "@mui/material";
import ChevronLeftIcon from "@mui/icons-material/ChevronLeft";
import ChevronRightIcon from "@mui/icons-material/ChevronRight";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";
import { calendarApi } from "../api/calendar";
import KpiRow from "../components/KpiRow";
import CalendarGrid from "../components/CalendarGrid";
import DayDetailChips from "../components/DayDetailChips";

const MONTH_NAMES = [
  "January", "February", "March", "April", "May", "June",
  "July", "August", "September", "October", "November", "December",
];

export default function CalendarPage() {
  const params = useParams();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();

  const year = Number(params.year);
  const month = Number(params.month);

  const [totals, setTotals] = useState<Record<string, number> | null>(null);
  const [detail, setDetail] = useState<Record<string, number> | null>(null);
  const [loadingDetail, setLoadingDetail] = useState(false);

  const selectedDayParam = searchParams.get("day");
  const selectedDay =
    selectedDayParam && selectedDayParam.startsWith(`${year}-${String(month).padStart(2, "0")}`)
      ? Number(selectedDayParam.split("-")[2])
      : null;

  useEffect(() => {
    if (!year || !month) return;
    setTotals(null);
    calendarApi.month(year, month).then(setTotals);
  }, [year, month]);

  useEffect(() => {
    if (!selectedDayParam) {
      setDetail(null);
      return;
    }
    setLoadingDetail(true);
    calendarApi
      .day(selectedDayParam)
      .then(setDetail)
      .finally(() => setLoadingDetail(false));
  }, [selectedDayParam]);

  const goMonth = (delta: number) => {
    let y = year;
    let m = month + delta;
    if (m === 0) { m = 12; y -= 1; }
    if (m === 13) { m = 1; y += 1; }
    navigate(`/calendar/${y}/${m}`);
  };

  const selectDay = (day: number) => {
    const iso = `${year}-${String(month).padStart(2, "0")}-${String(day).padStart(2, "0")}`;
    setSearchParams({ day: iso });
  };

  if (!year || !month || !totals) {
    return null;
  }

  return (
    <Box sx={{ maxWidth: 1600, mx: "auto", px: 3, pb: 4 }}>
      <Box sx={{ display: "flex", alignItems: "center", justifyContent: "center", gap: 2, mb: 2 }}>
        <IconButton onClick={() => goMonth(-1)}>
          <ChevronLeftIcon />
        </IconButton>
        <Typography variant="h5" sx={{ minWidth: 220, textAlign: "center", fontWeight: 600 }}>
          {MONTH_NAMES[month - 1]} {year}
        </Typography>
        <IconButton onClick={() => goMonth(1)}>
          <ChevronRightIcon />
        </IconButton>
      </Box>

      <KpiRow totals={totals} />
      <CalendarGrid year={year} month={month} totals={totals} selectedDay={selectedDay} onSelectDay={selectDay} />
      <DayDetailChips isoDate={selectedDayParam} detail={detail} loading={loadingDetail} />
    </Box>
  );
}
