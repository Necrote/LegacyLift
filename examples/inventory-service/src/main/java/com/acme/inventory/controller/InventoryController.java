package com.acme.inventory.controller;

import com.acme.inventory.service.InventoryService;
import com.acme.inventory.service.InventoryView;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.Parameter;
import io.swagger.v3.oas.annotations.enums.ParameterIn;
import io.swagger.v3.oas.annotations.media.Content;
import io.swagger.v3.oas.annotations.media.ExampleObject;
import io.swagger.v3.oas.annotations.media.Schema;
import io.swagger.v3.oas.annotations.responses.ApiResponse;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.server.ResponseStatusException;

import static org.springframework.http.HttpStatus.BAD_REQUEST;
import static org.springframework.http.HttpStatus.NOT_FOUND;

@RestController
@RequestMapping("/api/inventory")
public class InventoryController {

    private final InventoryService service;

    public InventoryController(InventoryService service) {
        this.service = service;
    }

    @Operation(
            summary = "Legacy inventory lookup",
            description = "Ported from InventoryServlet. Answers the original pipe-delimited line "
                    + "sku|name|qty|needsReorder|unitPrice, where unitPrice is post-discount.",
            parameters = {
                    @Parameter(name = "sku", in = ParameterIn.QUERY, required = true,
                            description = "SKU to look up"),
                    @Parameter(name = "orderQty", in = ParameterIn.QUERY, required = false,
                            description = "Order quantity used for the price break (default 0)")
            },
            responses = {
                    @ApiResponse(responseCode = "200", description = "Found",
                            content = @Content(mediaType = "text/plain",
                                    schema = @Schema(type = "string"),
                                    examples = @ExampleObject(value = "SKU-1|Widget|200|false|88.00"))),
                    @ApiResponse(responseCode = "400", description = "orderQty missing-typed or negative",
                            content = @Content(mediaType = "text/plain",
                                    schema = @Schema(type = "string"))),
                    @ApiResponse(responseCode = "404", description = "Unknown SKU",
                            content = @Content(mediaType = "text/plain",
                                    schema = @Schema(type = "string"),
                                    examples = @ExampleObject(value = "NOT FOUND"))),
                    @ApiResponse(responseCode = "500", description = "Database error",
                            content = @Content(mediaType = "text/plain",
                                    schema = @Schema(type = "string"),
                                    examples = @ExampleObject(value = "DB ERROR")))
            }
    )
    // Query parameters, not a path variable: the legacy servlet read both with
    // request.getParameter(...), so `?sku=X` is the contract every existing caller already uses.
    @GetMapping(produces = MediaType.TEXT_PLAIN_VALUE)
    public ResponseEntity<String> getInventory(
            @RequestParam("sku") String sku,
            @RequestParam(name = "orderQty", defaultValue = "0") int orderQty) {

        if (orderQty < 0) {
            throw new ResponseStatusException(BAD_REQUEST, "orderQty must be >= 0");
        }
        return service.getInventoryView(sku, orderQty)
                .map(view -> ResponseEntity.ok(line(view)))
                .orElseGet(() -> ResponseEntity.status(NOT_FOUND).body("NOT FOUND"));
    }

    /**
     * The legacy wire format, field for field and separator for separator.
     *
     * <p>unitPrice comes from toPlainString() rather than String.format("%.2f", ...): the service
     * has already rounded it to scale 2, and String.format is locale-sensitive - it would emit
     * "88,00" on a comma-decimal JVM and silently break every caller parsing the line.
     */
    private static String line(InventoryView view) {
        return view.sku() + "|" + view.name() + "|" + view.qty() + "|"
                + view.needsReorder() + "|" + view.unitPrice().toPlainString();
    }
}
