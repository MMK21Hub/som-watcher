from __future__ import annotations
from math import inf
from sys import stderr
from time import sleep
from traceback import format_exc
from argparse import ArgumentParser
from prometheus_client import start_http_server, Gauge
from typing import Any, List, Literal, Optional
from pydantic import BaseModel, Field, ValidationError, field_validator
import requests

# class Prices(BaseModel):
#     us: Optional[int] = Field(None, alias="US")
#     eu: Optional[int] = Field(None, alias="EU")
#     india: Optional[int] = Field(None, alias="IN")
#     ca: Optional[int] = Field(None, alias="CA")
#     au: Optional[int] = Field(None, alias="AU")
#     worldwide: Optional[int] = Field(None, alias="XX")

SHOP_API_URL = "https://summer.skyfall.dev/api/shop"
REGION_NAMES = {
    "US": "United States",
    "EU": "EU + UK",
    "IN": "India",
    "CA": "Canada",
    "AU": "Australia",
    "XX": "Rest of World",
}


type ShopType = Literal["public_shop", "black_market", "stickerlode"]


class ShopItem(BaseModel):
    title: str
    image_url: str = Field(..., alias="imageUrl")
    description: str
    purchase_url: Optional[str] = Field(None, alias="purchaseUrl")
    id: int
    shop_type: ShopType = Field(..., alias="shopType")
    prices: dict[str, int]
    stock_remaining: Optional[int] = Field(None, alias="stockRemaining")

    @field_validator("shop_type", mode="before")
    @classmethod
    def parse_shop_type(cls, value: Any) -> Any:
        match value:
            case "blackMarket":
                return "black_market"
            case "regular":
                return "public_shop"
            case "stickerlode":
                return "stickerlode"
            case _:
                return value


def fetch_shop() -> list[ShopItem]:
    response = requests.get(SHOP_API_URL)
    response.raise_for_status()
    data = response.json()
    if not data:
        raise ValueError("No data received from shop API")
    items: list[ShopItem] = []
    for item in data:
        try:
            items.append(ShopItem(**item))
        except ValidationError as e:
            print(f"Failed to parse item: {e}", file=stderr)
    if not items:
        raise ValueError("Failed to parse shop items from the API")
    return items


def main():
    parser = ArgumentParser()
    parser.add_argument(
        "--port",
        type=int,
        default=9040,
        help="the port to run the Prometheus exporter on",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="count",
        help="log whenever data is scraped",
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=10,
        help="how often to fetch data, in seconds",
    )
    args = parser.parse_args()

    start_http_server(args.port)
    print(f"Started metrics exporter: http://localhost:{args.port}/metrics", flush=True)

    has_had_success = False
    stock_gauge = Gauge(
        "som_shop_stock",
        "Stock remaining for shop items",
        ["item_id", "item_name", "item_image", "shop_type", "item_description"],
    )
    price_gauge = Gauge(
        "som_shop_price_shells",
        "Price for shop items",
        [
            "item_id",
            "item_name",
            "item_image",
            "shop_type",
            "item_description",
            "region",
            "region_name",
        ],
    )

    while True:
        try:
            items = fetch_shop()
            for item in items:
                stock_gauge.labels(
                    item_id=item.id,
                    item_name=item.title,
                    item_image=item.image_url,
                    shop_type=item.shop_type,
                    item_description=item.description,
                ).set(item.stock_remaining or +inf)
                for region, price in item.prices.items():
                    region_name = REGION_NAMES.get(region) or region
                    price_gauge.labels(
                        item_id=item.id,
                        item_name=item.title,
                        item_image=item.image_url,
                        shop_type=item.shop_type,
                        item_description=item.description,
                        region=region,
                        region_name=region_name,
                    ).set(price)
            if args.verbose:
                print(f"Successfully fetched {len(items)} shop items")
            has_had_success = True
        except Exception as e:
            # Exit the program if the first fetch fails
            if not has_had_success:
                raise e
            print(f"Failed to fetch data: {format_exc()}", file=stderr, flush=True)
        finally:
            sleep(args.interval)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass
