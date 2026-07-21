-- ===========================================================================
-- Phase 3 — Data-quality rule engine (portable: PostgreSQL + SQLite).
-- Loader (src/load_phase3.py) strips the `sunlog.` qualifier for SQLite and
-- seeds dq_rule + meta_* from config/project_config.yaml.
--
-- Detection runs against the OPERATIONAL layer (the exception-injected data in
-- the canonical fact tables). The clean baseline lives in data/processed/clean/
-- and is used only to prove correct KPI/financial logic (see tests).
-- ===========================================================================

-- --- Rule registry ---------------------------------------------------------
DROP VIEW IF EXISTS sunlog.v_dq_detected;
CREATE TABLE IF NOT EXISTS sunlog.dq_rule (
    rule_id                     TEXT PRIMARY KEY,
    rule_name                   TEXT NOT NULL,
    rule_category               TEXT NOT NULL,   -- COMPLETENESS / UNIQUENESS / VALIDITY /
                                                 -- REFERENTIAL / TIMELINESS / CONSISTENCY /
                                                 -- FINANCIAL_CONTROL / PROCESS_COMPLIANCE
    target_table                TEXT,
    target_column               TEXT,
    severity                    TEXT NOT NULL,   -- CRITICAL / HIGH / MEDIUM / LOW
    business_description        TEXT,
    technical_logic             TEXT,
    business_owner              TEXT,
    exception_type              TEXT,            -- links to manifest type (NULL for pure controls)
    expected_resolution_sla_hours INTEGER,
    active_flag                 INTEGER NOT NULL DEFAULT 1
);

-- --- Config-driven metadata (seeded by src/load_phase3.py) -----------------
CREATE TABLE IF NOT EXISTS sunlog.meta_dq_severity_weight (
    severity    TEXT PRIMARY KEY,
    weight      NUMERIC(6,2) NOT NULL
);

CREATE TABLE IF NOT EXISTS sunlog.meta_accessorial_band (
    charge_type TEXT PRIMARY KEY,
    max_allowed NUMERIC(12,2) NOT NULL
);

CREATE TABLE IF NOT EXISTS sunlog.meta_run_context (
    context_key TEXT PRIMARY KEY,
    context_value TEXT
);

-- ===========================================================================
-- Detection view: one row per detected exception in the operational layer.
-- Severity / owner / category / exception_type come from the registry, so the
-- business classification stays config-driven. reference_date drives aging.
-- ===========================================================================
CREATE VIEW sunlog.v_dq_detected AS
SELECT d.rule_id, r.rule_name, r.rule_category, r.severity, r.business_owner,
       r.exception_type, r.expected_resolution_sla_hours,
       d.record_id, d.record_type, d.reference_date, d.exception_description,
       'operational' AS source_layer
