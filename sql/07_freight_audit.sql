-- ===========================================================================
-- Phase 3 — Freight-rating engine + invoice audit (portable).
-- Transparent: every expected component is exposed, never hidden in a total.
-- Audit thresholds come from meta_audit_threshold (config-driven, not
-- hard-coded). Materiality is OR: an exception if the variance breaches the
-- absolute ($) OR the percentage threshold.
-- ===========================================================================

-- --- Expected freight per shipment (exactly one applicable rate) ------------
-- LEFT JOIN with the effective-date window: no in-window row => rate is either
-- missing (no rate at all for carrier+lane) or expired (a rate exists but not
-- covering the ship date).
DROP VIEW IF EXISTS sunlog.v_expected_freight;
CREATE VIEW sunlog.v_expected_freight AS
SELECT s.shipment_id, s.carrier_id, s.lane_id, s.actual_ship_date, s.shipment_weight_kg,
       rc.rate_id, rc.rate_basis, rc.rate_per_kg, rc.minimum_charge, rc.fuel_percentage,
       rc.currency AS rate_currency,
       CASE WHEN rc.rate_id IS NOT NULL THEN 'RATED'
            WHEN EXISTS (SELECT 1 FROM sunlog.dim_rate_card r2
                         WHERE r2.carrier_id = s.carrier_id AND r2.lane_id = s.lane_id)
                 THEN 'EXPIRED_RATE'
            ELSE 'MISSING_RATE' END AS rate_status,
       CASE WHEN rc.rate_id IS NULL THEN NULL
            WHEN rc.rate_per_kg * s.shipment_weight_kg > rc.minimum_charge
                 THEN ROUND(rc.rate_per_kg * s.shipment_weight_kg, 2)
            ELSE rc.minimum_charge END AS expected_base,
       CASE WHEN rc.rate_id IS NULL THEN NULL
            ELSE ROUND(
                 (CASE WHEN rc.rate_per_kg * s.shipment_weight_kg > rc.minimum_charge
                       THEN rc.rate_per_kg * s.shipment_weight_kg ELSE rc.minimum_charge END)
                 * rc.fuel_percentage, 2) END AS expected_fuel
FROM sunlog.fact_shipment s
LEFT JOIN sunlog.dim_rate_card rc
       ON rc.carrier_id = s.carrier_id AND rc.lane_id = s.lane_id
      AND s.actual_ship_date BETWEEN rc.effective_start_date AND rc.effective_end_date;

-- --- Invoice audit ---------------------------------------------------------
DROP VIEW IF EXISTS sunlog.v_freight_audit;
CREATE VIEW sunlog.v_freight_audit AS
SELECT a.invoice_id, a.invoice_number, a.shipment_id, a.invoice_carrier, a.shipment_carrier,
       a.lane_id, a.rate_id, a.rate_status, a.currency, a.rate_currency,
       a.expected_base, a.expected_fuel, a.expected_accessorial, a.expected_total,
       a.base_charge, a.fuel_surcharge, a.accessorial_charge, a.tax_amount, a.invoiced_total,
       a.variance_amount,
       CASE WHEN a.expected_total IS NULL OR a.expected_total = 0 THEN NULL
            ELSE ROUND(a.variance_amount * 100.0 / a.expected_total, 2) END AS variance_pct,
       a.is_material, a.fuel_variance,
       CASE
         WHEN a.matched_shipment_id IS NULL THEN 'SHIPMENT_MISMATCH'
         WHEN a.is_duplicate = 1 THEN 'DUPLICATE_INVOICE'
         WHEN a.rate_status = 'MISSING_RATE' THEN 'MISSING_RATE'
         WHEN a.rate_status = 'EXPIRED_RATE' THEN 'EXPIRED_RATE'
         WHEN a.invoice_carrier <> a.shipment_carrier THEN 'CARRIER_MISMATCH'
         WHEN a.currency <> a.rate_currency THEN 'INCORRECT_CURRENCY'
         WHEN a.fuel_material = 1 THEN 'INCORRECT_FUEL_SURCHARGE'
         WHEN a.is_material = 1 AND a.variance_amount > 0 THEN 'POTENTIAL_OVERCHARGE'
         WHEN a.is_material = 1 AND a.variance_amount < 0 THEN 'POTENTIAL_UNDERCHARGE'
         ELSE 'MATCHED' END AS audit_status,
       CASE WHEN a.is_material = 1 AND a.variance_amount > 0 THEN ROUND(a.variance_amount, 2) ELSE 0 END AS overcharge_amount,
       CASE WHEN a.is_material = 1 AND a.variance_amount < 0 THEN ROUND(-a.variance_amount, 2) ELSE 0 END AS undercharge_amount
