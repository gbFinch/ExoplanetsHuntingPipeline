# Agent Catalog

This catalog lists all available agents. The orchestrator reads this file to decide which agents to include in the chain.

---

## How to Use This Catalog

1. The orchestrator reads `context.md` and classifies the project type
2. It uses the **fixed default chain** for that type (see Default Chains below)
3. **The default chain is mandatory.** Every agent in the chain must be executed. No agents may be removed.
4. The orchestrator may **add** cross-cutting agents (research, decision) at appropriate positions
5. The final chain is written to `state.json`

---

## Default Chains

### Feature Development (TDD)
```
spec → analysis → architecture → impl-plan → test-spec → tests → code → review → summary
```

### Bug Fixing (TDD)
```
bug-report → bug-analysis → root-cause → fix-plan → repro-test → fix → verification → summary
```

### Greenfield Project
```
vision → research → tech-stack → architecture → project-structure → scaffolding → summary
```

### New Project (Greenfield + Feature combined)
```
vision → research → tech-stack → architecture → project-structure → scaffolding → impl-plan → test-spec → tests → code → review → summary
```

### Design
```
design-brief → design-research → design-system → design-impl → design-review → summary
```

### Documentation
```
doc-brief → doc-outline → doc-draft → doc-review → doc-final → summary
```

### Refactoring
```
refactor-analysis → refactor-plan → refactor-tests → refactor → refactor-verify → summary
```

---

## Agent Index

### Feature Development

| ID | Name | File | Output | Default Gate |
|----|------|------|--------|-------------|
| `spec` | Specification Writer | `agents/spec.md` | NN-spec.md | no |
| `analysis` | Requirements Analyst | `agents/analysis.md` | NN-analysis.md | no |
| `architecture` | Architecture Designer | `agents/architecture.md` | NN-architecture.md | **yes** |
| `impl-plan` | Implementation Planner | `agents/impl-plan.md` | NN-implementation-plan.md | **yes** |
| `test-spec` | Test Specification Writer | `agents/test-spec.md` | NN-test-spec.md | no |
| `tests` | Test Code Writer | `agents/tests.md` | NN-tests.\<ext\> | no |
| `code` | Code Generator | `agents/code.md` | NN-code.\<ext\> | no |
| `review` | Code Reviewer | `agents/review.md` | NN-review.md | no |

### Bug Fixing

| ID | Name | File | Output | Default Gate |
|----|------|------|--------|-------------|
| `bug-report` | Bug Report Formalizer | `agents/bug-report.md` | NN-bug-report.md | no |
| `bug-analysis` | Bug Analyst | `agents/bug-analysis.md` | NN-bug-analysis.md | no |
| `root-cause` | Root Cause Identifier | `agents/root-cause.md` | NN-root-cause.md | no |
| `fix-plan` | Fix Planner | `agents/fix-plan.md` | NN-fix-plan.md | **yes** |
| `repro-test` | Reproduction Test Writer | `agents/repro-test.md` | NN-repro-test.\<ext\> | no |
| `fix` | Fix Implementer | `agents/fix.md` | NN-fix.\<ext\> | no |
| `verification` | Fix Verifier | `agents/verification.md` | NN-verification.md | no |

### Greenfield Project

| ID | Name | File | Output | Default Gate |
|----|------|------|--------|-------------|
| `vision` | Project Vision Writer | `agents/vision.md` | NN-vision.md | no |
| `research` | Researcher | `agents/research.md` | NN-research.md | no |
| `tech-stack` | Technology Stack Decision | `agents/tech-stack.md` | NN-tech-stack.md | **yes** |
| `architecture` | Architecture Designer | `agents/architecture.md` | NN-architecture.md | **yes** |
| `project-structure` | Project Structure Designer | `agents/project-structure.md` | NN-project-structure.md | no |
| `scaffolding` | Scaffolding Generator | `agents/scaffolding.md` | NN-scaffolding.\<ext\> | no |

### New Project (Greenfield + Feature combined)

