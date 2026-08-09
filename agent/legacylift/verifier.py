"""Run the generated service's quality gate and read its failures back.

Pure subprocess + text handling: no OpenAI calls live here, so the loop's judgement
(cli.py) stays separate from the mechanics of talking to Maven.
"""
import re
import shutil
import subprocess
from pathlib import Path

MVN_ARGS = ["-B", "--no-transfer-progress", "verify"]
DEFAULT_TIMEOUT = 900  # PIT on even a small service is minutes, not seconds
TIMEOUT_RC = 124  # conventional shell exit code for a killed-on-timeout command
TAIL_LINES = 40
MAX_EXCERPT = 24_000

# The mutation gate is the reason this project exists (see CLAUDE.md). An LLM told to
# "make the build pass" can always do so by taking the gate apart, so fixes are checked
# against this floor before they are allowed anywhere near the disk.
MIN_MUTATION_THRESHOLD = 80

# Directories inside the generated service that must never be fed back to the model:
# target/ is ~44 MB of build output (surefire XML alone would blow the corpus cap) and
# .legacylift/ holds our own backups of earlier attempts.
SKIP_DIRS = frozenset({"target", ".legacylift"})


def _text(chunk) -> str:
    """subprocess hands back str in text mode, but bytes on some timeout paths."""
    if isinstance(chunk, bytes):
        return chunk.decode("utf-8", errors="replace")
    return chunk or ""


def preflight(service_dir) -> str:
    """Check the target is buildable and return the mvn to use, or exit saying why not.

    Called before anything is written, so pointing verify at the wrong directory does not
    leave a log or a .legacylift/ behind in it.
    """
    base = Path(service_dir)
    if not (base / "pom.xml").is_file():
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
    return mvn


def run_maven(service_dir, timeout: int = DEFAULT_TIMEOUT) -> tuple[int, str]:
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


def classify(output: str) -> str:
    """Name the failure: compile | test | mutation | unknown."""
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
    r"^\[INFO\] --- "  # goal boundaries: cheap context for where the build got to
)


def distill(output: str, limit: int = MAX_EXCERPT) -> str:
    """Cut a full mvn log down to the parts worth paying tokens for."""
    lines = output.splitlines()
    keep = {i for i, line in enumerate(lines) if _KEEP.search(line)}
    keep |= set(range(max(0, len(lines) - TAIL_LINES), len(lines)))
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


def gate_violations(files: dict[str, str]) -> list[str]:
    """Ways a proposed fix would make the build green by weakening the gate.

    Takes the model's files before they are written; a non-empty result means the fix
    must be rejected rather than applied.
    """
    problems = []
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
        elif name.endswith(".java") and _SWITCHED_OFF.search(content):
            problems.append(f"{rel}: a test was switched off with @Disabled/@Ignore")
    return problems
