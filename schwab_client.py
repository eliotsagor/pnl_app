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


def _leg_stop_probability(spot: float, contracts: dict, pos: dict, leg: dict, barrier: dict) -> float | None:
    """Probability this one leg's own stop triggers -- only meaningful for
    a 'leg'-scope barrier (Points ITM), which is genuinely tied to one
    strike. Callers must not call this for a 'position'-scope barrier
    ($/% Loss, or a live trail) -- see position_stop_probability instead,
    since those stops are evaluated against the position's combined value,
    not any single leg's own price."""
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


def _is_combined_move_position(position: dict) -> bool:
    """True for a position whose short legs genuinely move together as one
    combined price (an "Elmo" -- bot name contains "PAIC" -- which trades
    like a short strangle: both sides' option prices contribute to the same
    combined stop threshold). False for a BIC-style position, where each
    side is its own independent vertical even on the rare occasion a call
    side and put side happen to open as one position object -- BICs stop
    each side separately, so the *other* side's delta must not be used to
    help "offset" a side's own move toward its stop the way it legitimately
    would for a true combined (net-delta) position."""
    return "PAIC" in (position.get("bot_name") or "").upper()


def position_side_stop_probability(spot: float, contracts: dict, pos: dict, side: str) -> float | None:
    """For a 'position'-scope stop ($X Loss, X% Loss, or a live trail --
    see resolve_stop_barrier), the probability that spot moves far enough
    to push the combined option price to its stop threshold, attributed to
    `side` for display in the strikes table (which shows one row per
    strike).

    The sensitivity used to convert the combined $ distance into an implied
    SPX distance depends on whether this position's sides genuinely share
    one combined price or are independently-stopped verticals that happen
    to share a position object (see _is_combined_move_position):

    - Combined (Elmo, trades like a short strangle): both legs' prices
      move as spot moves and both contribute to reaching the combined
      stop, so this uses the *net* delta across every short leg (both
      sides), not just this side's own -- the put side's delta doesn't
      fully cancel the call side's, since both are short (same-signed
      exposure to a strangle-style position), so netting them still gives
      a real, usually larger, combined sensitivity than either side alone.
    - Independent (BIC-style, even if opened as one two-sided object):
      only this side's own delta is used, since a move in the *other*
      side's strike doesn't push *this* side's vertical toward its own
      stop -- each side is genuinely its own trade.

    Both cases produce the same probability on both strike rows only when
    combined; independent positions can show a different probability per
    side, correctly.
    """
    import tradesteward_fetch as tsf

    sides = tsf.short_strikes_by_side(pos)
    side_legs = sides.get(side, [])
    if not side_legs:
        return None
    barrier = tsf.resolve_stop_barrier(pos, side_legs[0])
    if not barrier or barrier["scope"] != "position":
        return None
    current = tsf.current_combined_price(pos)
    if current is None:
        return None

    legs_for_delta = (sides["C"] + sides["P"]) if _is_combined_move_position(pos) else side_legs

    net_delta = 0.0
    iv_weighted = 0.0
    iv_weight = 0.0
    for leg in legs_for_delta:
        contract = contracts.get((leg["strike"], leg["type"]))
        if not contract:
            continue
        delta = contract.get("delta")
        iv = contract.get("volatility")
        qty = abs(leg["qty"])
        if delta is not None:
            net_delta += abs(delta) * qty
        if iv:
            iv_weighted += iv * qty
            iv_weight += qty
    if net_delta <= 0 or iv_weight <= 0:
        return None
    avg_iv = iv_weighted / iv_weight

    price_move_needed = barrier["price"] - current
    spot_points_needed = price_move_needed / net_delta
    # A short call's combined-price contribution rises as spot rises; a
    # short put's rises as spot falls -- same convention as
    # option_price_barrier_probability's single-leg case. For a combined
    # position this reflects the direction *this side* moves toward the
    # stop, which is the direction shown on this side's strike row, even
    # though the delta magnitude used includes both sides.
    direction = 1 if side == "C" else -1
    implied_barrier = spot + direction * spot_points_needed
    years = _time_to_expiry_years()
    return touch_probability(spot, implied_barrier, avg_iv / 100, years)


