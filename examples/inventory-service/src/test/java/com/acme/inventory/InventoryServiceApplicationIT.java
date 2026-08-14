package com.acme.inventory;

import org.junit.jupiter.api.Test;
import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

/**
 * Boots the application the way `java -jar` does, which is the only way to catch a service
 * that builds but cannot start - a broken schema.sql, a driver at the wrong scope, a
 * datasource property that no longer resolves.
 *
 * <p>It became an *IT when the datasource became a real PostgreSQL: main() builds its own
 * context rather than a Spring test context, so @ServiceConnection cannot reach it and the
 * container's coordinates are passed as command-line arguments instead, exactly as the
 * environment does in compose.yaml.
 */
@Testcontainers
class InventoryServiceApplicationIT {

    @Container
    static PostgreSQLContainer<?> postgres = new PostgreSQLContainer<>("postgres:16-alpine");

    @Test
    void mainStartsWithoutWebServer() {
        InventoryServiceApplication.main(new String[]{
                "--spring.main.web-application-type=none",
                "--spring.datasource.url=" + postgres.getJdbcUrl(),
                "--spring.datasource.username=" + postgres.getUsername(),
                "--spring.datasource.password=" + postgres.getPassword(),
        });
    }
}
