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
from core.constants import TIER_SCAN_WINDOWS
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
from utils.adaptive_throttle import AdaptiveThrottler
from utils.integrated_circuit_breaker import circuit_breaker_manager
from utils.logging_config import ErrorTracker
from utils.metrics import PrometheusMetrics, RiskMetrics

logger = logging.getLogger("players")


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
    """Scrape market prices for players in a specific tier with pagination."""

    logger.info(f"Starting tier-based price scrape for {tier} tier", extra={"tier": tier, "platform": platform})

    # Increment active tasks
    PrometheusMetrics.increment_active_scrapers(tier)
    task_start_time = time.time()

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
        trades_collected = 0

        # Calculate next scan time for this tier
        next_scan = timezone.now() + TIER_SCAN_WINDOWS.get(tier, timedelta(hours=1))

        # Initialize adaptive throttler
        throttler = AdaptiveThrottler()

        # Initialize circuit breaker
        breaker = await circuit_breaker_manager.get_breaker(tier, sid)

        # Check if circuit is open globally
        if await breaker.is_open_globally():
            logger.warning(f"Circuit breaker is open for tier {tier}, skipping scrape")
            return

        async with FutClient(x_ut_sid=sid) as client:
            for player_id in player_ids:
                try:
                    # Get player's resource_id
                    player = await sync_to_async(Player.objects.filter(id=player_id).first)()

                    if not player or not player.resource_id:
                        continue

                    # Get adaptive delay
                    delay = await throttler.get_adjusted_delay(tier)
                    await asyncio.sleep(delay)

                    # Collect auctions from multiple pages (max 5 pages)
                    all_auctions = []

                    for page in range(1, 6):  # Max 5 pages
                        # Check circuit breaker before each request
                        if await breaker.is_open_globally():
                            logger.warning("Circuit breaker opened during scraping, stopping")
                            return

                        params = PlayerSearchParameters(page=page, resource_id=player.resource_id)

                        # Execute with circuit breaker
                        request_start = time.time()
                        try:
                            res = await client.search_players(params)
                            await breaker.record_success()
                        except Exception as e:
                            await breaker.record_failure(e)
                            raise

                        if res.auctions:
                            all_auctions.extend(res.auctions)

                            # Check if we should continue pagination
                            should_continue = False
                            for auction in res.auctions:
                                if auction.expires:
                                    # Convert expires (seconds) to timestamp
                                    expires_at = timezone.now() + timedelta(seconds=auction.expires)

                                    # Only continue if there might be auctions expiring before next scan
                                    if expires_at < next_scan:
                                        should_continue = True
                                        break

                            # Stop pagination if no more relevant auctions
                            if not should_continue or len(res.auctions) < 21:  # Less than full page
                                break

                            # Add delay between pages
                            await asyncio.sleep(human_delay(0.8, variance=0.2))
                        else:
                            break  # No more results

                    # Process collected auctions
                    if all_auctions:
                        # Filter auctions with buy now prices
                        buyable_auctions = [a for a in all_auctions if a.buy_now_price]

                        if buyable_auctions:
                            # Find minimum price for current market value
                            sorted_by_price = sorted(buyable_auctions, key=lambda x: x.buy_now_price)
                            min_price = sorted_by_price[0].buy_now_price

                            # Store current minimum price
                            await sync_to_async(PlayerPrice.objects.update_or_create)(
                                player=player,
                                platform=platform,
                                defaults={"current_price": Decimal(min_price), "last_updated": timezone.now()},
                            )

                            # Track ALL auctions expiring before next scan
                            for auction in buyable_auctions:
                                if auction.expires:
                                    expires_at = timezone.now() + timedelta(seconds=auction.expires)

                                    # Track auction if it expires before next scan
                                    if expires_at < next_scan:
                                        created = await sync_to_async(
                                            lambda: TradeWatch.objects.get_or_create(
                                                trade_id=str(auction.trade_id),
                                                defaults={
                                                    "player": player,
                                                    "listed_price": Decimal(auction.buy_now_price),
                                                    "expires_at": expires_at,
                                                    "discovered_at": timezone.now(),
                                                },
                                            )[1]
                                        )()

                                        if created:
                                            trades_collected += 1

                            # Add to price history (unverified)
                            await sync_to_async(PlayerPriceHistory.objects.create)(
                                player=player,
                                platform=platform,
                                price=Decimal(min_price),
                                fetched_at=timezone.now(),
                                is_verified=False,
                            )

                            success_count += 1

                            # Record success metrics
                            request_time = time.time() - task_start_time
                            PrometheusMetrics.record_request(
                                tier=tier, response_time=request_time, success=True, session_id=sid
                            )

                            logger.debug(
                                "Price scraped with pagination",
                                extra={
                                    "tier": tier,
                                    "player_id": player_id,
                                    "price": min_price,
                                    "total_listings": len(all_auctions),
                                    "trades_tracked": trades_collected,
                                },
                            )
                    else:
                        failure_count += 1

                except RateLimitError as e:
                    logger.warning(f"Rate limit hit while scraping {tier} tier", extra={"tier": tier})
                    # Record rate limit hit
                    RiskMetrics.record_rate_limit(session_id=sid)

                    # Back off for this tier
                    await asyncio.sleep(human_delay(10, variance=0.3))

                except Exception as e:
                    failure_count += 1

                    # Record error metrics
                    RiskMetrics.record_error(tier=tier, error_type=ErrorTracker.categorize_error(e), session_id=sid)
                    await ErrorTracker.log_error(
                        ErrorTracker.categorize_error(e), e, {"tier": tier, "player_id": player_id}
                    )

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
                "trades_collected": trades_collected,
            },
        )

    try:
        asyncio.run(_run())
    finally:
        # Decrement active tasks
        PrometheusMetrics.decrement_active_scrapers(tier)


