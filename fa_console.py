# -*- coding: utf-8 -*-
"""
fa_console — Correct Persian (Farsi) console I/O for Python on Windows
======================================================================

:Author:     Alireza Hosseini <alireza.hosseini@hotmail.com>
:Social:     Bale https://ble.ir/TechInsightsHub
             Eitaa https://eitaa.com/TechInsightsHub
             Aparat https://aparat.com/TechInsightsHub
:Version:    2.0.0
:Platform:   Windows (fully functional) / POSIX (safe no-op)
:Requires:   Python 3.8+

Overview
--------

Persian text in the classic Windows console fails in two independent
layers, and this module fixes both — automatically, with a single
``import``:

**Layer 1 — Encoding.** The default console code page on Windows is a
legacy legacy page (e.g. 720, 850, 1252), not UTF-8. Whenever a stream is
redirected or piped, Python decodes/encodes bytes with that legacy codec,
producing mojibake or raising ``UnicodeEncodeError``.

*Fix:* the console code page is switched to UTF-8 (65001) via the Win32
API, ``sys.stdin`` / ``sys.stdout`` / ``sys.stderr`` are reconfigured to
UTF-8 (neutralising even a broken ``PYTHONIOENCODING``), and the child-
process environment variables ``PYTHONUTF8`` / ``PYTHONIOENCODING`` are
pinned so spawned interpreters behave identically.

**Layer 2 — Rendering.** The classic Windows console host (``conhost`` —
the engine behind ``cmd.exe`` and the standalone PowerShell window) has
*no* Arabic script shaping and *no* bidirectional reordering. Logically
correct text is therefore *drawn* disconnected and left-to-right, i.e.
backwards and unreadable, even though the underlying data is perfect.

*Fix:* when the process is attached to a classic console, a
:class:`VisualStream` wrapper is installed on ``sys.stdout`` /
``sys.stderr``. Every write is converted from logical order to visual
order (letter shaping into Unicode Arabic Presentation Forms + a
bidirectional line reorder) before it reaches the screen. When
``arabic-reshaper`` and ``python-bidi`` are installed they are used for
maximum fidelity; otherwise a built-in, dependency-free engine is used.
:func:`fa_input` additionally provides a single-line editor with *live*
correct echo while typing.

Quick start
-----------

Fix everything in one line::

    import fa_console                 # configuration applied on import
    print("سلام دنیا")                # renders correctly everywhere
    name = fa_console.fa_input("نام: ")

Explicit API::

    from fa_console import setup_console, fa_print, fa_input
    report = setup_console()          # idempotent; force=True to redo
    fa_print("سلام", name)
    name = fa_input("نام: ")

Programmatic inspection::

    from fa_console import get_console_info, is_visual_mode
    print(get_console_info())         # detected environment / backends
    print(is_visual_mode())           # display transform active?

Interactive self-diagnostics::

    python fa_console.py              # prints a full environment report

Design contract
---------------

**Fail-open.** This module must never break the host application. Every
internal failure (missing Win32 API, no console attached, exotic stream
type, editor keystroke surprises, …) is caught, reported through the
``fa_console`` logger (a ``NullHandler`` is pre-installed, so nothing is
printed unless the application configures logging) and degrades to
standard Python behaviour. :class:`FaConsoleError` is raised only by the
low-level Win32 helpers and is always consumed inside :func:`setup_console`.

**Logical data invariant.** Values returned by :func:`fa_input` /
``input()`` are always *logical-order* Unicode. Visual transformation is
a *display-time-only* concern: comparisons, ``len()``, slicing, regexes
and file/storage writes all see plain correct Persian text. When standard
output is redirected to a file or pipe, no transformation is applied, so
downstream tools receive standards-compliant UTF-8.

Scope and limitations
---------------------

* The visual transform targets the classic console host (``conhost``) and
  the VS Code integrated terminal — xterm.js has no reliable bidirectional
  reordering, so logical Persian renders disconnected/backwards there.
  Windows Terminal (``WT_SESSION``) shapes and reorders Arabic natively
  and is left untouched. Escape hatches: ``FA_CONSOLE_FORCE_VISUAL=1``
  forces the transform on, ``FA_CONSOLE_NO_VISUAL=1`` forces it off.
* The live-typing editor mirrors built-in ``input()`` semantics
  (``KeyboardInterrupt`` on Ctrl+C, ``EOFError`` on Ctrl+Z) but provides
  no history or cursor movement; arrow keys are consumed and ignored.
  Extremely long inputs that wrap across terminal rows redraw only the
  last visual row.
* Not thread-safe beyond normal stream usage: the module mutates
  ``sys.stdin``/``sys.stdout`` once at import, which is standard practice;
  the console editor is inherently single-threaded.

Module layout
-------------

1. Metadata and logging
2. Public exceptions and result types
3. Constants and environment switches
4. Win32 helpers (code page, console font)
5. UTF-8 stream reconfiguration
6. Visual transformation engine (shaping + bidirectional reorder)
7. :class:`VisualStream` — transparent stdout/stderr wrapper
8. :class:`_ConhostLineEditor` — live-echo line input
9. Public API: :func:`setup_console`, :func:`fa_print`, :func:`fa_input`,
   :func:`is_visual_mode`, :func:`get_console_info`
10. Import-time auto-setup and script-mode diagnostics
"""

