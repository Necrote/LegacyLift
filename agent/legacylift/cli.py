"""LegacyLift CLI - analyze legacy code, generate a modern Spring Boot service."""
import os
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path

import click
from openai import OpenAI

from . import config, prompts, verifier
from .analyzer import collect_sources

# The delimiter the prompts tell the model to emit and the parser below are one contract:
# change either and you must change the other.
FILE_BLOCK = re.compile(r"===FILE: (.+?)===\n(.*?)(?====FILE: |\Z)", re.DOTALL)


def _parse_files(raw: str) -> dict[str, str]:
    """Pull ===FILE: <path>=== blocks out of a model response."""
    files = {}
    for m in FILE_BLOCK.finditer(raw):
        rel, content = m.group(1).strip(), m.group(2).strip()
        # The model sometimes wraps a file in a markdown code fence; strip a
        # leading ```lang line and a trailing ``` so they don't reach disk.
        content = re.sub(r"\A```[^\n]*\n", "", content)
        content = re.sub(r"\n```\s*\Z", "", content)
        files[rel] = content.strip() + "\n"
    return files


def _write_files(files: dict[str, str], out) -> list[str]:
    base = Path(out).resolve()
    for rel, content in files.items():
        dest = (base / rel).resolve()
        # The paths come from the model, so keep a stray `../` or an absolute path from
        # writing outside the tree the caller asked us to fill.
        if not dest.is_relative_to(base):
            raise SystemExit(f"refusing to write {rel}: it escapes {out}")
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(content, encoding="utf-8")
    return list(files)


def _ask(system: str, user: str) -> str:
    # verify runs unattended and only reaches here after a multi-minute build, so say what
    # is missing rather than letting the SDK raise from inside the loop.
    if not os.environ.get("OPENAI_API_KEY"):
        raise SystemExit(
            "OPENAI_API_KEY is not set, so the agent cannot be asked for anything.\n"
            'PowerShell: $env:OPENAI_API_KEY = "sk-..."   bash: export OPENAI_API_KEY=sk-...'
        )
    client = OpenAI()
    resp = client.chat.completions.create(
        model=config.MODEL,
        max_completion_tokens=config.MAX_TOKENS,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    )
    return resp.choices[0].message.content or ""


@click.group()
def main():
    """Agentic legacy -> Spring Boot modernization."""


@main.command()
@click.argument("legacy_dir")
@click.option("-o", "--out", default=config.PLAN_FILE, show_default=True)
def analyze(legacy_dir, out):
    """Read legacy source and write a modernization plan."""
    corpus = collect_sources(legacy_dir)
    plan = _ask(prompts.ANALYZE_SYSTEM, corpus)
    Path(out).write_text(plan, encoding="utf-8")
    click.echo(f"wrote {out}")


@main.command()
@click.argument("legacy_dir")
@click.option("-p", "--plan", default=config.PLAN_FILE, show_default=True)
@click.option("-o", "--out", default=config.OUTPUT_DIR, show_default=True)
def generate(legacy_dir, plan, out):
    """Generate a Spring Boot service from the plan + legacy source."""
    corpus = collect_sources(legacy_dir)
    plan_text = Path(plan).read_text(encoding="utf-8")
    raw = _ask(
        prompts.GENERATE_SYSTEM,
        f"# MODERNIZATION PLAN\n{plan_text}\n\n# LEGACY SOURCE\n{corpus}",
    )
    written = _write_files(_parse_files(raw), out)
    click.echo(f"wrote {len(written)} files to {out}")
    click.echo(f"next: run  legacylift verify {out}  (mvn verify + automated fixes)")


def _log(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(text + "\n")


def _backup(files, svc: Path, attempt: int) -> Path:
    """Copy the files a fix is about to overwrite, so a bad fix is never the only copy."""
    root = svc / config.WORK_DIR / f"attempt-{attempt}"
    for rel in files:
        src = svc / rel
        if src.is_file():
            dest = root / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dest)
    return root


@main.command()
@click.argument("service_dir")
@click.option("-n", "--max-iterations", default=config.MAX_ITERATIONS, show_default=True,
              help="Maximum fix attempts; mvn verify runs once more after each.")
