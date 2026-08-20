import type { Position, StrikeRow } from "../api/types";

const LEG_RE = /^(-?\d+)\s+\S+\s+.*?(\d+(?:\.\d+)?)([CP])$/;

export interface Leg {
  qty: number;
  strike: number;
  type: "C" | "P";
}

export function parseLeg(leg: string): Leg | null {
  const m = LEG_RE.exec(leg.trim());
  if (!m) return null;
  return { qty: parseInt(m[1], 10), strike: parseFloat(m[2]), type: m[3] as "C" | "P" };
}

function parseMoney(s: string | undefined): number {
  if (!s) return 0;
  const negative = s.trim().startsWith("-") || s.trim().startsWith("(");
  const cleaned = s.replace(/[$,()\-]/g, "").trim();
  if (!cleaned) return 0;
  const value = parseFloat(cleaned);
  return negative ? -value : value;
}

function shortStrikesBySide(position: Position): { C: Leg[]; P: Leg[] } {
  const out: { C: Leg[]; P: Leg[] } = { C: [], P: [] };
  for (const legStr of position.legs) {
    const leg = parseLeg(legStr);
    if (leg && leg.qty < 0) out[leg.type].push(leg);
  }
  return out;
}

/** Client-side re-implementation of tradesteward_fetch.aggregate_short_strikes
 * + the stop_probability/ev attachment done server-side, so the strikes
 * table can be recomputed live from an arbitrary filtered subset of
 * positions (the Elmo/BIC/Other and per-bot checkboxes) without a round trip.
 * Per-strike stop_probability is the qty-weighted average of the
 * contributing positions' own stop_probability (already resolved
 * server-side, including the Elmo combined-stop handling), which reproduces
 * the same numbers the backend computes for the unfiltered case. ev uses
 * that same per-strike stop_probability against this strike's own already-
 * split remaining/at_risk, matching the backend's model. */
export function aggregateShortStrikes(positions: Position[]): StrikeRow[] {
  const rows = new Map<string, StrikeRow & { probWeighted: number; probWeight: number }>();

  for (const pos of positions) {
    const sides = shortStrikesBySide(pos);
    const hasCall = sides.C.length > 0;
    const hasPut = sides.P.length > 0;

    // Real $ given back from today's value if the stop triggers (computed
    // server-side by position_give_back, exposed as pos.at_risk), not the
    // static entry-based max_loss -- a position sitting on banked profit
    // has a much bigger give-back than its original defined risk. Falls
    // back to max_loss if the server didn't attach it (e.g. an older
    // cached result).
    const atRisk = pos.at_risk != null ? pos.at_risk : Math.abs(parseMoney(pos.max_loss));
    const captured = Math.max(parseMoney(pos.profit_dollars), 0);
    // What's left to capture if this decays to worthless by expiry
    // (server-side position_remaining_value, exposed as pos.remaining),
    // not max_profit-minus-captured -- that reads $0 whenever TradeSteward
    // has no profit_target set, since its max_profit field just mirrors
    // current profit in that case rather than being a real ceiling.
    const remaining = pos.remaining != null ? pos.remaining : Math.max(Math.abs(parseMoney(pos.max_profit)) - captured, 0);

    for (const side of ["C", "P"] as const) {
      const legs = sides[side];
      if (legs.length === 0) continue;
      // Weighted by each side's own live option value (server-computed,
      // exposed as pos.side_split), not a flat 50/50 -- falls back to 0.5
      // if the server didn't attach it (e.g. an older cached result).
      const share = !hasCall || !hasPut ? 1.0 : (pos.side_split?.[side] ?? 0.5);
      const sideQty = legs.reduce((s, l) => s + -l.qty, 0);
      for (const leg of legs) {
        const key = `${side}${leg.strike}`;
        let row = rows.get(key);
        if (!row) {
          row = {
            type: side,
            strike: leg.strike,
            qty: 0,
            captured: 0,
            remaining: 0,
            at_risk: 0,
            positions: 0,
            is_bic: false,
            is_elmo: false,
            probWeighted: 0,
            probWeight: 0,
          };
          rows.set(key, row);
        }
        const legQty = -leg.qty;
        row.qty += legQty;
        if (sideQty) {
          const frac = share * (legQty / sideQty);
          row.captured += captured * frac;
          row.remaining += remaining * frac;
          row.at_risk += atRisk * frac;
        }
        row.positions += 1;
        row.is_bic = row.is_bic || pos.is_bic;
        row.is_elmo = row.is_elmo || pos.is_elmo;
        if (pos.stop_probability != null) {
          row.probWeighted += pos.stop_probability * legQty;
          row.probWeight += legQty;
        }
      }
    }
  }

  return Array.from(rows.values())
    .map((r) => {
      const { probWeighted, probWeight, ...row } = r;
      if (probWeight > 0) {
        const p = probWeighted / probWeight;
        row.stop_probability = p;
        // Same model as the EV-of-holding table: (1-p_stop) x what's left
        // if this decays to worthless, minus p_stop x the real give-back
        // to the stop -- doesn't need a separate P(capture) estimate since
        // "not stopped" is tied to a realistic (not maximal) payoff.
        row.ev = (1 - p) * row.remaining - p * row.at_risk;
      }
      return row;
    })
    .sort((a, b) => (a.type === "C" ? 1 : 0) - (b.type === "C" ? 1 : 0) || a.strike - b.strike);
}

export interface NetGreeksResult {
  net_delta: number;
  net_gamma: number;
  delta_at_minus_10: number;
  delta_at_plus_10: number;
}

/** Sums each filtered position's own already-computed delta/gamma (both
 * short and long legs, from position_expected_values server-side) --
 * doesn't need the option chain since those per-position figures are
 * already resolved. */
export function netGreeksFor(positions: Position[]): NetGreeksResult | null {
  const priced = positions.filter((p) => p.delta != null && p.gamma != null);
  if (priced.length === 0) return null;
  const netDelta = priced.reduce((s, p) => s + (p.delta ?? 0), 0);
  const netGamma = priced.reduce((s, p) => s + (p.gamma ?? 0), 0);
  return {
    net_delta: netDelta,
    net_gamma: netGamma,
    delta_at_minus_10: netDelta + netGamma * -10,
    delta_at_plus_10: netDelta + netGamma * 10,
  };
}