from __future__ import annotations

import io
import logging
import os
import sys
from dataclasses import dataclass
from typing import Any, Iterator

# --------------------------------------------------------------------------- #
# 1. Module metadata and logging
# --------------------------------------------------------------------------- #

__author__ = "Alireza Hosseini"
__email__ = "alireza.hosseini@hotmail.com"
__version__ = "2.0.2"

__all__ = [
    "FaConsoleError",
    "ConsoleSetupReport",
    "VisualStream",
    "setup_console",
    "fa_print",
    "fa_input",
    "is_visual_mode",
    "get_console_info",
]

#: Library-scoped logger. A ``NullHandler`` is pre-installed so the module
#: stays silent unless the host application configures logging.
logger = logging.getLogger("fa_console")
logger.addHandler(logging.NullHandler())


# --------------------------------------------------------------------------- #
# 2. Public exceptions and result types
# --------------------------------------------------------------------------- #


class FaConsoleError(Exception):
    """
    Raised by the low-level Win32 helpers when a console API call fails.

    The high-level API (:func:`setup_console` and friends) never lets this
    escape: failures are caught, logged at ``WARNING`` level through the
    ``fa_console`` logger, and reflected in :class:`ConsoleSetupReport`
    fields as ``False``. The module then continues with standard Python
    behaviour (fail-open contract).
    """


@dataclass(frozen=True)
class ConsoleSetupReport:
    """
    Outcome of the last :func:`setup_console` call.

    Attributes:
        codepage_set: Console input/output code page switched to UTF-8.
        font_set: Console font switched to a TrueType face with Arabic
            glyphs (classic consoles only; irrelevant for Windows Terminal).
        streams_reconfigured: All present standard streams reconfigured
            to UTF-8.
        visual_mode: Display-time logical→visual transformation active on
            ``sys.stdout`` / ``sys.stderr``.
        bidi_backend: ``"python-bidi"`` when the optional high-fidelity
            libraries are used, ``"builtin"`` for the dependency-free
            engine, or ``"none"`` when no transformation is active.
    """

    codepage_set: bool = False
    font_set: bool = False
    streams_reconfigured: bool = False
    visual_mode: bool = False
    bidi_backend: str = "none"


# --------------------------------------------------------------------------- #
# 3. Constants and environment switches
# --------------------------------------------------------------------------- #

#: Win32 code page identifier for UTF-8.
UTF8_CODEPAGE = 65001

#: ``GetStdHandle`` selector for the standard output device: ``(DWORD)-11``.
_STD_OUTPUT_HANDLE = 0xFFFF_FFF5

#: ``CONSOLE_FONT_INFOEX.FontFamily`` flag marking a TrueType font.
_TT_FONT = 0x04

#: TrueType font shipped with Windows that contains Arabic glyphs.
#: The stock raster/Consolas faces render Persian as hollow boxes.
_DEFAULT_FONT = "Courier New"

#: Set to ``1`` to force the visual transform even on redirect/non-Windows
#: (debugging escape hatch).
ENV_FORCE_VISUAL = "FA_CONSOLE_FORCE_VISUAL"

#: Set to ``1`` to unconditionally disable the visual transform.
ENV_NO_VISUAL = "FA_CONSOLE_NO_VISUAL"

# --------------------------- Arabic shaping tables -------------------------- #
#
# Minimal shaping tables covering the Arabic block plus the extra letters
# required for Persian (پ چ ژ ک گ ی). Values are Unicode Arabic Presentation
# Forms code points: (isolated, final, initial, medial).
#
# ``_DUAL_FORMS``  — letters that connect on both sides.
# ``_RIGHT_FORMS`` — letters that only connect to the *preceding* letter.

