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
import org.springframework.web.server.ResponseStatusException;

import java.math.BigDecimal;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.anyInt;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.Mockito.*;
import static org.springframework.http.HttpStatus.NOT_FOUND;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

@WebMvcTest(controllers = InventoryController.class)
@Import(DatabaseExceptionHandler.class)
class InventoryControllerTest {

    @Autowired
    private MockMvc mockMvc;

    @org.springframework.boot.test.mock.mockito.MockBean
    private InventoryService service;

    @Test
    void success_returnsJson_andDefaultOrderQtyIsZero() throws Exception {
        when(service.getInventoryView(anyString(), anyInt()))
                .thenReturn(new InventoryView("SKU1", "Name", 10, false, new BigDecimal("95.00")));

        var result = mockMvc.perform(get("/api/inventory/SKU1"))
                .andExpect(status().isOk())
                .andExpect(content().contentTypeCompatibleWith(MediaType.APPLICATION_JSON))
                .andExpect(jsonPath("$.sku").value("SKU1"))
                .andExpect(jsonPath("$.name").value("Name"))
                .andExpect(jsonPath("$.qty").value(10))
                .andExpect(jsonPath("$.needsReorder").value(false))
                // Ensure two-decimal formatting is preserved in JSON number
                .andExpect(content().string(org.hamcrest.Matchers.containsString("\"unitPrice\":95.00")))
                .andReturn();

        ArgumentCaptor<Integer> qtyCaptor = ArgumentCaptor.forClass(Integer.class);
        verify(service).getInventoryView(eq("SKU1"), qtyCaptor.capture());
        assertThat(qtyCaptor.getValue()).isEqualTo(0);
    }

    @Test
    void negativeOrderQty_isBadRequest400() throws Exception {
        mockMvc.perform(get("/api/inventory/SKU1?orderQty=-1"))
                .andExpect(status().isBadRequest());
        verifyNoInteractions(service);
    }

    @Test
    void nonNumericOrderQty_isBadRequest400() throws Exception {
        mockMvc.perform(get("/api/inventory/SKU1?orderQty=abc"))
                .andExpect(status().isBadRequest());
        verifyNoInteractions(service);
    }

    @Test
    void notFound_fromServiceMapsTo404() throws Exception {
        when(service.getInventoryView(anyString(), anyInt()))
                .thenThrow(new ResponseStatusException(NOT_FOUND, "NOT FOUND"));

        mockMvc.perform(get("/api/inventory/MISSING"))
                .andExpect(status().isNotFound());
    }

    @Test
    void dataAccessError_mapsTo500WithGenericMessage() throws Exception {
        when(service.getInventoryView(anyString(), anyInt()))
                .thenThrow(new DataRetrievalFailureException("boom"));

        mockMvc.perform(get("/api/inventory/SKU1"))
                .andExpect(status().isInternalServerError())
                .andExpect(content().string("DB ERROR"));
    }
}
