import { useState } from "react";
import { Alert, Box, Button, Grid, TextField, Typography } from "@mui/material";
import SaveIcon from "@mui/icons-material/Save";
import { useStrategies } from "../hooks/useStrategies";
import { money } from "../utils/money";

interface UnmappedLine {
  label: string;
  value: number;
}

interface Props {
  trade_date: string;
  initialValues: Record<string, number>;
  unmapped?: UnmappedLine[];
  onSave: (values: Record<string, number>) => void | Promise<void>;
  saving?: boolean;
}

/**
 * Shared editable per-strategy form, used by all 3 Enter Day flows (fetch,
 * screenshot upload, manual). Pass a `key` prop from the parent whenever
 * `initialValues` should reset the form (e.g. a fresh fetch/parse result).
 */
export default function DayEditorForm({ trade_date, initialValues, unmapped, onSave, saving }: Props) {
  const strategies = useStrategies();
  const [values, setValues] = useState<Record<string, number>>(initialValues);

  const setValue = (sheet: string, v: number) => {
    setValues((prev) => {
      const next = { ...prev };
      if (v === 0) delete next[sheet];
      else next[sheet] = v;
      return next;
    });
  };

  const allBicSheets = new Set(strategies.filter((s) => s.include_in_all_bics === 1).map((s) => s.sheet_name));
  const allBicsSubtotal = Object.entries(values)
    .filter(([sheet]) => allBicSheets.has(sheet))
    .reduce((sum, [, v]) => sum + v, 0);
  const total = Object.values(values).reduce((sum, v) => sum + v, 0);
  const hasValues = Object.keys(values).length > 0;

  return (
    <Box>
      <Typography variant="subtitle1" gutterBottom>
        Values for {trade_date}
      </Typography>

      {unmapped && unmapped.length > 0 && (
        <Alert severity="warning" sx={{ mb: 2 }}>
          {unmapped.length} unmapped label(s). Add them in the Mappings tab.
          {unmapped.map((u) => (
            <Typography key={u.label} variant="body2">
              • {u.label} = {u.value}
            </Typography>
          ))}
        </Alert>
      )}

      <Grid container spacing={2}>
        {strategies
          .filter((s) => s.sheet_name !== "All BICs")
          .map((s) => (
            <Grid key={s.id} size={6}>
              <TextField
                label={s.sheet_name}
                type="number"
                size="small"
                fullWidth
                value={values[s.sheet_name] ?? 0}
                onChange={(e) => setValue(s.sheet_name, parseFloat(e.target.value) || 0)}
              />
            </Grid>
          ))}
      </Grid>

      {hasValues && (
        <Typography variant="h6" sx={{ mt: 2, fontWeight: 700 }}>
          Live Total: {money(total)}{" "}
          <Typography component="span" variant="body2" color="text.secondary">
            (All BICs subtotal: {money(allBicsSubtotal)})
          </Typography>
        </Typography>
      )}

      <Button
        variant="contained"
        startIcon={<SaveIcon />}
        sx={{ mt: 2 }}
        disabled={saving}
        onClick={() => onSave(values)}
      >
        {saving ? "Saving…" : "Save to Database"}
      </Button>
    </Box>
  );
}
