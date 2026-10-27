package com.example.contracts;

import org.springframework.stereotype.Service;

@Service
public class ContractService {
    private final ContractRepository contracts;

    public ContractService(ContractRepository contracts) {
        this.contracts = contracts;
    }

    public Contract get(Long id) {
        return contracts.findById(id).orElseThrow();
    }
}
