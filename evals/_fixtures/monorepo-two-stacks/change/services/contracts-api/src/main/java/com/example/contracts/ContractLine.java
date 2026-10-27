package com.example.contracts;

import jakarta.persistence.Entity;
import jakarta.persistence.Id;

@Entity
public class ContractLine {
    @Id
    private Long id;
    private Long contractId;
    private String label;

    public Long getId() { return id; }
    public Long getContractId() { return contractId; }
    public String getLabel() { return label; }
}
