import typer

from mbd import __version__

app = typer.Typer(
    name="mbd",
    help="Scraper/ETL worker for the Canadian Halal & Muslim-Owned Business Directory.",
    no_args_is_help=True,
)


@app.command()
def version() -> None:
    """Print the installed mbd version."""
    typer.echo(__version__)


@app.command()
def worker() -> None:
    """Run the scheduler and job listener (arrives in Phase 6)."""
    typer.echo("mbd worker is not implemented yet (CLAUDE.md Phase 6).", err=True)
    raise typer.Exit(code=1)


if __name__ == "__main__":
    app()
