import os
from pathlib import Path
import argparse
import re

TEMPLATE_PATH = Path(__file__).parent.parent / 'parsers' / 'templates' / 'scraper_template.py'
IMPLEMENTATIONS_PATH = Path(__file__).parent.parent / 'parsers' / 'implementations'

CLASS_TEMPLATE = 'ExampleShopScraper'
CONFIG_TEMPLATE = 'ExampleShopConfig'


def generate_scraper(shop_name: str, description: str):
    """
    Generates a new scraper file from template
    Args:
        shop_name: Shop name (snake_case)
        description: Human-readable description
    """
    class_name = f"{shop_name.capitalize()}Scraper"
    config_class = f"{shop_name.capitalize()}Config"
    target_file = IMPLEMENTATIONS_PATH / f"{shop_name}_parser.py"

    if target_file.exists():
        raise FileExistsError(f"Scraper for '{shop_name}' already exists: {target_file}")

    with open(TEMPLATE_PATH, 'r', encoding='utf-8') as f:
        content = f.read()

    content = content.replace('{description}', description)
    content = content.replace(CLASS_TEMPLATE, class_name)
    content = content.replace(CONFIG_TEMPLATE, config_class)
    content = content.replace('example_shop', shop_name)
    content = content.replace('ExampleShop', shop_name.capitalize())
    content = re.sub(
        r"@register_parser_decorator\(['\"]example_shop['\"], ['\"]\{description\}['\"]\)",
        f"@register_parser_decorator('{shop_name}', '{description}')",
        content
    )
    content = f'"""\n{description}\n"""\n' + content

    with open(target_file, 'w', encoding='utf-8') as f:
        f.write(content)
    print(f"Scraper created: {target_file}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Scraper generator")
    parser.add_argument("shop_name", type=str, help="Shop name (snake_case)")
    parser.add_argument("description", type=str, help="Human-readable description")
    args = parser.parse_args()
    generate_scraper(args.shop_name, args.description) 