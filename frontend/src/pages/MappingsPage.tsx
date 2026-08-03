import { useEffect, useState } from "react";
import { Alert, Box, Button, Card, CardContent, MenuItem, Select, TextField, Typography } from "@mui/material";
import { mappingsApi } from "../api/mappings";
import { daysApi } from "../api/days";
import type { Mapping, Strategy } from "../api/types";

export default function MappingsPage() {
  const [mappings, setMappings] = useState<Mapping[]>([]);
  const [strategies, setStrategies] = useState<Strategy[]>([]);
  const [label, setLabel] = useState("");
  const [sheet, setSheet] = useState("");
  const [error, setError] = useState<string | null>(null);

  const load = () => mappingsApi.list().then(setMappings);

  useEffect(() => {
    load();
    daysApi.strategies().then((s) => {
      setStrategies(s);
      if (s.length) setSheet(s[0].sheet_name);
    });
  }, []);

  const submit = async () => {
    if (!label) return;
    setError(null);
    try {
      await mappingsApi.add(label, sheet);
      setLabel("");
      load();
    } catch (e) {
      setError((e as Error).message);
    }
  };

  return (
    <Box sx={{ maxWidth: 1600, mx: "auto", px: 3, pb: 4 }}>
      <Typography variant="h6" gutterBottom>
        Screenshot Label → Sheet Mappings
      </Typography>
      <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
        When the parser sees a label on the left, it puts the value on the sheet on the right. Multiple labels
        can map to one sheet and the values get summed.
      </Typography>

      <Box sx={{ mb: 3 }}>
        {mappings.map((m) => (
          <Typography key={m.screenshot_label} variant="body2" sx={{ fontFamily: "monospace" }}>
            '{m.screenshot_label}' → {m.sheet_name}
          </Typography>
        ))}
      </Box>

      <Card sx={{ p: 2, maxWidth: 500 }}>
        <CardContent>
          <Typography variant="subtitle2" gutterBottom>
            Add a new mapping
          </Typography>
          {error && (
            <Alert severity="error" sx={{ mb: 2 }}>
              {error}
            </Alert>
          )}
          <TextField
            label="Screenshot label (exact text as shown)"
            fullWidth
            size="small"
            value={label}
            onChange={(e) => setLabel(e.target.value)}
            sx={{ mb: 2 }}
          />
          <Select fullWidth size="small" value={sheet} onChange={(e) => setSheet(e.target.value)} sx={{ mb: 2 }}>
            {strategies.map((s) => (
              <MenuItem key={s.id} value={s.sheet_name}>
                {s.sheet_name}
              </MenuItem>
            ))}
          </Select>
          <Button variant="contained" onClick={submit}>
            Add mapping
          </Button>
        </CardContent>
      </Card>
    </Box>
  );
}
