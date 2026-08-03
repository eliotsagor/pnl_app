import { Card, Grid, Typography } from "@mui/material";
import { money } from "../utils/money";

interface Props {
  totals: Record<string, number>;
}

export default function KpiRow({ totals }: Props) {
  const values = Object.values(totals);
  const netPnl = values.reduce((a, b) => a + b, 0);
  const tradingDays = values.length;
  const winDays = values.filter((v) => v > 0).length;
  const lossDays = values.filter((v) => v < 0).length;
  const best = values.length ? Math.max(...values) : 0;
  const worst = values.length ? Math.min(...values) : 0;
  const avgPerDay = tradingDays ? netPnl / tradingDays : 0;

  const kpis = [
    { label: "Net P&L", value: money(netPnl) },
    { label: "Trading days", value: String(tradingDays) },
    { label: "Green / Red", value: `${winDays} / ${lossDays}` },
    { label: "Best / Worst", value: `${money(best)} / ${money(worst)}` },
    { label: "Avg / day", value: money(avgPerDay) },
  ];

  return (
    <Grid container spacing={1.5} sx={{ mb: 2 }}>
      {kpis.map((k) => (
        <Grid key={k.label} size={12 / kpis.length}>
          <Card sx={{ p: 1.5 }}>
            <Typography variant="caption" color="text.secondary">
              {k.label}
            </Typography>
            <Typography variant="h6" sx={{ fontWeight: 700 }}>
              {k.value}
            </Typography>
          </Card>
        </Grid>
      ))}
    </Grid>
  );
}
