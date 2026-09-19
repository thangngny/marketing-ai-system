import re
from pathlib import Path


def test_nine_hermes_skills_follow_frontmatter_contract():
    root = Path(__file__).parents[1] / "hermes" / "skills"
    files = sorted(root.glob("*/SKILL.md"))
    assert len(files) == 9
    for file in files:
        text = file.read_text(encoding="utf-8")
        name = re.search(r"^name: (.+)$", text, re.MULTILINE)
        description = re.search(r'^description: "(.+)"$', text, re.MULTILINE)
        assert name and name.group(1) == file.parent.name
        assert description and len(description.group(1)) <= 60
        assert description.group(1).endswith(".")
        assert "## Verification" in text
