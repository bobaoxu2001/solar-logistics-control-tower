-- ===========================================================================
-- Phase 3 — Carrier and lane component metrics (PostgreSQL + SQLite).
--
-- Directionality used by src/build_scorecards.py:
--   higher is better: OTIF, transit reliability, invoice accuracy, POD
--   lower is better:  freight cost/kg, claims rate
-- Configurable weights and volume thresholds are applied in Python so the
-- same deterministic min-max normalization is used on both databases.
-- ===========================================================================

DROP VIEW IF EXISTS sunlog.v_carrier_metrics;
CREATE VIEW sunlog.v_carrier_metrics AS
SELECT a.carrier_id, a.carrier_name,
       a.delivered_count, a.shipment_count,
       a.otif_pct, a.transit_reliability_pct, a.pod_compliance_pct,
       a.avg_delay_days, a.avg_actual_transit_days,
       f.invoiced_freight_usd, f.cost_per_kg,
       inv.invoice_count, inv.invoice_accuracy_pct,
       COALESCE(cl.claim_count, 0) AS claim_count,
       COALESCE(cl.claims_rate_pct, 0) AS claims_rate_pct
FROM (
    SELECT carrier_id, carrier_name,
           COUNT(*) AS shipment_count,
           SUM(is_delivered) AS delivered_count,
           ROUND(AVG(otif_flag) * 100, 2) AS otif_pct,
           ROUND(AVG(within_standard_flag) * 100, 2) AS transit_reliability_pct,
           ROUND(SUM(CASE WHEN is_delivered = 1 AND has_pod = 1 THEN 1 ELSE 0 END) * 100.0
                 / NULLIF(SUM(is_delivered), 0), 2) AS pod_compliance_pct,
           ROUND(AVG(delay_days), 2) AS avg_delay_days,
           ROUND(AVG(actual_transit_days), 2) AS avg_actual_transit_days
    FROM sunlog.analytics_shipment
    WHERE carrier_id IS NOT NULL
    GROUP BY carrier_id, carrier_name
) a
LEFT JOIN (
    SELECT s.carrier_id,
           ROUND(SUM(i.invoice_total), 2) AS invoiced_freight_usd,
           ROUND(SUM(i.invoice_total) / NULLIF(SUM(s.shipment_weight_kg), 0), 4) AS cost_per_kg
    FROM sunlog.fact_freight_invoice i
    JOIN sunlog.fact_shipment s ON i.shipment_id = s.shipment_id
    WHERE s.carrier_id IS NOT NULL
    GROUP BY s.carrier_id
) f ON a.carrier_id = f.carrier_id
LEFT JOIN (
    SELECT s.carrier_id, COUNT(*) AS invoice_count,
           ROUND(SUM(CASE WHEN fa.audit_status = 'MATCHED' THEN 1 ELSE 0 END) * 100.0
                 / NULLIF(COUNT(*), 0), 2) AS invoice_accuracy_pct
    FROM sunlog.v_freight_audit fa
    JOIN sunlog.fact_shipment s ON fa.shipment_id = s.shipment_id
    WHERE s.carrier_id IS NOT NULL
    GROUP BY s.carrier_id
) inv ON a.carrier_id = inv.carrier_id
LEFT JOIN (
    SELECT s.carrier_id, COUNT(*) AS claim_count,
           ROUND(COUNT(*) * 100.0 / NULLIF((SELECT COUNT(*)
                                             FROM sunlog.fact_shipment s2
                                            WHERE s2.carrier_id = s.carrier_id), 0), 3) AS claims_rate_pct
    FROM sunlog.fact_claim c
    JOIN sunlog.fact_shipment s ON c.shipment_id = s.shipment_id
    WHERE s.carrier_id IS NOT NULL
    GROUP BY s.carrier_id
) cl ON a.carrier_id = cl.carrier_id;

DROP VIEW IF EXISTS sunlog.v_lane_metrics;
CREATE VIEW sunlog.v_lane_metrics AS
SELECT a.lane_id, l.origin_name, l.destination_name, l.transport_mode, l.lane_region,
       a.shipment_count, a.delivered_count, a.otif_pct, a.avg_delay_days,
       a.avg_actual_transit_days, a.transit_reliability_pct,
       f.invoiced_freight_usd, f.cost_per_kg,
       COALESCE(cl.claim_count, 0) AS claim_count,
       COALESCE(cl.claims_rate_pct, 0) AS claims_rate_pct,
       COALESCE(aud.invoice_exception_count, 0) AS invoice_exception_count,
       COALESCE(aud.invoice_exception_pct, 0) AS invoice_exception_pct,
       COALESCE(acc.accessorial_shipment_count, 0) AS accessorial_shipment_count,
       COALESCE(acc.accessorial_rate_pct, 0) AS accessorial_rate_pct,
       cap.avg_capacity_utilization_pct,
       COALESCE(dq.dq_exception_count, 0) AS dq_exception_count,
       COALESCE(dq.dq_exception_rate_pct, 0) AS dq_exception_rate_pct
