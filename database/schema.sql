-- =============================================================================
-- Supply Chain Exception Resolution Agent - Database Schema
-- Compatible with Supabase PostgreSQL
-- =============================================================================

-- Enable UUID extension if available
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Drop existing tables in reverse order of dependencies (if re-creating)
DROP TABLE IF EXISTS data_sources CASCADE;
DROP TABLE IF EXISTS audit_logs CASCADE;
DROP TABLE IF EXISTS actions CASCADE;
DROP TABLE IF EXISTS resolution_options CASCADE;
DROP TABLE IF EXISTS exceptions CASCADE;
DROP TABLE IF EXISTS shipments CASCADE;
DROP TABLE IF EXISTS routes CASCADE;
DROP TABLE IF EXISTS carriers CASCADE;
DROP TABLE IF EXISTS purchase_order_items CASCADE;
DROP TABLE IF EXISTS purchase_orders CASCADE;
DROP TABLE IF EXISTS suppliers CASCADE;
DROP TABLE IF EXISTS inventory CASCADE;
DROP TABLE IF EXISTS warehouses CASCADE;
DROP TABLE IF EXISTS order_items CASCADE;
DROP TABLE IF EXISTS orders CASCADE;
DROP TABLE IF EXISTS products CASCADE;
DROP TABLE IF EXISTS customers CASCADE;

