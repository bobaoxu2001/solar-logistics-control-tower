# Power BI Data Model

The model is a star schema. Import the `rpt_*` views; do not connect report visuals directly to operational tables.

## Relationships

| One-side dimension | Key | Many-side fact | Foreign key | Active |
|---|---|---|---|---|
| `rpt_dim_date` | `date` | `rpt_fact_shipment` | `planned_delivery_date` | Yes |
| `rpt_dim_carrier` | `carrier_id` | `rpt_fact_shipment` | `carrier_id` | Yes |
| `rpt_dim_lane` | `lane_id` | `rpt_fact_shipment` | `lane_id` | Yes |
| `rpt_dim_product` | `product_id` | `rpt_fact_shipment` | `product_id` | Yes |
| `rpt_dim_location` | `location_id` | `rpt_fact_shipment` | `destination_location_id` | Yes |
| `rpt_fact_shipment` | `shipment_id` | `rpt_fact_milestone` | `shipment_id` | Yes |
| `rpt_dim_carrier` | `carrier_id` | `rpt_fact_freight_audit` | `invoice_carrier` | Yes |
| `rpt_dim_lane` | `lane_id` | `rpt_fact_freight_audit` | `lane_id` | Yes |
| `rpt_dim_product` | `product_id` | `rpt_fact_freight_audit` | `product_id` | Yes |
| `rpt_fact_shipment` | `shipment_id` | `rpt_fact_accrual` / `rpt_fact_claim` | `shipment_id` | Yes |

Use single-direction filtering from dimension to fact. Role-playing shipment dates should use inactive relationships and `USERELATIONSHIP` in date-specific measures. Keep scorecards as aggregate report tables filtered directly by carrier or lane; do not join them fact-to-fact. This avoids unnecessary many-to-many relationships.

## Grains and provenance

- Shipment: one row per source-derived shipment; public patterns with derived solar mapping.
- Milestone, freight invoice, claim, capacity, and approval data: simulated and labeled.
- Data-quality: one row per detected operational exception.
- Scorecards: one row per carrier or valid lane, generated deterministically from reporting views.
- Date: one complete calendar row per day from the earliest planned ship date through the latest planned delivery date.
