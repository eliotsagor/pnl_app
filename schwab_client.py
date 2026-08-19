"""Schwab Trader API access, used to get a real SPX 0DTE ATM straddle price
for the expected-move overlay on the Risk dashboard -- TradeSteward has no
options-chain data, and index tickers (^GSPC) have no listed options via
yfinance, so this is the only source for a market-implied expected move.

Auth uses schwab-py's OAuth wrapper: the first run opens a browser to Schwab's
login/consent page, then schwab-py exchanges the resulting code for a token
and refreshes it automatically afterwards. Client key/secret are stored in
Windows Credential Manager via keyring -- same pattern as
tradesteward_fetch.py's credential storage -- never written to disk in
plaintext. The refresh/access token pair itself is written by schwab-py to
TOKEN_PATH (its own on-disk cache, standard for this library); that file is
gitignored, just like the TradeSteward browser profile.

Run `python schwab_client.py --set-credentials` once per machine to store the
app key/secret, then `python schwab_client.py --login` once to do the
one-time browser consent (opens https://127.0.0.1:8080, the app's registered
callback URL). After that, get_client() just refreshes silently.
"""
from __future__ import annotations

import argparse
from pathlib import Path

KEYRING_SERVICE = "schwab_api"
KEYRING_KEY_ID = "__app_key__"
CALLBACK_URL = "https://127.0.0.1:8080"
TOKEN_PATH = Path.home() / ".schwab_token.json"


def _load_saved_credentials() -> tuple[str, str] | None:
    import keyring

    app_key = keyring.get_password(KEYRING_SERVICE, KEYRING_KEY_ID)
    if not app_key:
        return None
    app_secret = keyring.get_password(KEYRING_SERVICE, app_key)
    if not app_secret:
        return None
    return app_key, app_secret


def save_credentials(app_key: str, app_secret: str) -> None:
    import keyring

    keyring.set_password(KEYRING_SERVICE, KEYRING_KEY_ID, app_key)
    keyring.set_password(KEYRING_SERVICE, app_key, app_secret)


def clear_saved_credentials() -> None:
    import keyring

    app_key = keyring.get_password(KEYRING_SERVICE, KEYRING_KEY_ID)
    if app_key:
        try:
            keyring.delete_password(KEYRING_SERVICE, app_key)
        except keyring.errors.PasswordDeleteError:
            pass
        try:
            keyring.delete_password(KEYRING_SERVICE, KEYRING_KEY_ID)
        except keyring.errors.PasswordDeleteError:
            pass


def get_client(interactive: bool = True):
    """Return an authenticated schwab-py client. Reuses TOKEN_PATH if a
    valid token is already cached; otherwise (first run, or an expired
    refresh token) opens a browser for the OAuth consent flow -- requires
    interactive=True and a human at the machine."""
    import schwab

    creds = _load_saved_credentials()
    if not creds:
        raise RuntimeError(
            "No Schwab app credentials saved. Run "
            "`python schwab_client.py --set-credentials` first."
        )
    app_key, app_secret = creds
    return schwab.auth.easy_client(
        api_key=app_key,
        app_secret=app_secret,
        callback_url=CALLBACK_URL,
        token_path=str(TOKEN_PATH),
        interactive=interactive,
    )


def login_manual():
    """Copy-paste OAuth flow: prints the login URL, waits for you to paste
    back the full redirect URL after approving. Use this instead of
    get_client()'s automatic local-listener flow when that listener can't
    actually receive the callback (e.g. the browser refuses the self-signed
    HTTPS cert on 127.0.0.1 without ever showing a bypass option)."""
    import schwab

    creds = _load_saved_credentials()
    if not creds:
        raise RuntimeError(
            "No Schwab app credentials saved. Run "
            "`python schwab_client.py --set-credentials` first."
        )
    app_key, app_secret = creds
    return schwab.auth.client_from_manual_flow(
        api_key=app_key,
        app_secret=app_secret,
        callback_url=CALLBACK_URL,
        token_path=str(TOKEN_PATH),
    )


