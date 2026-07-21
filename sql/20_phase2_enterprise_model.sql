-- ===========================================================================
-- Phase 2 — Enterprise logistics model (PostgreSQL dialect; loader adapts for
-- SQLite by stripping the `sunlog.` schema qualifier, exactly as Phase 1 does).
--
-- The Phase 1 DDL (sql/02_create_tables.sql) created empty enterprise STUBS.
-- Phase 2 replaces them with the full, enriched definitions below. Tables are
-- DROPped children-first (they are empty, so this is lossless) and recreated
-- with complete columns + foreign keys. stg_shipment, stg_rejected_record,
-- validation_rule, data_quality_exception and all meta_* tables are Phase 1
-- artifacts and are intentionally NOT touched here.
--
-- Provenance: every table carries `data_class` (PUBLIC / DERIVED / SIMULATED).
-- This is the project's single provenance marker (the prompt's "source_type").
-- ===========================================================================

-- --- Drop empty Phase 1 enterprise stubs (children first) ------------------
DROP TABLE IF EXISTS sunlog.fact_invoice_approval;
DROP TABLE IF EXISTS sunlog.fact_accessorial_charge;
DROP TABLE IF EXISTS sunlog.fact_invoice_line;
DROP TABLE IF EXISTS sunlog.fact_freight_invoice;
DROP TABLE IF EXISTS sunlog.fact_proof_of_delivery;
DROP TABLE IF EXISTS sunlog.fact_claim;
DROP TABLE IF EXISTS sunlog.fact_accrual;
DROP TABLE IF EXISTS sunlog.fact_carrier_capacity;
DROP TABLE IF EXISTS sunlog.fact_shipment_milestone;
DROP TABLE IF EXISTS sunlog.fact_shipment;
DROP TABLE IF EXISTS sunlog.fact_purchase_order;
DROP TABLE IF EXISTS sunlog.dim_rate_card;
DROP TABLE IF EXISTS sunlog.dim_lane;
DROP TABLE IF EXISTS sunlog.dim_warehouse;
DROP TABLE IF EXISTS sunlog.dim_supplier;
DROP TABLE IF EXISTS sunlog.dim_business_partner;
DROP TABLE IF EXISTS sunlog.dim_product;
DROP TABLE IF EXISTS sunlog.dim_hts_code;
DROP TABLE IF EXISTS sunlog.dim_location_xref;
DROP TABLE IF EXISTS sunlog.dim_carrier;
DROP TABLE IF EXISTS sunlog.dim_location;
DROP TABLE IF EXISTS sunlog.meta_exception_manifest;
DROP TABLE IF EXISTS sunlog.rpt_lane_derivation;
DROP TABLE IF EXISTS sunlog.rpt_rate_reconciliation;
DROP TABLE IF EXISTS sunlog.rpt_phase2_baseline_validation;

-- ===========================================================================
-- Dimensions / master data
-- ===========================================================================
CREATE TABLE sunlog.dim_location (
    location_id         TEXT PRIMARY KEY,
    location_name       TEXT NOT NULL,
    city                TEXT,
    state_or_province   TEXT,
    country             TEXT,
    region              TEXT,
    location_type       TEXT,               -- MANUFACTURING_SITE / DISTRIBUTION_CENTER / WAREHOUSE / CUSTOMER_SITE / COUNTRY_FALLBACK
    latitude            NUMERIC(9,6),        -- NULL where source is insufficient (never fabricated)
    longitude           NUMERIC(9,6),
    active_flag         INTEGER NOT NULL DEFAULT 1,
    data_class          TEXT NOT NULL        -- PUBLIC / DERIVED / SIMULATED
);

-- Preserves the original raw location strings and how each mapped to a location_id.
CREATE TABLE sunlog.dim_location_xref (
    xref_id             TEXT PRIMARY KEY,
    raw_location_string TEXT NOT NULL,
    raw_field           TEXT NOT NULL,       -- manufacturing_site / destination_country
    location_id         TEXT NOT NULL REFERENCES sunlog.dim_location(location_id),
    match_method        TEXT NOT NULL,       -- EXACT / COUNTRY_PARSED / COUNTRY_FALLBACK
    data_class          TEXT NOT NULL DEFAULT 'DERIVED'
);

CREATE TABLE sunlog.dim_hts_code (
    hts_code                    TEXT PRIMARY KEY,
    product_category            TEXT NOT NULL,
    description                 TEXT,
    effective_start_date        DATE,
    effective_end_date          DATE,
    hazardous_material_flag     INTEGER NOT NULL DEFAULT 0,
    customs_document_required_flag INTEGER NOT NULL DEFAULT 1,
    code_type                   TEXT NOT NULL DEFAULT 'SIMULATED_ILLUSTRATIVE',  -- NOT official US HTS
    data_class                  TEXT NOT NULL DEFAULT 'SIMULATED'
);

