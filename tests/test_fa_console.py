# -*- coding: utf-8 -*-
"""
Golden and behavioural tests for fa_console.

All glyph-stream expectations below were hand-derived from the Unicode
Arabic Presentation Forms tables and verified against the reference
implementation. The autouse ``builtin_engine`` fixture (see ``conftest``)
pins the dependency-free backend so results are identical on machines
that also have ``arabic-reshaper``/``python-bidi`` installed.
"""

import io
import os

import pytest

import fa_console


def cps(string: str) -> list[str]:
    """Code points of *string* as ``'0x....'`` strings."""
    return [hex(ord(c)) for c in string]


def V(*codes: int) -> str:
    """String built from code-point integers."""
    return "".join(chr(c) for c in codes)


# --------------------------------------------------------------------------- #
# Shaping (builtin engine)
# --------------------------------------------------------------------------- #


class TestShaping:
    def test_salam_uses_lam_alef_ligature(self):
        # س (initial) + ل+ا (ligature, final because ل joins backwards) + م (isolated)
        assert cps(fa_console._transformer.shape("سلام")) == [
            "0xfeb3", "0xfefc", "0xfee1",
        ]

    def test_lam_alef_isolated(self):
        # Standalone لا: the lam connects to nothing backwards → isolated ligature.
        assert fa_console._transformer.shape("لا") == V(0xFEFB)

    def test_alef_salam_full_chain(self):
        # ا ل س ل + ا (ligature) م — checks joining across the whole word:
        # alef isolated, lam initial, seen medial, lam-alef final, meem isolated.
        assert cps(fa_console._transformer.shape("السلام")) == [
            "0xfe8d", "0xfedf", "0xfeb4", "0xfefc", "0xfee1",
        ]

    def test_basic_joining(self):
        # ع ل ی — initial / medial / final (Persian yeh).
        assert cps(fa_console._transformer.shape("علی")) == [
            "0xfecb", "0xfee0", "0xfbfd",
        ]

    def test_zwnj_breaks_joining_and_vanishes(self):
        # م ی ZWNJ ر و م — no joining across the ZWNJ; ZWNJ removed.
        assert cps(fa_console._transformer.shape("می‌روم")) == [
            "0xfee3", "0xfbfd", "0xfead", "0xfeed", "0xfee1",
        ]

    def test_right_joining_letters_stay_isolated(self):
        # د ا د — د never joins forward, so every letter stays isolated.
        assert cps(fa_console._transformer.shape("داد")) == [
            "0xfea9", "0xfe8d", "0xfea9",
        ]

    def test_persian_extras(self):
        # گ ژ پ چ — initial/medial/final forms of the Persian-specific glyphs.
        assert cps(fa_console._transformer.shape("گژپچ")) == [
            "0xfb94", "0xfb8b", "0xfb58", "0xfb7b",
        ]

    def test_urdu_pashto_letters(self):
        assert fa_console._transformer.shape("ٹ") == V(0xFB66)   # TTEH isolated
        assert fa_console._transformer.shape("ں") == V(0xFB9E)   # NOON GHUNNA
        assert fa_console._transformer.shape("ھ") == V(0xFBAA)   # HEH DOACHASHMEE
        assert fa_console._transformer.shape("ے") == V(0xFBAE)   # YEH BARREE

    def test_ascii_only_passthrough(self):
        assert fa_console._transformer.shape("hello 123") == "hello 123"


# --------------------------------------------------------------------------- #
# Bidirectional reorder (builtin engine)
# --------------------------------------------------------------------------- #


class TestReorder:
    def test_full_line_reverse_keeps_latin_upright(self):
        # Visual output must contain the Latin word and number unbroken.
        visual = fa_console._transformer.transform_line("متن test 123 فارسی")
        assert "test" in visual and "123" in visual

    def test_decimal_separator_w4(self):
        # UAX #9 rule W4: a dot between two digits belongs to the number.
        visual = fa_console._transformer.transform_line("عدد 3.14 تست")
        assert "3.14" in visual

    def test_persian_decimal_separator_w4(self):
        visual = fa_console._transformer.transform_line("۱۲.۵")
        assert "۱۲.۵" in visual

    def test_thousands_separator_w4(self):
        visual = fa_console._transformer.transform_line("1,234 عدد")
        assert "1,234" in visual

    def test_arabic_separators_always_ltr_tokens(self):
        visual = fa_console._transformer.transform_line("۱٬۰۰۰")
        assert "۱٬۰۰۰" in visual

    def test_brackets_are_mirrored(self):
        visual = fa_console._transformer.transform_line("سلام (تست)")
        assert visual.count("(") == 1 and visual.count(")") == 1

    def test_control_chars_survive(self):
        visual = fa_console._transformer.transform_line("سلام\x07تست")
        assert "\x07" in visual

    def test_latin_only_line_untouched(self):
        assert fa_console._transformer.transform_line("hello (3.14)") == "hello (3.14)"


