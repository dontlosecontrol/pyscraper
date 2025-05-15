# Kind of Framework for Web Scraping

Goals:
To obtain a medium scalable system while maintaining flexibility (including through extended configuration) for data collection with support for paralleling, proxies.



## Features

- Modular architecture with support for various parsers for different websites
- Asynchronous HTTP client based on AIOHTTP with session management
- Retry system for request errors
- Proxy support with automatic rotation (todo: will be moved to a separate service)
- WIP: Enhanced logging
- Mechanism for saving data in various formats

## Todo:
- improve generate-scraper logic
- Finish integration of Middleware with metrics (they are collected, but not displayed anywhere)
- Implement db_storage
- Simplify the logic of writing the parsers by creating more "helpers" and extend core/base_scraper.py with new functionality

## Project Architecture

```
scraper_project/
├── cli.py                 # Command-line interface
├── config/                # Configurations and config manager
│   ├── config_manager.py  # Configuration manager
│   ├── parsers_config.yaml # Main file for parser-specific settings
│   ├── config_models.py   # Pydantic models for configuration
│   └── ...
├── core/                  # System core
│   ├── base_scraper.py    # Base class for all scrapers
│   ├── data_models.py     # Data models
│   ├── exceptions.py      # Exceptions
│   └── ...
├── infrastructure/        # Infrastructure components
│   ├── http_client.py     # HTTP client
│   ├── proxy_manager.py   # Proxy management
│   ├── metrics.py         # Metrics collection # deprecated
│   ├── storage/           # Storage subsystem
│   │   ├── base_storage.py
│   │   ├── csv_storage.py
│   │   └── ...
│   └── ...
├── parsers/               # Parser implementations and templates
│   ├── parser_factory.py  # Parser factory
│   ├── implementations/   # Specific parser implementations
│   │   ├── knifecenter_parser.py
│   │   └── ...
│   └── templates/         # Templates for auto-generation
│       └── scraper_template.py
├── tests/                 # Tests, grouped by modules
│
├── utils/                 # Utilities
│   ├── logger_factory.py  # Logger factory
│   ├── retry_utils.py     # Decorator for retries (deprecated)
│   ├── html_utils.py      # HTML utilities
│   └── ...
└── README.md
```

## Installation

1. Clone the repository:
```bash
git clone git@github.com:dontlosecontrol/pyscraper.git
cd scraper_project
```

2. Create and activate a virtual environment:
```bash
python -m venv venv
source venv/bin/activate  # for Linux/Mac
# or
venv\Scripts\activate  # for Windows
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

## Usage

### Via Command Line

```bash
# List available parsers
python cli.py list-parsers

# Run a scraper for a specific site, saving results to CSV
# The filename will be generated automatically (e.g., knifecenter_YYYY-MM-DD.csv)
python cli.py scrape --parser knifecenter --urls https://www.knifecenter.com/knives.html --output-type csv

# Use a file with URLs and specify the number of concurrent tasks
python cli.py scrape --parser knifecenter --urls-file urls.txt --concurrency 5
```

### Saving Results in JSON

To save results in JSON format, you can specify the storage type via CLI or in the `config/parsers_config.yaml` configuration file for a specific parser. The output filename will be generated automatically.

Example of specifying in `config/parsers_config.yaml` for the `my_shop` parser:

```yaml
parsers:
  my_shop:
    storage:
      type: "json"
    # output_file will be generated automatically, e.g.: my_shop_YYYY-MM-DD.json
```

Or pass the storage type via CLI:

```bash
python cli.py scrape --parser knifecenter --urls https://example.com/category --output-type json
```

Results will be saved to an automatically generated file (e.g., `knifecenter_YYYY-MM-DD.json`) in JSON format.

## Creating Your Own Parser

### Quick Way: Auto-generation via CLI

You can automatically generate a template for a new scraper and register it in the system with a single command:

```bash
python cli.py generate-scraper --shop-name my_shop --description "Parser for My Shop"
```

- A file `parsers/implementations/my_shop_parser.py` will be created based on the template.
- The parser is automatically registered in the system via a decorator.
- You will need to implement the parsing logic in the generated file and, if necessary, add or update the configuration for your parser in the `config/parsers_config.yaml` file.

**Registration Decorator Example:**
```python
@register_parser_decorator('my_shop', 'Parser for My Shop')
class MyShopScraper(BaseScraper):
    ...
```

**Next Steps:**
1. Implement the parser methods in the generated file.
2. (Recommended) If necessary, add or update specific settings for your parser in the `config/parsers_config.yaml` file (e.g., `base_url`, selectors, etc.).

**Example:** [parsers/implementations/knifecenter_parser.py](parsers/implementations/knifecenter_parser.py)

### Alternative Way: Manually

1. Create or update the section for your parser in the `config/parsers_config.yaml` file. This file is used to override default settings or add parser-specific parameters (e.g., `user_agent`, `delay`, even XPaths, etc.).

```yaml
parsers:
  # ...other parsers...
  my_shop:
    # Specific configuration for My Shop
    user_agent: "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/91.0.4472.124 Safari/537.36"
    concurrency: 3
    timeout: 20
    # sessions_count, retries_count, and other parameters from ScraperConfig can be overridden here
    # You can also add custom parameters that your parser will read
    # e.g.: base_url: "https://my.shop.com"
```

2. Create a parser class in the `parsers/implementations/` directory (e.g., `my_shop_parser.py`):

```python
from parsers.parser_factory import register_parser_decorator

@register_parser_decorator('my_shop', 'Parser for My Shop')
class MyShopScraper(BaseScraper):
    ...
```

3. Implement the parser methods.

4. Ensure that all necessary configurations for your parser are present in `config/parsers_config.yaml` or that default values from `ScraperConfig` are correctly processed.

---

## License

MIT
