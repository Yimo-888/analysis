from collections import Counter

from django.shortcuts import get_object_or_404, render

from core.models import Product

from .models import Listing, PostingJob
from .services import PIPELINE_STEPS, VARIANTS_PER_PRODUCT

LISTING_STATUS_COLOR = {"POSTED": "success", "PENDING": "warning", "FAILED": "danger"}
JOB_STATUS_COLOR = {"COMPLETED": "success", "PROCESSING": "info",
                    "QUEUED": "secondary", "FAILED": "danger"}
COLOR_HEX = {"success": "#198754", "warning": "#ffc107", "danger": "#dc3545"}


def overview(request):
    jobs = list(PostingJob.objects.all())
    if not jobs:
        return render(request, "automation/overview.html", {"empty": True})

    listings = Listing.objects.all()
    total = listings.count()
    status_counts = Counter(listings.values_list("status", flat=True))
    status_dist = [{"status": s, "count": status_counts.get(s, 0),
                    "hex": COLOR_HEX[LISTING_STATUS_COLOR[s]]}
                   for s in ["POSTED", "PENDING", "FAILED"]]
    n_base = listings.values("base_product").distinct().count()
    catalog_size = Product.objects.count()
    posted = status_counts.get("POSTED", 0)

    # the connected pipeline steps (first step shows the live catalog size)
    steps = []
    for i, (name, detail) in enumerate(PIPELINE_STEPS):
        steps.append({"name": name,
                      "detail": f"{catalog_size:,} SKUs" if i == 0 else detail})

    sample = listings.select_related("base_product").first()
    sample_variants, sample_base = [], None
    if sample:
        sample_base = sample.base_product
        sample_variants = list(Listing.objects.filter(base_product=sample_base).order_by("variant_sku"))

    job_rows = [{"job": j, "color": JOB_STATUS_COLOR.get(j.status, "secondary")} for j in jobs]

    return render(request, "automation/overview.html", {
        "empty": False,
        "jobs": job_rows,
        "n_jobs": len(jobs),
        "total": total,
        "posted": posted,
        "pending": status_counts.get("PENDING", 0),
        "failed": status_counts.get("FAILED", 0),
        "success_rate": round(100 * posted / total) if total else 0,
        "n_base": n_base,
        "catalog_size": catalog_size,
        "variants_per": VARIANTS_PER_PRODUCT,
        "throughput": max(1, round(total / 60)),   # illustrative listings/sec
        "steps": steps,
        "status_dist": status_dist,
        "sample_base": sample_base,
        "sample_variants": sample_variants,
        "listing_colors": LISTING_STATUS_COLOR,
    })


def job_detail(request, pk):
    job = get_object_or_404(PostingJob, pk=pk)
    status = request.GET.get("status", "")
    listings = job.listings.select_related("base_product").order_by("variant_sku")
    if status:
        listings = listings.filter(status=status)
    shown = list(listings[:500])
    return render(request, "automation/job_detail.html", {
        "job": job,
        "job_color": JOB_STATUS_COLOR.get(job.status, "secondary"),
        "listings": shown,
        "truncated": listings.count() > len(shown),
        "status": status,
        "statuses": ["POSTED", "PENDING", "FAILED"],
        "listing_colors": LISTING_STATUS_COLOR,
    })
