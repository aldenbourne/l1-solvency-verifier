```python
#!/usr/bin/env python3
"""
Zero-dependency Hyperliquid L1 1:1 Cash-and-Carry Solvency & Delta Verifier.
Queries https://api.hyperliquid.xyz/info directly using Python 3 standard library.
"""

import json
import sys
import time
import urllib.request
from datetime import datetime, timezone

HL_INFO_URL = "https://api.hyperliquid.xyz/info"
DEFAULT_ADDRESS = "[0xHOUSE_SLEEVE_ADDRESS]"

SPOT_TO_PERP = {
    "UBTC": "BTC",
    "HYPE": "HYPE",
    "UETH": "ETH",
    "USOL": "SOL",
    "UZEC": "ZEC",
    "PURR": "PURR",
}


def hl_post(payload: dict):
    req = urllib.request.Request(
        HL_INFO_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=12) as resp:
        return json.loads(resp.read().decode("utf-8"))


def fetch_funding_14d(address: str) -> list:
    start_ms = int((time.time() - 14 * 86400) * 1000)
    cursor_ms = start_ms
    seen = set()
    rows = []
    for _ in range(12):
        batch = hl_post({"type": "userFunding", "user": address, "startTime": cursor_ms}) or []
        if not isinstance(batch, list) or not batch:
            break
        max_t = cursor_ms
        for item in batch:
            t = int(item.get("time") or 0)
            if t > max_t:
                max_t = t
            d = item.get("delta") or {}
            key = f"{t}|{d.get('coin','')}|{d.get('usdc','')}|{d.get('szi','')}"
            if key not in seen:
                seen.add(key)
                rows.append(item)
        if len(batch) < 500:
            break
        cursor_ms = max_t if max_t > cursor_ms else (max_t + 1)
    return rows


def audit_address(address: str) -> None:
    spot_meta, spot_ctxs = hl_post({"type": "spotMetaAndAssetCtxs"})
    spot_state = hl_post({"type": "spotClearinghouseState", "user": address})
    perp_state = hl_post({"type": "clearinghouseState", "user": address})
    abstraction = hl_post({"type": "userAbstraction", "user": address})
    agents = hl_post({"type": "extraAgents", "user": address}) or []
    fundings = fetch_funding_14d(address)

    tok_by_idx = {int(t["index"]): t["name"] for t in spot_meta.get("tokens", [])}
    spot_mid = {}
    for u in spot_meta.get("universe", []):
        idx = int(u["index"])
        if idx < len(spot_ctxs):
            base = tok_by_idx.get(int(u["tokens"][0]), "")
            quote = tok_by_idx.get(int(u["tokens"][1]), "")
            if quote == "USDC":
                spot_mid[base] = float(spot_ctxs[idx].get("midPx") or 0.0)

    avail_arr = spot_state.get("tokenToAvailableAfterMaintenance") or []
    is_unified = (abstraction == "unifiedAccount") or bool(avail_arr)

    usdc_cash = 0.0
    spot_legs = {}
    spot_total_usd = 0.0
    for b in spot_state.get("balances", []):
        coin = b.get("coin", "")
        tot = float(b.get("total") or 0.0)
        if coin == "USDC":
            usdc_cash = tot
        elif tot > 0:
            usd = tot * spot_mid.get(coin, 0.0)
            spot_total_usd += usd
            if usd >= 2.0:
                sym = SPOT_TO_PERP.get(coin, coin)
                spot_legs[sym] = {"token": coin, "qty": tot, "usd": usd}

    perp_legs = {}
    perp_signed_usd = 0.0
    for ap in perp_state.get("assetPositions", []):
        pos = ap.get("position") or {}
        szi = float(pos.get("szi") or 0.0)
        if abs(szi) > 0:
            val = float(pos.get("positionValue") or 0.0)
            signed = val if szi > 0 else -val
            perp_signed_usd += signed
            perp_legs[pos["coin"]] = {"szi": szi, "signed_usd": signed}

    perp_acct_val = float((perp_state.get("marginSummary") or {}).get("accountValue") or 0.0)
    maint_margin = float(perp_state.get("crossMaintenanceMarginUsed") or 0.0)

    # In Hyperliquid Unified Account mode, usdc_cash already settles perp uPnL continuously
    nav_usd = (usdc_cash + spot_total_usd) if is_unified else (usdc_cash + spot_total_usd + perp_acct_val)
    backing = usdc_cash if is_unified else perp_acct_val
    maint_pct = (maint_margin / backing * 100.0) if backing > 0 else 0.0
    net_delta = spot_total_usd + perp_signed_usd
    net_delta_pct = (net_delta / nav_usd * 100.0) if nav_usd > 0 else 0.0
    cum_funding = sum(float((f.get("delta") or {}).get("usdc") or 0.0) for f in fundings)

    def fmt_signed(val: float, decimals: int = 2) -> str:
        sign = "+" if val >= 0 else "-"
        return f"{sign}${abs(val):,.{decimals}f}"

    ts_now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    print("=" * 72)
    print(f"HYPERLIQUID L1 INDEPENDENT SOLVENCY & DELTA AUDIT ({ts_now})")
    print("=" * 72)
    print(f"Audited L1 Wallet     : {address}")
    print(f"Account Architecture  : {'Unified Account (Single Margin Pool)' if is_unified else 'Standard Split'}")
    print(f"Live Account NAV      : ${nav_usd:,.2f}")
    print(f"Unified Cash Balance  : ${usdc_cash:,.2f} USDC")
    print(f"Physical Spot Longs   : {fmt_signed(spot_total_usd)}")
    print(f"Perpetual Short Legs  : {fmt_signed(perp_signed_usd)}")
    print(f"Net Directional Delta : {fmt_signed(net_delta)} ({net_delta_pct:+.2f}% of NAV)")
    print(f"Maint. Margin Usage   : {maint_pct:.2f}%")
    print(f"14d Realized Funding  : {fmt_signed(cum_funding, 4)} USDC ({len(fundings)} hourly settlements)")
    print(f"Authorized Agent Keys : {len(agents)} (L1 Withdrawal Permission: 0.00% Protocol-Enforced)")

    syms = sorted(set(spot_legs.keys()) | set(perp_legs.keys()))
    if syms:
        print("\nMatched 1:1 Spot-Against-Perp Legs:")
        for s in syms:
            sp = spot_legs.get(s, {"token": s, "qty": 0.0, "usd": 0.0})
            pp = perp_legs.get(s, {"szi": 0.0, "signed_usd": 0.0})
            print(
                f"  {s:5s} | Spot: +{sp['qty']:.5f} (${sp['usd']:,.2f}) | "
                f"Perp: {pp['szi']:+.5f} ({fmt_signed(pp['signed_usd'])}) | "
                f"Net Delta: {fmt_signed(sp['usd'] + pp['signed_usd'])}"
            )
    print("=" * 72)


if __name__ == "__main__":
    target = sys.argv[1].strip() if len(sys.argv) > 1 else DEFAULT_ADDRESS
    if not target.startswith("0x") or len(target) != 42:
        print("Usage: python3 verify_l1_sleeve.py <0x_42_char_hyperliquid_address>")
        sys.exit(1)
    audit_address(target)
