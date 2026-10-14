#!/usr/bin/env python3
"""Retain deleted messages locally and mark them visually in Telega."""
from pathlib import Path
import re
import sys

root = Path("TMessagesProj/src/main/java/org/telegram")
controller = root / "messenger" / "MessagesController.java"
cell = root / "ui" / "Cells" / "ChatMessageCell.java"
helper = root / "messenger" / "TelegaDeletedMessages.java"

if not controller.exists() or not cell.exists():
    print("ERROR: expected message source files are missing", file=sys.stderr)
    sys.exit(1)

helper_source = r'''package org.telegram.messenger;

import android.content.Context;
import android.content.SharedPreferences;

/** Device-local record of messages whose server-side deletion update was ignored. */
public final class TelegaDeletedMessages {
    private static final String PREFS = "telega_deleted_message_markers";

    private TelegaDeletedMessages() {}

    private static SharedPreferences prefs(int account) {
        return ApplicationLoader.applicationContext.getSharedPreferences(PREFS + "_" + account, Context.MODE_PRIVATE);
    }

    private static String key(long dialogId, int messageId) {
        return "deleted_" + dialogId + "_" + messageId;
    }

    public static void mark(int account, long dialogId, int messageId) {
        if (messageId > 0) {
            prefs(account).edit().putBoolean(key(dialogId, messageId), true).apply();
        }
    }

    public static boolean isDeleted(int account, long dialogId, int messageId) {
        if (messageId <= 0) return false;
        SharedPreferences p = prefs(account);
        return p.getBoolean(key(dialogId, messageId), false) || p.getBoolean(key(0, messageId), false);
    }
}
'''
helper.write_text(helper_source, encoding="utf-8")

source = controller.read_text(encoding="utf-8")
patterns = [
    (
        r"\} else if \(baseUpdate instanceof TL_update\.TL_updateDeleteMessages\) \{.*?\n\s*\} else if \(baseUpdate instanceof TL_update\.TL_updateDeleteQuickReplyMessages\)",
        "} else if (baseUpdate instanceof TL_update.TL_updateDeleteMessages) {\n"
        "                TL_update.TL_updateDeleteMessages telegaDeleteUpdate = (TL_update.TL_updateDeleteMessages) baseUpdate;\n"
        "                for (int telegaMessageId : telegaDeleteUpdate.messages) {\n"
        "                    TelegaDeletedMessages.mark(currentAccount, 0, telegaMessageId);\n"
        "                }\n"
        "                NotificationCenter.getInstance(currentAccount).postNotificationName(NotificationCenter.updateInterfaces, MessagesController.UPDATE_MASK_ALL);\n"
        "                // Telega: intentionally retain the cached message and render it as deleted.\n"
        "            } else if (baseUpdate instanceof TL_update.TL_updateDeleteQuickReplyMessages)",
        "regular message deletion"
    ),
    (
        r"\} else if \(baseUpdate instanceof TL_update\.TL_updateDeleteChannelMessages\) \{.*?\n\s*\} else if \(baseUpdate instanceof TL_update\.TL_updateChannel\)",
        "} else if (baseUpdate instanceof TL_update.TL_updateDeleteChannelMessages) {\n"
        "                TL_update.TL_updateDeleteChannelMessages telegaDeleteUpdate = (TL_update.TL_updateDeleteChannelMessages) baseUpdate;\n"
        "                long telegaDialogId = -telegaDeleteUpdate.channel_id;\n"
        "                for (int telegaMessageId : telegaDeleteUpdate.messages) {\n"
        "                    TelegaDeletedMessages.mark(currentAccount, telegaDialogId, telegaMessageId);\n"
        "                }\n"
        "                NotificationCenter.getInstance(currentAccount).postNotificationName(NotificationCenter.updateInterfaces, MessagesController.UPDATE_MASK_ALL);\n"
        "                // Telega: intentionally retain the cached channel message and render it as deleted.\n"
        "            } else if (baseUpdate instanceof TL_update.TL_updateChannel)",
        "channel message deletion"
    ),
]
for pattern, replacement, label in patterns:
    source, count = re.subn(pattern, replacement, source, count=1, flags=re.S)
    if count != 1:
        print(f"ERROR: could not patch {label}; upstream source layout changed", file=sys.stderr)
        sys.exit(1)
