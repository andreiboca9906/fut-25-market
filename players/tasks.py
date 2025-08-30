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
from utils.adaptive_throttle import AdaptiveThrottler
from utils.integrated_circuit_breaker import circuit_breaker_manager
from utils.logging_config import ErrorTracker
from utils.metrics import PrometheusMetrics, RiskMetrics
from utils.task_deduplication import DeduplicatedTask

logger = logging.getLogger("players")


def _min_buy_now(auctions):
    """Get minimum buy now price from auctions."""
    return min((a.buy_now_price for a in auctions if a.buy_now_price), default=None)


@shared_task(bind=True, base=DeduplicatedTask)
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
                                        await sync_to_async(
                                            lambda: PlayerPriceHistory.objects.create(
                                                player=player_obj,
                                                platform=platform,
                                                price=Decimal(price),
                                                fetched_at=now,
                                            )
                                        )()

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
                                    await sync_to_async(
                                        lambda: PriceScrapeFailure.objects.create(
                                            job=job,
                                            player_id=def_id,
                                            reason="No transfer market listings found",
                                        )
                                    )()
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
                                    await sync_to_async(
                                        lambda: PriceScrapeFailure.objects.create(
                                            job=job,
                                            player_id=def_id,
                                            reason=f"Rate limited after {max_retries} retries",
                                            http_status=429,
                                        )
                                    )()
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
                                error_msg = str(ex)
                                await sync_to_async(
                                    lambda: PriceScrapeFailure.objects.create(
                                        job=job,
                                        player_id=def_id,
                                        reason=error_msg,
                                    )
                                )()
                                logger.error(
                                    "Failed to scrape price",
                                    extra={"job_id": job.id, "resource_id": def_id, "error": error_msg},
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
        logger.error("Price scrape job failed", extra={"job_id": job.id, "error": str(e)}, exc_info=True)
        raise


def human_delay(base_seconds: float, variance: float = 0.15) -> float:
    """Add human-like variance to delays."""
    jitter = base_seconds * variance
    return base_seconds + random.uniform(-jitter, jitter)


@shared_task(bind=True, name="players.tasks.scrape_tier_prices", base=DeduplicatedTask)
def scrape_tier_prices(self, tier: str, platform: str = "ps"):
    """Scrape market prices for players in a specific tier with pagination."""

    logger.info(f"Starting tier-based price scrape for {tier} tier", extra={"tier": tier, "platform": platform})

    # Increment active tasks
    PrometheusMetrics.increment_active_scrapers(tier)

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

        # Fetch all current prices for players in this batch
        player_prices_dict = {}
        player_prices = await sync_to_async(
            lambda: list(
                PlayerPrice.objects.filter(player_id__in=player_ids, platform=platform, current_price__gt=0)
                .exclude(current_price__isnull=True)
                .values("player_id", "current_price")
            )
        )()

        for price_data in player_prices:
            player_prices_dict[price_data["player_id"]] = price_data["current_price"]

        # Get active session
        def get_active_session():
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

            return row[0]

        success_count = 0
        failure_count = 0
        trades_collected = 0

        # Initialize adaptive throttler
        throttler = AdaptiveThrottler()

        # Session retry logic
        max_session_retries = 3
        session_retry_count = 0

        while session_retry_count < max_session_retries:
            try:
                # Get session ID
                sid = await sync_to_async(get_active_session)()

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

                            # Get player's last sold price from pre-fetched dict
                            max_buy_filter = None
                            if player_id in player_prices_dict:
                                current_price = player_prices_dict[player_id]
                                # Set max_buy to 115% of last sold price (15% over)
                                max_buy_filter = int(current_price * Decimal("1.15"))

                            # Get adaptive delay
                            delay = await throttler.get_adjusted_delay(tier)
                            await asyncio.sleep(delay)

                            # Collect auctions from single page (optimized for trade ID checking)
                            all_auctions = []

                            for page in range(1, 2):  # Max 1 page
                                # Check circuit breaker before each request
                                if await breaker.is_open_globally():
                                    logger.warning("Circuit breaker opened during scraping, stopping")
                                    return

                                params = PlayerSearchParameters(
                                    page=page, resource_id=player.resource_id, max_buy=max_buy_filter
                                )

                                # Execute with circuit breaker
                                request_start = time.time()
                                try:
                                    res = await client.search_players(params)
                                    await breaker.record_success()
                                except SessionExpiredError as e:
                                    # Session expired, need to get new session and retry
                                    logger.warning(
                                        f"Session expired for tier {tier}, getting new session",
                                        extra={"tier": tier, "session_id": sid},
                                    )
                                    raise  # Re-raise to trigger outer catch block
                                except Exception as e:
                                    await breaker.record_failure(e)
                                    raise
                                finally:
                                    request_end = time.time()

                                if res.auctions:
                                    # Check if any trade IDs are already saved (optimization: check last trade ID first)
                                    should_continue = False
                                    if res.auctions:
                                        # Check last trade ID first for optimization
                                        last_auction = res.auctions[-1]
                                        last_trade_exists = await sync_to_async(
                                            lambda: TradeWatch.objects.filter(
                                                trade_id=str(last_auction.trade_id)
                                            ).exists()
                                        )()

                                        # If last trade ID is already saved, skip checking others and don't continue
                                        if not last_trade_exists:
                                            # Check if any trade IDs in this page are new
                                            existing_trade_ids = set(
                                                await sync_to_async(
                                                    lambda: list(
                                                        TradeWatch.objects.filter(
                                                            trade_id__in=[str(a.trade_id) for a in res.auctions]
                                                        ).values_list("trade_id", flat=True)
                                                    )
                                                )()
                                            )

                                            # Only continue if we found new trade IDs
                                            new_auctions = [
                                                a for a in res.auctions if str(a.trade_id) not in existing_trade_ids
                                            ]
                                            if new_auctions:
                                                all_auctions.extend(new_auctions)
                                                should_continue = len(res.auctions) == 21  # Full page

                                    # Stop pagination if no new auctions or not a full page
                                    if not should_continue:
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

                                    # Track ALL auctions
                                    for auction in buyable_auctions:
                                        if auction.expires:
                                            expires_at = timezone.now() + timedelta(seconds=auction.expires)
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

                                    # Note: PlayerPriceHistory only records verified sold trades
                                    # Unverified scraping data is tracked via TradeWatch and current PlayerPrice

                                    success_count += 1

                                    # Record success metrics
                                    PrometheusMetrics.record_request(
                                        tier=tier,
                                        response_time=request_end - request_start,
                                        success=True,
                                        session_id=sid,
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
                                # No auctions found - still need to mark as scraped to avoid repeated attempts
                                await sync_to_async(
                                    lambda: PlayerPrice.objects.update_or_create(
                                        player_id=player_id,
                                        platform=platform,
                                        defaults={
                                            "current_price": 0,  # No market data available
                                            "last_updated": timezone.now(),
                                        },
                                    )
                                )()
                                success_count += 1

                                # Record success metrics (same as auction-found case)
                                PrometheusMetrics.record_request(
                                    tier=tier,
                                    response_time=request_end - request_start,
                                    success=True,
                                    session_id=sid,
                                )

                                logger.debug(
                                    "No auctions found, marked as scraped",
                                    extra={
                                        "tier": tier,
                                        "player_id": player_id,
                                    },
                                )

                        except RateLimitError as e:
                            logger.warning(f"Rate limit hit while scraping {tier} tier", extra={"tier": tier})
                            # Record rate limit hit
                            RiskMetrics.record_rate_limit(session_id=sid)

                            # Record failed request metric
                            if "request_start" in locals():
                                PrometheusMetrics.record_request(
                                    tier=tier, response_time=time.time() - request_start, success=False, session_id=sid
                                )

                            # Back off for this tier
                            await asyncio.sleep(human_delay(10, variance=0.3))

                        except SessionExpiredError:
                            # This is handled in outer try/catch, just re-raise
                            raise

                        except Exception as e:
                            failure_count += 1

                            # Record error metrics
                            RiskMetrics.record_error(
                                tier=tier, error_type=ErrorTracker.categorize_error(e), session_id=sid
                            )
                            await ErrorTracker.log_error(
                                ErrorTracker.categorize_error(e), e, {"tier": tier, "player_id": player_id}
                            )

                            # Record failed request metric
                            if "request_start" in locals():
                                PrometheusMetrics.record_request(
                                    tier=tier, response_time=time.time() - request_start, success=False, session_id=sid
                                )

                            logger.error(
                                f"Error scraping player in {tier} tier",
                                extra={"tier": tier, "player_id": player_id, "error": str(e)},
                                exc_info=True,  # This will log the full traceback
                            )

                # If we get here, session was successful, break out of retry loop
                break

            except SessionExpiredError as e:
                session_retry_count += 1

                if session_retry_count >= max_session_retries:
                    logger.error(
                        f"Max session retries ({max_session_retries}) reached for tier {tier}", extra={"tier": tier}
                    )
                    raise

                # Try to get a new session
                logger.info(
                    f"Session expired, attempting to get new session (attempt {session_retry_count}/{max_session_retries})",
                    extra={"tier": tier},
                )

                try:
                    # Wait a bit before getting new session
                    await asyncio.sleep(2)
                    # Session will be fetched in next iteration of loop

                except Exception:
                    logger.error(f"No active sessions available for tier {tier}")
                    raise

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


@shared_task(bind=True, name="players.tasks.verify_pending_trades", base=DeduplicatedTask)
def verify_pending_trades(self, batch_size: int = 60):
    """Verify pending trades that have expired to confirm actual sale prices."""

    logger.info(f"[TRADE_VERIFY] Starting trade verification task with batch_size={batch_size}")

    async def _run():
        # Get trades where expires_at < now() (auctions that have ended)
        current_time = timezone.now()
        logger.info(f"[TRADE_VERIFY] Checking for trades expired before {current_time}")

        pending_trades = await sync_to_async(
            lambda: list(
                TradeWatch.objects.filter(expires_at__lt=current_time, status=TradeWatch.PENDING).select_related(
                    "player"
                )[:batch_size]
            )
        )()

        if not pending_trades:
            logger.info("[TRADE_VERIFY] No pending trades to verify")
            return

        logger.info(f"[TRADE_VERIFY] Found {len(pending_trades)} pending trades to verify")

        # Get active session
        def get_active_session():
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

            return row[0]

        # Session retry logic
        max_session_retries = 3
        session_retry_count = 0
        verification_completed = False

        while session_retry_count < max_session_retries and not verification_completed:
            try:
                sid = await sync_to_async(get_active_session)()

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
                                        try:
                                            await sync_to_async(
                                                lambda: PlayerPrice.objects.update_or_create(
                                                    player_id=trade.player_id,
                                                    defaults={
                                                        "current_price": trade.listed_price,
                                                        "last_updated": timezone.now(),
                                                    },
                                                )
                                            )()

                                            # Record price update metric
                                            try:
                                                player_tier = await sync_to_async(
                                                    lambda: getattr(trade.player, "tier", None)
                                                )()
                                                if player_tier:
                                                    PrometheusMetrics.record_price_update(player_tier.tier)
                                            except Exception:
                                                # Ignore tier metric errors - not critical
                                                pass

                                        except Exception as price_error:
                                            logger.error(
                                                f"[TRADE_VERIFY] Failed to update price for player {trade.player_id}: {str(price_error)}",
                                                exc_info=True,
                                            )

                                        # Record verified sale in history (only for confirmed sales)
                                        try:
                                            await sync_to_async(
                                                lambda: PlayerPriceHistory.objects.create(
                                                    player=trade.player,
                                                    platform="ps",
                                                    price=trade.listed_price,
                                                    trade_id=trade.trade_id,
                                                    is_verified=True,
                                                    fetched_at=timezone.now(),
                                                )
                                            )()
                                        except Exception as history_error:
                                            logger.error(
                                                f"[TRADE_VERIFY] Failed to create price history for trade {trade.trade_id}: {str(history_error)}"
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

                                # Update checked_at and save
                                trade.checked_at = timezone.now()
                                try:
                                    await sync_to_async(trade.save)()
                                except Exception as save_error:
                                    logger.error(
                                        f"[TRADE_VERIFY] Failed to save trade {trade.trade_id}: {str(save_error)}"
                                    )

                            logger.info(
                                f"[TRADE_VERIFY] Batch verification completed - sold: {sold_count}, expired: {expired_count}, active: {active_count}, verified: {verified_count}",
                                extra={
                                    "batch_size": len(batch),
                                    "verified_count": verified_count,
                                    "sold_count": sold_count,
                                    "expired_count": expired_count,
                                    "active_count": active_count,
                                },
                            )

                        except SessionExpiredError:
                            # Session expired during processing, need to retry
                            logger.warning("[TRADE_VERIFY] Session expired during batch processing")
                            raise

                        except Exception as e:
                            logger.error(
                                f"[TRADE_VERIFY] Error verifying trades batch: {str(e)}",
                                extra={"error": str(e), "trade_count": len(trade_ids)},
                                exc_info=True,
                            )
                            # Mark batch as checked but keep pending status
                            for trade in batch:
                                trade.checked_at = timezone.now()
                                await sync_to_async(trade.save)()

                # If we get here, verification completed successfully
                verification_completed = True

            except SessionExpiredError as e:
                session_retry_count += 1

                if session_retry_count >= max_session_retries:
                    logger.error(f"[TRADE_VERIFY] Max session retries ({max_session_retries}) reached")
                    return

                logger.info(
                    f"[TRADE_VERIFY] Session expired, attempting to get new session (attempt {session_retry_count}/{max_session_retries})"
                )

                # Wait a bit before getting new session
                await asyncio.sleep(2)

    try:
        asyncio.run(_run())
        logger.info("[TRADE_VERIFY] Trade verification task completed successfully")
    except Exception as e:
        logger.error(f"[TRADE_VERIFY] Task failed with error: {str(e)}", exc_info=True)
        raise


@shared_task(bind=True, name="players.tasks.recalculate_player_tiers", base=DeduplicatedTask)
def recalculate_player_tiers(self):
    """Recalculate hotness scores and tiers for all players."""

    logger.info("Starting player tier recalculation")

    async def _run():
        calculator = CardHotnessCalculator()
        await calculator.recalculate_all_tiers()

    asyncio.run(_run())

    logger.info("Player tier recalculation completed")


@shared_task(bind=True, name="players.tasks.cleanup_expired_trades", base=DeduplicatedTask)
def cleanup_expired_trades(self):
    """Clean up old expired trade watches."""

    cutoff_time = timezone.now() - timedelta(days=1)

    deleted_count = TradeWatch.objects.filter(
        status__in=[TradeWatch.EXPIRED, TradeWatch.SOLD], created_at__lt=cutoff_time
    ).delete()[0]

    logger.info(f"Cleaned up {deleted_count} expired trades")
