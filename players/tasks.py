import asyncio
import logging
import os
import random
import time
from datetime import timedelta
from decimal import Decimal

from asgiref.sync import sync_to_async
from celery import shared_task
from django.db import connection
from django.utils import timezone

from auth_api.services import FutClient
from core.exceptions import RateLimitError, SessionExpiredError
from core.fut_models.search import PlayerSearchParameters
from market.services import MarketService
from players.models import (
    Player,
    PlayerPrice,
    PlayerPriceHistory,
    PriceScrapeFailure,
    PriceScrapeJob,
    TradeWatch,
)
from players.services import CardHotnessCalculator, TierBasedPriorityQueue

logger = logging.getLogger("market.scraper")


def _min_buy_now(auctions):
    """Get minimum buy now price from auctions."""
    return min((a.buy_now_price for a in auctions if a.buy_now_price), default=None)


@shared_task(bind=True)
def scrape_market_prices(self, platform: str = "ps"):
    """Scrape market prices for all players with resource_id."""

    job = PriceScrapeJob.objects.create(status="running")
    logger.info("Starting price scrape job", extra={"job_id": job.id, "platform": platform})

    try:
        # Get active session from Postgres
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT session_id
                FROM ea_accounts
                WHERE session_id IS NOT NULL AND is_expired = FALSE
                LIMIT 1
            """)
            row = cursor.fetchone()

        if not row:
            job.status = "failed"
            job.notes = "No active session available in ea_accounts"
            job.ended_at = timezone.now()
            job.save()
            raise SessionExpiredError("No active session available in ea_accounts")

        sid = row[0]

        # Get player resource IDs
        player_ids = list(
            Player.objects.exclude(resource_id__isnull=True).values_list("resource_id", flat=True).distinct()
        )

        # For testing: limit to top 10 players
        if os.getenv("TEST_MODE", "false").lower() == "true":
            player_ids = player_ids[:10]
            logger.info("TEST MODE: Limited to 10 players", extra={"job_id": job.id})

        job.total_targets = len(player_ids)
        job.save()

        batch_size = int(os.getenv("SCRAPE_BATCH_SIZE", "50"))
        now = timezone.now()

        async def _run():
            async with FutClient(x_ut_sid=sid) as client:
                for i in range(0, len(player_ids), batch_size):
                    chunk = player_ids[i : i + batch_size]
                    for def_id in chunk:
                        # Retry logic for individual player
                        max_retries = 3
                        retry_count = 0

                        while retry_count <= max_retries:
                            try:
                                params = PlayerSearchParameters(page=1, resource_id=def_id)
                                res = await client.search_players(params)
                                price = _min_buy_now(res.auctions)

                                if price is not None:
                                    player_obj = await sync_to_async(
                                        lambda: Player.objects.filter(resource_id=def_id).first()
                                    )()
                                    if player_obj:
                                        await sync_to_async(PlayerPrice.objects.update_or_create)(
                                            player=player_obj,
                                            platform=platform,
                                            defaults={"current_price": Decimal(price), "last_updated": now},
                                        )
                                        await sync_to_async(PlayerPriceHistory.objects.create)(
                                            player=player_obj,
                                            platform=platform,
                                            price=Decimal(price),
                                            fetched_at=now,
                                        )
                                        job.success_count += 1
                                        logger.info(
                                            "Price updated",
                                            extra={
                                                "job_id": job.id,
                                                "resource_id": def_id,
                                                "price": price,
                                                "player_id": player_obj.id,
                                            },
                                        )
                                else:
                                    # No price available - skip, don't retry
                                    job.failure_count += 1
                                    await sync_to_async(PriceScrapeFailure.objects.create)(
                                        job=job,
                                        player_id=def_id,
                                        reason="No transfer market listings found",
                                    )
                                    logger.info(
                                        "No listings found, skipping", extra={"job_id": job.id, "resource_id": def_id}
                                    )
                                break  # Success, exit retry loop

                            except RateLimitError:
                                retry_count += 1
                                job.rate_limit_hits += 1

                                if retry_count > max_retries:
                                    # Max retries reached, give up on this player
                                    job.failure_count += 1
                                    await sync_to_async(PriceScrapeFailure.objects.create)(
                                        job=job,
                                        player_id=def_id,
                                        reason=f"Rate limited after {max_retries} retries",
                                        http_status=429,
                                    )
                                    logger.warning(
                                        "Rate limit: max retries reached, skipping player",
                                        extra={"job_id": job.id, "resource_id": def_id, "retry_count": retry_count},
                                    )
                                else:
                                    # Wait and retry this player
                                    wait_time = 2**retry_count  # Exponential backoff
                                    logger.info(
                                        "Rate limited, retrying player",
                                        extra={
                                            "job_id": job.id,
                                            "resource_id": def_id,
                                            "retry_count": retry_count,
                                            "wait_time": wait_time,
                                        },
                                    )
                                    await asyncio.sleep(wait_time)

                            except Exception as ex:
                                job.failure_count += 1
                                await sync_to_async(PriceScrapeFailure.objects.create)(
                                    job=job,
                                    player_id=def_id,
                                    reason=str(ex),
                                )
                                logger.error(
                                    "Failed to scrape price",
                                    extra={"job_id": job.id, "resource_id": def_id, "error": str(ex)},
                                )
                                break  # Don't retry on other errors

                        await sync_to_async(job.save)()

                    await asyncio.sleep(4)  # cooperative pacing between chunks (increased for rate limits)

        asyncio.run(_run())

        job.status = "completed"
        job.ended_at = timezone.now()
        job.save()

        logger.info(
            "Price scrape job completed",
            extra={
                "job_id": job.id,
                "success_count": job.success_count,
                "failure_count": job.failure_count,
                "total_targets": job.total_targets,
            },
        )

    except SessionExpiredError:
        # Don't retry for session expired errors
        logger.error("Session expired, stopping scrape", extra={"job_id": job.id})
        raise

    except Exception as e:
        job.status = "failed"
        job.notes = str(e)
        job.ended_at = timezone.now()
        job.save()
        logger.error("Price scrape job failed", extra={"job_id": job.id, "error": str(e)})
        raise


def human_delay(base_seconds: float, variance: float = 0.15) -> float:
    """Add human-like variance to delays."""
    jitter = base_seconds * variance
    return base_seconds + random.uniform(-jitter, jitter)


def human_sleep(base_seconds: float):
    """Sleep with human-like variance."""
    time.sleep(human_delay(base_seconds))


@shared_task(bind=True, name="players.tasks.scrape_tier_prices")
def scrape_tier_prices(self, tier: str, platform: str = "ps"):
    """Scrape market prices for players in a specific tier."""

    logger.info(f"Starting tier-based price scrape for {tier} tier", extra={"tier": tier, "platform": platform})

    async def _run():
        priority_queue = TierBasedPriorityQueue()

        # Check if we should scrape this tier
        should_scrape = await priority_queue.should_scrape_tier(tier)
        if not should_scrape:
            logger.info(f"Skipping {tier} tier - not due for refresh yet", extra={"tier": tier})
            return

        # Get batch of players for this tier
        player_ids = await priority_queue.get_next_batch(tier)

        if not player_ids:
            logger.warning(f"No players found in {tier} tier", extra={"tier": tier})
            return

        logger.info(
            f"Scraping {len(player_ids)} players in {tier} tier", extra={"tier": tier, "count": len(player_ids)}
        )

        # Get active session
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT session_id
                FROM ea_accounts
                WHERE session_id IS NOT NULL AND is_expired = FALSE
                ORDER BY RANDOM()
                LIMIT 1
            """)
            row = cursor.fetchone()

        if not row:
            raise SessionExpiredError("No active session available")

        sid = row[0]

        success_count = 0
        failure_count = 0

        async with FutClient(x_ut_sid=sid) as client:
            for player_id in player_ids:
                try:
                    # Get player's resource_id
                    player = await sync_to_async(Player.objects.filter(id=player_id).first)()

                    if not player or not player.resource_id:
                        continue

                    # Add human-like delay before request
                    await asyncio.sleep(human_delay(1.5, variance=0.2))

                    params = PlayerSearchParameters(page=1, resource_id=player.resource_id)
                    res = await client.search_players(params)

                    # Process auctions
                    if res.auctions:
                        # Get cheapest buy now prices
                        cheapest_auctions = sorted(
                            [a for a in res.auctions if a.buy_now_price], key=lambda x: x.buy_now_price
                        )[:5]

                        if cheapest_auctions:
                            min_price = cheapest_auctions[0].buy_now_price

                            # Store unverified price
                            await sync_to_async(PlayerPrice.objects.update_or_create)(
                                player=player,
                                platform=platform,
                                defaults={"current_price": Decimal(min_price), "last_updated": timezone.now()},
                            )

                            # Create trade watches for verification
                            for auction in cheapest_auctions[:3]:  # Track top 3 for verification
                                await sync_to_async(TradeWatch.objects.get_or_create)(
                                    trade_id=auction.trade_id,
                                    defaults={
                                        "player": player,
                                        "listed_price": Decimal(auction.buy_now_price),
                                        "discovered_at": timezone.now(),
                                    },
                                )

                            # Add to price history
                            await sync_to_async(PlayerPriceHistory.objects.create)(
                                player=player,
                                platform=platform,
                                price=Decimal(min_price),
                                fetched_at=timezone.now(),
                                is_verified=False,
                            )

                            success_count += 1
                            logger.debug(
                                "Price scraped",
                                extra={
                                    "tier": tier,
                                    "player_id": player_id,
                                    "price": min_price,
                                    "listings": len(res.auctions),
                                },
                            )
                    else:
                        failure_count += 1

                except RateLimitError:
                    logger.warning(f"Rate limit hit while scraping {tier} tier", extra={"tier": tier})
                    # Back off for this tier
                    await asyncio.sleep(human_delay(10, variance=0.3))

                except Exception as e:
                    failure_count += 1
                    logger.error(
                        f"Error scraping player in {tier} tier",
                        extra={"tier": tier, "player_id": player_id, "error": str(e)},
                    )

        logger.info(
            f"Completed {tier} tier scrape",
            extra={
                "tier": tier,
                "success_count": success_count,
                "failure_count": failure_count,
                "total": len(player_ids),
            },
        )

    asyncio.run(_run())


