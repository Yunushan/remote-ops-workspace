import pytest

from remote_ops_workspace.terminal_highlighting import (
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
