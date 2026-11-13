"""Учебный фрагмент для тестового задания ТОЛЬКООПТ.

Python 3.10+, только стандартная библиотека. Запуск примера: python starter.py
В функции recommend_price намеренно есть ошибки. Исправьте её по правилам ниже.
sample_fetch_offers имитирует внешний источник: реальные запросы не нужны.

Контракт fetch_offers(): async-функция без аргументов, возвращает словарь
со status (success / partial / error) и offers (список предложений).
Все суммы на входе — положительные Decimal с точностью до копейки.
seller — строка; delivery_days — неотрицательное целое число или None.
Формат входных данных корректен; дополнительных проверок типов не требуется.
fetch_offers может завершиться исключением или долго ожидать ответа.
current_price — текущая цена; min_price — минимально допустимая цена.
timeout_s — положительное число секунд, по умолчанию 2.

ПРАВИЛА В ПОРЯДКЕ ПРИМЕНЕНИЯ
1. Ограничьте ожидание fetch_offers значением timeout_s. При ошибке источника,
   тайм-ауте или status != success верните текущую цену и HOLD.
2. Учитывайте предложения с известной доставкой не более 6 дней.
   Исключайте собственный магазин MYSHOP независимо от регистра букв.
3. Если подходящих предложений нет, верните текущую цену и HOLD,
   даже если текущая цена ниже min_price.
4. Минимальную цену подходящего конкурента уменьшите на 1,5% и округлите
   вниз до копейки. Рекомендация — максимум из этой суммы и min_price.
5. Если рекомендация отличается от текущей цены более чем на 30% в любую
   сторону, верните рекомендацию и REVIEW. Иначе — рекомендацию и APPLY.
   Ровно 30% допускается. REVIEW означает, что автоматическое применение
   запрещено до ручной проверки.

РЕЗУЛЬТАТ
Словарь с полями price (Decimal), decision (APPLY / REVIEW / HOLD),
reason (короткая понятная причина). Сохраните интерфейс recommend_price;
вспомогательные функции допустимы. Пример ниже после исправления должен
вернуть price = Decimal("4728.00"), decision = "APPLY".

ПРОВЕРКА
Добавьте минимум два автоматических теста: обычный расчёт и один сбой
или граничный случай на ваш выбор. Укажите команду запуска тестов.
Достаточно стандартной библиотеки; pytest также допустим.
"""

import asyncio
from decimal import ROUND_DOWN, Decimal

OWN_SHOP = "MYSHOP"            # собственный магазин, исключаем из конкурентов
MAX_DELIVERY_DAYS = 6          # учитываем доставку не дольше 6 дней
DISCOUNT = Decimal("0.015")    # снижение цены конкурента на 1,5%
KOPECK = Decimal("0.01")
REVIEW_THRESHOLD = Decimal("0.30")  # порог отклонения от текущей цены


def _hold(current_price, reason):
    return {"price": current_price, "decision": "HOLD", "reason": reason}


def _is_suitable(offer):
    """Правило 2: известная доставка <= 6 дней и продавец не наш магазин."""
    days = offer.get("delivery_days")
    if days is None or days > MAX_DELIVERY_DAYS:
        return False
    return str(offer.get("seller", "")).strip().casefold() != OWN_SHOP.casefold()


def _target_price(competitor_price, min_price):
    """Правило 4: -1,5%, округление вниз до копейки, но не ниже min_price."""
    competitor_price = Decimal(competitor_price)
    lowered = (competitor_price * (1 - DISCOUNT)).quantize(KOPECK, ROUND_DOWN)
    return max(lowered, Decimal(min_price))


def _is_review_needed(recommended, current_price):
    """Правило 5: отклонение строго больше 30% в любую сторону (ровно 30% допустимо)."""
    deviation = abs(recommended - current_price)
    return deviation > abs(current_price) * REVIEW_THRESHOLD


async def recommend_price(fetch_offers, current_price, min_price, timeout_s=2.0):
    current_price = Decimal(current_price)
    min_price = Decimal(min_price)

    # Правило 1: ограничиваем ожидание, любые сбои источника => HOLD.
    try:
        result = await asyncio.wait_for(fetch_offers(), timeout=timeout_s)
    except (asyncio.TimeoutError, TimeoutError):
        return _hold(current_price, f"Источник не ответил за {timeout_s} с")
    except Exception as exc:  # сбой источника не должен ломать расчёт
        return _hold(current_price, f"Ошибка источника: {type(exc).__name__}")

    if not isinstance(result, dict) or result.get("status") != "success":
        status = result.get("status") if isinstance(result, dict) else "нет ответа"
        return _hold(current_price, f"Источник вернул status={status}")

    # Правило 2: подходящие предложения конкурентов.
    offers = result.get("offers") or []
    competitor_prices = [
        Decimal(offer["price"]) for offer in offers if _is_suitable(offer)
    ]

    # Правило 3: нет подходящих предложений => HOLD, даже если current < min_price.
    if not competitor_prices:
        return _hold(current_price, "Нет подходящих предложений конкурентов")

    # Правило 4: рекомендация не ниже min_price.
    recommended = _target_price(min(competitor_prices), min_price)

    # Правило 5: сильное отклонение от текущей цены требует ручной проверки.
    if _is_review_needed(recommended, current_price):
        return {
            "price": recommended,
            "decision": "REVIEW",
            "reason": "Отклонение от текущей цены более 30%",
        }
    return {
        "price": recommended,
        "decision": "APPLY",
        "reason": "Цена конкурента снижена на 1,5%",
    }


async def sample_fetch_offers():
    return {
        "status": "success",
        "offers": [
            {"seller": "myshop", "price": Decimal("4300.00"), "delivery_days": 2},
            {"seller": "PARTS", "price": Decimal("4800.00"), "delivery_days": 3},
            {"seller": "SLOW", "price": Decimal("4700.00"), "delivery_days": 8},
        ],
    }


if __name__ == "__main__":
    result = asyncio.run(recommend_price(
        sample_fetch_offers,
        current_price=Decimal("4900.00"),
        min_price=Decimal("4500.00"),
    ))
    print(result)
