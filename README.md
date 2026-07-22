# LegacyLift 🏗️→☁️

**An agentic AI copilot that converts legacy Java monoliths into tested, deployable Spring Boot microservices.**

Legacy modernization is how I spent 3 years working for a US banking financial services client for Kin+Carta - converting COBOL/PCF-era
services into Spring Boot microservices on OpenShift, with quality enforced by PIT mutation testing.
LegacyLift automates that workflow with an LLM agent, while keeping the quality gates that make generated code trustworthy.

## How it works

```
legacy code ──► [1] ANALYZE ──► MODERNIZATION_PLAN.md   (service boundaries, entities, endpoints)
                     │
                     ▼
               [2] GENERATE ──► Spring Boot service + JUnit tests
                     │
                     ▼
               [3] VERIFY  ──► build + tests + PIT mutation score gate (CI)
```

The agent never ships code that hasn't passed the same gates a human engineer's code would:
compile, unit tests green, **80%+ PIT mutation score**.

## Why the quality gates matter

LLMs generate plausible code; mutation testing proves the *tests* actually constrain behavior.
A generated service with 80%+ PIT score is defensibly production-grade in a way "it compiles" is not.
## Author

Vivek Patel — [linkedin.com/in/necrote](https://linkedin.com/in/necrote) · Backend engineer, fintech platform modernization.
