"""Recompute analytics over the existing data (without reseeding)."""
from django.core.management.base import BaseCommand

from core.services.run import run_engine


class Command(BaseCommand):
    help = "Run the full analytics pipeline over the current catalog."

    def handle(self, *args, **opts):
        summary = run_engine()
        if not summary.get("products"):
            self.stdout.write(self.style.WARNING("No products found. Run `seed_demo` first."))
            return
        self.stdout.write(self.style.SUCCESS(
            f"Analyzed {summary['products']} SKUs (run {summary['run_date']}), "
            f"boundary rank {summary['boundary_rank']}, {summary['mispriced']} mispriced."))