_DUAL_FORMS: dict[int, tuple[int, int, int, int]] = {
    0x0626: (0xFE89, 0xFE8A, 0xFE8B, 0xFE8C),  # ئ
    0x0628: (0xFE8F, 0xFE90, 0xFE91, 0xFE92),  # ب
    0x062A: (0xFE95, 0xFE96, 0xFE97, 0xFE98),  # ت
    0x062B: (0xFE99, 0xFE9A, 0xFE9B, 0xFE9C),  # ث
    0x062C: (0xFE9D, 0xFE9E, 0xFE9F, 0xFEA0),  # ج
    0x062D: (0xFEA1, 0xFEA2, 0xFEA3, 0xFEA4),  # ح
    0x062E: (0xFEA5, 0xFEA6, 0xFEA7, 0xFEA8),  # خ
    0x0633: (0xFEB1, 0xFEB2, 0xFEB3, 0xFEB4),  # س
    0x0634: (0xFEB5, 0xFEB6, 0xFEB7, 0xFEB8),  # ش
    0x0635: (0xFEB9, 0xFEBA, 0xFEBB, 0xFEBC),  # ص
    0x0636: (0xFEBD, 0xFEBE, 0xFEBF, 0xFEC0),  # ض
    0x0637: (0xFEC1, 0xFEC2, 0xFEC3, 0xFEC4),  # ط
    0x0638: (0xFEC5, 0xFEC6, 0xFEC7, 0xFEC8),  # ظ
    0x0639: (0xFEC9, 0xFECA, 0xFECB, 0xFECC),  # ع
    0x063A: (0xFECD, 0xFECE, 0xFECF, 0xFED0),  # غ
    0x0641: (0xFED1, 0xFED2, 0xFED3, 0xFED4),  # ف
    0x0642: (0xFED5, 0xFED6, 0xFED7, 0xFED8),  # ق
    0x0643: (0xFED9, 0xFEDA, 0xFEDB, 0xFEDC),  # ك
    0x0644: (0xFEDD, 0xFEDE, 0xFEDF, 0xFEE0),  # ل
    0x0645: (0xFEE1, 0xFEE2, 0xFEE3, 0xFEE4),  # م
    0x0646: (0xFEE5, 0xFEE6, 0xFEE7, 0xFEE8),  # ن
    0x0647: (0xFEE9, 0xFEEA, 0xFEEB, 0xFEEC),  # ه
    0x064A: (0xFEF1, 0xFEF2, 0xFEF3, 0xFEF4),  # ي
    0x067E: (0xFB56, 0xFB57, 0xFB58, 0xFB59),  # پ
    0x0686: (0xFB7A, 0xFB7B, 0xFB7C, 0xFB7D),  # چ
    0x06A9: (0xFB8E, 0xFB8F, 0xFB90, 0xFB91),  # ک
    0x06AF: (0xFB92, 0xFB93, 0xFB94, 0xFB95),  # گ
    0x06CC: (0xFBFC, 0xFBFD, 0xFBFE, 0xFBFF),  # ی
}

_RIGHT_FORMS: dict[int, tuple[int, int | None]] = {
    0x0621: (0xFE80, None),    # ء  (joins on neither side)
    0x0622: (0xFE81, 0xFE82),  # آ
    0x0623: (0xFE83, 0xFE84),  # أ
    0x0624: (0xFE85, 0xFE86),  # ؤ
    0x0625: (0xFE87, 0xFE88),  # إ
    0x0627: (0xFE8D, 0xFE8E),  # ا
    0x0629: (0xFE93, 0xFE94),  # ة
    0x062F: (0xFEA9, 0xFEAA),  # د
    0x0630: (0xFEAB, 0xFEAC),  # ذ
    0x0631: (0xFEAD, 0xFEAE),  # ر
    0x0632: (0xFEAF, 0xFEB0),  # ز
    0x0648: (0xFEED, 0xFEEE),  # و
    0x0649: (0xFEEF, 0xFEF0),  # ى
    0x0698: (0xFB8A, 0xFB8B),  # ژ
}

#: Arabic tatweel/kashida — a dual-joining letter whose forms are itself.
_TATWEEL = 0x0640

#: Zero-width non-joiner: breaks shaping across it, invisible in output.
_ZWNJ = 0x200C

#: Combining marks (diacritics) are shaping-transparent.
_TRANSPARENT = frozenset(range(0x064B, 0x0660)) | {0x0670}

#: Unicode ranges containing RTL letters and Arabic presentation forms.
_RTL_RANGES = (
    (0x0600, 0x06FF),
    (0x0750, 0x077F),
    (0x08A0, 0x08FF),
    (0xFB50, 0xFDFF),
    (0xFE70, 0xFEFF),
)

#: Arabic-Indic and Persian digits. They live inside an RTL block but flow
#: left-to-right as a number, so they are treated as LTR tokens.
_ARABIC_DIGITS = frozenset(range(0x0660, 0x066A)) | frozenset(range(0x06F0, 0x06FA))

#: Bracket mirroring applied during visual reordering (Unicode Bidi rule L4).
_MIRROR = {"(": ")", ")": "(", "[": "]", "]": "[", "{": "}", "}": "{"}


# --------------------------------------------------------------------------- #
# 4. Win32 helpers
# --------------------------------------------------------------------------- #

_kernel32_cache: Any = None


def _get_kernel32() -> Any:
    """Return the loaded ``kernel32`` DLL, or ``None`` off-Windows."""
    global _kernel32_cache
    if _kernel32_cache is None and os.name == "nt":
        import ctypes
        from ctypes import wintypes  # noqa: F401  (ensures syscall types ready)

        _kernel32_cache = ctypes.WinDLL("kernel32", use_last_error=True)
    return _kernel32_cache


def _set_console_codepage() -> bool:
    """
    Switch the attached console's input and output code page to UTF-8.

    Returns:
        ``True`` on success, ``False`` when no console is attached.

    Raises:
        FaConsoleError: If the console reports failure for the switch.
    """
    import ctypes

    k32 = _get_kernel32()
    if k32 is None:
        return False
    k32.SetConsoleOutputCP.argtypes = [ctypes.c_uint]
    k32.SetConsoleCP.argtypes = [ctypes.c_uint]
    k32.SetConsoleOutputCP.restype = ctypes.c_int
    k32.SetConsoleCP.restype = ctypes.c_int

    out_ok = k32.SetConsoleOutputCP(UTF8_CODEPAGE)
    in_ok = k32.SetConsoleCP(UTF8_CODEPAGE)
    if not (out_ok and in_ok):
        raise FaConsoleError(
            f"SetConsoleCP/SetConsoleOutputCP failed "
            f"(GetLastError={ctypes.get_last_error()})"
        )
    return True


