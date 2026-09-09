# Changelog

All notable changes to **fa-console** are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [2.2.0] - 2026-09-09

### Added

- **Built-in engine: lam-alef ligatures.** لام + alef (ا أ إ آ) now fuse
  into the single ligature glyph (FEFB/FEFC family) with the correct
  isolated/final form, matching professional shaping instead of drawing
  two separate letters.
- **Built-in engine: Urdu/Pashto letter support** — ٹ ھ (dual-joining)
  and ڈ ڑ ں ۀ ہ ے (right-joining), extending shaping coverage beyond
  Persian/Arabic.
- **Automated test suite** (pytest) covering the shaping goldens,
  lam-alef ligatures, UAX #9 W4 numeric-separator behaviour, terminal
  detection in all environment combinations, `fa_normalize`, and
  `VisualStream` — plus a GitHub Actions test matrix (Windows,
  Python 3.8 → 3.14). The publish workflow now runs the tests before
  uploading.
- `MANIFEST.in` — tests and docs are included in the source
  distribution.

### Changed

- License metadata migrated to PEP 639 SPDX form (`license = "MIT"`,
  `license-files`), dropping the deprecated trove classifier.
- Docs: documented `python -m fa_console` diagnostics and the required
  import order with `colorama`/`tqdm` (import `fa_console` first).

## [2.1.0] - 2026-09-09

### Added

- **`fa_normalize(text, digits="keep")`** — new public API that folds
  Arabic-lookalike characters onto their Persian canonical forms, so text
  typed with an Arabic keyboard layout (ي U+064A / ك U+0643) compares,
  hashes and stores identically to the same word typed with a Persian
  layout (ی U+06CC / ک U+06A9). Letters with a genuinely distinct meaning
  (e.g. ة vs ه) are deliberately *not* folded. The optional `digits`
  argument unifies digit styles: `"keep"` (default — digits untouched),
  `"persian"`, `"arabic"` or `"ascii"`. The mapping is a pure 1:1
  code-point fold; string length is always preserved.
- **`fa_input(normalize=True)`** — optional keyword argument that runs the
  typed value through `fa_normalize` before returning it. The default
  (`False`) is unchanged and returns the text exactly as typed.
- Shaping tables now document that *both* keyboard variants of every
  shared letter are covered: Persian ی (0x06CC) / ک (0x06A9) *and*
  Arabic-layout ي (0x064A) / ك (0x0643) — supported since 2.0.0, now
  stated explicitly in code and docs.
- `python fa_console.py` self-diagnostics now also print a normalization
  sample (Arabic-layout letters + Arabic-Indic digits → Persian forms).
- `example.py` gained an Arabic-vs-Persian keyboard variant demo.

### Fixed

- **Numeric separators no longer split number runs.** The Arabic decimal
  separator (٫ U+066B) and thousands separator (٬ U+066C) are now treated
  as part of a left-to-right number run by the built-in reorder engine —
  previously a value such as `۱۲٫۵` rendered as `۵٫۲۱` in the classic
  console. Likewise, an ASCII `.` or `,` wedged between two digits of any
  style (e.g. `12.5`, `۱۰.۵`, `1,000`) is kept inside the number run,
  matching Unicode UAX #9 rule W4. The `python-bidi` backend (when
  installed) was already correct and is unchanged.

### Documentation

- New `CHANGELOG.md` (this file).
- Both READMEs and the module docstring gained a *Persian vs. Arabic
  keyboard input* section covering letter variants, digit styles and
  numeric separators.

## [2.0.2] - 2026-09-08

### Fixed

- Build metadata only: the package version is now single-sourced from
  `fa_console.__version__` (declared `dynamic` in `pyproject.toml`), so it
  can never drift between the module and the published distribution.

## [2.0.1] - 2026-09-08

### Fixed

- The display transform is now also applied in the **VS Code integrated
  terminal**: its xterm.js engine lacks reliable bidirectional reordering,
  so logical Persian appeared disconnected/backwards there. Windows
  Terminal (`WT_SESSION`) remains untouched — it shapes and reorders
  Arabic natively.

### Changed

- CI: the PyPI publish workflow triggers on `v*` tag pushes
  (`git push origin v2.0.1` publishes the release).

## [2.0.0] - 2026-09-08

### Added

- Initial public release. One `import fa_console` fixes both independent
  layers of Persian console I/O on Windows:
  - **Encoding layer** — console code page switched to UTF-8 (65001) via
    Win32 (`SetConsoleCP`/`SetConsoleOutputCP`), `sys.stdin`/`stdout`/
    `stderr` reconfigured to UTF-8 (neutralising a broken
    `PYTHONIOENCODING`), child processes pinned via `PYTHONUTF8`, and a
    TrueType console font with Arabic glyphs selected on classic consoles.
  - **Rendering layer** — logical→visual transformation (contextual letter
    shaping into Arabic Presentation Forms + bidirectional line reorder)
    installed as a transparent `VisualStream` wrapper on stdout/stderr, so
    even plain `print()` renders joined, right-to-left text. Two backends:
    `arabic-reshaper` + `python-bidi` when installed, otherwise a built-in,
    dependency-free engine.
- `fa_input()` — Persian-safe `input()` with live, correctly-rendered echo
  while typing and built-in-compatible semantics (`KeyboardInterrupt` /
  `EOFError`).
- `fa_print()`, `setup_console()`, `is_visual_mode()`, `get_console_info()`,
  `VisualStream`, `ConsoleSetupReport`, `FaConsoleError`.
- Smart detection: Windows Terminal and redirected output are left
  untouched; fail-open design (internal failures never crash the host).
- Linux/macOS: safe no-op. Python 3.8+, zero required dependencies.

[2.2.0]: https://github.com/Padandish/fa-console/compare/v2.1.0...v2.2.0
[2.1.0]: https://github.com/Padandish/fa-console/compare/v2.0.2...v2.1.0
[2.0.2]: https://github.com/Padandish/fa-console/compare/v2.0.1...v2.0.2
[2.0.1]: https://github.com/Padandish/fa-console/compare/v2.0.0...v2.0.1
[2.0.0]: https://github.com/Padandish/fa-console/commit/e9efd6d
