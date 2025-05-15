import asyncio
from typing import List, Optional
import typer

from config.config_manager import ConfigManager, ConfigError
from parsers.parser_factory import ParserFactory
from utils.scraper_generator import generate_scraper as _generate_scraper_template
import parsers.implementations  # noqa: F401
from core.exceptions import UnknownParserError
from core.base_scraper import BaseScraper

app = typer.Typer(help="Web Scraper with configurable settings")


def _get_urls_from_file(file_path: str) -> List[str]:
    """Reads URLs from a file, one per line."""
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            return [line.strip() for line in f if line.strip()]
    except FileNotFoundError:
        typer.echo(f"Error: URLs file not found at '{file_path}'", err=True)
        raise typer.Exit(1)
    except Exception as e:
        typer.echo(f"Error reading URLs file '{file_path}': {e}", err=True)
        raise typer.Exit(1)

def _gather_urls(urls: Optional[List[str]], urls_file: Optional[str]) -> List[str]:
    """Collects URLs from commandline arguments and/or a file."""
    gathered_urls: List[str] = []
    if urls:
        gathered_urls.extend(urls)
    if urls_file:
        gathered_urls.extend(_get_urls_from_file(urls_file))
    if not gathered_urls:
        typer.echo("Error: No URLs provided. Use --urls or --urls-file.", err=True)
        raise typer.Exit(1)
    return gathered_urls

def _configure_scraper(
    parser_name: str,
    output_type_cli: Optional[str],
    concurrency_cli: Optional[int]
) -> ConfigManager:
    """Initializes and configures the ConfigManager based on parser name and CLI args."""
    try:
        cfg = ConfigManager(shop_name=parser_name)

        # Apply CLI overrides and finalize settings
        cfg.finalize_runtime_settings(
            output_type_cli=output_type_cli,
            concurrency_cli=concurrency_cli
        )

        return cfg

    except (FileNotFoundError, ConfigError, ValueError) as e:
        # Catch specific errors from ConfigManager and finalize_runtime_settings
        typer.echo(f"Error during configuration: {e}", err=True)
        raise typer.Exit(1)
    except Exception as e:
        typer.echo(f"Unexpected error during configuration: {e}", err=True)
        raise typer.Exit(1)

def _initialize_scraper(parser_name: str, cfg: ConfigManager) -> BaseScraper:
    """Initializes the scraper using the factory."""
    try:
        scraper = ParserFactory.get_parser(parser_name, cfg)
        return scraper
    except UnknownParserError as exc:
        typer.echo(f"Unknown parser error: {exc}", err=True)
        raise typer.Exit(1)
    except Exception as e:
        typer.echo(f"An unexpected error occurred during scraper initialization: {e}", err=True)
        raise typer.Exit(1)

async def _run_scrape_process(scraper: BaseScraper, urls: List[str]):
    """Runs the main scraping process and saves results."""
    # Access storage config through scraper.config_manager
    storage_config = scraper.config_manager.config.storage
    output_file = storage_config.output_file
    
    if not output_file:
        scraper.logger.error(f"Output file name was missing in config, falling back to {output_file}")
        raise ConfigError("Output file name not specified in configuration")

    try:
        async with scraper:
            scraper.logger.info(f"Starting scrape process for {len(urls)} URLs.")
            await scraper.scrape_urls(urls)
            scraper.logger.info(f"Scraping finished. Found {len(scraper.results)} potential items.")
            await scraper.save_results(output_file=output_file)
            items_saved_count = getattr(scraper.storage, '_items_saved_count', len(scraper.results))
            typer.echo(f"Scraping completed. {items_saved_count} items saved to {output_file}")
            scraper.logger.info(f"Results saved to {output_file}")
    except Exception as e:
        scraper.logger.exception("An error occurred during the scraping execution.")
        typer.echo(f"An unexpected error occurred during scraping execution: {e}", err=True)


@app.command()
def list_parsers() -> None:
    """Prints available parsers and their descriptions."""
    parsers = ParserFactory.list_parsers()
    if not parsers:
        typer.echo("No parsers available.")
        return
    typer.echo("Available parsers:")
    for name, descr in parsers.items():
        typer.echo(f"- {name}: {descr}")

@app.command()
def generate_scraper(
    shop_name: str = typer.Option(..., help="Shop name in snake_case (e.g., my_shop)"),
    description: str = typer.Option(..., help="Human-readable description (e.g., 'Scraper for My Shop')"),
):
    """Generates a new scraper template file and configuration."""
    try:
        _generate_scraper_template(shop_name, description)
        typer.echo(f"Scraper template '{shop_name}' successfully generated.")
    except Exception as e:
        typer.echo(f"Error generating scraper template: {e}", err=True)
        raise typer.Exit(1)

@app.command()
def scrape(
    parser: str = typer.Option(..., "--parser", "-p", help="Parser name to use (see list-parsers)"),
    urls: Optional[List[str]] = typer.Option(None, "--urls", "-u", help="Direct URLs to scrape (repeatable)"),
    urls_file: Optional[str] = typer.Option(None, "--urls-file", "-f", help="File containing URLs (one per line)"),
    output_type: Optional[str] = typer.Option(None, "--output-type", "-t", help="Force storage type (csv or json)"),
    concurrency: Optional[int] = typer.Option(None, "--concurrency", help="Concurrency limit override"),
):
    """Runs the specified scraper for the given URLs."""
    try:
        # 1. Configure Scraper
        cfg = _configure_scraper(parser, output_type, concurrency)
        
        # 2. Gather URLs
        gathered_urls = _gather_urls(urls, urls_file)
        typer.echo(f"Collected {len(gathered_urls)} URLs to scrape.")

        # 3. Initialize Scraper
        scraper_instance = _initialize_scraper(parser, cfg)
        typer.echo(f"Scraper '{parser}' initialized successfully.")

        # 4. Run Scraping Process
        asyncio.run(_run_scrape_process(scraper_instance, gathered_urls))
        typer.echo("Scrape command finished successfully.")

    except typer.Exit:
        raise
    except Exception as e:
        typer.echo(f"Scraping process failed with an unexpected error: {e}", err=True)
        raise typer.Exit(1)


if __name__ == "__main__":
    app()
