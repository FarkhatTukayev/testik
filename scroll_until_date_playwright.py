#!/usr/bin/env python3
"""Scroll list with mouse wheel, click "Load more", stop on target date."""

from __future__ import annotations

import argparse
import asyncio
import re
from dataclasses import dataclass
from typing import Pattern

from playwright.async_api import TimeoutError as PlaywrightTimeoutError
from playwright.async_api import Page
from playwright.async_api import async_playwright


DEFAULT_DATE = "13/4/2025"


@dataclass
class ScrollState:
    """Tracks progress to detect when scrolling gets stuck."""

    stagnant_steps: int = 0
    previous_height: int = -1


def parse_target_date(date_text: str) -> tuple[int, int, int]:
    """Parse date provided as d/m/yyyy and return normalized numbers."""
    parts = [part.strip() for part in date_text.split("/")]
    if len(parts) != 3:
        raise ValueError("Ожидается формат даты d/m/yyyy, пример: 13/4/2025")

    day, month, year = (int(parts[0]), int(parts[1]), int(parts[2]))
    if not 1 <= day <= 31 or not 1 <= month <= 12 or year < 1:
        raise ValueError(f"Некорректная дата: {date_text}")
    return day, month, year


def date_regex(date_text: str) -> Pattern[str]:
    """Match date in common separators and optional zero-padding."""
    day, month, year = parse_target_date(date_text)
    separators = r"[./-]"
    return re.compile(rf"\b0?{day}{separators}0?{month}{separators}{year}\b")


async def get_scroll_height(page: Page, list_selector: str | None) -> int:
    """Get current scroll height for page or list container."""
    if list_selector:
        locator = page.locator(list_selector).first
        return await locator.evaluate("el => el.scrollHeight")
    return await page.evaluate("() => document.scrollingElement?.scrollHeight ?? 0")


async def scroll_step(
    page: Page,
    list_selector: str | None,
    scroll_pixels: int,
) -> None:
    """Perform one scroll step using wheel and JS fallback."""
    if list_selector:
        container = page.locator(list_selector).first
        await container.hover()
        await page.mouse.wheel(0, scroll_pixels)
        await container.evaluate("(el, delta) => { el.scrollTop += delta; }", scroll_pixels)
        return

    await page.mouse.wheel(0, scroll_pixels)
    await page.evaluate(
        "(delta) => window.scrollBy({ top: delta, left: 0, behavior: 'instant' })",
        scroll_pixels,
    )


async def click_load_more(page: Page, load_more_text: str) -> bool:
    """Try to click the first visible and enabled load-more element."""
    locator = page.get_by_text(load_more_text, exact=False)
    count = await locator.count()
    for i in range(count):
        item = locator.nth(i)
        if not await item.is_visible():
            continue
        try:
            await item.click(timeout=2000)
            return True
        except PlaywrightTimeoutError:
            continue
    return False


async def scroll_until_date(
    page: Page,
    target_date: str,
    list_selector: str | None,
    load_more_text: str,
    max_scrolls: int,
    scroll_pixels: int,
    pause_ms: int,
    stagnant_limit: int,
) -> None:
    target_regex = date_regex(target_date)
    state = ScrollState(previous_height=await get_scroll_height(page, list_selector))

    for step in range(1, max_scrolls + 1):
        if await page.get_by_text(target_regex).first.is_visible():
            print(f"✅ Найдена дата {target_date} на шаге {step}.")
            return

        clicked = await click_load_more(page, load_more_text)
        if clicked:
            print(f"ℹ️  Нажали '{load_more_text}' на шаге {step}.")
            await page.wait_for_timeout(pause_ms)

        await scroll_step(page, list_selector, scroll_pixels)
        await page.wait_for_timeout(pause_ms)

        current_height = await get_scroll_height(page, list_selector)
        if current_height <= state.previous_height and not clicked:
            state.stagnant_steps += 1
        else:
            state.stagnant_steps = 0
        state.previous_height = current_height

        if state.stagnant_steps >= stagnant_limit:
            raise RuntimeError(
                "Прокрутка перестала продвигаться: возможно, достигнут конец списка "
                "или требуется другой селектор/текст кнопки Load more."
            )

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
        "--stagnant-limit",
        type=int,
        default=25,
        help="Сколько шагов подряд без прогресса считать зависанием",
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
            stagnant_limit=args.stagnant_limit,
        )

        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