@shared_task(bind=True, name="players.tasks.verify_pending_trades")
def verify_pending_trades(self, batch_size: int = 20):
    """Verify pending trades to confirm actual sale prices."""

    logger.info("Starting trade verification task")

    async def _run():
        # Get trades older than 5 minutes
        cutoff_time = timezone.now() - timedelta(minutes=5)

        pending_trades = await sync_to_async(
            lambda: list(
                TradeWatch.objects.filter(status=TradeWatch.PENDING, discovered_at__lt=cutoff_time).select_related(
                    "player"
                )[:batch_size]
            )
        )()

        if not pending_trades:
            logger.info("No pending trades to verify")
            return

        logger.info(f"Verifying {len(pending_trades)} trades")

        # Get active session
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT session_id
                FROM ea_accounts
                WHERE session_id IS NOT NULL AND is_expired = FALSE
                ORDER BY RANDOM()
                LIMIT 1
            """)
            row = cursor.fetchone()

        if not row:
            raise SessionExpiredError("No active session available")

        sid = row[0]

        async with FutClient(x_ut_sid=sid) as client:
            # Create market service
            market_service = MarketService(client.session, sid)

            # Get all trade IDs to check
            trade_ids = [trade.trade_id for trade in pending_trades]

            # Add human-like delay before batch request
            await asyncio.sleep(human_delay(1.0, variance=0.2))

            try:
                # Get status for all trades in one API call
                trade_statuses = await market_service.get_trade_status(trade_ids)

                verified_count = 0
                sold_count = 0
                expired_count = 0
                active_count = 0

                # Process each trade based on its status
                for trade in pending_trades:
                    trade_id_str = str(trade.trade_id)

                    if trade_id_str in trade_statuses:
                        status_info = trade_statuses[trade_id_str]

                        if status_info.status == "sold":
                            trade.status = TradeWatch.SOLD
                            sold_count += 1

                            # Update verified price
                            await sync_to_async(PlayerPrice.objects.filter(player_id=trade.player_id).update)(
                                current_price=trade.listed_price, last_updated=timezone.now()
                            )

                            # Mark in history as verified
                            await sync_to_async(PlayerPriceHistory.objects.create)(
                                player=trade.player,
                                platform="ps",
                                price=trade.listed_price,
                                trade_id=trade.trade_id,
                                is_verified=True,
                                fetched_at=timezone.now(),
                            )

                            verified_count += 1

                        elif status_info.status == "expired":
                            trade.status = TradeWatch.EXPIRED
                            expired_count += 1

                        elif status_info.status == "active":
                            trade.status = TradeWatch.ACTIVE
                            active_count += 1

                    else:
                        # Trade not found in response - likely expired or very old
                        trade.status = TradeWatch.EXPIRED
                        expired_count += 1

                    trade.checked_at = timezone.now()
                    await sync_to_async(trade.save)()

                logger.info(
                    "Trade verification completed",
                    extra={
                        "verified_count": verified_count,
                        "sold_count": sold_count,
                        "expired_count": expired_count,
                        "active_count": active_count,
                        "total": len(pending_trades),
                    },
                )

            except Exception as e:
                logger.error("Error verifying trades batch", extra={"error": str(e), "trade_count": len(trade_ids)})
                # Fall back to marking all as needing re-check
                for trade in pending_trades:
                    trade.checked_at = timezone.now()
                    await sync_to_async(trade.save)()

    asyncio.run(_run())


@shared_task(bind=True, name="players.tasks.recalculate_player_tiers")
def recalculate_player_tiers(self):
    """Recalculate hotness scores and tiers for all players."""

    logger.info("Starting player tier recalculation")

    async def _run():
        calculator = CardHotnessCalculator()
        await calculator.recalculate_all_tiers()

    asyncio.run(_run())

    logger.info("Player tier recalculation completed")


@shared_task(bind=True, name="players.tasks.cleanup_expired_trades")
def cleanup_expired_trades(self):
    """Clean up old expired trade watches."""

    cutoff_time = timezone.now() - timedelta(days=1)

    deleted_count = TradeWatch.objects.filter(
        status__in=[TradeWatch.EXPIRED, TradeWatch.SOLD], created_at__lt=cutoff_time
    ).delete()[0]

    logger.info(f"Cleaned up {deleted_count} expired trades")