@shared_task(bind=True, name="players.tasks.verify_pending_trades")
def verify_pending_trades(self, batch_size: int = 60):
    """Verify pending trades that have expired to confirm actual sale prices."""

    logger.info("Starting trade verification task")

    async def _run():
        # Get trades where expires_at < now() (auctions that have ended)
        current_time = timezone.now()

        pending_trades = await sync_to_async(
            lambda: list(
                TradeWatch.objects.filter(expires_at__lt=current_time, status=TradeWatch.PENDING).select_related(
                    "player"
                )[:batch_size]
            )
        )()

        if not pending_trades:
            logger.info("No expired trades to verify")
            return

        logger.info(f"Verifying {len(pending_trades)} expired trades")

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

            # Process in batches of 20 (API limit)
            for i in range(0, len(pending_trades), 20):
                batch = pending_trades[i : i + 20]
                trade_ids = [trade.trade_id for trade in batch]

                # Add human-like delay before batch request
                await asyncio.sleep(human_delay(1.0, variance=0.2))

                try:
                    # Get status for trades in this batch
                    trade_statuses = await market_service.get_trade_status(trade_ids)

                    verified_count = 0
                    sold_count = 0
                    expired_count = 0
                    active_count = 0

                    # Process each trade based on its status
                    for trade in batch:
                        trade_id_str = str(trade.trade_id)

                        if trade_id_str in trade_statuses:
                            status_info = trade_statuses[trade_id_str]

                            if status_info.status == "sold":
                                trade.status = TradeWatch.SOLD
                                sold_count += 1

                                # Update current_price with verified sold price
                                await sync_to_async(PlayerPrice.objects.filter(player_id=trade.player_id).update)(
                                    current_price=trade.listed_price, last_updated=timezone.now()
                                )

                                # Record verified sale in history
                                await sync_to_async(PlayerPriceHistory.objects.create)(
                                    player=trade.player,
                                    platform="ps",
                                    price=trade.listed_price,
                                    trade_id=trade.trade_id,
                                    is_verified=True,
                                    fetched_at=timezone.now(),
                                )

                                verified_count += 1

                                logger.debug(
                                    "Trade verified as sold",
                                    extra={
                                        "trade_id": trade.trade_id,
                                        "player_id": trade.player_id,
                                        "price": float(trade.listed_price),
                                    },
                                )

                            elif status_info.status == "expired":
                                trade.status = TradeWatch.EXPIRED
                                expired_count += 1

                            elif status_info.status == "active":
                                # Still active even though expires_at passed - check again later
                                trade.status = TradeWatch.ACTIVE
                                active_count += 1

                        else:
                            # Trade not found in response - mark as expired
                            trade.status = TradeWatch.EXPIRED
                            expired_count += 1

                        trade.checked_at = timezone.now()
                        await sync_to_async(trade.save)()

                    logger.info(
                        "Batch verification completed",
                        extra={
                            "batch_size": len(batch),
                            "verified_count": verified_count,
                            "sold_count": sold_count,
                            "expired_count": expired_count,
                            "active_count": active_count,
                        },
                    )

                except Exception as e:
                    logger.error("Error verifying trades batch", extra={"error": str(e), "trade_count": len(trade_ids)})
                    # Mark batch as checked but keep pending status
                    for trade in batch:
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
