-- ===========================================================================
-- Phase 3 — Logistics KPI views (portable). Aggregate analytics_shipment
-- (built by src/build_analytics_base.py, which precomputes date-difference
-- flags so these views need no dialect-specific date functions) and the
-- operational fact tables. All KPIs are computed on the OPERATIONAL layer.
--
-- OTIF definitions:
--   on_time  = actual_delivery_date <= planned_delivery_date  (delivered only)
--   in_full  = delivered_quantity  >= planned_quantity        (delivered only)
--   otif     = on_time AND in_full
-- (flags are NULL for in-transit shipments, so AVG() ranges over delivered.)
-- ===========================================================================

DROP VIEW IF EXISTS sunlog.v_kpi_otif_summary;
CREATE VIEW sunlog.v_kpi_otif_summary AS
SELECT COUNT(*) AS shipment_count,
       SUM(is_delivered) AS delivered_count,
       SUM(git_flag) AS in_transit_count,
       ROUND(AVG(otif_flag) * 100, 2) AS otif_pct,
       ROUND(AVG(on_time_flag) * 100, 2) AS on_time_pct,
       ROUND(AVG(in_full_flag) * 100, 2) AS in_full_pct,
       SUM(late_flag) AS late_shipment_count,
       SUM(partial_flag) AS partial_shipment_count,
       ROUND(AVG(delay_days), 2) AS avg_delay_days
FROM sunlog.analytics_shipment;

DROP VIEW IF EXISTS sunlog.v_kpi_otif_by_carrier;
CREATE VIEW sunlog.v_kpi_otif_by_carrier AS
SELECT carrier_id, carrier_name,
       SUM(is_delivered) AS delivered_count,
       ROUND(AVG(otif_flag) * 100, 2) AS otif_pct,
       ROUND(AVG(on_time_flag) * 100, 2) AS on_time_pct,
       ROUND(AVG(in_full_flag) * 100, 2) AS in_full_pct,
       ROUND(AVG(delay_days), 2) AS avg_delay_days
FROM sunlog.analytics_shipment
WHERE is_delivered = 1
GROUP BY carrier_id, carrier_name;

DROP VIEW IF EXISTS sunlog.v_kpi_otif_by_mode;
CREATE VIEW sunlog.v_kpi_otif_by_mode AS
SELECT shipment_mode,
       SUM(is_delivered) AS delivered_count,
       ROUND(AVG(otif_flag) * 100, 2) AS otif_pct,
       ROUND(AVG(on_time_flag) * 100, 2) AS on_time_pct,
       ROUND(AVG(in_full_flag) * 100, 2) AS in_full_pct
FROM sunlog.analytics_shipment WHERE is_delivered = 1
GROUP BY shipment_mode;

DROP VIEW IF EXISTS sunlog.v_kpi_otif_by_lane;
CREATE VIEW sunlog.v_kpi_otif_by_lane AS
SELECT lane_id,
       SUM(is_delivered) AS delivered_count,
       ROUND(AVG(otif_flag) * 100, 2) AS otif_pct,
       ROUND(AVG(delay_days), 2) AS avg_delay_days
FROM sunlog.analytics_shipment WHERE is_delivered = 1
GROUP BY lane_id;

DROP VIEW IF EXISTS sunlog.v_kpi_otif_by_category;
CREATE VIEW sunlog.v_kpi_otif_by_category AS
SELECT product_category,
       SUM(is_delivered) AS delivered_count,
       ROUND(AVG(otif_flag) * 100, 2) AS otif_pct
FROM sunlog.analytics_shipment WHERE is_delivered = 1
GROUP BY product_category;

DROP VIEW IF EXISTS sunlog.v_kpi_otif_by_region;
CREATE VIEW sunlog.v_kpi_otif_by_region AS
SELECT destination_region,
       SUM(is_delivered) AS delivered_count,
       ROUND(AVG(otif_flag) * 100, 2) AS otif_pct
FROM sunlog.analytics_shipment WHERE is_delivered = 1
GROUP BY destination_region;

DROP VIEW IF EXISTS sunlog.v_kpi_otif_by_month;
CREATE VIEW sunlog.v_kpi_otif_by_month AS
SELECT reporting_month,
       SUM(is_delivered) AS delivered_count,
       ROUND(AVG(otif_flag) * 100, 2) AS otif_pct,
       SUM(late_flag) AS late_count
