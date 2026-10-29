package com.example.contracts;

import java.util.List;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ContractController {
    private final ContractService service;

    public ContractController(ContractService service) {
        this.service = service;
    }

    @GetMapping("/contracts/{id}")
    public Contract get(@PathVariable Long id) {
        return service.get(id);
    }

    @GetMapping("/clients/{clientId}/contracts")
    public List<ContractService.ContractView> listForClient(@PathVariable Long clientId) {
        return service.listForClient(clientId);
    }
}
