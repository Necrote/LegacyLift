package com.acme.inventory.service;

import com.acme.inventory.entity.Inventory;
import com.acme.inventory.repository.InventoryRepository;
import ch.qos.logback.classic.Level;
import ch.qos.logback.classic.Logger;
import ch.qos.logback.classic.spi.ILoggingEvent;
import ch.qos.logback.core.read.ListAppender;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.mockito.Mockito;

import java.math.BigDecimal;
import java.util.Optional;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.Mockito.when;

class InventoryServiceTest {

    private InventoryRepository repository;
    private InventoryService service;

    @BeforeEach
    void setUp() {
        repository = Mockito.mock(InventoryRepository.class);
        service = new InventoryService(repository);
    }

    /** Unknown SKU is an empty Optional, not an exception - the controller renders the 404. */
    @Test
    void unknownSkuYieldsEmpty() {
        when(repository.findBySku(anyString())).thenReturn(Optional.empty());

        assertThat(service.getInventoryView("NOPE", 0)).isEmpty();
    }

    /** Unwraps the Optional so each rule test below reads as it did before. */
    private InventoryView view(String sku, int orderQty) {
        return service.getInventoryView(sku, orderQty).orElseThrow();
    }

    @Test
    void needsReorderIsTrueAtOrBelowReorderLevel_boundaryAtEqual() {
        Inventory inv = new Inventory("S1", "Item", 100, 100, new BigDecimal("10.00"));
        when(repository.findBySku("S1")).thenReturn(Optional.of(inv));

        InventoryView view = view("S1", 0);

        assertThat(view.needsReorder()).isTrue();
    }

    @Test
    void needsReorderIsFalseAboveReorderLevel_boundaryAtPlusOne() {
        Inventory inv = new Inventory("S2", "Item", 101, 100, new BigDecimal("10.00"));
        when(repository.findBySku("S2")).thenReturn(Optional.of(inv));

        InventoryView view = view("S2", 0);

        assertThat(view.needsReorder()).isFalse();
    }

    @Test
    void discountsApplyAtExactBoundariesAndMidpoints_whenNotNeedingReorder() {
        Inventory inv = new Inventory("S3", "Item", 200, 100, new BigDecimal("100.00"));
        when(repository.findBySku("S3")).thenReturn(Optional.of(inv));

        // 99 -> 0%
        assertThat(view("S3", 99).unitPrice()).isEqualByComparingTo("100.00");
        // 100 -> 5%
        assertThat(view("S3", 100).unitPrice()).isEqualByComparingTo("95.00");
        // 499 -> 5%
        assertThat(view("S3", 499).unitPrice()).isEqualByComparingTo("95.00");
        // 500 -> 12%
        assertThat(view("S3", 500).unitPrice()).isEqualByComparingTo("88.00");
    }

    @Test
    void discountsAreDisabledWhenNeedingReorder_evenAtOrAboveBoundaries() {
        Inventory inv = new Inventory("S4", "Item", 50, 100, new BigDecimal("200.00")); // qty below reorder -> needsReorder
        when(repository.findBySku("S4")).thenReturn(Optional.of(inv));

        assertThat(view("S4", 100).unitPrice()).isEqualByComparingTo("200.00");
        assertThat(view("S4", 500).unitPrice()).isEqualByComparingTo("200.00");
    }

    @Test
    void negativeQtyIsClampedToZeroAndLogged_needsReorderComputedAfterClamp() {
        Inventory inv = new Inventory("NEG", "Item", -1, 0, new BigDecimal("10.00"));
        when(repository.findBySku("NEG")).thenReturn(Optional.of(inv));

        // Capture logs
        Logger logger = (Logger) org.slf4j.LoggerFactory.getLogger(InventoryService.class);
        ListAppender<ILoggingEvent> listAppender = new ListAppender<>();
        listAppender.start();
        logger.addAppender(listAppender);

        InventoryView view = view("NEG", 0);

        assertThat(view.qty()).isEqualTo(0); // clamped
        assertThat(view.needsReorder()).isTrue(); // 0 <= 0

        boolean containsError = listAppender.list.stream()
                .anyMatch(e -> e.getLevel() == Level.ERROR && e.getFormattedMessage().contains("negative qty for NEG"));
        assertThat(containsError).isTrue();
    }
}