FROM sunlog.analytics_shipment WHERE is_delivered = 1
GROUP BY reporting_month;

-- --- Goods in transit ------------------------------------------------------
DROP VIEW IF EXISTS sunlog.v_kpi_git_summary;
CREATE VIEW sunlog.v_kpi_git_summary AS
SELECT COUNT(*) AS git_shipment_count,
       ROUND(SUM(shipment_value_usd), 2) AS git_value_usd,
       ROUND(SUM(shipment_weight_kg), 2) AS git_weight_kg,
       ROUND(AVG(git_age_days), 1) AS avg_git_age_days,
       SUM(overdue_git_flag) AS overdue_git_count,
       ROUND(SUM(CASE WHEN overdue_git_flag = 1 THEN shipment_value_usd ELSE 0 END), 2) AS overdue_git_value_usd
FROM sunlog.analytics_shipment WHERE git_flag = 1;

DROP VIEW IF EXISTS sunlog.v_kpi_git_aging;
CREATE VIEW sunlog.v_kpi_git_aging AS
SELECT CASE
         WHEN git_age_days <= 7  THEN '0-7'
         WHEN git_age_days <= 14 THEN '8-14'
         WHEN git_age_days <= 30 THEN '15-30'
         WHEN git_age_days <= 60 THEN '31-60'
         ELSE '60+' END AS aging_bucket,
       COUNT(*) AS git_count,
       ROUND(SUM(shipment_value_usd), 2) AS git_value_usd
FROM sunlog.analytics_shipment WHERE git_flag = 1
GROUP BY aging_bucket;

DROP VIEW IF EXISTS sunlog.v_kpi_git_by_carrier;
CREATE VIEW sunlog.v_kpi_git_by_carrier AS
SELECT carrier_id, carrier_name, COUNT(*) AS git_count,
       ROUND(SUM(shipment_value_usd), 2) AS git_value_usd, ROUND(AVG(git_age_days), 1) AS avg_age_days
FROM sunlog.analytics_shipment WHERE git_flag = 1
GROUP BY carrier_id, carrier_name;

-- --- Transit time ----------------------------------------------------------
DROP VIEW IF EXISTS sunlog.v_kpi_transit_by_mode;
CREATE VIEW sunlog.v_kpi_transit_by_mode AS
SELECT shipment_mode,
       COUNT(*) AS delivered_count,
       ROUND(AVG(planned_transit_days), 1) AS avg_planned_transit_days,
       ROUND(AVG(actual_transit_days), 1) AS avg_actual_transit_days,
       ROUND(AVG(transit_variance_days), 1) AS avg_transit_variance_days,
       ROUND(AVG(within_standard_flag) * 100, 1) AS within_standard_pct
FROM sunlog.analytics_shipment WHERE is_delivered = 1
GROUP BY shipment_mode;

DROP VIEW IF EXISTS sunlog.v_kpi_transit_by_lane;
CREATE VIEW sunlog.v_kpi_transit_by_lane AS
SELECT lane_id, COUNT(*) AS delivered_count,
       ROUND(AVG(actual_transit_days), 1) AS avg_actual_transit_days,
       ROUND(AVG(within_standard_flag) * 100, 1) AS within_standard_pct
FROM sunlog.analytics_shipment WHERE is_delivered = 1
GROUP BY lane_id;

-- --- Freight spend (invoiced, operational layer as billed) -----------------
-- Joined to a valid shipment; includes duplicate/erroneous invoices (=exposure,
-- quantified by the freight audit). Excludes orphan invoices (no shipment).
DROP VIEW IF EXISTS sunlog.v_kpi_freight_summary;
CREATE VIEW sunlog.v_kpi_freight_summary AS
SELECT COUNT(*) AS invoice_count,
       ROUND(SUM(i.invoice_total), 2) AS invoiced_freight_usd,
       ROUND(SUM(i.base_charge), 2) AS base_freight_usd,
       ROUND(SUM(i.fuel_surcharge), 2) AS fuel_surcharge_usd,
       ROUND(SUM(i.accessorial_charge), 2) AS accessorial_usd,
       ROUND(SUM(i.fuel_surcharge) * 100.0 / NULLIF(SUM(i.base_charge), 0), 2) AS fuel_pct_of_base,
       ROUND(SUM(i.accessorial_charge) * 100.0 / NULLIF(SUM(i.invoice_total), 0), 2) AS accessorial_pct_of_total