def spx_expected_move_remaining() -> dict:
    """Market-implied expected move for the rest of today's session, from the
    real SPX 0DTE ATM straddle (call mid + put mid at the strike closest to
    spot, expiring today) -- more accurate than a VIX-based estimate since it
    reads the actual market price traders are paying right now, no
    assumption that today's realized vol matches the 30-day VIX term.

    Returns {'spot': float, 'atm_strike': float, 'straddle_mid': float,
    'expected_move': float} or {} if today has no listed SPX expiration
    (e.g. a non-trading day) or the chain came back empty.

    expected_move ~= 0.8 * straddle_mid is the standard rule of thumb (a
    straddle's price overstates the 1-sigma move by roughly that factor
    because it also prices in tail risk) -- we return the raw straddle_mid
    too so the caller isn't locked into that constant.
    """
    from datetime import date

    client = get_client(interactive=False)
    today = date.today()
    resp = client.get_option_chain(
        "$SPX",
        contract_type=client.Options.ContractType.ALL,
        strike_count=1,
        include_underlying_quote=True,
        from_date=today,
        to_date=today,
    )
    resp.raise_for_status()
    data = resp.json()

    spot = (data.get("underlying") or {}).get("mark") or (data.get("underlying") or {}).get("last")
    call_map = data.get("callExpDateMap") or {}
    put_map = data.get("putExpDateMap") or {}
    if not spot or not call_map or not put_map:
        return {}

    def _atm_leg(exp_map: dict) -> dict | None:
        # exp_map: {"YYYY-MM-DD:DTE": {"<strike>": [ {contract}, ... ]}}
        for strikes in exp_map.values():
            closest = min(strikes.items(), key=lambda kv: abs(float(kv[0]) - spot))
            return {"strike": float(closest[0]), "contract": closest[1][0]}
        return None

    call_leg = _atm_leg(call_map)
    put_leg = _atm_leg(put_map)
    if not call_leg or not put_leg:
        return {}

    def _mid(contract: dict) -> float:
        bid = contract.get("bid") or 0.0
        ask = contract.get("ask") or 0.0
        if bid and ask:
            return (bid + ask) / 2
        return contract.get("mark") or contract.get("last") or 0.0

    straddle_mid = _mid(call_leg["contract"]) + _mid(put_leg["contract"])
    return {
        "spot": float(spot),
        "atm_strike": call_leg["strike"],
        "straddle_mid": straddle_mid,
        "expected_move": straddle_mid * 0.8,
    }


def _time_to_expiry_years(hours_remaining: float | None = None) -> float:
    """Years remaining until today's 0DTE expiry (4pm ET close). If
    hours_remaining isn't given, computes it from the current time."""
    if hours_remaining is None:
        import datetime
        import zoneinfo

        now = datetime.datetime.now(zoneinfo.ZoneInfo("America/New_York"))
        close = now.replace(hour=16, minute=0, second=0, microsecond=0)
        hours_remaining = max((close - now).total_seconds() / 3600, 0.0)
    # Trading-hours convention: 6.5h/day, ~252 trading days/year.
    return hours_remaining / 6.5 / 252


def touch_probability(spot: float, barrier: float, iv: float, years: float) -> float | None:
    """P(spot touches `barrier` at some point before expiry), via the
    reflection-principle approximation for a driftless geometric Brownian
    motion: P(touch) ~= 2 * Phi(-|ln(barrier/spot)| / (iv * sqrt(years))).

    Standard "probability of touching" formula used for barrier options;
    doubling the terminal-breach probability accounts for paths that cross
    the barrier intraday and drift back before expiry, which a terminal-only
    calculation would miss entirely -- relevant here since these are 0DTE
    stops that trigger on touch, not on where SPX ends up at the close.

    Returns None if inputs are degenerate (zero time/vol left, e.g. after
    the close) rather than a nonsensical answer.
    """
    import math

    if spot <= 0 or barrier <= 0 or iv <= 0 or years <= 0:
        return None
    z = abs(math.log(barrier / spot)) / (iv * math.sqrt(years))
    # Phi(-z) via the standard normal CDF, using erf (no scipy dependency).
    phi_neg_z = 0.5 * math.erfc(z / math.sqrt(2))
    return min(2 * phi_neg_z, 1.0)