FROM (
    -- DQ01 missing carrier id ------------------------------------------------
    SELECT 'DQ01' AS rule_id, shipment_id AS record_id, 'shipment' AS record_type,
           actual_ship_date AS reference_date,
           'Shipment has no carrier assigned' AS exception_description
    FROM sunlog.fact_shipment WHERE carrier_id IS NULL
    UNION ALL
    -- DQ02 invalid lane id ---------------------------------------------------
    SELECT 'DQ02', shipment_id, 'shipment', actual_ship_date,
           'Shipment references a lane id not present in dim_lane'
    FROM sunlog.fact_shipment
    WHERE lane_id IS NOT NULL AND lane_id NOT IN (SELECT lane_id FROM sunlog.dim_lane)
    UNION ALL
    -- DQ03 delivery before ship ---------------------------------------------
    SELECT 'DQ03', shipment_id, 'shipment', actual_ship_date,
           'Actual delivery date precedes actual ship date'
    FROM sunlog.fact_shipment
    WHERE actual_delivery_date IS NOT NULL AND actual_delivery_date < actual_ship_date
    UNION ALL
    -- DQ04 over delivery -----------------------------------------------------
    SELECT 'DQ04', shipment_id, 'shipment', actual_delivery_date,
           'Delivered quantity exceeds planned/ordered quantity'
    FROM sunlog.fact_shipment
    WHERE delivered_quantity IS NOT NULL AND delivered_quantity > planned_quantity
    UNION ALL
    -- DQ05 partial delivery --------------------------------------------------
    SELECT 'DQ05', shipment_id, 'shipment', actual_delivery_date,
           'Delivered quantity is short of planned/ordered quantity'
    FROM sunlog.fact_shipment
    WHERE delivered_quantity IS NOT NULL AND delivered_quantity < planned_quantity
    UNION ALL
    -- DQ06 missing POD -------------------------------------------------------
    SELECT 'DQ06', shipment_id, 'shipment', actual_delivery_date,
           'Delivered shipment has no proof-of-delivery record'
    FROM sunlog.fact_shipment s
    WHERE s.shipment_status = 'DELIVERED'
      AND s.shipment_id NOT IN (SELECT shipment_id FROM sunlog.fact_proof_of_delivery)
    UNION ALL
    -- DQ07 shipment without invoice -----------------------------------------
    SELECT 'DQ07', shipment_id, 'shipment', actual_delivery_date,
           'Delivered shipment has no freight invoice'
    FROM sunlog.fact_shipment s
    WHERE s.shipment_status = 'DELIVERED'
      AND s.shipment_id NOT IN (SELECT shipment_id FROM sunlog.fact_freight_invoice WHERE shipment_id IS NOT NULL)
    UNION ALL
    -- DQ08 missing customs documentation ------------------------------------
    SELECT 'DQ08', milestone_id, 'milestone', planned_timestamp,
           'Customs milestone missing / documentation not completed'
    FROM sunlog.fact_shipment_milestone
    WHERE milestone_status = 'MISSED' AND exception_reason = 'MISSING_CUSTOMS_DOCUMENTATION'
    UNION ALL
    -- DQ09 missing HTS code --------------------------------------------------
    SELECT 'DQ09', product_id, 'product', NULL,
           'Product master row has no HTS code'
    FROM sunlog.dim_product WHERE hts_code IS NULL
    UNION ALL
    -- DQ10 damaged-shipment claim requiring action --------------------------
    SELECT 'DQ10', claim_id, 'claim', created_date,
           'Open damage claim requiring review'
    FROM sunlog.fact_claim WHERE claim_type = 'DAMAGE' AND claim_status = 'OPEN'
    UNION ALL
    -- DQ11 invoice carrier mismatch -----------------------------------------
    SELECT 'DQ11', i.invoice_id, 'invoice', i.invoice_date,
           'Invoice carrier differs from shipment carrier'
    FROM sunlog.fact_freight_invoice i
    JOIN sunlog.fact_shipment s ON i.shipment_id = s.shipment_id
    WHERE s.carrier_id IS NOT NULL AND i.carrier_id <> s.carrier_id
    UNION ALL
    -- DQ12 incorrect fuel surcharge -----------------------------------------
    SELECT 'DQ12', i.invoice_id, 'invoice', i.invoice_date,
           'Fuel surcharge does not match contractual percentage of base charge'
    FROM sunlog.fact_freight_invoice i
    JOIN sunlog.fact_shipment s ON i.shipment_id = s.shipment_id
    JOIN sunlog.dim_rate_card rc ON rc.carrier_id = s.carrier_id AND rc.lane_id = s.lane_id
    CROSS JOIN (SELECT
        (SELECT threshold_value FROM sunlog.meta_audit_threshold WHERE threshold_name='absolute_variance_usd') AS abs_t,
        (SELECT threshold_value FROM sunlog.meta_audit_threshold WHERE threshold_name='variance_pct')/100.0 AS pct_t) t
    -- Audit materiality is OR: flag when the variance breaches EITHER the
    -- absolute ($) OR the percentage threshold (a large % error still matters
    -- even if small in dollars).
    WHERE ABS(i.fuel_surcharge - i.base_charge * rc.fuel_percentage) > t.abs_t
       OR ABS(i.fuel_surcharge - i.base_charge * rc.fuel_percentage) > t.pct_t * (i.base_charge * rc.fuel_percentage)
    UNION ALL
    -- DQ13 incorrect currency ------------------------------------------------
    -- Compared to the invoice carrier's default (contractual) currency, so it
    -- is evaluable even when the shipment carrier/lane is itself broken.
    SELECT 'DQ13', i.invoice_id, 'invoice', i.invoice_date,
           'Invoice currency differs from the contractual (carrier default) currency'
    FROM sunlog.fact_freight_invoice i
    JOIN sunlog.dim_carrier c ON i.carrier_id = c.carrier_id
    WHERE i.currency <> c.default_currency
    UNION ALL
    -- DQ14 expired rate card -------------------------------------------------
    SELECT 'DQ14', i.invoice_id, 'invoice', i.invoice_date,
           'Shipment shipped after the applicable rate card expiry'
    FROM sunlog.fact_freight_invoice i
    JOIN sunlog.fact_shipment s ON i.shipment_id = s.shipment_id
    WHERE EXISTS (SELECT 1 FROM sunlog.dim_rate_card rc
                  WHERE rc.carrier_id = s.carrier_id AND rc.lane_id = s.lane_id)
      AND NOT EXISTS (SELECT 1 FROM sunlog.dim_rate_card rc
                  WHERE rc.carrier_id = s.carrier_id AND rc.lane_id = s.lane_id
                    AND s.actual_ship_date BETWEEN rc.effective_start_date AND rc.effective_end_date)
    UNION ALL
    -- DQ15 duplicate invoice number (flag the non-canonical copy) ------------
    SELECT 'DQ15', f.invoice_id, 'invoice', f.invoice_date,
           'Invoice number appears on more than one invoice record'
    FROM sunlog.fact_freight_invoice f
    WHERE f.invoice_number IN (SELECT invoice_number FROM sunlog.fact_freight_invoice
                               GROUP BY invoice_number HAVING COUNT(*) > 1)
      AND f.invoice_id > (SELECT MIN(f2.invoice_id) FROM sunlog.fact_freight_invoice f2
                          WHERE f2.invoice_number = f.invoice_number)
    UNION ALL
    -- DQ16 duplicate payment risk (>1 PAID invoice per shipment) ------------
    SELECT 'DQ16', f.invoice_id, 'invoice', f.invoice_date,
           'More than one PAID invoice exists for the same shipment'
    FROM sunlog.fact_freight_invoice f
    WHERE f.payment_status = 'PAID' AND f.shipment_id IS NOT NULL
      AND f.shipment_id IN (SELECT shipment_id FROM sunlog.fact_freight_invoice
                            WHERE payment_status='PAID' AND shipment_id IS NOT NULL
                            GROUP BY shipment_id HAVING COUNT(*) > 1)
      AND f.invoice_id > (SELECT MIN(f2.invoice_id) FROM sunlog.fact_freight_invoice f2
                          WHERE f2.shipment_id = f.shipment_id AND f2.payment_status='PAID')
    UNION ALL
    -- DQ17 invoice without valid shipment -----------------------------------
    SELECT 'DQ17', invoice_id, 'invoice', invoice_date,
           'Invoice references a shipment id not present in fact_shipment'
    FROM sunlog.fact_freight_invoice
    WHERE shipment_id IS NOT NULL AND shipment_id NOT IN (SELECT shipment_id FROM sunlog.fact_shipment)
    UNION ALL
    -- DQ18 unauthorized accessorial -----------------------------------------
    SELECT 'DQ18', accessorial_id, 'accessorial', NULL,
           'Accessorial charge is not contractually allowed'
    FROM sunlog.fact_accessorial_charge WHERE contractually_allowed_flag = 0
    UNION ALL
    -- DQ19 excessive accessorial (demurrage above contractual band) ---------
    SELECT 'DQ19', a.accessorial_id, 'accessorial', NULL,
           'Accessorial charge exceeds the contractual band for its type'
    FROM sunlog.fact_accessorial_charge a
    JOIN sunlog.meta_accessorial_band b ON a.charge_type = b.charge_type
    WHERE a.charge_amount > b.max_allowed
    UNION ALL
    -- DQ20 paid invoice without approval (control) --------------------------
    SELECT 'DQ20', invoice_id, 'invoice', invoice_date,
           'Invoice is PAID but not fully approved'
    FROM sunlog.fact_freight_invoice
    WHERE payment_status = 'PAID' AND approval_status <> 'APPROVED'
    UNION ALL
    -- DQ21 invalid milestone sequence (control) -----------------------------
    SELECT 'DQ21', m.milestone_id, 'milestone', m.planned_timestamp,
           'Milestone actual timestamp is earlier than a prior milestone'
    FROM sunlog.fact_shipment_milestone m
    WHERE m.milestone_status = 'COMPLETED' AND m.actual_timestamp IS NOT NULL
      AND m.actual_timestamp < (SELECT MAX(m2.actual_timestamp)
            FROM sunlog.fact_shipment_milestone m2
            WHERE m2.shipment_id = m.shipment_id AND m2.milestone_sequence < m.milestone_sequence
              AND m2.milestone_status = 'COMPLETED')
    UNION ALL
    -- DQ22 capacity utilization above 100% (control) ------------------------
    SELECT 'DQ22', capacity_id, 'capacity', period_start,
           'Carrier/lane capacity utilization exceeds 100%'
    FROM sunlog.fact_carrier_capacity WHERE capacity_utilization_pct > 100.0
    UNION ALL
    -- DQ23 broken PO-shipment relationship (control) ------------------------
    SELECT 'DQ23', shipment_id, 'shipment', actual_ship_date,
           'Shipment references a purchase order not present in fact_purchase_order'
    FROM sunlog.fact_shipment
    WHERE po_id IS NOT NULL AND po_id NOT IN (SELECT po_id FROM sunlog.fact_purchase_order)
    UNION ALL
    -- DQ24 invoice component reconciliation (control) -----------------------
    SELECT 'DQ24', invoice_id, 'invoice', invoice_date,
           'Invoice total does not equal the sum of its charge components'
    FROM sunlog.fact_freight_invoice
    WHERE ABS(invoice_total - (base_charge + fuel_surcharge + accessorial_charge + tax_amount)) > 0.01
    UNION ALL
    -- DQ25 missing required delivery milestone (control) --------------------
    SELECT 'DQ25', s.shipment_id, 'shipment', s.actual_delivery_date,
           'Delivered shipment has no completed CUSTOMER_DELIVERY milestone'
    FROM sunlog.fact_shipment s
    WHERE s.shipment_status = 'DELIVERED'
      AND NOT EXISTS (SELECT 1 FROM sunlog.fact_shipment_milestone m
                      WHERE m.shipment_id = s.shipment_id
                        AND m.milestone_type = 'CUSTOMER_DELIVERY' AND m.milestone_status = 'COMPLETED')
) d
JOIN sunlog.dq_rule r ON d.rule_id = r.rule_id
WHERE r.active_flag = 1;
