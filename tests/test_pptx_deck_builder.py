"""Offline tests for the blueprint deck builder and its registry wiring."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest
from PIL import Image
from pptx import Presentation
from pptx.enum.shapes import MSO_SHAPE_TYPE
from pptx.util import Inches

from meddraft_ai.core.skill_registry import REGISTERED_PROMPT_SUBDIRS, SkillRegistry

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "meddraft_ai" / "prompts" / "pptx" / "scripts" / "deck_builder.py"
FETCH_SCRIPT = REPO_ROOT / "meddraft_ai" / "prompts" / "pptx" / "scripts" / "fetch_figures.py"


def _load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


deck_builder = _load_module(SCRIPT, "meddraft_deck_builder")
fetch_cli = _load_module(FETCH_SCRIPT, "meddraft_fetch_figures")


def _figure(path: Path) -> None:
    Image.new("RGB", (1600, 1200), (20, 90, 110)).save(path, format="PNG")


def _blueprint(tmp_path: Path) -> dict:
    _figure(tmp_path / "fig.png")
    return {
        "title": "Test deck",
        "subtitle": "A six-slide walkthrough",
        "accent": "#0E7C86",
        "sources": ["Source A", "Source B"],
        "slides": [
            {"kind": "cover", "title": "Test deck", "subtitle": "A six-slide walkthrough"},
            {"kind": "agenda", "title": "Agenda", "bullets": ["One", "Two", "Three"]},
            {"kind": "section", "kicker": "SECTION 01", "title": "Anatomy"},
            {
                "kind": "content",
                "title": "A claim, not a label",
                "bullets": ["Evidence one.", "Evidence two.", "Evidence three."],
                "takeaway": "This is the so-what.",
                "notes": "Say this out loud.",
            },
            {
                "kind": "figure",
                "title": "Histology",
                "image_path": "fig.png",
                "caption": "A caption.",
                "credit": "Source: example.org (CC BY 4.0)",
                "bullets": ["Reading cue."],
            },
            {"kind": "summary", "title": "Key takeaways", "bullets": ["One", "Two"]},
        ],
    }


class TestValidateBlueprint:
    def test_flags_figure_without_image_or_query(self):
        warnings = deck_builder.validate_blueprint(
            {"title": "T", "slides": [{"kind": "figure", "title": "F"}]}
        )
        assert any("needs image_path or query" in item for item in warnings)

    def test_query_only_figure_is_a_reminder_not_an_error(self):
        warnings = deck_builder.validate_blueprint(
            {"title": "T", "slides": [{"kind": "figure", "query": "sulcus histology"}]}
        )
        assert any("query is ready" in item for item in warnings)

    def test_unknown_kind_is_flagged(self):
        warnings = deck_builder.validate_blueprint(
            {"title": "T", "slides": [{"kind": "quote", "title": "Q"}]}
        )
        assert any("unknown kind" in item for item in warnings)

    def test_empty_content_slide_is_flagged(self):
        warnings = deck_builder.validate_blueprint(
            {"title": "T", "slides": [{"kind": "content", "title": "C"}]}
        )
        assert any("no bullets" in item for item in warnings)


class TestFitSize:
    def test_long_text_gets_smaller_type(self):
        short = deck_builder.fit_size(["Short."], 8.0, 2.0, base=40, minimum=12)
        long = deck_builder.fit_size(
            ["A much longer paragraph. " * 12], 8.0, 2.0, base=40, minimum=12
        )
        assert long < short

    def test_never_goes_below_minimum(self):
        size = deck_builder.fit_size(["word " * 500], 3.0, 0.5, base=40, minimum=14)
        assert size == 14


class TestBuildDeck:
    def test_builds_all_six_slide_kinds(self, tmp_path):
        blueprint = _blueprint(tmp_path)
        out = tmp_path / "deck.pptx"

        result = deck_builder.build_deck(blueprint, out, base_dir=tmp_path)

        assert result["success"] is True
        assert result["slides"] == 6
        assert result["warnings"] == []
        assert out.exists()

    def test_canvas_is_16_by_9(self, tmp_path):
        blueprint = _blueprint(tmp_path)
        out = tmp_path / "deck.pptx"
        deck_builder.build_deck(blueprint, out, base_dir=tmp_path)

        prs = Presentation(str(out))
        assert prs.slide_width == Inches(13.333)
        assert prs.slide_height == Inches(7.5)

    def test_speaker_notes_are_written(self, tmp_path):
        blueprint = _blueprint(tmp_path)
        out = tmp_path / "deck.pptx"
        deck_builder.build_deck(blueprint, out, base_dir=tmp_path)

        prs = Presentation(str(out))
        notes = prs.slides[3].notes_slide.notes_text_frame.text
        assert notes == "Say this out loud."

    def test_figure_slide_embeds_a_picture(self, tmp_path):
        blueprint = _blueprint(tmp_path)
        out = tmp_path / "deck.pptx"
        deck_builder.build_deck(blueprint, out, base_dir=tmp_path)

        prs = Presentation(str(out))
        figure_slide = prs.slides[4]
        pictures = [s for s in figure_slide.shapes if s.shape_type == MSO_SHAPE_TYPE.PICTURE]
        assert len(pictures) == 1

    def test_missing_figure_degrades_to_a_slot_not_a_crash(self, tmp_path):
        blueprint = _blueprint(tmp_path)
        blueprint["slides"][4]["image_path"] = "missing.png"

        out = tmp_path / "deck.pptx"
        result = deck_builder.build_deck(blueprint, out, base_dir=tmp_path)

        assert result["success"] is True
        assert out.exists()

    def test_unknown_kind_renders_as_content(self, tmp_path):
        blueprint = {
            "title": "T",
            "slides": [{"kind": "quote", "title": "Not a real kind", "bullets": ["One."]}],
        }
        out = tmp_path / "deck.pptx"
        result = deck_builder.build_deck(blueprint, out, base_dir=tmp_path)

        assert result["slides"] == 1
        assert any("unknown kind" in item for item in result["warnings"])

    def test_accent_override_is_accepted(self, tmp_path):
        blueprint = _blueprint(tmp_path)
        out = tmp_path / "deck.pptx"
        result = deck_builder.build_deck(blueprint, out, base_dir=tmp_path, accent="#C0392B")
        assert result["success"] is True


class TestLoadBlueprint:
    def test_reads_utf8_with_bom(self, tmp_path):
        path = tmp_path / "deck.json"
        path.write_bytes(b"\xef\xbb\xbf" + json.dumps({"title": "T"}).encode("utf-8"))
        assert deck_builder.load_blueprint(path)["title"] == "T"

    def test_reads_utf16_from_powershell_redirect(self, tmp_path):
        path = tmp_path / "deck.json"
        path.write_bytes(json.dumps({"title": "T"}).encode("utf-16"))
        assert deck_builder.load_blueprint(path)["title"] == "T"


class TestRegistryWiring:
    def test_pptx_pack_is_registered(self):
        assert "pptx" in REGISTERED_PROMPT_SUBDIRS
    def test_registry_resolves_the_pack_skill_md(self):
        registry = SkillRegistry().load()
        content = registry.get_skill("pptx")
        assert "deck_builder.py" in content
        assert "fetch_figures.py" in content

    @pytest.mark.parametrize(
        "task",
        [
            "Build a PowerPoint deck for the seminar",
            "create lecture slides about periodontal anatomy",
            "make a presentation deck for journal club",
        ],
    )
    def test_deck_tasks_route_to_pptx(self, task):
        assert SkillRegistry().match_skill_for_task(task) == "pptx"

    def test_manuscript_tasks_do_not_route_to_pptx(self):
        result = SkillRegistry().match_skill_for_task("revise the discussion section of this paper")
        assert result != "pptx"


class TestFetchFiguresBlueprintWriteBack:
    def _blueprint(self, tmp_path: Path) -> Path:
        path = tmp_path / "deck.json"
        path.write_text(
            json.dumps(
                {
                    "title": "Deck",
                    "slides": [
                        {
                            "kind": "figure",
                            "title": "Histology",
                            "query": "gingival sulcus histology",
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )
        return path

    def _fake_result(self, tmp_path: Path) -> dict:
        figures_dir = tmp_path / "figures"
        figures_dir.mkdir()
        image = figures_dir / "slide-01-histology.png"
        Image.new("RGB", (1200, 900), (10, 80, 100)).save(image, format="PNG")
        return {
            "success": True,
            "out_dir": str(figures_dir),
            "count": 1,
            "failed": 0,
            "providers": {"serpapi": 1},
            "failures": [],
            "figures": [
                {
                    "id": "slide-01-histology",
                    "query": "gingival sulcus histology",
                    "title": "Sulcular epithelium",
                    "provider": "serpapi",
                    "image_url": "https://example.org/full.png",
                    "context_url": "https://example.org/page",
                    "path": str(image),
                    "width": 1200,
                    "height": 900,
                    "format": "PNG",
                    "bytes": image.stat().st_size,
                    "sha256": "a" * 64,
                }
            ],
        }

    def test_writes_image_path_and_credit_back(self, tmp_path, monkeypatch, capsys):
        blueprint = self._blueprint(tmp_path)
        monkeypatch.setattr(
            fetch_cli, "fetch_figures", lambda *a, **k: self._fake_result(tmp_path)
        )

        code = fetch_cli.main(["--blueprint", str(blueprint), "--json"])
        payload = json.loads(capsys.readouterr().out)

        assert code == 0
        assert payload["blueprint_slides_updated"] == 1
        updated = json.loads(blueprint.read_text(encoding="utf-8"))
        slide = updated["slides"][0]
        assert slide["image_path"] == "figures/slide-01-histology.png"
        assert slide["credit"] == "Source: https://example.org/page"
        assert slide["caption"] == "Sulcular epithelium"

    def test_no_write_keeps_the_blueprint_untouched(self, tmp_path, monkeypatch, capsys):
        blueprint = self._blueprint(tmp_path)
        original = blueprint.read_text(encoding="utf-8")
        monkeypatch.setattr(
            fetch_cli, "fetch_figures", lambda *a, **k: self._fake_result(tmp_path)
        )

        fetch_cli.main(["--blueprint", str(blueprint), "--no-write", "--json"])

        assert blueprint.read_text(encoding="utf-8") == original