def _set_console_font(face: str = _DEFAULT_FONT) -> bool:
    """
    Point the classic console at a TrueType font containing Arabic glyphs.

    This is a best-effort cosmetic fix: raster fonts and Consolas render
    Persian letters as hollow boxes. Skipped entirely on modern terminals
    (Windows Terminal / VS Code), which manage their own fonts.

    Returns:
        ``True`` if the font was changed, ``False`` when skipped or when no
        console is attached.

    Raises:
        FaConsoleError: If the API call fails on an attached console.
    """
    import ctypes
    from ctypes import wintypes

    if _modern_terminal():
        return False

    k32 = _get_kernel32()
    if k32 is None:
        return False

    k32.GetStdHandle.restype = ctypes.c_void_p
    k32.GetStdHandle.argtypes = [wintypes.DWORD]
    k32.GetConsoleMode.restype = wintypes.BOOL
    k32.GetConsoleMode.argtypes = [ctypes.c_void_p, ctypes.POINTER(wintypes.DWORD)]
    k32.SetCurrentConsoleFontEx.restype = wintypes.BOOL
    k32.SetCurrentConsoleFontEx.argtypes = [
        ctypes.c_void_p,
        wintypes.BOOL,
        ctypes.c_void_p,
    ]

    handle = k32.GetStdHandle(_STD_OUTPUT_HANDLE)
    mode = wintypes.DWORD()
    if not handle or not k32.GetConsoleMode(handle, ctypes.byref(mode)):
        return False  # no interactive console attached (file/pipe output)

    class COORD(ctypes.Structure):
        _fields_ = [("X", wintypes.SHORT), ("Y", wintypes.SHORT)]

    class CONSOLE_FONT_INFO_EX(ctypes.Structure):
        _fields_ = [
            ("cbSize", wintypes.ULONG),
            ("nFont", wintypes.DWORD),
            ("dwFontSize", COORD),
            ("FontFamily", wintypes.UINT),
            ("FontWeight", wintypes.UINT),
            ("FaceName", wintypes.WCHAR * 32),
        ]

    cfi = CONSOLE_FONT_INFO_EX()
    cfi.cbSize = ctypes.sizeof(CONSOLE_FONT_INFO_EX)
    cfi.dwFontSize.Y = 16
    cfi.FontFamily = _TT_FONT
    cfi.FontWeight = 400
    cfi.FaceName = face
    if not k32.SetCurrentConsoleFontEx(handle, False, ctypes.byref(cfi)):
        raise FaConsoleError(
            f"SetCurrentConsoleFontEx({face!r}) failed "
            f"(GetLastError={ctypes.get_last_error()})"
        )
    return True


def _get_console_output_codepage() -> int | None:
    """Current console output code page, or ``None`` if unavailable."""
    import ctypes

    k32 = _get_kernel32()
    if k32 is None:
        return None
    try:
        k32.GetConsoleOutputCP.restype = ctypes.c_uint
        return int(k32.GetConsoleOutputCP())
    except Exception:  # pragma: no cover - exotic systems
        return None


# --------------------------------------------------------------------------- #
# 5. UTF-8 stream reconfiguration
# --------------------------------------------------------------------------- #


def _reconfigure_stream(name: str) -> bool:
    """
    Force standard stream *name* (``"stdin"``/``"stdout"``/``"stderr"``)
    to UTF-8 with lossless-for-display error handling.

    Uses :meth:`io.TextIOWrapper.reconfigure` (Python ≥ 3.7) and falls back
    to manual ``TextIOWrapper`` replacement on older interpreters.

    Returns:
        ``True`` if the stream is present and now UTF-8.
    """
    stream = getattr(sys, name, None)
    if stream is None:  # e.g. pythonw has no stdout
        return False
    try:
        stream.flush()
    except Exception:  # unflushable stream — reconfigure still worth trying
        pass
    try:
        stream.reconfigure(encoding="utf-8", errors="replace")
        return True
    except Exception as exc:
        logger.debug("reconfigure(%s) unavailable: %s", name, exc)
    # Legacy fallback: replace the stream with a fresh UTF-8 TextIOWrapper.
    try:
        buffered = getattr(stream, "buffer", None) or getattr(stream, "raw", None)
        if buffered is not None:
            setattr(
                sys, name,
                io.TextIOWrapper(buffered, encoding="utf-8", errors="replace"),
            )
            return True
    except Exception as exc:
        logger.warning("could not reconfigure sys.%s to UTF-8: %s", name, exc)
    return False


def _modern_terminal() -> bool:
    """
    ``True`` for terminals that shape and reorder Arabic text natively and
    reliably — Windows Terminal (``WT_SESSION``) and other ``TERM_PROGRAM``
    hosts (mintty, etc.).

    Note:
        VS Code's integrated terminal (``TERM_PROGRAM=vscode``, powered by
        xterm.js) deliberately does **not** count as modern: xterm.js lacks
        reliable bidirectional reordering for RTL text, so logical Persian
        appears disconnected/backwards there. The visual transform is
        therefore applied inside VS Code as well.
    """
    if os.environ.get("WT_SESSION"):
        return True
    term_program = os.environ.get("TERM_PROGRAM")
    return bool(term_program) and term_program != "vscode"


