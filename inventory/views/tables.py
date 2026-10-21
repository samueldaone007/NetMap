from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods, require_POST

from ..forms import form_class_for, inline_form_class
from ..models import Connection, Device, IPAddress, Port
from ..services.paste import PasteError, paste_rows
from ..tables import CONFIGS, build_table, cell_context

LIST_ROUTES = {
    "devices": "device_list",
    "ips": "ip_list",
    "ports": "port_list",
    "connections": "connection_list",
}

KIND_TITLES = {
    "devices": "device",
    "ips": "IP address",
    "ports": "port",
    "connections": "connection",
}


def _get_config(kind):
    try:
        return CONFIGS[kind]
    except KeyError:
        return None


@login_required
@require_http_methods(["GET"])
def table_view(request, kind):
    config = _get_config(kind)
    if config is None:
        return HttpResponseBadRequest("Unknown table.")
    context = build_table(config, request)
    if request.headers.get("HX-Request"):
        return render(request, "inventory/partials/table_panel.html", context)
    return render(request, "inventory/table_list.html", context)


@login_required
@require_http_methods(["GET", "POST"])
def cell_edit(request, kind, pk, field):
    config = _get_config(kind)
    if config is None:
        return HttpResponseBadRequest("Unknown table.")
    column = next(
        (col for col in config.columns if col.field == field and col.editable), None
    )
    if column is None:
        return HttpResponseBadRequest("That field is not editable here.")
    obj = get_object_or_404(config.model, pk=pk)
    if request.method == "GET" and request.GET.get("display"):
        return render(
            request,
            "inventory/partials/table_cell.html",
            {"cell": cell_context(config, obj, column), "config": config},
        )
    FormClass = inline_form_class(config.model, field)
    if request.method == "POST":
        form = FormClass(request.POST, instance=obj)
        if form.is_valid():
            obj = form.save()
            obj.refresh_from_db()
            return render(
                request,
                "inventory/partials/table_cell.html",
                {"cell": cell_context(config, obj, column), "config": config},
            )
    else:
        form = FormClass(instance=obj)
    return render(
        request,
        "inventory/partials/inline_form.html",
        {
            "form": form,
            "field": field,
            "kind": kind,
            "obj": obj,
            "cell": cell_context(config, obj, column),
        },
    )


@login_required
@require_POST
def table_paste(request, kind):
    config = _get_config(kind)
    if config is None:
        return HttpResponseBadRequest("Unknown table.")
    text = request.POST.get("paste_text", "")
    try:
        result = paste_rows(kind, text, config.paste_fields)
    except PasteError as exc:
        context = build_table(config, request)
        context.update({"paste_errors": exc.errors, "paste_text": text, "open_paste": True})
        return render(request, "inventory/table_list.html", context)
    messages.success(
        request,
        f"Pasted {result.created} {KIND_TITLES[kind]}{'s' if result.created != 1 else ''}.",
    )
    return redirect(LIST_ROUTES[kind])


@login_required
@require_http_methods(["GET", "POST"])
def record_create(request, kind):
    config = _get_config(kind)
    if config is None:
        return HttpResponseBadRequest("Unknown table.")
    FormClass = form_class_for(kind)
    if request.method == "POST":
        form = FormClass(request.POST)
        if form.is_valid():
            obj = form.save()
            messages.success(request, f"Added {obj}.")
            return redirect(LIST_ROUTES[kind])
    else:
        initial = {}
        if kind == "ports" and request.GET.get("device"):
            initial["device"] = request.GET["device"]
        if kind == "ips" and request.GET.get("subnet"):
            initial["subnet"] = request.GET["subnet"]
        form = FormClass(initial=initial)
    return render(
        request,
        "inventory/record_form.html",
        {
            "form": form,
            "config": config,
            "form_title": f"Add {KIND_TITLES[kind]}",
            "cancel_url": LIST_ROUTES[kind],
        },
    )
