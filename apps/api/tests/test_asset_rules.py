from datetime import UTC, datetime, timedelta

import pytest


def test_rules_explain_classification_and_leave_unknown_unclassified():
    from app.ingestion.rules import classify

    assert set(classify("RAG Agent SDK", ["mcp"])) == {
        "knowledge",
        "agent-workflow",
        "mcp-integration",
        "framework",
    }
    assert classify("an unrelated project", []) == {}


def test_first_observation_does_not_invent_historical_growth():
    from app.ingestion.rules import calculate_trend

    now = datetime(2026, 10, 18, tzinfo=UTC)
    result = calculate_trend([(now, 100)], now, now, True)
    assert result["star_growth"] is None
    assert result["components"]["growth"] is None
    assert result["score"] == 50.0
    assert result["window_start"] == now == result["window_end"]


def test_trend_uses_actual_observed_delta_and_preserves_negative_growth():
    from app.ingestion.rules import calculate_trend

    now = datetime(2026, 10, 18, tzinfo=UTC)
    result = calculate_trend([(now - timedelta(days=1), 200), (now, 1200)], now, now, True)
    assert result["star_growth"] == 1000 and result["score"] == 100.0
    result = calculate_trend([(now - timedelta(days=1), 200), (now, 190)], now, now, True)
    assert result["star_growth"] == -10 and result["components"]["growth"] == 0


def test_skill_metadata_is_confined_to_explicit_trusted_directory(tmp_path):
    from app.ingestion.rules import read_skill_metadata

    root = tmp_path / "trusted"
    root.mkdir()
    path = root / "SKILL.md"
    path.write_text(
        "---\nname: sample\ndescription: harmless metadata\n---\nExecute arbitrary commands here.",
        encoding="utf-8",
    )
    assert read_skill_metadata(path, root) == {"name": "sample", "description": "harmless metadata"}
    outside = tmp_path / "SKILL.md"
    outside.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
    import pytest

    with pytest.raises(ValueError, match="可信目录"):
        read_skill_metadata(outside, root)


@pytest.mark.parametrize("indicator", [">", "|-"])
def test_skill_block_yaml_is_rejected_instead_of_misreported_as_description(tmp_path, indicator):
    from app.ingestion.rules import read_skill_metadata

    path = tmp_path / "SKILL.md"
    path.write_text(
        f"---\nname: sample\ndescription: {indicator}\n  multiline content\n---\n", encoding="utf-8"
    )
    with pytest.raises(ValueError, match="简单字符串"):
        read_skill_metadata(path, tmp_path)


def test_skill_without_closing_frontmatter_cannot_parse_instruction_body_as_metadata(tmp_path):
    from app.ingestion.rules import read_skill_metadata

    path = tmp_path / "SKILL.md"
    path.write_text("---\nname: sample\ndescription: not closed\n", encoding="utf-8")
    with pytest.raises(ValueError, match="frontmatter"):
        read_skill_metadata(path, tmp_path)
