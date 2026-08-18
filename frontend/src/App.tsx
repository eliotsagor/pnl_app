import { Routes, Route, Navigate } from "react-router-dom";
import { CssBaseline } from "@mui/material";
import TopNav from "./components/TopNav";
import EnterDayPage from "./pages/EnterDayPage";
import CustomTradesPage from "./pages/CustomTradesPage";
import CalendarPage from "./pages/CalendarPage";
import CalendarIndexRedirect from "./pages/CalendarIndexRedirect";
import YearViewPage from "./pages/YearViewPage";
import StrategyYearPage from "./pages/StrategyYearPage";
import MappingsPage from "./pages/MappingsPage";
import ExportPage from "./pages/ExportPage";
import PositionsPage from "./pages/PositionsPage";

export default function App() {
  return (
    <>
      <CssBaseline />
      <TopNav />
      <Routes>
        <Route path="/" element={<Navigate to="/enter-day" replace />} />
        <Route path="/enter-day" element={<EnterDayPage />} />
        <Route path="/custom-trades" element={<CustomTradesPage />} />
        <Route path="/calendar" element={<CalendarIndexRedirect />} />
        <Route path="/calendar/:year/:month" element={<CalendarPage />} />
        <Route path="/year-view" element={<YearViewPage />} />
        <Route path="/strategy-year/:year/:sheet" element={<StrategyYearPage />} />
        <Route path="/total-year/:year" element={<StrategyYearPage kind="total" />} />
        <Route path="/all-bics-year/:year" element={<StrategyYearPage kind="all-bics" />} />
        <Route path="/mappings" element={<MappingsPage />} />
        <Route path="/positions" element={<PositionsPage />} />
        <Route path="/export" element={<ExportPage />} />
      </Routes>
    </>
  );
}
