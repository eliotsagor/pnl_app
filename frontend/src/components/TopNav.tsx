import { Box, ToggleButton, ToggleButtonGroup, Typography } from "@mui/material";
import { useNavigate, useLocation } from "react-router-dom";
import AnalyticsIcon from "@mui/icons-material/Analytics";
import EditCalendarIcon from "@mui/icons-material/EditCalendar";
import CalculateIcon from "@mui/icons-material/Calculate";
import CalendarMonthIcon from "@mui/icons-material/CalendarMonth";
import TableChartIcon from "@mui/icons-material/TableChart";
import RouteIcon from "@mui/icons-material/Route";
import FileDownloadIcon from "@mui/icons-material/FileDownload";
import ShowChartIcon from "@mui/icons-material/ShowChart";
import WarningAmberIcon from "@mui/icons-material/WarningAmber";

const NAV_ITEMS = [
  { path: "/enter-day", label: "Enter Day", icon: <EditCalendarIcon fontSize="small" /> },
  { path: "/custom-trades", label: "Custom Trades", icon: <CalculateIcon fontSize="small" /> },
  { path: "/calendar", label: "Calendar", icon: <CalendarMonthIcon fontSize="small" /> },
  { path: "/year-view", label: "Year View", icon: <TableChartIcon fontSize="small" /> },
  { path: "/positions", label: "Positions", icon: <ShowChartIcon fontSize="small" /> },
  { path: "/risk", label: "Risk", icon: <WarningAmberIcon fontSize="small" /> },
  { path: "/mappings", label: "Mappings", icon: <RouteIcon fontSize="small" /> },
  { path: "/export", label: "Export", icon: <FileDownloadIcon fontSize="small" /> },
];

export default function TopNav() {
  const navigate = useNavigate();
  const location = useLocation();
  const active = location.pathname.startsWith("/strategy-year")
    ? "/year-view"
    : NAV_ITEMS.find((n) => location.pathname.startsWith(n.path))?.path ?? "/enter-day";

  return (
    <Box sx={{ maxWidth: 1600, mx: "auto", px: 3, pt: 3 }}>
      <Typography variant="h5" sx={{ display: "flex", alignItems: "center", gap: 1, mb: 2, fontWeight: 600 }}>
        <AnalyticsIcon /> Daily P&L Tracker
      </Typography>
      <ToggleButtonGroup
        value={active}
        exclusive
        onChange={(_, val) => val && navigate(val)}
        sx={{
          bgcolor: "background.paper",
          border: "1px solid rgba(255,255,255,0.10)",
          borderRadius: "12px",
          p: "4px",
          mb: 3,
          "& .MuiToggleButton-root": {
            border: "none",
            borderRadius: "9px !important",
            textTransform: "none",
            fontWeight: 500,
            gap: 0.75,
            px: 1.5,
          },
        }}
      >
        {NAV_ITEMS.map((item) => (
          <ToggleButton key={item.path} value={item.path}>
            {item.icon}
            {item.label}
          </ToggleButton>
        ))}
      </ToggleButtonGroup>
    </Box>
  );
}
