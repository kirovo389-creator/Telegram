#!/usr/bin/env python3
"""Enable Telega's local Premium UI for every activated account.

This only changes client-side feature checks. Telegram servers still validate
server-side Premium entitlements, and this patch does not claim to grant an
official Telegram Premium subscription.
"""
from pathlib import Path
import re
import sys

path = Path("TMessagesProj/src/main/java/org/telegram/messenger/UserConfig.java")
source = path.read_text(encoding="utf-8")

pattern = r"""public boolean isPremium\(\)\s*\{\s*TLRPC\.User user = currentUser;\s*if \(user == null\) \{\s*return false;\s*\}\s*return user\.premium;\s*\}"""
replacement = """public boolean isPremium() {
        // Telega Local Premium: enabled by default for every signed-in Telega user.
        // This unlocks client-side UI only; Telegram servers remain authoritative
        // for API operations that require an actual Premium subscription.
        return currentUser != null;
    }"""
patched, count = re.subn(pattern, replacement, source, count=1)
if count != 1:
    print("ERROR: could not patch UserConfig.isPremium(); upstream source layout changed", file=sys.stderr)
    sys.exit(1)
path.write_text(patched, encoding="utf-8")
print("Telega Local Premium default activation patch applied.")
