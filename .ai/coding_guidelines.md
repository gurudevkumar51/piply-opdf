# Coding Guidelines

## 1. Modular Development Approach

* **Preserve Stability:** Whatever functionality is already implemented and stable MUST remain unchanged and be reused. Do not arbitrarily refactor working components unless strictly necessary for integration.
* **Forward Planning:** For functionality that is not yet implemented, create module structures, interfaces, contracts, and placeholders in advance.
* **Module Independence:** Development should be performed module by module. This allows independent implementation, testing, deployment, and enhancement without impacting existing components.
* **High Cohesion & Loose Coupling:** Every module should be highly cohesive (doing one thing well) and loosely coupled to simplify maintenance and future expansion.
* **Incremental Expansion:** The framework must support an incremental development lifecycle where new capabilities (e.g., ML models, Similarity engines) can be plugged into the pipeline without requiring major refactoring of existing workflows.

## 2. Object-Oriented Design Principles (OOP)

To maintain high coding standards, scalability, and optimized code, the framework maximizes the use of Object-Oriented Programming (OOP) principles:

* **Encapsulation:** Keep module-level responsibilities strictly bounded. Avoid global state leakage.
* **Abstraction:** Rely heavily on interfaces and base classes (e.g., Abstract Base Classes in Python) for defining engine contracts.
* **Inheritance:** Use inheritance where appropriate for sharing reusable behaviors across similar detectors or extractors.
* **Polymorphism:** Design the pipeline so that processing engines and strategies can be easily swapped or extended (e.g., swapping OCR engines, swapping ML models).

## 3. SOLID Principles

* **Single Responsibility:** A class should only have one reason to change. 
* **Open/Closed:** Code should be open for extension (e.g., adding a new Level 2 Similarity algorithm) but closed for modification.
* **Liskov Substitution:** Subtypes must be substitutable for their base types.
* **Interface Segregation:** Create narrow, focused interfaces rather than large, monolithic ones.
* **Dependency Inversion:** Depend on abstractions, not concretions.

## 4. Required Design Patterns

Utilize the following design patterns where beneficial across the architecture:
* **Factory Pattern:** For instantiating different OCR models, ML predictors, or Data Extractors based on configuration.
* **Strategy Pattern:** For applying different processing logic based on the Document or Component type (e.g., Table Extraction vs Paragraph Extraction).
* **Builder Pattern:** For safely building complex manifests and document reconstructions.
* **Repository Pattern:** To abstract the storage layers (SQLite, JSON, files) for the Knowledge Base from the business logic.
* **Observer Pattern:** To emit events across the pipeline (e.g., logging, UI updates during the Human Feedback Loop).
* **Dependency Injection:** To pass required services (like a specific DB session or Config manager) into downstream engines.
