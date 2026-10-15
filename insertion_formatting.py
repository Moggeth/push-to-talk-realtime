"""Local, conservative formatting at an editor's insertion point."""

from __future__ import annotations

import re
from dataclasses import dataclass

INSERTION_MODES = ("auto", "standalone", "insert")

# Only unambiguous common opening words are lowered. Unknown words may be names.
COMMON_OPENERS = frozenset(
    [
        "a",
        "an",
        "the",
        "this",
        "that",
        "these",
        "those",
        "it",
        "its",
        "we",
        "you",
        "he",
        "she",
        "they",
        "them",
        "our",
        "your",
        "their",
        "my",
        "his",
        "her",
        "and",
        "or",
        "but",
        "so",
        "because",
        "although",
        "though",
        "while",
        "when",
        "where",
        "which",
        "who",
        "what",
        "how",
        "why",
        "if",
        "unless",
        "until",
        "since",
        "for",
        "from",
        "with",
        "without",
        "into",
        "onto",
        "to",
        "of",
        "at",
        "by",
        "on",
        "in",
        "as",
        "is",
        "are",
        "was",
        "were",
        "be",
        "been",
        "being",
        "do",
        "does",
        "did",
        "have",
        "has",
        "had",
        "can",
        "could",
        "would",
        "should",
        "might",
        "must",
        "not",
        "no",
        "yes",
        "just",
        "also",
        "even",
        "really",
        "very",
        "quite",
        "some",
        "any",
        "all",
        "each",
        "every",
        "another",
        "other",
        "more",
        "most",
        "less",
        "much",
        "many",
        "few",
        "first",
        "then",
        "than",
        "there",
        "here",
        "now",
        "perhaps",
        "probably",
        "actually",
        "basically",
        "please",
        "thanks",
        "thank",
        "well",
        "let",
        "lets",
        "instead",
        "only",
        "still",
        "already",
        "about",
        "around",
        "between",
        "both",
        "either",
        "neither",
        "one",
        "two",
        "three",
        "four",
        "five",
        "six",
        "seven",
        "eight",
        "nine",
        "ten",
    ]
)


@dataclass(frozen=True)
class CaretContext:
    before: str
    after: str


@dataclass(frozen=True)
class InsertionPlan:
    style: str
    label: str
    context: CaretContext | None = None


def choose_plan(mode: str, context: CaretContext | None, *, bullet=False) -> InsertionPlan:
    if bullet:
        return InsertionPlan("standalone", "Bullets")
    if mode == "standalone":
        return InsertionPlan("standalone", "Standalone")
    if mode == "insert":
        return InsertionPlan("insert", "Insert", context)
    if context is None:
        return InsertionPlan("standalone", "Auto: unavailable")
    # A newline is a paragraph boundary even after trailing indentation.
    line = context.before.rsplit("\n", 1)[-1].rstrip()
    start = not line or bool(re.search(r"[.!?][\"\u201d\u2019)\]]*$", line))
    return InsertionPlan(
        "standalone" if start else "insert",
        "Auto: standalone" if start else "Auto: insert",
        context,
    )


def format_insertion(text: str, plan: InsertionPlan, standalone: str) -> str:
    if not text.strip():
        return ""
    if plan.style == "standalone":
        cleaned = standalone.rstrip()
    else:
        cleaned = text.strip()
        # Remove a provider's sentence-ending punctuation, preserving ellipses,
        # decimals, initials, and abbreviations that have meaningful final dots.
        if cleaned.endswith(("!", "?")):
            cleaned = cleaned.rstrip("!?")
        elif cleaned.endswith(".") and not cleaned.endswith(".."):
            word = cleaned.split()[-1]
            abbreviation = word.lower() in {"etc.", "e.g.", "i.e.", "mr.", "mrs.", "dr.", "vs."}
            if not abbreviation and not re.fullmatch(r"(?:[A-Za-z]\.)+", word):
                cleaned = cleaned[:-1]
        match = re.match(r"([A-Za-z]+)(.*)", cleaned, re.DOTALL)
        if match and match[1].istitle() and match[1].lower() in COMMON_OPENERS:
            cleaned = match[1].lower() + match[2]
    context = plan.context
    if context is None:
        return cleaned if plan.style == "insert" else standalone
    before, after = context.before, context.after
    # Avoid duplicate punctuation at a splice, including standalone inserts.
    if after[:1] in (".", "!", "?", ",", ";", ":") and cleaned.endswith(tuple(".!?,;:")):
        cleaned = cleaned.rstrip(".!?,;:")
    leading = ""
    trailing = ""
    word_splice = bool(before and after and before[-1].isalnum() and after[0].isalnum())
    if (
        (
            before
            and not word_splice
            and not before[-1].isspace()
            and before[-1] not in '([{"\u201c\u2018/\u2014-'
        )
        and cleaned
        and cleaned[0] not in ',.;:!?)]}"\u201d\u2019'
    ):
        leading = " "
    if after:
        if (
            not word_splice
            and not after[0].isspace()
            and after[0] not in ',.;:!?)]}"\u201d\u2019/\u2014-'
        ):
            trailing = " "
    elif plan.style == "standalone":
        # Retain the configured suffix at the end of a paragraph/document.
        trailing = standalone[len(standalone.rstrip()) :]
    return leading + cleaned + trailing
