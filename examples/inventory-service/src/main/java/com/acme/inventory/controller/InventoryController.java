package com.acme.inventory.controller;

import com.acme.inventory.service.InventoryService;
import com.acme.inventory.service.InventoryView;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.server.ResponseStatusException;

import static org.springframework.http.HttpStatus.BAD_REQUEST;

@RestController
@RequestMapping("/api/inventory")
public class InventoryController {

    private final InventoryService service;

    public InventoryController(InventoryService service) {
        this.service = service;
    }

    @GetMapping("/{sku}")
    public InventoryView getInventory(@PathVariable String sku,
                                      @RequestParam(name = "orderQty", defaultValue = "0") int orderQty) {
        if (orderQty < 0) {
            throw new ResponseStatusException(BAD_REQUEST, "orderQty must be >= 0");
        }
        return service.getInventoryView(sku, orderQty);
    }
}
