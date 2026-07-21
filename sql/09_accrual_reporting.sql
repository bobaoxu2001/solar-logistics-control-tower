-- ===========================================================================
-- Phase 3 — Freight accrual & variance reporting (portable).
-- Built on fact_accrual (per shipment, per accounting period) produced in
-- Phase 2. "Plan" here is the expected-freight baseline, NOT an approved
-- corporate budget — labeled accordingly.
-- ===========================================================================

DROP VIEW IF EXISTS sunlog.v_accrual_summary;
CREATE VIEW sunlog.v_accrual_summary AS
SELECT COUNT(*) AS accrual_count,
       ROUND(SUM(expected_freight_cost), 2) AS total_expected_freight,
       ROUND(SUM(actual_invoice_cost), 2) AS total_actual_invoice,
       ROUND(SUM(CASE WHEN accrual_status <> 'RELEASED' THEN expected_freight_cost ELSE 0 END), 2) AS open_accrual_balance,
       SUM(CASE WHEN invoice_received_flag = 0 THEN 1 ELSE 0 END) AS uninvoiced_shipment_count,
       ROUND(SUM(accrual_variance), 2) AS total_accrual_variance,
       SUM(CASE WHEN accrual_status = 'RELEASED' THEN 1 ELSE 0 END) AS released_count,
       SUM(CASE WHEN accrual_status = 'ACCRUED' THEN 1 ELSE 0 END) AS open_count
FROM sunlog.fact_accrual;

DROP VIEW IF EXISTS sunlog.v_accrual_by_status;
CREATE VIEW sunlog.v_accrual_by_status AS
SELECT accrual_status, invoice_received_flag, COUNT(*) AS shipment_count,
       ROUND(SUM(expected_freight_cost), 2) AS expected_freight,
       ROUND(SUM(actual_invoice_cost), 2) AS actual_invoice
FROM sunlog.fact_accrual GROUP BY accrual_status, invoice_received_flag;

DROP VIEW IF EXISTS sunlog.v_accrual_by_period;
CREATE VIEW sunlog.v_accrual_by_period AS
SELECT accounting_period,
       COUNT(*) AS shipment_count,
       ROUND(SUM(expected_freight_cost), 2) AS expected_freight,
       ROUND(SUM(CASE WHEN invoice_received_flag = 1 THEN actual_invoice_cost ELSE 0 END), 2) AS actual_invoice,
       ROUND(SUM(CASE WHEN accrual_status <> 'RELEASED' THEN expected_freight_cost ELSE 0 END), 2) AS open_accrual,
       SUM(CASE WHEN invoice_received_flag = 0 THEN 1 ELSE 0 END) AS uninvoiced_count
FROM sunlog.fact_accrual GROUP BY accounting_period;

DROP VIEW IF EXISTS sunlog.v_accrual_by_carrier;
CREATE VIEW sunlog.v_accrual_by_carrier AS
SELECT s.carrier_id,
       COUNT(*) AS shipment_count,
       ROUND(SUM(ac.expected_freight_cost), 2) AS expected_freight,
       ROUND(SUM(CASE WHEN ac.accrual_status <> 'RELEASED' THEN ac.expected_freight_cost ELSE 0 END), 2) AS open_accrual
FROM sunlog.fact_accrual ac
JOIN sunlog.fact_shipment s ON ac.shipment_id = s.shipment_id
GROUP BY s.carrier_id;

-- Expected-freight baseline (simulated logistics plan) vs actual invoiced,
-- by accounting period. Clearly NOT an approved corporate budget.
DROP VIEW IF EXISTS sunlog.v_plan_vs_actual;
CREATE VIEW sunlog.v_plan_vs_actual AS
SELECT accounting_period AS period,
       ROUND(SUM(expected_freight_cost), 2) AS simulated_plan_expected_freight,
       ROUND(SUM(CASE WHEN invoice_received_flag = 1 THEN actual_invoice_cost ELSE 0 END), 2) AS actual_invoiced_freight,
       ROUND(SUM(CASE WHEN invoice_received_flag = 1 THEN actual_invoice_cost ELSE 0 END)
             - SUM(expected_freight_cost), 2) AS variance_vs_plan
FROM sunlog.fact_accrual GROUP BY accounting_period;