def _atm_iv_and_spot(client, symbol: str = "$SPX") -> tuple[float, float] | None:
    """(spot, atm_iv) for today's 0DTE chain, atm_iv as a decimal (e.g. 0.13
    for 13%). Used as the touch-probability vol input for barriers defined
    directly in SPX terms (the "Points ITM" stop type, and general
    strike-touch queries) -- the ATM contract's own reported IV, not an
    assumption."""
    from datetime import date

    resp = client.get_option_chain(
        symbol,
        contract_type=client.Options.ContractType.CALL,
        strike_count=1,
        include_underlying_quote=True,
        from_date=date.today(),
        to_date=date.today(),
    )
    resp.raise_for_status()
    data = resp.json()
    spot = (data.get("underlying") or {}).get("mark") or (data.get("underlying") or {}).get("last")
    call_map = data.get("callExpDateMap") or {}
    if not spot or not call_map:
        return None
    for strikes in call_map.values():
        closest = min(strikes.items(), key=lambda kv: abs(float(kv[0]) - spot))
        iv = closest[1][0].get("volatility")
        if iv and iv > 0:
            return float(spot), float(iv) / 100
    return None


def strike_touch_probabilities(strikes: list[float]) -> dict:
    """{'spot': float, 'iv': float, 'probabilities': {strike: prob}} -- the
    plain probability that SPX itself touches each given strike before
    today's close, using the ATM contract's own IV. {} if unavailable."""
    client = get_client(interactive=False)
    atm = _atm_iv_and_spot(client)
    if not atm:
        return {}
    spot, iv = atm
    years = _time_to_expiry_years()
    probs = {}
    for k in strikes:
        p = touch_probability(spot, k, iv, years)
        if p is not None:
            probs[k] = p
    return {"spot": spot, "iv": iv, "probabilities": probs}


def option_chain_lookup(symbol: str = "$SPX") -> dict:
    """{(strike, 'C'|'P'): contract_dict} for every contract in today's 0DTE
    chain -- used to find each short leg's own bid/ask/IV for the
    option-price-barrier stop-probability calculation, since a stop defined
    in option-price terms (a $ or % loss) needs that specific contract's own
    vol, not the ATM contract's."""
    from datetime import date

    client = get_client(interactive=False)
    resp = client.get_option_chain(
        symbol,
        contract_type=client.Options.ContractType.ALL,
        include_underlying_quote=True,
        from_date=date.today(),
        to_date=date.today(),
    )
    resp.raise_for_status()
    data = resp.json()
    spot = (data.get("underlying") or {}).get("mark") or (data.get("underlying") or {}).get("last")
    out: dict = {"spot": float(spot) if spot else None, "contracts": {}}
    for side, exp_map in (("C", data.get("callExpDateMap") or {}), ("P", data.get("putExpDateMap") or {})):
        for strikes in exp_map.values():
            for strike_str, contracts in strikes.items():
                out["contracts"][(float(strike_str), side)] = contracts[0]
    return out


def option_price_barrier_probability(spot: float, strike: float, side: str, contract: dict, barrier_price: float) -> float | None:
    """P(this specific option's price crosses `barrier_price`) before
    expiry, by converting the option-price barrier into an implied SPX
    barrier via the contract's own delta (first-order local approximation:
    a dOptionPrice move corresponds to dOptionPrice / |delta| points of SPX
    movement), then applying the same touch-probability formula to that
    implied SPX level using the contract's own IV.

    This is an approximation, not a full path-dependent option-price
    barrier model (which would need to account for delta itself changing as
    spot moves) -- but for a same-day 0DTE stop a few points away, the
    local-linear approximation is standard practice and far better than
    ignoring the option's convexity/vol entirely.
    """
    delta = contract.get("delta")
    iv = contract.get("volatility")
    mark = contract.get("mark") or contract.get("last")
    if not delta or not iv or iv <= 0 or mark is None:
        return None
    delta = abs(delta)
    price_move_needed = barrier_price - mark  # positive: option needs to gain value to hit the stop
    spot_points_needed = price_move_needed / delta
    # A short call's price rises as spot rises; a short put's price rises as
    # spot falls -- so the SPX barrier is spot +points for a call's stop,
    # spot -points for a put's stop (points itself may be negative if the
    # option is already past its stop price).
    direction = 1 if side == "C" else -1
    implied_barrier = spot + direction * spot_points_needed
    years = _time_to_expiry_years()
    return touch_probability(spot, implied_barrier, iv / 100, years)