CREATE TABLE sunlog.dim_product (
    product_id          TEXT PRIMARY KEY,
    product_sku         TEXT NOT NULL,
    product_category    TEXT NOT NULL,       -- SOLAR_MODULE / INVERTER / BATTERY_ESS / BOS_COMPONENT
    product_description TEXT,
    unit_of_measure     TEXT,
    unit_weight_kg      NUMERIC(12,4),       -- nominal pack weight (median of observed weight/qty)
    unit_value_usd      NUMERIC(12,4),       -- nominal pack value  (median of observed value/qty)
    hts_code            TEXT REFERENCES sunlog.dim_hts_code(hts_code),
    hazardous_material_flag INTEGER NOT NULL DEFAULT 0,
    temperature_controlled_flag INTEGER NOT NULL DEFAULT 0,
    stackable_flag      INTEGER NOT NULL DEFAULT 1,
    active_flag         INTEGER NOT NULL DEFAULT 1,
    data_class          TEXT NOT NULL DEFAULT 'SIMULATED'
);

-- Unified partner registry (suppliers + carriers + brokers + customers).
CREATE TABLE sunlog.dim_business_partner (
    partner_id          TEXT PRIMARY KEY,
    partner_name        TEXT NOT NULL,
    partner_type        TEXT NOT NULL,       -- SUPPLIER / CARRIER / BROKER / CUSTOMER
    country             TEXT,
    region              TEXT,
    active_flag         INTEGER NOT NULL DEFAULT 1,
    data_class          TEXT NOT NULL DEFAULT 'DERIVED'
);

CREATE TABLE sunlog.dim_supplier (
    supplier_id             TEXT PRIMARY KEY,
    supplier_name           TEXT NOT NULL,   -- real vendor name from public source (PUBLIC)
    supplier_location_id    TEXT REFERENCES sunlog.dim_location(location_id),
    primary_product_category TEXT,
    country                 TEXT,
    active_flag             INTEGER NOT NULL DEFAULT 1,
    data_class              TEXT NOT NULL DEFAULT 'DERIVED'
);

CREATE TABLE sunlog.dim_warehouse (
    warehouse_id        TEXT PRIMARY KEY,
    warehouse_name      TEXT NOT NULL,
    location_id         TEXT REFERENCES sunlog.dim_location(location_id),
    warehouse_type      TEXT,                -- DISTRIBUTION_CENTER / CROSS_DOCK
    capacity_weight_kg  NUMERIC(14,2),
    capacity_pallets    INTEGER,
    active_flag         INTEGER NOT NULL DEFAULT 1,
    data_class          TEXT NOT NULL DEFAULT 'SIMULATED'
);

CREATE TABLE sunlog.dim_carrier (
    carrier_id          TEXT PRIMARY KEY,
    carrier_name        TEXT NOT NULL,       -- fictional (see config/project_config.yaml)
    carrier_type        TEXT,                -- OCEAN_LINE / AIR_CARGO / TRUCKING / RAIL / MULTIMODAL / FORWARDER / BROKER / FINAL_MILE
    primary_mode        TEXT,
    operating_region    TEXT,
    payment_terms       TEXT,
    default_currency    TEXT,
    active_flag         INTEGER NOT NULL DEFAULT 1,
    effective_start_date DATE,
    effective_end_date  DATE,
    data_class          TEXT NOT NULL DEFAULT 'SIMULATED'
);

CREATE TABLE sunlog.dim_lane (
    lane_id                 TEXT PRIMARY KEY,
    origin_location_id      TEXT REFERENCES sunlog.dim_location(location_id),
    destination_location_id TEXT REFERENCES sunlog.dim_location(location_id),
    origin_name             TEXT,
    destination_name        TEXT,
    transport_mode          TEXT,
    lane_region             TEXT,
    standard_transit_days   INTEGER,
    estimated_distance      NUMERIC(10,1),   -- NULL: true geographic distance not measurable from source
    distance_unit           TEXT,
    transit_derivation_method TEXT,          -- MODE_REGION_STANDARD
    active_flag             INTEGER NOT NULL DEFAULT 1,
    data_class              TEXT NOT NULL DEFAULT 'DERIVED'
);

