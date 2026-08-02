"""
Tests for dashboard.settings: local on-device settings persistence.
"""

import json

from dashboard import corners, settings


class TestLoad:
    def test_missing_file_returns_defaults(self, tmp_path):
        path = tmp_path / "settings.json"

        assert settings.load(str(path)) == settings.DEFAULTS

    def test_corrupt_json_falls_back_to_defaults(self, tmp_path):
        path = tmp_path / "settings.json"
        path.write_text("{not valid json")

        assert settings.load(str(path)) == settings.DEFAULTS

    def test_non_dict_json_falls_back_to_defaults(self, tmp_path):
        path = tmp_path / "settings.json"
        path.write_text("[1, 2, 3]")

        assert settings.load(str(path)) == settings.DEFAULTS

    def test_saved_values_override_defaults(self, tmp_path):
        path = tmp_path / "settings.json"
        path.write_text(
            json.dumps({"corner_style": "blocky", "corner_radius": "small", "font_choice": "default"})
        )

        loaded = settings.load(str(path))

        assert loaded == {"corner_style": "blocky", "corner_radius": "small", "font_choice": "default"}

    def test_partial_file_fills_in_missing_keys_from_defaults(self, tmp_path):
        # font_choice isn't used as the example value here -- "default" is
        # currently its only valid choice (see dashboard.settings.
        # VALID_FONT_CHOICES's comment), so it can't demonstrate an
        # override the way corner_style can.
        path = tmp_path / "settings.json"
        path.write_text(json.dumps({"corner_style": "blocky"}))

        loaded = settings.load(str(path))

        assert loaded["corner_style"] == "blocky"
        assert loaded["corner_radius"] == settings.DEFAULTS["corner_radius"]
        assert loaded["font_choice"] == settings.DEFAULTS["font_choice"]

    def test_unknown_corner_style_falls_back_to_default(self, tmp_path):
        # A hand-edited or version-skewed settings.json must not crash
        # SettingsPage.setup() later -- RadioButton(current_index=...) /
        # CORNER_STYLE_ORDER.index() would raise on an unrecognized value.
        path = tmp_path / "settings.json"
        path.write_text(json.dumps({"corner_style": "extra-chunky"}))

        assert settings.load(str(path))["corner_style"] == settings.DEFAULTS["corner_style"]

    def test_unknown_corner_radius_falls_back_to_default(self, tmp_path):
        path = tmp_path / "settings.json"
        path.write_text(json.dumps({"corner_radius": "gigantic"}))

        assert settings.load(str(path))["corner_radius"] == settings.DEFAULTS["corner_radius"]

    def test_unknown_font_choice_falls_back_to_default(self, tmp_path):
        # Same crash risk as above -- FONT_CHOICE_ORDER.index() in
        # dashboard/settings_page.py raises on an unrecognized choice.
        path = tmp_path / "settings.json"
        path.write_text(json.dumps({"font_choice": "comic-sans"}))

        assert settings.load(str(path))["font_choice"] == "default"

    def test_unknown_keys_are_ignored(self, tmp_path):
        path = tmp_path / "settings.json"
        path.write_text(json.dumps({"font_choice": "inter", "mystery_key": "??"}))

        loaded = settings.load(str(path))

        assert "mystery_key" not in loaded


class TestSave:
    def test_save_writes_readable_json(self, tmp_path):
        path = tmp_path / "settings.json"

        settings.save(
            {"corner_style": "blocky", "corner_radius": "medium", "font_choice": "default"}, str(path)
        )

        assert settings.load(str(path)) == {
            "corner_style": "blocky",
            "corner_radius": "medium",
            "font_choice": "default",
        }

    def test_save_merges_partial_dict_over_defaults(self, tmp_path):
        # font_choice isn't used as the example value here -- see
        # test_partial_file_fills_in_missing_keys_from_defaults above.
        path = tmp_path / "settings.json"

        merged = settings.save({"corner_radius": "medium"}, str(path))

        assert merged["corner_radius"] == "medium"
        assert merged["corner_style"] == settings.DEFAULTS["corner_style"]
        assert merged["font_choice"] == settings.DEFAULTS["font_choice"]

    def test_save_drops_unknown_keys(self, tmp_path):
        path = tmp_path / "settings.json"

        merged = settings.save({"font_choice": "inter", "bogus": True}, str(path))

        assert "bogus" not in merged
        assert "bogus" not in settings.load(str(path))

    def test_save_returns_the_merged_dict(self, tmp_path):
        path = tmp_path / "settings.json"

        merged = settings.save({"corner_radius": "small"}, str(path))

        assert merged == settings.load(str(path))

    def test_save_rejects_invalid_values_falling_back_to_defaults(self, tmp_path):
        path = tmp_path / "settings.json"

        merged = settings.save(
            {"corner_style": "extra-chunky", "corner_radius": "gigantic", "font_choice": "wingdings"},
            str(path),
        )

        assert merged == settings.DEFAULTS


def test_defaults_reproduce_theme_class_defaults():
    # dashboard.theme.CompressoTheme's own class-level corner_style/
    # corner_radius/font_choice defaults -- checked against the raw
    # values rather than importing CompressoTheme itself, to avoid a
    # dashboard.settings -> dashboard.theme import (theme already imports
    # this module's sibling dashboard.font/font5x5, not settings, but
    # there's no need to introduce the coupling just for this check).
    assert settings.DEFAULTS["corner_style"] == "smooth"
    assert settings.DEFAULTS["corner_radius"] == "large"
    assert settings.DEFAULTS["corner_radius"] in corners.RADIUS_CHOICES
    assert settings.DEFAULTS["font_choice"] == "default"
