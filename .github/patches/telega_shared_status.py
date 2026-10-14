#!/usr/bin/env python3
"""Add Telega-only shared emoji statuses using Telegram profile bio as transport.

The status is encoded in Unicode tag characters at the end of the bio, so
ordinary Telegram clients normally render no visible marker. This is not an
official Telegram emoji status and may be stripped by clients/servers.
"""
from pathlib import Path
import re
import sys

root = Path("TMessagesProj/src/main/java/org/telegram")
helper = root / "messenger" / "TelegaLocalStatus.java"
profile = root / "ui" / "ProfileActivity.java"

helper_source = r'''package org.telegram.messenger;

/**
 * Telega shared local status transport. Stores a custom-emoji document ID in
 * Unicode tag characters appended to the Telegram bio. Telegram's profile
 * storage acts as the sync channel; no Telega-owned server is used.
 */
public final class TelegaLocalStatus {
    private static final int TAG_BASE = 0xE0000;
    private static final int TAG_END = 0xE007F;
    private static final String PREFIX = "TG1.";

    private TelegaLocalStatus() {}

    public static String update(String about, long documentId, int until) {
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
    }

    public static String strip(String about) {
        if (about == null || about.isEmpty()) return about == null ? "" : about;
        int end = about.codePointBefore(about.length());
        if (end != TAG_END) return about;
        int cursor = about.length() - Character.charCount(end);
        int start = cursor;
        while (start > 0) {
            int cp = about.codePointBefore(start);
            if (cp < TAG_BASE || cp >= TAG_END) break;
            start -= Character.charCount(cp);
        }
        String decoded = decode(about.substring(start, cursor));
        if (decoded == null || !decoded.startsWith(PREFIX)) return about;
        return about.substring(0, start);
    }

    public static long getDocumentId(String about) {
        String payload = getPayload(about);
        if (payload == null || !payload.startsWith(PREFIX)) return 0;
        String[] parts = payload.split("\\\\.", -1);
        if (parts.length != 3) return 0;
        try {
            return Long.parseLong(parts[1], 36);
        } catch (Throwable ignore) {
            return 0;
        }
    }

    public static int getUntil(String about) {
        String payload = getPayload(about);
        if (payload == null || !payload.startsWith(PREFIX)) return 0;
        String[] parts = payload.split("\\\\.", -1);
        if (parts.length != 3) return 0;
        try {
            return Integer.parseInt(parts[2], 36);
        } catch (Throwable ignore) {
            return 0;
        }
    }

    private static String getPayload(String about) {
        if (about == null || about.isEmpty() || about.codePointBefore(about.length()) != TAG_END) return null;
        int cursor = about.length() - Character.charCount(TAG_END);
        int start = cursor;
        while (start > 0) {
            int cp = about.codePointBefore(start);
            if (cp < TAG_BASE || cp >= TAG_END) break;
            start -= Character.charCount(cp);
        }
        return decode(about.substring(start, cursor));
    }

    private static String decode(String encoded) {
        StringBuilder out = new StringBuilder();
        for (int i = 0; i < encoded.length();) {
            int cp = encoded.codePointAt(i);
            if (cp < TAG_BASE || cp >= TAG_END) return null;
            out.append((char) (cp - TAG_BASE));
            i += Character.charCount(cp);
        }
        return out.toString();
    }
}
'''

helper.write_text(helper_source, encoding="utf-8")

s = profile.read_text(encoding="utf-8")
if "import org.telegram.messenger.TelegaLocalStatus;" not in s:
    marker = "import org.telegram.messenger.UserConfig;"
    if marker not in s:
        print("ERROR: ProfileActivity import anchor not found", file=sys.stderr)
        sys.exit(1)
    s = s.replace(marker, marker + "\nimport org.telegram.messenger.TelegaLocalStatus;", 1)

# Use the existing animated emoji selector, but save the choice in the shared
# profile bio for own-user statuses. Channel statuses retain their native path.
call = "getMessagesController().updateEmojiStatus(currentChat == null ? 0 : -currentChat.id, emojiStatus, gift);"
replacement = """if (currentChat == null && gift == null) {
                    saveTelegaLocalStatus(documentId == null ? 0L : documentId, until == null ? 0 : until);
                } else {
                    getMessagesController().updateEmojiStatus(currentChat == null ? 0 : -currentChat.id, emojiStatus, gift);
                }"""
