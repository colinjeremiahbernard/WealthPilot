"""
RPA client-data extractor for the Investment Assistant pipeline.

Scrapes a (local or remote) HTML page listing clients, validates the
records, and forwards them as JSON to an n8n webhook for downstream
processing (profile matching + message generation).

Usage:
    python extract_clients.py --source docs/index.html --webhook-url $N8N_WEBHOOK_URL
    python extract_clients.py --source https://example.github.io/clients --dry-run
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
import time
from dataclasses import dataclass, asdict
from typing import Literal
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger("extract_clients")

InvestorProfile = Literal["Conservador", "Moderado", "Arrojado"]
VALID_PROFILES = {"Conservador", "Moderado", "Arrojado"}


@dataclass
class Client:
    name: str
    email: str
    balance: float
    profile: InvestorProfile

    def to_dict(self) -> dict:
        return asdict(self)


class ExtractionError(RuntimeError):
    """Raised when the client table can't be parsed."""


def fetch_html(source: str) -> str:
    """Fetch HTML from a URL, or read it from a local file."""
    parsed = urlparse(source)
    if parsed.scheme in ("http", "https"):
        log.info("Fetching clients page from %s", source)
        resp = requests.get(source, timeout=15)
        resp.raise_for_status()
        return resp.text

    log.info("Reading clients page from local file %s", source)
    with open(source, "r", encoding="utf-8") as f:
        return f.read()


def parse_clients(html: str) -> list[Client]:
    """Parse the clients table out of the page HTML."""
    soup = BeautifulSoup(html, "lxml")
    table = soup.find("table", {"id": "clients"}) or soup.find("table")
    if table is None:
        raise ExtractionError("No <table> found on the page.")

    rows = table.find_all("tr")[1:]  # skip header row
    clients: list[Client] = []

    for i, row in enumerate(rows, start=1):
        cells = [c.get_text(strip=True) for c in row.find_all(["td", "th"])]
        if len(cells) < 4:
            log.warning("Skipping row %d: expected 4 columns, got %d", i, len(cells))
            continue

        name, email, balance_raw, profile = cells[:4]

        try:
            balance = float(
                balance_raw.replace("R$", "").replace(".", "").replace(",", ".").strip()
            )
        except ValueError:
            log.warning("Skipping row %d: could not parse balance %r", i, balance_raw)
            continue

        if profile not in VALID_PROFILES:
            log.warning("Skipping row %d: unknown profile %r", i, profile)
            continue

        clients.append(
            Client(name=name, email=email, balance=balance, profile=profile)  # type: ignore[arg-type]
        )

    if not clients:
        raise ExtractionError("Table was found but no valid client rows were parsed.")

    log.info("Parsed %d valid client(s)", len(clients))
    return clients


def send_to_webhook(clients: list[Client], webhook_url: str, retries: int = 3) -> requests.Response:
    """POST the extracted clients to the n8n webhook, with basic exponential backoff."""
    payload = {"clients": [c.to_dict() for c in clients]}

    for attempt in range(1, retries + 1):
        try:
            log.info("Sending %d client(s) to n8n (attempt %d/%d)", len(clients), attempt, retries)
            resp = requests.post(webhook_url, json=payload, timeout=20)
            resp.raise_for_status()
            log.info("Webhook accepted payload: HTTP %d", resp.status_code)
            return resp
        except requests.RequestException as exc:
            log.warning("Webhook call failed: %s", exc)
            if attempt == retries:
                raise
            time.sleep(2 ** attempt)

    raise RuntimeError("unreachable")


def main() -> int:
    load_dotenv()

    parser = argparse.ArgumentParser(description="Extract client data and forward it to n8n.")
    parser.add_argument(
        "--source",
        default="docs/index.html",
        help="URL or local path to the clients page (default: docs/index.html)",
    )
    parser.add_argument(
        "--webhook-url",
        default=os.getenv("N8N_WEBHOOK_URL"),
        help="n8n webhook URL (or set N8N_WEBHOOK_URL in .env)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Parse and print clients without sending them anywhere.",
    )
    args = parser.parse_args()

    try:
        html = fetch_html(args.source)
        clients = parse_clients(html)
    except (ExtractionError, requests.RequestException, OSError) as exc:
        log.error("Extraction failed: %s", exc)
        return 1

    if args.dry_run:
        for c in clients:
            print(c.to_dict())
        return 0

    if not args.webhook_url:
        log.error("No webhook URL provided. Pass --webhook-url or set N8N_WEBHOOK_URL.")
        return 1

    try:
        send_to_webhook(clients, args.webhook_url)
    except requests.RequestException as exc:
        log.error("Failed to reach n8n webhook after retries: %s", exc)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
