package com.example.contracts;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

import java.util.Optional;
import org.junit.jupiter.api.Test;

class ContractServiceTest {
    @Test
    void getReturnsTheContract() {
        var repository = mock(ContractRepository.class);
        var contract = new Contract();
        when(repository.findById(1L)).thenReturn(Optional.of(contract));

        assertThat(new ContractService(repository).get(1L)).isSameAs(contract);
    }
}
