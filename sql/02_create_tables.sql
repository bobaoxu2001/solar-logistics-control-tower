-- ===========================================================================
-- Solar Logistics Control Tower — relational model DDL (PostgreSQL dialect).
-- The loader (src/load_database.py) rewrites schema qualifiers for SQLite.
--
-- Layer conventions:
--   stg_*   staging of cleaned public source data (Phase 1)
--   dim_*   master data (Phase 2 — simulated enterprise data)
--   fact_*  transactional data (Phase 2)
--   meta_*  provenance, ETL and configuration
-- ===========================================================================

-- ---------------------------------------------------------------------------
-- Staging: cleaned public shipment data with full lineage
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS sunlog.stg_shipment (
    source_record_id        BIGINT PRIMARY KEY,     -- ID from the raw USAID file
    po_so_number            TEXT,
    asn_dn_number           TEXT,
    project_code            TEXT,
    destination_country     TEXT NOT NULL,
    managed_by              TEXT,
    fulfill_via             TEXT,
    incoterm                TEXT,
    shipment_mode_raw       TEXT,
    shipment_mode           TEXT,                   -- AIR / AIR_CHARTER / TRUCK / OCEAN / NULL
    missing_mode_flag       INTEGER NOT NULL DEFAULT 0,
    pq_first_sent_date      DATE,
    po_sent_date            DATE,
    scheduled_delivery_date DATE NOT NULL,
    actual_delivery_date    DATE NOT NULL,
    delivery_recorded_date  DATE,
    product_group_raw       TEXT,
    sub_classification_raw  TEXT,
    product_category        TEXT,                   -- SOLAR_MODULE / INVERTER / BATTERY_ESS / BOS_COMPONENT
    vendor_name             TEXT,
    item_description_raw    TEXT,
    manufacturing_site      TEXT,
    first_line_designation  INTEGER,
    unit_of_measure_per_pack INTEGER,
    line_item_quantity      BIGINT NOT NULL CHECK (line_item_quantity > 0),
    line_item_value_usd     NUMERIC(14,2),
    pack_price_usd          NUMERIC(12,2),
    unit_price_usd          NUMERIC(12,4),
    weight_kg               NUMERIC(12,2),
    weight_source           TEXT,
    freight_cost_usd        NUMERIC(12,2),
    freight_cost_source     TEXT,
    line_item_insurance_usd NUMERIC(12,2),
    reporting_scheduled_delivery_date DATE,
    reporting_actual_delivery_date    DATE
);

CREATE TABLE IF NOT EXISTS sunlog.stg_rejected_record (
    reject_id           TEXT PRIMARY KEY,
    source_record_id    TEXT,
    rejection_reason    TEXT NOT NULL,
    raw_payload         TEXT,               -- original row serialized as JSON
    rejected_at         TIMESTAMP NOT NULL
);

-- ---------------------------------------------------------------------------
-- Dimensions (populated in Phase 2 — simulated enterprise master data,
-- derived from the staged public shipments)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS sunlog.dim_location (
    location_id     TEXT PRIMARY KEY,
    location_name   TEXT NOT NULL,
    country         TEXT,
    region          TEXT,
    location_type   TEXT,                   -- MANUFACTURING_SITE / PORT / RDC / WAREHOUSE / CUSTOMER_SITE
    data_class      TEXT NOT NULL           -- PUBLIC / DERIVED / SIMULATED
);

CREATE TABLE IF NOT EXISTS sunlog.dim_carrier (
    carrier_id          TEXT PRIMARY KEY,
    carrier_name        TEXT NOT NULL,
    carrier_type        TEXT,               -- OCEAN_LINE / TRUCKING / AIR_CARGO / FORWARDER / MULTIMODAL
    primary_mode        TEXT,
    payment_terms       TEXT,
    currency            TEXT,
    active_flag         INTEGER NOT NULL DEFAULT 1,
    effective_start_date DATE,
    effective_end_date  DATE,
    data_class          TEXT NOT NULL DEFAULT 'SIMULATED'
);

CREATE TABLE IF NOT EXISTS sunlog.dim_lane (
    lane_id             TEXT PRIMARY KEY,
    origin_location    TEXT REFERENCES sunlog.dim_location(location_id),
    destination_location TEXT REFERENCES sunlog.dim_location(location_id),
    transport_mode      TEXT,
    standard_transit_days INTEGER,
    estimated_distance_km NUMERIC(10,1),
    lane_region         TEXT,
    active_flag         INTEGER NOT NULL DEFAULT 1,
    data_class          TEXT NOT NULL DEFAULT 'DERIVED'
);

CREATE TABLE IF NOT EXISTS sunlog.dim_product (
    product_id          TEXT PRIMARY KEY,
    product_category    TEXT NOT NULL,
    product_description TEXT,
    product_weight_kg   NUMERIC(10,2),
    unit_of_measure     TEXT,
    hts_code            TEXT,
    hazardous_material_flag INTEGER NOT NULL DEFAULT 0,
    data_class          TEXT NOT NULL DEFAULT 'SIMULATED'
);

