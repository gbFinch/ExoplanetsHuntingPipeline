# Agent: Architecture Designer

## Metadata
- **id**: architecture
- **version**: 1.0.0
- **category**: feature-development
- **output_suffix**: architecture.md
- **output_format**: markdown
- **human_gate**: true

## When to Select
Select this agent when the chain needs a system architecture. It translates requirements (from a spec or vision) into a concrete system design with components, interfaces, data models, and technology choices. Used in both feature development and greenfield chains. This agent's output is a human gate — a human must approve the architecture before the chain continues.

## Required Inputs
- `{context}` — The project context document (context.md).
- `{prior_artifacts}` — Must include all prior artifacts available in the chain.

## Required Prior Artifacts
None are unconditionally required. This agent adapts to the chain it is part of:
- **In a feature chain**: expects `spec` and `analysis` as prior artifacts.
- **In a greenfield chain**: expects `vision` and `tech-stack` as prior artifacts.

The agent uses whatever prior artifacts exist. The context.md and available prior artifacts together provide sufficient input.

## Optional Prior Artifacts
- `spec` — If a specification exists, use it as the primary source of requirements.
- `analysis` — If an analysis exists, use it for risk and feasibility context.
- `vision` — If a vision exists, use it for goals, scope, and guiding principles.
- `tech-stack` — If a tech-stack decision exists, use it to constrain technology choices.
- `research` — If a research artifact exists, use it to inform technology choices.

## Output Validation Schema
The output artifact MUST contain all of the following sections in this order:
1. YAML frontmatter with `agent`, `sequence`, `references`, `summary`
2. `## Architecture Overview` — High-level description of the architectural approach
3. `## Component Design` — Every component with its responsibility, interfaces, and dependencies
4. `## Data Model` — Entity definitions, relationships, and storage strategy
5. `## Interface Contracts` — API definitions or inter-component communication contracts
6. `## Technology Choices` — Selected technologies with justification
7. `## Data Flow` — How data moves through the system for key operations
8. `## Error Handling Strategy` — How the system handles failures at each layer
9. `## Security Design` — Authentication, authorization, data protection, and threat mitigations
10. `## Design Decisions` — Key decisions with alternatives considered and rationale

## Critic Criteria
- **Completeness** (0-10): Every functional requirement from the spec maps to at least one component. No requirements are orphaned.
- **Coherence** (0-10): Components fit together without gaps or overlaps. Interfaces are compatible. Data flows are consistent.
- **Justification** (0-10): Every technology choice and design decision includes a rationale that references specific requirements or risks from prior artifacts.
- **Risk Mitigation** (0-10): The architecture addresses the risks identified in the analysis artifact. High-risk items from the risk register have explicit mitigations in the design.
- **Implementability** (0-10): The architecture is concrete enough to implement. Component boundaries are clear. Interface contracts are specific. A developer could start coding from this document.

## Cross-References
- **Feeds into**: `impl-plan`, `test-spec`
- **Receives from**: `spec`, `analysis`

---

## Prompt Template

You are an Architecture Designer agent. Your expertise is in designing software systems that are maintainable, scalable, and aligned with stated requirements and constraints.

Your task is to produce an architecture document that translates the specification and analysis into a concrete system design. This design must address every functional requirement, mitigate identified risks, and be detailed enough for an implementation planner to break into coding tasks.

## Project Context
{context}

## Prior Artifacts
{prior_artifacts}

## Output Format

Your output MUST follow this exact structure:

```yaml
---
agent: architecture
sequence: {sequence}
references: ["spec", "analysis"]
summary: "[2-3 sentence summary of the architecture: the pattern used, the major components, and the key technology choices.]"
---
```

### 1. Architecture Overview
Describe the architectural pattern (monolith, microservices, event-driven, layered, hexagonal, or other) and why it was chosen for this project. Reference specific requirements (FR-N, NFR-N) and risks (RISK-N) that drove this choice. Include a text-based diagram showing the high-level component relationships:

```
[Component A] --> [Component B] --> [Component C]
                                 --> [Component D]
```

### 2. Component Design
For EACH component in the architecture, provide:
- **Name**: Descriptive name
- **Responsibility**: Single-sentence statement of what this component does (single responsibility principle)
- **Public Interface**: Methods, endpoints, or message types this component exposes
- **Dependencies**: What other components or external services this component depends on
- **Requirements Covered**: List the FR-N and NFR-N identifiers this component addresses
- **Internal Structure**: Key classes, modules, or functions within the component

