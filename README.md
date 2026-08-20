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

**Prerequisites:** Python 3.14, Java 21 (Temurin), Maven 3.9+, **Docker**, and an OpenAI
**Platform** API key (pay-as-you-go billing — ChatGPT subscription credits do not work here).

Docker is required by `verify`, not just by the demo: the generated service's `*IT` tests start a
real PostgreSQL through Testcontainers, so `mvn verify` needs a running daemon. `legacylift
verify` checks for one up front and tells you to start Docker rather than spending fix attempts
on it.

Create the virtualenv and install the agent **from the repo root**:

```powershell
# Windows / PowerShell
py -3.14 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e .\agent
$env:OPENAI_API_KEY = "sk-..."
```

```bash
# macOS / Linux
python3.14 -m venv .venv
source .venv/bin/activate
pip install -e ./agent
export OPENAI_API_KEY="sk-..."
```

Activation is per-terminal — re-run the activate line in each new shell, or the `legacylift`
command won't be on your `PATH`.

Run the three-stage pipeline against the bundled sample, **staying in the repo root** so each
command finds what the previous one wrote:

```bash
legacylift analyze  samples/legacy-inventory                      # -> MODERNIZATION_PLAN.md
legacylift generate samples/legacy-inventory -o output/inventory-service
legacylift verify   output/inventory-service                      # compile + JUnit + PIT >=80% gate
```

`generate` reads `MODERNIZATION_PLAN.md` from the current directory (override with `-p`), which is
why every command runs from the root.

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

The generated service ships a multi-stage `Dockerfile` **and** a `compose.yaml`, so it runs as a
container next to a real PostgreSQL with no JDK, no Maven and no database installed on your
machine — and no manual edits. From the generated service directory:

```bash
cd output/inventory-service
docker compose up --build
```

That brings up `postgres:16-alpine` and the service together, waits for the database to pass a
`pg_isready` healthcheck before starting the app, and keeps the data in a named volume. The
service image itself holds no database — it is one service in the stack.

Then, in another terminal:

```bash
# well-stocked SKU (qty 200 > reorder level 50), 500 units -> 12% price break applied
curl "http://localhost:8080/api/inventory?sku=SKU-1&orderQty=500"
# SKU-1|Widget|200|false|88.00

# reorder-flagged SKU (qty 5 <= reorder level 10) -> price break suppressed by the reorder rule
curl "http://localhost:8080/api/inventory?sku=SKU-2&orderQty=500"
# SKU-2|Gadget|5|true|100.00
```

On **Windows PowerShell**, `curl` is an alias for `Invoke-WebRequest`, which rejects a URL without a
scheme (`The URI prefix is not recognized`). Call the real curl that ships with Windows 10+ instead:

```powershell
curl.exe "http://localhost:8080/api/inventory?sku=SKU-1&orderQty=500"
```

The generated service also describes itself. Every endpoint it serves is published as OpenAPI,
so the contract is discoverable from the service rather than from this file:

- **Swagger UI** — <http://localhost:8080/swagger-ui.html>
- **OpenAPI spec (JSON)** — <http://localhost:8080/v3/api-docs>

The generation prompt requires the description to match the *ported* contract rather than an
idealized REST reading of it — a `text/plain` endpoint is documented as `text/plain`, a query
parameter as a query parameter, and each legacy status code with the exact body it carries. It
is written as annotations on the classes the generator already emits, never as a separate
`@Bean OpenAPI` configuration class, which would be one more untested class for PIT to mutate.

The response is the legacy pipe-delimited line `sku|name|qty|needsReorder|unitPrice`, preserved
from the original servlet along with its `404 NOT FOUND` for an unknown SKU. The price-break
boundaries are preserved too — the same SKU at `orderQty=100` returns `95.00` (5%) and at `99`
returns `100.00` (no break).

**The build stage runs the unit tests but stops at `package`**, one phase before the `verify` that
pitest is bound to — the mutation gate belongs in `legacylift verify` and CI, not in every image
build. Nothing is skipped to make the image build pass. The runtime stage is a JRE-only Alpine
image running as a non-root user, with the JVM as PID 1 so `docker stop` shuts Spring down cleanly.

