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

## Configuration

Every tunable — model, token cap, corpus size limit, command defaults, Maven timeout — lives in
`agent/legacylift/config.py`, and each one can be overridden for a single run with a
`LEGACYLIFT_*` environment variable:

```bash
LEGACYLIFT_MODEL=gpt-5-mini legacylift generate samples/legacy-inventory
LEGACYLIFT_MAX_ITERATIONS=5 legacylift verify output/inventory-service
```

The mutation-gate invariants (the 80% floor, the Maven arg list) are deliberately **not**
overridable — an env var that could set the threshold to 0, or slip in `-DskipTests`, would
disable the quality gate from outside the process. Those change only by editing the file.

## Run the generated service (Docker demo)

The generated service ships its own multi-stage `Dockerfile`, so it runs as a container with no
JDK, no Maven and no database on your machine — and no manual edits. From the generated service
directory:

```bash
cd output/inventory-service
docker build -t legacylift/inventory-service .
docker run --rm -p 8080:8080 legacylift/inventory-service
```

Then, in another terminal:

```bash
# well-stocked SKU (qty 200 > reorder level 50), 500 units -> 12% price break applied
curl "localhost:8080/api/v1/inventory?sku=SKU-1&orderQty=500"
# SKU-1|Widget|200|false|88.00

# reorder-flagged SKU (qty 5 <= reorder level 10) -> price break suppressed by the reorder rule
curl "localhost:8080/api/v1/inventory?sku=SKU-2&orderQty=500"
# SKU-2|Gadget|5|true|100.00
```

The response is the legacy pipe-delimited line `sku|name|qty|needsReorder|unitPrice`, preserved
from the original servlet along with its `404 NOT FOUND` for an unknown SKU. The price-break
boundaries are preserved too — the same SKU at `orderQty=100` returns `95.00` (5%) and at `99`
returns `100.00` (no break).

**The build stage runs the unit tests but stops at `package`**, one phase before the `verify` that
pitest is bound to — the mutation gate belongs in `legacylift verify` and CI, not in every image
build. Nothing is skipped to make the image build pass. The runtime stage is a JRE-only Alpine
image running as a non-root user, with the JVM as PID 1 so `docker stop` shuts Spring down cleanly.

Prefer to run it without Docker? `mvn spring-boot:run` in the same directory works too, and serves
the identical responses — the in-memory H2 and its `data.sql` seed are part of the generated
service now, not a manual step.

> Generation is stochastic, so class names and the exact endpoint can vary between runs. If a
> `curl` above 404s, check what your service actually exposes:
> `grep -rn "Mapping" src/main/java --include=*.java`.

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
- **Containerized out of the box** — every generated service ships a multi-stage `Dockerfile`
  (Maven build stage → JRE-only Alpine runtime, non-root) plus an in-memory datasource and seed,
  so `docker build && docker run` serves the endpoint with nothing installed but Docker.
- **Automated fix loop** — `legacylift verify` takes generated code to verified code unattended:
  classifies the failure (compile / test / mutation), sends a filtered Maven excerpt plus the
  current source back to the agent, applies the fix, re-runs, capped at 3 attempts — with fixes
  that weaken the mutation gate rejected before they reach disk.

**Week 2 — next**

- **Replace H2 with PostgreSQL** — Testcontainers for tests, a real datasource for run
  (the generated `Dockerfile` becomes one service in a `docker compose` stack).

## Why the quality gates matter

LLMs generate plausible code; mutation testing proves the *tests* actually constrain behavior.
A generated service with 80%+ PIT score is defensibly production-grade in a way "it compiles" is not.
## Author

Vivek Patel — [linkedin.com/in/necrote](https://linkedin.com/in/necrote) · Backend engineer, fintech platform modernization.
