"""
Logistics domain investigation tools.
Queries live Supabase PostgreSQL data via SupplyChainQueries.
"""

from typing import Any, Dict, List, Optional
from database.queries.supply_chain import SupplyChainQueries


def get_shipment(shipment_id: str) -> Optional[Dict[str, Any]]:
    """
    Retrieve shipment details, associated order, carrier information,
    route, delay hours, and tracking notes.
    Accepts shipment UUID or shipment_number (e.g. 'SHP-1002' or 'TRK-2024-1002').
    """
    return SupplyChainQueries.get_shipment(shipment_id)


def get_carrier(carrier_id: str) -> Optional[Dict[str, Any]]:
    """
    Retrieve carrier details, mode of transport, reliability rating,
    and base pricing.
    """
    return SupplyChainQueries.get_carrier(carrier_id)


def get_route(origin: str, destination: str) -> Optional[Dict[str, Any]]:
    """
    Retrieve route details between origin and destination cities,
    including distance in km, transit hours, and current risk level.
    """
    return SupplyChainQueries.get_route(origin, destination)


def get_delivery_status(shipment_id: str) -> Optional[Dict[str, Any]]:
    """
    Retrieve real-time tracking status, delay hours, current location,
    and driver/logistics notes for a shipment.
    """
    return SupplyChainQueries.get_delivery_status(shipment_id)


def find_alternative_carrier(
    origin: Optional[str] = None,
    destination: Optional[str] = None,
    exclude_carrier_id: Optional[str] = None,
    min_reliability: float = 0.85
) -> List[Dict[str, Any]]:
    """
    Find active alternative freight carriers with high reliability ratings.
    """
    return SupplyChainQueries.find_alternative_carrier(
        exclude_carrier_id=exclude_carrier_id,
        min_reliability=min_reliability
    )


def find_alternative_route(
    origin: str,
    destination: str,
    exclude_route_id: Optional[str] = None
) -> List[Dict[str, Any]]:
    """
    Find alternative transportation corridors avoiding high-risk or disrupted segments.
    """
    return SupplyChainQueries.find_alternative_route(
        origin=origin,
        destination=destination,
        exclude_route_id=exclude_route_id
    )
