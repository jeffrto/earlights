import click


@click.group()
@click.version_option(package_name="earlights", prog_name="earlights")
def main() -> None:
    """Turn Audible bookmarks into text highlights."""
