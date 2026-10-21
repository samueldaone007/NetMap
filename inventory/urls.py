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
    path("subnets/", views.subnet_list, name="subnet_list"),
    path("subnets/new/", views.subnet_create, name="subnet_create"),
    path("subnets/<int:pk>/", views.subnet_detail, name="subnet_detail"),
    path("subnets/<int:pk>/edit/", views.subnet_edit, name="subnet_edit"),
    path("subnets/<int:pk>/next-free/", views.subnet_next_free, name="subnet_next_free"),
]
