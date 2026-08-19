"""Run the generated service's quality gate and read its failures back.

Pure subprocess + text handling: no OpenAI calls live here, so the loop's judgement
(cli.py) stays separate from the mechanics of talking to Maven.
"""
import re
import shutil
import subprocess
from pathlib import Path

from .config import (
    DOCKER_TIMEOUT,
    EXCERPT_CHARS,
    EXCERPT_TAIL_LINES,
    MIN_MUTATION_THRESHOLD,
    MVN_ARGS,
    MVN_TIMEOUT,
    TIMEOUT_RC,
)


def _text(chunk) -> str:
    """subprocess hands back str in text mode, but bytes on some timeout paths."""
    if isinstance(chunk, bytes):
        return chunk.decode("utf-8", errors="replace")
    return chunk or ""


def preflight(service_dir) -> str:
    """Check the target is buildable and return the mvn to use, or exit saying why not.

    Checks a pom.xml, `mvn`, and - only for a service whose tests use Testcontainers - a
    reachable Docker daemon. Called before anything is written, so pointing verify at the
    wrong directory does not leave a log or a work directory behind in it.
    """
    base = Path(service_dir)
    pom = base / "pom.xml"
    if not pom.is_file():
        raise SystemExit(
            f"{service_dir} has no pom.xml (resolved to {base.resolve()}).\n"
            f"Point verify at the generated service directory, e.g. output/inventory-service."
        )
    # On Windows the executable is mvn.cmd, so the bare string "mvn" would not resolve;
    # which() finds the real target and gives us a clear error instead of FileNotFoundError.
    mvn = shutil.which("mvn")
    if mvn is None:
        raise SystemExit(
            "mvn is not on PATH, so the quality gate cannot run.\n"
            "Install Maven 3.9+ and a JDK 21 (the generated pom targets Java 21), then re-run."
        )
    # Conditional on purpose: a service with no Testcontainers tests verifies fine without
    # Docker, and demanding it would break those runs for nothing.
    if "testcontainers" in pom.read_text(encoding="utf-8", errors="replace").lower():
        _require_docker()
    return mvn


