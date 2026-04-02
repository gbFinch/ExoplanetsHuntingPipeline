# Prompt Engineering Guidelines

All agent prompts in this system MUST follow these standards. Read this document before writing or modifying any agent prompt.

---

## 1. Structure Standards

Every agent prompt template must follow this structure in order:

### 1.1 Role Definition (required)
Open with a clear role statement:
```
You are a [Role Name] agent. Your expertise is in [specific domain].
```

### 1.2 Task Statement (required)
One clear sentence stating what to produce:
```
Your task is to produce a [artifact type] based on the provided context and prior artifacts.
```

### 1.3 Context Injection (required)
All input is provided inline. Never assume the agent can access files:
```
## Project Context
{context}

## Prior Artifacts
{prior_artifacts}
```

### 1.4 Output Format (required)
Define exact sections, ordering, and what each section must contain:
```
## Output Format
Your output MUST follow this exact structure:
1. YAML frontmatter (agent, sequence, references, summary)
2. [Section 1] — [what it contains]
3. [Section 2] — [what it contains]
...
```

### 1.5 Anti-Patterns (required)
Explicitly state what NOT to do:
```
## Do NOT
- Do not include meta-commentary about your process
- Do not use vague language ("various", "some", "etc.")
- Do not repeat the context verbatim
- [domain-specific anti-patterns]
```

### 1.6 Quality Checklist (required)
End with a self-verification checklist:
```
## Before Finalizing
Verify your output against this checklist:
- [ ] All required sections present and substantive
- [ ] YAML frontmatter includes summary (2-3 sentences)
- [ ] References to prior artifacts are explicit
- [ ] No filler or boilerplate text
- [ ] [domain-specific checks]
```

---

## 2. Quality Standards

Every agent prompt must produce output that meets these criteria:

### 2.1 Self-Contained
A reader with no prior context can understand the artifact on its own. Every artifact must stand alone.

### 2.2 Frontmatter Summary
Every markdown artifact must include YAML frontmatter with a `summary` field (2-3 sentences). This is critical for the context accumulation strategy — later agents receive these summaries instead of full artifacts.

```yaml
---
agent: spec
sequence: 1
references: []
summary: "Defines a REST API authentication system supporting OAuth2 and JWT. Covers user registration, login, token refresh, and session management. Targets Node.js/Express with PostgreSQL."
---
```

### 2.3 Explicit References
When building on prior artifacts, reference them by name and section:
- Good: "Based on the scalability requirement in 01-spec.md (NFR-3), the architecture uses..."
- Bad: "As mentioned earlier, the architecture should be scalable..."

### 2.4 No Filler
- No: "In this document, we will discuss the architecture for..."
- Yes: "## Architecture Overview\nThe system uses a microservices pattern with..."

Avoid introductions, conclusions, and transitional paragraphs that don't add substance.

### 2.5 Concrete Language
Use numbers, names, and specifics. Never use:
- "various" → list the actual items
- "some" → specify which ones
- "etc." → complete the list
- "several" → give the count
- "may/might/could" (when describing what the system does) → use "will" or "does"

---

## 3. Critic Prompt Standards

The critic prompt is constructed by the orchestrator from `agents/critic.md` (base behavior) + the producing agent's `## Critic Criteria` section. The combined critic prompt must follow these rules:

### 3.1 Structural Validation First
Check the artifact against the agent's `## Output Validation Schema` before any semantic analysis. If required sections are missing, auto-fail immediately.

### 3.2 Independent Dimension Scoring
Score each dimension independently. Do not let one dimension's score influence another. Complete all dimension scores before computing the average.

### 3.3 Specific Issue Citations
Every issue must reference the exact section or content it applies to:
- Good: `{ "location": "Functional Requirements, item 3", "description": "Requirement is not testable — 'user-friendly' is subjective" }`
- Bad: `{ "location": "general", "description": "Some requirements are vague" }`

### 3.4 Severity Classification
- **Critical**: Blocks downstream agents. Missing required sections, contradictory requirements, fundamentally wrong approach.
- **Major**: Significantly reduces artifact quality. Incomplete analysis, missing important considerations, weak justifications.
- **Minor**: Reduces polish but doesn't block progress. Awkward phrasing, minor inconsistencies, missing edge cases.
- **Suggestion**: Optional improvements. Better naming, additional examples, formatting improvements.

### 3.5 Constructive Feedback
Every issue MUST include a suggested fix:
- Good: `"description": "NFR-2 lacks a specific performance target. Suggest: 'API response time under 200ms for p95.'"`
- Bad: `"description": "NFR-2 is too vague."`

---

## 4. Code Artifact Standards

When an agent produces code (not markdown), these additional standards apply:

### 4.1 No Frontmatter in Code
Code files do not contain YAML frontmatter. Metadata is tracked only in state.json.

### 4.2 Production Quality
Generated code must be production-ready:
- Proper error handling
- Input validation at system boundaries
- No placeholder or TODO comments (unless explicitly marking a known limitation)
- Follows the project's existing code style and conventions (as described in context.md)

### 4.3 TDD Compliance
Test artifacts are produced BEFORE implementation code. The code agent's prompt must reference the test file and state: "Write implementation code that passes all tests in [test artifact]."

---

## 5. Prompt Testing

When writing or modifying an agent prompt:

1. **Test with simple input**: Run the prompt with a minimal context.md to verify it produces a structurally valid artifact.
2. **Test with complex input**: Run with a detailed, multi-faceted context.md to verify it handles complexity.
3. **Verify critic differentiation**: Ensure the critic criteria actually distinguish between good and bad output (a perfect score should be rare).
4. **Test with summarized context**: Verify the prompt works when prior artifacts are provided as summaries (not full content), simulating later chain steps.
