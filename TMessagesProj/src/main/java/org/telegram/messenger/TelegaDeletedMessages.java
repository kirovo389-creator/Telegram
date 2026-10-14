package org.telegram.messenger;

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