def _is_combined_stop_position(position: dict) -> bool:
    """True for a position whose stop is managed as one unit across both
    sides (a manually-triggered "Elmo" -- marked by "PAIC" in the bot name)
    rather than two independently-stopped verticals.

    "BIC" bots always stop each side separately even on the rare occasion
    they open as one two-sided position object, so that name takes explicit
    priority over "PAIC" if a name somehow contained both. Every other bot
    in practice (BIC-style "CALL only"/"PUT only" bots) already opens as a
    separate single-sided position per side anyway, so this only matters
    for the rare 4-leg both-sides-in-one-position case."""
    name = (position.get("bot_name") or "").upper()
    if "BIC" in name:
        return False
    return "PAIC" in name


def _leg_stop_probability(spot: float, contracts: dict, pos: dict, leg: dict, barrier: dict) -> float | None:
    key = (leg["strike"], leg["type"])
    if barrier["kind"] == "spot_price":
        # Use the specific contract's own IV if we have it, else skip rather
        # than guess with an unrelated vol figure.
        contract = contracts.get(key)
        iv = contract.get("volatility") if contract else None
        if not iv or iv <= 0:
            return None
        return touch_probability(spot, barrier["price"], iv / 100, _time_to_expiry_years())
    contract = contracts.get(key)
    if not contract:
        return None
    return option_price_barrier_probability(spot, leg["strike"], leg["type"], contract, barrier["price"])


def stop_probabilities_by_strike(positions: list[dict]) -> dict:
    """{(strike, 'C'|'P'): probability} -- the probability each short
    strike's stop actually triggers before today's close. Where a strike has
    multiple legs (several positions sharing it), returns their qty-weighted
    average probability.

    Most bots (BIC-style "CALL only"/"PUT only") already open as a separate
    single-sided position per side, so their two legs' stops are genuinely
    independent and each gets its own probability. A combined-stop position
    (an "Elmo" -- see _is_combined_stop_position) manages both sides as one
    unit, so both its strikes get the same combined probability: the chance
    *either* side triggers, P = 1 - (1-p_call)(1-p_put), treating the two
    touch events as roughly independent (a simplification -- SPX obviously
    can't be both far up and far down at once -- but a reasonable estimate
    without modeling their joint distribution).

    Skips legs with no parseable stop (resolve_stop_barrier returned None)
    or missing chain data for that specific contract -- callers should treat
    a strike absent from the result as "unknown", not "zero risk".
    """
    import tradesteward_fetch as tsf

    chain = option_chain_lookup()
    spot = chain.get("spot")
    contracts = chain.get("contracts", {})
    if not spot:
        return {}

    weighted: dict[tuple[float, str], list[tuple[float, float]]] = {}  # key -> [(prob, weight), ...]
    for pos in positions:
        sides = tsf.short_strikes_by_side(pos)
        combined = _is_combined_stop_position(pos) and sides["C"] and sides["P"]

        if combined:
            # One stop_target shared by both sides -- compute each side's own
            # probability against it, then fold them into a single combined
            # probability applied to every short leg in this position.
            leg_probs = []
            for side_legs in sides.values():
                for leg in side_legs:
                    barrier = tsf.resolve_stop_barrier(pos, leg)
                    if not barrier:
                        continue
                    p = _leg_stop_probability(spot, contracts, pos, leg, barrier)
                    if p is not None:
                        leg_probs.append(p)
            if not leg_probs:
                continue
            combined_prob = 1.0
            for p in leg_probs:
                combined_prob *= 1 - p
            combined_prob = 1 - combined_prob
            for side_legs in sides.values():
                for leg in side_legs:
                    key = (leg["strike"], leg["type"])
                    weighted.setdefault(key, []).append((combined_prob, -leg["qty"]))
            continue

        for leg_str in pos.get("legs", []):
            leg = tsf.parse_leg(leg_str)
            if not leg or leg["qty"] >= 0:
                continue  # only short legs carry a stop that closes *this* position
            barrier = tsf.resolve_stop_barrier(pos, leg)
            if not barrier:
                continue
            p = _leg_stop_probability(spot, contracts, pos, leg, barrier)
            if p is not None:
                key = (leg["strike"], leg["type"])
                weighted.setdefault(key, []).append((p, -leg["qty"]))

    out = {}
    for key, entries in weighted.items():
        total_w = sum(w for _, w in entries)
        if total_w:
            out[key] = sum(p * w for p, w in entries) / total_w
    return out


