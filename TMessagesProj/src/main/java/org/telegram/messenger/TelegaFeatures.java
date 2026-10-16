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

    public static boolean isAutoProxyEnabled() {
        return SharedConfig.proxyRotationEnabled;
    }

    public static boolean setAutoProxyEnabled(boolean enabled) {
        SharedConfig.loadProxyList();
        if (enabled && SharedConfig.proxyList.size() < 2) return false;
        if (enabled && !SharedConfig.isProxyEnabled()) {
            SharedConfig.ProxyInfo selected = SharedConfig.currentProxy;
            if (selected == null || !SharedConfig.proxyList.contains(selected)) {
                selected = SharedConfig.proxyList.isEmpty() ? null : SharedConfig.proxyList.get(0);
            }
            if (selected == null) return false;
            SharedConfig.currentProxy = selected;
            SharedPreferences.Editor editor = MessagesController.getGlobalMainSettings().edit();
            selected.settings.toSharedPreferences(editor);
            editor.putBoolean("proxy_enabled", true);
            editor.apply();
            ConnectionsManager.setProxySettings(true, selected.settings);
        }
        SharedConfig.proxyRotationEnabled = enabled;
        SharedConfig.saveConfig();
        NotificationCenter.getGlobalInstance().postNotificationName(NotificationCenter.proxySettingsChanged);
        return true;
    }

    /**
     * Clear reaction counters for dialogs with unread reactions. The server-side
     * messages.readReactions call is used, rather than only hiding the local badge.
     */
    public static void markAllUnreadReactionsAsRead(int account) {
        final long now = System.currentTimeMillis();
        final String lastKey = "auto_read_reactions_" + account;
        if (now - prefs().getLong(lastKey, 0) < 60_000L) return;
        try {
            Object controller = MessagesController.getInstance(account);
            Field dialogsField = controller.getClass().getDeclaredField("dialogs_dict");
            dialogsField.setAccessible(true);
            Object dialogs = dialogsField.get(controller);
            Method sizeMethod = dialogs.getClass().getMethod("size");
            Method valueAtMethod = dialogs.getClass().getMethod("valueAt", int.class);
            Method getInputPeer = controller.getClass().getMethod("getInputPeer", long.class);
            Field unreadField = TLRPC.Dialog.class.getField("unread_reactions_count");
            Field idField = TLRPC.Dialog.class.getField("id");
            Class<?> requestClass = Class.forName("org.telegram.tgnet.TLRPC$TL_messages_readReactions");
            Field peerField = requestClass.getField("peer");
            int size = ((Number) sizeMethod.invoke(dialogs)).intValue();
            for (int i = 0; i < size; i++) {
                Object value = valueAtMethod.invoke(dialogs, i);
                if (!(value instanceof TLRPC.Dialog)) continue;
                TLRPC.Dialog dialog = (TLRPC.Dialog) value;
                if (unreadField.getInt(dialog) <= 0) continue;
                long dialogId = idField.getLong(dialog);
                Object peer = getInputPeer.invoke(controller, dialogId);
                if (peer == null) continue;
                Object request = requestClass.getDeclaredConstructor().newInstance();
                peerField.set(request, peer);
                ConnectionsManager.getInstance(account).sendRequest((TLObject) request, (response, error) -> {});
            }
            prefs().edit().putLong(lastKey, now).apply();
        } catch (Throwable error) {
            Log.w("Telega", "Could not automatically mark unread reactions as read", error);
        }
    }

    public static boolean isTurboDownloadEnabled() {
        return prefs().getBoolean("turbo_downloads", false);
    }
    public static void setTurboDownloadEnabled(boolean enabled) {
        prefs().edit().putBoolean("turbo_downloads", enabled).apply();
    }
    public static boolean isMessageEffectsEnabled() {
        return prefs().getBoolean("message_effects", true);
    }
    public static void setMessageEffectsEnabled(boolean enabled) {
        prefs().edit().putBoolean("message_effects", enabled).apply();
    }

    public static boolean isBadgeEnabled() {
        return prefs().getBoolean("telega_badge", false);
    }
    public static void setBadgeEnabled(boolean enabled) {
        prefs().edit().putBoolean("telega_badge", enabled).apply();
        TelegaBadgeSync.update(UserConfig.selectedAccount, enabled);
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
