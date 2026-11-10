import sys

import click

from .audible import AudibleError, list_library


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