CREATE TABLE sunlog.dim_rate_card (
    rate_id             TEXT PRIMARY KEY,
    carrier_id          TEXT REFERENCES sunlog.dim_carrier(carrier_id),
    lane_id             TEXT REFERENCES sunlog.dim_lane(lane_id),
    transport_mode      TEXT,
    effective_start_date DATE NOT NULL,
    effective_end_date  DATE NOT NULL,
    rate_basis          TEXT NOT NULL,       -- PER_KG / PER_SHIPMENT / FLAT_LANE / WEIGHT_BAND
    base_rate           NUMERIC(12,4),
    rate_per_kg         NUMERIC(12,4),
    rate_per_shipment   NUMERIC(12,2),
    minimum_charge      NUMERIC(12,2),
    fuel_percentage     NUMERIC(6,4),
    currency            TEXT NOT NULL,
    detention_allowed_flag  INTEGER NOT NULL DEFAULT 1,
    demurrage_allowed_flag  INTEGER NOT NULL DEFAULT 1,
    storage_allowed_flag    INTEGER NOT NULL DEFAULT 1,
    data_class          TEXT NOT NULL DEFAULT 'SIMULATED'
);

-- ===========================================================================
-- Operational facts
-- ===========================================================================
CREATE TABLE sunlog.fact_purchase_order (
    po_id               TEXT PRIMARY KEY,
    po_number           TEXT NOT NULL,
    supplier_id         TEXT REFERENCES sunlog.dim_supplier(supplier_id),
    product_id          TEXT REFERENCES sunlog.dim_product(product_id),
    ordered_quantity    BIGINT,
    unit_price          NUMERIC(12,4),
    purchase_value      NUMERIC(16,2),
    currency            TEXT,
    po_created_date     DATE,
    expected_ship_date  DATE,
    expected_delivery_date DATE,
    po_status           TEXT,                -- OPEN / SHIPPED / CLOSED
    data_class          TEXT NOT NULL DEFAULT 'DERIVED'
);

CREATE TABLE sunlog.fact_shipment (
    shipment_id         TEXT PRIMARY KEY,
    source_record_id    BIGINT REFERENCES sunlog.stg_shipment(source_record_id),  -- lineage
    po_id               TEXT REFERENCES sunlog.fact_purchase_order(po_id),
    carrier_id          TEXT REFERENCES sunlog.dim_carrier(carrier_id),
    lane_id             TEXT REFERENCES sunlog.dim_lane(lane_id),
    product_id          TEXT REFERENCES sunlog.dim_product(product_id),
    origin_location_id  TEXT REFERENCES sunlog.dim_location(location_id),
    destination_location_id TEXT REFERENCES sunlog.dim_location(location_id),
    warehouse_id        TEXT REFERENCES sunlog.dim_warehouse(warehouse_id),
    shipment_mode       TEXT,
    incoterm            TEXT,
    booking_date        DATE,
    planned_ship_date   DATE,
    actual_ship_date    DATE,
    planned_delivery_date DATE,
    actual_delivery_date  DATE,
    planned_quantity    BIGINT,
    shipped_quantity    BIGINT,
    delivered_quantity  BIGINT,
    shipment_weight_kg  NUMERIC(14,2),
    shipment_value_usd  NUMERIC(16,2),
    shipment_status     TEXT,                -- IN_TRANSIT / DELIVERED
    customs_required_flag INTEGER NOT NULL DEFAULT 0,
    hazmat_flag         INTEGER NOT NULL DEFAULT 0,
    is_delivered_flag   INTEGER NOT NULL DEFAULT 1,
    ship_date_derived_flag INTEGER NOT NULL DEFAULT 1,  -- source has no ship date
    weight_imputed_flag INTEGER NOT NULL DEFAULT 0,
    mode_imputed_flag   INTEGER NOT NULL DEFAULT 0,
    data_class          TEXT NOT NULL DEFAULT 'DERIVED'
);

CREATE TABLE sunlog.fact_shipment_milestone (
    milestone_id        TEXT PRIMARY KEY,
    shipment_id         TEXT REFERENCES sunlog.fact_shipment(shipment_id),
    milestone_type      TEXT NOT NULL,
    milestone_sequence  INTEGER NOT NULL,
    planned_timestamp   TIMESTAMP,
    actual_timestamp    TIMESTAMP,
    milestone_status    TEXT,                -- PLANNED / COMPLETED / MISSED / SKIPPED
    exception_reason    TEXT,
    data_class          TEXT NOT NULL DEFAULT 'SIMULATED'
);

