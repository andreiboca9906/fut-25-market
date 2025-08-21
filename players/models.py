from typing import Dict, List

from django.db import models, transaction
from django.db.models import Avg, Case, Count, Max, Min, When
from django.utils import timezone


class PlayerManager(models.Manager):
    """Custom manager for Player model."""

    @transaction.atomic
    def bulk_upsert(self, players: List[Dict]) -> bool:
        """Insert or update players in batch."""
        if not players:
            return True

        try:
            for player_data in players:
                player_fields = {
                    "id": player_data.get("id"),
                    "timestamp": player_data.get("timestamp"),
                    "formation": player_data.get("formation"),
                    "untradeable": player_data.get("untradeable"),
                    "asset_id": player_data.get("assetId"),
                    "rating": player_data.get("rating"),
                    "dream": player_data.get("dream"),
                    "item_type": player_data.get("itemType"),
                    "resource_id": player_data.get("resourceId"),
                    "owners": player_data.get("owners"),
                    "discard_value": player_data.get("discardValue"),
                    "card_subtype_id": player_data.get("cardsubtypeid"),
                    "last_sale_price": player_data.get("lastSalePrice"),
                    "injury_type": player_data.get("injuryType"),
                    "injury_games": player_data.get("injuryGames"),
                    "preferred_position": player_data.get("preferredPosition"),
                    "stats_list": player_data.get("statsList"),
                    "lifetime_stats": player_data.get("lifetimeStats"),
                    "contract": player_data.get("contract"),
                    "team_id": player_data.get("teamid"),
                    "rare_flag": player_data.get("rareflag"),
                    "play_style": player_data.get("playStyle"),
                    "league_id": player_data.get("leagueId"),
                    "loyalty_bonus": player_data.get("loyaltyBonus"),
                    "pile": player_data.get("pile"),
                    "nation": player_data.get("nation"),
                    "resource_game_year": player_data.get("resourceGameYear"),
                    "guid_asset_id": player_data.get("guidAssetId"),
                    "attribute_array": player_data.get("attributeArray"),
                    "skill_moves": player_data.get("skillmoves"),
                    "weak_foot_ability_type_code": player_data.get("weakfootabilitytypecode"),
                    "preferred_foot": player_data.get("preferredfoot"),
                    "possible_positions": player_data.get("possiblePositions"),
                    "gender": player_data.get("gender"),
                    "base_traits": player_data.get("baseTraits"),
                    "icon_traits_priorities": player_data.get("iconTraitsPriorities"),
                    "icon_traits": player_data.get("iconTraits"),
                    "plus_plus_roles": player_data.get("plusPlusRoles"),
                    "groups": player_data.get("groups"),
                    "first_name": player_data.get("first_name"),
                    "last_name": player_data.get("last_name"),
                }

                # Remove None values
                player_fields = {k: v for k, v in player_fields.items() if v is not None}

                self.update_or_create(id=player_fields["id"], defaults=player_fields)

            return True
        except Exception as e:
            print(f"Failed to upsert players: {e}")
            return False

    def get_summary_stats(self) -> Dict:
        """Get summary statistics of players."""
        try:
            # General statistics
            general_stats = self.aggregate(
                total_count=Count("id"),
                unique_players=Count("asset_id", distinct=True),
                avg_rating=Avg("rating"),
                min_rating=Min("rating"),
                max_rating=Max("rating"),
                rare_count=Count(Case(When(rare_flag=1, then=1))),
                common_count=Count(Case(When(rare_flag=0, then=1))),
                untradeable_count=Count(Case(When(untradeable=True, then=1))),
                tradeable_count=Count(Case(When(untradeable=False, then=1))),
            )

            # Rating distribution
            rating_distribution = []
            rating_ranges = [
                ("90+", 90, 100),
                ("85-89", 85, 89),
                ("80-84", 80, 84),
                ("75-79", 75, 79),
                ("70-74", 70, 74),
                ("65-69", 65, 69),
                ("<65", 0, 64),
            ]

            for label, min_val, max_val in rating_ranges:
                if max_val < 100:
                    count = self.filter(rating__gte=min_val, rating__lte=max_val).count()
                else:
                    count = self.filter(rating__gte=min_val).count()
                if count > 0:
                    rating_distribution.append({"rating_range": label, "count": count})

            # Position distribution (top 10)
            position_distribution = []
            positions = (
                self.exclude(preferred_position__isnull=True)
                .values("preferred_position")
                .annotate(count=Count("id"))
                .order_by("-count")[:10]
            )

            for pos in positions:
                position_distribution.append({"preferred_position": pos["preferred_position"], "count": pos["count"]})

            # Card type distribution
            card_type_distribution = []
            card_types = (
                self.exclude(item_type__isnull=True).values("item_type").annotate(count=Count("id")).order_by("-count")
            )

            for ct in card_types:
                card_type_distribution.append({"item_type": ct["item_type"], "count": ct["count"]})

            return {
                "general_stats": general_stats,
                "rating_distribution": rating_distribution,
                "position_distribution": position_distribution,
                "card_type_distribution": card_type_distribution,
            }

        except Exception as e:
            print(f"Failed to get players summary: {e}")
            return {
                "error": str(e),
                "general_stats": {},
                "rating_distribution": [],
                "position_distribution": [],
                "card_type_distribution": [],
            }


