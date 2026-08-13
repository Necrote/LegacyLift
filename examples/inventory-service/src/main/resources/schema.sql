-- Schema for the table the legacy servlet queried:
--   "SELECT sku, name, qty, reorder_level, unit_price FROM inventory WHERE sku = ?"
-- Types match the JPA entity exactly, because ddl-auto=validate compares the two at
-- startup and fails fast on any drift (varchar lengths and the numeric precision/scale
-- come from the @Column annotations on Inventory).
-- IF NOT EXISTS keeps this idempotent: spring.sql.init runs it on every boot.
CREATE TABLE IF NOT EXISTS inventory (
    sku           VARCHAR(100)   NOT NULL,
    name          VARCHAR(255)   NOT NULL,
    qty           INTEGER        NOT NULL,
    reorder_level INTEGER        NOT NULL,
    unit_price    NUMERIC(19, 4) NOT NULL,
    CONSTRAINT pk_inventory PRIMARY KEY (sku)
);
