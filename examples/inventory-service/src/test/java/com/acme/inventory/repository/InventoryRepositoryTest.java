package com.acme.inventory.repository;

import com.acme.inventory.entity.Inventory;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;

import java.math.BigDecimal;
import java.util.Optional;

import static org.assertj.core.api.Assertions.assertThat;

@DataJpaTest
class InventoryRepositoryTest {

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