def _require_docker() -> None:
    """Exit unless a Docker daemon is reachable.

    Without this a stopped Docker Desktop surfaces as a plain test failure, and the fix loop
    spends its three attempts - and three model calls - rewriting code to solve a problem
    that is not in the code.
    """
    hint = (
        "The integration tests (*IT) start a PostgreSQL container, so `mvn verify` needs a\n"
        "running Docker daemon. Start Docker Desktop (or dockerd) and re-run."
    )
    docker = shutil.which("docker")
    if docker is None:
        raise SystemExit(f"docker is not on PATH.\n{hint}")
    try:
        proc = subprocess.run(
            [docker, "info"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=DOCKER_TIMEOUT,
            check=False,
        )
    except subprocess.TimeoutExpired:
        raise SystemExit(
            f"`docker info` did not answer within {DOCKER_TIMEOUT}s.\n{hint}"
        ) from None
    if proc.returncode != 0:
        raise SystemExit(f"`docker info` failed:\n{proc.stderr.strip()[:500]}\n{hint}")


def run_maven(service_dir, timeout: int = MVN_TIMEOUT) -> tuple[int, str]:
    """Run `mvn verify` in service_dir. Returns (exit code, combined output)."""
    base = Path(service_dir)
    mvn = preflight(base)
    try:
        proc = subprocess.run(
            [mvn, *MVN_ARGS],
            cwd=base,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            check=False,  # a failing build is the normal case here, not an exception
        )
    except subprocess.TimeoutExpired as exc:
        killed = _text(exc.stdout) + _text(exc.stderr)
        return TIMEOUT_RC, f"{killed}\n[legacylift] mvn verify exceeded {timeout}s and was killed."
    return proc.returncode, _text(proc.stdout) + _text(proc.stderr)


# Which plugin Maven died in is the most reliable signal of what actually broke; the
# text markers below are only a fallback for output that lacks the summary line.
_GOAL_KINDS = (
    ("maven-compiler-plugin", "compile"),
    ("maven-surefire-plugin", "test"),
    ("maven-failsafe-plugin", "test"),
    ("pitest-maven", "mutation"),
)


# Testcontainers could not reach a Docker daemon or fetch an image. No edit to the service
# fixes this, so it is classified apart from a real test failure and never sent to the model.
_ENVIRONMENT = re.compile(
    r"Could not find a valid Docker environment|Cannot connect to the Docker daemon|"
    r"Can't get Docker image|DockerClientProviderStrategy"
)


def classify(output: str) -> str:
    """Name the failure: compile | test | mutation | environment | unknown."""
    # Checked before the goal table: a Docker outage surfaces as a failsafe/surefire failure,
    # which would otherwise be reported as a broken test.
    if _ENVIRONMENT.search(output):
        return "environment"
    goal = re.search(r"Failed to execute goal (\S+)", output)
    if goal:
        for needle, kind in _GOAL_KINDS:
            if needle in goal.group(1):
                return kind
    if "COMPILATION ERROR" in output:
        return "compile"
    if "There are test failures" in output or re.search(r"Tests run:.*Failures: [1-9]", output):
        return "test"
    if "below threshold" in output:
        return "mutation"
    return "unknown"


def headline(output: str, kind: str) -> str:
    """One line naming the failure, for the console and the log."""
    if kind == "environment":
        m = _ENVIRONMENT.search(output)
        if m:
            return f"{m.group(0)} - Docker is not usable from this build"
    if kind == "mutation":
        m = re.search(r"Mutation score of \d+ is below threshold of \d+", output)
        if m:
            return m.group(0)
    elif kind == "test":
        m = re.search(r"Tests run: .*?Failures: \d+, Errors: \d+[^\n]*", output)
        if m:
            return m.group(0).strip()
    elif kind == "compile":
        # The first [ERROR] of a compile failure is the banner "COMPILATION ERROR :";
        # the line naming a file is the one worth reporting.
        m = re.search(r"^\[ERROR\].*\.java:\[[^\n]*", output, re.MULTILINE)
        if m:
            return m.group(0).removeprefix("[ERROR]").strip()
    m = re.search(r"^\[ERROR\]\s+(\S[^\n]*)", output, re.MULTILINE)
    if m:
        return m.group(1).strip()[:200]
    return f"{kind} failure (no [ERROR] line in the output)"


_KEEP = re.compile(
    r"\[ERROR\]|\[FATAL\]|COMPILATION ERROR|Tests run:|BUILD FAILURE|"
    r"Failed to execute goal|below threshold|mutations? (?:killed|survived)|"
    r"Could not find a valid Docker environment|Can't get Docker image|"
    r"^\[INFO\] --- "  # goal boundaries: cheap context for where the build got to
)


def distill(output: str, limit: int = EXCERPT_CHARS) -> str:
    """Cut a full mvn log down to the parts worth paying tokens for."""
    lines = output.splitlines()
    keep = {i for i, line in enumerate(lines) if _KEEP.search(line)}
    keep |= set(range(max(0, len(lines) - EXCERPT_TAIL_LINES), len(lines)))
    picked, prev = [], None
    for i in sorted(keep):
        if prev is not None and i > prev + 1:
            picked.append(f"    ... {i - prev - 1} lines omitted ...")
        picked.append(lines[i])
        prev = i
    excerpt = "\n".join(picked)
    if len(excerpt) > limit:
        head, tail = excerpt[: limit // 3], excerpt[-(2 * limit // 3):]
        excerpt = f"{head}\n... TRUNCATED to {limit} chars ...\n{tail}"
    return excerpt


_THRESHOLD = re.compile(r"<mutationThreshold>\s*(\d+)\s*</mutationThreshold>")
_SWITCHED_OFF = re.compile(r"^\s*@(?:Disabled|Ignore)\b", re.MULTILINE)

# Skip flags that turn the gate off from inside the pom. Each is a real plugin/user property:
# <skipPitest>true</skipPitest> in a <properties> block is enough to make `mvn verify` green
# without running a single mutant, and MVN_ARGS is frozen so no command-line flag can undo it.
_SKIPS = re.compile(
    r"<(skipPitest|skipTests|skipITs|maven\.test\.skip|testFailureIgnore)>\s*true\s*</\1>",
    re.IGNORECASE,
)
# Shrinking what PIT measures raises the score without improving any test.
_NARROWERS = ("<excludedClasses>", "<excludedMethods>")
_EXCLUDED_TESTS = re.compile(r"<excludedTestClasses>(.*?)</excludedTestClasses>", re.DOTALL)
_PARAM = re.compile(r"<param>\s*(.*?)\s*</param>", re.DOTALL)
_TESTCONTAINERS = re.compile(r"\borg\.testcontainers\b")


def gate_violations(files: dict[str, str], service_dir=None) -> list[str]:
    """Ways a proposed fix would make the build green by weakening the gate.

    Takes the model's files before they are written; a non-empty result means the fix
    must be rejected rather than applied.

    `service_dir` supplies the on-disk pom for the checks that are about REMOVAL. Those
    have to be relative: generation is stochastic, so a service that never had (say) a
    failsafe plugin must not have every later pom fix rejected as "you deleted it".
    """
    problems = []
    current_pom = ""
    if service_dir is not None:
        pom = Path(service_dir) / "pom.xml"
        if pom.is_file():
            current_pom = pom.read_text(encoding="utf-8", errors="replace")

    for rel, content in files.items():
        name = rel.replace("\\", "/")
        if name.endswith("pom.xml"):
            found = _THRESHOLD.search(content)
            if not found:
                problems.append(f"{rel}: <mutationThreshold> was removed")
            elif int(found.group(1)) < MIN_MUTATION_THRESHOLD:
                problems.append(
                    f"{rel}: <mutationThreshold> lowered to {found.group(1)} "
                    f"(the gate requires at least {MIN_MUTATION_THRESHOLD})"
                )
            if "mutationCoverage" not in content or "<phase>verify</phase>" not in content:
                problems.append(f"{rel}: pitest is no longer bound to the verify phase")
            if "pitest-junit5-plugin" not in content:
                problems.append(f"{rel}: the pitest-junit5-plugin dependency was removed")
            for skip in _SKIPS.finditer(content):
                problems.append(f"{rel}: <{skip.group(1)}> was set to true, which skips the gate")
            for tag in _NARROWERS:
                if tag in content and tag not in current_pom:
                    problems.append(
                        f"{rel}: {tag} was added, shrinking what PIT measures"
                    )
            # Only *IT may be kept out of the mutation run - that is the failsafe split.
            # Anything else here is a real test class quietly dropped from the gate.
            for block in _EXCLUDED_TESTS.findall(content):
                for param in _PARAM.findall(block):
                    if not param.endswith("IT"):
                        problems.append(
                            f"{rel}: <excludedTestClasses> excludes {param!r}, which is not an "
                            f"*IT pattern"
                        )
            if "maven-failsafe-plugin" in current_pom and "maven-failsafe-plugin" not in content:
                problems.append(
                    f"{rel}: the maven-failsafe-plugin was removed, so no *IT would run"
                )
        elif name.endswith(".java"):
            if _SWITCHED_OFF.search(content):
                problems.append(f"{rel}: a test was switched off with @Disabled/@Ignore")
            # A container-backed test named *Test runs under surefire with no container, and
            # lands inside the mutation gate. Renaming an IT is the easiest way to "fix" one.
            if _TESTCONTAINERS.search(content) and not name.endswith("IT.java"):
                problems.append(
                    f"{rel}: uses Testcontainers but is not named *IT, so it would run under "
                    f"surefire and inside the mutation gate"
                )
    return problems