@click.option("--legacy", default=None,
              help="Legacy source dir, included so fixes can consult the original business rules.")
@click.option("--timeout", default=config.MVN_TIMEOUT, show_default=True,
              help="Seconds to allow one mvn verify run.")
def verify(service_dir, max_iterations, legacy, timeout):
    """Run mvn verify, feed failures back to the agent, retry (capped)."""
    svc = Path(service_dir)
    verifier.preflight(svc)  # before the log below, so a wrong path leaves nothing behind
    log = svc / config.WORK_DIR / config.LOG_NAME
    started = datetime.now(timezone.utc).isoformat(timespec="seconds")
    _log(log, f"\n===== legacylift verify {service_dir} @ {started} "
              f"(max {max_iterations} fixes) =====")

    rc, output = verifier.run_maven(svc, timeout=timeout)
    attempt = 0
    while rc != 0:
        kind = verifier.classify(output)
        why = verifier.headline(output, kind)
        excerpt = verifier.distill(output)
        click.echo(f"  mvn verify FAILED (exit {rc}, {kind}): {why}")
        _log(log, f"\n--- verify #{attempt + 1}: exit {rc}, {kind}: {why}\n{excerpt}")

        # No edit to the service can fix a missing Docker daemon, so stop rather than spend
        # attempts (and model calls) rewriting code over an environment problem. Checked here
        # because FIX_HINTS has no entry for this kind - indexing it would raise KeyError.
        if kind == "environment":
            click.echo("  the integration tests need a running Docker daemon - "
                       "start Docker and re-run. Nothing was changed.")
            _log(log, "--- stopped: environment failure, no fix attempted")
            break

        if attempt >= max_iterations:
            break
        attempt += 1
        click.echo(f"  fix attempt {attempt}/{max_iterations}: asking {config.MODEL} ...")

        request = [
            f"# BUILD FAILURE ({kind})", why, "",
            "# MAVEN OUTPUT (filtered)", excerpt, "",
            "# CURRENT SERVICE SOURCE",
            collect_sources(svc, exclude_dirs=config.SKIP_DIRS),
        ]
        if legacy:
            request += ["", "# ORIGINAL LEGACY SOURCE", collect_sources(legacy)]
        raw = _ask(prompts.FIX_SYSTEM + prompts.FIX_HINTS[kind], "\n".join(request))

        files = _parse_files(raw)
        if not files:
            click.echo("  the agent proposed no file changes - stopping.")
            _log(log, f"--- fix {attempt}: no files proposed. Model said:\n{raw.strip()[:2000]}")
            break

        # Reject before writing: a fix that passes by dismantling the gate is not a fix.
        violations = verifier.gate_violations(files, svc)
        if violations:
            click.echo("  REJECTED - the proposed fix weakens the quality gate:")
            for v in violations:
                click.echo(f"    - {v}")
            _log(log, f"--- fix {attempt}: REJECTED, not written: {'; '.join(violations)}")
            raise SystemExit(
                "Nothing was written. The mutation gate is the point of this service, so a fix "
                "that removes it is discarded rather than applied."
            )

        backup = _backup(files, svc, attempt)
        _write_files(files, svc)
        click.echo(f"  rewrote {len(files)} file(s): {', '.join(sorted(files))}")
        _log(log, f"--- fix {attempt}: rewrote {len(files)} file(s) "
                  f"(originals in {backup}): {', '.join(sorted(files))}")

        rc, output = verifier.run_maven(svc, timeout=timeout)

    if rc == 0:
        done = f"VERIFIED after {attempt} fix attempt(s) - mvn verify green, PIT gate held."
        click.echo(done)
        _log(log, done)
        return

    kind = verifier.classify(output)
    failed = (f"FAILED after {attempt} fix attempt(s) - last failure ({kind}): "
              f"{verifier.headline(output, kind)}")
    _log(log, failed)
    click.echo(f"\n{failed}")
    click.echo(f"The last attempt is left in {svc}; earlier versions of each rewritten file are "
               f"in {svc / config.WORK_DIR}. Full log: {log}")
    raise SystemExit(1)


if __name__ == "__main__":
    main()
