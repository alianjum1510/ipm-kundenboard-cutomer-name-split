"""
Splits a customer name so part 1 never exceeds `max_length` characters.
The overflow goes to part 2 ("Customer Name Teil 2").

Split priority:
  1. Last whitespace at or before the limit (never cuts a word)
  2. Last separator (, ; / - & .) at or before the limit
  3. Hard cut at the limit (only for a single 100+ char "word")

A boundary is only accepted if it keeps part 1 at least `min_fill_ratio`
of the limit, so "A VeryLongCompanyNameWithoutSpaces..." doesn't end up
with part 1 = "A".

Length is counted in Unicode code points after NFC normalisation, so
"Müller" is 6 characters whether ü was typed precomposed or decomposed.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

SEPARATORS = frozenset(",;/-&.")


@dataclass(frozen=True)
class SplitResult:
    part1: str
    part2: str
    was_split: bool


def split_customer_name(
    value: str | None,
    max_length: int = 100,
    min_fill_ratio: float = 0.5,
) -> SplitResult:
    min_fill = int(max_length * min_fill_ratio)
    clean = re.sub(r"\s+", " ", unicodedata.normalize("NFC", value or "")).strip()

    if len(clean) <= max_length:
        return SplitResult(clean, "", False)

    cut = -1

    # 1. Whitespace. clean[max_length] being a space means part 1 can be exactly max_length long.
    for i in range(max_length, min_fill - 1, -1):
        if clean[i] == " ":
            cut = i
            break

    # 2. Separator: cut right after it, so the separator stays with part 1.
    if cut == -1:
        for i in range(max_length, max(min_fill, 1) - 1, -1):
            if clean[i - 1] in SEPARATORS:
                cut = i
                break

    # 3. Hard cut.
    if cut == -1:
        cut = max_length

    part1 = clean[:cut].strip()
    part2 = re.sub(r"^[\s,;]+", "", clean[cut:]).strip()  # no dangling comma in Teil 2
    return SplitResult(part1, part2, True)
