import { Card, CardContent, Grid, Typography } from "@mui/material";
import { money } from "../utils/money";
import { tintForValue, borderForValue, colorForValue } from "../utils/colors";

interface Props {
  year: number;
  month: number; // 1-12
  totals: Record<string, number>;
  selectedDay: number | null;
  onSelectDay: (day: number) => void;
}

const WEEKDAY_LABELS = ["MON", "TUE", "WED", "THU", "FRI"];

export default function CalendarGrid({ year, month, totals, selectedDay, onSelectDay }: Props) {
  const firstWeekday = new Date(year, month - 1, 1).getDay(); // 0=Sun
  const daysInMonth = new Date(year, month, 0).getDate();

  // Mon=0 .. Fri=4 leading offset for the 1st of the month; weekend days are dropped.
  const firstWeekdayMonFri = (firstWeekday + 6) % 7; // 0=Mon .. 6=Sun
  const leadingBlanks = firstWeekdayMonFri > 4 ? 0 : firstWeekdayMonFri;

  const cells: (number | null)[] = [];
  for (let i = 0; i < leadingBlanks; i++) cells.push(null);
  for (let d = 1; d <= daysInMonth; d++) {
    const dow = new Date(year, month - 1, d).getDay(); // 0=Sun .. 6=Sat
    if (dow === 0 || dow === 6) continue;
    cells.push(d);
  }

  return (
    <Grid container spacing={1}>
      {WEEKDAY_LABELS.map((label) => (
        <Grid key={label} size={12 / 5}>
          <Typography variant="caption" color="text.secondary" sx={{ display: "block", textAlign: "center" }}>
            {label}
          </Typography>
        </Grid>
      ))}
      {cells.map((day, i) => {
        if (day === null) return <Grid key={`e${i}`} size={12 / 5} />;
        const v = totals[String(day)];
        const hasData = v !== undefined;
        const isSelected = selectedDay === day;
        return (
          <Grid key={day} size={12 / 5}>
            <Card
              onClick={() => hasData && onSelectDay(day)}
              sx={{
                height: 56,
                cursor: hasData ? "pointer" : "default",
                bgcolor: hasData ? tintForValue(v) : "#141413",
                border: "1px solid",
                borderColor: isSelected ? "primary.main" : hasData ? borderForValue(v) : "rgba(255,255,255,0.08)",
                transition: "transform 0.12s ease, box-shadow 0.12s ease",
                "&:hover": hasData ? { transform: "translateY(-2px)", boxShadow: 6 } : {},
              }}
            >
              <CardContent sx={{ p: "6px 10px !important" }}>
                <Typography variant="caption" color="text.secondary">
                  {day}
                </Typography>
                {hasData && (
                  <Typography variant="caption" sx={{ display: "block", fontWeight: 700, color: colorForValue(v) }}>
                    {money(v)}
                  </Typography>
                )}
              </CardContent>
            </Card>
          </Grid>
        );
      })}
    </Grid>
  );
}
