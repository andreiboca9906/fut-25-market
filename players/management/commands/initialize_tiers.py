import asyncio

from django.core.management.base import BaseCommand
from django.db import models, transaction

from players.models import Player, PlayerTier
from players.services import CardHotnessCalculator


class Command(BaseCommand):
    help = "Initialize player tiers for all players"

    def add_arguments(self, parser):
        parser.add_argument(
            "--recalculate",
            action="store_true",
            help="Recalculate tiers for all players with price history",
        )

    def handle(self, *args, **options):
        if options["recalculate"]:
            self.stdout.write("Recalculating tiers for all players with price history...")

            async def run_recalculation():
                calculator = CardHotnessCalculator()
                await calculator.recalculate_all_tiers()

            asyncio.run(run_recalculation())

            self.stdout.write(self.style.SUCCESS("Successfully recalculated all player tiers"))
        else:
            # Initialize all players without tiers to COLD
            self.stdout.write("Initializing tiers for players without tier data...")

            with transaction.atomic():
                # Get all players without tier data
                players_without_tier = Player.objects.filter(tier__isnull=True).values_list("id", flat=True)

                # Create tier records for them
                tier_objects = [
                    PlayerTier(player_id=player_id, tier=PlayerTier.COLD, hotness_score=0)
                    for player_id in players_without_tier
                ]

                PlayerTier.objects.bulk_create(tier_objects, ignore_conflicts=True)

                count = len(tier_objects)
                self.stdout.write(self.style.SUCCESS(f"Successfully initialized {count} player tiers"))

        # Display tier statistics
        tier_stats = PlayerTier.objects.values("tier").annotate(count=models.Count("player_id")).order_by("tier")

        self.stdout.write("\nTier Distribution:")
        for stat in tier_stats:
            self.stdout.write(f"  {stat['tier']}: {stat['count']} players")