-- -----------------------------------------------------------------------------
-- 1. CUSTOMERS
-- -----------------------------------------------------------------------------
CREATE TABLE customers (
    id VARCHAR(64) PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    email VARCHAR(255),
    tier VARCHAR(50) DEFAULT 'STANDARD' CHECK (tier IN ('STANDARD', 'PRIORITY', 'ENTERPRISE', 'VIP')),
    sla_hours INTEGER DEFAULT 48,
    contact_phone VARCHAR(50),
    shipping_address TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- -----------------------------------------------------------------------------
-- 2. PRODUCTS
-- -----------------------------------------------------------------------------
CREATE TABLE products (
    id VARCHAR(64) PRIMARY KEY,
    sku VARCHAR(100) UNIQUE NOT NULL,
    name VARCHAR(255) NOT NULL,
    category VARCHAR(100),
    unit_price NUMERIC(12, 2) NOT NULL,
    unit_cost NUMERIC(12, 2) NOT NULL,
    weight_kg NUMERIC(10, 4),
    primary_supplier_id VARCHAR(64),
    critical_level VARCHAR(20) DEFAULT 'MEDIUM' CHECK (critical_level IN ('LOW', 'MEDIUM', 'HIGH', 'CRITICAL')),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- -----------------------------------------------------------------------------
-- 3. WAREHOUSES
-- -----------------------------------------------------------------------------
CREATE TABLE warehouses (
    id VARCHAR(64) PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    code VARCHAR(50) UNIQUE NOT NULL,
    location VARCHAR(255) NOT NULL,
    city VARCHAR(100) NOT NULL,
    state VARCHAR(100),
    country VARCHAR(100),
    capacity_sqft INTEGER,
    operating_cost_per_day NUMERIC(10, 2),
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- -----------------------------------------------------------------------------
-- 4. INVENTORY
-- -----------------------------------------------------------------------------
CREATE TABLE inventory (
    id VARCHAR(64) PRIMARY KEY,
    warehouse_id VARCHAR(64) NOT NULL REFERENCES warehouses(id) ON DELETE RESTRICT,
    product_id VARCHAR(64) NOT NULL REFERENCES products(id) ON DELETE RESTRICT,
    quantity_available INTEGER NOT NULL DEFAULT 0 CHECK (quantity_available >= 0),
    quantity_reserved INTEGER NOT NULL DEFAULT 0 CHECK (quantity_reserved >= 0),
    quantity_in_transit INTEGER NOT NULL DEFAULT 0 CHECK (quantity_in_transit >= 0),
    reorder_point INTEGER NOT NULL DEFAULT 50,
    safety_stock INTEGER NOT NULL DEFAULT 20,
    unit_holding_cost_per_day NUMERIC(8, 2),
    last_restocked_at TIMESTAMP WITH TIME ZONE,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_warehouse_product UNIQUE (warehouse_id, product_id)
);

-- -----------------------------------------------------------------------------
-- 5. SUPPLIERS
-- -----------------------------------------------------------------------------
CREATE TABLE suppliers (
    id VARCHAR(64) PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    code VARCHAR(50) UNIQUE NOT NULL,
    category VARCHAR(100),
    city VARCHAR(100) NOT NULL,
    country VARCHAR(100),
    lead_time_days INTEGER NOT NULL DEFAULT 7,
    expedite_lead_time_days INTEGER DEFAULT 3,
    reliability_rating NUMERIC(3, 2) DEFAULT 0.95 CHECK (reliability_rating BETWEEN 0.0 AND 1.0),
    capacity_units_per_day INTEGER DEFAULT 1000,
    current_capacity_utilized INTEGER DEFAULT 400,
    expedite_cost_multiplier NUMERIC(4, 2),
    contact_email VARCHAR(255),
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Products name their usual supplier; declared here because suppliers is created
-- after products.
ALTER TABLE products ADD CONSTRAINT fk_products_primary_supplier
    FOREIGN KEY (primary_supplier_id) REFERENCES suppliers(id) ON DELETE SET NULL;

-- -----------------------------------------------------------------------------
-- 6. CARRIERS
-- -----------------------------------------------------------------------------
CREATE TABLE carriers (
    id VARCHAR(64) PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    code VARCHAR(50) UNIQUE NOT NULL,
    mode VARCHAR(50) DEFAULT 'ROAD' CHECK (mode IN ('ROAD', 'AIR', 'RAIL', 'OCEAN')),
    reliability_rating NUMERIC(3, 2) DEFAULT 0.92 CHECK (reliability_rating BETWEEN 0.0 AND 1.0),
    base_cost_per_km NUMERIC(8, 2),
    expedite_cost_multiplier NUMERIC(4, 2),
    avg_speed_kmh NUMERIC(6, 2),
    freight_cost_per_kg NUMERIC(10, 2),
    contact_phone VARCHAR(50),
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- -----------------------------------------------------------------------------
-- 7. ROUTES
-- -----------------------------------------------------------------------------
CREATE TABLE routes (
    id VARCHAR(64) PRIMARY KEY,
    origin_city VARCHAR(100) NOT NULL,
    destination_city VARCHAR(100) NOT NULL,
    distance_km NUMERIC(10, 2) NOT NULL,
    estimated_transit_hours NUMERIC(6, 2) NOT NULL,
    standard_risk_level VARCHAR(20) DEFAULT 'LOW' CHECK (standard_risk_level IN ('LOW', 'MEDIUM', 'HIGH')),
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_route_pair UNIQUE (origin_city, destination_city)
);

-- -----------------------------------------------------------------------------
-- 8. ORDERS
-- -----------------------------------------------------------------------------
CREATE TABLE orders (
    id VARCHAR(64) PRIMARY KEY,
    order_number VARCHAR(100) UNIQUE NOT NULL,
    customer_id VARCHAR(64) NOT NULL REFERENCES customers(id) ON DELETE RESTRICT,
    order_date TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    required_delivery_date TIMESTAMP WITH TIME ZONE NOT NULL,
    status VARCHAR(50) DEFAULT 'PENDING' CHECK (status IN ('PENDING', 'PROCESSING', 'SHIPPED', 'DELIVERED', 'DELAYED', 'CANCELLED', 'EXCEPTION')),
    total_amount NUMERIC(12, 2) NOT NULL DEFAULT 0.0,
    shipping_city VARCHAR(100) NOT NULL,
    shipping_address TEXT,
    priority VARCHAR(20) DEFAULT 'MEDIUM' CHECK (priority IN ('LOW', 'MEDIUM', 'HIGH', 'CRITICAL')),
    assigned_warehouse_id VARCHAR(64) REFERENCES warehouses(id),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- -----------------------------------------------------------------------------
-- 9. ORDER ITEMS
-- -----------------------------------------------------------------------------
CREATE TABLE order_items (
    id VARCHAR(64) PRIMARY KEY,
    order_id VARCHAR(64) NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
    product_id VARCHAR(64) NOT NULL REFERENCES products(id) ON DELETE RESTRICT,
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    unit_price NUMERIC(12, 2) NOT NULL,
    total_price NUMERIC(12, 2) NOT NULL,
    fulfilled_quantity INTEGER DEFAULT 0,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- -----------------------------------------------------------------------------
-- 10. PURCHASE ORDERS
-- -----------------------------------------------------------------------------
CREATE TABLE purchase_orders (
    id VARCHAR(64) PRIMARY KEY,
    po_number VARCHAR(100) UNIQUE NOT NULL,
    supplier_id VARCHAR(64) NOT NULL REFERENCES suppliers(id) ON DELETE RESTRICT,
    destination_warehouse_id VARCHAR(64) NOT NULL REFERENCES warehouses(id) ON DELETE RESTRICT,
    issue_date TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    expected_delivery_date TIMESTAMP WITH TIME ZONE NOT NULL,
    actual_delivery_date TIMESTAMP WITH TIME ZONE,
    status VARCHAR(50) DEFAULT 'ISSUED' CHECK (status IN ('ISSUED', 'CONFIRMED', 'IN_TRANSIT', 'RECEIVED', 'DELAYED', 'CANCELLED', 'EXPEDITED')),
    total_cost NUMERIC(12, 2) NOT NULL DEFAULT 0.0,
    is_expedited BOOLEAN DEFAULT FALSE,
    notes TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- -----------------------------------------------------------------------------
-- 11. PURCHASE ORDER ITEMS
-- -----------------------------------------------------------------------------
CREATE TABLE purchase_order_items (
    id VARCHAR(64) PRIMARY KEY,
    purchase_order_id VARCHAR(64) NOT NULL REFERENCES purchase_orders(id) ON DELETE CASCADE,
    product_id VARCHAR(64) NOT NULL REFERENCES products(id) ON DELETE RESTRICT,
    quantity_ordered INTEGER NOT NULL CHECK (quantity_ordered > 0),
    quantity_received INTEGER DEFAULT 0,
    unit_cost NUMERIC(12, 2) NOT NULL,
    total_cost NUMERIC(12, 2) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- -----------------------------------------------------------------------------
-- 12. SHIPMENTS
-- -----------------------------------------------------------------------------
CREATE TABLE shipments (
    id VARCHAR(64) PRIMARY KEY,
    shipment_number VARCHAR(100) UNIQUE NOT NULL,
    order_id VARCHAR(64) REFERENCES orders(id) ON DELETE SET NULL,
    purchase_order_id VARCHAR(64) REFERENCES purchase_orders(id) ON DELETE SET NULL,
    carrier_id VARCHAR(64) NOT NULL REFERENCES carriers(id) ON DELETE RESTRICT,
    route_id VARCHAR(64) REFERENCES routes(id) ON DELETE SET NULL,
    origin_location VARCHAR(255) NOT NULL,
    destination_location VARCHAR(255) NOT NULL,
    pickup_date TIMESTAMP WITH TIME ZONE,
    expected_delivery_date TIMESTAMP WITH TIME ZONE NOT NULL,
    actual_delivery_date TIMESTAMP WITH TIME ZONE,
    status VARCHAR(50) DEFAULT 'CREATED' CHECK (status IN ('CREATED', 'IN_TRANSIT', 'OUT_FOR_DELIVERY', 'DELIVERED', 'DELAYED', 'REROUTED', 'EXCEPTION', 'CANCELLED')),
    shipping_cost NUMERIC(10, 2) NOT NULL DEFAULT 0.0,
    delay_hours INTEGER DEFAULT 0,
    weight_kg NUMERIC(12, 2),
    current_location VARCHAR(255),
    tracking_notes TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- -----------------------------------------------------------------------------
-- 13. EXCEPTIONS
-- -----------------------------------------------------------------------------
CREATE TABLE exceptions (
    id VARCHAR(64) PRIMARY KEY,
    exception_code VARCHAR(100) UNIQUE NOT NULL,
    category VARCHAR(50) NOT NULL CHECK (category IN ('PROCUREMENT', 'LOGISTICS', 'INVENTORY', 'CROSS_FUNCTIONAL')),
    exception_type VARCHAR(100) NOT NULL,
    severity VARCHAR(20) DEFAULT 'MEDIUM' CHECK (severity IN ('LOW', 'MEDIUM', 'HIGH', 'CRITICAL')),
    status VARCHAR(50) DEFAULT 'OPEN' CHECK (status IN ('OPEN', 'INVESTIGATING', 'PENDING_APPROVAL', 'APPROVED', 'RESOLVED', 'REJECTED', 'IGNORED')),
    order_id VARCHAR(64) REFERENCES orders(id) ON DELETE SET NULL,
    shipment_id VARCHAR(64) REFERENCES shipments(id) ON DELETE SET NULL,
    purchase_order_id VARCHAR(64) REFERENCES purchase_orders(id) ON DELETE SET NULL,
    warehouse_id VARCHAR(64) REFERENCES warehouses(id) ON DELETE SET NULL,
    product_id VARCHAR(64) REFERENCES products(id) ON DELETE SET NULL,
    title VARCHAR(255) NOT NULL,
    description TEXT NOT NULL,
    detected_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    root_cause TEXT,
    business_impact TEXT,
    estimated_financial_loss NUMERIC(12, 2) DEFAULT 0.0,
    resolved_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- -----------------------------------------------------------------------------
-- 14. RESOLUTION OPTIONS
-- -----------------------------------------------------------------------------
CREATE TABLE resolution_options (
    id VARCHAR(64) PRIMARY KEY,
    exception_id VARCHAR(64) NOT NULL REFERENCES exceptions(id) ON DELETE CASCADE,
    option_name VARCHAR(255) NOT NULL,
    action_type VARCHAR(100) NOT NULL,
    description TEXT NOT NULL,
    estimated_cost NUMERIC(12, 2) NOT NULL DEFAULT 0.0,
    expected_time_hours NUMERIC(8, 2) NOT NULL DEFAULT 24.0,
    inventory_impact TEXT,
    customer_impact TEXT,
    operational_risk VARCHAR(20) DEFAULT 'LOW' CHECK (operational_risk IN ('LOW', 'MEDIUM', 'HIGH')),
    feasibility BOOLEAN DEFAULT TRUE,
    confidence_score NUMERIC(3, 2) DEFAULT 0.85 CHECK (confidence_score BETWEEN 0.0 AND 1.0),
    reasoning TEXT NOT NULL,
    is_recommended BOOLEAN DEFAULT FALSE,
    is_selected BOOLEAN DEFAULT FALSE,
    parameters JSONB DEFAULT '{}',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- -----------------------------------------------------------------------------
-- 15. ACTIONS
-- -----------------------------------------------------------------------------
CREATE TABLE actions (
    id VARCHAR(64) PRIMARY KEY,
    exception_id VARCHAR(64) NOT NULL REFERENCES exceptions(id) ON DELETE CASCADE,
    resolution_option_id VARCHAR(64) REFERENCES resolution_options(id) ON DELETE SET NULL,
    action_type VARCHAR(100) NOT NULL,
    executed_by VARCHAR(100) DEFAULT 'SYSTEM_AGENT',
    execution_status VARCHAR(50) DEFAULT 'PENDING' CHECK (execution_status IN ('PENDING', 'SUCCESS', 'FAILED', 'CANCELLED')),
    payload JSONB DEFAULT '{}',
    result_message TEXT,
    executed_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- -----------------------------------------------------------------------------
-- 16. AUDIT LOGS
-- -----------------------------------------------------------------------------
CREATE TABLE audit_logs (
    id VARCHAR(64) PRIMARY KEY,
    exception_id VARCHAR(64) REFERENCES exceptions(id) ON DELETE CASCADE,
    agent_step VARCHAR(100) NOT NULL,
    tool_called VARCHAR(100),
    input_payload JSONB DEFAULT '{}',
    output_payload JSONB DEFAULT '{}',
    decision TEXT,
    human_approval_status VARCHAR(50),
    notes TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- -----------------------------------------------------------------------------
-- 17. DATA SOURCES — provenance of the loaded operational data
-- -----------------------------------------------------------------------------
CREATE TABLE data_sources (
    id VARCHAR(64) PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    kaggle_ref VARCHAR(255),
    rows_in_source INTEGER,
    rows_loaded INTEGER,
    source_as_of DATE,
    replayed_to DATE,
    notes TEXT,
    loaded_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- -----------------------------------------------------------------------------
-- INDEXES FOR PERFORMANCE & FAST LOOKUP
-- -----------------------------------------------------------------------------
CREATE INDEX idx_orders_customer ON orders(customer_id);
CREATE INDEX idx_orders_status ON orders(status);
CREATE INDEX idx_inventory_warehouse_product ON inventory(warehouse_id, product_id);
CREATE INDEX idx_shipments_order ON shipments(order_id);
CREATE INDEX idx_shipments_status ON shipments(status);
CREATE INDEX idx_purchase_orders_supplier ON purchase_orders(supplier_id);
CREATE INDEX idx_purchase_orders_status ON purchase_orders(status);
CREATE INDEX idx_exceptions_status ON exceptions(status);
CREATE INDEX idx_exceptions_category ON exceptions(category);
CREATE INDEX idx_exceptions_severity ON exceptions(severity);
CREATE INDEX idx_audit_logs_exception ON audit_logs(exception_id);
CREATE INDEX idx_order_items_order ON order_items(order_id);
CREATE INDEX idx_po_items_po ON purchase_order_items(purchase_order_id);
CREATE INDEX idx_shipments_po ON shipments(purchase_order_id);
CREATE INDEX idx_shipments_carrier ON shipments(carrier_id);
CREATE INDEX idx_shipments_expected ON shipments(expected_delivery_date);
CREATE INDEX idx_purchase_orders_expected ON purchase_orders(expected_delivery_date);
CREATE INDEX idx_inventory_product ON inventory(product_id);
CREATE INDEX idx_products_supplier ON products(primary_supplier_id);
CREATE INDEX idx_exceptions_shipment ON exceptions(shipment_id);
CREATE INDEX idx_exceptions_po ON exceptions(purchase_order_id);
CREATE INDEX idx_exceptions_wh_product ON exceptions(warehouse_id, product_id);
