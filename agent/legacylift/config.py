"""Every tunable value in LegacyLift, in one place.

Settings in the TUNABLE sections read an optional `LEGACYLIFT_*` environment variable, so a
run can be re-pointed without editing code:

    PowerShell:  $env:LEGACYLIFT_MODEL = "gpt-5-mini"
    bash:        LEGACYLIFT_MODEL=gpt-5-mini legacylift generate samples/legacy-inventory

The INVARIANTS section at the bottom is deliberately NOT overridable - see the note there.
"""
import os

ENV_PREFIX = "LEGACYLIFT_"


def _str(name: str, default: str) -> str:
    return os.environ.get(ENV_PREFIX + name, default)


def _int(name: str, default: int) -> int:
    raw = os.environ.get(ENV_PREFIX + name)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError:
        # Config read at import time, so a typo would otherwise surface as a confusing
        # traceback from whichever module happened to touch the value first.
        raise SystemExit(
            f"{ENV_PREFIX}{name}={raw!r} is not a whole number (default is {default})."
        ) from None


def _exts(name: str, default: frozenset[str]) -> frozenset[str]:
    raw = os.environ.get(ENV_PREFIX + name)
    if raw is None:
        return default
    # Accept ".java,.sql" or "java sql" and normalize both to {".java", ".sql"}.
    parts = [p.strip() for p in raw.replace(",", " ").split()]
    return frozenset("." + p.lstrip(".") for p in parts if p.strip("."))


def _names(name: str, default: frozenset[str]) -> frozenset[str]:
    """Like _exts, but for whole filenames - no leading dot is added or stripped.

    Kept separate because these entries are matched against Path.name: running "Dockerfile"
    through _exts would turn it into ".Dockerfile" and it would never match anything.
    """
    raw = os.environ.get(ENV_PREFIX + name)
    if raw is None:
        return default
    return frozenset(p.strip() for p in raw.replace(",", " ").split() if p.strip())


# --- TUNABLE: the model ------------------------------------------------------------------
# MODEL is the OpenAI chat model every stage runs on; MAX_TOKENS caps one reply. A full
# service generation is the largest reply, so lowering MAX_TOKENS truncates generate first.
MODEL = _str("MODEL", "gpt-5")
MAX_TOKENS = _int("MAX_TOKENS", 20_000)

# --- TUNABLE: pipeline defaults (each is also a CLI flag) --------------------------------
# Relative to the current directory: analyze writes PLAN_FILE, generate reads it back, so
# both commands must run from the same place (the repo root).
PLAN_FILE = _str("PLAN_FILE", "MODERNIZATION_PLAN.md")
OUTPUT_DIR = _str("OUTPUT_DIR", "output/service")
MAX_ITERATIONS = _int("MAX_ITERATIONS", 3)

# --- TUNABLE: how much source is fed to the model ----------------------------------------
# collect_sources concatenates files with these extensions and stops at MAX_BYTES, which
# bounds context cost. Past the cap it truncates rather than failing.
SOURCE_EXTS = _exts(
    "SOURCE_EXTS",
    frozenset({".java", ".jsp", ".sql", ".xml", ".properties", ".yml", ".yaml"}),
)
# Files the generated service depends on that have no usable suffix: Path("Dockerfile").suffix
# and Path(".dockerignore").suffix are both "", so an extension list can never reach them and
# the fix loop would be asked to repair a service whose container setup it cannot see.
# Matched on the whole filename, so these keep their exact spelling - not run through _exts,
# which would turn "Dockerfile" into ".Dockerfile".
SOURCE_NAMES = _names("SOURCE_NAMES", frozenset({"Dockerfile", ".dockerignore"}))
MAX_BYTES = _int("MAX_BYTES", 400_000)

# --- TUNABLE: the verify loop -------------------------------------------------------------
# PIT on even a small service is minutes, not seconds - and `verify` now also runs the *IT
# classes, whose first run pulls the postgres and ryuk images before a container even starts.
MVN_TIMEOUT = _int("MVN_TIMEOUT", 1_500)
# Just a liveness probe on the Docker daemon (see verifier._require_docker), so this is short
# on purpose: an unresponsive daemon should fail fast, not hold the run open.
DOCKER_TIMEOUT = _int("DOCKER_TIMEOUT", 30)
EXCERPT_CHARS = _int("EXCERPT_CHARS", 24_000)  # cap on the distilled Maven log sent back
EXCERPT_TAIL_LINES = _int("EXCERPT_TAIL_LINES", 40)  # always-kept tail of that log

# Per-service scratch directory holding verify.log and the attempt-N/ backups. Lives inside
# the generated service, which is why SKIP_DIRS below has to know about it.
WORK_DIR = _str("WORK_DIR", ".legacylift")
LOG_NAME = _str("LOG_NAME", "verify.log")
BUILD_DIR = _str("BUILD_DIR", "target")

# Directories that must never be read back into the corpus: Maven's build output (~44 MB,
# and surefire XML alone would blow MAX_BYTES) and our own backups of earlier attempts,
# which would otherwise return as duplicate .java files. Derived so that renaming WORK_DIR
# or BUILD_DIR above cannot silently stop them being excluded.
SKIP_DIRS = frozenset({BUILD_DIR, WORK_DIR})


# --- INVARIANTS: not configurable, on purpose ---------------------------------------------
# The PIT mutation gate is what makes generated code trustworthy (see CLAUDE.md); the fix
# loop already refuses to weaken it from the inside. Reading these from the environment
# would reintroduce that hole from the outside - LEGACYLIFT_MIN_MUTATION_THRESHOLD=0 would
# make gate_violations() toothless, and a settable arg list could smuggle in -DskipTests.
# Change them by editing this file and meaning it.
MIN_MUTATION_THRESHOLD = 80
MVN_ARGS = ["-B", "--no-transfer-progress", "verify"]

TIMEOUT_RC = 124  # conventional shell exit code for a killed-on-timeout command
