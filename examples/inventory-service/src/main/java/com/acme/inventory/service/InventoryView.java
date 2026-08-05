package com.acme.inventory.service;

import java.math.BigDecimal;

public record InventoryView(
        String sku,
        String name,
        int qty,
        boolean needsReorder,
        BigDecimal unitPrice
) {
}
