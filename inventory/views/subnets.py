from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_GET, require_POST

from ..forms import SubnetForm
from ..models import Subnet
from ..services.subnets import build_ip_grid, find_next_free, reserve_next_free


@login_required
@require_GET
def subnet_list(request):
    search = request.GET.get("q", "").strip()
    subnets = Subnet.objects.annotate(
        used_ips=Count("ips", filter=Q(ips__status="used")),
        reserved_ips=Count("ips", filter=Q(ips__status="reserved")),
        recorded_ips=Count("ips"),
    )
    if search:
        subnets = subnets.filter(
            Q(name__icontains=search)
            | Q(cidr__icontains=search)
            | Q(purpose__icontains=search)
        )
    subnets = subnets.order_by("cidr")
    return render(
        request,
        "inventory/subnet_list.html",
        {"subnets": subnets, "search": search, "total": subnets.count()},
    )


@login_required
def subnet_create(request):
    if request.method == "POST":
        form = SubnetForm(request.POST)
        if form.is_valid():
            subnet = form.save()
            messages.success(request, f"Added subnet {subnet.cidr}.")
            return redirect("subnet_detail", pk=subnet.pk)
    else:
        form = SubnetForm()
    return render(
        request,
        "inventory/subnet_form.html",
        {"form": form, "form_title": "Add subnet"},
    )


@login_required
def subnet_edit(request, pk):
    subnet = get_object_or_404(Subnet, pk=pk)
    if request.method == "POST":
        form = SubnetForm(request.POST, instance=subnet)
        if form.is_valid():
            form.save()
            messages.success(request, "Subnet updated.")
            return redirect("subnet_detail", pk=subnet.pk)
    else:
        form = SubnetForm(instance=subnet)
    return render(
        request,
        "inventory/subnet_form.html",
        {"form": form, "form_title": f"Edit {subnet.name}", "subnet": subnet},
    )


@login_required
@require_GET
def subnet_detail(request, pk):
    subnet = get_object_or_404(Subnet, pk=pk)
    grid = build_ip_grid(subnet, request.GET.get("chunk", 0))
    next_free = find_next_free(subnet)
    return render(
        request,
        "inventory/subnet_detail.html",
        {
            "subnet": subnet,
            "grid": grid,
            "next_free": next_free,
            "recorded_ips": subnet.ips.select_related("device").order_by("address"),
        },
    )


@login_required
@require_POST
def subnet_next_free(request, pk):
    subnet = get_object_or_404(Subnet, pk=pk)
    ip = reserve_next_free(subnet)
    if ip is None:
        messages.warning(request, "This subnet has no free addresses left.")
    else:
        messages.success(
            request,
            f"Next free address {ip.address} logged as free. Assign it from the IP ledger.",
        )
    return redirect("subnet_detail", pk=subnet.pk)
