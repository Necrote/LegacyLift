package com.acme.inventory.repository;

import com.acme.inventory.entity.Inventory;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.jdbc.AutoConfigureTestDatabase;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;
import org.springframework.boot.testcontainers.service.connection.ServiceConnection;
import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

import java.math.BigDecimal;
import java.util.Optional;

import static org.assertj.core.api.Assertions.assertThat;

/**
 * Named *IT, so failsafe runs it and PIT does not: it needs a Docker daemon, which the image
 * build (which stops at `package`) and the mutation gate must both stay free of.
 *
 * <p>It runs against the real PostgreSQL the service targets, with the real schema.sql, under
 * the shipped ddl-auto=validate. That makes it the check that the JPA entity and schema.sql
 * still agree - drift between them fails the build here rather than at `docker compose up`.
 */
@DataJpaTest
// Without this, @DataJpaTest swaps the container out for an embedded database - which is no
// longer on the classpath at all, so the context would simply fail to start.
@AutoConfigureTestDatabase(replace = AutoConfigureTestDatabase.Replace.NONE)
@Testcontainers
class InventoryRepositoryIT {

    // @ServiceConnection points spring.datasource.* at the container, so no test property
    // duplicates the URL, user or password.
    @Container
    @ServiceConnection
    static PostgreSQLContainer<?> postgres = new PostgreSQLContainer<>("postgres:16-alpine");

    @Autowired
    private InventoryRepository repository;

    @Test
    void saveAndFindBySku_findsPersistedEntity() {
        Inventory inv = new Inventory("ABC123", "Widget", 15, 5, new BigDecimal("12.34"));
        repository.save(inv);

        Optional<Inventory> found = repository.findBySku("ABC123");
        assertThat(found).isPresent();
        assertThat(found.get().getName()).isEqualTo("Widget");
        assertThat(repository.findBySku("MISSING")).isEmpty();
    }
}