def stop_probabilities_by_strike(positions: list[dict]) -> dict:
    """{(strike, 'C'|'P'): probability} -- the probability each short
    strike's stop actually triggers before today's close. Where a strike has
    multiple legs (several positions sharing it), returns their qty-weighted
    average probability.

    Branches on each position's resolved stop barrier scope (see
    resolve_stop_barrier):

    - 'leg' scope ("N Points ITM"): genuinely tied to one strike --
      _leg_stop_probability as before.
    - 'position' scope ($X Loss, X% Loss, a live trail): evaluated against
      the position's *combined* value, not any single leg's own price. For
      a one-sided position (a normal vertical) this reduces to that one
      side's own probability. For a two-sided combined-stop position (an
      Elmo, which stops like a short strangle -- either side's move can
      push the combined price to the stop), position_side_stop_probability
      gives each side's own share of that risk, which is what the strikes
      table needs for per-strike attribution -- not a single merged
      "did the position stop at all" figure.

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
        all_short_legs = sides["C"] + sides["P"]
        if not all_short_legs:
            continue
        barrier = tsf.resolve_stop_barrier(pos, all_short_legs[0])
        if not barrier:
            continue

        if barrier["scope"] == "position":
            for side, side_legs in sides.items():
                if not side_legs:
                    continue
                p = position_side_stop_probability(spot, contracts, pos, side)
                if p is None:
                    continue
                for leg in side_legs:
                    key = (leg["strike"], leg["type"])
                    weighted.setdefault(key, []).append((p, -leg["qty"]))
            continue

        for leg in all_short_legs:
            leg_barrier = tsf.resolve_stop_barrier(pos, leg)
            if not leg_barrier:
                continue
            p = _leg_stop_probability(spot, contracts, pos, leg, leg_barrier)
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
    """{serial: {'stop_probability': float, 'ev': float, 'delta': float,
    'gamma': float}} -- for each open position, its own probability of
    being stopped (see
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
        all_legs = [leg for side_legs in sides.values() for leg in side_legs]
        if not all_legs:
            continue
        leg_probs = [stop_probs.get((leg["strike"], leg["type"])) for leg in all_legs]
        leg_probs = [p for p in leg_probs if p is not None]
        if not leg_probs:
            continue
        # A two-sided position's two sides carry the same per-side risk-share
        # probability already (see stop_probabilities_by_strike), not
        # independent events, so the position's own overall stop chance is
        # the higher of the two -- taking the max avoids double counting the
        # same combined stop as if call and put were separate risks.
        p_stop = max(leg_probs)

        # This position's own net delta/gamma -- unlike net_greeks (book-wide),
        # this is scoped to just this position's legs (both short and long,
        # since a spread's own risk depends on its full structure), so you can
        # see which specific trade is driving exposure independent of whatever
        # else in the book might be offsetting it.
        pos_delta = 0.0
        pos_gamma = 0.0
        for leg_str in pos.get("legs", []):
            leg_full = tsf.parse_leg(leg_str)
            if not leg_full:
                continue
            c = contracts.get((leg_full["strike"], leg_full["type"]))
            if not c or c.get("delta") is None or c.get("gamma") is None:
                continue
            pos_delta += leg_full["qty"] * c["delta"] * 100
            pos_gamma += leg_full["qty"] * c["gamma"] * 100

        spot = chain["spot"]
        barrier = tsf.resolve_stop_barrier(pos, all_legs[0])
        total_gain = None
        total_loss = None

        if barrier and barrier["scope"] == "position":
            # $/% Loss or a live trail -- evaluated against the position's
            # combined value, not any single leg's own option price (see
            # resolve_stop_barrier / position_give_back). gain_from_here is
            # the combined current value decaying to worthless; loss_from_here
            # is the same combined give-back used for at_risk in
            # aggregate_short_strikes.
            current_combined = tsf.current_combined_price(pos)
            qty = abs(all_legs[0]["qty"])
            if current_combined is not None:
                total_gain = current_combined * qty * 100
                total_loss = tsf.position_give_back(pos)
        else:
            # "N Points ITM" -- genuinely per-leg, via that leg's own chain
            # contract (a local-linear delta step; see the module docstring
            # note on why this isn't repriced with Black-Scholes instead).
            total_gain = 0.0
            total_loss = 0.0
            priced_any = False
            for leg in all_legs:
                leg_barrier = tsf.resolve_stop_barrier(pos, leg)
                contract = contracts.get((leg["strike"], leg["type"]))
                current = contract.get("mark") if contract else None
                if current is None or leg_barrier is None:
                    continue
                delta = contract.get("delta")
                if not delta:
                    continue
                direction = 1 if leg["type"] == "C" else -1
                spot_points_to_stop = (leg_barrier["price"] - spot) * direction
                stop_price = current + abs(delta) * spot_points_to_stop
                qty = -leg["qty"]
                total_gain += current * qty * 100
                total_loss += max(stop_price - current, 0.0) * qty * 100
                priced_any = True
            if not priced_any:
                total_gain = total_loss = None

        if total_gain is None or total_loss is None:
            continue

        ev = (1 - p_stop) * total_gain - p_stop * total_loss
        out[pos.get("serial")] = {
            "stop_probability": p_stop,
            "ev": ev,
            "delta": pos_delta,
            "gamma": pos_gamma,
        }
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
