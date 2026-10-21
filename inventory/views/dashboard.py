from django.contrib.auth.decorators import login_required
from django.shortcuts import render

from ..models import Connection, Device, Location, Subnet


@login_required
def dashboard(request):
    return render(
        request,
        "inventory/dashboard.html",
        {
            "site_count": Location.objects.values("site").distinct().count(),
            "device_count": Device.objects.count(),
            "subnet_count": Subnet.objects.count(),
            "connection_count": Connection.objects.count(),
        },
    )
