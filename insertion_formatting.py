"""Local, conservative formatting at an editor's insertion point."""

from __future__ import annotations

import re
from dataclasses import dataclass

INSERTION_MODES = ("auto", "standalone", "insert")

# Empty rich-text paragraphs may contain caret anchors or object placeholders.
_EDITOR_ANCHORS = str.maketrans(
    "",
    "",
    "\u200b\u200e\u200f\u202a\u202b\u202c\u202d\u202e\u2060\u2066\u2067\u2068\u2069\ufeff\ufffc",
)


def visible_context(text: str) -> str:
    return (
        text.translate(_EDITOR_ANCHORS)
        .replace("\r\n", "\n")
        .replace("\r", "\n")
        .replace("\u2028", "\n")
        .replace("\u2029", "\n")
    )


def boundary_kind(text: str, *, before: bool) -> str:
    text = visible_context(text)
    if not text:
        return "empty"
    char = text[-1] if before else text[0]
    if char == "\n":
        return "newline"
    if char.isspace():
        return "space"
    if char in ".!?":
        return "sentence"
    if char in "([{":
        return "opening"
    if char in ')]}"\u201d\u2019':
        return "closing"
    if char.isalnum():
        return "word"
    if char in ",;:/-":
        return "punctuation"
    return "other"


def initial_case(text: str) -> str:
    text = text.lstrip()
    if not text:
        return "empty"
    return "upper" if text[0].isupper() else ("lower" if text[0].islower() else "other")


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
    selected_lowercase_word: bool = False
    selected_trailing_space: bool = False


@dataclass(frozen=True)
class InsertionPlan:
    style: str
    label: str
    context: CaretContext | None = None
    trim_terminal: bool = True
    reason: str = "explicit"


def choose_plan(mode: str, context: CaretContext | None, *, bullet=False) -> InsertionPlan:
    if bullet:
        return InsertionPlan("standalone", "Bullets", reason="bullet")
    if mode == "standalone":
        return InsertionPlan("standalone", "Standalone")
    if mode == "insert":
        return InsertionPlan("insert", "Insert", context)
    if context is None:
        return InsertionPlan("standalone", "Auto: unavailable", reason="no_context")
    # A newline is a paragraph boundary even after trailing indentation.
    line = visible_context(context.before).rsplit("\n", 1)[-1].rstrip()
    start = not line or bool(re.search(r"[.!?][\"\u201d\u2019)\]]*$", line))
    start = start or bool(re.fullmatch(r"[\s(\[{\"\u201c\u2018]*|(?:[-*\u2022]|\d+[.)])\s*", line))
    return InsertionPlan(
        "standalone" if start else "insert",
        "Auto: standalone" if start else "Auto: insert",
        context,
        trim_terminal=bool(visible_context(context.after).split("\n", 1)[0].strip()),
        reason="empty_paragraph"
        if not line
        else (
            "boundary"
            if start
            else ("word_replacement" if context.selected_lowercase_word else "continuation")
        ),
    )


def format_insertion(text: str, plan: InsertionPlan, standalone: str) -> str:
    if not text.strip():
        return ""
    if plan.style == "standalone":
        cleaned = standalone.rstrip()
    else:
        cleaned = text.strip()
        continuation = plan.trim_terminal
        # Remove a provider's sentence-ending punctuation, preserving ellipses,
        # decimals, initials, and abbreviations that have meaningful final dots.
        # At the end of existing text, keep punctuation to finish the sentence.
        if continuation and cleaned.endswith(("!", "?")):
            cleaned = cleaned.rstrip("!?")
        elif continuation and cleaned.endswith(".") and not cleaned.endswith(".."):
            word = cleaned.split()[-1]
            abbreviation = word.lower() in {"etc.", "e.g.", "i.e.", "mr.", "mrs.", "dr.", "vs."}
            if not abbreviation and (word == "I." or not re.fullmatch(r"(?:[A-Za-z]\.)+", word)):
                cleaned = cleaned[:-1]
        match = re.match(r"([A-Za-z]+)(.*)", cleaned, re.DOTALL)
        replacement_start = re.match(r"([^\W\d_]+(?:['\u2019-][^\W\d_]+)*)(.*)", cleaned, re.DOTALL)
        if match and match[1].istitle() and match[1].lower() in COMMON_OPENERS:
            cleaned = match[1].lower() + match[2]
        elif (
            plan.context is not None
            and plan.context.selected_lowercase_word
            and replacement_start is not None
            and replacement_start[1] != "I"
            and replacement_start[1].istitle()
        ):
            # Replacing an explicitly lowercase word supplies a stronger case
            # signal than a provider's default sentence-initial capitalization.
            cleaned = replacement_start[1].lower() + replacement_start[2]
    context = plan.context
    if context is None:
        return cleaned if plan.style == "insert" else standalone
    before, after = visible_context(context.before), visible_context(context.after)
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
    elif context.selected_trailing_space:
        trailing = " "
    return leading + cleaned + trailing
