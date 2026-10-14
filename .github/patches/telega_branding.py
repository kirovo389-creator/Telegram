#!/usr/bin/env python3
"""Replace user-facing Telegram branding in Android string resources with Telega."""
from pathlib import Path
import re
import sys

res = Path("TMessagesProj/src/main/res")
if not res.exists():
    print("ERROR: Android resources directory missing", file=sys.stderr)
    sys.exit(1)

files = list(res.glob("values*/strings.xml"))
if not files:
    print("ERROR: no strings.xml resource files found", file=sys.stderr)
    sys.exit(1)

changed = 0
for path in files:
    source = path.read_text(encoding="utf-8")
    original = source

    def replace_text(match):
        text = match.group(1)
        # Preserve product/support URLs and email addresses that intentionally
        # point to Telegram's official infrastructure.
        if "://" in text or "telegram.org" in text.lower() or "@telegram" in text.lower():
            return match.group(0)
        text = re.sub(r"(?<![A-Za-z])Telegram Beta(?![A-Za-z])", "Telega Beta", text)
        text = re.sub(r"(?<![A-Za-z])Telegram(?![A-Za-z])", "Telega", text)
        return ">" + text + "<"

    source = re.sub(r">([^<>]*)<", replace_text, source)
    if source != original:
        path.write_text(source, encoding="utf-8")
        changed += 1

print(f"Telega branding updated in {changed} Android string resource files.")
