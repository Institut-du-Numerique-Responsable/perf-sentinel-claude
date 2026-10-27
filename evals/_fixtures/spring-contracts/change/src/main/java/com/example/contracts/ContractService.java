package com.example.contracts;

import java.util.ArrayList;
import java.util.List;
import org.springframework.stereotype.Service;

@Service
public class ContractService {
    private final ContractRepository contracts;
    private final ContractLineRepository lines;

    public ContractService(ContractRepository contracts, ContractLineRepository lines) {
        this.contracts = contracts;
        this.lines = lines;
    }

    public Contract get(Long id) {
        return contracts.findById(id).orElseThrow();
    }

    public List<ContractView> listForClient(Long clientId) {
        List<ContractView> views = new ArrayList<>();
        for (Contract contract : contracts.findByClientId(clientId)) {
            views.add(new ContractView(contract, lines.findByContractId(contract.getId())));
        }
        return views;
    }

    public record ContractView(Contract contract, List<ContractLine> lines) {
    }
}