CREATE TABLE sunlog.fact_freight_invoice (
    invoice_id          TEXT PRIMARY KEY,
    invoice_number      TEXT NOT NULL,
    shipment_id         TEXT REFERENCES sunlog.fact_shipment(shipment_id),
    carrier_id          TEXT REFERENCES sunlog.dim_carrier(carrier_id),
    invoice_date        DATE,
    service_period_start DATE,
    service_period_end  DATE,
    base_charge         NUMERIC(14,2),
    fuel_surcharge      NUMERIC(14,2),
    accessorial_charge  NUMERIC(14,2),
    tax_amount          NUMERIC(14,2),
    invoice_total       NUMERIC(14,2),
    currency            TEXT,
    approval_status     TEXT,                -- PENDING / APPROVED / REJECTED / ON_HOLD
    payment_status      TEXT,                -- UNPAID / PAID / DISPUTED
    data_class          TEXT NOT NULL DEFAULT 'SIMULATED'
);

CREATE TABLE sunlog.fact_invoice_line (
    invoice_line_id     TEXT PRIMARY KEY,
    invoice_id          TEXT REFERENCES sunlog.fact_freight_invoice(invoice_id),
    line_type           TEXT NOT NULL,       -- BASE_FREIGHT / FUEL_SURCHARGE / ACCESSORIAL / TAX
    description         TEXT,
    amount              NUMERIC(14,2),
    currency            TEXT,
    data_class          TEXT NOT NULL DEFAULT 'SIMULATED'
);

CREATE TABLE sunlog.fact_accessorial_charge (
    accessorial_id      TEXT PRIMARY KEY,
    invoice_id          TEXT REFERENCES sunlog.fact_freight_invoice(invoice_id),
    shipment_id         TEXT REFERENCES sunlog.fact_shipment(shipment_id),
    charge_type         TEXT NOT NULL,       -- DETENTION / DEMURRAGE / STORAGE / LIFTGATE / CUSTOMS_DOC / RE_DELIVERY
    charge_amount       NUMERIC(12,2),
    supporting_document_flag INTEGER NOT NULL DEFAULT 1,
    contractually_allowed_flag INTEGER NOT NULL DEFAULT 1,
    approval_status     TEXT,
    reason              TEXT,
    data_class          TEXT NOT NULL DEFAULT 'SIMULATED'
);

CREATE TABLE sunlog.fact_proof_of_delivery (
    pod_id              TEXT PRIMARY KEY,
    shipment_id         TEXT REFERENCES sunlog.fact_shipment(shipment_id),
    delivery_timestamp  TIMESTAMP,
    received_timestamp  TIMESTAMP,
    recipient_name      TEXT,                -- generic role-based (no real PII)
    document_reference  TEXT,
    pod_status          TEXT,                -- RECEIVED / MISSING / PENDING
    data_class          TEXT NOT NULL DEFAULT 'SIMULATED'
);

CREATE TABLE sunlog.fact_claim (
    claim_id            TEXT PRIMARY KEY,
    shipment_id         TEXT REFERENCES sunlog.fact_shipment(shipment_id),
    claim_type          TEXT,                -- DAMAGE / SHORTAGE / LOSS / DOCUMENTATION / TEMPERATURE_EXCURSION
    claim_amount        NUMERIC(12,2),
    claim_status        TEXT,                -- OPEN / APPROVED / DENIED / CLOSED
    root_cause          TEXT,
    created_date        DATE,
    closed_date         DATE,
    data_class          TEXT NOT NULL DEFAULT 'SIMULATED'
);

CREATE TABLE sunlog.fact_carrier_capacity (
    capacity_id         TEXT PRIMARY KEY,
    carrier_id          TEXT REFERENCES sunlog.dim_carrier(carrier_id),
    lane_id             TEXT REFERENCES sunlog.dim_lane(lane_id),
    period_start        DATE NOT NULL,
    period_month        TEXT NOT NULL,       -- YYYY-MM
    available_capacity_kg NUMERIC(16,2),
    booked_capacity_kg  NUMERIC(16,2),
    utilized_capacity_kg NUMERIC(16,2),
    capacity_utilization_pct NUMERIC(6,2),
    data_class          TEXT NOT NULL DEFAULT 'SIMULATED'
);

CREATE TABLE sunlog.fact_invoice_approval (
    approval_id         TEXT PRIMARY KEY,
    invoice_id          TEXT REFERENCES sunlog.fact_freight_invoice(invoice_id),
    approval_stage      TEXT NOT NULL,       -- LOGISTICS_REVIEW / RATE_VALIDATION / FINANCE_APPROVAL / PAYMENT_RELEASE
    assigned_role       TEXT,
    submitted_timestamp TIMESTAMP,
    approved_timestamp  TIMESTAMP,
    approval_status     TEXT,                -- PENDING / APPROVED / REJECTED
    rejection_reason    TEXT,
    data_class          TEXT NOT NULL DEFAULT 'SIMULATED'
);

