-- ===========================================================================
-- Phase 3 — Power BI reporting layer (PostgreSQL + SQLite).
-- Grain is explicit and dimensions use one-to-many relationships to facts.
-- reporting_date_dim, carrier_scorecard_result, and lane_scorecard_result are
-- materialized by Python before these views are created.
-- ===========================================================================

DROP VIEW IF EXISTS sunlog.rpt_lane_scorecard;
DROP VIEW IF EXISTS sunlog.rpt_carrier_scorecard;
DROP VIEW IF EXISTS sunlog.rpt_fact_claim;
DROP VIEW IF EXISTS sunlog.rpt_fact_accrual;
DROP VIEW IF EXISTS sunlog.rpt_fact_data_quality;
DROP VIEW IF EXISTS sunlog.rpt_fact_freight_audit;
DROP VIEW IF EXISTS sunlog.rpt_fact_milestone;
DROP VIEW IF EXISTS sunlog.rpt_fact_shipment;
DROP VIEW IF EXISTS sunlog.rpt_dim_location;
DROP VIEW IF EXISTS sunlog.rpt_dim_product;
DROP VIEW IF EXISTS sunlog.rpt_dim_lane;
DROP VIEW IF EXISTS sunlog.rpt_dim_carrier;
DROP VIEW IF EXISTS sunlog.rpt_dim_date;

CREATE VIEW sunlog.rpt_dim_date AS SELECT * FROM sunlog.reporting_date_dim;

CREATE VIEW sunlog.rpt_dim_carrier AS
SELECT carrier_id, carrier_name, carrier_type, primary_mode, operating_region,
       payment_terms, default_currency, active_flag, data_class
FROM sunlog.dim_carrier;

CREATE VIEW sunlog.rpt_dim_lane AS
SELECT lane_id, origin_location_id, destination_location_id, origin_name,
       destination_name, transport_mode, lane_region, standard_transit_days,
       transit_derivation_method, active_flag, data_class
FROM sunlog.dim_lane;

CREATE VIEW sunlog.rpt_dim_product AS
SELECT product_id, product_sku, product_category, product_description,
       unit_of_measure, hts_code, hazardous_material_flag,
       temperature_controlled_flag, active_flag, data_class
FROM sunlog.dim_product;

CREATE VIEW sunlog.rpt_dim_location AS
SELECT location_id, location_name, city, state_or_province, country, region,
       location_type, active_flag, data_class
FROM sunlog.dim_location;

-- Grain: one row per shipment.
CREATE VIEW sunlog.rpt_fact_shipment AS
SELECT shipment_id, source_record_id, carrier_id, lane_id, product_id,
       origin_location_id, destination_location_id, warehouse_id, shipment_mode,
       incoterm, shipment_status, planned_quantity, delivered_quantity,
       shipment_weight_kg, shipment_value_usd, planned_ship_date, actual_ship_date,
       planned_delivery_date, actual_delivery_date, is_delivered, on_time_flag,
       in_full_flag, otif_flag, late_flag, partial_flag, delay_days,
       planned_transit_days, actual_transit_days, transit_variance_days,
       within_standard_flag, git_flag, git_age_days, overdue_git_flag,
       reporting_month, has_pod, has_invoice, hazmat_flag, customs_required_flag
FROM sunlog.analytics_shipment;

-- Grain: one row per shipment milestone.
CREATE VIEW sunlog.rpt_fact_milestone AS
SELECT milestone_id, shipment_id, milestone_type, milestone_sequence,
       planned_timestamp, actual_timestamp, milestone_status, exception_reason,
       data_class
FROM sunlog.fact_shipment_milestone;

-- Grain: one row per freight invoice, including orphan/duplicate exposures.
CREATE VIEW sunlog.rpt_fact_freight_audit AS
SELECT fa.*, s.product_id, s.origin_location_id, s.destination_location_id,
       s.shipment_weight_kg, s.shipment_value_usd
FROM sunlog.v_freight_audit fa
LEFT JOIN sunlog.fact_shipment s ON fa.shipment_id = s.shipment_id;

-- Grain: one row per detected exception.
CREATE VIEW sunlog.rpt_fact_data_quality AS
SELECT d.detected_exception_id, d.rule_id, d.exception_type, d.record_id,
       d.record_type, d.detected_timestamp, d.severity, d.exception_description,
       d.business_owner, d.resolution_status, d.exception_age_days,
       d.source_layer, r.rule_category, r.expected_resolution_sla_hours,
       w.weight AS severity_weight
FROM sunlog.dq_detected_exception d
JOIN sunlog.dq_rule r ON d.rule_id = r.rule_id
JOIN sunlog.meta_dq_severity_weight w ON d.severity = w.severity;

-- Grain: one row per shipment accrual/accounting period record.
CREATE VIEW sunlog.rpt_fact_accrual AS
SELECT a.*, s.carrier_id, s.lane_id, s.product_id
FROM sunlog.fact_accrual a
JOIN sunlog.fact_shipment s ON a.shipment_id = s.shipment_id;

-- Grain: one row per claim.
CREATE VIEW sunlog.rpt_fact_claim AS
SELECT c.*, s.carrier_id, s.lane_id, s.product_id
FROM sunlog.fact_claim c
JOIN sunlog.fact_shipment s ON c.shipment_id = s.shipment_id;

CREATE VIEW sunlog.rpt_carrier_scorecard AS SELECT * FROM sunlog.carrier_scorecard_result;
CREATE VIEW sunlog.rpt_lane_scorecard AS SELECT * FROM sunlog.lane_scorecard_result;
