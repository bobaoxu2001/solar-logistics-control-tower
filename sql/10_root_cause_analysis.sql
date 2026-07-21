-- ===========================================================================
-- Phase 3 — Reproducible root-cause evidence views (PostgreSQL + SQLite).
-- These views expose observations and drill-down evidence. The accompanying
-- Python builder labels causal language conservatively as "possible cause".
-- ===========================================================================

DROP VIEW IF EXISTS sunlog.v_rca_monthly_otif;
CREATE VIEW sunlog.v_rca_monthly_otif AS
SELECT reporting_month,
       SUM(is_delivered) AS delivered_count,
       SUM(late_flag) AS late_count,
       ROUND(AVG(otif_flag) * 100, 2) AS otif_pct,
       ROUND(AVG(on_time_flag) * 100, 2) AS on_time_pct,
       ROUND(AVG(CASE WHEN late_flag = 1 THEN delay_days END), 2) AS avg_late_days,
       ROUND(SUM(CASE WHEN late_flag = 1 THEN shipment_value_usd ELSE 0 END), 2) AS late_shipment_value_usd
FROM sunlog.analytics_shipment
WHERE is_delivered = 1
GROUP BY reporting_month;

DROP VIEW IF EXISTS sunlog.v_rca_delay_drilldown;
CREATE VIEW sunlog.v_rca_delay_drilldown AS
SELECT a.reporting_month, a.carrier_id, a.carrier_name, a.lane_id,
       l.origin_name, l.destination_name, l.transport_mode,
       COUNT(*) AS delivered_count,
       SUM(a.late_flag) AS late_count,
       ROUND(AVG(a.otif_flag) * 100, 2) AS otif_pct,
       ROUND(AVG(CASE WHEN a.late_flag = 1 THEN a.delay_days END), 2) AS avg_late_days,
       ROUND(SUM(CASE WHEN a.late_flag = 1 THEN a.shipment_value_usd ELSE 0 END), 2) AS late_shipment_value_usd,
       COUNT(c.claim_id) AS claim_count,
       ROUND(COALESCE(SUM(c.claim_amount), 0), 2) AS claim_cost_usd
FROM sunlog.analytics_shipment a
LEFT JOIN sunlog.dim_lane l ON a.lane_id = l.lane_id
LEFT JOIN sunlog.fact_claim c ON a.shipment_id = c.shipment_id
WHERE a.is_delivered = 1
GROUP BY a.reporting_month, a.carrier_id, a.carrier_name, a.lane_id,
         l.origin_name, l.destination_name, l.transport_mode;

DROP VIEW IF EXISTS sunlog.v_rca_freight_pattern;
CREATE VIEW sunlog.v_rca_freight_pattern AS
SELECT fa.invoice_carrier AS carrier_id, c.carrier_name, fa.audit_status,
       COUNT(*) AS affected_invoice_count,
       ROUND(SUM(fa.invoiced_total), 2) AS invoiced_amount_usd,
       ROUND(SUM(fa.overcharge_amount), 2) AS overcharge_exposure_usd,
       ROUND(SUM(CASE WHEN fa.audit_status = 'DUPLICATE_INVOICE'
                      THEN fa.invoiced_total ELSE 0 END), 2) AS duplicate_exposure_usd,
       COUNT(DISTINCT fa.shipment_id) AS affected_shipment_count,
       ROUND(SUM(COALESCE(s.shipment_value_usd, 0)), 2) AS affected_shipment_value_usd
FROM sunlog.v_freight_audit fa
LEFT JOIN sunlog.dim_carrier c ON fa.invoice_carrier = c.carrier_id
LEFT JOIN sunlog.fact_shipment s ON fa.shipment_id = s.shipment_id
WHERE fa.audit_status <> 'MATCHED'
GROUP BY fa.invoice_carrier, c.carrier_name, fa.audit_status;

DROP VIEW IF EXISTS sunlog.v_rca_dq_pattern;
CREATE VIEW sunlog.v_rca_dq_pattern AS
SELECT d.rule_id, r.rule_name, d.exception_type, d.severity, d.business_owner,
       COUNT(*) AS detected_count,
       ROUND(COUNT(*) * w.weight, 2) AS weighted_exception_points,
       p.manifest_count, p.true_positive_count, p.false_positive_count,
       p.false_negative_count, p.precision_pct, p.recall_pct, p.notes
FROM sunlog.dq_detected_exception d
JOIN sunlog.dq_rule r ON d.rule_id = r.rule_id
JOIN sunlog.meta_dq_severity_weight w ON d.severity = w.severity
LEFT JOIN sunlog.rpt_dq_detection_performance p ON d.exception_type = p.exception_type
GROUP BY d.rule_id, r.rule_name, d.exception_type, d.severity, d.business_owner,
         w.weight, p.manifest_count, p.true_positive_count, p.false_positive_count,
         p.false_negative_count, p.precision_pct, p.recall_pct, p.notes;