CREATE TABLE sunlog.fact_accrual (
    accrual_id          TEXT PRIMARY KEY,
    shipment_id         TEXT REFERENCES sunlog.fact_shipment(shipment_id),
    accounting_period   TEXT NOT NULL,       -- YYYY-MM
    expected_freight_cost NUMERIC(14,2),
    invoice_received_flag INTEGER NOT NULL DEFAULT 0,
    actual_invoice_cost NUMERIC(14,2),
    accrual_status      TEXT,                -- ACCRUED / RELEASED / PARTIAL
    accrual_created_date DATE,
    accrual_release_date DATE,
    accrual_variance    NUMERIC(14,2),
    data_class          TEXT NOT NULL DEFAULT 'DERIVED'
);

-- ===========================================================================
-- Exception manifest + Phase 2 reports
-- ===========================================================================
CREATE TABLE sunlog.meta_exception_manifest (
    exception_manifest_id TEXT PRIMARY KEY,
    exception_type      TEXT NOT NULL,
    target_table        TEXT NOT NULL,
    record_id           TEXT NOT NULL,
    column_name         TEXT,
    clean_value         TEXT,
    injected_value      TEXT,
    injection_timestamp TIMESTAMP,
    random_seed         INTEGER,
    configured_rate     NUMERIC(8,5),
    severity            TEXT,
    expected_detection_rule TEXT,
    data_class          TEXT NOT NULL DEFAULT 'SIMULATED'
);

CREATE TABLE sunlog.rpt_lane_derivation (
    lane_id             TEXT PRIMARY KEY,
    origin_name         TEXT,
    destination_name    TEXT,
    transport_mode      TEXT,
    n_shipments         INTEGER,
    median_order_lead_days NUMERIC(8,2),      -- real proxy: actual_delivery - po_sent (where available)
    median_derived_transit_days NUMERIC(8,2), -- median of generated actual transit
    standard_transit_days INTEGER,
    derivation_method   TEXT,
    data_sufficiency    TEXT                  -- HIGH / MEDIUM / LOW
);

CREATE TABLE sunlog.rpt_rate_reconciliation (
    reconciliation_scope TEXT PRIMARY KEY,    -- e.g. mode name or 'ALL'
    n_shipments_with_freight INTEGER,
    median_observed_freight NUMERIC(14,2),
    median_expected_freight NUMERIC(14,2),
    expected_to_observed_ratio NUMERIC(8,4),
    notes               TEXT
);

CREATE TABLE sunlog.rpt_phase2_baseline_validation (
    validation_name     TEXT PRIMARY KEY,
    records_tested      BIGINT,
    failures            BIGINT,
    pass_rate           NUMERIC(7,4),
    severity            TEXT,
    status              TEXT                  -- PASS / FAIL
);

-- --- Indexes ---------------------------------------------------------------
CREATE INDEX IF NOT EXISTS ix_p2_shipment_carrier  ON sunlog.fact_shipment (carrier_id);
CREATE INDEX IF NOT EXISTS ix_p2_shipment_lane     ON sunlog.fact_shipment (lane_id);
CREATE INDEX IF NOT EXISTS ix_p2_shipment_source   ON sunlog.fact_shipment (source_record_id);
CREATE INDEX IF NOT EXISTS ix_p2_shipment_status   ON sunlog.fact_shipment (shipment_status);
CREATE INDEX IF NOT EXISTS ix_p2_milestone_ship    ON sunlog.fact_shipment_milestone (shipment_id, milestone_sequence);
CREATE INDEX IF NOT EXISTS ix_p2_invoice_ship      ON sunlog.fact_freight_invoice (shipment_id);
CREATE INDEX IF NOT EXISTS ix_p2_invoice_number    ON sunlog.fact_freight_invoice (invoice_number);
CREATE INDEX IF NOT EXISTS ix_p2_invline_invoice   ON sunlog.fact_invoice_line (invoice_id);
CREATE INDEX IF NOT EXISTS ix_p2_accessorial_inv   ON sunlog.fact_accessorial_charge (invoice_id);
CREATE INDEX IF NOT EXISTS ix_p2_ratecard_lookup   ON sunlog.dim_rate_card (carrier_id, lane_id, transport_mode);
CREATE INDEX IF NOT EXISTS ix_p2_accrual_period    ON sunlog.fact_accrual (accounting_period);
CREATE INDEX IF NOT EXISTS ix_p2_capacity_period   ON sunlog.fact_carrier_capacity (period_month);
CREATE INDEX IF NOT EXISTS ix_p2_manifest_type     ON sunlog.meta_exception_manifest (exception_type, target_table);
