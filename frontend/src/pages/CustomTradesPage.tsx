import { useState } from "react";
import {
  Alert,
  Box,
  Button,
  Card,
  CardContent,
  Divider,
  Grid,
  IconButton,
  MenuItem,
  Select,
  TextField,
  Typography,
} from "@mui/material";
import DeleteIcon from "@mui/icons-material/Delete";
import DeleteSweepIcon from "@mui/icons-material/DeleteSweep";
import SaveIcon from "@mui/icons-material/Save";
import { DatePicker } from "@mui/x-date-pickers/DatePicker";
import dayjs, { type Dayjs } from "dayjs";
import { daysApi } from "../api/days";
import { useStrategies } from "../hooks/useStrategies";
import { money } from "../utils/money";

interface Leg {
  time: string;
  units: number;
  price: number;
  action: "DEBIT" | "CREDIT";
  mult: number;
  cash: number;
}

export default function CustomTradesPage() {
  const strategies = useStrategies();
  const [tradeDate, setTradeDate] = useState<Dayjs>(dayjs());
  const [targetStrategy, setTargetStrategy] = useState("FOMC Meeting");
  const [legs, setLegs] = useState<Leg[]>([]);

  const [time, setTime] = useState("");
  const [units, setUnits] = useState(1);
  const [price, setPrice] = useState(0);
  const [action, setAction] = useState<"DEBIT" | "CREDIT">("DEBIT");
  const [mult, setMult] = useState(100);

  const [saving, setSaving] = useState(false);
  const [saveResult, setSaveResult] = useState<{ new_total: number } | null>(null);
  const [saveError, setSaveError] = useState<string | null>(null);

  const addLeg = () => {
    const sign = action === "DEBIT" ? -1 : 1;
    const cash = sign * units * price * mult;
    setLegs((prev) => [...prev, { time, units, price, action, mult, cash }]);
    setTime("");
    setUnits(1);
    setPrice(0);
  };

  const removeLeg = (i: number) => setLegs((prev) => prev.filter((_, idx) => idx !== i));
  const clearAll = () => {
    setLegs([]);
    setSaveResult(null);
  };

  const total = legs.reduce((sum, l) => sum + l.cash, 0);
  const isoDate = tradeDate.format("YYYY-MM-DD");

  const save = async () => {
    setSaving(true);
    setSaveError(null);
    try {
      const result = await daysApi.addToStrategy(isoDate, targetStrategy, total);
      setSaveResult(result);
      setLegs([]);
    } catch (e) {
      setSaveError((e as Error).message);
    } finally {
      setSaving(false);
    }
  };

  return (
    <Box sx={{ maxWidth: 1600, mx: "auto", px: 3, pb: 4 }}>
      <Typography variant="h6" gutterBottom>
        Custom Trade P&L Calculator
      </Typography>
      <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
        For days with manual trade-log calculations (e.g. FOMC custom diagonals).
      </Typography>

      <Box sx={{ display: "flex", gap: 2, mb: 2, maxWidth: 500 }}>
        <DatePicker
          label="Trade date"
          value={tradeDate}
          onChange={(v) => v && setTradeDate(v)}
          slotProps={{ textField: { size: "small", fullWidth: true } }}
        />
        <Select
          size="small"
          fullWidth
          value={targetStrategy}
          onChange={(e) => setTargetStrategy(e.target.value)}
          displayEmpty
        >
          {strategies
            .filter((s) => s.sheet_name !== "All BICs")
            .map((s) => (
              <MenuItem key={s.id} value={s.sheet_name}>
                {s.sheet_name}
              </MenuItem>
            ))}
        </Select>
      </Box>

      <Divider sx={{ my: 2 }} />
      <Typography variant="subtitle2" gutterBottom>
        Add each trade leg:
      </Typography>
      <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
        Enter quantity (positive for long, negative for short), price per spread unit (in dollars), and whether
        it's a DEBIT or CREDIT to your account.
      </Typography>

      <Card sx={{ p: 2, mb: 3 }}>
        <CardContent sx={{ py: "8px !important" }}>
          <Grid container spacing={2} sx={{ alignItems: "center" }}>
            <Grid size={3}>
              <TextField
                label="Time"
                size="small"
                fullWidth
                placeholder="14:30:31"
                value={time}
                onChange={(e) => setTime(e.target.value)}
              />
            </Grid>
            <Grid size={2}>
              <TextField
                label="Spread units"
                type="number"
                size="small"
                fullWidth
                value={units}
                onChange={(e) => setUnits(parseFloat(e.target.value) || 0)}
              />
            </Grid>
            <Grid size={2}>
              <TextField
                label="Price per unit"
                type="number"
                size="small"
                fullWidth
                value={price}
                onChange={(e) => setPrice(parseFloat(e.target.value) || 0)}
              />
            </Grid>
            <Grid size={2}>
              <Select size="small" fullWidth value={action} onChange={(e) => setAction(e.target.value as "DEBIT" | "CREDIT")}>
                <MenuItem value="DEBIT">DEBIT (out)</MenuItem>
                <MenuItem value="CREDIT">CREDIT (in)</MenuItem>
              </Select>
            </Grid>
            <Grid size={1.5}>
              <TextField
                label="Mult"
                type="number"
                size="small"
                fullWidth
                value={mult}
                onChange={(e) => setMult(parseFloat(e.target.value) || 0)}
              />
            </Grid>
            <Grid size={1.5}>
              <Button variant="outlined" startIcon={<span>+</span>} onClick={addLeg} fullWidth>
                Add
              </Button>
            </Grid>
          </Grid>
        </CardContent>
      </Card>

      {legs.length > 0 && (
        <>
          <Typography variant="subtitle2" gutterBottom>
            Trade ledger:
          </Typography>
          {legs.map((l, i) => (
            <Box key={i} sx={{ display: "flex", alignItems: "center", gap: 2, py: 0.5 }}>
              <Typography variant="body2" sx={{ flex: 3, fontFamily: "monospace" }}>
                {l.time} | {l.units.toFixed(0)}u × ${l.price.toFixed(2)} × {l.mult} {l.action}
              </Typography>
              <Typography variant="body2" sx={{ flex: 1 }}>
                {l.cash >= 0 ? "+" : ""}
                {money(l.cash)}
              </Typography>
              <IconButton size="small" onClick={() => removeLeg(i)}>
                <DeleteIcon fontSize="small" />
              </IconButton>
            </Box>
          ))}

          <Typography variant="h6" sx={{ mt: 2, mb: 2, fontWeight: 700 }}>
            Net P&L: {money(total)}
          </Typography>

          <Box sx={{ display: "flex", gap: 2 }}>
            <Button variant="contained" startIcon={<SaveIcon />} onClick={save} disabled={saving}>
              {saving ? "Saving…" : `Save ${money(total)} to ${targetStrategy} on ${isoDate}`}
            </Button>
            <Button startIcon={<DeleteSweepIcon />} onClick={clearAll}>
              Clear all
            </Button>
          </Box>
        </>
      )}

      {saveError && (
        <Alert severity="error" sx={{ mt: 2 }}>
          {saveError}
        </Alert>
      )}
      {saveResult && (
        <Alert severity="success" sx={{ mt: 2 }}>
          Added to {targetStrategy} on {isoDate} (new total there: {money(saveResult.new_total)})
        </Alert>
      )}
    </Box>
  );
}