# --------------------------------------------------------------------------- #
# Terminal detection
# --------------------------------------------------------------------------- #


class TestDetection:
    @pytest.mark.parametrize(
        ("env", "expected"),
        [
            ({}, False),                                   # classic conhost
            ({"WT_SESSION": "x"}, True),                   # Windows Terminal
            ({"TERM_PROGRAM": "vscode"}, False),           # xterm.js → needs the transform
            ({"TERM_PROGRAM": "vscode", "WT_SESSION": "x"}, True),
            ({"TERM_PROGRAM": "mintty"}, True),            # other hosts are trusted
        ],
        ids=["conhost", "wt", "vscode", "wt-wins", "other"],
    )
    def test_modern_terminal(self, monkeypatch, env, expected):
        monkeypatch.delenv("WT_SESSION", raising=False)
        monkeypatch.delenv("TERM_PROGRAM", raising=False)
        for key, value in env.items():
            monkeypatch.setenv(key, value)
        assert fa_console._modern_terminal() is expected


# --------------------------------------------------------------------------- #
# Public API behaviour
# --------------------------------------------------------------------------- #


class TestPassthroughAndStreams:
    def test_to_visual_off_returns_logical(self, monkeypatch):
        monkeypatch.setattr(fa_console, "_visual_mode", False)
        assert fa_console._to_visual("سلام") == "سلام"

    def test_visual_stream_converts_write(self, monkeypatch):
        monkeypatch.setattr(fa_console, "_visual_mode", True)
        sink = io.StringIO()
        stream = fa_console.VisualStream(sink)
        stream.write("سلام")
        assert sink.getvalue() == V(0xFEE1, 0xFEFC, 0xFEB3)

    def test_visual_stream_passthrough_when_off(self, monkeypatch):
        monkeypatch.setattr(fa_console, "_visual_mode", False)
        sink = io.StringIO()
        stream = fa_console.VisualStream(sink)
        stream.write("سلام")
        assert sink.getvalue() == "سلام"

    def test_newline_structure_survives(self, monkeypatch):
        monkeypatch.setattr(fa_console, "_visual_mode", True)
        result = fa_console._to_visual("سلام\nhello")
        assert "\n" in result and "hello" in result

    def test_fa_print_plain_output(self, capsys):
        fa_console.fa_print("سلام دنیا")
        assert capsys.readouterr().out == "سلام دنیا\n"

    def test_get_console_info_keys(self):
        info = fa_console.get_console_info()
        for key in ("version", "author", "visual_mode", "bidi_backend", "term_program"):
            assert key in info


# --------------------------------------------------------------------------- #
# fa_normalize
# --------------------------------------------------------------------------- #


class TestNormalize:
    def test_arabic_kaf_folds_to_persian(self):
        assert fa_console.fa_normalize("كتاب") == "کتاب"

    def test_arabic_yeh_folds_to_persian(self):
        assert fa_console.fa_normalize("ي") == "ی"

    def test_persian_text_unchanged(self):
        assert fa_console.fa_normalize("سلام دنیا") == "سلام دنیا"

    def test_letters_with_distinct_meaning_are_kept(self):
        # ة and ه mean different things and must never be folded together.
        assert fa_console.fa_normalize("ة") == "ة"

    @pytest.mark.parametrize(
        ("source", "digits", "expected"),
        [
            ("2026", "persian", "۲۰۲۶"),
            ("۲۰۲۶", "ascii", "2026"),
            ("٢٠٢٦", "persian", "۲۰۲۶"),
            ("2026", "keep", "2026"),
            ("a1b۲c٣", "ascii", "a1b2c3"),
        ],
    )
    def test_digit_unification(self, source, digits, expected):
        assert fa_console.fa_normalize(source, digits=digits) == expected

    def test_length_preserved(self):
        source = "كتاب 2026"
        assert len(fa_console.fa_normalize(source, digits="ascii")) == len(source)

    def test_invalid_digits_style_raises(self):
        with pytest.raises(ValueError):
            fa_console.fa_normalize("x", digits="roman")

    def test_normalize_roundtrip_with_input_mock(self, monkeypatch):
        # fa_input(normalize=True) folds before returning (piped-input path).
        monkeypatch.setattr("builtins.input", lambda: "كتاب")
        assert fa_console.fa_input("نام: ", normalize=True) == "کتاب"
