package com.acme.inventory.entity;

import org.junit.jupiter.api.Test;

import java.math.BigDecimal;

import static org.assertj.core.api.Assertions.assertThat;

/**
 * The accessors are what the controller builds its response from, so a getter returning
 * the wrong thing is a real defect, not boilerplate. These assertions used to be made
 * indirectly by the repository test; that test now needs a PostgreSQL container and is
 * excluded from the mutation gate, so the cover is restored here with no database.
 */
class InventoryTest {

    @Test
    void constructorArgumentsAreExposedByTheAccessors() {
        Inventory inv = new Inventory("SKU-9", "Sprocket", 42, 7, new BigDecimal("13.5000"));

        assertThat(inv.getSku()).isEqualTo("SKU-9");
        assertThat(inv.getName()).isEqualTo("Sprocket");
        assertThat(inv.getQty()).isEqualTo(42);
        assertThat(inv.getReorderLevel()).isEqualTo(7);
        assertThat(inv.getUnitPrice()).isEqualByComparingTo(new BigDecimal("13.5000"));
    }
}
