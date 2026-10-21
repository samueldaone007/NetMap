from django.urls import path

from . import views

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("devices/", views.table_view, {"kind": "devices"}, name="device_list"),
    path("ips/", views.table_view, {"kind": "ips"}, name="ip_list"),
    path("ports/", views.table_view, {"kind": "ports"}, name="port_list"),
    path(
        "connections/",
        views.table_view,
        {"kind": "connections"},
        name="connection_list",
    ),
    path(
        "tables/<str:kind>/<int:pk>/cell/<str:field>/",
        views.cell_edit,
        name="table_cell",
    ),
    path("tables/<str:kind>/paste/", views.table_paste, name="table_paste"),
    path("records/<str:kind>/new/", views.record_create, name="record_create"),
]
