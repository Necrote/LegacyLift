package com.acme.inventory.service;

import com.acme.inventory.entity.Inventory;
import com.acme.inventory.repository.InventoryRepository;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;
import org.springframework.web.server.ResponseStatusException;

import java.math.BigDecimal;
import java.math.RoundingMode;

import static org.springframework.http.HttpStatus.NOT_FOUND;

@Service
public class InventoryService {

    private static final Logger log = LoggerFactory.getLogger(InventoryService.class);

    private final InventoryRepository repository;

    public InventoryService(InventoryRepository repository) {
        this.repository = repository;
    }

    public InventoryView getInventoryView(String sku, int orderQty) {
        Inventory inv = repository.findBySku(sku)
                .orElseThrow(() -> new ResponseStatusException(NOT_FOUND, "NOT FOUND"));

        int qty = inv.getQty();
        if (qty < 0) {
            qty = 0;
            // BUSINESS RULE 3: clamp and log
            log.error("negative qty for {}", sku);
        }

        boolean needsReorder = qty <= inv.getReorderLevel(); // BUSINESS RULE 1: <= threshold

        BigDecimal discountRate = BigDecimal.ZERO;
        if (!needsReorder) { // BUSINESS RULE 2: no discounts when needing reorder
            if (orderQty >= 500) {
                discountRate = new BigDecimal("0.12");
            } else if (orderQty >= 100) {
                discountRate = new BigDecimal("0.05");
            }
        }

        BigDecimal price = inv.getUnitPrice()
                .multiply(BigDecimal.ONE.subtract(discountRate))
                .setScale(2, RoundingMode.HALF_UP);

        return new InventoryView(inv.getSku(), inv.getName(), qty, needsReorder, price);
        // Response unitPrice is post-discount, rounded to 2 decimals to mirror legacy formatting.
    }
}
