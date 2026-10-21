from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.http import require_GET

from ..models import ImportBatch
from ..services.exports import build_pdf, build_workbook, inventory_counts


@login_required
@require_GET
def export_index(request):
    return render(
        request,
        "inventory/export_index.html",
        {
            "counts": inventory_counts(),
            "last_import": ImportBatch.objects.filter(status=ImportBatch.Status.IMPORTED).first(),
        },
    )


@login_required
@require_GET
def export_workbook(request):
    payload = build_workbook()
    filename = f"netmap-inventory-{timezone.localdate().isoformat()}.xlsx"
    response = HttpResponse(
        payload,
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response


@login_required
@require_GET
def export_pdf(request):
    payload = build_pdf()
    filename = f"netmap-inventory-{timezone.localdate().isoformat()}.pdf"
    response = HttpResponse(payload, content_type="application/pdf")
    response["Content-Disposition"] = (
        f'attachment; filename="{filename}"; filename*=UTF-8\'\'{filename}'
    )
    return response