FROM (
    SELECT lane_id, COUNT(*) AS shipment_count, SUM(is_delivered) AS delivered_count,
           ROUND(AVG(otif_flag) * 100, 2) AS otif_pct,
           ROUND(AVG(delay_days), 2) AS avg_delay_days,
           ROUND(AVG(actual_transit_days), 2) AS avg_actual_transit_days,
           ROUND(AVG(within_standard_flag) * 100, 2) AS transit_reliability_pct
    FROM sunlog.analytics_shipment
    WHERE lane_id IN (SELECT lane_id FROM sunlog.dim_lane)
    GROUP BY lane_id
) a
LEFT JOIN sunlog.dim_lane l ON a.lane_id = l.lane_id
LEFT JOIN (
    SELECT s.lane_id, ROUND(SUM(i.invoice_total), 2) AS invoiced_freight_usd,
           ROUND(SUM(i.invoice_total) / NULLIF(SUM(s.shipment_weight_kg), 0), 4) AS cost_per_kg
    FROM sunlog.fact_freight_invoice i
    JOIN sunlog.fact_shipment s ON i.shipment_id = s.shipment_id
    GROUP BY s.lane_id
) f ON a.lane_id = f.lane_id
LEFT JOIN (
    SELECT s.lane_id, COUNT(*) AS claim_count,
           ROUND(COUNT(*) * 100.0 / NULLIF((SELECT COUNT(*) FROM sunlog.fact_shipment s2
                                            WHERE s2.lane_id = s.lane_id), 0), 3) AS claims_rate_pct
    FROM sunlog.fact_claim c
    JOIN sunlog.fact_shipment s ON c.shipment_id = s.shipment_id
    GROUP BY s.lane_id
) cl ON a.lane_id = cl.lane_id
LEFT JOIN (
    SELECT s.lane_id,
           SUM(CASE WHEN fa.audit_status <> 'MATCHED' THEN 1 ELSE 0 END) AS invoice_exception_count,
           ROUND(SUM(CASE WHEN fa.audit_status <> 'MATCHED' THEN 1 ELSE 0 END) * 100.0
                 / NULLIF(COUNT(*), 0), 2) AS invoice_exception_pct
    FROM sunlog.v_freight_audit fa
    JOIN sunlog.fact_shipment s ON fa.shipment_id = s.shipment_id
    GROUP BY s.lane_id
) aud ON a.lane_id = aud.lane_id
LEFT JOIN (
    SELECT s.lane_id,
           COUNT(DISTINCT CASE WHEN ac.accessorial_id IS NOT NULL THEN s.shipment_id END)
               AS accessorial_shipment_count,
           ROUND(COUNT(DISTINCT CASE WHEN ac.accessorial_id IS NOT NULL THEN s.shipment_id END) * 100.0
                 / NULLIF(COUNT(DISTINCT s.shipment_id), 0), 2) AS accessorial_rate_pct
    FROM sunlog.fact_shipment s
    LEFT JOIN sunlog.fact_accessorial_charge ac ON ac.shipment_id = s.shipment_id
    GROUP BY s.lane_id
) acc ON a.lane_id = acc.lane_id
LEFT JOIN (
    SELECT lane_id, ROUND(AVG(capacity_utilization_pct), 2) AS avg_capacity_utilization_pct
    FROM sunlog.fact_carrier_capacity GROUP BY lane_id
) cap ON a.lane_id = cap.lane_id
LEFT JOIN (
    SELECT mapped.lane_id, COUNT(*) AS dq_exception_count,
           ROUND(COUNT(*) * 100.0 / NULLIF((SELECT COUNT(*) FROM sunlog.fact_shipment s3
                                            WHERE s3.lane_id = mapped.lane_id), 0), 2)
               AS dq_exception_rate_pct
    FROM (
        SELECT d.detected_exception_id, s.lane_id
        FROM sunlog.dq_detected_exception d
        JOIN sunlog.fact_shipment s ON d.record_type = 'shipment' AND d.record_id = s.shipment_id
        UNION ALL
        SELECT d.detected_exception_id, s.lane_id
        FROM sunlog.dq_detected_exception d
        JOIN sunlog.fact_freight_invoice i ON d.record_type = 'invoice' AND d.record_id = i.invoice_id
        JOIN sunlog.fact_shipment s ON i.shipment_id = s.shipment_id
        UNION ALL
        SELECT d.detected_exception_id, s.lane_id
        FROM sunlog.dq_detected_exception d
        JOIN sunlog.fact_claim c ON d.record_type = 'claim' AND d.record_id = c.claim_id
        JOIN sunlog.fact_shipment s ON c.shipment_id = s.shipment_id
        UNION ALL
        SELECT d.detected_exception_id, s.lane_id
        FROM sunlog.dq_detected_exception d
        JOIN sunlog.fact_accessorial_charge ac ON d.record_type = 'accessorial' AND d.record_id = ac.accessorial_id
        JOIN sunlog.fact_shipment s ON ac.shipment_id = s.shipment_id
        UNION ALL
        SELECT d.detected_exception_id, s.lane_id
        FROM sunlog.dq_detected_exception d
        JOIN sunlog.fact_shipment_milestone m ON d.record_type = 'milestone' AND d.record_id = m.milestone_id
        JOIN sunlog.fact_shipment s ON m.shipment_id = s.shipment_id
        UNION ALL
        SELECT d.detected_exception_id, c.lane_id
        FROM sunlog.dq_detected_exception d
        JOIN sunlog.fact_carrier_capacity c ON d.record_type = 'capacity' AND d.record_id = c.capacity_id
    ) mapped
    WHERE mapped.lane_id IS NOT NULL
    GROUP BY mapped.lane_id
) dq ON a.lane_id = dq.lane_id;