# --------------------------------------------------------------------------- #
# 6. Visual transformation engine
# --------------------------------------------------------------------------- #


def _is_rtl_letter(code: int) -> bool:
    """``True`` for RTL *letters* (digits excluded — they stay LTR)."""
    return any(lo <= code <= hi for lo, hi in _RTL_RANGES) and code not in _ARABIC_DIGITS


def _has_rtl(text: str) -> bool:
    """Fast scan: does *text* contain at least one RTL letter?"""
    return any(_is_rtl_letter(ord(ch)) for ch in text)


def _is_ltr_token(ch: str) -> bool:
    """
    ``True`` for characters that keep left-to-right order inside a number
    or Latin word: ASCII alphanumerics, Persian/Arabic digits, etc.
    """
    if ord(ch) in _ARABIC_DIGITS:
        return True
    return ch.isalnum() and not _is_rtl_letter(ord(ch))


class _VisualTransformer:
    """
    Converts logical-order Persian/Arabic text into visually-ordered text
    suitable for terminals with no bidi/shaping support.

    Two backends, chosen lazily:

    ``"python-bidi"``
        ``arabic-reshaper`` + ``python-bidi`` (full UAX #9, ligatures such
        as لا, Persian language rules). Used automatically when installed.
    ``"builtin"``
        Dependency-free engine: joining-context letter shaping into
        Arabic Presentation Forms plus a run-reversing line reorder that
        keeps Latin words and numbers upright and mirrors brackets.

    Both backends are wrapped in per-call exception guards; on failure the
    input line is returned unchanged so output is never lost.
    """

    def __init__(self) -> None:
        self._lib_transform: Any = None
        self._lib_checked: bool = False

    # -- backend selection ---------------------------------------------------

    def _load_lib(self) -> Any:
        """Load the optional high-fidelity backend once, if available."""
        if not self._lib_checked:
            self._lib_checked = True
            try:
                import arabic_reshaper
                from bidi.algorithm import get_display

                try:
                    shaper = arabic_reshaper.ArabicReshaper(
                        configuration={"language": "Farsi"}
                    )
                    self._lib_transform = lambda text: get_display(shaper.reshape(text))
                except Exception:  # fall back to default reshaper config
                    self._lib_transform = lambda text: get_display(
                        arabic_reshaper.reshape(text)
                    )
                logger.debug("visual backend: python-bidi + arabic-reshaper")
            except Exception:
                self._lib_transform = None
                logger.debug("visual backend: builtin (optional libs not installed)")
        return self._lib_transform

    @property
    def backend_name(self) -> str:
        """Currently selected backend: ``"python-bidi"``, ``"builtin"`` or
        ``"none"`` before first use."""
        if not self._lib_checked:
            self._load_lib()
        return "python-bidi" if self._lib_transform else "builtin"

    # -- shaping ---------------------------------------------------------------

    @staticmethod
    def _effective(chars: list[str], index: int, step: int) -> int | str | None:
        """
        Walk to the previous (``step=-1``) or next (``step=+1``) shaping-
        relevant character, skipping transparent marks. Returns the code
        point, ``None`` at the boundary, or the string ``"BREAK"`` when a
        ZWNJ terminates joining.
        """
        j = index + step
        while 0 <= j < len(chars):
            code = ord(chars[j])
            if code == _ZWNJ:
                return "BREAK"
            if code in _TRANSPARENT:
                j += step
                continue
            return code
        return None

    def shape(self, text: str) -> str:
        """
        Replace each Arabic/Persian letter with the presentation form
        (isolated / initial / medial / final) dictated by its joining
        context. Non-Arabic characters and transparent marks pass through;
        ZWNJ breaks joining and is removed from the output.
        """
        if not _has_rtl(text):
            return text
        chars = list(text)
        out: list[str] = []
        for i, ch in enumerate(chars):
            code = ord(ch)
            if code == _ZWNJ:
                continue
            if code in _TRANSPARENT:
                out.append(ch)
                continue
            if code == _TATWEEL:
                iso = fin = ini = med = ch
                joins_prev, joins_next = True, True
            elif code in _DUAL_FORMS:
                iso, fin, ini, med = _DUAL_FORMS[code]
                joins_prev, joins_next = True, True
            elif code in _RIGHT_FORMS:
                iso, fin = _RIGHT_FORMS[code]
                ini = med = None
                joins_prev, joins_next = True, False
            else:
                out.append(ch)
                continue

            prev = self._effective(chars, i, -1)
            nxt = self._effective(chars, i, +1)
            prev_dual = isinstance(prev, int) and (
                prev in _DUAL_FORMS or prev == _TATWEEL
            )
            nxt_joins = isinstance(nxt, int) and (
                nxt in _DUAL_FORMS or nxt in _RIGHT_FORMS or nxt == _TATWEEL
            )

            if prev_dual and joins_next and nxt_joins and med is not None:
                out.append(chr(med))
            elif prev_dual and joins_prev and fin is not None:
                out.append(chr(fin))
            elif joins_next and nxt_joins and ini is not None:
                out.append(chr(ini))
            else:
                out.append(chr(iso))
        return "".join(out)

    # -- bidirectional line reorder ---------------------------------------------

    def reorder_line(self, line: str) -> str:
        """
        Reorder a shaped logical line for an LTR-drawing terminal: the RTL
        flow is reversed while maximal Latin/number runs stay upright and
        brackets are mirrored. Control characters pass through untouched.
        """
        if not _has_rtl(line):
            return line
        out: list[str] = []
        cluster: list[str] = []
        for ch in reversed(line):
            if ord(ch) < 32:  # control chars act as hard boundaries
                if cluster:
                    out.extend(reversed(cluster))
                    cluster.clear()
                out.append(ch)
            elif _is_ltr_token(ch):
                cluster.append(ch)
            else:
                if cluster:
                    out.extend(reversed(cluster))
                    cluster.clear()
                out.append(_MIRROR.get(ch, ch))
        if cluster:
            out.extend(reversed(cluster))
        return "".join(out)

    # -- public entry points -------------------------------------------------------

    def transform_line(self, line: str) -> str:
        """
        Fully transform one logical line (no ``\\n`` inside) into visual
        order. Backend failures degrade to the input line unchanged.
        """
        if not _has_rtl(line):
            return line
        lib = self._load_lib()
        if lib is not None:
            try:
                return lib(line)
            except Exception as exc:
                logger.warning("python-bidi backend failed (%s); using builtin", exc)
        try:
            return self.reorder_line(self.shape(line))
        except Exception as exc:  # absolute last resort: never lose output
            logger.warning("builtin visual transform failed (%s)", exc)
            return line

    def transform_text(self, text: str) -> str:
        """
        Transform arbitrary text (may contain ``\\n``) line by line, so
        newline structure survives intact.
        """
        if not text:
            return text
        return "\n".join(self.transform_line(part) for part in text.split("\n"))


