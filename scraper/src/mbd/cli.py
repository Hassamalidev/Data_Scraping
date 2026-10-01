import logging
import shutil
from typing import Annotated

import typer

from mbd import __version__
from mbd.config import REPO_ROOT, get_settings
from mbd.fetch import FetchError, PoliteClient, RobotsDisallowedError

FIXTURES_DIR = REPO_ROOT / "scraper" / "tests" / "fixtures"

app = typer.Typer(
    name="mbd",
    help="Scraper/ETL worker for the Canadian Halal & Muslim-Owned Business Directory.",
    no_args_is_help=True,
)


@app.callback()
def main(verbose: Annotated[bool, typer.Option("--verbose", "-v")] = False) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)


@app.command()
def version() -> None:
    """Print the installed mbd version."""
    typer.echo(__version__)


@app.command()
def inspect(
    url: str,
    source_id: Annotated[
        str, typer.Option("--source", help="Source id the page belongs to, e.g. jaffari_dir.")
    ],
    fixture: Annotated[
        str | None,
        typer.Option(help="Also save the body as tests/fixtures/<source>/<name>."),
    ] = None,
) -> None:
    """Fetch one URL politely and report what came back (source inspection)."""
    with PoliteClient.from_settings(get_settings()) as client:
        try:
            result = client.get(url, source_id=source_id, conditional=False)
        except RobotsDisallowedError:
            typer.echo(f"robots.txt: DISALLOWED for our User-Agent -> {url}")
            raise typer.Exit(code=2) from None
        except FetchError as exc:
            typer.echo(f"fetch failed: {exc}")
            raise typer.Exit(code=1) from None

    typer.echo("robots.txt: allowed")
    typer.echo(f"final url:  {result.url}")
    typer.echo(f"status:     {result.status_code}")
    typer.echo(f"type:       {result.headers.get('content-type', '?')}")
    typer.echo(f"size:       {result.raw_path.stat().st_size} bytes")
    typer.echo(f"etag:       {result.headers.get('etag', '-')}")
    typer.echo(f"modified:   {result.headers.get('last-modified', '-')}")
    typer.echo(f"raw copy:   {result.raw_path}")
    if fixture:
        target = FIXTURES_DIR / source_id / fixture
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(result.raw_path, target)
        typer.echo(f"fixture:    {target}")


@app.command()
def worker() -> None:
    """Run the scheduler and job listener (arrives in Phase 6)."""
    typer.echo("mbd worker is not implemented yet (CLAUDE.md Phase 6).", err=True)
    raise typer.Exit(code=1)


if __name__ == "__main__":
    app()
