import sys
from pathlib import Path

import click

from .audible import AudibleError, list_library
from .audio import AudioError
from .config import ConfigError, load_config
from .deepgram import DeepgramError
from .pipeline import Options, PipelineError, process_book
from .state import StateError

ERRORS = (AudibleError, AudioError, ConfigError, DeepgramError, PipelineError, StateError)


@click.group()
@click.version_option(package_name="earlights", prog_name="earlights")
def main() -> None:
    """Turn Audible bookmarks into text highlights."""


@main.command()
@click.option("--profile", help="audible-cli profile to use.")
def library(profile: str | None) -> None:
    """List the books in your Audible library."""
    try:
        books = list_library(profile)
    except AudibleError as exc:
        click.echo(f"Error: {exc}", err=True)
        sys.exit(1)
    for book in books:
        click.echo(f"{book.asin}  {book.title} — {', '.join(book.authors)}")


@main.command()
@click.argument("book")
@click.option(
    "--mode",
    type=click.Choice(["transcript", "epub", "ai", "auto"]),
    help="How to get the text. Default: transcript, or auto when an EPUB is known.",
)
@click.option("--epub", type=click.Path(path_type=Path), help="EPUB of the same book.")
@click.option("--lang", help="Language code for the transcription, e.g. pt-BR.")
@click.option("--out", type=click.Path(path_type=Path), help="Markdown file to write.")
@click.option("--readwise", is_flag=True, help="Send the highlights to Readwise.")
@click.option("--force", is_flag=True, help="Process every bookmark again.")
@click.option("--profile", help="audible-cli profile to use.")
def process(
    book: str,
    mode: str | None,
    epub: Path | None,
    lang: str | None,
    out: Path | None,
    readwise: bool,
    force: bool,
    profile: str | None,
) -> None:
    """Turn the bookmarks of BOOK (ASIN or part of the title) into a Markdown file."""
    if mode not in (None, "transcript") or epub or readwise:
        raise click.UsageError("not implemented yet: only the transcript mode works for now")
    options = Options(
        mode=mode,
        epub=epub,
        language=lang,
        out=out,
        readwise=readwise,
        force=force,
        profile=profile,
    )
    try:
        path = process_book(book, options, load_config(), click.echo)
    except ERRORS as exc:
        click.echo(f"Error: {exc}", err=True)
        sys.exit(1)
    if path:
        click.echo(f"Wrote {path}")
