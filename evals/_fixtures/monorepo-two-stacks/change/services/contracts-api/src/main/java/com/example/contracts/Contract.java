package com.example.contracts;

import jakarta.persistence.Entity;
import jakarta.persistence.Id;

@Entity
public class Contract {
    @Id
    private Long id;
    private Long clientId;
    private String reference;

    public Long getId() { return id; }
    public Long getClientId() { return clientId; }
    public String getReference() { return reference; }
}
