"""Synthetic option chain shared by HTTP and stdio protocol tests."""

from typing import Any

CHAIN_DATA: dict[str, Any] = {
    "OptionPair": [
        {
            "Put": {
                "symbol": f"SYNTHETIC{index}" + "X" * 700,
                "displaySymbol": 'Synthetic 漢字😀 "\\',
                "strikePrice": "100.1234567890123456789",
                "optionGreek": {"delta": "-0.1234567890123456789"},
            }
        }
        for index in range(96)
    ],
    "nearPrice": "100.1234567890123456789",
}
