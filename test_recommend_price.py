"""Автотесты для recommend_price (стандартная библиотека + pytest).

Команда запуска из папки проекта:
    python -m pytest -q
Без pytest:
    python -m unittest -v test_recommend_price
"""

import asyncio
import unittest
from decimal import ROUND_DOWN, Decimal

from starter import recommend_price, sample_fetch_offers

KOPECK = Decimal("0.01")
DISCOUNT = Decimal("0.015")


def _expected(competitor_price, min_price):
    """Эталон расчёта по правилу 4, независимый от кода функции."""
    lowered = (competitor_price * (1 - DISCOUNT)).quantize(KOPECK, ROUND_DOWN)
    return max(lowered, min_price)


def _fetch(offers, status="success"):
    """Имитация async-источника с заданными предложениями и статусом."""

    async def fetch_offers():
        return {"status": status, "offers": offers}

    return fetch_offers


async def _slow_fetch_offers():
    await asyncio.sleep(5)
    return {"status": "success", "offers": []}


async def _broken_fetch_offers():
    raise ConnectionError("источник недоступен")


def run(coro):
    return asyncio.run(coro)


# ---------- Тест 1. Обычный расчёт ----------

def test_regular_calculation():
    result = run(recommend_price(
        sample_fetch_offers,
        current_price=Decimal("4900.00"),
        min_price=Decimal("4500.00"),
    ))

    # MYSHOP (4300) исключён независимо от регистра, SLOW (8 дней) — по доставке;
    # остаётся PARTS 4800 -> 4800 * 0.985 = 4728.00, отклонение < 30% -> APPLY.
    assert result["price"] == Decimal("4728.00")
    assert isinstance(result["price"], Decimal)
    assert result["decision"] == "APPLY"
    assert result["reason"]


def test_decimal_math_round_down_and_min_price_floor():
    # 999.99 * 0.985 = 984.99015 -> вниз до копейки 984.99
    result = run(recommend_price(
        _fetch([{"seller": "A", "price": Decimal("999.99"), "delivery_days": 0}]),
        current_price=Decimal("999.99"),
        min_price=Decimal("100.00"),
    ))
    assert result["price"] == Decimal("984.99")

    # 1000.01 * 0.985 = 985.00985 -> вниз до копейки 985.00
    result = run(recommend_price(
        _fetch([{"seller": "A", "price": Decimal("1000.01"), "delivery_days": 6}]),
        current_price=Decimal("1000.01"),
        min_price=Decimal("100.00"),
    ))
    assert result["price"] == Decimal("985.00")

    # Расчётный уровень ниже min_price -> рекомендация = min_price.
    result = run(recommend_price(
        _fetch([{"seller": "A", "price": Decimal("1000.00"), "delivery_days": 1}]),
        current_price=Decimal("1000.00"),
        min_price=Decimal("990.00"),
    ))
    assert result["price"] == Decimal("990.00")
    assert result["decision"] == "APPLY"


# ---------- Тест 2. Сбои и граничные случаи ----------

def test_source_error_returns_hold():
    for fetch in (_broken_fetch_offers, _fetch([], status="partial"), _fetch([], status="error")):
        result = run(recommend_price(
            fetch,
            current_price=Decimal("4900.00"),
            min_price=Decimal("4500.00"),
        ))
        assert result["decision"] == "HOLD"
        assert result["price"] == Decimal("4900.00")
        assert result["reason"]


def test_timeout_returns_hold():
    result = run(recommend_price(
        _slow_fetch_offers,
        current_price=Decimal("4900.00"),
        min_price=Decimal("4500.00"),
        timeout_s=0.05,
    ))
    assert result["decision"] == "HOLD"
    assert result["price"] == Decimal("4900.00")


def test_hold_when_no_suitable_offers_even_below_min_price():
    offers = [
        {"seller": "  MyShop ", "price": Decimal("4000.00"), "delivery_days": 1},
        {"seller": "SLOW", "price": Decimal("4100.00"), "delivery_days": 7},
        {"seller": "UNKNOWN", "price": Decimal("4200.00"), "delivery_days": None},
    ]
    result = run(recommend_price(
        _fetch(offers),
        current_price=Decimal("4000.00"),  # текущая цена ниже min_price
        min_price=Decimal("4500.00"),
    ))
    assert result["decision"] == "HOLD"
    assert result["price"] == Decimal("4000.00")


def test_review_when_deviation_over_30_percent():
    # Результат сильно ниже текущей цены: 985.00 против 2000.00 (-50%) -> REVIEW
    result = run(recommend_price(
        _fetch([{"seller": "A", "price": Decimal("1000.00"), "delivery_days": 2}]),
        current_price=Decimal("2000.00"),
        min_price=Decimal("100.00"),
    ))
    assert result["price"] == _expected(Decimal("1000.00"), Decimal("100.00"))
    assert result["price"] == Decimal("985.00")
    assert result["decision"] == "REVIEW"

    # Результат сильно выше текущей цены: min_price 1600.00 против 1000.00 (+60%) -> REVIEW
    result = run(recommend_price(
        _fetch([{"seller": "A", "price": Decimal("1000.00"), "delivery_days": 2}]),
        current_price=Decimal("1000.00"),
        min_price=Decimal("1600.00"),
    ))
    assert result["price"] == Decimal("1600.00")
    assert result["decision"] == "REVIEW"


def test_exactly_30_percent_is_allowed():
    # Конкурент 710.65989847715736040609137055838 -> 699.9999... -> вниз 700.00,
    # отклонение от current 1000.00 ровно 30% -> APPLY (ровно 30% допускается).
    result = run(recommend_price(
        _fetch([{"seller": "A",
                 "price": Decimal("710.65989847715736040609137055838"),
                 "delivery_days": 2}]),
        current_price=Decimal("1000.00"),
        min_price=Decimal("100.00"),
    ))
    assert result["price"] == Decimal("700.00")
    assert result["decision"] == "APPLY"

    # Тот же порог сверху: 1300.00 против 1000.00 — ровно +30% -> APPLY.
    result = run(recommend_price(
        _fetch([{"seller": "A", "price": Decimal("1319.80"), "delivery_days": 2}]),
        current_price=Decimal("1000.00"),
        min_price=Decimal("100.00"),
    ))
    assert result["price"] == Decimal("1300.00")
    assert result["decision"] == "APPLY"

    # 1300.01 против 1000.00 — уже больше 30% -> REVIEW.
    result = run(recommend_price(
        _fetch([{"seller": "A", "price": Decimal("1319.81"), "delivery_days": 2}]),
        current_price=Decimal("1000.00"),
        min_price=Decimal("100.00"),
    ))
    assert result["price"] == Decimal("1300.01")
    assert result["decision"] == "REVIEW"


# ---------- Обёртка unittest: запуск без pytest ----------

class RecommendPriceTests(unittest.TestCase):
    test_regular_calculation = staticmethod(test_regular_calculation)
    test_decimal_math_round_down_and_min_price_floor = staticmethod(
        test_decimal_math_round_down_and_min_price_floor
    )
    test_source_error_returns_hold = staticmethod(test_source_error_returns_hold)
    test_timeout_returns_hold = staticmethod(test_timeout_returns_hold)
    test_hold_when_no_suitable_offers_even_below_min_price = staticmethod(
        test_hold_when_no_suitable_offers_even_below_min_price
    )
    test_review_when_deviation_over_30_percent = staticmethod(
        test_review_when_deviation_over_30_percent
    )
    test_exactly_30_percent_is_allowed = staticmethod(test_exactly_30_percent_is_allowed)


if __name__ == "__main__":
    unittest.main()
