package com.acme.inventory;

import org.junit.jupiter.api.Test;

class InventoryServiceApplicationTest {

    @Test
    void mainStartsWithoutWebServer() {
        InventoryServiceApplication.main(new String[]{"--spring.main.web-application-type=none"});
    }
}
