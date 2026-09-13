"""Local, review-first OCR for manually captured sportsbook screenshots."""
from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
from io import BytesIO
from pathlib import Path
from typing import Any

from PIL import Image, ImageEnhance, ImageOps
from rapidfuzz import fuzz, process

from app.db.player_directory_store import player_directory_store

MAX_IMAGE_BYTES = 8 * 1024 * 1024
SUPPORTED_MARKETS = {
    "passing_yards", "passing_tds", "passing_interceptions",
    "rushing_yards", "receiving_yards", "receptions", "anytime_td",
}


class ScreenshotOCRError(RuntimeError):
    pass


def _tesseract_path() -> str:
    candidates = [
        shutil.which("tesseract"),
        r"C:\Program Files\Tesseract-OCR\tesseract.exe",
        r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
    ]
    for candidate in candidates:
        if candidate and Path(candidate).is_file():
            return candidate
    raise ScreenshotOCRError("Local OCR is not installed. Install Tesseract-OCR before using screenshot batches.")


def _number(token: str, *, odds: bool = False) -> float | None:
    value = token.replace(",", ".")
    try:
        if "." in value:
            parsed = float(value)
        elif len(value) == 3 and value.startswith("1") and odds:
            parsed = float(f"{value[0]}.{value[1:]}")
        elif len(value) == 3:
            parsed = float(f"{value[:-1]}.{value[-1]}")
        else:
            parsed = float(value)
    except ValueError:
        return None
    return parsed if parsed > 0 else None


def _directory_match(raw_name: str) -> tuple[str | None, int | None]:
    players = player_directory_store.search("", limit=10_000)
    choices = {str(item.get("player_name") or ""): item for item in players}
    if not raw_name or not choices:
        return None, None
    match = process.extractOne(raw_name, choices.keys(), scorer=fuzz.ratio, score_cutoff=65)
    if not match:
        return None, None
    return str(match[0]), round(float(match[1]))


def _rows_from_text(text: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for raw_line in text.splitlines():
        cleaned = " ".join(raw_line.split())
        numbers = re.findall(r"(?<!\d)(?:\d{1,3}\.\d{1,2}|\d{3})(?!\d)", cleaned)
        if len(numbers) < 4:
            continue
        first_number = cleaned.find(numbers[0])
        raw_name = re.sub(r"^[^A-Za-z]+", "", cleaned[:first_number]).strip()
        line = _number(numbers[0])
        over = _number(numbers[1], odds=True)
        under = _number(numbers[3], odds=True)
        suggested_name, match_score = _directory_match(raw_name)
        rows.append({
            "raw_text": cleaned,
            "raw_name": raw_name,
            "suggested_player_name": suggested_name,
            "match_score": match_score,
            "line": line,
            "over_odds": over,
            "under_odds": under,
            "status": "review_required",
        })
    return rows


def extract_screenshot(content: bytes, filename: str) -> dict[str, Any]:
    if not content:
        raise ScreenshotOCRError("The screenshot is empty.")
    if len(content) > MAX_IMAGE_BYTES:
        raise ScreenshotOCRError("Each screenshot must be 8 MB or smaller.")
    suffix = Path(filename or "screenshot.png").suffix.lower()
    if suffix not in {".png", ".jpg", ".jpeg", ".webp"}:
        raise ScreenshotOCRError("Upload a PNG, JPG, JPEG, or WEBP screenshot.")
    try:
        image = Image.open(BytesIO(content)).convert("L")
    except Exception as exc:
        raise ScreenshotOCRError("This file could not be read as an image.") from exc

    with tempfile.TemporaryDirectory(prefix="proplens-ocr-") as directory:
        prepared_path = Path(directory) / "prepared.png"
        scaled = image.resize((image.width * 3, image.height * 3))
        enhanced = ImageEnhance.Contrast(ImageOps.autocontrast(scaled)).enhance(2)
        enhanced.save(prepared_path)
        completed = subprocess.run(
            [_tesseract_path(), str(prepared_path), "stdout", "--psm", "6", "-l", "eng"],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    if completed.returncode:
        raise ScreenshotOCRError("Local OCR could not read this screenshot. Try a clearer, uncropped capture.")
    text = completed.stdout.strip()
    return {"filename": filename, "raw_text": text, "rows": _rows_from_text(text)}
