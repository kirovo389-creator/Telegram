#!/usr/bin/env python3
"""Apply Telega's local deleted-message retention patch after upstream sync.

This deliberately ignores server deletion updates in this client only. It does not
restore messages on Telegram's servers or other clients.
"""
from pathlib import Path
import re
import sys

path = Path("TMessagesProj/src/main/java/org/telegram/messenger/MessagesController.java")
source = path.read_text(encoding="utf-8")

patterns = [
    (
        r"\} else if \(baseUpdate instanceof TL_update\.TL_updateDeleteMessages\) \{.*?\n\s*\} else if \(baseUpdate instanceof TL_update\.TL_updateDeleteQuickReplyMessages\)",
        "} else if (baseUpdate instanceof TL_update.TL_updateDeleteMessages) {\n"
        "                // Telega: keep a local copy when a regular message is deleted remotely.\n"
        "            } else if (baseUpdate instanceof TL_update.TL_updateDeleteQuickReplyMessages)",
        "regular message deletion"
    ),
    (
        r"\} else if \(baseUpdate instanceof TL_update\.TL_updateDeleteChannelMessages\) \{.*?\n\s*\} else if \(baseUpdate instanceof TL_update\.TL_updateChannel\)",
        "} else if (baseUpdate instanceof TL_update.TL_updateDeleteChannelMessages) {\n"
        "                // Telega: keep a local copy when a channel message is deleted remotely.\n"
        "            } else if (baseUpdate instanceof TL_update.TL_updateChannel)",
        "channel message deletion"
    ),
]

for pattern, replacement, label in patterns:
    source, count = re.subn(pattern, replacement, source, count=1, flags=re.S)
    if count != 1:
        print(f"ERROR: could not patch {label}; upstream source layout changed", file=sys.stderr)
        sys.exit(1)

path.write_text(source, encoding="utf-8")
print("Telega deleted-message retention patch applied.")
