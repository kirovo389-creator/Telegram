#!/usr/bin/env python3
"""Repair the profile-style patch against current upstream source."""
from pathlib import Path
import sys

root = Path("TMessagesProj/src/main/java/org/telegram")
profile = root / "ui" / "ProfileActivity.java"
color_activity = root / "ui" / "PeerColorActivity.java"

p = profile.read_text(encoding="utf-8")
# The earlier patch accidentally inserted the literal characters \n before this block.
bad_start = r"\n            if (userInfo != null) {"
if bad_start in p:
    start = p.index(bad_start)
    end_marker = "\n            }\n\n        if (avatarContainer == null"
    end = p.find(end_marker, start)
    if end < 0:
        print("ERROR: malformed profile-style block end not found", file=sys.stderr)
        sys.exit(1)
    p = p[:start] + p[end + len("\n            }\n"):]

# Apply style only where the local variable user exists.
anchor = """if (userId != 0) {
            TLRPC.User user = getMessagesController().getUser(userId);
            if (user == null) {
                return;
            }"""
style = """if (userInfo != null) {
                int telegaProfileColor = TelegaLocalStatus.getProfileColor(userInfo.about);
                long telegaBackgroundEmoji = TelegaLocalStatus.getProfileEmoji(userInfo.about);
                if (telegaProfileColor >= 0 || telegaBackgroundEmoji != 0) {
                    if (user.profile_color == null) user.profile_color = new TLRPC.TL_peerColor();
                    if (telegaProfileColor >= 0) {
                        user.profile_color.flags |= 1;
                        user.profile_color.color = telegaProfileColor;
                    }
                    if (telegaBackgroundEmoji != 0) {
                        user.profile_color.flags |= 2;
                        user.profile_color.background_emoji_id = telegaBackgroundEmoji;
                    }
                }
            }"""
if "int telegaProfileColor = TelegaLocalStatus.getProfileColor(userInfo.about);" not in p:
    if anchor not in p:
        print("ERROR: ProfileActivity viewed-user anchor not found", file=sys.stderr)
        sys.exit(1)
    p = p.replace(anchor, anchor + "\n            " + style, 1)
profile.write_text(p, encoding="utf-8")

c = color_activity.read_text(encoding="utf-8")
c = c.replace('FileLog.e("Telega profile style save failed: " + error.text);',
              'Log.e("Telega", "Profile style save failed: " + error.text);')
c = c.replace('}), ConnectionsManager.RequestFlagFailOnServerErrors);', '}));')
color_activity.write_text(c, encoding="utf-8")
print("Telega profile-style compile fixes applied.")
