-- Demo seed. The two rows exercise both business rules in a single request each:
--   SKU-1  qty 200 > reorder_level 50  -> not flagged, so quantity price breaks apply
--   SKU-2  qty 5  <= reorder_level 10  -> flagged for reorder, which suppresses any break
-- ON CONFLICT DO NOTHING keeps this idempotent: spring.sql.init runs it on every boot,
-- and unlike the old in-memory database a real PostgreSQL volume survives a restart.
INSERT INTO inventory (sku, name, qty, reorder_level, unit_price)
VALUES ('SKU-1', 'Widget', 200, 50, 100.0000)
ON CONFLICT (sku) DO NOTHING;

INSERT INTO inventory (sku, name, qty, reorder_level, unit_price)
VALUES ('SKU-2', 'Gadget', 5, 10, 100.0000)
ON CONFLICT (sku) DO NOTHING;