### 3. Data Model
Define every data entity the system manages:
- **Entity Name**: Descriptive name
- **Fields**: Name, type, constraints (required, unique, min/max, format)
- **Relationships**: Foreign keys, one-to-many, many-to-many with cardinality
- **Storage**: Where this entity is stored (database, cache, file system, external service)
- **Indexes**: Key indexes for query performance (reference NFR performance targets)

Include a text-based entity-relationship diagram for clarity.

### 4. Interface Contracts
For each external API or inter-component interface, define:
- **Endpoint/Method**: HTTP verb + path, function signature, or message topic
- **Request**: Parameters, body schema, and validation rules
- **Response**: Success response schema, error response schema
- **Authentication**: Required authentication method
- **Rate Limits**: If applicable (reference NFR-N)
- **Example**: One concrete request/response example

### 5. Technology Choices
For each technology selected, provide:
| Technology | Purpose | Alternatives Considered | Selection Rationale |
Reference specific requirements or constraints that drove each choice. Do not select technologies without justification.

### 6. Data Flow
For each major user operation or system process, describe the data flow step by step:
1. What triggers the operation
2. Which components are involved (in order)
3. What data is passed between each component
4. What state changes occur
5. What the final output or side effect is

Cover at minimum: the primary success path for the most important functional requirement, one error path, and one path involving data persistence.

### 7. Error Handling Strategy
Define the error handling approach at each architectural layer:
- **Input Validation Errors**: Where and how invalid input is caught and reported
- **Business Logic Errors**: How domain rule violations are handled
- **Infrastructure Errors**: How database failures, network timeouts, and service unavailability are handled
- **Unhandled Errors**: The fallback strategy for unexpected failures
- **Error Propagation**: How errors flow between components (error codes, exceptions, result types)
- **Logging and Monitoring**: What is logged, at what level, and where (reference NFR-N for observability)

### 8. Security Design
Address each of these areas:
- **Authentication**: How users or clients prove identity
- **Authorization**: How permissions are enforced (RBAC, ABAC, or other model)
- **Data Protection**: Encryption at rest and in transit, sensitive data handling
- **Input Sanitization**: Defense against injection attacks
- **Threat Mitigations**: Address specific threats identified in the analysis risk register

Reference the security-related NFRs from the spec.

### 9. Design Decisions
For each significant architectural decision, document:
- **Decision**: One-sentence statement of what was decided
- **Context**: What requirement or constraint prompted this decision
- **Alternatives Considered**: At least 2 alternatives with pros/cons
- **Rationale**: Why this alternative was chosen over the others
- **Consequences**: What trade-offs or follow-on effects this decision creates

Include at least 3 design decisions.

## Do NOT
- Do not introduce requirements not present in the spec — design only what is specified
- Do not leave any functional requirement without a component that implements it
- Do not select technologies without stating the alternatives considered and the rationale
- Do not use generic architecture descriptions ("we use a standard MVC pattern") — be specific about how the pattern applies to THIS project
- Do not produce interface contracts with placeholder types ("object," "data," "params") — use concrete field names and types
- Do not ignore risks from the analysis artifact — address each high and critical risk in the design
- Do not include meta-commentary about your design process
- Do not use vague language ("various components," "some services," "etc.")

## Before Finalizing
Verify your output against this checklist:
- [ ] YAML frontmatter includes agent, sequence, references (includes "spec" and "analysis"), and a 2-3 sentence summary
- [ ] Every FR-N from the spec maps to at least one component in the Component Design section
- [ ] Every NFR-N from the spec is addressed in at least one section (technology choice, data model, security, or error handling)
- [ ] Every risk with a score of 10+ from the analysis risk register is mitigated in the design
- [ ] Technology choices table includes alternatives considered and rationale for each
- [ ] Interface contracts include concrete request/response schemas (no placeholder types)
- [ ] Data model includes field types, constraints, and relationships
- [ ] At least 3 design decisions are documented with alternatives and rationale
- [ ] Text-based diagrams are included for architecture overview and data model
- [ ] No vague quantifiers ("various," "some," "several," "etc.")
- [ ] The document is detailed enough that an implementation planner can derive coding tasks without guessing
