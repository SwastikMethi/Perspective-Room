"""T01 and configuration loading: personas, defaults, cases, fixture evidence, templates."""

import json
import shutil
from pathlib import Path

import pytest
import yaml

from app.catalog import ConfigError, load_catalog
from app.prompts.loader import template

ROSTER = ["mentor", "skeptic", "explorer", "strategist", "engineer", "customer", "civic", "health"]


def contract_enum(handoff: Path, name: str) -> list[str]:
    spec = yaml.safe_load((handoff / "contracts/openapi.yaml").read_text())
    return spec["components"]["schemas"][name]["enum"]


def copy_handoff(src: Path, dst: Path) -> Path:
    shutil.copytree(src / "config", dst / "config")
    shutil.copytree(src / "fixtures", dst / "fixtures")
    return dst


def edit_json(path: Path, fn) -> None:
    data = json.loads(path.read_text())
    fn(data)
    path.write_text(json.dumps(data))


def test_loads_exactly_eight_contract_personas_in_roster_order(handoff_dir):
    cat = load_catalog(handoff_dir)
    assert cat.order == ROSTER
    assert sorted(cat.personas) == sorted(contract_enum(handoff_dir, "PersonaId"))
    assert cat.personas["customer"].display_name == "Customer advocate"


def test_default_selection_is_the_valid_trio(handoff_dir):
    assert load_catalog(handoff_dir).default_selection == ["mentor", "skeptic", "explorer"]


def test_duplicate_persona_id_fails_clearly(handoff_dir, tmp_path):
    root = copy_handoff(handoff_dir, tmp_path)

    def dup(data):
        data["personas"][1]["id"] = "mentor"

    edit_json(root / "config/personalities.json", dup)
    with pytest.raises(ConfigError, match="duplicate persona id: mentor"):
        load_catalog(root)


def test_missing_mandatory_profile_field_fails(handoff_dir, tmp_path):
    root = copy_handoff(handoff_dir, tmp_path)
    edit_json(root / "config/personalities.json", lambda d: d["personas"][0].pop("voice"))
    with pytest.raises(ConfigError, match="voice"):
        load_catalog(root)


def test_wrong_persona_count_fails(handoff_dir, tmp_path):
    root = copy_handoff(handoff_dir, tmp_path)
    edit_json(root / "config/personalities.json", lambda d: d["personas"].pop())
    with pytest.raises(ConfigError, match="exactly 8"):
        load_catalog(root)


def test_unknown_defaults_key_is_rejected(handoff_dir, tmp_path):
    root = copy_handoff(handoff_dir, tmp_path)
    edit_json(root / "config/app.defaults.json", lambda d: d["limits"].update(surprise=1))
    with pytest.raises(ConfigError, match="surprise"):
        load_catalog(root)


def test_defaults_expose_authoritative_limits(handoff_dir):
    d = load_catalog(handoff_dir).defaults
    assert (d.limits.auto_contributions, d.limits.panel_contributions) == (3, 8)
    assert d.limits.provider_attempts_per_turn == 40
    assert d.timeouts_seconds.turn_deadline == 600
    assert d.jev_thresholds.routing_confidence == 0.35


def test_persona_hash_is_stable_and_content_sensitive(handoff_dir, tmp_path):
    a = load_catalog(handoff_dir).persona_hash("skeptic")
    assert a == load_catalog(handoff_dir).persona_hash("skeptic")
    root = copy_handoff(handoff_dir, tmp_path)
    edit_json(root / "config/personalities.json", lambda d: d["personas"][1].update(voice="x"))
    assert load_catalog(root).persona_hash("skeptic") != a


def test_cases_and_fixture_evidence_load(handoff_dir):
    cat = load_catalog(handoff_dir)
    assert len(cat.cases) == 30 and cat.cases_version == "1.0.0"
    assert cat.cases["case_02"].persona_ids == ["civic", "mentor", "skeptic"]
    pack = cat.fixture_packs["00000000-0000-4000-8000-000000000102"]
    assert pack["is_fixture"] is True and pack["sources"][0]["is_fixture"] is True


def test_persona_template_carries_doc06_instruction_and_hash():
    t = template("persona")
    assert "You are one simulated perspective in an idea-development conversation." in t.text
    assert "Do not expose hidden reasoning." in t.text
    assert len(t.sha256) == 64 and t.version == t.sha256[:12]


def test_every_pipeline_template_exists():
    names = [
        "intake",
        "persona",
        "standard",
        "summary",
        "memory",
        "research_search",
        "research_normalize",
    ]
    assert all(template(n).text.strip() for n in names)
