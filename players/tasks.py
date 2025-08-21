import asyncio
import logging
import os
from decimal import Decimal

from asgiref.sync import sync_to_async
from celery import shared_task
from django.db import connection
from django.utils import timezone

from auth_api.services import FutClient
from core.exceptions import RateLimitError, SessionExpiredError
from core.fut_models.search import PlayerSearchParameters
from players.models import Player, PlayerPrice, PlayerPriceHistory, PriceScrapeFailure, PriceScrapeJob

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
