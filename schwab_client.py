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
