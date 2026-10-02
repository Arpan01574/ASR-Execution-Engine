"""
ASR Engine v3 — Demo Perpetual Futures Test Trade
==================================================
This script:
  1. Validates Telegram bot connectivity (prints full API response)
  2. Connects to Binance DEMO perpetual futures via ccxt
  3. Places a MARKET LONG on BNB/USDT perpetual
  4. Waits 5 seconds, then closes the position
  5. Sends detailed Telegram notifications at every step
"""

import os
import sys
import json
import time
import asyncio
import traceback
import aiohttp
from pathlib import Path
from datetime import datetime, timezone
from dotenv import load_dotenv
import ccxt.async_support as ccxt

# ── Paths & Env ─────────────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Load env files (execution/.env has priority — loaded second, overwrites)
load_dotenv(PROJECT_ROOT / ".env")
load_dotenv(PROJECT_ROOT / "execution" / ".env", override=True)

# ── Telegram Helper ─────────────────────────────────────────────────────

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")


async def telegram_test() -> bool:
    """Test Telegram bot connectivity by calling getMe + sendMessage."""
    print("\n" + "=" * 60)
    print("STEP 1: TELEGRAM BOT CONNECTIVITY TEST")
    print("=" * 60)

    if not TELEGRAM_BOT_TOKEN:
        print("❌ TELEGRAM_BOT_TOKEN is EMPTY or not set!")
        return False
    if not TELEGRAM_CHAT_ID:
        print("❌ TELEGRAM_CHAT_ID is EMPTY or not set!")
        return False

    print(f"  Bot Token: {TELEGRAM_BOT_TOKEN[:10]}...{TELEGRAM_BOT_TOKEN[-6:]}")
    print(f"  Chat ID:   {TELEGRAM_CHAT_ID}")

    async with aiohttp.ClientSession() as session:
        # --- Test 1: getMe (verify token is valid) ---
        print("\n  [1/3] Calling getMe to verify bot token...")
        url_get_me = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getMe"
        try:
            async with session.get(url_get_me, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                status = resp.status
                body = await resp.text()
                print(f"    HTTP Status: {status}")
                print(f"    Response:    {body}")
                if status != 200 or '"ok":false' in body.lower():
                    print("  ❌ getMe FAILED — token is invalid or bot is not reachable!")
                    return False
                print("  ✅ Bot token is VALID.")
        except Exception as e:
            print(f"  ❌ getMe request error: {e}")
            traceback.print_exc()
            return False

        # --- Test 2: getUpdates (check if bot can receive messages) ---
        print("\n  [2/3] Calling getUpdates to check recent messages...")
        url_updates = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getUpdates?limit=5"
        try:
            async with session.get(url_updates, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                status = resp.status
                body = await resp.text()
                print(f"    HTTP Status: {status}")
                data = json.loads(body)
                if data.get("ok"):
                    updates = data.get("result", [])
                    print(f"    Pending updates: {len(updates)}")
                    for upd in updates[-3:]:
                        msg = upd.get("message", {})
                        from_user = msg.get("from", {})
                        print(f"      - Update {upd['update_id']}: '{msg.get('text', '')}' from @{from_user.get('username', '?')}")
                else:
                    print(f"    ⚠️ getUpdates response: {body}")
        except Exception as e:
            print(f"  ⚠️ getUpdates error (non-fatal): {e}")

        # --- Test 3: sendMessage ---
        print("\n  [3/3] Sending a test message to the chat...")
        url_send = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        test_msg = (
            "🤖 <b>ASR Engine v3 — Telegram Test</b>\n\n"
            f"✅ Bot is connected and working!\n"
            f"⏰ Time: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}\n"
            f"📡 Ready for trade notifications."
        )
        payload = {
            "chat_id": TELEGRAM_CHAT_ID,
            "text": test_msg,
            "parse_mode": "HTML",
        }
        try:
            async with session.post(url_send, json=payload, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                status = resp.status
                body = await resp.text()
                print(f"    HTTP Status: {status}")
                print(f"    Response:    {body}")
                if status == 200 and '"ok":true' in body.lower():
                    print("  ✅ Message SENT successfully!")
                    return True
                else:
                    print("  ❌ sendMessage FAILED!")
                    print("     Common causes:")
                    print("     - Bot hasn't been started by the user (send /start to the bot)")
                    print("     - Chat ID is wrong")
                    print("     - Bot was removed from the chat")
                    return False
        except Exception as e:
            print(f"  ❌ sendMessage error: {e}")
            traceback.print_exc()
            return False


async def send_telegram(text: str) -> bool:
    """Send a Telegram message. Returns True on success."""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("  ⚠️ Telegram not configured, skipping notification.")
        return False
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": text, "parse_mode": "HTML"}
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                body = await resp.text()
                if resp.status == 200 and '"ok":true' in body.lower():
                    print("  📨 Telegram notification sent.")
                    return True
                else:
                    print(f"  ❌ Telegram send failed: {resp.status} — {body}")
                    return False
    except Exception as e:
        print(f"  ❌ Telegram error: {e}")
        return False


# ── Perpetual Futures Demo Trade ────────────────────────────────────────

async def execute_demo_trade():
    """Execute a full BNB/USDT perpetual futures round-trip on Binance demo."""
    print("\n" + "=" * 60)
    print("STEP 2: BINANCE PERPETUAL FUTURES DEMO TRADE")
    print("=" * 60)

    api_key = os.getenv("BINANCE_API_KEY", "")
    api_secret = os.getenv("BINANCE_API_SECRET", "")

    if not api_key or not api_secret:
        print("❌ BINANCE_API_KEY or BINANCE_API_SECRET not set in .env!")
        return

    print(f"  API Key: {api_key[:8]}...{api_key[-4:]}")
    print(f"  Mode:    DEMO (Testnet)")

    # Initialize exchange
    exchange = ccxt.binance({
        "apiKey": api_key,
        "secret": api_secret,
        "enableRateLimit": True,
        "options": {
            "defaultType": "future",        # Perpetual futures
            "adjustForTimeDifference": True,
        },
    })

    # Enable demo/testnet trading
    exchange.enable_demo_trading(True)

    try:
        # ── Load Markets ──
        print("\n  [1/6] Loading markets...")
        await exchange.load_markets()
        print(f"  ✅ Markets loaded. Total symbols: {len(exchange.symbols)}")

        # ── Check Balance ──
        print("\n  [2/6] Fetching futures balance...")
        balance = await exchange.fetch_balance()
        usdt_balance = balance.get("USDT", {})
        usdt_free = float(usdt_balance.get("free", 0))
        usdt_total = float(usdt_balance.get("total", 0))
        usdt_used = float(usdt_balance.get("used", 0))
        print(f"  💰 USDT Balance — Free: ${usdt_free:,.2f} | Used: ${usdt_used:,.2f} | Total: ${usdt_total:,.2f}")

        if usdt_free < 10:
            print("  ⚠️ Low balance warning! Need at least $10 USDT for a test trade.")

        # ── Get Current Price ──
        symbol = "BNB/USDT:USDT"   # Perpetual futures notation in ccxt
        print(f"\n  [3/6] Fetching current price for {symbol}...")
        ticker = await exchange.fetch_ticker(symbol)
        current_price = float(ticker.get("last", 0))
        print(f"  📊 Current BNB Price: ${current_price:,.2f}")

        # Calculate quantity — target ~$30 notional
        qty = round(0.05, 3)  # BNB minimum step is usually 0.001
        notional = qty * current_price
        print(f"  📐 Order Size: {qty} BNB ≈ ${notional:,.2f} notional")

        # ── Place LONG (MARKET BUY) ──
        print(f"\n  [4/6] Placing MARKET BUY (LONG) for {qty} {symbol}...")
        entry_order = await exchange.create_order(
            symbol=symbol,
            type="market",
            side="buy",
            amount=qty,
        )

        entry_id = entry_order.get("id", "?")
        entry_status = entry_order.get("status", "?")
        entry_price = float(entry_order.get("average") or entry_order.get("price") or 0)
        entry_filled = float(entry_order.get("filled") or 0)
        entry_cost = float(entry_order.get("cost") or 0)

        print(f"  ✅ LONG ORDER FILLED")
        print(f"     Order ID:    {entry_id}")
        print(f"     Status:      {entry_status}")
        print(f"     Fill Price:  ${entry_price:,.4f}")
        print(f"     Filled Qty:  {entry_filled}")
        print(f"     Cost:        ${entry_cost:,.2f}")

        # Send entry notification
        await send_telegram(
            f"📈 <b>DEMO TRADE — ENTRY</b>\n\n"
            f"<b>Direction:</b> LONG\n"
            f"<b>Asset:</b> {symbol}\n"
            f"<b>Qty:</b> {entry_filled}\n"
            f"<b>Entry Price:</b> ${entry_price:,.4f}\n"
            f"<b>Notional:</b> ${entry_cost:,.2f}\n"
            f"<b>Order ID:</b> <code>{entry_id}</code>\n"
            f"<b>Time:</b> {datetime.now(timezone.utc).strftime('%H:%M:%S UTC')}"
        )

        # ── Check Open Position ──
        print(f"\n  [5/6] Checking open positions...")
        positions = await exchange.fetch_positions([symbol])
        for pos in positions:
            side = pos.get("side", "?")
            contracts = pos.get("contracts", 0)
            unrealized_pnl = pos.get("unrealizedPnl", 0)
            leverage = pos.get("leverage", "?")
            print(f"    Position: {side} {contracts} contracts | uPnL: ${float(unrealized_pnl or 0):,.4f} | Leverage: {leverage}x")

        # ── Wait & Close ──
        wait_secs = 5
        print(f"\n  ⏳ Waiting {wait_secs} seconds before closing position...")
        await asyncio.sleep(wait_secs)

        print(f"\n  [6/6] Placing MARKET SELL to close {qty} {symbol}...")
        exit_order = await exchange.create_order(
            symbol=symbol,
            type="market",
            side="sell",
            amount=qty,
        )

        exit_id = exit_order.get("id", "?")
        exit_status = exit_order.get("status", "?")
        exit_price = float(exit_order.get("average") or exit_order.get("price") or 0)
        exit_filled = float(exit_order.get("filled") or 0)

        pnl = (exit_price - entry_price) * qty
        pnl_pct = ((exit_price / entry_price) - 1) * 100 if entry_price > 0 else 0

        print(f"  ✅ POSITION CLOSED")
        print(f"     Order ID:    {exit_id}")
        print(f"     Status:      {exit_status}")
        print(f"     Exit Price:  ${exit_price:,.4f}")
        print(f"     Filled Qty:  {exit_filled}")
        print(f"     PnL:         ${pnl:,.4f} ({pnl_pct:+.3f}%)")

        # Send exit notification
        pnl_emoji = "🟢" if pnl >= 0 else "🔴"
        await send_telegram(
            f"📉 <b>DEMO TRADE — EXIT</b>\n\n"
            f"<b>Asset:</b> {symbol}\n"
            f"<b>Entry:</b> ${entry_price:,.4f}\n"
            f"<b>Exit:</b> ${exit_price:,.4f}\n"
            f"<b>PnL:</b> {pnl_emoji} ${pnl:,.4f} ({pnl_pct:+.3f}%)\n"
            f"<b>Duration:</b> ~{wait_secs}s\n"
            f"<b>Time:</b> {datetime.now(timezone.utc).strftime('%H:%M:%S UTC')}\n\n"
            f"✅ <b>Round-trip complete. System verified.</b>"
        )

        # ── Final Balance ──
        final_balance = await exchange.fetch_balance()
        final_usdt = float(final_balance.get("USDT", {}).get("free", 0))
        print(f"\n  💰 Final USDT Balance: ${final_usdt:,.2f} (was ${usdt_free:,.2f})")

    except ccxt.NetworkError as e:
        print(f"\n  ❌ NETWORK ERROR: {e}")
        traceback.print_exc()
        await send_telegram(f"❌ <b>TRADE FAILED — Network Error</b>\n\n<code>{str(e)[:200]}</code>")

    except ccxt.ExchangeError as e:
        print(f"\n  ❌ EXCHANGE ERROR: {e}")
        traceback.print_exc()
        await send_telegram(f"❌ <b>TRADE FAILED — Exchange Error</b>\n\n<code>{str(e)[:200]}</code>")

    except Exception as e:
        print(f"\n  ❌ UNEXPECTED ERROR: {e}")
        traceback.print_exc()
        await send_telegram(f"❌ <b>TRADE FAILED — Unexpected Error</b>\n\n<code>{str(e)[:200]}</code>")

    finally:
        await exchange.close()
        print("\n  🔌 Exchange connection closed.")


# ── Main ────────────────────────────────────────────────────────────────

async def main():
    print("=" * 60)
    print(" ASR ENGINE v3 — PERPETUAL FUTURES DEMO TRADE TEST")
    print(f" Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    # Step 1: Test Telegram
    tg_ok = await telegram_test()
    if not tg_ok:
        print("\n⚠️ Telegram test FAILED — continuing with trade anyway (check logs above).")

    # Step 2: Execute demo trade
    await execute_demo_trade()

    print("\n" + "=" * 60)
    print(" TEST COMPLETE")
    print("=" * 60)


if __name__ == "__main__":
    if sys.platform == "win32":
        sys.stdout.reconfigure(encoding="utf-8")
    asyncio.run(main())
