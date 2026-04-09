from __future__ import annotations

from collections.abc import Mapping

from ..channels.sms.gateways.base import SmsGateway
from ..events import DeliveryEvent


def parse_onfon_delivery_report(
    query_params: Mapping[str, object],
    gateway: SmsGateway,
) -> DeliveryEvent | None:
    return gateway.parse_delivery_report(query_params)