FROM sunlog.fact_freight_invoice i
WHERE i.shipment_id IN (SELECT shipment_id FROM sunlog.fact_shipment);

DROP VIEW IF EXISTS sunlog.v_kpi_freight_by_carrier;
CREATE VIEW sunlog.v_kpi_freight_by_carrier AS
SELECT s.carrier_id,
       COUNT(*) AS invoice_count,
       ROUND(SUM(i.invoice_total), 2) AS invoiced_freight_usd,
       ROUND(SUM(i.invoice_total) / NULLIF(SUM(s.shipment_weight_kg), 0), 4) AS cost_per_kg,
       ROUND(SUM(i.invoice_total) * 100.0 / NULLIF(SUM(s.shipment_value_usd), 0), 2) AS freight_pct_of_value
FROM sunlog.fact_freight_invoice i
JOIN sunlog.fact_shipment s ON i.shipment_id = s.shipment_id
GROUP BY s.carrier_id;

DROP VIEW IF EXISTS sunlog.v_kpi_freight_by_mode;
CREATE VIEW sunlog.v_kpi_freight_by_mode AS
SELECT s.shipment_mode,
       COUNT(*) AS invoice_count,
       ROUND(SUM(i.invoice_total), 2) AS invoiced_freight_usd,
       ROUND(SUM(i.invoice_total) / NULLIF(SUM(s.shipment_weight_kg), 0), 4) AS cost_per_kg
FROM sunlog.fact_freight_invoice i
JOIN sunlog.fact_shipment s ON i.shipment_id = s.shipment_id
GROUP BY s.shipment_mode;

DROP VIEW IF EXISTS sunlog.v_kpi_freight_by_month;
CREATE VIEW sunlog.v_kpi_freight_by_month AS
SELECT a.reporting_month,
       ROUND(SUM(i.invoice_total), 2) AS invoiced_freight_usd
FROM sunlog.fact_freight_invoice i
JOIN sunlog.analytics_shipment a ON i.shipment_id = a.shipment_id
GROUP BY a.reporting_month;

-- --- Process / compliance KPIs --------------------------------------------
DROP VIEW IF EXISTS sunlog.v_kpi_pod_compliance;
CREATE VIEW sunlog.v_kpi_pod_compliance AS
SELECT SUM(is_delivered) AS delivered_count,
       SUM(CASE WHEN is_delivered = 1 AND has_pod = 1 THEN 1 ELSE 0 END) AS pod_count,
       ROUND(SUM(CASE WHEN is_delivered = 1 AND has_pod = 1 THEN 1 ELSE 0 END) * 100.0
             / NULLIF(SUM(is_delivered), 0), 2) AS pod_compliance_pct,
       SUM(CASE WHEN is_delivered = 1 AND has_pod = 0 THEN 1 ELSE 0 END) AS missing_pod_count
FROM sunlog.analytics_shipment;

DROP VIEW IF EXISTS sunlog.v_kpi_claims;
CREATE VIEW sunlog.v_kpi_claims AS
SELECT COUNT(*) AS claim_count,
       ROUND(SUM(claim_amount), 2) AS claim_cost_usd,
       ROUND(COUNT(*) * 100.0 / (SELECT SUM(is_delivered) FROM sunlog.analytics_shipment), 3) AS claims_rate_pct,
       SUM(CASE WHEN claim_status = 'OPEN' THEN 1 ELSE 0 END) AS open_claims
FROM sunlog.fact_claim;

DROP VIEW IF EXISTS sunlog.v_kpi_capacity;
CREATE VIEW sunlog.v_kpi_capacity AS
SELECT ROUND(AVG(capacity_utilization_pct), 2) AS avg_utilization_pct,
       MAX(capacity_utilization_pct) AS max_utilization_pct,
       SUM(CASE WHEN capacity_utilization_pct > 100 THEN 1 ELSE 0 END) AS over_capacity_count
FROM sunlog.fact_carrier_capacity;
