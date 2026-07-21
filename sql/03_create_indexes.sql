-- Indexes supporting the KPI, audit, and three-way-match workloads.

CREATE INDEX IF NOT EXISTS ix_stg_shipment_mode        ON sunlog.stg_shipment (shipment_mode);
CREATE INDEX IF NOT EXISTS ix_stg_shipment_country     ON sunlog.stg_shipment (destination_country);
CREATE INDEX IF NOT EXISTS ix_stg_shipment_sched_date  ON sunlog.stg_shipment (scheduled_delivery_date);

CREATE INDEX IF NOT EXISTS ix_shipment_carrier         ON sunlog.fact_shipment (carrier_id);
CREATE INDEX IF NOT EXISTS ix_shipment_lane            ON sunlog.fact_shipment (lane_id);
CREATE INDEX IF NOT EXISTS ix_shipment_po              ON sunlog.fact_shipment (po_id);
CREATE INDEX IF NOT EXISTS ix_shipment_dates           ON sunlog.fact_shipment (ship_date, actual_delivery_date);

CREATE INDEX IF NOT EXISTS ix_milestone_shipment       ON sunlog.fact_shipment_milestone (shipment_id, milestone_type);

CREATE INDEX IF NOT EXISTS ix_invoice_shipment         ON sunlog.fact_freight_invoice (shipment_id);
CREATE INDEX IF NOT EXISTS ix_invoice_carrier          ON sunlog.fact_freight_invoice (carrier_id);
CREATE INDEX IF NOT EXISTS ix_invoice_number           ON sunlog.fact_freight_invoice (invoice_number);

CREATE INDEX IF NOT EXISTS ix_accessorial_invoice      ON sunlog.fact_accessorial_charge (invoice_id);
CREATE INDEX IF NOT EXISTS ix_rate_card_lookup         ON sunlog.dim_rate_card (carrier_id, lane_id, transport_mode, effective_start_date);
CREATE INDEX IF NOT EXISTS ix_accrual_period           ON sunlog.fact_accrual (accounting_period);
CREATE INDEX IF NOT EXISTS ix_dq_exception_rule        ON sunlog.data_quality_exception (rule_id, resolution_status);