#: Module-wide transformer instance used by :func:`_to_visual`.
_transformer = _VisualTransformer()

#: Master switch: ``True`` once :func:`setup_console` decides the process is
#: attached to a classic console and installs :class:`VisualStream`.
_visual_mode = False


def _to_visual(text: str) -> str:
    """
    Logical→visual conversion gated by :data:`_visual_mode`. Safe to call
    from anywhere: returns *text* unchanged when the transform is off.
    """
    if not _visual_mode or not text:
        return text
    try:
        return _transformer.transform_text(text)
    except Exception as exc:  # pragma: no cover - transform_text is guarded
        logger.warning("visual transform failed (%s); emitting logical text", exc)
        return text


# --------------------------------------------------------------------------- #
# 7. VisualStream — transparent stdout/stderr wrapper
# --------------------------------------------------------------------------- #


class VisualStream:
    """
    Write-through wrapper that converts logical-order Persian text to
    visual order on its way to the underlying stream.

    Installing this on ``sys.stdout`` is what makes *plain* ``print()``
    (not just :func:`fa_print`) render correctly in classic consoles.
    Everything except :meth:`write` / :meth:`writelines` is delegated to
    the wrapped stream, so buffering, ``isatty()``, ``fileno()``,
    encodings and context-manager usage keep working.

    Write failures of the underlying stream propagate unchanged; the
    transformation itself never raises (see :func:`_to_visual`).
    """

    def __init__(self, stream: Any) -> None:
        self._inner = stream

    # -- transformed writes ----------------------------------------------------

    def write(self, text: str) -> int:
        """Transform *text* (if the visual mode is on) and write it."""
        return self._inner.write(_to_visual(text))

    def writelines(self, lines: Any) -> None:
        """Transform and write each line; newlines must be embedded by caller."""
        return self._inner.writelines(_to_visual(line) for line in lines)

    # -- direct delegation ------------------------------------------------------

    def flush(self) -> None:
        self._inner.flush()

    def isatty(self) -> bool:
        return self._inner.isatty()

    def fileno(self) -> int:
        return self._inner.fileno()

    def close(self) -> None:
        self._inner.close()

    def readable(self) -> bool:
        return False

    def writable(self) -> bool:
        return True

    def seekable(self) -> bool:
        return False

    @property
    def encoding(self) -> str:
        return self._inner.encoding

    @property
    def fa_inner(self) -> Any:
        """The wrapped stream — used by the line editor to bypass the
        transform for already-visual content (avoids double conversion)."""
        return self._inner

    def __iter__(self) -> Iterator[str]:
        return iter(self._inner)

    def __enter__(self) -> "VisualStream":
        return self

    def __exit__(self, *exc_info: Any) -> None:
        self._inner.close()

    def __getattr__(self, name: str) -> Any:
        # Only called for attributes not defined above; delegates the rest
        # (detach, reconfigure, buffer, name, mode, …) to the inner stream.
        return getattr(self._inner, name)

    def __repr__(self) -> str:
        return f"<VisualStream wrapping {self._inner!r}>"


# --------------------------------------------------------------------------- #
# 8. _ConhostLineEditor — live-echo line input for classic consoles
# --------------------------------------------------------------------------- #


