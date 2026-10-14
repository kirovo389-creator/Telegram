package org.telegram.messenger;

import android.content.Context;
import android.content.SharedPreferences;
import android.graphics.Color;
import android.util.Log;

import org.telegram.tgnet.ConnectionsManager;
import org.telegram.tgnet.TLObject;
import org.telegram.tgnet.TLRPC;

import java.lang.reflect.Field;
import java.lang.reflect.Method;
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;

/** Settings and Telega-only interoperability helpers. */
public final class TelegaFeatures {
    private static final String PREFS = "telega_features";
    private static final int TAG_BASE = 0xE0000;
    private static final int TAG_END = 0xE007F;
    private static final String ARTICLE_TAG = "TELEGA_ARTICLE_V1";

    private TelegaFeatures() {}

    private static SharedPreferences prefs() {
        return ApplicationLoader.applicationContext.getSharedPreferences(PREFS, Context.MODE_PRIVATE);
    }

    public static boolean isDeletedMessagesEnabled(int account) {
        return prefs().getBoolean("deleted_messages", true);
    }
    public static void setDeletedMessagesEnabled(boolean enabled) {
        prefs().edit().putBoolean("deleted_messages", enabled).apply();
    }
    public static boolean isGhostModeEnabled() {
        return prefs().getBoolean("ghost_mode", false);
    }
    public static void setGhostModeEnabled(boolean enabled) {
        prefs().edit().putBoolean("ghost_mode", enabled).apply();
    }
    public static boolean isAutoArchiveEnabled() {
        return prefs().getBoolean("auto_archive", false);
    }
    public static void setAutoArchiveEnabled(boolean enabled) {
        prefs().edit().putBoolean("auto_archive", enabled).apply();
    }
    public static boolean isAntiSoundEnabled() {
        return prefs().getBoolean("anti_sound", false);
    }
    public static void setAntiSoundEnabled(boolean enabled) {
        prefs().edit().putBoolean("anti_sound", enabled).apply();
    }

    /** Prevent server read receipts and online-status renewals while Ghost mode is on. */
    public static boolean shouldSuppressRequest(int account, TLObject request) {
        if (!isGhostModeEnabled() || request == null) return false;
        String name = request.getClass().getSimpleName().toLowerCase(Locale.US);
        if (name.contains("updatestatus")) return true;
        return name.contains("readhistory")
                || name.contains("readmessagecontents")
                || name.contains("readmentions")
                || name.contains("readreactions")
                || name.contains("readdiscussion")
                || name.contains("readencryptedhistory")
                || name.contains("readstories");
    }

    /**
     * Mute and, where the current API exposes the request, move newly discovered bots/groups/channels
     * to Archive. A persistent per-dialog marker prevents repeated requests for existing peers.
     */
    public static void onPeerAvailable(int account, long dialogId, boolean eligible) {
        if (!eligible || (!isAutoArchiveEnabled() && !isAntiSoundEnabled())) return;
        SharedPreferences p = prefs();
        String key = "handled_" + account + "_" + dialogId;
        if (p.getBoolean(key, false)) return;
        p.edit().putBoolean(key, true).apply();
        final boolean archive = isAutoArchiveEnabled();
        final boolean mute = archive || isAntiSoundEnabled();
        AndroidUtilities.runOnUIThread(() -> {
            try {
                if (mute) NotificationsController.getInstance(account).muteDialog(dialogId, 0, true);
            } catch (Throwable error) {
                Log.w("Telega", "Unable to mute new dialog", error);
            }
            if (archive) {
                tryArchiveDialog(account, dialogId);
            }
        });
    }

    private static void tryArchiveDialog(int account, long dialogId) {
        try {
            Class<?> requestClass = Class.forName("org.telegram.tgnet.TLRPC$TL_messages_editPeerFolders");
            Object request = requestClass.getDeclaredConstructor().newInstance();
            Field peersField = requestClass.getField("folder_peers");
            Class<?> folderPeerClass = Class.forName("org.telegram.tgnet.TLRPC$TL_inputFolderPeer");
            Object folderPeer = folderPeerClass.getDeclaredConstructor().newInstance();
            Object controller = MessagesController.getInstance(account);
            Method getInputPeer = controller.getClass().getMethod("getInputPeer", long.class);
            Object inputPeer = getInputPeer.invoke(controller, dialogId);
            if (inputPeer == null) return;
            folderPeerClass.getField("peer").set(folderPeer, inputPeer);
            folderPeerClass.getField("folder_id").setInt(folderPeer, 1);
            ArrayList<Object> list = new ArrayList<>();
            list.add(folderPeer);
            peersField.set(request, list);
            ConnectionsManager.getInstance(account).sendRequest((TLObject) request, (response, error) -> {
                if (error != null || response == null) return;
                try {
                    Method processUpdates = controller.getClass().getMethod("processUpdates", TLRPC.Updates.class, boolean.class);
                    if (response instanceof TLRPC.Updates) processUpdates.invoke(controller, response, false);
                } catch (Throwable ignored) {
                }
            });
        } catch (Throwable error) {
            Log.w("Telega", "Auto Archive request is not supported by this API layer", error);
        }
    }

    private static String hiddenTag(String payload) {
        StringBuilder result = new StringBuilder();
        for (int i = 0; i < payload.length(); i++) result.appendCodePoint(TAG_BASE + payload.charAt(i));
        result.appendCodePoint(TAG_END);
        return result.toString();
    }

    /** Fallback transport: ordinary text plus an invisible marker; Telega renders it as an article. */
    public static String encodeArticle(String text) {
        String clean = text == null ? "" : text;
        return "Статья: " + clean + hiddenTag(ARTICLE_TAG);
    }

    /** Returns cleaned article text when the Telega marker is present; otherwise null. */
    public static String decodeArticle(String text) {
        if (text == null || text.isEmpty() || text.codePointBefore(text.length()) != TAG_END) return null;
        int cursor = text.length() - Character.charCount(TAG_END);
        int start = cursor;
        while (start > 0) {
            int cp = text.codePointBefore(start);
            if (cp < TAG_BASE || cp >= TAG_END) break;
            start -= Character.charCount(cp);
        }
        StringBuilder decoded = new StringBuilder();
        for (int i = start; i < cursor;) {
            int cp = text.codePointAt(i);
            if (cp < TAG_BASE || cp >= TAG_END) return null;
            decoded.append((char) (cp - TAG_BASE));
            i += Character.charCount(cp);
        }
        if (!ARTICLE_TAG.equals(decoded.toString())) return null;
        return text.substring(0, start);
    }
}
