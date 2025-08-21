"""Test script for trade status API."""

import asyncio
import os
import sys
import traceback

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import django

# Setup Django
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "fut_market.settings")
django.setup()

from asgiref.sync import sync_to_async
from django.db import connection

from auth_api.services import FutClient
from market.services import MarketService
from players.models import TradeWatch
from players.tasks import verify_pending_trades


async def test_trade_status_api():
    """Test the trade status API with real trade IDs."""

    print("\n=== Testing Trade Status API ===\n")

    # Get active session
    def get_session():
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT session_id
                FROM ea_accounts
                WHERE session_id IS NOT NULL AND is_expired = FALSE
                LIMIT 1
            """)
            return cursor.fetchone()

    row = await sync_to_async(get_session)()

    if not row:
        print("❌ No active session available")
        return

    sid = row[0]
    print(f"✅ Using session: {sid[:20]}...")

    # Get some pending trade watches from the database
    trades = await sync_to_async(lambda: list(TradeWatch.objects.filter(status=TradeWatch.PENDING)[:5]))()

    if not trades:
        print("⚠️  No pending trades in database to test")
        # Use example trade IDs if you have them
        example_trade_ids = []  # Add real trade IDs here for testing
        if example_trade_ids:
            print(f"Using example trade IDs: {example_trade_ids}")
        else:
            print("Please add some trade IDs to test or create some TradeWatch records")
            return
    else:
        trade_ids = [trade.trade_id for trade in trades]
        print(f"Found {len(trade_ids)} pending trades to check: {trade_ids}")

    async with FutClient(x_ut_sid=sid) as client:
        market_service = MarketService(client.session, sid)

        try:
            print("\nCalling get_trade_status API...")
            trade_statuses = await market_service.get_trade_status(trade_ids)

            if trade_statuses:
                print(f"\n✅ Successfully retrieved status for {len(trade_statuses)} trades:\n")
                for trade_id, status in trade_statuses.items():
                    print(f"  Trade {trade_id}:")
                    print(f"    Status: {status.status}")
                    print(f"    Current Bid: {status.current_bid}")
                    print(f"    Bid Count: {status.bid_count}")
                    print(f"    Expires: {status.expires}")
                    print()
            else:
                print("⚠️  No trade status data returned")

        except Exception as e:
            print(f"❌ Error calling trade status API: {e}")
            traceback.print_exc()


async def test_verify_pending_trades():
    """Test the verify_pending_trades task logic."""

    print("\n=== Testing Verify Pending Trades Logic ===\n")

    # Check if there are pending trades
    pending_count = await sync_to_async(TradeWatch.objects.filter(status=TradeWatch.PENDING).count)()
    print(f"Found {pending_count} pending trades in database")

    if pending_count > 0:
        print("\nRunning verify_pending_trades task...")
        try:
            # Run the task (it's synchronous but contains async code)
            verify_pending_trades(batch_size=5)
            print("✅ Task completed successfully")

            # Check results
            sold = await sync_to_async(TradeWatch.objects.filter(status=TradeWatch.SOLD).count)()
            expired = await sync_to_async(TradeWatch.objects.filter(status=TradeWatch.EXPIRED).count)()
            active = await sync_to_async(TradeWatch.objects.filter(status=TradeWatch.ACTIVE).count)()

            print("\nResults:")
            print(f"  Sold: {sold}")
            print(f"  Expired: {expired}")
            print(f"  Active: {active}")

        except Exception as e:
            print(f"❌ Error running task: {e}")
            traceback.print_exc()
    else:
        print("No pending trades to verify. Create some TradeWatch records first.")


async def main():
    """Run all tests."""
    print("Testing EA FC 25 Trade Status System")
    print("=" * 40)

    await test_trade_status_api()
    # Uncomment to test the full task
    # await test_verify_pending_trades()

    print("\n" + "=" * 40)
    print("Tests completed!")


if __name__ == "__main__":
    asyncio.run(main())
