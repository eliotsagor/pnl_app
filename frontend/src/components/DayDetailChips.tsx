import { Box, Card, CardContent, Chip, CircularProgress, Typography } from "@mui/material";
import { money } from "../utils/money";
import { tintForValue, colorForValue } from "../utils/colors";

interface Props {
  isoDate: string | null;
  detail: Record<string, number> | null;
  loading: boolean;
}

export default function DayDetailChips({ isoDate, detail, loading }: Props) {
  return (
    <Card sx={{ mt: 2, minHeight: 76 }}>
      <CardContent sx={{ py: "10px !important" }}>
        {!isoDate ? (
          <Typography variant="body2" color="text.secondary">
            Click a day above to see its breakdown.
          </Typography>
        ) : (
          <>
            <Typography variant="subtitle2" color="text.secondary" gutterBottom>
              {isoDate}
            </Typography>
            {loading ? (
              <CircularProgress size={18} />
            ) : (
              <Box sx={{ display: "flex", flexWrap: "wrap", gap: 1 }}>
                {Object.entries(detail ?? {}).map(([sheet, v]) => (
                  <Chip
                    key={sheet}
                    size="small"
                    label={`${sheet}: ${money(v)}`}
                    sx={{ bgcolor: tintForValue(v, 0.15), color: colorForValue(v), fontWeight: 600 }}
                  />
                ))}
              </Box>
            )}
          </>
        )}
      </CardContent>
    </Card>
  );
}
