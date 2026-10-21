"""Address maths for subnet pages."""
from __future__ import annotations

import ipaddress
import math
from dataclasses import dataclass

from django.db import transaction
from django.utils import timezone

from ..models import IPAddress


def usable_bounds(network):
    if network.version == 4 and network.prefixlen < 31:
        return int(network.network_address) + 1, int(network.broadcast_address) - 1
    return int(network.network_address), int(network.broadcast_address)


def usable_count(network) -> int:
    start, end = usable_bounds(network)
    return max(end - start + 1, 0)


def iter_usable(network, offset: int = 0, limit: int | None = None):
    start, end = usable_bounds(network)
    current = start + offset
    yielded = 0
    while current <= end and (limit is None or yielded < limit):
        yield ipaddress.ip_address(current)
        current += 1
        yielded += 1


def find_next_free(subnet) -> str | None:
    network = ipaddress.ip_network(subnet.cidr, strict=False)
    taken = set(subnet.ips.values_list("address", flat=True))
    for address in iter_usable(network):
        if str(address) not in taken:
            return str(address)
    return None


def reserve_next_free(subnet):
    with transaction.atomic():
        locked = type(subnet).objects.select_for_update().get(pk=subnet.pk)
        candidate = find_next_free(locked)
        if candidate is None:
            return None
        return IPAddress.objects.create(
            address=candidate,
            subnet=locked,
            status=IPAddress.Status.FREE,
            source=IPAddress._meta.get_field("source").default,
            last_verified=timezone.localdate(),
        )


@dataclass
class IPGrid:
    cells: list
    chunk: int
    chunk_count: int
    total: int
    chunk_size: int = 256

    @property
    def has_previous(self):
        return self.chunk > 0

    @property
    def has_next(self):
        return self.chunk + 1 < self.chunk_count

    @property
    def previous_chunk(self):
        return max(self.chunk - 1, 0)

    @property
    def next_chunk(self):
        return min(self.chunk + 1, max(self.chunk_count - 1, 0))

    @property
    def start_number(self):
        return self.chunk * self.chunk_size + 1

    @property
    def end_number(self):
        return min((self.chunk + 1) * self.chunk_size, self.total)


def build_ip_grid(subnet, requested_chunk=0, chunk_size: int = 256) -> IPGrid:
    network = ipaddress.ip_network(subnet.cidr, strict=False)
    total = usable_count(network)
    chunk_count = max(math.ceil(total / chunk_size), 1)
    chunk = min(max(int(requested_chunk or 0), 0), chunk_count - 1)
    records = {str(ip.address): ip for ip in subnet.ips.select_related("device").all()}

    cells = []
    for address in iter_usable(network, offset=chunk * chunk_size, limit=chunk_size):
        key = str(address)
        record = records.get(key)
        if record:
            state = record.status
            label = record.hostname or (record.device.name if record.device else "")
        else:
            state = "unrecorded"
            label = ""
        cells.append(
            {
                "address": key,
                "short": key.rsplit(".", 1)[-1] if network.version == 4 else key,
                "state": state,
                "record": record,
                "label": label,
            }
        )
    return IPGrid(cells=cells, chunk=chunk, chunk_count=chunk_count, total=total)
