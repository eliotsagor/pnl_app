import { useEffect, useState } from "react";
import {
  Accordion,
  AccordionDetails,
  AccordionSummary,
  Alert,
  Box,
  Button,
  Divider,
  Tab,
  Tabs,
  Typography,
} from "@mui/material";
import ExpandMoreIcon from "@mui/icons-material/ExpandMore";
import EventRepeatIcon from "@mui/icons-material/EventRepeat";
import LinkIcon from "@mui/icons-material/Link";
import PhotoCameraIcon from "@mui/icons-material/PhotoCamera";
import EditIcon from "@mui/icons-material/Edit";
import AutoAwesomeIcon from "@mui/icons-material/AutoAwesome";
import { DatePicker } from "@mui/x-date-pickers/DatePicker";
import dayjs, { type Dayjs } from "dayjs";
import { daysApi } from "../api/days";
import { screenshotApi, type ParseScreenshotResult } from "../api/screenshot";
import DayEditorForm from "../components/DayEditorForm";
import TradeStewardJobPanel from "../components/TradeStewardJobPanel";
import { money } from "../utils/money";
import { colorForValue } from "../utils/colors";

export default function EnterDayPage() {
  const [tradeDate, setTradeDate] = useState<Dayjs>(dayjs());
  const [tab, setTab] = useState(0);
  const isoDate = tradeDate.format("YYYY-MM-DD");

  // ---------- Fetch from TradeSteward tab ----------
  const [fetchResult, setFetchResult] = useState<{
    sheet_values: Record<string, number>;
    unmapped: { label: string; value: number }[];
    day_total: number;
  } | null>(null);
  const [fetchSaving, setFetchSaving] = useState(false);
  const [fetchSaved, setFetchSaved] = useState(false);
  const [backfillStart, setBackfillStart] = useState<Dayjs>(dayjs("2026-04-07"));
  const [backfillEnd, setBackfillEnd] = useState<Dayjs>(dayjs());

  useEffect(() => {
    setFetchResult(null);
    setFetchSaved(false);
  }, [isoDate]);

  const saveFetch = async (values: Record<string, number>) => {
    setFetchSaving(true);
    try {
      await daysApi.save(isoDate, values);
      setFetchSaved(true);
    } finally {
      setFetchSaving(false);
    }
  };

  // ---------- Manual tab ----------
  const [manualValues, setManualValues] = useState<Record<string, number> | null>(null);
  const [manualSaving, setManualSaving] = useState(false);
  const [manualSaved, setManualSaved] = useState(false);

  useEffect(() => {
    setManualValues(null);
    setManualSaved(false);
    daysApi.get(isoDate).then(setManualValues);
  }, [isoDate]);

  const saveManual = async (values: Record<string, number>) => {
    setManualSaving(true);
    try {
      await daysApi.save(isoDate, values);
      setManualSaved(true);
    } finally {
      setManualSaving(false);
    }
  };

  // ---------- Upload Screenshot tab ----------
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<string | null>(null);
  const [parsing, setParsing] = useState(false);
  const [parsed, setParsed] = useState<ParseScreenshotResult | null>(null);
  const [parseError, setParseError] = useState<string | null>(null);
  const [uploadSaving, setUploadSaving] = useState(false);
  const [uploadSaved, setUploadSaved] = useState(false);

  const onFileChange = (f: File | null) => {
    setFile(f);
    setParsed(null);
    setParseError(null);
    setUploadSaved(false);
    setPreview(f ? URL.createObjectURL(f) : null);
  };

  const doParse = async () => {
    if (!file) return;
    setParsing(true);
    setParseError(null);
    try {
      const result = await screenshotApi.parse(file);
      setParsed(result);
    } catch (e) {
      setParseError((e as Error).message);
    } finally {
      setParsing(false);
    }
  };

  const saveUpload = async (values: Record<string, number>) => {
    setUploadSaving(true);
    try {
      await daysApi.save(isoDate, values);
      setUploadSaved(true);
    } finally {
      setUploadSaving(false);
    }
  };

  return (
    <Box sx={{ maxWidth: 1600, mx: "auto", px: 3, pb: 4 }}>
      <Box sx={{ mb: 2, maxWidth: 240 }}>
        <DatePicker
          label="Trade date"
          value={tradeDate}
          onChange={(v) => v && setTradeDate(v)}
          slotProps={{ textField: { size: "small", fullWidth: true } }}
        />
      </Box>

      <Tabs value={tab} onChange={(_, v) => setTab(v)} sx={{ mb: 2 }}>
        <Tab icon={<LinkIcon fontSize="small" />} iconPosition="start" label="Fetch from TradeSteward" />
        <Tab icon={<PhotoCameraIcon fontSize="small" />} iconPosition="start" label="Upload Screenshot" />
        <Tab icon={<EditIcon fontSize="small" />} iconPosition="start" label="Manual Entry" />
      </Tabs>

      {tab === 0 && (
        <Box>
          <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
            Pulls the day's per-strategy P&L straight from TradeSteward — no screenshot, exact numbers. TradeSteward
            requires a fresh sign-in (passkey or password) each run, so this opens a browser window — log in there,
            then it continues automatically.
          </Typography>

          <TradeStewardJobPanel
            mode="fetch-day"
            tradeDate={isoDate}
            buttonLabel="Fetch this day"
            onDone={(result) => setFetchResult(result)}
          />

          {fetchResult && (
            <>
              <Divider sx={{ my: 2 }} />
              <Typography variant="h6" sx={{ mb: 2, fontWeight: 700 }}>
                Day total (bot trades): {money(fetchResult.day_total)}
              </Typography>
              <DayEditorForm
                key={`fetch-${isoDate}`}
                trade_date={isoDate}
                initialValues={fetchResult.sheet_values}
                unmapped={fetchResult.unmapped}
                onSave={saveFetch}
                saving={fetchSaving}
              />
              {fetchSaved && (
                <Alert severity="success" sx={{ mt: 2 }}>
                  Saved {isoDate}
                </Alert>
              )}
            </>
          )}

          <Divider sx={{ my: 3 }} />
          <Accordion sx={{ border: "1px solid rgba(255,255,255,0.10)", borderRadius: "12px !important", "&:before": { display: "none" } }}>
            <AccordionSummary expandIcon={<ExpandMoreIcon />}>
              <Box sx={{ display: "flex", alignItems: "center", gap: 1 }}>
                <EventRepeatIcon fontSize="small" />
                <Typography>Backfill a date range</Typography>
              </Box>
            </AccordionSummary>
            <AccordionDetails>
              <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
                Fetches every weekday in the range in one session and saves each day.
              </Typography>
              <Box sx={{ display: "flex", gap: 2, mb: 2, maxWidth: 500 }}>
                <DatePicker
                  label="From"
                  value={backfillStart}
                  onChange={(v) => v && setBackfillStart(v)}
                  slotProps={{ textField: { size: "small", fullWidth: true } }}
                />
                <DatePicker
                  label="To"
                  value={backfillEnd}
                  onChange={(v) => v && setBackfillEnd(v)}
                  slotProps={{ textField: { size: "small", fullWidth: true } }}
                />
              </Box>
              <TradeStewardJobPanel
                mode="backfill"
                backfillStart={backfillStart.format("YYYY-MM-DD")}
                backfillEnd={backfillEnd.format("YYYY-MM-DD")}
                buttonLabel="Run backfill"
              />
            </AccordionDetails>
          </Accordion>
        </Box>
      )}

      {tab === 1 && (
        <Box>
          <Box sx={{ display: "flex", alignItems: "center", gap: 2, mb: 2 }}>
            <Button component="label" variant="outlined">
              Choose screenshot
              <input
                type="file"
                accept="image/png,image/jpeg"
                hidden
                onChange={(e) => onFileChange(e.target.files?.[0] ?? null)}
              />
            </Button>
            {file && (
              <Button variant="contained" startIcon={<AutoAwesomeIcon />} onClick={doParse} disabled={parsing}>
                {parsing ? "Parsing…" : "Parse with Claude"}
              </Button>
            )}
          </Box>

          {preview && <img src={preview} alt="screenshot preview" style={{ maxWidth: 400, borderRadius: 8 }} />}

          {parseError && (
            <Alert severity="error" sx={{ mt: 2 }}>
              {parseError}
            </Alert>
          )}

          {parsed && (
            <>
              <Divider sx={{ my: 2 }} />
              <Typography variant="subtitle2" gutterBottom>
                Parsed lines from screenshot:
              </Typography>
              {parsed.lines.map((l) => (
                <Typography key={l.label} variant="body2" sx={{ color: colorForValue(l.value) }}>
                  ● {l.label}: {money(l.value)}
                </Typography>
              ))}

              {parsed.total !== null && (
                <Typography variant="body2" sx={{ mt: 1 }}>
                  Headline total in screenshot: {money(parsed.total)}
                </Typography>
              )}
              {parsed.total !== null &&
                (Math.abs(parsed.computed_total - parsed.total) < 0.01 ? (
                  <Alert severity="success" sx={{ mt: 1 }}>
                    Computed total {money(parsed.computed_total)} matches screenshot
                  </Alert>
                ) : (
                  <Alert severity="warning" sx={{ mt: 1 }}>
                    Computed {money(parsed.computed_total)} ≠ screenshot {money(parsed.total)}
                  </Alert>
                ))}

              <Divider sx={{ my: 2 }} />
              <DayEditorForm
                key={`upload-${isoDate}-${file?.name}`}
                trade_date={isoDate}
                initialValues={parsed.sheet_values}
                unmapped={parsed.unmapped}
                onSave={saveUpload}
                saving={uploadSaving}
              />
              {uploadSaved && (
                <Alert severity="success" sx={{ mt: 2 }}>
                  Saved {isoDate}
                </Alert>
              )}
            </>
          )}
        </Box>
      )}

      {tab === 2 && manualValues !== null && (
        <Box>
          <DayEditorForm
            key={`manual-${isoDate}`}
            trade_date={isoDate}
            initialValues={manualValues}
            onSave={saveManual}
            saving={manualSaving}
          />
          {manualSaved && (
            <Alert severity="success" sx={{ mt: 2 }}>
              Saved {isoDate}
            </Alert>
          )}
        </Box>
      )}
    </Box>
  );
}
