"""
Binance Demo — Cancel All Orders & Close All Positions
=======================================================
Cleans up the entire futures account so you start fresh.
"""

import os
import sys
import asyncio
import traceback
from pathlib import Path
from dotenv import load_dotenv
import ccxt.async_support as ccxt

PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")
load_dotenv(PROJECT_ROOT / "execution" / ".env", override=True)


async def main():
    if sys.platform == "win32":
        sys.stdout.reconfigure(encoding="utf-8")

    print("=" * 60)
    print(" BINANCE DEMO — CLOSE ALL POSITIONS & CANCEL ALL ORDERS")
    print("=" * 60)

    exchange = ccxt.binance({
        "apiKey": os.getenv("BINANCE_API_KEY", ""),
        "secret": os.getenv("BINANCE_API_SECRET", ""),
        "enableRateLimit": True,
        "options": {
            "defaultType": "future",
            "adjustForTimeDifference": True,
            "fetchOpenOrders": {"warnWithoutSymbol": False},
        },
    })
    exchange.enable_demo_trading(True)

    try:
        await exchange.load_markets()
        print("✅ Connected to Binance Demo.\n")

        # ── 1. Cancel ALL open orders ──
        print("─── STEP 1: Cancel All Open Orders ───")
        open_orders = await exchange.fetch_open_orders()
        if not open_orders:
            print("  No open orders found. ✅")
        else:
            print(f"  Found {len(open_orders)} open order(s):")
            for order in open_orders:
                sym = order.get("symbol", "?")
                oid = order.get("id", "?")
                side = order.get("side", "?")
                amt = order.get("amount", 0)
                print(f"    Cancelling {side} {amt} {sym} (ID: {oid})...")
                try:
                    await exchange.cancel_order(oid, sym)
                    print(f"    ✅ Cancelled.")
                except Exception as e:
                    print(f"    ❌ Failed: {e}")
            print(f"  Done — processed {len(open_orders)} orders.")

        # ── 2. Close ALL open positions ──
        print("\n─── STEP 2: Close All Open Positions ───")
        positions = await exchange.fetch_positions()
        open_positions = [
            p for p in positions
            if float(p.get("contracts") or 0) > 0
        ]

        if not open_positions:
            print("  No open positions found. ✅")
        else:
            print(f"  Found {len(open_positions)} open position(s):")
            for pos in open_positions:
                sym = pos.get("symbol", "?")
                side = pos.get("side", "?")
                contracts = float(pos.get("contracts") or 0)
                upnl = float(pos.get("unrealizedPnl") or 0)
                entry_price = float(pos.get("entryPrice") or 0)

                # To close: sell if long, buy if short
                close_side = "sell" if side == "long" else "buy"

                print(f"    Position: {side.upper()} {contracts} {sym} | Entry: ${entry_price:,.2f} | uPnL: ${upnl:,.4f}")
                print(f"    → Closing with MARKET {close_side.upper()} {contracts}...")

                try:
                    close_order = await exchange.create_order(
                        symbol=sym,
                        type="market",
                        side=close_side,
                        amount=contracts,
                    )
                    status = close_order.get("status", "?")
                    print(f"    ✅ Closed. Order status: {status}")
                except Exception as e:
                    print(f"    ❌ Failed to close: {e}")
                    traceback.print_exc()

            print(f"  Done — processed {len(open_positions)} positions.")

        # ── 3. Verify clean state ──
        print("\n─── STEP 3: Verify Clean State ───")
        remaining_orders = await exchange.fetch_open_orders()
        remaining_positions = [
            p for p in (await exchange.fetch_positions())
            if float(p.get("contracts") or 0) > 0
        ]
        balance = await exchange.fetch_balance()
        usdt_free = float(balance.get("USDT", {}).get("free") or 0)

        print(f"  Open Orders:    {len(remaining_orders)}")
        print(f"  Open Positions: {len(remaining_positions)}")
        print(f"  USDT Balance:   ${usdt_free:,.2f}")

        if not remaining_orders and not remaining_positions:
            print("\n✅ Account is CLEAN — ready for fresh trading!")
        else:
            print("\n⚠️ Some items remain — may need manual cleanup on Binance.")

    except Exception as e:
        print(f"\n❌ Error: {e}")
        traceback.print_exc()
    finally:
        await exchange.close()
        print("\n🔌 Connection closed.")


if __name__ == "__main__":
    asyncio.run(main())
