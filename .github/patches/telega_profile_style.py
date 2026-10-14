#!/usr/bin/env python3
"""Persist profile accent color and background emoji for Telega clients.

This extends the shared Telega profile-bio payload created by telega_shared_status.py.
It does not alter Telegram's server-side Premium checks; style sync uses invisible
Unicode tag metadata and is only interpreted by Telega builds carrying this patch.
"""
from pathlib import Path
import sys

root = Path("TMessagesProj/src/main/java/org/telegram")
status_file = root / "messenger" / "TelegaLocalStatus.java"
profile = root / "ui" / "ProfileActivity.java"
color_activity = root / "ui" / "PeerColorActivity.java"

if not status_file.exists() or not profile.exists() or not color_activity.exists():
    print("ERROR: Expected Telegram source files are missing", file=sys.stderr)
    sys.exit(1)

s = status_file.read_text(encoding="utf-8")
old_update = '''    public static String update(String about, long documentId, int until) {
        String clean = strip(about == null ? "" : about);
        if (documentId == 0) {
            return clean;
        }
        String payload = PREFIX + Long.toString(documentId, 36) + "." + Integer.toString(Math.max(0, until), 36);
        StringBuilder hidden = new StringBuilder();
        for (int i = 0; i < payload.length(); i++) {
            hidden.appendCodePoint(TAG_BASE + payload.charAt(i));
        }
        hidden.appendCodePoint(TAG_END);
        return clean + hidden;
    }'''
new_update = '''    private static String encodePayload(String clean, long documentId, int until, int color, long backgroundEmojiId) {
        if (documentId == 0 && color < 0 && backgroundEmojiId == 0) return clean;
        String payload = PREFIX + Long.toString(Math.max(0, documentId), 36) + "." + Integer.toString(Math.max(0, until), 36) + "." + Integer.toString(color + 1, 36) + "." + Long.toString(Math.max(0, backgroundEmojiId), 36);
        StringBuilder hidden = new StringBuilder();
        for (int i = 0; i < payload.length(); i++) hidden.appendCodePoint(TAG_BASE + payload.charAt(i));
        hidden.appendCodePoint(TAG_END);
        return clean + hidden;
    }

    public static String update(String about, long documentId, int until) {
        String source = about == null ? "" : about;
        int color = getProfileColor(source);
        long backgroundEmojiId = getProfileEmoji(source);
        String clean = strip(source);
        return encodePayload(clean, documentId, until, color, backgroundEmojiId);
    }

    public static String updateProfileStyle(String about, int color, long backgroundEmojiId) {
        String source = about == null ? "" : about;
        long documentId = getDocumentId(source);
        int until = getUntil(source);
        return encodePayload(strip(source), documentId, until, color, backgroundEmojiId);
    }

    public static int getProfileColor(String about) {
        String[] parts = getParts(about);
        if (parts == null || parts.length < 5) return -1;
        try { return Integer.parseInt(parts[3], 36) - 1; } catch (Throwable ignore) { return -1; }
    }

    public static long getProfileEmoji(String about) {
        String[] parts = getParts(about);
        if (parts == null || parts.length < 5) return 0;
        try { return Long.parseLong(parts[4], 36); } catch (Throwable ignore) { return 0; }
    }

    private static String[] getParts(String about) {
        String payload = getPayload(about);
        if (payload == null || !payload.startsWith(PREFIX)) return null;
        return payload.split("\\\\.", -1);
    }'''
if old_update not in s:
    print("ERROR: TelegaLocalStatus.update anchor not found", file=sys.stderr)
    sys.exit(1)
s = s.replace(old_update, new_update, 1)
s = s.replace('''        String payload = getPayload(about);
        if (payload == null || !payload.startsWith(PREFIX)) return 0;
        String[] parts = payload.split("\\\\.", -1);
        if (parts.length != 3) return 0;''','''        String[] parts = getParts(about);
        if (parts == null || parts.length < 3) return 0;''',1)
s = s.replace('''        String payload = getPayload(about);
        if (payload == null || !payload.startsWith(PREFIX)) return 0;
        String[] parts = payload.split("\\\\.", -1);
        if (parts.length != 3) return 0;''','''        String[] parts = getParts(about);
        if (parts == null || parts.length < 3) return 0;''',1)
status_file.write_text(s, encoding="utf-8")

c = color_activity.read_text(encoding="utf-8")
if "import org.telegram.messenger.TelegaLocalStatus;" not in c:
    marker = "import org.telegram.messenger.UserConfig;"
    if marker not in c:
        print("ERROR: PeerColorActivity import anchor not found", file=sys.stderr)
        sys.exit(1)
    c = c.replace(marker, marker + "\nimport org.telegram.messenger.TelegaLocalStatus;", 1)

call = "            getMessagesController().putUser(me, false);"
if call not in c:
    print("ERROR: PeerColorActivity apply/save anchor not found", file=sys.stderr)
    sys.exit(1)
c = c.replace(call, "            saveTelegaProfileStyle(me, profilePage.selectedColor, profilePage.selectedEmoji);\n" + call, 1)
method_anchor = "    private void showBulletin() {"
method = '''    private void saveTelegaProfileStyle(TLRPC.User me, int color, long backgroundEmojiId) {
        if (me == null) return;
        TLRPC.UserFull full = getMessagesController().getUserFull(me.id);
        if (full == null) return;
        String about = full.about == null ? "" : full.about;
        String newAbout = TelegaLocalStatus.updateProfileStyle(about, color, backgroundEmojiId);
        if (about.equals(newAbout)) return;
        TL_account.updateProfile request = new TL_account.updateProfile();
        request.flags |= 4;
        request.about = newAbout;
        getConnectionsManager().sendRequest(request, (response, error) -> AndroidUtilities.runOnUIThread(() -> {
            if (error != null) {
                Log.e("Telega", "Profile style save failed: " + error.text);
                return;
            }
            full.about = newAbout;
            getNotificationCenter().postNotificationName(NotificationCenter.updateInterfaces, MessagesController.UPDATE_MASK_ALL);
        }));
    }

'''
if method_anchor not in c:
    print("ERROR: PeerColorActivity method insertion anchor not found", file=sys.stderr)
    sys.exit(1)
c = c.replace(method_anchor, method + method_anchor, 1)
color_activity.write_text(c, encoding="utf-8")

p = profile.read_text(encoding="utf-8")
if "import org.telegram.messenger.TelegaLocalStatus;" not in p:
    marker = "import org.telegram.messenger.UserConfig;"
    if marker not in p:
        print("ERROR: ProfileActivity import anchor not found", file=sys.stderr)
        sys.exit(1)
    p = p.replace(marker, marker + "\nimport org.telegram.messenger.TelegaLocalStatus;", 1)

# Apply the shared style only after the viewed user object is available.
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
if anchor not in p:
    print("ERROR: ProfileActivity viewed-user anchor not found", file=sys.stderr)
    sys.exit(1)
p = p.replace(anchor, anchor + "\\n            " + style, 1)
profile.write_text(p, encoding="utf-8")
print("Telega shared profile color/background emoji patch applied.")
