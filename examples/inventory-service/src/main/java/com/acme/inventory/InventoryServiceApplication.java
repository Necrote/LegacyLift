package com.acme.inventory;

import io.swagger.v3.oas.annotations.OpenAPIDefinition;
import io.swagger.v3.oas.annotations.info.Info;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

// The description lives in annotations on classes that already exist - never a @Configuration
// class with an @Bean OpenAPI method, which PIT would mutate and no test would cover.
@SpringBootApplication
@OpenAPIDefinition(info = @Info(title = "Inventory Service", version = "1.0"))
public class InventoryServiceApplication {

    public static void main(String[] args) {
        SpringApplication.run(InventoryServiceApplication.class, args);
    }
}