def position_expected_values(positions: list[dict]) -> dict:
    """{serial: {'stop_probability': float, 'ev': float}} -- for each open
    position, its own probability of being stopped (see
    stop_probabilities_by_strike for how combined-stop "Elmo" positions are
    handled) and the expected value of continuing to hold it, built from
    each short leg's own current price and stop price rather than the
    position's original entry-to-max-loss figures:

        loss_from_here = (stop_price - current_price) * qty * 100
        gain_from_here = current_price * qty * 100  (decay to worthless)
        EV = (1 - p_stop) * gain_from_here - p_stop * loss_from_here

    This matters because a position already sitting near max profit has
    very little room left to lose even with a nearby (high-probability)
    stop -- using the position's original max_loss (the entry-to-stop
    distance, not here-to-stop) would overstate the downside and make an
    already-winning trade look like a bad one to keep holding. A position
    at 95% of max profit with a 95% stop probability should show an EV
    close to its remaining premium, not a coin-flip against the full
    original risk, since "stopped" from here mostly means giving back a
    little, and "not stopped" mostly means banking what's left.

    Summed across a position's short legs (an Elmo's two sides both count,
    weighted by their own qty). A position with no resolvable stop or
    missing chain data for its legs is omitted -- treat an absent serial as
    "unknown," not "EV 0."
    """
    import tradesteward_fetch as tsf

    chain = option_chain_lookup()
    contracts = chain.get("contracts", {})
    if not chain.get("spot"):
        return {}

    stop_probs = stop_probabilities_by_strike(positions)

    out = {}
    for pos in positions:
        sides = tsf.short_strikes_by_side(pos)
        combined = _is_combined_stop_position(pos) and sides["C"] and sides["P"]

        all_legs = [leg for side_legs in sides.values() for leg in side_legs]
        leg_probs = [stop_probs.get((leg["strike"], leg["type"])) for leg in all_legs]
        leg_probs = [p for p in leg_probs if p is not None]
        if not leg_probs:
            continue
        p_stop = leg_probs[0] if combined else max(leg_probs)

        spot = chain["spot"]
        total_gain = 0.0
        total_loss = 0.0
        priced_any = False
        for leg in all_legs:
            barrier = tsf.resolve_stop_barrier(pos, leg)
            contract = contracts.get((leg["strike"], leg["type"]))
            current = contract.get("mark") if contract else None
            if current is None or barrier is None:
                continue

            if barrier["kind"] == "option_price":
                stop_price = barrier["price"]
            else:  # spot_price ("N Points ITM") -- convert via this leg's
                # own current delta (a local-linear step). Tried repricing
                # via Black-Scholes instead, but it diverges badly from
                # Schwab's own live 0DTE prices this close to expiry (real
                # 0DTE options don't price like vanilla BS at this range)
                # -- the delta-anchored estimate, while it has its own known
                # weakness (delta instability in the very final minutes),
                # is at least anchored to a real quoted greek rather than a
                # theoretical model that's demonstrably wrong here.
                delta = contract.get("delta")
                if not delta:
                    continue
                direction = 1 if leg["type"] == "C" else -1
                spot_points_to_stop = (barrier["price"] - spot) * direction
                stop_price = current + abs(delta) * spot_points_to_stop

            qty = -leg["qty"]  # positive short contract count
            total_gain += current * qty * 100
            total_loss += max(stop_price - current, 0.0) * qty * 100
            priced_any = True
        if not priced_any:
            continue

        # A defined-risk spread's long leg caps the real max loss (and its
        # short leg's own premium caps the real max gain) below what a
        # naive per-leg calc can imply -- clamp both against TradeSteward's
        # own stated ceilings for this position, which already account for
        # the full spread structure.
        max_profit = abs(tsf.parse_money(pos.get("max_profit", "0") or "0"))
        captured = max(tsf.parse_money(pos.get("profit_dollars", "0") or "0"), 0.0)
        remaining_ceiling = max(max_profit - captured, 0.0)
        at_risk_ceiling = abs(tsf.parse_money(pos.get("max_loss", "0") or "0"))
        total_gain = min(total_gain, remaining_ceiling) if remaining_ceiling else total_gain
        total_loss = min(total_loss, at_risk_ceiling) if at_risk_ceiling else total_loss

        ev = (1 - p_stop) * total_gain - p_stop * total_loss
        out[pos.get("serial")] = {"stop_probability": p_stop, "ev": ev}
    return out