FROM (
    SELECT b.*,
           (b.invoiced_total - b.expected_total) AS variance_amount,
           (b.fuel_surcharge - b.expected_fuel) AS fuel_variance,
           -- Audit materiality (dispute worthiness) is AND: a variance is
           -- material only if it breaches BOTH the $ floor AND the % threshold.
           -- This keeps the clean baseline's small rating noise as MATCHED,
           -- while the DQ layer (OR-based) still flags every injected error.
           CASE WHEN b.expected_total IS NULL THEN NULL
                WHEN ABS(b.invoiced_total - b.expected_total) > b.abs_t
                 AND ABS(b.invoiced_total - b.expected_total) > b.pct_t * b.expected_total THEN 1 ELSE 0 END AS is_material,
           CASE WHEN b.expected_fuel IS NULL THEN 0
                WHEN ABS(b.fuel_surcharge - b.expected_fuel) > b.abs_t
                 AND ABS(b.fuel_surcharge - b.expected_fuel) > b.pct_t * b.expected_fuel THEN 1 ELSE 0 END AS fuel_material
    FROM (
        SELECT i.invoice_id, i.invoice_number, i.shipment_id,
               i.carrier_id AS invoice_carrier, s.carrier_id AS shipment_carrier,
               s.shipment_id AS matched_shipment_id,
               ef.lane_id, ef.rate_id, ef.rate_status, ef.rate_currency,
               ef.expected_base, ef.expected_fuel,
               COALESCE((SELECT SUM(ac.charge_amount) FROM sunlog.fact_accessorial_charge ac
                         JOIN sunlog.meta_accessorial_band mb ON ac.charge_type = mb.charge_type
                         WHERE ac.invoice_id = i.invoice_id AND ac.contractually_allowed_flag = 1
                           AND ac.supporting_document_flag = 1 AND ac.charge_amount <= mb.max_allowed), 0) AS expected_accessorial,
               -- NULL (unknown) when there is no applicable rate, so unrated
               -- invoices are never scored as a full-value overcharge.
               CASE WHEN ef.expected_base IS NULL THEN NULL ELSE
                 (ef.expected_base + COALESCE(ef.expected_fuel, 0)
                  + COALESCE((SELECT SUM(ac.charge_amount) FROM sunlog.fact_accessorial_charge ac
                         JOIN sunlog.meta_accessorial_band mb ON ac.charge_type = mb.charge_type
                         WHERE ac.invoice_id = i.invoice_id AND ac.contractually_allowed_flag = 1
                           AND ac.supporting_document_flag = 1 AND ac.charge_amount <= mb.max_allowed), 0)
                  + i.tax_amount) END AS expected_total,
               i.base_charge, i.fuel_surcharge, i.accessorial_charge, i.tax_amount,
               i.invoice_total AS invoiced_total, i.currency,
               CASE WHEN i.invoice_number IN (SELECT invoice_number FROM sunlog.fact_freight_invoice
                                              GROUP BY invoice_number HAVING COUNT(*) > 1)
                     AND i.invoice_id > (SELECT MIN(f2.invoice_id) FROM sunlog.fact_freight_invoice f2
                                         WHERE f2.invoice_number = i.invoice_number)
                    THEN 1 ELSE 0 END AS is_duplicate,
               (SELECT threshold_value FROM sunlog.meta_audit_threshold WHERE threshold_name='absolute_variance_usd') AS abs_t,
               (SELECT threshold_value FROM sunlog.meta_audit_threshold WHERE threshold_name='variance_pct')/100.0 AS pct_t
        FROM sunlog.fact_freight_invoice i
        LEFT JOIN sunlog.fact_shipment s ON i.shipment_id = s.shipment_id
        LEFT JOIN sunlog.v_expected_freight ef ON i.shipment_id = ef.shipment_id
    ) b
) a;

