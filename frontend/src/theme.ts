import { createTheme } from "@mui/material/styles";

// Mirrors .streamlit/config.toml's palette so the visual identity carries over.
export const theme = createTheme({
  palette: {
    mode: "dark",
    background: { default: "#0d0d0d", paper: "#1a1a19" },
    primary: { main: "#3987e5" },
  },
  shape: { borderRadius: 12 },
});

export const COLOR_GOOD = "#0ca30c";
export const COLOR_CRITICAL = "#d03b3b";
export const COLOR_WARNING = "#d0a13b";
