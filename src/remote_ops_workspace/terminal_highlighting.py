from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from . import command_safety as safe


@dataclass(frozen=True, slots=True)
class TerminalSyntaxRule:
    key: str
    label: str
    pattern: str
    color: str
    flags: int = re.MULTILINE

    def compile(self) -> re.Pattern[str]:
        return re.compile(self.pattern, self.flags)

    def to_dict(self) -> dict[str, object]:
        return {
            "key": self.key,
            "label": self.label,
            "pattern": self.pattern,
            "color": self.color,
            "flags": self.flags,
        }


@dataclass(frozen=True, slots=True)
class TerminalHighlightSpan:
    start: int
    end: int
    text: str
    rule_key: str
    label: str
    color: str

    def to_dict(self) -> dict[str, object]:
        return {
            "start": self.start,
            "end": self.end,
            "text": self.text,
            "rule_key": self.rule_key,
            "label": self.label,
            "color": self.color,
        }


@dataclass(frozen=True, slots=True)
class TerminalHighlightFragment:
    text: str
    rule_key: str = "plain"
    label: str = "Plain text"
    color: str = ""

    def to_dict(self) -> dict[str, str]:
        return {
            "text": self.text,
            "rule_key": self.rule_key,
            "label": self.label,
            "color": self.color,
        }


DEFAULT_TERMINAL_SYNTAX_RULES: tuple[TerminalSyntaxRule, ...] = (
    TerminalSyntaxRule("prompt", "Shell prompt", r"(?m)^\$ .+$", "#7cc7ff"),
    TerminalSyntaxRule("note", "Note marker", r"\[note\][^\n]*", "#d7ba7d"),
    TerminalSyntaxRule(
        "error",
        "Error marker",
        r"(?i)(?:\[(?:error|fatal)\]|\b(?:error|failed|denied|refused|fatal)\b)[^\n]*",
        "#ff6b6b",
    ),
    TerminalSyntaxRule(
        "warning",
        "Warning marker",
        r"(?i)(?:\[(?:warn|warning)\]|\b(?:warn|warning|timeout|timed out)\b)[^\n]*",
        "#f5c84c",
    ),
    TerminalSyntaxRule("success", "Success marker", r"(?i)\b(ok|success|ready|connected|passed)\b", "#73d673"),
    TerminalSyntaxRule(
        "ipv4",
        "IPv4 address",
        r"\b(?:(?:25[0-5]|2[0-4]\d|1?\d?\d)\.){3}(?:25[0-5]|2[0-4]\d|1?\d?\d)\b",
        "#4ec9b0",
    ),
    TerminalSyntaxRule("path", "Filesystem path", r"(?<!\w)(?:[A-Za-z]:\\[^\s]+|/(?:[^\s/]+/)*[^\s/]*)", "#c586c0"),
)


def default_terminal_syntax_rules() -> tuple[TerminalSyntaxRule, ...]:
    return DEFAULT_TERMINAL_SYNTAX_RULES


def terminal_syntax_rule_keys(rules: tuple[TerminalSyntaxRule, ...] | None = None) -> tuple[str, ...]:
    return tuple(rule.key for rule in (rules or DEFAULT_TERMINAL_SYNTAX_RULES))


def parse_terminal_syntax_rules(items: list[dict[str, Any]]) -> tuple[TerminalSyntaxRule, ...]:
    rules: list[TerminalSyntaxRule] = []
    seen: set[str] = set()
    for index, item in enumerate(items):
        key = _rule_key(str(item.get("key") or f"custom-{index + 1}"))
        if key in seen:
            raise ValueError(f"duplicate terminal syntax rule key: {key}")
        label = safe.clean_text(str(item.get("label") or key), "terminal syntax rule label")
        pattern = safe.clean_text(str(item.get("pattern") or ""), "terminal syntax rule pattern")
        if not pattern:
            raise ValueError(f"terminal syntax rule {key} requires a pattern")
        color = _hex_color(str(item.get("color") or "#ffffff"), f"terminal syntax rule {key} color")
        flags = re.MULTILINE
        if item.get("ignore_case") is True:
            flags |= re.IGNORECASE
        rule = TerminalSyntaxRule(key=key, label=label, pattern=pattern, color=color, flags=flags)
        rule.compile()
        rules.append(rule)
        seen.add(key)
    return tuple(rules)


def highlight_terminal_text(
    text: str,
    rules: tuple[TerminalSyntaxRule, ...] | None = None,
) -> tuple[TerminalHighlightSpan, ...]:
    source = _terminal_text(text)
    if not source:
        return ()
    spans: list[TerminalHighlightSpan] = []
    occupied = [False] * len(source)
    for rule in rules or DEFAULT_TERMINAL_SYNTAX_RULES:
        for match in rule.compile().finditer(source):
            start, end = match.span()
            if start == end or any(occupied[start:end]):
                continue
            for index in range(start, end):
                occupied[index] = True
            spans.append(
                TerminalHighlightSpan(
                    start=start,
                    end=end,
                    text=source[start:end],
                    rule_key=rule.key,
                    label=rule.label,
                    color=rule.color,
                )
            )
    return tuple(sorted(spans, key=lambda span: (span.start, span.end)))


def terminal_highlight_fragments(
    text: str,
    rules: tuple[TerminalSyntaxRule, ...] | None = None,
) -> tuple[TerminalHighlightFragment, ...]:
    source = _terminal_text(text)
    if not source:
        return ()
    spans = highlight_terminal_text(source, rules)
    fragments: list[TerminalHighlightFragment] = []
    cursor = 0
    for span in spans:
        if span.start > cursor:
            fragments.append(TerminalHighlightFragment(source[cursor : span.start]))
        fragments.append(TerminalHighlightFragment(span.text, span.rule_key, span.label, span.color))
        cursor = span.end
    if cursor < len(source):
        fragments.append(TerminalHighlightFragment(source[cursor:]))
    return tuple(fragment for fragment in fragments if fragment.text)


def _rule_key(value: str) -> str:
    key = safe.option_value(value.strip().lower(), "terminal syntax rule key")
    if not re.fullmatch(r"[a-z0-9][a-z0-9_.-]{0,63}", key):
        raise ValueError("terminal syntax rule key must use lowercase letters, numbers, dots, dashes or underscores")
    return key


def _hex_color(value: str, label: str) -> str:
    color = safe.option_value(value.strip(), label)
    if not re.fullmatch(r"#[0-9A-Fa-f]{6}", color):
        raise ValueError(f"{label} must be a #RRGGBB color")
    return color.lower()


def _terminal_text(value: str) -> str:
    text = str(value)
    for char in text:
        codepoint = ord(char)
        if codepoint < 32 and char not in {"\n", "\r", "\t"}:
            raise ValueError("terminal text contains unsupported control characters")
        if codepoint == 127:
            raise ValueError("terminal text contains unsupported control characters")
    return text
