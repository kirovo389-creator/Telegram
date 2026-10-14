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
        r"(\\} else if \\(baseUpdate instanceof TL_update\\.TL_updateDeleteMessages\\) \\{)(.*?)(\\n\\s*\\} else if \\(baseUpdate instanceof TL_update\\.TL_updateDeleteQuickReplyMessages\\))",
        "                TL_update.TL_updateDeleteMessages telegaDeleteUpdate = (TL_update.TL_updateDeleteMessages) baseUpdate;\\n"
        "                for (int telegaMessageId : telegaDeleteUpdate.messages) {\\n"
        "                    TelegaDeletedMessages.mark(currentAccount, 0, telegaMessageId);\\n"
        "                }\\n"
        "                NotificationCenter.getInstance(currentAccount).postNotificationName(NotificationCenter.updateInterfaces, MessagesController.UPDATE_MASK_ALL);\\n"
        "                // Telega: retain this message and mark it deleted.",
        "regular message deletion"
    ),
    (
        r"(\\} else if \\(baseUpdate instanceof TL_update\\.TL_updateDeleteChannelMessages\\) \\{)(.*?)(\\n\\s*\\} else if \\(baseUpdate instanceof TL_update\\.TL_updateChannel\\))",
        "                TL_update.TL_updateDeleteChannelMessages telegaDeleteUpdate = (TL_update.TL_updateDeleteChannelMessages) baseUpdate;\\n"
        "                long telegaDialogId = -telegaDeleteUpdate.channel_id;\\n"
        "                for (int telegaMessageId : telegaDeleteUpdate.messages) {\\n"
        "                    TelegaDeletedMessages.mark(currentAccount, telegaDialogId, telegaMessageId);\\n"
        "                }\\n"
        "                NotificationCenter.getInstance(currentAccount).postNotificationName(NotificationCenter.updateInterfaces, MessagesController.UPDATE_MASK_ALL);\\n"
        "                // Telega: retain this channel message and mark it deleted.",
        "channel message deletion"
    ),
]
for pattern, replacement_body, label in patterns:
    match = re.search(pattern, source, count=1, flags=re.S)
    if not match:
        print(f"ERROR: could not patch {label}; upstream source layout changed", file=sys.stderr)
        sys.exit(1)
    branch_start, original_body, next_branch = match.groups()
    wrapped = (
        branch_start
        + "\\n                if (TelegaFeatures.isDeletedMessagesEnabled(currentAccount)) {\\n"
        + replacement_body
        + "\\n                } else {"
        + original_body
        + "\\n                }"
        + next_branch
    )
    source = source[:match.start()] + wrapped + source[match.end():]
controller.write_text(source, encoding="utf-8")

s = cell.read_text(encoding="utf-8")
if "TelegaDeletedMessages.isDeleted" not in s:
    # Apply translucency while drawing the cell's children. This avoids trying
    # to inject code into a message-binding method whose upstream overloads vary.
    draw_code = """
        if (currentMessageObject != null && currentMessageObject.messageOwner != null
                && org.telegram.messenger.TelegaDeletedMessages.isDeleted(org.telegram.messenger.UserConfig.selectedAccount,
                    currentMessageObject.messageOwner.dialog_id, currentMessageObject.messageOwner.id)) {
            android.graphics.Paint telegaDeletedPaint = new android.graphics.Paint(android.graphics.Paint.ANTI_ALIAS_FLAG);
            telegaDeletedPaint.setTextSize(org.telegram.messenger.AndroidUtilities.dp(14));
            telegaDeletedPaint.setColor(0xFF858585);
            canvas.drawText("🗑", org.telegram.messenger.AndroidUtilities.dp(12), getHeight() - org.telegram.messenger.AndroidUtilities.dp(10), telegaDeletedPaint);
        }
"""
    dispatch_match = re.search(
        r"(?:@Override\s*)?protected void dispatchDraw\(android\.graphics\.Canvas canvas\)\s*\{|"
        r"(?:@Override\s*)?protected void dispatchDraw\(Canvas canvas\)\s*\{",
        s
    )
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

        method_body = s[method_open:method_end + 1]
        original_draw = "super.dispatchDraw(canvas);"
        if original_draw not in method_body:
            print("ERROR: dispatchDraw super call not found", file=sys.stderr)
            sys.exit(1)
        wrapped_draw = """
        boolean telegaDeletedForDraw = currentMessageObject != null
                && currentMessageObject.messageOwner != null
                && org.telegram.messenger.TelegaDeletedMessages.isDeleted(org.telegram.messenger.UserConfig.selectedAccount,
                    currentMessageObject.messageOwner.dialog_id, currentMessageObject.messageOwner.id);
        if (telegaDeletedForDraw) {
            int telegaLayer = canvas.saveLayerAlpha(0, 0, getWidth(), getHeight(), 148);
            super.dispatchDraw(canvas);
            canvas.restoreToCount(telegaLayer);
        } else {
            super.dispatchDraw(canvas);
        }
"""
        method_body = method_body.replace(original_draw, wrapped_draw, 1)
        method_body = method_body[:-1] + draw_code + "\n    }"
        s = s[:method_open] + method_body + s[method_end + 1:]
    else:
        dispatch = """
    @Override
    protected void dispatchDraw(android.graphics.Canvas canvas) {
        boolean telegaDeletedForDraw = currentMessageObject != null
                && currentMessageObject.messageOwner != null
                && org.telegram.messenger.TelegaDeletedMessages.isDeleted(org.telegram.messenger.UserConfig.selectedAccount,
                    currentMessageObject.messageOwner.dialog_id, currentMessageObject.messageOwner.id);
        if (telegaDeletedForDraw) {
            int telegaLayer = canvas.saveLayerAlpha(0, 0, getWidth(), getHeight(), 148);
            super.dispatchDraw(canvas);
            canvas.restoreToCount(telegaLayer);
        } else {
            super.dispatchDraw(canvas);
        }
""" + draw_code + """    }

"""
        s = s[:s.rfind("}")] + dispatch + s[s.rfind("}"):]
cell.write_text(s, encoding="utf-8")
print("Telega deleted-message retention and visual marker patch applied.")
