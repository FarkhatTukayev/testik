#!/usr/bin/env python3
"""Scrolls through a list with mouse wheel until target date is found.

Behavior:
1. Scroll down step-by-step.
2. If a visible "Load more" appears, click it and continue scrolling.
3. Stop once the target date text becomes visible.
"""

from __future__ import annotations

import argparse
import asyncio
import re
from typing import Pattern

from playwright.async_api import TimeoutError as PlaywrightTimeoutError
from playwright.async_api import async_playwright


DEFAULT_DATE = "13/4/2025"


def date_regex(date_text: str) -> Pattern[str]:
    """Supports user format dd/m/yyyy and tolerant zero-padding."""
    day, month, year = [part.strip() for part in date_text.split("/")]
    return re.compile(rf"\b0?{int(day)}/0?{int(month)}/{int(year)}\b")


async def scroll_until_date(
    page,
    target_date: str,
    list_selector: str | None,
    load_more_text: str,
    max_scrolls: int,
    scroll_pixels: int,
    pause_ms: int,
) -> None:
    target_regex = date_regex(target_date)
    load_more = page.get_by_text(load_more_text, exact=False)

    for step in range(1, max_scrolls + 1):
        # Exit condition: target date is now visible.
        if await page.get_by_text(target_regex).first.is_visible():
            print(f"✅ Найдена дата {target_date} на шаге {step}.")
            return

        # Click Load more whenever it appears.
        if await load_more.first.is_visible():
            try:
                await load_more.first.click(timeout=2000)
                await page.wait_for_timeout(pause_ms)
                print(f"ℹ️  Нажали '{load_more_text}' на шаге {step}.")
            except PlaywrightTimeoutError:
                pass

        # Scroll in the list container (if specified) or whole page.
        if list_selector:
            container = page.locator(list_selector).first
            await container.hover()
        await page.mouse.wheel(0, scroll_pixels)
        await page.wait_for_timeout(pause_ms)

    raise RuntimeError(
        f"Не удалось найти дату {target_date} за {max_scrolls} прокруток. "
        "Увеличьте --max-scrolls или проверьте формат даты/селекторы."
    )


async def main() -> None:
    parser = argparse.ArgumentParser(
        description="Прокрутка списка до даты с кликом по Load more"
    )
    parser.add_argument("--url", required=True, help="URL страницы со списком")
    parser.add_argument(
        "--target-date",
        default=DEFAULT_DATE,
        help="Целевая дата в формате d/m/yyyy (по умолчанию 13/4/2025)",
    )
    parser.add_argument(
        "--load-more-text",
        default="Load more",
        help="Текст кнопки догрузки",
    )
    parser.add_argument(
        "--list-selector",
        default=None,
        help="CSS-селектор скроллящегося контейнера (если есть)",
    )
    parser.add_argument(
        "--max-scrolls",
        type=int,
        default=800,
        help="Максимум шагов прокрутки",
    )
    parser.add_argument(
        "--scroll-pixels",
        type=int,
        default=1200,
        help="Размер одного шага прокрутки",
    )
    parser.add_argument(
        "--pause-ms",
        type=int,
        default=500,
        help="Пауза между действиями в мс",
    )
    parser.add_argument(
        "--headless",
        action="store_true",
        help="Запуск браузера в headless-режиме",
    )
    args = parser.parse_args()

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=args.headless)
        page = await browser.new_page()
        await page.goto(args.url, wait_until="domcontentloaded")

        await scroll_until_date(
            page=page,
            target_date=args.target_date,
            list_selector=args.list_selector,
            load_more_text=args.load_more_text,
            max_scrolls=args.max_scrolls,
            scroll_pixels=args.scroll_pixels,
            pause_ms=args.pause_ms,
        )

        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
