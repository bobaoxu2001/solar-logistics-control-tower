-- ===========================================================================
-- Phase 3 — Three-way match: purchase order <-> shipment <-> freight invoice.
-- One row per invoice. Statuses feed a Finance-ready payment decision.
-- Reuses v_freight_audit for the rate/variance/duplicate signals.
-- ===========================================================================

DROP VIEW IF EXISTS sunlog.v_three_way_match;
CREATE VIEW sunlog.v_three_way_match AS
SELECT m.invoice_id, m.invoice_number, m.shipment_id, m.po_id,
       m.po_match_status, m.shipment_match_status, m.invoice_match_status,
       m.product_match_status, m.quantity_match_status, m.carrier_match_status,
       m.currency_match_status, m.rate_match_status, m.duplicate_check_status,
       m.variance_amount, m.audit_status,
       CASE
         WHEN m.shipment_match_status = 'MISSING' OR m.po_match_status = 'MISSING' THEN 'MISSING_RECORD'
         WHEN m.duplicate_check_status = 'DUPLICATE'
              OR m.carrier_match_status = 'MISMATCH'
              OR m.audit_status = 'SHIPMENT_MISMATCH' THEN 'BLOCK_PAYMENT'
         WHEN m.rate_match_status <> 'MATCH'
              OR m.quantity_match_status = 'EXCEPTION'
              OR m.currency_match_status = 'MISMATCH'
              OR m.audit_status IN ('POTENTIAL_OVERCHARGE','INCORRECT_FUEL_SURCHARGE') THEN 'REVIEW_REQUIRED'
         WHEN m.quantity_match_status = 'WARNING'
              OR m.audit_status = 'POTENTIAL_UNDERCHARGE' THEN 'MATCHED_WITH_WARNING'
         ELSE 'MATCHED' END AS overall_match_status,
       CASE
         WHEN m.shipment_match_status = 'MISSING' THEN 'Invoice has no matching shipment'
         WHEN m.po_match_status = 'MISSING' THEN 'Shipment has no matching purchase order'
         WHEN m.duplicate_check_status = 'DUPLICATE' THEN 'Duplicate invoice number'
         WHEN m.carrier_match_status = 'MISMATCH' THEN 'Invoice carrier differs from shipment carrier'
         WHEN m.rate_match_status <> 'MATCH' THEN 'Rate issue: ' || m.rate_match_status
         WHEN m.quantity_match_status = 'EXCEPTION' THEN 'Delivered quantity exceeds ordered'
         WHEN m.currency_match_status = 'MISMATCH' THEN 'Currency differs from contract'
         WHEN m.audit_status IN ('POTENTIAL_OVERCHARGE','INCORRECT_FUEL_SURCHARGE') THEN 'Charge above expected'
         ELSE '' END AS exception_reason,
       CASE
         WHEN m.shipment_match_status = 'MISSING' OR m.po_match_status = 'MISSING' THEN 'Return to carrier - do not pay'
         WHEN m.duplicate_check_status = 'DUPLICATE' THEN 'Block - verify not already paid'
         WHEN m.carrier_match_status = 'MISMATCH' THEN 'Block - confirm billing entity'
         WHEN m.rate_match_status <> 'MATCH' THEN 'Route to Procurement for rate validation'
         WHEN m.audit_status IN ('POTENTIAL_OVERCHARGE','INCORRECT_FUEL_SURCHARGE') THEN 'Short-pay to expected - dispute variance'
         WHEN m.quantity_match_status = 'EXCEPTION' THEN 'Reconcile delivery with Warehouse'
         ELSE 'Approve for payment' END AS recommended_action
FROM (
    SELECT i.invoice_id, i.invoice_number, i.shipment_id, s.po_id,
           CASE WHEN s.po_id IS NULL THEN 'MISSING'
                WHEN s.po_id IN (SELECT po_id FROM sunlog.fact_purchase_order) THEN 'MATCH'
                ELSE 'MISSING' END AS po_match_status,
           CASE WHEN s.shipment_id IS NULL THEN 'MISSING' ELSE 'MATCH' END AS shipment_match_status,
           CASE WHEN s.shipment_id IS NULL THEN 'MISSING' ELSE 'MATCH' END AS invoice_match_status,
           -- PO groups several shipment lines, so a differing product id is a
           -- multi-product PO (informational), not an exception.
           CASE WHEN po.product_id IS NULL OR s.product_id IS NULL THEN 'UNKNOWN'
                WHEN po.product_id = s.product_id THEN 'MATCH' ELSE 'MULTI_PRODUCT_PO' END AS product_match_status,
           -- Quantity is compared to the shipment's own ordered (planned)
           -- quantity, not the grouped PO total.
           CASE WHEN s.delivered_quantity IS NULL THEN 'PENDING'
                WHEN s.delivered_quantity > s.planned_quantity THEN 'EXCEPTION'
                WHEN s.delivered_quantity < s.planned_quantity THEN 'WARNING'
                ELSE 'MATCH' END AS quantity_match_status,
           CASE WHEN s.carrier_id IS NULL THEN 'UNKNOWN'
                WHEN i.carrier_id = s.carrier_id THEN 'MATCH' ELSE 'MISMATCH' END AS carrier_match_status,
           CASE WHEN i.currency = 'USD' THEN 'MATCH' ELSE 'MISMATCH' END AS currency_match_status,
           CASE WHEN fa.rate_status = 'RATED' THEN 'MATCH' ELSE COALESCE(fa.rate_status, 'NO_RATE') END AS rate_match_status,
           CASE WHEN fa.audit_status = 'DUPLICATE_INVOICE' THEN 'DUPLICATE' ELSE 'OK' END AS duplicate_check_status,
           fa.variance_amount, fa.audit_status
    FROM sunlog.fact_freight_invoice i
    LEFT JOIN sunlog.fact_shipment s ON i.shipment_id = s.shipment_id
    LEFT JOIN sunlog.fact_purchase_order po ON s.po_id = po.po_id
    LEFT JOIN sunlog.v_freight_audit fa ON i.invoice_id = fa.invoice_id
) m;

DROP VIEW IF EXISTS sunlog.v_three_way_match_summary;
CREATE VIEW sunlog.v_three_way_match_summary AS
SELECT overall_match_status, COUNT(*) AS invoice_count,
       ROUND(SUM(CASE WHEN variance_amount > 0 THEN variance_amount ELSE 0 END), 2) AS total_positive_variance
FROM sunlog.v_three_way_match GROUP BY overall_match_status;
