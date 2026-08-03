import { useEffect, useState } from "react";
import { Box, Button, Typography } from "@mui/material";
import FileDownloadIcon from "@mui/icons-material/FileDownload";
import TableViewIcon from "@mui/icons-material/TableView";
import { exportApi } from "../api/exportApi";

export default function ExportPage() {
  const [days, setDays] = useState<number | null>(null);
  const [ready, setReady] = useState<{ blob: Blob; filename: string } | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    exportApi.stats().then((s) => setDays(s.days_with_data));
  }, []);

  const generate = async () => {
    setBusy(true);
    try {
      const result = await exportApi.generate();
      setReady(result);
    } finally {
      setBusy(false);
    }
  };

  const download = () => {
    if (!ready) return;
    const url = URL.createObjectURL(ready.blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = ready.filename;
    a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <Box sx={{ maxWidth: 1600, mx: "auto", px: 3, pb: 4 }}>
      <Typography variant="h6" gutterBottom>
        Export to Excel
      </Typography>
      <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
        Generates an .xlsx file matching the original layout. Uses the template file as a base so all conditional
        formatting (red/green) is preserved.
      </Typography>

      {!ready ? (
        <Button variant="contained" startIcon={<TableViewIcon />} onClick={generate} disabled={busy}>
          {busy ? "Generating…" : "Generate Excel file"}
        </Button>
      ) : (
        <Button variant="contained" startIcon={<FileDownloadIcon />} onClick={download}>
          Download {ready.filename}
        </Button>
      )}

      {days !== null && (
        <Typography variant="body2" color="text.secondary" sx={{ mt: 3 }}>
          Database contains {days} days of data.
        </Typography>
      )}
    </Box>
  );
}
