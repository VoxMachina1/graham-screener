# Code Conventions

## Language & Style

- **Python 3.11+** (specified in CI workflow)
- No linter config (no `.flake8`, `pyproject.toml`, or `ruff.toml`)
- Implicit style: PEP 8 with some alignment liberties

## Naming

| Pattern | Used for |
|---|---|
| `SCREAMING_SNAKE_CASE` | Module-level constants (`MIN_MARKET_CAP_B`, `GROWTH_CAP`, `FRED_AAA_SERIES`) |
| `snake_case` | Functions, variables, parameters |
| `_underscore_prefix` | Private/internal helpers (`_safe_float`, `_col_letter`, `_wiki_tables`, `_apply_color_coding`, `_write_markdown_tab`, `_write_docs_tab`) |

## Constants

All tunable parameters live at module top as named constants, sourced from env vars at startup:

```python
GROWTH_CAP          = 25.0
GRAHAM_NO_GROWTH_PE = 8.5
MIN_MARKET_CAP_B    = 2.0
```

Aligned with spaces for visual grouping — common across the file.

## Docstrings

Google-style (summary line + body paragraphs), applied to most public functions:

```python
def get_combined_data(ticker: str) -> dict:
    """
    Merge yfinance (price, EPS history) and Finnhub (current fundamentals).
    Finnhub values take precedence for current EPS, growth, and balance sheet.
    Falls back to yfinance values where Finnhub is missing.

    Returns a unified dict with all fields downstream code expects: ...
    """
```

Private helpers get shorter one-liners.

## Type Hints

Used selectively — return types on computation functions, `float | None` union syntax (Python 3.10+ style):

```python
def compute_growth_5yr_cagr(annual_eps: list) -> float | None:
def graham_metrics(price: float, eps: float, g: float, aaa_yield: float, pb: float | None) -> dict:
```

Not applied to all functions — data-heavy fetch functions often just return `dict`.

## Section Organization

Step-based structure with Unicode box-drawing dividers:

```python
# ═════════════════════════════════════════════
# STEP 1 — FETCH UNIVERSE
# ═════════════════════════════════════════════
```

Sub-sections within steps use lighter dividers:

```python
# ── Price ───────────────────────────────────────────────────────
```

## Logging

Standard library `logging`, single module-level logger:

```python
logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")
log = logging.getLogger(__name__)
```

Usage: `log.info(...)`, `log.warning(...)` — no `log.error()` or `log.debug()`.

## Early-Return Pattern

Ticker processing uses an error-dict early return rather than exceptions:

```python
row["Error"] = "No price"
return row
```

## Deferred Imports

Some imports appear inside functions to avoid top-level dependency when not needed:

```python
def _wiki_tables(url: str) -> list:
    from io import StringIO
    ...

def _write_markdown_tab(sh, df):
    from datetime import date
    ...
```

## NaN Handling

Explicit NaN guard using the `v != v` identity (NaN is the only float not equal to itself):

```python
eps = [e for e in annual_eps if e is not None and e == e]
```

Also via `_safe_float()` helper which returns `None` for NaN/None/non-numeric values.

## Multi-Assignment Alignment

Related assignments are space-aligned for readability:

```python
FRED_API_KEY     = os.environ["FRED_API_KEY"]
FINNHUB_API_KEY  = os.environ["FINNHUB_API_KEY"]
GSHEET_CREDS_JSON   = os.environ["GSHEET_CREDS_JSON"]
GSHEET_SPREADSHEET  = os.environ.get("GSHEET_SPREADSHEET", "Lynch & Graham Screener")
```
