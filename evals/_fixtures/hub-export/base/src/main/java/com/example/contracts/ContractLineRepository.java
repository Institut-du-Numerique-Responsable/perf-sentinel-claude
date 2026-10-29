package com.example.contracts;

import java.util.List;
import org.springframework.data.jpa.repository.JpaRepository;

public interface ContractLineRepository extends JpaRepository<ContractLine, Long> {
    List<ContractLine> findByContractId(Long contractId);
}