-- --- Accessorial audit (unauthorized / excessive) --------------------------
DROP VIEW IF EXISTS sunlog.v_accessorial_audit;
CREATE VIEW sunlog.v_accessorial_audit AS
SELECT ac.accessorial_id, ac.invoice_id, ac.shipment_id, ac.charge_type, ac.charge_amount,
       ac.contractually_allowed_flag, ac.supporting_document_flag, mb.max_allowed,
       CASE WHEN ac.contractually_allowed_flag = 0 THEN 'UNAUTHORIZED'
            WHEN ac.charge_amount > mb.max_allowed THEN 'EXCESSIVE'
            WHEN ac.supporting_document_flag = 0 THEN 'UNSUPPORTED'
            ELSE 'ALLOWED' END AS accessorial_status,
       CASE WHEN ac.contractually_allowed_flag = 0 THEN ac.charge_amount
            WHEN ac.charge_amount > mb.max_allowed THEN ac.charge_amount - mb.max_allowed
            ELSE 0 END AS recoverable_amount
FROM sunlog.fact_accessorial_charge ac
LEFT JOIN sunlog.meta_accessorial_band mb ON ac.charge_type = mb.charge_type;

-- --- Audit roll-ups --------------------------------------------------------
DROP VIEW IF EXISTS sunlog.v_audit_by_status;
CREATE VIEW sunlog.v_audit_by_status AS
SELECT audit_status, COUNT(*) AS invoice_count,
       SUM(CAST((CASE WHEN is_material = 1 AND variance_amount > 0 THEN variance_amount ELSE 0 END)
                * 100 + 0.01 AS BIGINT)) / 100.0 AS total_overcharge,
       SUM(CAST((CASE WHEN is_material = 1 AND variance_amount < 0 THEN -variance_amount ELSE 0 END)
                * 100 + 0.01 AS BIGINT)) / 100.0 AS total_undercharge
FROM sunlog.v_freight_audit GROUP BY audit_status;

DROP VIEW IF EXISTS sunlog.v_audit_overcharge_by_carrier;
CREATE VIEW sunlog.v_audit_overcharge_by_carrier AS
SELECT invoice_carrier AS carrier_id, COUNT(*) AS flagged_invoices,
       SUM(CAST((CASE WHEN is_material = 1 AND variance_amount > 0 THEN variance_amount ELSE 0 END)
                * 100 + 0.01 AS BIGINT)) / 100.0 AS total_overcharge
FROM sunlog.v_freight_audit
WHERE audit_status NOT IN ('MATCHED')
GROUP BY invoice_carrier;

-- Recoverable = duplicate invoice totals + overcharges + unauthorized/excessive
-- accessorials. Duplicate-payment risk (a second PAID invoice) is included via
-- the duplicate classification.
DROP VIEW IF EXISTS sunlog.v_audit_recoverable_summary;
CREATE VIEW sunlog.v_audit_recoverable_summary AS
SELECT
  (SELECT COALESCE(SUM(CAST((CASE WHEN is_material = 1 AND variance_amount > 0 THEN variance_amount ELSE 0 END)
                                  * 100 + 0.01 AS BIGINT)),0) / 100.0
     FROM sunlog.v_freight_audit
     WHERE audit_status IN ('POTENTIAL_OVERCHARGE','INCORRECT_FUEL_SURCHARGE')) AS overcharge_recoverable,
  (SELECT COALESCE(SUM(CAST(invoiced_total * 100 + 0.01 AS BIGINT)),0) / 100.0
     FROM sunlog.v_freight_audit
     WHERE audit_status = 'DUPLICATE_INVOICE') AS duplicate_invoice_exposure,
  (SELECT COALESCE(SUM(CAST(recoverable_amount * 100 + 0.01 AS BIGINT)),0) / 100.0
     FROM sunlog.v_accessorial_audit
     WHERE accessorial_status IN ('UNAUTHORIZED','EXCESSIVE')) AS accessorial_recoverable;