class _ConhostLineEditor:
    """
    Single-line editor with live *correct* Persian echo for classic
    Windows consoles (``msvcrt.getwch()`` based).

    The stock console echo draws each keystroke in logical order — i.e.
    disconnected and backwards. This editor mutes the console echo, keeps
    the logical buffer, and after every keystroke redraws the whole line
    in visual order through the raw (non-transforming) stream.

    Keystroke contract (mirrors built-in ``input()`` where it matters):

    ================  ======================================================
    Key               Behaviour
    ================  ======================================================
    Enter / Ctrl+M    Finish; return the logical text
    Backspace (0x08)  Delete last character; also accepts 0x7F
    Ctrl+C (0x03)     Raise :class:`KeyboardInterrupt`
    Ctrl+Z (0x1A)     Raise :class:`EOFError`
    Arrows / F-keys   Two-byte sequence consumed and ignored
    Tab               Ignored (avoids cursor/column misalignment)
    anything else     Appended when printable
    ================  ======================================================

    Known limitation: inputs long enough to wrap across terminal rows
    redraw only the final visual row (single-line ``\\r`` redraw).
    """

    def __init__(self, prompt: str) -> None:
        import msvcrt

        self._msvcrt = msvcrt
        self._prompt = prompt
        self._prompt_visual = _to_visual(prompt)
        self._buffer: list[str] = []
        self._last_len = 0
        out = sys.stdout
        # Write pre-visualised content through the *inner* stream to bypass
        # VisualStream and avoid a double transformation.
        self._raw = getattr(out, "fa_inner", out)

    # -- internals -----------------------------------------------------------

    def _redraw(self) -> None:
        """Repaint ``prompt + visual(buffer)``, erasing any leftover cells."""
        visual = _to_visual("".join(self._buffer))
        line = self._prompt_visual + visual
        pad = self._last_len - len(line)
        suffix = " " * pad if pad > 0 else ""
        self._raw.write("\r" + line + suffix + "\r" + line)
        self._raw.flush()
        self._last_len = len(line)

    # -- public ----------------------------------------------------------------

    def readline(self) -> str:
        """
        Read one line. Returns the *logical-order* string typed by the user.

        Raises:
            KeyboardInterrupt: on Ctrl+C (matching built-in ``input()``).
            EOFError: on Ctrl+Z (matching built-in ``input()``).
        """
        self._raw.write(self._prompt_visual)
        self._raw.flush()
        while True:
            ch = self._msvcrt.getwch()
            if ch in ("\r", "\n"):
                self._raw.write("\n")
                self._raw.flush()
                return "".join(self._buffer)
            code = ord(ch)
            if code in (0, 224):  # arrow / function-key prefix byte
                self._msvcrt.getwch()
            elif ch in ("\x08", "\x7f"):
                if self._buffer:
                    self._buffer.pop()
                    self._redraw()
            elif ch == "\x03":
                self._raw.write("\n")
                raise KeyboardInterrupt
            elif ch == "\x1a":
                raise EOFError
            elif ch == "\t" or not ch.isprintable():
                continue
            else:
                self._buffer.append(ch)
                self._redraw()


# --------------------------------------------------------------------------- #
# 9. Public API
# --------------------------------------------------------------------------- #


def setup_console(force: bool = False) -> ConsoleSetupReport:
    """
    Apply the full Persian/Unicode console configuration.

    Steps (all guarded, see the fail-open contract in the module docs):

    1. Pin ``PYTHONUTF8`` / ``PYTHONIOENCODING`` for child processes.
    2. Windows only: switch the console code page to UTF-8 and select a
       TrueType font with Arabic glyphs (classic consoles).
    3. Reconfigure ``sys.stdin`` / ``sys.stdout`` / ``sys.stderr`` to UTF-8.
    4. Classic-console only: install :class:`VisualStream` on stdout and
       stderr so *every* write is displayed shaped and right-to-left.

    Args:
        force: Re-run the configuration even if it already ran (idempotent
            by default). The visual stream wrapper is only installed once;
            with ``force=True`` an existing wrapper is reused, never nested.

    Returns:
        :class:`ConsoleSetupReport` describing what was applied.
    """
    global _setup_done, _visual_mode, _last_report

    if _setup_done and not force:
        return _last_report

    # 1) Environment for child processes.
    os.environ["PYTHONIOENCODING"] = "utf-8"
    os.environ["PYTHONUTF8"] = "1"

    codepage_set = font_set = streams_ok = False

    # 2) Windows console specifics.
    if _is_windows():
        try:
            codepage_set = _set_console_codepage()
        except FaConsoleError as exc:
            logger.warning("code page switch to UTF-8 skipped: %s", exc)
        except Exception as exc:  # unexpected — still non-fatal
            logger.warning("code page switch raised unexpectedly: %s", exc)
        try:
            font_set = _set_console_font()
        except FaConsoleError as exc:
            logger.warning("console font switch skipped: %s", exc)
        except Exception as exc:
            logger.warning("console font switch raised unexpectedly: %s", exc)

    # 3) UTF-8 standard streams.
    streams_ok = all(_reconfigure_stream(name) for name in ("stdin", "stdout", "stderr"))

    # 4) Display transform for consoles without Arabic shaping.
    visual = False
    if sys.stdout is not None:
        if os.environ.get(ENV_NO_VISUAL):
            visual = False
            logger.debug("visual transform disabled via %s", ENV_NO_VISUAL)
        elif os.environ.get(ENV_FORCE_VISUAL):
            visual = True
            logger.debug("visual transform forced via %s", ENV_FORCE_VISUAL)
        elif _is_windows() and not _modern_terminal():
            try:
                visual = bool(sys.stdout.isatty())
            except Exception:
                visual = False
        if visual and not isinstance(sys.stdout, VisualStream):
            sys.stdout = VisualStream(sys.stdout)
            if sys.stderr is not None and not isinstance(sys.stderr, VisualStream):
                sys.stderr = VisualStream(sys.stderr)

    _visual_mode = visual
    _last_report = ConsoleSetupReport(
        codepage_set=codepage_set,
        font_set=font_set,
        streams_reconfigured=streams_ok,
        visual_mode=visual,
        bidi_backend=_transformer.backend_name if visual else "none",
    )
    _setup_done = True
    logger.info("setup complete: %s", _last_report)
    return _last_report