if call not in s:
    print("ERROR: status-selection update call not found; upstream source layout changed", file=sys.stderr)
    sys.exit(1)
s = s.replace(call, replacement, 1)

# Insert the profile-bio transport helper before showStatusSelect.
anchor = "    public void showStatusSelect() {"
method = r'''    private void saveTelegaLocalStatus(long documentId, int until) {
        if (getParentActivity() == null) return;
        long selfId = UserConfig.getInstance(currentAccount).getClientUserId();
        TLRPC.UserFull full = userInfo != null ? userInfo : getMessagesController().getUserFull(selfId);
        String oldAbout = full == null || full.about == null ? "" : full.about;
        String newAbout = TelegaLocalStatus.update(oldAbout, documentId, until);
        if (oldAbout.equals(newAbout)) return;

        TL_account.updateProfile request = new TL_account.updateProfile();
        request.flags |= 4;
        request.about = newAbout;
        ConnectionsManager.getInstance(currentAccount).sendRequest(request, (response, error) -> AndroidUtilities.runOnUIThread(() -> {
            if (error != null) {
                FileLog.e("Telega shared status save failed: " + error.text);
                if (getParentActivity() != null) {
                    org.telegram.ui.Components.AlertsCreator.processError(currentAccount, error, ProfileActivity.this, request);
                }
                return;
            }
            if (full != null) full.about = newAbout;
            if (response instanceof TLRPC.User) {
                TLRPC.User updatedUser = (TLRPC.User) response;
                if (full != null) {
                    NotificationCenter.getInstance(currentAccount).postNotificationName(NotificationCenter.userInfoDidLoad, updatedUser.id, full);
                }
            }
            updateProfileData(true);
            getNotificationCenter().postNotificationName(NotificationCenter.updateInterfaces, MessagesController.UPDATE_MASK_ALL);
        }), ConnectionsManager.RequestFlagFailOnServerErrors);
    }

'''
if anchor not in s:
    print("ERROR: showStatusSelect anchor not found", file=sys.stderr)
    sys.exit(1)
s = s.replace(anchor, method + anchor, 1)

# In the profile header, prefer the server status; if absent, show the shared
# Telega status decoded from the viewed user's profile bio.
condition = "if (user != null/* && !getMessagesController().premiumFeaturesBlocked()*/ && !MessagesController.isSupportUser(user) && DialogObject.getEmojiStatusDocumentId(user.emoji_status) != 0) {"
condition_new = """if (user != null/* && !getMessagesController().premiumFeaturesBlocked()*/ && !MessagesController.isSupportUser(user) && (DialogObject.getEmojiStatusDocumentId(user.emoji_status) != 0 || (userInfo != null && TelegaLocalStatus.getDocumentId(userInfo.about) != 0))) {
                        TLRPC.EmojiStatus telegaStatusToShow = user.emoji_status;
                        if (DialogObject.getEmojiStatusDocumentId(telegaStatusToShow) == 0 && userInfo != null) {
                            long telegaDocumentId = TelegaLocalStatus.getDocumentId(userInfo.about);
                            if (telegaDocumentId != 0) {
                                TLRPC.TL_emojiStatus localStatus = new TLRPC.TL_emojiStatus();
                                localStatus.document_id = telegaDocumentId;
                                int telegaUntil = TelegaLocalStatus.getUntil(userInfo.about);
                                if (telegaUntil > 0) {
                                    localStatus.flags |= 1;
                                    localStatus.until = telegaUntil;
                                }
                                telegaStatusToShow = localStatus;
                            }
                        }"""
if condition not in s:
    print("ERROR: profile emoji status rendering anchor not found", file=sys.stderr)
    sys.exit(1)
s = s.replace(condition, condition_new, 1)
render_call = "nameTextView[a].setRightDrawable(getEmojiStatusDrawable(user.emoji_status, false, false, a));"
if render_call not in s:
    print("ERROR: profile emoji drawable call not found", file=sys.stderr)
    sys.exit(1)
s = s.replace(render_call, "nameTextView[a].setRightDrawable(getEmojiStatusDrawable(telegaStatusToShow, false, false, a));", 1)

profile.write_text(s, encoding="utf-8")
print("Telega shared local emoji status patch applied.")