CREATE TABLE IF NOT EXISTS sunlog.dim_rate_card (
    rate_id             TEXT PRIMARY KEY,
    carrier_id          TEXT REFERENCES sunlog.dim_carrier(carrier_id),
    lane_id             TEXT REFERENCES sunlog.dim_lane(lane_id),
    transport_mode      TEXT,
    effective_start_date DATE NOT NULL,
    effective_end_date  DATE NOT NULL,
    base_rate           NUMERIC(12,4) NOT NULL,
    rate_basis          TEXT NOT NULL,      -- PER_KG / PER_SHIPMENT / PER_CONTAINER
    fuel_percentage     NUMERIC(5,2),
    minimum_charge      NUMERIC(12,2),
    currency            TEXT NOT NULL,
    data_class          TEXT NOT NULL DEFAULT 'SIMULATED'
);

-- ---------------------------------------------------------------------------
-- Facts (Phase 2)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS sunlog.fact_purchase_order (
    po_id               TEXT PRIMARY KEY,
    po_number           TEXT NOT NULL,
    supplier_id         TEXT,
    product_id          TEXT REFERENCES sunlog.dim_product(product_id),
    ordered_quantity    BIGINT,
    purchase_value_usd  NUMERIC(14,2),
    expected_ship_date  DATE,
    expected_delivery_date DATE,
    data_class          TEXT NOT NULL DEFAULT 'DERIVED'
);

CREATE TABLE IF NOT EXISTS sunlog.fact_shipment (
    shipment_id         TEXT PRIMARY KEY,
    source_record_id    BIGINT REFERENCES sunlog.stg_shipment(source_record_id),
    po_id               TEXT REFERENCES sunlog.fact_purchase_order(po_id),
    carrier_id          TEXT REFERENCES sunlog.dim_carrier(carrier_id),
    lane_id             TEXT REFERENCES sunlog.dim_lane(lane_id),
    product_id          TEXT REFERENCES sunlog.dim_product(product_id),
    origin_location_id  TEXT REFERENCES sunlog.dim_location(location_id),
    destination_location_id TEXT REFERENCES sunlog.dim_location(location_id),
    shipment_mode       TEXT,
    incoterm            TEXT,
    ship_date           DATE,
    planned_delivery_date DATE,
    actual_delivery_date  DATE,
    planned_quantity    BIGINT,
    delivered_quantity  BIGINT,
    shipment_weight_kg  NUMERIC(12,2),
    shipment_value_usd  NUMERIC(14,2),
    shipment_status     TEXT,               -- PLANNED / IN_TRANSIT / DELIVERED / EXCEPTION
    data_class          TEXT NOT NULL DEFAULT 'DERIVED'
);

CREATE TABLE IF NOT EXISTS sunlog.fact_shipment_milestone (
    milestone_id        TEXT PRIMARY KEY,
    shipment_id         TEXT REFERENCES sunlog.fact_shipment(shipment_id),
    milestone_type      TEXT NOT NULL,      -- BOOKING_CONFIRMED / PICKUP / ORIGIN_DEPARTURE / PORT_ARRIVAL /
                                            -- CUSTOMS_CLEARANCE / WAREHOUSE_ARRIVAL / OUT_FOR_DELIVERY /
                                            -- CUSTOMER_DELIVERY / POD_RECEIVED
    planned_timestamp   TIMESTAMP,
    actual_timestamp    TIMESTAMP,
    milestone_status    TEXT,               -- PLANNED / COMPLETED / MISSED / SKIPPED
    exception_reason    TEXT,
    data_class          TEXT NOT NULL DEFAULT 'SIMULATED'
);

CREATE TABLE IF NOT EXISTS sunlog.fact_freight_invoice (
    invoice_id          TEXT PRIMARY KEY,
    invoice_number      TEXT NOT NULL,
    shipment_id         TEXT REFERENCES sunlog.fact_shipment(shipment_id),
    carrier_id          TEXT REFERENCES sunlog.dim_carrier(carrier_id),
    invoice_date        DATE,
    base_charge         NUMERIC(12,2),
    fuel_surcharge      NUMERIC(12,2),
    accessorial_charge  NUMERIC(12,2),
    tax_amount          NUMERIC(12,2),
    invoice_total       NUMERIC(12,2),
    currency            TEXT,
    approval_status     TEXT,               -- PENDING / APPROVED / REJECTED / ON_HOLD
    payment_status      TEXT,               -- UNPAID / PAID / DISPUTED
    data_class          TEXT NOT NULL DEFAULT 'SIMULATED'
);

CREATE TABLE IF NOT EXISTS sunlog.fact_accessorial_charge (
    accessorial_id      TEXT PRIMARY KEY,
    invoice_id          TEXT REFERENCES sunlog.fact_freight_invoice(invoice_id),
    charge_type         TEXT NOT NULL,      -- DETENTION / DEMURRAGE / LIFTGATE / STORAGE / RE_DELIVERY / CUSTOMS_EXAM
    charge_amount       NUMERIC(12,2),
    supporting_document_flag INTEGER NOT NULL DEFAULT 0,
    contractually_allowed_flag INTEGER NOT NULL DEFAULT 0,
    approval_status     TEXT,
    data_class          TEXT NOT NULL DEFAULT 'SIMULATED'
);