def net_greeks(positions: list[dict]) -> dict:
    """Book-wide net delta and gamma (in underlying-equivalent shares, i.e.
    already multiplied by qty and the 100x SPX multiplier), summed across
    every leg of every open position -- unlike the stop-probability work,
    this includes long legs too, since a spread's net exposure depends on
    both sides.

    Also returns delta shocked +-10 points: a first-order (gamma) local
    approximation of how net delta would look after a 10pt move --
    delta_at(dS) = net_delta + net_gamma * dS -- using the book's current
    net gamma as a constant slope. This ignores gamma's own curvature
    (gamma isn't actually constant over a 10pt move) but is the standard
    quick estimate and matches what the two "delta at +-10pt" figures on a
    typical 0DTE risk panel represent.

    Returns {} if the chain isn't available; a leg whose specific contract
    is missing from the chain is skipped (not treated as zero exposure --
    the net figures are a best-effort sum over whatever legs we could
    price).
    """
    import tradesteward_fetch as tsf

    chain = option_chain_lookup()
    contracts = chain.get("contracts", {})
    if not chain.get("spot"):
        return {}

    net_delta = 0.0
    net_gamma = 0.0
    for pos in positions:
        for leg_str in pos.get("legs", []):
            leg = tsf.parse_leg(leg_str)
            if not leg:
                continue
            contract = contracts.get((leg["strike"], leg["type"]))
            if not contract:
                continue
            delta = contract.get("delta")
            gamma = contract.get("gamma")
            if delta is None or gamma is None:
                continue
            # leg["qty"] is already signed (short negative); Schwab's own
            # delta sign convention (put deltas negative) means qty * delta
            # gives the correct signed exposure without extra sign-flipping.
            net_delta += leg["qty"] * delta * 100
            net_gamma += leg["qty"] * gamma * 100

    return {
        "net_delta": net_delta,
        "net_gamma": net_gamma,
        "delta_at_minus_10": net_delta + net_gamma * -10,
        "delta_at_plus_10": net_delta + net_gamma * 10,
    }


def main():
    ap = argparse.ArgumentParser(description="Schwab API credential setup / login.")
    ap.add_argument(
        "--set-credentials",
        action="store_true",
        help="Store your Schwab app key/secret in Windows Credential Manager. "
        "Prompts for both (hidden input); never written to disk in plaintext.",
    )
    ap.add_argument("--clear-credentials", action="store_true", help="Remove saved app key/secret.")
    ap.add_argument(
        "--login",
        action="store_true",
        help="Run the one-time OAuth browser consent flow and cache the resulting token.",
    )
    ap.add_argument(
        "--login-manual",
        action="store_true",
        help="Same as --login, but copy-paste based instead of relying on a local "
        "listener catching the redirect automatically -- use this if --login's "
        "browser flow fails (e.g. a self-signed-cert warning with no bypass option).",
    )
    args = ap.parse_args()

    if args.set_credentials:
        import getpass

        app_key = input("Schwab app key: ").strip()
        app_secret = getpass.getpass("Schwab app secret: ")
        save_credentials(app_key, app_secret)
        print(">>> Saved Schwab app credentials to Windows Credential Manager.")
        return

    if args.clear_credentials:
        clear_saved_credentials()
        print(">>> Cleared saved Schwab app credentials.")
        return

    if args.login:
        get_client(interactive=True)
        print(f">>> Signed in. Token cached at {TOKEN_PATH}.")
        return

    if args.login_manual:
        login_manual()
        print(f">>> Signed in. Token cached at {TOKEN_PATH}.")
        return

    ap.print_help()


if __name__ == "__main__":
    main()
