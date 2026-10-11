"""Shared supported values for order requests and builders."""

from typing import Literal, get_args

QuantityType = Literal["QUANTITY", "DOLLAR", "ALL_I_OWN"]
OrderTerm = Literal[
    "GOOD_UNTIL_CANCEL",
    "GOOD_FOR_DAY",
    "GOOD_TILL_DATE",
    "IMMEDIATE_OR_CANCEL",
    "FILL_OR_KILL",
]
OrderType = Literal[
    "EQ",
    "OPTN",
    "SPREADS",
    "BUY_WRITES",
    "BUTTERFLY",
    "IRON_BUTTERFLY",
    "CONDOR",
    "IRON_CONDOR",
    "MF",
    "MMF",
]
PriceType = Literal[
    "MARKET",
    "LIMIT",
    "STOP",
    "STOP_LIMIT",
    "TRAILING_STOP_CNST_BY_LOWER_TRIGGER",
    "UPPER_TRIGGER_BY_TRAILING_STOP_CNST",
    "TRAILING_STOP_PRCT_BY_LOWER_TRIGGER",
    "UPPER_TRIGGER_BY_TRAILING_STOP_PRCT",
    "TRAILING_STOP_CNST",
    "TRAILING_STOP_PRCT",
    "HIDDEN_STOP",
    "HIDDEN_STOP_BY_LOWER_TRIGGER",
    "UPPER_TRIGGER_BY_HIDDEN_STOP",
    "NET_DEBIT",
    "NET_CREDIT",
    "NET_EVEN",
    "MARKET_ON_OPEN",
    "MARKET_ON_CLOSE",
    "LIMIT_ON_OPEN",
    "LIMIT_ON_CLOSE",
]
MarketSession = Literal["REGULAR", "EXTENDED", "EXTO"]
OrderAction = Literal[
    "BUY",
    "SELL",
    "BUY_TO_COVER",
    "SELL_SHORT",
    "BUY_OPEN",
    "BUY_CLOSE",
    "SELL_OPEN",
    "SELL_CLOSE",
    "EXCHANGE",
]
SecurityType = Literal["EQ", "OPTN", "MF", "MMF"]

VALID_QUANTITY_TYPES = frozenset(get_args(QuantityType))
VALID_ORDER_TERMS = frozenset(get_args(OrderTerm))
VALID_ORDER_TYPES = frozenset(get_args(OrderType))
VALID_PRICE_TYPES = frozenset(get_args(PriceType))
VALID_MARKET_SESSIONS = frozenset(get_args(MarketSession))
VALID_ORDER_ACTIONS = frozenset(get_args(OrderAction))
VALID_SECURITY_TYPES = frozenset(get_args(SecurityType))
