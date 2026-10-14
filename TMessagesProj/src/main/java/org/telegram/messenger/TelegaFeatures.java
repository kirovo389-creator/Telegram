package org.telegram.messenger;

import android.content.Context;
import android.content.SharedPreferences;
import android.graphics.Color;
import android.graphics.drawable.GradientDrawable;
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
    private static final String LIST_TAG = "TELEGA_LIST_V1";

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
        if (enabled) markExistingDialogsHandled(UserConfig.selectedAccount);
    }
    public static boolean isAntiSoundEnabled() {
        return prefs().getBoolean("anti_sound", false);
    }
    public static void setAntiSoundEnabled(boolean enabled) {
        prefs().edit().putBoolean("anti_sound", enabled).apply();
        if (enabled) markExistingDialogsHandled(UserConfig.selectedAccount);
    }

    public static boolean isBadgeEnabled() {
        return prefs().getBoolean("telega_badge", false);
    }
    public static void setBadgeEnabled(boolean enabled) {
        prefs().edit().putBoolean("telega_badge", enabled).apply();
        AndroidUtilities.runOnUIThread(() -> {
            try {
                NotificationCenter.getGlobalInstance().postNotificationName(NotificationCenter.updateInterfaces, MessagesController.UPDATE_MASK_ALL);
            } catch (Throwable ignored) {}
        });
    }

    /** Snapshot current dialogs when the user enables these toggles, so old chats aren't swept into Archive. */
    public static void markExistingDialogsHandled(int account) {
        try {
            Object controller = MessagesController.getInstance(account);
            java.lang.reflect.Field field = controller.getClass().getDeclaredField("dialogs_dict");
            field.setAccessible(true);
            Object dialogs = field.get(controller);
            java.lang.reflect.Method size = dialogs.getClass().getMethod("size");
            java.lang.reflect.Method keyAt = dialogs.getClass().getMethod("keyAt", int.class);
            int count = ((Number) size.invoke(dialogs)).intValue();
            SharedPreferences.Editor editor = prefs().edit();
            for (int i = 0; i < count; i++) {
                long dialogId = ((Number) keyAt.invoke(dialogs, i)).longValue();
                editor.putBoolean("handled_" + account + "_" + dialogId, true);
            }
            editor.apply();
        } catch (Throwable error) {
            Log.w("Telega", "Could not snapshot existing dialogs before enabling automation", error);
        }
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
                if (mute) NotificationsController.getInstance(account).muteDialog(dialogId, Integer.MAX_VALUE, true);
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
            Class<?> requestClass;
            try {
                requestClass = Class.forName("org.telegram.tgnet.TLRPC$TL_folders_editPeerFolders");
            } catch (ClassNotFoundException missingFoldersNamespace) {
                requestClass = Class.forName("org.telegram.tgnet.TLRPC$TL_messages_editPeerFolders");
            }
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
        boolean listContent = false;
        String[] lines = clean.split("\\r?\\n");
        int listMarkers = 0;
        for (String line : lines) {
            String item = line.trim();
            if (item.matches("^(?:[•●▪◦☐☑-]\\s+|[0-9]{1,3}[.)]\\s+).+")) {
                listMarkers++;
            }
        }
        listContent = listMarkers >= 2 || clean.contains("☐") || clean.contains("☑");
        String prefix = listContent ? "Список: " : "Статья: ";
        return prefix + clean + hiddenTag(listContent ? LIST_TAG : ARTICLE_TAG);
    }

    /** Removes Telega article/list metadata while preserving the ordinary fallback text. */
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
        String marker = decoded.toString();
        if (!ARTICLE_TAG.equals(marker) && !LIST_TAG.equals(marker)) return null;
        return text.substring(0, start);
    }
}
