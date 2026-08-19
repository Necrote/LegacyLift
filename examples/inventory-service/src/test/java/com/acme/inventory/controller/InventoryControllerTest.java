package com.acme.inventory.controller;

import com.acme.inventory.service.InventoryService;
import com.acme.inventory.service.InventoryView;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.context.annotation.Import;
import org.springframework.dao.DataRetrievalFailureException;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import java.math.BigDecimal;
import java.util.Optional;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.anyInt;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.Mockito.*;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

@WebMvcTest(controllers = InventoryController.class)
@Import(DatabaseExceptionHandler.class)
class InventoryControllerTest {

    @Autowired
    private MockMvc mockMvc;

    @org.springframework.boot.test.mock.mockito.MockBean
    private InventoryService service;

    /**
     * Pins the ported wire contract: the exact pipe-delimited body AND its Content-Type. A
     * mutation that reorders, reformats or re-delimits the fields is killed here rather than
     * surviving - the mutation gate proves the logic is constrained, not that the bytes on the
     * wire still match.
     */
    @Test
    void success_returnsLegacyPipeDelimitedLine_asTextPlain() throws Exception {
        when(service.getInventoryView(anyString(), anyInt())).thenReturn(
                Optional.of(new InventoryView("SKU-1", "Widget", 200, false, new BigDecimal("88.00"))));

        mockMvc.perform(get("/api/inventory?sku=SKU-1&orderQty=500"))
                .andExpect(status().isOk())
                .andExpect(content().contentTypeCompatibleWith(MediaType.TEXT_PLAIN))
                .andExpect(content().string("SKU-1|Widget|200|false|88.00"));
    }

    @Test
    void reorderFlaggedSku_rendersTrueAndTheUndiscountedPrice() throws Exception {
        when(service.getInventoryView(anyString(), anyInt())).thenReturn(
                Optional.of(new InventoryView("SKU-2", "Gadget", 5, true, new BigDecimal("100.00"))));

        mockMvc.perform(get("/api/inventory?sku=SKU-2&orderQty=500"))
                .andExpect(status().isOk())
                .andExpect(content().string("SKU-2|Gadget|5|true|100.00"));
    }

    @Test
    void orderQtyDefaultsToZeroWhenAbsent() throws Exception {
        when(service.getInventoryView(anyString(), anyInt())).thenReturn(
                Optional.of(new InventoryView("SKU-1", "Widget", 200, false, new BigDecimal("100.00"))));

        mockMvc.perform(get("/api/inventory?sku=SKU-1")).andExpect(status().isOk());

        ArgumentCaptor<Integer> qty = ArgumentCaptor.forClass(Integer.class);
        verify(service).getInventoryView(eq("SKU-1"), qty.capture());
        assertThat(qty.getValue()).isEqualTo(0);
    }

    @Test
    void unknownSku_is404WithTheLegacyBody() throws Exception {
        when(service.getInventoryView(anyString(), anyInt())).thenReturn(Optional.empty());

        mockMvc.perform(get("/api/inventory?sku=MISSING"))
                .andExpect(status().isNotFound())
                .andExpect(content().string("NOT FOUND"));
    }

    @Test
    void negativeOrderQty_isBadRequest400() throws Exception {
        mockMvc.perform(get("/api/inventory?sku=SKU-1&orderQty=-1"))
                .andExpect(status().isBadRequest());
        verifyNoInteractions(service);
    }

    @Test
    void nonNumericOrderQty_isBadRequest400() throws Exception {
        mockMvc.perform(get("/api/inventory?sku=SKU-1&orderQty=abc"))
                .andExpect(status().isBadRequest());
        verifyNoInteractions(service);
    }

    @Test
    void missingSku_isBadRequest400() throws Exception {
        mockMvc.perform(get("/api/inventory"))
                .andExpect(status().isBadRequest());
        verifyNoInteractions(service);
    }

    @Test
    void dataAccessError_mapsTo500WithGenericMessage() throws Exception {
        when(service.getInventoryView(anyString(), anyInt()))
                .thenThrow(new DataRetrievalFailureException("boom"));

        mockMvc.perform(get("/api/inventory?sku=SKU-1"))
                .andExpect(status().isInternalServerError())
                .andExpect(content().string("DB ERROR"));
    }
}