class Player(models.Model):
    id = models.BigIntegerField(primary_key=True)
    timestamp = models.BigIntegerField(null=True, blank=True)
    formation = models.CharField(max_length=20, null=True, blank=True)
    untradeable = models.BooleanField(null=True, blank=True)
    asset_id = models.IntegerField(null=True, blank=True, db_index=True)
    rating = models.IntegerField(null=True, blank=True, db_index=True)
    dream = models.BooleanField(null=True, blank=True)
    item_type = models.CharField(max_length=50, null=True, blank=True)
    resource_id = models.BigIntegerField(null=True, blank=True)
    owners = models.IntegerField(null=True, blank=True)
    discard_value = models.IntegerField(null=True, blank=True)
    card_subtype_id = models.IntegerField(null=True, blank=True)
    last_sale_price = models.IntegerField(null=True, blank=True)
    injury_type = models.CharField(max_length=50, null=True, blank=True)
    injury_games = models.IntegerField(null=True, blank=True)
    preferred_position = models.CharField(max_length=10, null=True, blank=True, db_index=True)
    stats_list = models.JSONField(null=True, blank=True)
    lifetime_stats = models.JSONField(null=True, blank=True)
    contract = models.IntegerField(null=True, blank=True)
    team_id = models.IntegerField(null=True, blank=True, db_index=True)
    rare_flag = models.IntegerField(null=True, blank=True)
    play_style = models.IntegerField(null=True, blank=True)
    league_id = models.IntegerField(null=True, blank=True, db_index=True)
    loyalty_bonus = models.IntegerField(null=True, blank=True)
    pile = models.IntegerField(null=True, blank=True)
    nation = models.IntegerField(null=True, blank=True, db_index=True)
    resource_game_year = models.IntegerField(null=True, blank=True)
    guid_asset_id = models.UUIDField(null=True, blank=True)
    attribute_array = models.JSONField(null=True, blank=True)
    skill_moves = models.IntegerField(null=True, blank=True)
    weak_foot_ability_type_code = models.IntegerField(null=True, blank=True)
    preferred_foot = models.IntegerField(null=True, blank=True)
    possible_positions = models.JSONField(null=True, blank=True)
    gender = models.IntegerField(null=True, blank=True)
    base_traits = models.JSONField(null=True, blank=True)
    icon_traits_priorities = models.JSONField(null=True, blank=True)
    icon_traits = models.JSONField(null=True, blank=True)
    plus_plus_roles = models.JSONField(null=True, blank=True)
    groups = models.JSONField(null=True, blank=True)
    first_name = models.CharField(max_length=100, null=True, blank=True)
    last_name = models.CharField(max_length=100, null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    objects = PlayerManager()

    class Meta:
        db_table = "players"

    def __str__(self):
        name = f"{self.first_name or ''} {self.last_name or ''}".strip()
        return name if name else f"Player {self.id}"


class PlayerPriceManager(models.Manager):
    """Custom manager for PlayerPrice model."""

    @transaction.atomic
    def update_price(self, player_id: int, platform: str, price: float, currency: str = "COINS"):
        """Update or create price for a player."""
        return self.update_or_create(
            player_id=player_id, platform=platform, defaults={"current_price": price, "currency": currency}
        )


class PlayerPrice(models.Model):
    id = models.AutoField(primary_key=True)
    player = models.ForeignKey(Player, on_delete=models.CASCADE, related_name="prices", db_column="player_id")
    platform = models.CharField(max_length=10)
    current_price = models.DecimalField(max_digits=12, decimal_places=2)
    currency = models.CharField(max_length=10, default="COINS")
    last_updated = models.DateTimeField(default=timezone.now)

    objects = PlayerPriceManager()

    class Meta:
        db_table = "player_prices"
        unique_together = ["player", "platform"]

    def __str__(self):
        return f"{self.player} - {self.platform}: {self.current_price} {self.currency}"


class PlayerPriceHistory(models.Model):
    id = models.AutoField(primary_key=True)
    player = models.ForeignKey(Player, on_delete=models.CASCADE, related_name="price_history", db_column="player_id")
    platform = models.CharField(max_length=10)
    price = models.DecimalField(max_digits=12, decimal_places=2)
    currency = models.CharField(max_length=10, default="COINS")
    fetched_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = "player_price_history"

    def __str__(self):
        return f"{self.player} - {self.platform} @ {self.fetched_at}: {self.price} {self.currency}"


class PriceScrapeJob(models.Model):
    id = models.AutoField(primary_key=True)
    started_at = models.DateTimeField(default=timezone.now)
    ended_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(
        max_length=20, choices=[("running", "Running"), ("completed", "Completed"), ("failed", "Failed")]
    )
    total_targets = models.IntegerField(default=0)
    success_count = models.IntegerField(default=0)
    failure_count = models.IntegerField(default=0)
    rate_limit_hits = models.IntegerField(default=0)
    notes = models.TextField(null=True, blank=True)

    class Meta:
        db_table = "price_scrape_jobs"

    def __str__(self):
        return f"Job {self.id} - {self.status} ({self.success_count}/{self.total_targets})"


class PriceScrapeFailure(models.Model):
    id = models.AutoField(primary_key=True)
    job = models.ForeignKey(PriceScrapeJob, on_delete=models.CASCADE, related_name="failures")
    player_id = models.BigIntegerField()
    reason = models.CharField(max_length=255)
    http_status = models.IntegerField(null=True, blank=True)
    payload = models.TextField(null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = "price_scrape_failures"

    def __str__(self):
        return f"Job {self.job_id} - Player {self.player_id}: {self.reason}"
