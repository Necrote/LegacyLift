"""LegacyLift CLI - analyze legacy code, generate a modern Spring Boot service."""
import re
from pathlib import Path

import click
from openai import OpenAI

from . import prompts
from .analyzer import collect_sources

MODEL = "gpt-5"


def _ask(system: str, user: str) -> str:
    client = OpenAI()
    resp = client.chat.completions.create(
        model=MODEL,
        max_completion_tokens=16000,
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
@click.option("-o", "--out", default="MODERNIZATION_PLAN.md", show_default=True)
def analyze(legacy_dir, out):
    """Read legacy source and write a modernization plan."""
    corpus = collect_sources(legacy_dir)
    plan = _ask(prompts.ANALYZE_SYSTEM, corpus)
    Path(out).write_text(plan, encoding="utf-8")
    click.echo(f"wrote {out}")


@main.command()
@click.argument("legacy_dir")
@click.option("-p", "--plan", default="MODERNIZATION_PLAN.md", show_default=True)
@click.option("-o", "--out", default="output/service", show_default=True)
def generate(legacy_dir, plan, out):
    """Generate a Spring Boot service from the plan + legacy source."""
    corpus = collect_sources(legacy_dir)
    plan_text = Path(plan).read_text(encoding="utf-8")
    raw = _ask(
        prompts.GENERATE_SYSTEM,
        f"# MODERNIZATION PLAN\n{plan_text}\n\n# LEGACY SOURCE\n{corpus}",
    )
    n = 0
    for m in re.finditer(r"===FILE: (.+?)===\n(.*?)(?====FILE: |\Z)", raw, re.DOTALL):
        rel, content = m.group(1).strip(), m.group(2).strip()
        # The model sometimes wraps a file in a markdown code fence; strip a
        # leading ```lang line and a trailing ``` so they don't reach disk.
        content = re.sub(r"\A```[^\n]*\n", "", content)
        content = re.sub(r"\n```\s*\Z", "", content)
        content = content.strip() + "\n"
        dest = Path(out) / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(content, encoding="utf-8")
        n += 1
    click.echo(f"wrote {n} files to {out}")
    click.echo("next: cd there and run  mvn verify  (tests + PIT gate)")


if __name__ == "__main__":
    main()