CREATE TABLE IF NOT EXISTS sunlog.fact_proof_of_delivery (
    pod_id              TEXT PRIMARY KEY,
    shipment_id         TEXT REFERENCES sunlog.fact_shipment(shipment_id),
    pod_received_date   DATE,
    pod_document_flag   INTEGER NOT NULL DEFAULT 0,
    received_by         TEXT,
    data_class          TEXT NOT NULL DEFAULT 'SIMULATED'
);

CREATE TABLE IF NOT EXISTS sunlog.fact_claim (
    claim_id            TEXT PRIMARY KEY,
    shipment_id         TEXT REFERENCES sunlog.fact_shipment(shipment_id),
    claim_type          TEXT,               -- DAMAGE / LOSS / SHORTAGE / DELAY
    claim_amount_usd    NUMERIC(12,2),
    claim_status        TEXT,               -- OPEN / APPROVED / DENIED / CLOSED
    root_cause          TEXT,
    created_date        DATE,
    closed_date         DATE,
    data_class          TEXT NOT NULL DEFAULT 'SIMULATED'
);

CREATE TABLE IF NOT EXISTS sunlog.fact_accrual (
    accrual_id          TEXT PRIMARY KEY,
    shipment_id         TEXT REFERENCES sunlog.fact_shipment(shipment_id),
    accounting_period   TEXT NOT NULL,      -- YYYY-MM
    expected_freight_cost NUMERIC(12,2),
    invoice_received_flag INTEGER NOT NULL DEFAULT 0,
    actual_invoice_cost NUMERIC(12,2),
    accrual_variance    NUMERIC(12,2),
    data_class          TEXT NOT NULL DEFAULT 'DERIVED'
);

CREATE TABLE IF NOT EXISTS sunlog.fact_carrier_capacity (
    capacity_id         TEXT PRIMARY KEY,
    carrier_id          TEXT REFERENCES sunlog.dim_carrier(carrier_id),
    lane_id             TEXT REFERENCES sunlog.dim_lane(lane_id),
    period_month        TEXT NOT NULL,      -- YYYY-MM
    committed_capacity_kg NUMERIC(14,2),
    tendered_weight_kg  NUMERIC(14,2),
    accepted_weight_kg  NUMERIC(14,2),
    data_class          TEXT NOT NULL DEFAULT 'SIMULATED'
);

CREATE TABLE IF NOT EXISTS sunlog.fact_invoice_approval (
    approval_id         TEXT PRIMARY KEY,
    invoice_id          TEXT REFERENCES sunlog.fact_freight_invoice(invoice_id),
    submitted_date      DATE,
    approved_date       DATE,
    approver_role       TEXT,
    approval_action     TEXT,               -- APPROVED / REJECTED / ESCALATED
    data_class          TEXT NOT NULL DEFAULT 'SIMULATED'
);

-- ---------------------------------------------------------------------------
-- Data-quality framework
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS sunlog.validation_rule (
    rule_id             TEXT PRIMARY KEY,
    rule_name           TEXT NOT NULL,
    target_table        TEXT NOT NULL,
    target_column       TEXT,
    rule_category       TEXT,               -- COMPLETENESS / UNIQUENESS / REFERENTIAL / VALIDITY / TIMELINESS
    severity            TEXT,               -- CRITICAL / HIGH / MEDIUM / LOW
    rule_description    TEXT,
    owner               TEXT,
    active_flag         INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS sunlog.data_quality_exception (
    exception_id        TEXT PRIMARY KEY,
    rule_id             TEXT REFERENCES sunlog.validation_rule(rule_id),
    record_id           TEXT,
    detected_timestamp  TIMESTAMP,
    severity            TEXT,
    exception_description TEXT,
    root_cause_category TEXT,
    resolution_status   TEXT DEFAULT 'OPEN',
    assigned_owner      TEXT,
    resolved_timestamp  TIMESTAMP
);

-- ---------------------------------------------------------------------------
-- Configuration & provenance
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS sunlog.meta_audit_threshold (
    threshold_name      TEXT PRIMARY KEY,
    threshold_value     NUMERIC(12,4) NOT NULL,
    description         TEXT
);

CREATE TABLE IF NOT EXISTS sunlog.meta_scorecard_weight (
    metric_name         TEXT PRIMARY KEY,
    weight              NUMERIC(5,4) NOT NULL,
    description         TEXT
);

CREATE TABLE IF NOT EXISTS sunlog.meta_source_provenance (
    source_name         TEXT PRIMARY KEY,
    source_url          TEXT,
    sha256              TEXT,
    row_count           BIGINT,
    loaded_at           TIMESTAMP,
    notes               TEXT
);

CREATE TABLE IF NOT EXISTS sunlog.meta_etl_log (
    run_id              TEXT PRIMARY KEY,
    step_name           TEXT NOT NULL,
    started_at          TIMESTAMP,
    finished_at         TIMESTAMP,
    rows_processed      BIGINT,
    rows_rejected       BIGINT,
    status              TEXT
);
