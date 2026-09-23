# Zero-Cost Headless Google Maps Scraper

A lightweight, zero-setup Playwright CLI tool for one-off B2B prospecting without setting up Google Cloud Platform billing or API keys. Extracts business details, ratings, reviews, contact info, and exact GPS coordinates using headless browser automation.

Originally adapted from `zohaibbashir/Google-Maps-Scrapper` to run reliably on headless Linux servers, VPS environments, and autonomous agent runners.

---

## When to Use This vs. Google Places API

Google Cloud offers an official free credit tier (including allowances for Text Search and Place Details).
- **Use the official Google Places API** if you are building mission-critical client pipelines, need automated live production services, high throughput, SLA guarantees, or official data licensing.
- **Use this tool** for quick ad-hoc reconnaissance, local prospecting, or one-off exploratory scraping where setting up GCP billing accounts and managing API keys is overkill.

---

## Key Features

- **Headless Linux & VPS Ready**: Runs out-of-the-box in headless environments with anti-automation flag evasion (`navigator.webdriver` removal).
- **Accurate Pin Coordinates**: Extracts true business pin coordinates (`!3d`/`!4d` parameters) instead of camera/viewport center coordinates.
- **Locality & Garbage Row Filtering**: Filters out administrative locality cards (cities, towns, districts) and empty suggestion rows to ensure only valid businesses are saved.
- **Regional Bias Control (`--country` / `-c`)**: Appends Google's `gl` parameter (e.g. `us`, `uk`, `it`) to prevent results from being skewed by host VPS IP geolocation.
- **Automated Consent Wall Handling**: Automatically dismisses regional and European/cloud IP consent redirects and cookie prompts.
- **Stable Semantic Selectors**: Uses stable DOM and semantic attributes (`data-item-id="address"`, `data-item-id="authority"`, `data-item-id="oloc"`, `div[role="feed"]`) instead of brittle CSS hash classes.
- **Direct Single-Place Match Detection**: Accurately detects and parses queries that resolve directly to a single business profile instead of a multi-listing feed.
- **CSV & JSON Export**: Native export to `.csv` or `.json` formats with `--append` support for cumulative dataset generation.
- **Rate-Limit Jitter**: Integrated randomized delays and natural scrolling patterns prevent rapid IP throttling.

---

## Requirements & Quickstart

### Prerequisites

- Python 3.9+
- Linux, macOS, or Windows

### Installation

1. Clone repository:
   ```bash
   git clone https://github.com/anaimx/google-maps-scraper.git
   cd google-maps-scraper
   ```

2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

3. Install Playwright browser binaries:
   ```bash
   playwright install chromium
   ```
   *(On headless Ubuntu/Debian, install system dependencies if needed: `playwright install-deps chromium`)*

---

## Usage Examples

Run either `main.py` or `gmaps_scraper.py`:

### Extract 20 Places to CSV
```bash
python main.py -s "coffee shop seattle" -t 20 -c us -o leads.csv
```

### Extract 10 Places to JSON with Regional Country Bias
```bash
python main.py -s "bookstore edinburgh" -t 10 -c uk -o bookstores.json
```

### Direct Single Place Query
```bash
python main.py -s "art gallery florence" -c it -o gallery.json
```

### Append Results to Existing Dataset
```bash
python main.py -s "bakery dublin" -t 15 -c ie -o bakeries.csv --append
```

### Run with Visible Browser (Headful Mode for Debugging)
```bash
python main.py -s "coffee shop seattle" -t 5 --headful
```

### Run Tests
```bash
pytest tests/ -v
```

---

## CLI Options

| Flag | Full Option | Type | Default | Description |
|---|---|---|---|---|
| `-s` | `--search` | String | *Required* | Search query for Google Maps |
| `-t` | `--total` | Integer | `10` | Number of business listings to extract |
| `-c` | `--country` | String | `None` | Two-letter country code (`us`, `uk`, `it`) for regional bias (`&gl=<country>`) |
| `-o` | `--output` | String | `gmaps_results.csv` | Output file path (`.csv` or `.json`) |
| | `--append` | Flag | `False` | Append scraped records to existing file |
| | `--headful` | Flag | `False` | Run in visible browser window (default: headless) |

---

## Output Schema

| Field Name | Type | Description |
|---|---|---|
| `name` | String | Business or venue name |
| `category` | String | Primary business category / industry tag |
| `rating` | Float | Average Google review rating (e.g. `4.8`) |
| `reviews_count` | Integer | Total number of published Google reviews |
| `address` | String | Cleaned physical address |
| `phone` | String | Cleaned contact telephone number |
| `website` | String | Official business website URL |
| `plus_code` | String | Google Open Location Code (Plus Code) |
| `latitude` | Float | Extracted GPS latitude coordinate (pin coordinate) |
| `longitude` | Float | Extracted GPS longitude coordinate (pin coordinate) |
| `maps_url` | String | Direct Google Maps place link |
| `scraped_at` | String | ISO 8601 UTC timestamp of extraction |

---

## Attribution & Disclaimer

- **Base Adaptation**: Originally based on [zohaibbashir/Google-Maps-Scrapper](https://github.com/zohaibbashir/Google-Maps-Scrapper) (MIT License, 2023), retconned for headless server stability, consent bypass, pin coordinate extraction, and locality filtering.
- **Terms of Service & Rate Limits**: This tool is provided for educational and research purposes. Scraping Google Maps at scale may violate Google's Terms of Service and trigger IP rate limits or CAPTCHAs. Use responsibly with reasonable request volumes and delays. For high-volume production pipelines, use the official Google Places API.
