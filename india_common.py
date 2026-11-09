"""Shared Indian equity-trading helpers.

All monetary values returned by this module are ``Decimal`` instances. Fee
rates are decimal fractions, not percentages: ``0.0003`` means 0.03%.
The checked-in configuration intentionally contains zero fee rates. Replace
them with the values from the account's current broker charge sheet.
"""

import datetime as _datetime
import json
import os
from decimal import Decimal, ROUND_HALF_UP

try:
    from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
except ImportError:  # Python 3.8 fallback: IST has no daylight-saving time.
    ZoneInfo = None
    ZoneInfoNotFoundError = ImportError


UTC = _datetime.timezone.utc
IST_OFFSET = _datetime.timedelta(hours=5, minutes=30)
if ZoneInfo is not None:
    try:
        IST = ZoneInfo("Asia/Kolkata")
    except ZoneInfoNotFoundError:  # tzdata may be absent.
        IST = _datetime.timezone(IST_OFFSET, "IST")
else:
    IST = _datetime.timezone(IST_OFFSET, "IST")
PRE_OPEN = (_datetime.time(9, 0), _datetime.time(9, 15))
REGULAR_SESSION = (_datetime.time(9, 15), _datetime.time(15, 30))
DEFAULT_TICK_SIZE = Decimal("0.05")

_ROOT = os.path.dirname(os.path.abspath(__file__))
DEFAULT_CONFIG_PATH = os.path.join(_ROOT, "trader", "config.json")
DEFAULT_HOLIDAYS_PATH = os.path.join(_ROOT, "holidays.json")

DEFAULT_CONFIG = {
    "capital": Decimal("0"),
    "max_loss_per_trade": Decimal("0"),
    "daily_loss_limit": Decimal("0"),
    "flat_by": "15:15",
    "entry_window": ["09:15", "15:00"],
    "paper": True,
    "tick_sizes": {},
    "special_sessions": {},
    "trading_costs": {
        "brokerage": {"percent": Decimal("0"), "max_per_order": Decimal("0")},
        "stt": {"sell_percent": Decimal("0")},
        "exchange_charges": {"percent": Decimal("0")},
        "sebi_fees": {"per_crore": Decimal("0")},
        "stamp_duty": {"buy_percent": Decimal("0")},
        "gst": {"percent": Decimal("0")},
    },
}


def _copy_defaults():
    result = dict(DEFAULT_CONFIG)
    result["tick_sizes"] = {}
    result["special_sessions"] = {}
    result["trading_costs"] = {
        key: dict(value) for key, value in DEFAULT_CONFIG["trading_costs"].items()
    }
    return result


def _decimal(value):
    return Decimal(str(value))


def _merge(base, override):
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            _merge(base[key], value)
        else:
            base[key] = value
    return base


def load_config(path=DEFAULT_CONFIG_PATH):
    """Load JSON configuration and merge it over safe, documented defaults."""
    config = _copy_defaults()
    if path and os.path.exists(path):
        with open(path, encoding="utf-8") as handle:
            data = json.load(handle)
        if not isinstance(data, dict):
            raise ValueError("config.json must contain a JSON object")
        _merge(config, data)
    for key in ("capital", "max_loss_per_trade", "daily_loss_limit"):
        config[key] = _decimal(config[key])
    for symbol, size in config["tick_sizes"].items():
        config["tick_sizes"][symbol.upper()] = _decimal(size)
    for section in config["trading_costs"].values():
        for key, value in section.items():
            section[key] = _decimal(value)
    return config


def load_holidays(path=DEFAULT_HOLIDAYS_PATH):
    """Return holiday dates from JSON as ``date`` objects.

    The file may be a list of ISO dates or ``{"holidays": [...]}``. Invalid
    dates are reported rather than silently making a trading day available.
    """
    with open(path, encoding="utf-8") as handle:
        data = json.load(handle)
    dates = data.get("holidays", []) if isinstance(data, dict) else data
    if not isinstance(dates, list):
        raise ValueError("holidays.json holidays must be a list")
    try:
        return {_datetime.date.fromisoformat(str(value)) for value in dates}
    except ValueError as error:
        raise ValueError("holidays.json contains a non-ISO date") from error