Prefer to run the service from source? `docker compose up -d db` starts just the database, and
`mvn spring-boot:run` in the same directory then serves the identical responses — the datasource,
`schema.sql` and the `data.sql` seed are part of the generated service now, not a manual step.

> **If startup fails with a Hibernate validation error**, the named volume is holding an older
> schema: `schema.sql` uses `CREATE TABLE IF NOT EXISTS`, so it will not re-shape a table that
> already exists, and `spring.jpa.hibernate.ddl-auto=validate` then refuses to start against the
> stale one. `docker compose down -v` drops the volume and the next `up` rebuilds it.

> Generation is stochastic, so class names and the exact endpoint can vary between runs. If a
> `curl` above 404s you don't have to grep for the real path — the running service will tell you.
> Open <http://localhost:8080/swagger-ui.html> and read it off the page, or from a terminal:
>
> ```powershell
> # PowerShell: every path the running service exposes
> (Invoke-RestMethod http://localhost:8080/v3/api-docs).paths.PSObject.Properties.Name
> ```
>
> ```bash
> # bash: the YAML rendering is readable as-is, no jq needed
> curl -s http://localhost:8080/v3/api-docs.yaml
> ```

## Roadmap

**Done ✅**

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
  (Maven build stage → JRE-only Alpine runtime, non-root) plus a `compose.yaml`, so
  `docker compose up --build` serves the endpoint with nothing installed but Docker.
- **PostgreSQL, not an in-memory stand-in** — the service runs against a real PostgreSQL as one
  service in a compose stack, with the schema owned by `schema.sql` and checked at every startup
  by `ddl-auto=validate`. The database tests are Testcontainers `*IT` classes run by failsafe on
  the real engine, so entity/schema drift fails the build instead of the demo.
- **Automated fix loop** — `legacylift verify` takes generated code to verified code unattended:
  classifies the failure (compile / test / mutation), sends a filtered Maven excerpt plus the
  current source back to the agent, applies the fix, re-runs, capped at 3 attempts — with fixes
  that weaken the mutation gate rejected before they reach disk.

**TO-DOs**

- **Regenerate `examples/inventory-service` from the pipeline** — the fixture now conforms to the
  prompt, but it is hand-maintained, so CI verifies a service the generator has not actually been
  observed to produce. A clean `generate` run committed as the fixture would close that gap.
- **Run the generated service on Kubernetes (kind)** — deploy the image with a plain manifest
  first, so the moving parts stay visible before a chart hides them. Done when `kubectl
  port-forward` + `curl` answers from inside the cluster.
- **Generate the Helm chart** — it belongs in `GENERATE_SYSTEM` beside the `Dockerfile` and
  `compose.yaml`: the agent should ship deployable services, not output a human then deploys.
  Self-contained PostgreSQL, actuator probes, one replica. Done when `helm install` serves the
  endpoint.
- **Verify what `mvn verify` cannot see** — nothing checks `compose.yaml` today, and the chart
  will have the same hole: the gate is green whether or not the service can actually deploy. Add
  `docker compose config` and `helm lint` to `legacylift verify`. Done when a broken chart fails
  the gate.
- **Architecture diagram + demo GIF** — a Mermaid diagram of `analyze → generate → verify`, plus
  an asciinema recording of a real pipeline run. Done when the README shows the pipeline instead
  of describing it.
- **Limitations & design decisions** — context-window truncation, what is hand-maintained versus
  generated, why mutation score rather than line coverage, the 3-attempt cap. Done when a senior
  engineer trusts the repo because of what it admits, not despite it.

## Why the quality gates matter

LLMs generate plausible code; mutation testing proves the *tests* actually constrain behavior.
A generated service with 80%+ PIT score is defensibly production-grade in a way "it compiles" is not.
## Author

Vivek Patel — [linkedin.com/in/necrote](https://linkedin.com/in/necrote) · Backend engineer, fintech platform modernization.
