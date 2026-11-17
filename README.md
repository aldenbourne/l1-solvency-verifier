# Hyperliquid L1 Cash-and-Carry Solvency & Delta Verifier

Zero-dependency Python CLI tool published by **AldenBourne** (`https://www.aldenbourne.com`) to independently audit any Hyperliquid L1 `1:1` delta-neutral cash-and-carry account directly against Hyperliquid's public Layer-1 Info RPC (`https://api.hyperliquid.xyz/info`).

No API keys, wallet connections, or third-party packages (`pip`) are required—uses Python 3 standard library only.

## What This Script Audits Directly Against L1

1. **Account Mode & True Unified NAV:** Queries `spotClearinghouseState`, `clearinghouseState`, and `userAbstraction` to compute exact live equity (accounting properly for Unified Account real-time variation margin settlement).
2. **1:1 Physical Spot vs. Perpetual Short Equilibrium:** Pairs every spot balance (`UBTC`, `UETH`, `HYPE`, `USOL`, `UZEC`, `PURR`) against its corresponding perpetual short leg to verify net directional exposure (`Net Delta $` and `% of NAV`).
3. **Maintenance Margin Health:** Computes live cross-maintenance margin utilization.
4. **Protocol-Enforced Agent Key Scope:** Lists active `extraAgents` authorized on the wallet and their expiration timestamps (all Hyperliquid L1 Agent Keys are cryptographically restricted from signing withdrawals at L1 consensus).
5. **Paginated 14-Day Hourly Funding Audit:** Forward-paginates `userFunding` (`500` records/page with composite deduplication) to verify exact cumulative USDC settled over the trailing 14 days.

## Quick Start

```bash
# Audit the default AldenBourne public house sleeve:
python3 verify_l1_sleeve.py

# Or audit any arbitrary Hyperliquid L1 0x... address:
python3 verify_l1_sleeve.py 0xYOUR_HYPERLIQUID_ADDRESS