Uses agents from both the Greenfield and Feature chains. No new agents — this is a combined chain for building a complete project from idea to working code in a single workflow.

| ID | Name | File | Output | Default Gate |
|----|------|------|--------|-------------|
| `vision` | Project Vision Writer | `agents/vision.md` | NN-vision.md | no |
| `research` | Researcher | `agents/research.md` | NN-research.md | no |
| `tech-stack` | Technology Stack Decision | `agents/tech-stack.md` | NN-tech-stack.md | **yes** |
| `architecture` | Architecture Designer | `agents/architecture.md` | NN-architecture.md | **yes** |
| `project-structure` | Project Structure Designer | `agents/project-structure.md` | NN-project-structure.md | no |
| `scaffolding` | Scaffolding Generator | `agents/scaffolding.md` | NN-scaffolding.\<ext\> | no |
| `impl-plan` | Implementation Planner | `agents/impl-plan.md` | NN-implementation-plan.md | **yes** |
| `test-spec` | Test Specification Writer | `agents/test-spec.md` | NN-test-spec.md | no |
| `tests` | Test Code Writer | `agents/tests.md` | NN-tests.\<ext\> | no |
| `code` | Code Generator | `agents/code.md` | NN-code.\<ext\> | no |
| `review` | Code Reviewer | `agents/review.md` | NN-review.md | no |

### Design

| ID | Name | File | Output | Default Gate |
|----|------|------|--------|-------------|
| `design-brief` | Design Brief Writer | `agents/design-brief.md` | NN-design-brief.md | no |
| `design-research` | Design Researcher | `agents/design-research.md` | NN-design-research.md | no |
| `design-system` | Design System Specifier | `agents/design-system.md` | NN-design-system.md | **yes** |
| `design-impl` | Design Implementer | `agents/design-impl.md` | NN-design-impl.\<ext\> | no |
| `design-review` | Design Reviewer | `agents/design-review.md` | NN-design-review.md | no |

### Documentation

| ID | Name | File | Output | Default Gate |
|----|------|------|--------|-------------|
| `doc-brief` | Documentation Brief Writer | `agents/doc-brief.md` | NN-doc-brief.md | no |
| `doc-outline` | Documentation Outliner | `agents/doc-outline.md` | NN-doc-outline.md | no |
| `doc-draft` | Documentation Drafter | `agents/doc-draft.md` | NN-doc-draft.md | no |
| `doc-review` | Documentation Reviewer | `agents/doc-review.md` | NN-doc-review.md | no |
| `doc-final` | Documentation Finalizer | `agents/doc-final.md` | NN-doc-final.md | no |

### Refactoring

| ID | Name | File | Output | Default Gate |
|----|------|------|--------|-------------|
| `refactor-analysis` | Refactoring Analyst | `agents/refactor-analysis.md` | NN-refactor-analysis.md | no |
| `refactor-plan` | Refactoring Planner | `agents/refactor-plan.md` | NN-refactor-plan.md | **yes** |
| `refactor-tests` | Refactoring Test Writer | `agents/refactor-tests.md` | NN-refactor-tests.\<ext\> | no |
| `refactor` | Refactoring Implementer | `agents/refactor.md` | NN-refactor.\<ext\> | no |
| `refactor-verify` | Refactoring Verifier | `agents/refactor-verify.md` | NN-refactor-verification.md | no |

### Cross-Cutting

| ID | Name | File | Output | When to Insert |
|----|------|------|--------|---------------|
| `research` | Researcher | `agents/research.md` | NN-research.md | Context mentions unfamiliar technology or requires investigation |
| `decision` | Decision Maker | `agents/decision.md` | NN-decision.md | Chain hits a fork with multiple viable paths |
| `summary` | Summarizer | `agents/summary.md` | NN-summary.md | Always added as the final step of any chain |

### System

| ID | Name | File | Description |
|----|------|------|-------------|
| `critic` | Critic | `agents/critic.md` | Quality gate invoked after every artifact. Not part of the chain — invoked automatically by the orchestrator. |