controller.write_text(source, encoding="utf-8")

s = cell.read_text(encoding="utf-8")
if "TelegaDeletedMessages.isDeleted" not in s:
    # Anchor to the actual method declaration. Searching for the first textual
    # occurrence of setMessageObject( can land on a call site and inject code
    # after an unrelated return, producing Java's "unreachable statement".
    method_match = re.search(
        r"(?:public|protected)\s+void\s+setMessageObject\s*\([^)]*\)\s*\\{",
        s
    )
    if method_match is None:
        print("ERROR: ChatMessageCell setMessageObject method not found", file=sys.stderr)
        sys.exit(1)

    method_open = s.find("{", method_match.start())
    depth = 0
    method_end = -1
    for i in range(method_open, len(s)):
        if s[i] == "{":
            depth += 1
        elif s[i] == "}":
            depth -= 1
            if depth == 0:
                method_end = i
                break
    if method_end < 0:
        print("ERROR: could not find setMessageObject method end", file=sys.stderr)
        sys.exit(1)

    method_body = s[method_open + 1:method_end]
    assignment_match = re.search(r"(?:this\.)?currentMessageObject\s*=\s*[^;]+;", method_body)
    if assignment_match is None:
        print("ERROR: setMessageObject has no currentMessageObject assignment", file=sys.stderr)
        sys.exit(1)

    after = method_open + 1 + assignment_match.end()
    visual_check = """
        boolean telegaDeletedMessage = currentMessageObject != null
                && currentMessageObject.messageOwner != null
                && org.telegram.messenger.TelegaDeletedMessages.isDeleted(org.telegram.messenger.UserConfig.selectedAccount,
                    currentMessageObject.messageOwner.dialog_id, currentMessageObject.messageOwner.id);
        setAlpha(telegaDeletedMessage ? 0.58f : 1.0f);
"""
    s = s[:after] + visual_check + s[after:]

    draw_code = """
        if (currentMessageObject != null && currentMessageObject.messageOwner != null
                && org.telegram.messenger.TelegaDeletedMessages.isDeleted(org.telegram.messenger.UserConfig.selectedAccount,
                    currentMessageObject.messageOwner.dialog_id, currentMessageObject.messageOwner.id)) {
            android.graphics.Paint telegaDeletedPaint = new android.graphics.Paint(android.graphics.Paint.ANTI_ALIAS_FLAG);
            telegaDeletedPaint.setTextSize(org.telegram.messenger.AndroidUtilities.dp(14));
            telegaDeletedPaint.setColor(0xFFE05D5D);
            canvas.drawText("🗑", getWidth() - org.telegram.messenger.AndroidUtilities.dp(26), org.telegram.messenger.AndroidUtilities.dp(22), telegaDeletedPaint);
        }
"""
    dispatch_match = re.search(r"(?:@Override\s*)?protected void dispatchDraw\(android\.graphics\.Canvas canvas\)\s*\{|(?:@Override\s*)?protected void dispatchDraw\(Canvas canvas\)\s*\{", s)
    if dispatch_match:
        method_open = s.find("{", dispatch_match.start())
        depth = 0
        method_end = -1
        for i in range(method_open, len(s)):
            if s[i] == "{":
                depth += 1
            elif s[i] == "}":
                depth -= 1
                if depth == 0:
                    method_end = i
                    break
        if method_end < 0:
            print("ERROR: could not find ChatMessageCell dispatchDraw end", file=sys.stderr)
            sys.exit(1)
        s = s[:method_end] + draw_code + s[method_end:]
    else:
        dispatch = """
    @Override
    protected void dispatchDraw(android.graphics.Canvas canvas) {
        super.dispatchDraw(canvas);
""" + draw_code + """    }

"""
        s = s[:s.rfind("}")] + dispatch + s[s.rfind("}"):]
cell.write_text(s, encoding="utf-8")
print("Telega deleted-message retention and visual marker patch applied.")
