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
import org.springframework.web.server.ResponseStatusException;

import java.math.BigDecimal;
import java.util.Optional;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.catchThrowable;
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

    @Test
    void notFoundYields404() {
        when(repository.findBySku(anyString())).thenReturn(Optional.empty());

        Throwable thrown = catchThrowable(() -> service.getInventoryView("NOPE", 0));

        assertThat(thrown)
                .isInstanceOf(ResponseStatusException.class)
                .hasMessageContaining("404 NOT_FOUND");
    }

    @Test
    void needsReorderIsTrueAtOrBelowReorderLevel_boundaryAtEqual() {
        Inventory inv = new Inventory("S1", "Item", 100, 100, new BigDecimal("10.00"));
        when(repository.findBySku("S1")).thenReturn(Optional.of(inv));

        InventoryView view = service.getInventoryView("S1", 0);

        assertThat(view.needsReorder()).isTrue();
    }

    @Test
    void needsReorderIsFalseAboveReorderLevel_boundaryAtPlusOne() {
        Inventory inv = new Inventory("S2", "Item", 101, 100, new BigDecimal("10.00"));
        when(repository.findBySku("S2")).thenReturn(Optional.of(inv));

        InventoryView view = service.getInventoryView("S2", 0);

        assertThat(view.needsReorder()).isFalse();
    }

    @Test
    void discountsApplyAtExactBoundariesAndMidpoints_whenNotNeedingReorder() {
        Inventory inv = new Inventory("S3", "Item", 200, 100, new BigDecimal("100.00"));
        when(repository.findBySku("S3")).thenReturn(Optional.of(inv));

        // 99 -> 0%
        assertThat(service.getInventoryView("S3", 99).unitPrice()).isEqualByComparingTo("100.00");
        // 100 -> 5%
        assertThat(service.getInventoryView("S3", 100).unitPrice()).isEqualByComparingTo("95.00");
        // 499 -> 5%
        assertThat(service.getInventoryView("S3", 499).unitPrice()).isEqualByComparingTo("95.00");
        // 500 -> 12%
        assertThat(service.getInventoryView("S3", 500).unitPrice()).isEqualByComparingTo("88.00");
    }

    @Test
    void discountsAreDisabledWhenNeedingReorder_evenAtOrAboveBoundaries() {
        Inventory inv = new Inventory("S4", "Item", 50, 100, new BigDecimal("200.00")); // qty below reorder -> needsReorder
        when(repository.findBySku("S4")).thenReturn(Optional.of(inv));

        assertThat(service.getInventoryView("S4", 100).unitPrice()).isEqualByComparingTo("200.00");
        assertThat(service.getInventoryView("S4", 500).unitPrice()).isEqualByComparingTo("200.00");
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

        InventoryView view = service.getInventoryView("NEG", 0);

        assertThat(view.qty()).isEqualTo(0); // clamped
        assertThat(view.needsReorder()).isTrue(); // 0 <= 0

        boolean containsError = listAppender.list.stream()
                .anyMatch(e -> e.getLevel() == Level.ERROR && e.getFormattedMessage().contains("negative qty for NEG"));
        assertThat(containsError).isTrue();
    }
}
