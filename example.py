# -*- coding: utf-8 -*-
"""
example.py — quick tour of the fa_console package
=================================================

Run it in any console (cmd.exe, classic PowerShell, Windows Terminal):

    python example.py

The single import below configures UTF-8 everywhere and — on the classic
Windows console (conhost) — also installs the display transform, so every
``print`` / ``input`` afterwards handles Persian out of the box.

Author: Alireza Hosseini <alireza.hosseini@hotmail.com>
"""

import fa_console  # one import does all the configuration

# ------------------------------------------------------------------ output
fa_console.fa_print("سلام دنیا! این متن حتی در cmd کلاسیک هم درست دیده می‌شود.")
print("متن مخلوط: سال ۱۴۰۵ — نسخه 2.0 — 100% آماده")  # plain print works too

# ------------------------------------------------------- environment probe
info = fa_console.get_console_info()
print()
fa_console.fa_print(f"تبدیل نمایشی فعال : {fa_console.is_visual_mode()}")
fa_console.fa_print(f"موتور bidi        : {info['bidi_backend']}")
fa_console.fa_print(f"کدپیج کنسول       : {info['console_codepage']}")
fa_console.fa_print(f"انکودینگ stdout   : {info['stdout_encoding']}")
print("-" * 52)

# ------------------------------------------------------------------- input
name = fa_console.fa_input("نام خود را وارد کنید: ")
print()
fa_console.fa_print(f"سلام، {name} جان! خوش آمدی.")
fa_console.fa_print(f"طول نام شما: {len(name)} کاراکتر")
fa_console.fa_print("حروف نام شما: " + " · ".join(name))
print()

# ------------------------------------------------------ data stays logical
# The visual transform is display-only: strings keep the correct length,
# comparisons succeed and files/storage receive standard logical UTF-8.
sample = "سلام دنیا"
fa_console.fa_print(f"داده منطقی سالم: len('{sample}') = {len(sample)} (انتظار: 9)")
fa_console.fa_print(f"مقایسه مستقیم: {'سلام' in sample} ✓")

print()
fa_console.fa_print("پایان! گزارش کامل محیط: python fa_console.py")