def fa_print(*values: Any, sep: str = " ", end: str = "\n",
             file: Any = None, flush: bool = False) -> None:
    """
    Persian-safe :func:`print` drop-in.

    Transformation happens inside the installed :class:`VisualStream`, so
    this is a pure pass-through to :func:`print`; it exists for API
    symmetry and for explicitness in application code.
    """
    print(*values, sep=sep, end=end, file=file, flush=flush)


def fa_input(prompt: str = "") -> str:
    """
    Persian-safe :func:`input` replacement.

    On classic consoles the prompt is written through the visual stream
    and a :class:`_ConhostLineEditor` provides live, correctly-rendered
    echo while typing. Everywhere else (Windows Terminal, IDEs, piped
    stdin) it degrades to plain ``print(prompt)`` + ``input()``.

    Args:
        prompt: Prompt text in logical order; rendered correctly.

    Returns:
        The *logical-order* string typed by the user.

    Raises:
        KeyboardInterrupt: on Ctrl+C.
        EOFError: on Ctrl+Z (interactive) or closed stdin (piped).
    """
    if _visual_mode and _is_windows() and sys.stdin is not None:
        try:
            if sys.stdin.isatty():
                try:
                    return _ConhostLineEditor(prompt).readline()
                except (EOFError, KeyboardInterrupt):
                    raise
                except Exception as exc:
                    logger.warning("line editor unavailable (%s); using input()", exc)
        except Exception:
            pass  # isatty probing failed — fall through to plain input()
    if prompt:
        # VisualStream (when installed) performs the display conversion.
        print(prompt, end="", flush=True)
    return input()


def is_visual_mode() -> bool:
    """``True`` when the display-time logical→visual transform is active."""
    return _visual_mode


def _stream_isatty(stream: Any) -> bool | None:
    """``stream.isatty()`` safely; ``None`` when it cannot be probed."""
    try:
        return bool(stream.isatty()) if stream is not None else None
    except Exception:
        return None


def get_console_info() -> dict[str, Any]:
    """
    Return a snapshot of the detected/active console configuration.

    Useful for bug reports and the script-mode diagnostics. Keys:
    ``author``, ``version``, ``platform``, ``python``, ``os_name``,
    ``stdin_encoding``, ``stdout_encoding``, ``stdout_isatty``,
    ``console_codepage``, ``modern_terminal``, ``visual_mode``,
    ``bidi_backend``, ``force_visual_env``, ``no_visual_env``,
    ``last_setup_report``.
    """
    stdout = sys.stdout
    return {
        "author": f"{__author__} <{__email__}>",
        "version": __version__,
        "platform": sys.platform,
        "python": sys.version.split()[0],
        "os_name": os.name,
        "stdin_encoding": getattr(sys.stdin, "encoding", None),
        "stdout_encoding": getattr(stdout, "encoding", None),
        "stdout_isatty": _stream_isatty(sys.stdout),
        "console_codepage": _get_console_output_codepage(),
        "modern_terminal": _modern_terminal(),
        "term_program": os.environ.get("TERM_PROGRAM"),
        "visual_mode": _visual_mode,
        "bidi_backend": _transformer.backend_name if _visual_mode else "none",
        "force_visual_env": bool(os.environ.get(ENV_FORCE_VISUAL)),
        "no_visual_env": bool(os.environ.get(ENV_NO_VISUAL)),
        "last_setup_report": _last_report,
    }


def _is_windows() -> bool:
    """``True`` on Microsoft Windows (``os.name == "nt"``)."""
    return os.name == "nt"


# --------------------------------------------------------------------------- #
# 10. Import-time auto-setup and script-mode diagnostics
# --------------------------------------------------------------------------- #

_setup_done = False
_last_report = ConsoleSetupReport()

try:
    setup_console()
except Exception:  # absolute last resort — the import must never fail
    logger.exception("fa_console auto-setup failed; standard behaviour retained")


def _self_diagnostics() -> None:
    """Print a human-readable report (entry point when run as a script)."""
    info = get_console_info()
    line = "=" * 64
    print(line)
    print(f"fa_console {__version__} — self diagnostics")
    print(line)
    for key, value in info.items():
        print(f"  {key:<20}: {value}")
    print(line)
    sample = "سلام علی! سال ۱۴۰۵ — (test 123)"
    print(f"  logical sample : {sample}")
    print(f"  visual sample  : {_to_visual(sample)}")
    print(line)


if __name__ == "__main__":
    _self_diagnostics()
