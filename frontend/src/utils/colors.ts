import { COLOR_GOOD, COLOR_CRITICAL } from "../theme";

export function colorForValue(v: number): string {
  return v >= 0 ? COLOR_GOOD : COLOR_CRITICAL;
}

export function tintForValue(v: number, alpha = 0.12): string {
  return v >= 0 ? `rgba(12,163,12,${alpha})` : `rgba(208,59,59,${alpha})`;
}

export function borderForValue(v: number, alpha = 0.35): string {
  return v >= 0 ? `rgba(12,163,12,${alpha})` : `rgba(208,59,59,${alpha})`;
}
