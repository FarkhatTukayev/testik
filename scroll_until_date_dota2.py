#!/usr/bin/env python3
"""Desktop automation for Dota 2 list scrolling until a target date is found.

Flow:
1. OCR current screen (or selected region).
2. If "Load more" text is visible, click it.
3. Scroll wheel down.
4. Repeat until target date (default: 13/4/2025) appears.

This script is for desktop/game UI (not browser automation).
"""

from __future__ import annotations

import argparse
import re
import time
from dataclasses import dataclass
from typing import Optional, Tuple

import pyautogui
import pytesseract
from PIL import Image, ImageOps


DEFAULT_DATE = "13/4/2025"


@dataclass
class Rect:
    x: int
    y: int
    width: int
    height: int


def parse_date_regex(date_text: str) -> re.Pattern[str]:
    parts = [part.strip() for part in date_text.split("/")]
    if len(parts) != 3:
        raise ValueError("Формат даты: d/m/yyyy (например 13/4/2025)")

    day, month, year = map(int, parts)
    if not 1 <= day <= 31 or not 1 <= month <= 12 or year < 1:
        raise ValueError(f"Некорректная дата: {date_text}")

    return re.compile(rf"\b0?{day}[./-]0?{month}[./-]{year}\b")


def parse_region(region: Optional[str]) -> Optional[Rect]:
    if not region:
        return None
    values = [int(v.strip()) for v in region.split(",")]
    if len(values) != 4:
        raise ValueError("Регион должен быть в формате x,y,width,height")
    return Rect(*values)


def screenshot(region: Optional[Rect]) -> Image.Image:
    if region is None:
        return pyautogui.screenshot()
    return pyautogui.screenshot(region=(region.x, region.y, region.width, region.height))


def preprocess(image: Image.Image) -> Image.Image:
    gray = ImageOps.grayscale(image)
    # Mild contrast/threshold preprocessing helps OCR in game UIs.
    return gray.point(lambda p: 255 if p > 160 else 0)


def read_text(image: Image.Image, lang: str) -> str:
    return pytesseract.image_to_string(image, lang=lang, config="--psm 6")


def find_load_more_box(image: Image.Image, lang: str, load_more_text: str) -> Optional[Tuple[int, int, int, int]]:
    data = pytesseract.image_to_data(
        image,
        lang=lang,
        config="--psm 6",
        output_type=pytesseract.Output.DICT,
    )

    tokens = load_more_text.lower().split()
    n = len(data["text"])

    for i in range(n):
        word = data["text"][i].strip().lower()
        if not word:
            continue

        # Match single token "load" then next token "more" (default phrase).
        if len(tokens) == 2 and word == tokens[0] and i + 1 < n:
            next_word = data["text"][i + 1].strip().lower()
            if next_word == tokens[1]:
                x1 = min(data["left"][i], data["left"][i + 1])
                y1 = min(data["top"][i], data["top"][i + 1])
                x2 = max(
                    data["left"][i] + data["width"][i],
                    data["left"][i + 1] + data["width"][i + 1],
                )
                y2 = max(
                    data["top"][i] + data["height"][i],
                    data["top"][i + 1] + data["height"][i + 1],
                )
                return (x1, y1, x2 - x1, y2 - y1)

        # Fallback for one-token matches.
        if len(tokens) == 1 and word == tokens[0]:
            return (data["left"][i], data["top"][i], data["width"][i], data["height"][i])

    return None


def center_of_box(box: Tuple[int, int, int, int], offset: Tuple[int, int]) -> Tuple[int, int]:
    left, top, width, height = box
    return (offset[0] + left + width // 2, offset[1] + top + height // 2)


def run(
    target_date: str,
    load_more_text: str,
    list_region: Optional[Rect],
    ocr_region: Optional[Rect],
    max_steps: int,
    scroll_amount: int,
    pause_s: float,
    lang: str,
    startup_delay_s: float,
) -> None:
    pyautogui.FAILSAFE = True
    date_re = parse_date_regex(target_date)

    print(f"Старт через {startup_delay_s:.1f} сек. Переключитесь в окно Dota 2...")
    time.sleep(startup_delay_s)

    for step in range(1, max_steps + 1):
        capture_region = ocr_region or list_region
        raw = screenshot(capture_region)
        processed = preprocess(raw)
        text = read_text(processed, lang=lang)

        if date_re.search(text):
            print(f"✅ Найдена дата {target_date} на шаге {step}.")
            return

        load_box = find_load_more_box(processed, lang=lang, load_more_text=load_more_text)
        if load_box is not None:
            offset = (
                0 if capture_region is None else capture_region.x,
                0 if capture_region is None else capture_region.y,
            )
            cx, cy = center_of_box(load_box, offset)
            pyautogui.moveTo(cx, cy, duration=0.1)
            pyautogui.click()
            print(f"ℹ️  Нажали '{load_more_text}' на шаге {step}.")
            time.sleep(pause_s)

        # Scroll in the list area if region set, otherwise at current mouse position.
        if list_region is not None:
            pyautogui.moveTo(list_region.x + list_region.width // 2, list_region.y + list_region.height // 2, duration=0.05)

        pyautogui.scroll(-scroll_amount)
        time.sleep(pause_s)

    raise RuntimeError(
        f"Не удалось найти дату {target_date} за {max_steps} шагов. "
        "Проверьте регион OCR/списка, язык OCR и формат даты."
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Прокрутка списка в Dota 2 до даты с кликом по Load more"
    )
    parser.add_argument("--target-date", default=DEFAULT_DATE, help="Целевая дата: d/m/yyyy")
    parser.add_argument("--load-more-text", default="Load more", help="Текст кнопки догрузки")
    parser.add_argument(
        "--list-region",
        default=None,
        help="Регион списка x,y,width,height (куда отправлять скролл)",
    )
    parser.add_argument(
        "--ocr-region",
        default=None,
        help="Регион OCR x,y,width,height (если нужно отдельно от list-region)",
    )
    parser.add_argument("--max-steps", type=int, default=800, help="Максимум шагов")
    parser.add_argument("--scroll-amount", type=int, default=700, help="Сила одного скролла")
    parser.add_argument("--pause-s", type=float, default=0.4, help="Пауза между шагами")
    parser.add_argument("--lang", default="eng", help="Язык OCR для tesseract, например eng")
    parser.add_argument(
        "--startup-delay-s",
        type=float,
        default=3.0,
        help="Задержка перед стартом, чтобы переключиться в игру",
    )
    args = parser.parse_args()

    run(
        target_date=args.target_date,
        load_more_text=args.load_more_text,
        list_region=parse_region(args.list_region),
        ocr_region=parse_region(args.ocr_region),
        max_steps=args.max_steps,
        scroll_amount=args.scroll_amount,
        pause_s=args.pause_s,
        lang=args.lang,
        startup_delay_s=args.startup_delay_s,
    )


if __name__ == "__main__":
    main()
