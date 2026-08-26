import pytest

import remote_ops_workspace.terminal_highlighting as highlighting_module
from remote_ops_workspace.terminal_highlighting import (
    TerminalHighlightFragment,
    TerminalSyntaxRule,
    default_terminal_syntax_rules,
    highlight_terminal_text,
    parse_terminal_syntax_rules,
    terminal_highlight_fragments,
    terminal_syntax_rule_keys,
)


def test_default_terminal_highlighting_marks_mobaxterm_style_tokens() -> None:
    spans = highlight_terminal_text(
        "$ ssh admin@192.0.2.10\n"
        "[note] X11 forwarding requested\n"
        "warning: timed out waiting for /var/log/app.log\n"
        "ready\n"
    )
    by_key = {span.rule_key: span for span in spans}

    assert {"prompt", "note", "warning", "success"} <= set(by_key)
    assert "192.0.2.10" in by_key["prompt"].text
    assert by_key["note"].color == "#d7ba7d"
    assert "timed out" in by_key["warning"].text
    assert by_key["success"].text == "ready"
    assert "error" in terminal_syntax_rule_keys()


def test_terminal_highlight_fragments_cover_plain_and_colored_text() -> None:
    text = (
        "ok on 192.0.2.10\n"
        "https://192.0.2.10:9090/\n"
        "$ curl https://example.test/status\n"
        "plain\n"
    )
    fragments = terminal_highlight_fragments(text)

    assert "".join(fragment.text for fragment in fragments) == text
    assert any(fragment.rule_key == "success" for fragment in fragments)
    assert any(fragment.rule_key == "ipv4" for fragment in fragments)
    links = [fragment for fragment in fragments if fragment.rule_key == "url"]
    assert [link.text for link in links] == [
        "https://192.0.2.10:9090/",
        "https://example.test/status",
    ]
    assert all(link.color == "#54ccef" for link in links)
    assert any(
        fragment.rule_key == "prompt" and fragment.text == "$ curl "
        for fragment in fragments
    )
    assert any(fragment.rule_key == "plain" and fragment.text for fragment in fragments)


def test_custom_terminal_syntax_rules_are_validated_and_applied() -> None:
    rules = parse_terminal_syntax_rules(
        [
            {
                "key": "deploy",
                "label": "Deploy keyword",
                "pattern": r"deploy-\d+",
                "color": "#00ffaa",
            }
        ]
    )
    spans = highlight_terminal_text("job deploy-42 finished", rules)

    assert len(spans) == 1
    assert spans[0].to_dict() == {
        "start": 4,
        "end": 13,
        "text": "deploy-42",
        "rule_key": "deploy",
        "label": "Deploy keyword",
        "color": "#00ffaa",
    }


def test_custom_terminal_syntax_rules_reject_bad_color_and_duplicate_keys() -> None:
    with pytest.raises(ValueError, match="#RRGGBB"):
        parse_terminal_syntax_rules([{"key": "bad", "pattern": "x", "color": "red"}])

    with pytest.raises(ValueError, match="duplicate"):
        parse_terminal_syntax_rules(
            [
                {"key": "dup", "pattern": "x", "color": "#ffffff"},
                {"key": "dup", "pattern": "y", "color": "#000000"},
            ]
        )


def test_terminal_rule_serialization_and_case_insensitive_matching() -> None:
    rules = parse_terminal_syntax_rules(
        [
            {
                "label": "Deploy",
                "pattern": "ready",
                "color": "#ABCDEF",
                "ignore_case": True,
            }
        ]
    )

    assert default_terminal_syntax_rules()
    assert rules[0].to_dict() == {
        "key": "custom-1",
        "label": "Deploy",
        "pattern": "ready",
        "color": "#abcdef",
        "flags": rules[0].flags,
    }
    assert highlight_terminal_text("READY", rules)[0].text == "READY"
    assert TerminalHighlightFragment("plain").to_dict() == {
        "text": "plain",
        "rule_key": "plain",
        "label": "Plain text",
        "color": "",
    }


def test_terminal_highlighting_handles_empty_and_zero_width_matches() -> None:
    zero_width = TerminalSyntaxRule("empty", "Empty", r"(?=x)", "#ffffff")
    exact = TerminalSyntaxRule("exact", "Exact", r"x", "#ffffff")

    assert highlight_terminal_text("x", (zero_width, exact))[0].rule_key == "exact"
    assert terminal_highlight_fragments("x", (exact,)) == (
        TerminalHighlightFragment("x", "exact", "Exact", "#ffffff"),
    )
    assert terminal_highlight_fragments("") == ()


@pytest.mark.parametrize(
    ("item", "message"),
    [
        ({"key": "missing", "pattern": ""}, "is required"),
        ({"key": "bad key", "pattern": "x"}, "terminal syntax rule key"),
    ],
)
def test_terminal_syntax_rules_reject_missing_patterns_and_invalid_keys(item, message) -> None:
    with pytest.raises(ValueError, match=message):
        parse_terminal_syntax_rules([item])


def test_terminal_syntax_rules_defensively_reject_empty_cleaned_pattern(monkeypatch) -> None:
    original_clean_text = highlighting_module.safe.clean_text

    def clean_text(value, label, **kwargs):
        if label == "terminal syntax rule pattern":
            return ""
        return original_clean_text(value, label, **kwargs)

    monkeypatch.setattr(
        "remote_ops_workspace.terminal_highlighting.safe.clean_text",
        clean_text,
    )

    with pytest.raises(ValueError, match="requires a pattern"):
        parse_terminal_syntax_rules([{"key": "empty", "pattern": "ignored"}])


@pytest.mark.parametrize("text", ["bad\x00text", "bad\x7ftext"])
def test_terminal_highlighting_rejects_unsupported_control_characters(text: str) -> None:
    with pytest.raises(ValueError, match="unsupported control characters"):
        highlight_terminal_text(text)


def test_terminal_highlighting_empty_text_has_no_spans() -> None:
    assert highlight_terminal_text("") == ()