def to_ist(value=None):
    """Convert an aware datetime to IST; naive datetimes are assumed IST."""
    if value is None:
        return _datetime.datetime.now(UTC).astimezone(IST)
    if not isinstance(value, _datetime.datetime):
        raise TypeError("to_ist expects a datetime")
    if value.tzinfo is None:
        return value.replace(tzinfo=IST)
    return value.astimezone(IST)


def _time(value):
    if isinstance(value, _datetime.time):
        return value
    hour, minute = str(value).split(":")[:2]
    return _datetime.time(int(hour), int(minute))


def _session_for(day, config):
    special = config.get("special_sessions", {}).get(day.isoformat())
    if special is None:
        return REGULAR_SESSION
    if special is False or special.get("closed", False):
        return None
    return _time(special.get("open", "09:15")), _time(special.get("close", "15:30"))


def is_market_open(at=None, holidays=None, config=None, include_pre_open=False):
    """Return whether ``at`` is within an NSE session.

    Regular trading is the default. Set ``include_pre_open`` to include the
    09:00-09:15 auction window. Special sessions are date-keyed in config.
    """
    config = config or load_config()
    current = to_ist(at)
    holidays = load_holidays() if holidays is None else set(holidays)
    if current.weekday() >= 5 or current.date() in holidays:
        return False
    session = _session_for(current.date(), config)
    if session is None:
        return False
    if include_pre_open and REGULAR_SESSION[0] > current.time() >= PRE_OPEN[0]:
        return True
    return session[0] <= current.time() < session[1]


def next_open(at=None, holidays=None, config=None):
    """Return the next regular-session opening datetime in IST."""
    config = config or load_config()
    current = to_ist(at)
    holidays = load_holidays() if holidays is None else set(holidays)
    day = current.date()
    while True:
        if day.weekday() < 5 and day not in holidays:
            session = _session_for(day, config)
            if session is not None:
                opening = _datetime.datetime.combine(day, session[0], tzinfo=IST)
                if opening > current:
                    return opening
        day += _datetime.timedelta(days=1)
        current = _datetime.datetime.combine(day, _datetime.time.min, tzinfo=IST)


def yahoo_symbol(symbol):
    """Return the Yahoo Finance symbol for an NSE equity ticker."""
    symbol = str(symbol).strip().upper()
    return symbol if symbol.endswith(".NS") else symbol + ".NS"


def round_to_tick(price, symbol=None, config=None):
    config = config or load_config()
    tick = config.get("tick_sizes", {}).get(str(symbol).upper(), DEFAULT_TICK_SIZE)
    value = _decimal(price)
    return (value / tick).quantize(Decimal("1"), rounding=ROUND_HALF_UP) * tick


def calculate_trading_costs(buy_value, sell_value, config=None):
    """Calculate configurable intraday equity charges for one round trip."""
    config = config or load_config()
    buy = _decimal(buy_value)
    sell = _decimal(sell_value)
    turnover = buy + sell
    rates = config["trading_costs"]
    brokerage = min(
        buy * rates["brokerage"]["percent"],
        rates["brokerage"]["max_per_order"],
    ) + min(
        sell * rates["brokerage"]["percent"],
        rates["brokerage"]["max_per_order"],
    )
    charges = {
        "brokerage": brokerage,
        "stt": sell * rates["stt"]["sell_percent"],
        "exchange_charges": turnover * rates["exchange_charges"]["percent"],
        "sebi_fees": turnover / Decimal("10000000") * rates["sebi_fees"]["per_crore"],
        "stamp_duty": buy * rates["stamp_duty"]["buy_percent"],
    }
    taxable = brokerage + charges["exchange_charges"] + charges["sebi_fees"]
    charges["gst"] = taxable * rates["gst"]["percent"]
    charges["total"] = sum(charges.values(), Decimal("0"))
    return charges


trading_costs = calculate_trading_costs
