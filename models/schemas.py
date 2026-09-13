"""
Domain and persistence schemas for the Supply Chain Exception Resolution Agent.
Uses Pydantic v2 for data validation and typing.
"""

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field


# -----------------------------------------------------------------------------
# ENUMS
# -----------------------------------------------------------------------------

class CustomerTier(str, Enum):
    STANDARD = "STANDARD"
    PRIORITY = "PRIORITY"
    ENTERPRISE = "ENTERPRISE"
    VIP = "VIP"


class CriticalLevel(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class OrderStatus(str, Enum):
    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    SHIPPED = "SHIPPED"
    DELIVERED = "DELIVERED"
    DELAYED = "DELAYED"
    CANCELLED = "CANCELLED"
    EXCEPTION = "EXCEPTION"


class POStatus(str, Enum):
    ISSUED = "ISSUED"
    CONFIRMED = "CONFIRMED"
    IN_TRANSIT = "IN_TRANSIT"
    RECEIVED = "RECEIVED"
    DELAYED = "DELAYED"
    CANCELLED = "CANCELLED"
    EXPEDITED = "EXPEDITED"


class ShipmentStatus(str, Enum):
    CREATED = "CREATED"
    IN_TRANSIT = "IN_TRANSIT"
    OUT_FOR_DELIVERY = "OUT_FOR_DELIVERY"
    DELIVERED = "DELIVERED"
    DELAYED = "DELAYED"
    REROUTED = "REROUTED"
    EXCEPTION = "EXCEPTION"
    CANCELLED = "CANCELLED"


class ExceptionCategory(str, Enum):
    PROCUREMENT = "PROCUREMENT"
    LOGISTICS = "LOGISTICS"
    INVENTORY = "INVENTORY"
    CROSS_FUNCTIONAL = "CROSS_FUNCTIONAL"


class ExceptionSeverity(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class ExceptionStatus(str, Enum):
    OPEN = "OPEN"
    INVESTIGATING = "INVESTIGATING"
    PENDING_APPROVAL = "PENDING_APPROVAL"
    APPROVED = "APPROVED"
    RESOLVED = "RESOLVED"
    REJECTED = "REJECTED"
    IGNORED = "IGNORED"


class OperationalRisk(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class ExecutionStatus(str, Enum):
    PENDING = "PENDING"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


# -----------------------------------------------------------------------------
# DOMAIN MODELS
# -----------------------------------------------------------------------------

class Customer(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    email: Optional[str] = None
    tier: CustomerTier = CustomerTier.STANDARD
    sla_hours: int = 48
    contact_phone: Optional[str] = None
    shipping_address: Optional[str] = None
    created_at: Optional[datetime] = None


class Product(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    sku: str
    name: str
    category: Optional[str] = None
    unit_price: float
    unit_cost: float
    weight_kg: float = 1.0
    critical_level: CriticalLevel = CriticalLevel.MEDIUM
    created_at: Optional[datetime] = None


class Warehouse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    code: str
    location: str
    city: str
    state: Optional[str] = None
    country: str = "India"
    capacity_sqft: Optional[int] = None
    operating_cost_per_day: float = 5000.0
    is_active: bool = True


class Inventory(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    warehouse_id: str
    product_id: str
    quantity_available: int = 0
    quantity_reserved: int = 0
    quantity_in_transit: int = 0
    reorder_point: int = 50
    safety_stock: int = 20
    unit_holding_cost_per_day: float = 2.0
    last_restocked_at: Optional[datetime] = None


class Supplier(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    code: str
    category: Optional[str] = None
    city: str
    country: str = "India"
    lead_time_days: int = 7
    expedite_lead_time_days: int = 3
    reliability_rating: float = 0.95
    capacity_units_per_day: int = 1000
    current_capacity_utilized: int = 400
    expedite_cost_multiplier: float = 1.35
    contact_email: Optional[str] = None
    is_active: bool = True


class Carrier(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    code: str
    mode: str = "ROAD"
    reliability_rating: float = 0.92
    base_cost_per_km: float = 12.0
    expedite_cost_multiplier: float = 1.50
    avg_speed_kmh: float = 45.0
    contact_phone: Optional[str] = None
    is_active: bool = True


class Route(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    origin_city: str
    destination_city: str
    distance_km: float
    estimated_transit_hours: float
    standard_risk_level: OperationalRisk = OperationalRisk.LOW
    is_active: bool = True


class OrderItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    order_id: str
    product_id: str
    quantity: int
    unit_price: float
    total_price: float
    fulfilled_quantity: int = 0


class Order(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    order_number: str
    customer_id: str
    order_date: datetime
    required_delivery_date: datetime
    status: OrderStatus = OrderStatus.PENDING
    total_amount: float = 0.0
    shipping_city: str
    shipping_address: Optional[str] = None
    priority: CriticalLevel = CriticalLevel.MEDIUM
    assigned_warehouse_id: Optional[str] = None
    items: List[OrderItem] = Field(default_factory=list)


class PurchaseOrderItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    purchase_order_id: str
    product_id: str
    quantity_ordered: int
    quantity_received: int = 0
    unit_cost: float
    total_cost: float


class PurchaseOrder(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    po_number: str
    supplier_id: str
    destination_warehouse_id: str
    issue_date: datetime
    expected_delivery_date: datetime
    actual_delivery_date: Optional[datetime] = None
    status: POStatus = POStatus.ISSUED
    total_cost: float = 0.0
    is_expedited: bool = False
    notes: Optional[str] = None
    items: List[PurchaseOrderItem] = Field(default_factory=list)


class Shipment(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    shipment_number: str
    order_id: Optional[str] = None
    purchase_order_id: Optional[str] = None
    carrier_id: str
    route_id: Optional[str] = None
    origin_location: str
    destination_location: str
    pickup_date: Optional[datetime] = None
    expected_delivery_date: datetime
    actual_delivery_date: Optional[datetime] = None
    status: ShipmentStatus = ShipmentStatus.CREATED
    shipping_cost: float = 0.0
    delay_hours: int = 0
    current_location: Optional[str] = None
    tracking_notes: Optional[str] = None


class ExceptionRecord(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    exception_code: str
    category: ExceptionCategory
    exception_type: str
    severity: ExceptionSeverity = ExceptionSeverity.MEDIUM
    status: ExceptionStatus = ExceptionStatus.OPEN
    order_id: Optional[str] = None
    shipment_id: Optional[str] = None
    purchase_order_id: Optional[str] = None
    warehouse_id: Optional[str] = None
    product_id: Optional[str] = None
    title: str
    description: str
    detected_at: Optional[datetime] = None
    root_cause: Optional[str] = None
    business_impact: Optional[str] = None
    estimated_financial_loss: float = 0.0
    resolved_at: Optional[datetime] = None


class ResolutionOption(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    exception_id: str
    option_name: str
    action_type: str
    description: str
    estimated_cost: float
    expected_time_hours: float
    inventory_impact: Optional[str] = None
    customer_impact: Optional[str] = None
    operational_risk: OperationalRisk = OperationalRisk.LOW
    feasibility: bool = True
    confidence_score: float = 0.85
    reasoning: str
    is_recommended: bool = False
    is_selected: bool = False
    parameters: Dict[str, Any] = Field(default_factory=dict)


class ActionRecord(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    exception_id: str
    resolution_option_id: Optional[str] = None
    action_type: str
    executed_by: str = "SYSTEM_AGENT"
    execution_status: ExecutionStatus = ExecutionStatus.PENDING
    payload: Dict[str, Any] = Field(default_factory=dict)
    result_message: Optional[str] = None
    executed_at: Optional[datetime] = None


class AuditLog(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    exception_id: Optional[str] = None
    agent_step: str
    tool_called: Optional[str] = None
    input_payload: Dict[str, Any] = Field(default_factory=dict)
    output_payload: Dict[str, Any] = Field(default_factory=dict)
    decision: Optional[str] = None
    human_approval_status: Optional[str] = None
    notes: Optional[str] = None
    created_at: Optional[datetime] = None


# -----------------------------------------------------------------------------
# DAY 2: AGENTIC INVESTIGATION SCHEMAS
# -----------------------------------------------------------------------------

class InvestigationStep(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    step_number: int
    thought: str
    tool_name: str
    tool_input: Dict[str, Any] = Field(default_factory=dict)
    tool_output_summary: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))



class BusinessImpact(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    inventory_impact: str
    procurement_impact: str
    logistics_impact: str
    customer_impact: str
    stockout_risk: str
    financial_exposure: Optional[float] = 0.0


class InvestigationResult(BaseModel):
    """Structured result returned at the conclusion of an Agentic AI Investigation."""
    model_config = ConfigDict(from_attributes=True)

    exception_id: str
    exception_type: str
    severity: str
    root_cause: str
    evidence: List[str] = Field(default_factory=list)
    inventory_impact: str
    procurement_impact: str
    logistics_impact: str
    customer_impact: str
    stockout_risk: str
    relevant_suppliers: List[Dict[str, Any]] = Field(default_factory=list)
    relevant_warehouses: List[Dict[str, Any]] = Field(default_factory=list)
    relevant_shipments: List[Dict[str, Any]] = Field(default_factory=list)
    investigation_steps: List[InvestigationStep] = Field(default_factory=list)
    tools_used: List[str] = Field(default_factory=list)
    confidence: float = 0.90
    investigation_complete: bool = True


# -----------------------------------------------------------------------------
# DAY 3: RESOLUTION & EXECUTION SCHEMAS
# -----------------------------------------------------------------------------

class ResolutionResult(BaseModel):
    """Structured result returned at the conclusion of Resolution Planning."""
    model_config = ConfigDict(from_attributes=True)

    exception_id: str
    recommended_option: ResolutionOption
    alternatives: List[ResolutionOption] = Field(default_factory=list)
    reasoning: str
    estimated_cost: float = 0.0
    estimated_time: float = 0.0  # in hours
    inventory_impact: str
    customer_impact: str
    operational_risk: str = "LOW"
    feasibility: bool = True
    confidence: float = 0.85
    approval_required: bool = True


class ExecutionResult(BaseModel):
    """Structured result returned after executing an approved resolution action."""
    model_config = ConfigDict(from_attributes=True)

    action_id: str
    exception_id: str
    resolution_option_id: Optional[str] = None
    action_type: str
    status: ExecutionStatus = ExecutionStatus.SUCCESS
    result_message: str
    verified_db_changes: Dict[str, Any] = Field(default_factory=dict)
    executed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


