"""Output and error conventions shared by the public command groups."""

import json
from contextlib import contextmanager
from enum import Enum
from pathlib import Path

import typer

from fane.shared.errors import FaneError


class ConversionFormat(str, Enum):
    beancount = "beancount"
    json = "json"
    jsonl = "jsonl"
    legacy_json = "legacy-json"


def output_text(content: str, output: str = "-") -> None:
    if output == "-":
        typer.echo(content, nl=not content.endswith("\n"))
    else:
        target = Path(output).expanduser()
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            content if content.endswith("\n") else content + "\n", encoding="utf-8"
        )


def output_json(value, output: str = "-") -> None:
    output_text(json.dumps(value, ensure_ascii=False, indent=2), output)


@contextmanager
def command_errors(label: str, *, code: int = 1, json_error: bool = False):
    try:
        yield
    except typer.Exit:
        raise
    except (FaneError, ValueError, OSError, RuntimeError) as error:
        if json_error:
            typer.echo(
                json.dumps(
                    {"status": "rejected", "error": str(error)}, ensure_ascii=False
                ),
                err=True,
            )
        else:
            typer.echo(f"{label}: {error}", err=True)
        raise typer.Exit(code) from error
