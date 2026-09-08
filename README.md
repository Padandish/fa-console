# fa-console

> **One import. Correct Persian (Farsi) in the Windows console.**

**English** | [فارسی](README.fa.md)

[![PyPI version](https://img.shields.io/pypi/v/fa-console.svg)](https://pypi.org/project/fa-console/)
[![Python](https://img.shields.io/pypi/pyversions/fa-console.svg)](https://pypi.org/project/fa-console/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![OS](https://img.shields.io/badge/platform-Windows-blue.svg)](#compatibility)

`fa_console` makes Python's built-in `print()` and `input()` work correctly
with Persian text on Windows — **automatically**, with zero required
dependencies and no changes to your code beyond a single `import`.

It fixes both independent layers of the problem:

| Layer | Problem without `fa_console` | With `fa_console` |
|-------|------------------------------|-------------------|
| **Encoding** | Legacy console code page (720 / 1252 / …) mangles UTF-8 on redirect or piping; crashes with `UnicodeEncodeError` | Console code page switched to UTF-8 (65001); standard streams reconfigured to UTF-8; child processes pinned via `PYTHONUTF8` |
| **Rendering** | Classic console host (`conhost`) has no Arabic shaping and no bidirectional reordering — correct text is *drawn* disconnected and backwards | Every write is converted to visual order (letter shaping + bidi) so text appears joined and right-to-left. While typing, `fa_input` echoes correctly in real time |

**Before**

```
>>> print("سلام دنیا")
ﺎﯿﻧﺩ ﻡﻼﺳ          # disconnected, reversed, unreadable
```

**After**

```
>>> import fa_console
>>> print("سلام دنیا")
سلام دنیا          # joined, right-to-left, readable
```

## Features

- ✅ **One-line setup** — `import fa_console` configures everything at import time
- ✅ **Encoding layer** — UTF-8 code page, UTF-8 `sys.stdin`/`sys.stdout`/`sys.stderr`
  (neutralises even a broken `PYTHONIOENCODING`), and pinned environment variables
  for spawned subprocesses
- ✅ **Rendering layer** — logical→visual transformation (letter shaping into
  Unicode Arabic Presentation Forms + bidirectional reordering) applied to *all*
  output, including plain `print()` and f-strings
- ✅ **Two transformation backends** — uses `arabic-reshaper` + `python-bidi`
  when installed (full UAX #9, lam-alef ligatures, Persian rules); otherwise a
  built-in, dependency-free engine
- ✅ **Live-typing echo** — `fa_input()` renders letters joined and right-to-left
  *while you type*, with built-in-`input()`-compatible semantics
  (`KeyboardInterrupt` / `EOFError`)
- ✅ **Smart detection** — Windows Terminal and redirected files/pipes are
  left untouched; the VS Code integrated terminal gets the same visual
  transform as the classic console (its xterm.js engine lacks reliable
  bidi reordering)
- ✅ **Fail-open design** — the module never crashes the host application; every
  internal failure is logged through the `fa_console` logger and degrades
  gracefully to standard Python behaviour
- ✅ **Zero required dependencies** — pure standard library, Python 3.8+

## Installation

```bash
pip install fa-console
```

Optional, higher-fidelity rendering backend:

```bash
pip install "fa-console[high-fidelity]"   # arabic-reshaper + python-bidi
```

Or simply copy `fa_console.py` into your project — it is intentionally a
single, self-contained module.

## Quick start

```python
import fa_console                      # everything is configured here

print("سلام دنیا!")                    # renders correctly everywhere
name = fa_console.fa_input("نام شما: ")  # live, correct echo while typing
print(f"سلام، {name} جان!")            # logical data, correct display
```

The value returned by `input()` / `fa_input()` is always **logical-order**
Unicode: comparisons, `len()`, slicing, regexes and file writes all see plain,
correct Persian text. Visual transformation is a display-time-only concern.

## API overview

| Member | Purpose |
|--------|---------|
| `setup_console(force=False)` | Apply the full configuration; idempotent. Returns a `ConsoleSetupReport` |
| `fa_print(*args, **kwargs)` | Persian-safe drop-in for `print()` |
| `fa_input(prompt="")` | Persian-safe `input()` with live correct echo |
| `is_visual_mode()` | `True` when the display transform is active |
| `get_console_info()` | Dict snapshot of the detected environment (great for bug reports) |
| `VisualStream` | The transparent stream wrapper (advanced use) |
| `FaConsoleError` | Deliberate low-level failures (consumed internally — fail-open) |

### Self-diagnostics

```bash
python fa_console.py
```

Prints a full environment report: encodings, console code page, detected
terminal type, active bidi backend and a rendered sample.

## How it works

1. **Encoding layer** — `SetConsoleCP`/`SetConsoleOutputCP` (Win32) switch the
   console to UTF-8; `sys.stdin`/`sys.stdout`/`sys.stderr` are reconfigured to
   UTF-8; `PYTHONUTF8=1` / `PYTHONIOENCODING=utf-8` are pinned for child
   processes.
2. **Rendering layer** — on classic `conhost` only, a `VisualStream` wrapper is
   installed on stdout/stderr. Each write is converted: Arabic/Persian letters
   are replaced by their contextual presentation forms (isolated / initial /
   medial / final, including پ چ ژ ک گ ی), then the line is reordered for an
   LTR-drawing terminal while Latin words and numbers stay upright and brackets
   are mirrored.
3. **Detection** — the transform engages only when stdout is an interactive
   classic console. Windows Terminal (`WT_SESSION`), VS Code terminals
   (`TERM_PROGRAM`) and redirected output are bypassed, because they render
   Arabic correctly or must receive standard logical text.

## Configuration

| Environment variable | Effect |
|----------------------|--------|
| `FA_CONSOLE_FORCE_VISUAL=1` | Force the visual transform on (debugging) |
| `FA_CONSOLE_NO_VISUAL=1` | Unconditionally disable the visual transform |

## Compatibility

| Environment | Behaviour |
|-------------|-----------|
| `cmd.exe` / standalone PowerShell (conhost) | Encoding fixed + visual transform + live typing echo |
| Windows Terminal | Encoding fixed; native rendering (module steps aside) |
| VS Code integrated terminal | Encoding fixed + visual transform (xterm.js has no reliable bidi) |
| JetBrains / IDLE consoles | Encoding fixed; module steps aside (non-tty) |
| Output redirected to file / pipe | Standard logical UTF-8 — safe for other tools |
| Linux / macOS | Safe no-op (standard behaviour) |

## Limitations & FAQ

- **Letters look disconnected while I type in `cmd`.** `fa_input()` redraws the
  line correctly as you type; the console's own echo of system prompts is
  outside any program's control.
- **Perfect native rendering?** Use [Windows Terminal](https://aka.ms/terminal)
  — the module detects it and lets it do the shaping.
- **Does the transform corrupt my data?** No — it is display-only. Values,
  comparisons and files always hold logical text.
- **Persian looks wrong in the VS Code terminal.** That is an xterm.js
  limitation — this package compensates automatically by applying the same
  visual transform used for the classic console (see
  `FA_CONSOLE_NO_VISUAL=1` if you ever need to switch it off).
- **Other RTL languages?** The shaping tables cover Arabic and Persian letters;
  the engine is language-agnostic for the letters it knows.

## Development

```bash
git clone https://github.com/Padandish/fa-console.git
cd fa-console
python -m pip install build
python -m build          # creates dist/
```

Run the interactive example in any console:

```bash
python example.py
```

Run the full environment diagnostics:

```bash
python fa_console.py
```

## Author

**Alireza Hosseini** — [alireza.hosseini@hotmail.com](mailto:alireza.hosseini@hotmail.com)

### Tech channels

Follow **TechInsightsHub** for updates, tutorials and related projects:

| Platform | Link |
|----------|------|
| Bale | [ble.ir/TechInsightsHub](https://ble.ir/TechInsightsHub) |
| Eitaa | [eitaa.com/TechInsightsHub](https://eitaa.com/TechInsightsHub) |
| Aparat | [aparat.com/TechInsightsHub](https://aparat.com/TechInsightsHub) |

## License

[MIT](LICENSE) © Alireza Hosseini
