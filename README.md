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

## Quick start

Install the agent (Python 3.12):

```bash
cd agent
pip install -e .
# PowerShell:  $env:OPENAI_API_KEY = "sk-..."
# bash:        export OPENAI_API_KEY = sk-...
```

Run the three-stage pipeline against the bundled sample:

```bash
legacylift analyze  ../samples/legacy-inventory                          # -> MODERNIZATION_PLAN.md
legacylift generate ../samples/legacy-inventory -o ../output/inventory-service
legacylift verify   ../output/inventory-service                          # compile + JUnit + PIT >=80% gate
```

`verify` is the quality gate: it runs `mvn verify` — compile, JUnit tests, then PIT — and **fails
if the mutation score drops below 80%**. When the build fails it doesn't just report; it feeds the
Maven errors back to the agent, applies the fix, and re-runs, **capped at 3 attempts**:

```
$ legacylift verify output/inventory-service
  mvn verify FAILED (exit 1, compile): InventoryControllerTest.java:[7,49] package org.springframework.boot.test.mock does not exist
  fix attempt 1/3: asking gpt-5 ...
  rewrote 1 file(s): src/test/java/com/acme/inventory/controller/InventoryControllerTest.java
VERIFIED after 1 fix attempt(s) - mvn verify green, PIT gate held.
```

The loop is not allowed to cheat its way to green. A proposed fix that lowers `mutationThreshold`,
unbinds pitest from the verify phase, or `@Disabled`s a test is **rejected before it is written** —
the gate is the product, so a "fix" that removes it is discarded. Every rewritten file is backed up
under `.legacylift/attempt-N/`, and each run appends to `.legacylift/verify.log`. If 3 attempts
aren't enough, it says so and exits non-zero rather than claiming success.

## Run the generated service (demo)

The generated service is a runnable Spring Boot app (its pom includes `spring-boot-maven-plugin`).
Running it locally today needs two small manual tweaks — a **Week-2 automation target**: scope the
H2 dependency `runtime` instead of `test`, and drop a `data.sql` seed under
`src/main/resources`. With those in place:

```bash
cd output/inventory-service
mvn spring-boot:run
```

```bash
# well-stocked SKU, 500 units -> 12% price break applied
curl "localhost:8080/api/inventory/SKU-1?orderQty=500"
# {"sku":"SKU-1","name":"Widget","qty":200,"needsReorder":false,"unitPrice":88.00}

# reorder-flagged SKU -> price break suppressed by the reorder rule
curl "localhost:8080/api/inventory/SKU-2?orderQty=500"
# {"sku":"SKU-2","name":"Gadget","qty":5,"needsReorder":true,"unitPrice":100.00}
```

The JSON endpoint is `GET /api/inventory/{sku}?orderQty=N`; a legacy pipe-delimited endpoint is
also generated at `GET /api/v1/inventory?sku=...&orderQty=N`.

## Roadmap

**Week 1 — done ✅**

- **End-to-end pipeline** — `analyze → generate → verify` running on the OpenAI API (gpt-5).
- **Traceable plan** — `analyze` emits a `MODERNIZATION_PLAN.md` where every claim is anchored to a
  file path and a verbatim source quote (no fabricated line numbers).
- **Full Spring Boot 3 / Java 21 service** — controller / service / repository / entity + JUnit 5
  tests, generated from the plan and the legacy source.
- **Enforced quality gate** — `mvn verify` runs PIT bound to the verify phase (JUnit 5 bridge wired
  in) and fails under 80% mutation score; the sample clears it at ~83%.
- **Tests proven to constrain, not just cover** — deleting each business rule turns a specific test
  red (manual mutation check).
- **Runnable service + live curl demo** — see above.
- **Automated fix loop** — `legacylift verify` takes generated code to verified code unattended:
  classifies the failure (compile / test / mutation), sends a filtered Maven excerpt plus the
  current source back to the agent, applies the fix, re-runs, capped at 3 attempts — with fixes
  that weaken the mutation gate rejected before they reach disk.

**Week 2 — next**

- **Replace H2 with PostgreSQL** — Testcontainers for tests, a real datasource for run.
- **Runnable out of the box** — auto-configured datasource + an optional seed profile, so the
  runtime-H2 and demo-seed steps above aren't manual.

## Why the quality gates matter

LLMs generate plausible code; mutation testing proves the *tests* actually constrain behavior.
A generated service with 80%+ PIT score is defensibly production-grade in a way "it compiles" is not.
## Author

Vivek Patel — [linkedin.com/in/necrote](https://linkedin.com/in/necrote) · Backend engineer, fintech platform modernization.
