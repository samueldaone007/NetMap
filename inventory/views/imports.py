from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from ..imports import (
    ImportCommitError,
    ImportEngine,
    ImportFileError,
    ImportUndoError,
    TARGET_LABELS,
    display_cell,
    field_names_for,
    fields_for,
    read_sheet,
    safe_original_name,
    sheet_names,
    undo_import,
    validate_upload,
)
from ..models import ImportBatch


def _editable(batch):
    return batch.status in {ImportBatch.Status.UPLOADED, ImportBatch.Status.MAPPED}


@login_required
@require_GET
def import_index(request):
    batches = ImportBatch.objects.all()[:30]
    return render(
        request,
        "inventory/import_index.html",
        {"batches": batches, "target_labels": TARGET_LABELS},
    )


@login_required
@require_POST
def import_upload(request):
    upload = request.FILES.get("spreadsheet")
    try:
        original_name = validate_upload(upload)
    except ImportFileError as exc:
        messages.error(request, str(exc))
        return redirect("import_index")

    batch = ImportBatch.objects.create(
        uploaded_file=upload,
        original_name=safe_original_name(original_name),
        uploaded_by=request.user,
    )
    try:
        names = sheet_names(batch)
    except ImportFileError as exc:
        batch.uploaded_file.delete(save=False)
        batch.delete()
        messages.error(request, str(exc))
        return redirect("import_index")
    batch.sheet_name = names[0]
    batch.save(update_fields=["sheet_name"])
    return redirect("import_map", pk=batch.pk)


@login_required
@require_http_methods(["GET", "POST"])
def import_map(request, pk):
    batch = get_object_or_404(ImportBatch, pk=pk)
    if not _editable(batch):
        messages.info(request, "That import is closed. Undo it first if you need to re-import.")
        return redirect("import_index")
    try:
        names = sheet_names(batch)
    except ImportFileError as exc:
        messages.error(request, str(exc))
        return redirect("import_index")

    if request.method == "POST":
        sheet = request.POST.get("sheet", batch.sheet_name or names[0])
        target = request.POST.get("target", batch.target_type or "devices")
        has_header = request.POST.get("header_mode", "1") == "1"
    else:
        sheet = request.GET.get("sheet", batch.sheet_name or names[0])
        target = request.GET.get("target", batch.target_type or "devices")
        if request.GET:
            has_header = request.GET.get("has_header") == "1"
        else:
            has_header = batch.has_header

    if sheet not in names:
        sheet = names[0]
    if target not in TARGET_LABELS:
        target = "devices"

    context = {
        "batch": batch,
        "sheets": names,
        "sheet": sheet,
        "target": target,
        "target_labels": TARGET_LABELS,
        "has_header": has_header,
        "fields": fields_for(target),
        "errors": [],
    }
    try:
        data = read_sheet(batch, sheet, has_header)
    except ImportFileError as exc:
        context["errors"] = [str(exc)]
        return render(request, "inventory/import_map.html", context)

    submitted_mapping = None
    if request.method == "POST":
        submitted_mapping = {}
        values = []
        for index in range(data.column_count):
            value = request.POST.get(f"map_{index}", "").strip()
            submitted_mapping[str(index)] = value
            if value:
                values.append(value)
        allowed = field_names_for(target)
        if any(value not in allowed for value in values):
            context["errors"].append("One of the selected fields is not valid for this import type.")
        if len(values) != len(set(values)):
            context["errors"].append("Map each NetMap field from only one spreadsheet column.")
        if not values:
            context["errors"].append("Map at least one column before previewing.")
        if not context["errors"]:
            batch.sheet_name = sheet
            batch.target_type = target
            batch.has_header = has_header
            batch.mapping = submitted_mapping
            batch.status = ImportBatch.Status.MAPPED
            batch.save(
                update_fields=[
                    "sheet_name",
                    "target_type",
                    "has_header",
                    "mapping",
                    "status",
                    "updated_at",
                ]
            )
            return redirect("import_preview", pk=batch.pk)

    existing_mapping = submitted_mapping
    if existing_mapping is None:
        existing_mapping = batch.mapping if target == batch.target_type else {}
    columns = []
    for index in range(data.column_count):
        samples = []
        for _, row in data.rows[:5]:
            samples.append(display_cell(row[index]) if index < len(row) else "")
        columns.append(
            {
                "index": index,
                "header": data.headers[index],
                "samples": samples,
                "current": existing_mapping.get(str(index), ""),
            }
        )
    context.update({"columns": columns, "row_count": len(data.rows)})
    return render(request, "inventory/import_map.html", context)


@login_required
@require_GET
def import_preview(request, pk):
    batch = get_object_or_404(ImportBatch, pk=pk)
    if not batch.target_type or not batch.mapping:
        messages.info(request, "Map the columns before previewing this import.")
        return redirect("import_map", pk=batch.pk)
    engine = ImportEngine(batch)
    result = engine.run()
    preview_rows = result.rows[:400]
    return render(
        request,
        "inventory/import_preview.html",
        {
            "batch": batch,
            "result": result,
            "preview_rows": preview_rows,
            "hidden_count": max(len(result.rows) - len(preview_rows), 0),
            "target_label": TARGET_LABELS.get(batch.target_type, batch.target_type),
        },
    )


@login_required
@require_POST
def import_commit(request, pk):
    batch = get_object_or_404(ImportBatch, pk=pk)
    if batch.status != ImportBatch.Status.MAPPED:
        messages.info(request, "This import has already been saved or closed.")
        return redirect("import_index")
    engine = ImportEngine(batch)
    try:
        result, undo_data = engine.commit()
    except ImportCommitError as exc:
        messages.error(request, f"{exc} Nothing was saved.")
        return redirect("import_preview", pk=batch.pk)
    except (ImportFileError, ValidationError, IntegrityError) as exc:
        messages.error(request, f"Import failed and was rolled back: {exc}")
        return redirect("import_preview", pk=batch.pk)

    batch.status = ImportBatch.Status.IMPORTED
    batch.imported_at = timezone.now()
    batch.summary = {
        "counts": result.counts,
        "created": result.created_count,
        "updated": result.updated_count,
        "placeholders": result.placeholder_count,
        "rows": result.total_rows,
    }
    batch.undo_data = undo_data
    batch.row_count = result.total_rows
    batch.save(
        update_fields=[
            "status",
            "imported_at",
            "summary",
            "undo_data",
            "row_count",
            "updated_at",
        ]
    )
    messages.success(
        request,
        f"Imported {result.total_rows} row{'s' if result.total_rows != 1 else ''}: "
        f"{result.created_count} created, {result.updated_count} updated.",
    )
    return redirect("import_index")


@login_required
@require_POST
def import_undo(request, pk):
    batch = get_object_or_404(ImportBatch, pk=pk)
    try:
        undo_import(batch)
    except ImportUndoError as exc:
        messages.error(request, str(exc))
    else:
        messages.success(request, f"Import of {batch.original_name} undone as one batch.")
    return redirect("import_index")
