#!/usr/bin/env python3
"""Telega feature toggles, privacy controls, local sticker/article transport and profile fixes."""
from pathlib import Path
import re
import sys

ROOT = Path("TMessagesProj/src/main/java/org/telegram")
settings_path = ROOT / "ui" / "SettingsActivity.java"
controller_path = ROOT / "messenger" / "MessagesController.java"
connections_path = Path("TMessagesProj/src/main/java/org/telegram/tgnet/ConnectionsManager.java")
peer_color_path = ROOT / "ui" / "PeerColorActivity.java"
profile_path = ROOT / "ui" / "ProfileActivity.java"
send_helper_path = ROOT / "messenger" / "SendMessagesHelper.java"
rich_editor_path = ROOT / "ui" / "iv" / "RichEditor.java"
rich_layout_path = ROOT / "ui" / "iv" / "ChatAttachAlertRichLayout.java"
message_object_path = ROOT / "messenger" / "MessageObject.java"
deleted_cell_path = ROOT / "ui" / "Cells" / "ChatMessageCell.java"
status_path = ROOT / "messenger" / "TelegaLocalStatus.java"

for required in [settings_path, controller_path, connections_path, peer_color_path, profile_path, send_helper_path, rich_editor_path, rich_layout_path, message_object_path, deleted_cell_path, status_path]:
    if not required.exists():
        print(f"ERROR: required source file missing: {required}", file=sys.stderr)
        sys.exit(1)

features_java = r'''package org.telegram.messenger;

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
'''
(ROOT / "messenger" / "TelegaFeatures.java").write_text(features_java, encoding="utf-8")

settings_java = r'''package org.telegram.ui;

import android.content.Context;
import android.graphics.Color;
import android.graphics.drawable.GradientDrawable;
import android.view.Gravity;
import android.view.View;
import android.widget.CompoundButton;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.Switch;
import android.widget.TextView;

import org.telegram.messenger.AndroidUtilities;
import org.telegram.messenger.R;
import org.telegram.messenger.TelegaFeatures;
import org.telegram.ui.ActionBar.ActionBar;
import org.telegram.ui.ActionBar.BaseFragment;
import org.telegram.ui.ActionBar.Theme;

/** Telega-specific behavior toggles. */
public class TelegaSettingsActivity extends BaseFragment {

    @Override
    public View createView(Context context) {
        actionBar.setBackButtonImage(R.drawable.ic_ab_back);
        actionBar.setAllowOverlayTitle(true);
        actionBar.setTitle("Настройки Telega");
        actionBar.setActionBarMenuOnItemClick(new ActionBar.ActionBarMenuOnItemClick() {
            @Override
            public void onItemClick(int id) {
                if (id == -1) finishFragment();
            }
        });

        ScrollView scroll = new ScrollView(context);
        scroll.setFillViewport(true);
        scroll.setBackgroundColor(Theme.getColor(Theme.key_windowBackgroundGray));
        LinearLayout list = new LinearLayout(context);
        list.setOrientation(LinearLayout.VERTICAL);
        list.setPadding(0, AndroidUtilities.dp(8), 0, AndroidUtilities.dp(20));
        scroll.addView(list, new ScrollView.LayoutParams(-1, -2));

        addToggle(context, list, "Удалённые сообщения",
                "Оставлять у себя сообщения, которые собеседник удалил для всех.",
                TelegaFeatures.isDeletedMessagesEnabled(currentAccount),
                (button, enabled) -> TelegaFeatures.setDeletedMessagesEnabled(enabled));
        addToggle(context, list, "Призрак",
                "Не отправлять отметки о прочтении и не обновлять онлайн-статус. Серверные ограничения всё равно действуют.",
                TelegaFeatures.isGhostModeEnabled(),
                (button, enabled) -> TelegaFeatures.setGhostModeEnabled(enabled));
        addToggle(context, list, "Auto Archive",
                "Автоматически архивировать новые группы, каналы и ботов и отключать им звук.",
                TelegaFeatures.isAutoArchiveEnabled(),
                (button, enabled) -> TelegaFeatures.setAutoArchiveEnabled(enabled));
        addToggle(context, list, "Анти звук",
                "Автоматически отключать уведомления у новых групп, каналов и ботов.",
                TelegaFeatures.isAntiSoundEnabled(),
                (button, enabled) -> TelegaFeatures.setAntiSoundEnabled(enabled));

        fragmentView = scroll;
        return fragmentView;
    }

    private void addToggle(Context context, LinearLayout parent, String title, String summary,
                           boolean checked, CompoundButton.OnCheckedChangeListener listener) {
        LinearLayout row = new LinearLayout(context);
        row.setOrientation(LinearLayout.HORIZONTAL);
        row.setGravity(Gravity.CENTER_VERTICAL);
        row.setPadding(AndroidUtilities.dp(16), AndroidUtilities.dp(13), AndroidUtilities.dp(16), AndroidUtilities.dp(13));
        GradientDrawable rowBackground = new GradientDrawable();
        rowBackground.setColor(Theme.getColor(Theme.key_windowBackgroundWhite));
        rowBackground.setCornerRadius(AndroidUtilities.dp(12));
        row.setBackground(rowBackground);
        LinearLayout textColumn = new LinearLayout(context);
        textColumn.setOrientation(LinearLayout.VERTICAL);
        TextView titleView = new TextView(context);
        titleView.setText(title);
        titleView.setTextSize(16);
        titleView.setTextColor(Theme.getColor(Theme.key_windowBackgroundWhiteBlackText));
        TextView summaryView = new TextView(context);
        summaryView.setText(summary);
        summaryView.setTextSize(13);
        summaryView.setLineSpacing(AndroidUtilities.dp(2), 1.0f);
        summaryView.setTextColor(Theme.getColor(Theme.key_windowBackgroundWhiteGrayText2));
        LinearLayout.LayoutParams titleParams = new LinearLayout.LayoutParams(-1, -2);
        textColumn.addView(titleView, titleParams);
        LinearLayout.LayoutParams summaryParams = new LinearLayout.LayoutParams(-1, -2);
        summaryParams.topMargin = AndroidUtilities.dp(4);
        textColumn.addView(summaryView, summaryParams);
        row.addView(textColumn, new LinearLayout.LayoutParams(0, -2, 1f));
        Switch toggle = new Switch(context);
        toggle.setChecked(checked);
        toggle.setOnCheckedChangeListener(listener);
        LinearLayout.LayoutParams toggleParams = new LinearLayout.LayoutParams(-2, -2);
        toggleParams.leftMargin = AndroidUtilities.dp(12);
        row.addView(toggle, toggleParams);
        row.setOnClickListener(v -> toggle.setChecked(!toggle.isChecked()));
        LinearLayout.LayoutParams rowParams = new LinearLayout.LayoutParams(-1, -2);
        rowParams.setMargins(AndroidUtilities.dp(12), 0, AndroidUtilities.dp(12), AndroidUtilities.dp(8));
        parent.addView(row, rowParams);
    }
}
'''
(ROOT / "ui" / "TelegaSettingsActivity.java").write_text(settings_java, encoding="utf-8")

# Add the Telega settings row under the standard settings list.
s = settings_path.read_text(encoding="utf-8")
row_anchor = '        items.add(SettingCell.Factory.of(10, IconBackgroundColors.PURPLE.top, IconBackgroundColors.PURPLE.bottom, R.drawable.settings_language, getString(R.string.SettingsLanguage), LocaleController.getCurrentLanguageName()));'
row = row_anchor + '\n        items.add(SettingCell.Factory.of(26, IconBackgroundColors.CYAN.top, IconBackgroundColors.CYAN.bottom, R.drawable.settings_power, "Настройки Telega", "Дополнительные функции Telega Beta"));'
if 'SettingCell.Factory.of(26, IconBackgroundColors.CYAN.top' not in s:
    if row_anchor not in s:
        print("ERROR: SettingsActivity language row anchor not found", file=sys.stderr)
        sys.exit(1)
    s = s.replace(row_anchor, row, 1)
handler_anchor = '            case 10:\n                presentSettingFragment(new LanguageSelectActivity());\n                break;'
handler = handler_anchor + '\n            case 26:\n                presentSettingFragment(new TelegaSettingsActivity());\n                break;'
if 'case 26:\n                presentSettingFragment(new TelegaSettingsActivity());' not in s:
    if handler_anchor not in s:
        print("ERROR: SettingsActivity item handler anchor not found", file=sys.stderr)
        sys.exit(1)
    s = s.replace(handler_anchor, handler, 1)
settings_path.write_text(s, encoding="utf-8")

# Hook newly discovered bots and joined groups/channels for auto-mute/archive.
c = controller_path.read_text(encoding="utf-8")
user_pattern = r"(?m)^\s*(?:public|protected|private)\s+(?:(?:final|synchronized)\s+)*void\s+putUser\s*\(\s*(?:final\s+)?TLRPC\.User\s+(\w+)[^)]*\)\s*\{"
chat_pattern = r"(?m)^\s*(?:public|protected|private)\s+(?:(?:final|synchronized)\s+)*void\s+putChat\s*\(\s*(?:final\s+)?TLRPC\.Chat\s+(\w+)[^)]*\)\s*\{"
user_match = re.search(user_pattern, c)
if user_match and "TelegaFeatures.onPeerAvailable(currentAccount, " not in c:
    user = user_match.group(1)
    c = c[:user_match.end()] + f'\n        if ({user} != null && {user}.bot && {user}.id != UserConfig.getInstance(currentAccount).getClientUserId()) TelegaFeatures.onPeerAvailable(currentAccount, {user}.id, true);' + c[user_match.end():]
else:
    print("WARNING: MessagesController.putUser hook unavailable; user auto-mute will rely on chat hook.")
chat_match = re.search(chat_pattern, c)
if chat_match and "TelegaFeatures.onPeerAvailable(currentAccount, -" not in c:
    chat = chat_match.group(1)
    c = c[:chat_match.end()] + f'\n        if ({chat} != null && ({chat}.megagroup || {chat}.broadcast) && !ChatObject.isNotInChat({chat})) TelegaFeatures.onPeerAvailable(currentAccount, -{chat}.id, true);' + c[chat_match.end():]
else:
    print("WARNING: MessagesController.putChat hook unavailable; archive/mute may not trigger for new chats.")
controller_path.write_text(c, encoding="utf-8")

# Suppress selected privacy-sensitive API requests while Ghost is enabled.
cn = connections_path.read_text(encoding="utf-8")
anchor = '    private void sendRequestInternal(TLObject object, RequestDelegate onComplete, RequestDelegateTimestamp onCompleteTimestamp, QuickAckDelegate onQuickAck, WriteToSocketDelegate onWriteToSocket, int flags, int datacenterId, int connectionType, boolean immediate, int requestToken) {\n'
injected = anchor + '        if (org.telegram.messenger.TelegaFeatures.shouldSuppressRequest(currentAccount, object)) {\n            if (BuildVars.LOGS_ENABLED) FileLog.d("Telega Ghost suppressed " + object.getClass().getSimpleName());\n            return;\n        }\n'
if 'TelegaFeatures.shouldSuppressRequest(currentAccount, object)' not in cn:
    if anchor not in cn:
        print("ERROR: ConnectionsManager.sendRequestInternal anchor not found", file=sys.stderr)
        sys.exit(1)
    cn = cn.replace(anchor, injected, 1)
connections_path.write_text(cn, encoding="utf-8")

# Premium-sticker fallback transport: send an ordinary fallback emoji with Telega's invisible custom-emoji payload.
sh = send_helper_path.read_text(encoding="utf-8")
if "TELEGA_PREMIUM_STICKER_FALLBACK" not in sh:
    pat = r"(public void sendSticker\s*\(\s*TLRPC\.Document\s+document,.*?\)\s*\{)"
    m = re.search(pat, sh, flags=re.S)
    if not m:
        print("ERROR: SendMessagesHelper.sendSticker anchor not found", file=sys.stderr)
        sys.exit(1)
    fallback = r'''
        // TELEGA_PREMIUM_STICKER_FALLBACK: non-Premium accounts send fallback text plus invisible sticker metadata.
        TLRPC.User telegaActualUser = UserConfig.getInstance(currentAccount).getCurrentUser();
        if (document != null && MessageObject.isPremiumSticker(document) && (telegaActualUser == null || !telegaActualUser.premium)) {
            String telegaFallback = MessageObject.findAnimatedEmojiEmoticon(document, null, currentAccount);
            if (telegaFallback == null || telegaFallback.length() == 0) telegaFallback = "✨";
            String telegaTransport = telegaFallback + TelegaCustomEmoji.encode(document.id, telegaFallback.length());
            sendMessage(SendMessageParams.of(telegaTransport, peer));
            return;
        }
'''
    sh = sh[:m.end()] + fallback + sh[m.end():]
send_helper_path.write_text(sh, encoding="utf-8")

# Rich editor fallback: transport article body in a plain message so server Premium gates cannot drop it.
for path in [rich_editor_path, rich_layout_path]:
    src = path.read_text(encoding="utf-8")
    old = "enterView.sendConvertedRichAsSimple(listView.toSimpleMessage(), notify, scheduleDate, scheduleRepeatPeriod);"
    new = "enterView.sendConvertedRichAsSimple(org.telegram.messenger.TelegaFeatures.encodeArticle(listView.toSimpleMessage().toString()), notify, scheduleDate, scheduleRepeatPeriod);"
    if old in src:
        src = src.replace(old, new, 1)
    elif "TelegaFeatures.encodeArticle(listView.toSimpleMessage())" not in src:
        print(f"ERROR: rich article fallback anchor not found in {path}", file=sys.stderr)
        sys.exit(1)
    path.write_text(src, encoding="utf-8")

# Decode article transport and apply distinct article styling in Telega clients.
mo = message_object_path.read_text(encoding="utf-8")
if "TelegaFeatures.decodeArticle(messageText.toString())" not in mo:
    anchor = "\n        isEmbedVideo"
    article_code = r'''
        if (messageOwner != null && messageText != null && messageText.length() > 0) {
            String telegaArticleText = TelegaFeatures.decodeArticle(messageText.toString());
            if (telegaArticleText != null) {
                messageText = telegaArticleText;
                messageOwner.message = telegaArticleText;
                if (messageOwner.entities == null) messageOwner.entities = new ArrayList<>();
                if (telegaArticleText.length() >= 7) {
                    TLRPC.TL_messageEntityBold telegaArticleTitle = new TLRPC.TL_messageEntityBold();
                    telegaArticleTitle.offset = 0;
                    telegaArticleTitle.length = 7;
                    messageOwner.entities.add(telegaArticleTitle);
                }
                if (telegaArticleText.length() > 8) {
                    TLRPC.TL_messageEntityBlockquote telegaArticleBody = new TLRPC.TL_messageEntityBlockquote();
                    telegaArticleBody.offset = 8;
                    telegaArticleBody.length = telegaArticleText.length() - 8;
                    telegaArticleBody.collapsed = false;
                    messageOwner.entities.add(telegaArticleBody);
                }
            }
        }
'''
    if anchor not in mo:
        print("ERROR: MessageObject article decode anchor not found", file=sys.stderr)
        sys.exit(1)
    mo = mo.replace(anchor, "\n" + article_code + anchor, 1)
message_object_path.write_text(mo, encoding="utf-8")

# The alpha layer in dispatchDraw alone misses the bubble painted by onDraw.
# Apply alpha to the entire recycled message cell and draw a small vector trash icon instead of an emoji.
dc = deleted_cell_path.read_text(encoding="utf-8")
if "telegaDeletedForDraw" in dc:
    dc = dc.replace(
        "        if (telegaDeletedForDraw) {\n            int telegaLayer = canvas.saveLayerAlpha(0, 0, getWidth(), getHeight(), 148);\n            super.dispatchDraw(canvas);\n            canvas.restoreToCount(telegaLayer);\n        } else {\n            super.dispatchDraw(canvas);\n        }",
        "        setAlpha(telegaDeletedForDraw ? 0.64f : 1.0f);\n        super.dispatchDraw(canvas);",
        1
    )
    trash_old = '            android.graphics.Paint telegaDeletedPaint = new android.graphics.Paint(android.graphics.Paint.ANTI_ALIAS_FLAG);\n            telegaDeletedPaint.setTextSize(org.telegram.messenger.AndroidUtilities.dp(14));\n            telegaDeletedPaint.setColor(0xFF858585);\n            canvas.drawText("🗑", org.telegram.messenger.AndroidUtilities.dp(12), getHeight() - org.telegram.messenger.AndroidUtilities.dp(10), telegaDeletedPaint);'
    trash_new = '''            android.graphics.Paint telegaDeletedPaint = new android.graphics.Paint(android.graphics.Paint.ANTI_ALIAS_FLAG);
            telegaDeletedPaint.setColor(0xFFFF1744);
            telegaDeletedPaint.setStyle(android.graphics.Paint.Style.STROKE);
            telegaDeletedPaint.setStrokeWidth(org.telegram.messenger.AndroidUtilities.dp(1.35f));
            telegaDeletedPaint.setStrokeCap(android.graphics.Paint.Cap.ROUND);
            android.graphics.Rect telegaBubbleBounds = currentBackgroundDrawable == null ? null : currentBackgroundDrawable.getBounds();
            float telegaBubbleRight = telegaBubbleBounds != null && !telegaBubbleBounds.isEmpty()
                    ? telegaBubbleBounds.right
                    : backgroundDrawableLeft + Math.max(backgroundDrawableRight, backgroundWidth);
            float telegaBubbleBottom = telegaBubbleBounds != null && !telegaBubbleBounds.isEmpty()
                    ? telegaBubbleBounds.bottom : getHeight();
            float telegaTrashX = telegaBubbleRight - org.telegram.messenger.AndroidUtilities.dp(17);
            float telegaTrashY = telegaBubbleBottom - org.telegram.messenger.AndroidUtilities.dp(13);
            float telegaTrashW = org.telegram.messenger.AndroidUtilities.dp(8);
            float telegaTrashH = org.telegram.messenger.AndroidUtilities.dp(9);
            canvas.drawRoundRect(telegaTrashX, telegaTrashY + org.telegram.messenger.AndroidUtilities.dp(3), telegaTrashX + telegaTrashW, telegaTrashY + telegaTrashH, org.telegram.messenger.AndroidUtilities.dp(1), org.telegram.messenger.AndroidUtilities.dp(1), telegaDeletedPaint);
            canvas.drawLine(telegaTrashX - org.telegram.messenger.AndroidUtilities.dp(1), telegaTrashY + org.telegram.messenger.AndroidUtilities.dp(2), telegaTrashX + telegaTrashW + org.telegram.messenger.AndroidUtilities.dp(1), telegaTrashY + org.telegram.messenger.AndroidUtilities.dp(2), telegaDeletedPaint);
            canvas.drawLine(telegaTrashX + org.telegram.messenger.AndroidUtilities.dp(2), telegaTrashY, telegaTrashX + org.telegram.messenger.AndroidUtilities.dp(6), telegaTrashY, telegaDeletedPaint);'''
    if trash_old in dc:
        dc = dc.replace(trash_old, trash_new, 1)
    elif 'canvas.drawText("🗑"' in dc:
        print("ERROR: deleted-message emoji marker source changed", file=sys.stderr)
        sys.exit(1)
    deleted_cell_path.write_text(dc, encoding="utf-8")

# Extend hidden profile metadata to keep name color/name emoji when profile color is changed, and vice versa.
st = status_path.read_text(encoding="utf-8")
if "getNameColor(String about)" not in st:
    old_sig = "private static String encodePayload(String clean, long documentId, int until, int color, long backgroundEmojiId) {"
    if old_sig not in st:
        print("ERROR: TelegaLocalStatus encodePayload signature changed", file=sys.stderr)
        sys.exit(1)
    st = st.replace(old_sig, "private static String encodePayload(String clean, long documentId, int until, int color, long backgroundEmojiId, int nameColor, long nameEmojiId) {", 1)
    old_guard = "if (documentId == 0 && color < 0 && backgroundEmojiId == 0) return clean;"
    st = st.replace(old_guard, "if (documentId == 0 && color < 0 && backgroundEmojiId == 0 && nameColor < 0 && nameEmojiId == 0) return clean;", 1)
    old_payload = 'String payload = PREFIX + Long.toString(Math.max(0, documentId), 36) + "." + Integer.toString(Math.max(0, until), 36) + "." + Integer.toString(color + 1, 36) + "." + Long.toString(Math.max(0, backgroundEmojiId), 36);'
    new_payload = 'String payload = PREFIX + Long.toString(Math.max(0, documentId), 36) + "." + Integer.toString(Math.max(0, until), 36) + "." + Integer.toString(color + 1, 36) + "." + Long.toString(Math.max(0, backgroundEmojiId), 36) + "." + Integer.toString(nameColor + 1, 36) + "." + Long.toString(Math.max(0, nameEmojiId), 36);'
    if old_payload not in st:
        print("ERROR: TelegaLocalStatus payload layout anchor not found", file=sys.stderr)
        sys.exit(1)
    st = st.replace(old_payload, new_payload, 1)
    # Profile changes preserve name style unless a separate name edit is applied.
    st = st.replace("return encodePayload(clean, documentId, until, color, backgroundEmojiId);",
                    "return encodePayload(clean, documentId, until, color, backgroundEmojiId, getNameColor(source), getNameEmoji(source));", 1)
    st = st.replace("return encodePayload(strip(source), documentId, until, color, backgroundEmojiId);",
                    "return encodePayload(strip(source), documentId, until, color, backgroundEmojiId, getNameColor(source), getNameEmoji(source));", 1)
    insert_anchor = "    private static String[] getParts(String about) {"
    methods = r'''    public static int getNameColor(String about) {
        String[] parts = getParts(about);
        if (parts == null || parts.length < 7) return -1;
        try { return Integer.parseInt(parts[5], 36) - 1; } catch (Throwable ignore) { return -1; }
    }

    public static long getNameEmoji(String about) {
        String[] parts = getParts(about);
        if (parts == null || parts.length < 7) return 0;
        try { return Long.parseLong(parts[6], 36); } catch (Throwable ignore) { return 0; }
    }

    public static String updateAllStyles(String about, int profileColor, long profileEmoji, int nameColor, long nameEmoji) {
        String source = about == null ? "" : about;
        return encodePayload(strip(source), getDocumentId(source), getUntil(source), profileColor, profileEmoji, nameColor, nameEmoji);
    }

'''
    if insert_anchor not in st:
        print("ERROR: TelegaLocalStatus parts method anchor not found", file=sys.stderr)
        sys.exit(1)
    st = st.replace(insert_anchor, methods + insert_anchor, 1)
    status_path.write_text(st, encoding="utf-8")

# Merge style fields independently instead of overwriting profile settings when name color changes.
pc = peer_color_path.read_text(encoding="utf-8")
helper_start = pc.find("    private void saveTelegaProfileStyle(")
if helper_start >= 0 and "TelegaLocalStatus.updateAllStyles" not in pc[helper_start:helper_start + 5000]:
    about_line = '        String about = full.about == null ? "" : full.about;\n        String newAbout = TelegaLocalStatus.updateProfileStyle(about, color, backgroundEmojiId);'
    about_new = '''        String about = full.about == null ? "" : full.about;
        int sharedProfileColor = applyingProfile ? color : TelegaLocalStatus.getProfileColor(about);
        long sharedProfileEmoji = applyingProfile ? backgroundEmojiId : TelegaLocalStatus.getProfileEmoji(about);
        int sharedNameColor = applyingName ? (namePage == null ? UserObject.getColorId(me) : namePage.selectedColor) : TelegaLocalStatus.getNameColor(about);
        long sharedNameEmoji = applyingName ? (namePage == null ? UserObject.getEmojiId(me) : namePage.selectedEmoji) : TelegaLocalStatus.getNameEmoji(about);
        if (applyingName && namePage != null && namePage.selectedPeerCollectible != null) {
            sharedNameColor = telegaClosestPeerColorId(namePage.selectedPeerCollectible.accent_color, PAGE_NAME);
            sharedNameEmoji = namePage.selectedPeerCollectible.background_emoji_id;
        }
        String newAbout = TelegaLocalStatus.updateAllStyles(about, sharedProfileColor, sharedProfileEmoji, sharedNameColor, sharedNameEmoji);'''
    if about_line in pc:
        pc = pc.replace(about_line, about_new, 1)
    else:
        sync_line = '        String newAbout = TelegaLocalStatus.updateProfileStyle(about, syncColor, syncBackgroundEmoji);'
        sync_new = """        android.content.SharedPreferences saved = ApplicationLoader.applicationContext.getSharedPreferences("telega_profile_style_" + full.id, Context.MODE_PRIVATE);
        int sharedProfileColor = syncColor;
        long sharedProfileEmoji = syncBackgroundEmoji;
        int sharedNameColor = TelegaLocalStatus.getNameColor(about);
        long sharedNameEmoji = TelegaLocalStatus.getNameEmoji(about);
        if (saved.contains("nameColor")) {
            sharedNameColor = saved.getInt("nameColor", sharedNameColor);
            sharedNameEmoji = saved.getLong("nameEmoji", sharedNameEmoji);
        }
        String newAbout = TelegaLocalStatus.updateAllStyles(about, sharedProfileColor, sharedProfileEmoji, sharedNameColor, sharedNameEmoji);"""
        if sync_line in pc:
            pc = pc.replace(sync_line, sync_new, 1)
        elif "TelegaLocalStatus.updateAllStyles(about," not in pc:
            print("ERROR: profile-style metadata merge anchor not found", file=sys.stderr)
            sys.exit(1)

# NFT resale preview: choose the closest ordinary supported color and emoji, never invoke the buy flow.
if "telegaClosestPeerColorId" not in pc:
    insert_anchor = "    private void showBulletin() {"
    method = r'''    private int telegaClosestPeerColorId(int accentColor, int pageType) {
        MessagesController mc = getMessagesController();
        MessagesController.PeerColors palette = pageType == PAGE_NAME ? mc.peerColors : mc.profilePeerColors;
        if (palette == null || palette.colors == null || palette.colors.isEmpty()) return 0;
        int targetR = Color.red(accentColor), targetG = Color.green(accentColor), targetB = Color.blue(accentColor);
        long bestDistance = Long.MAX_VALUE;
        int bestId = palette.colors.get(0).id;
        for (int i = 0; i < palette.colors.size(); i++) {
            MessagesController.PeerColor candidate = palette.colors.get(i);
            int candidateColor = candidate.getColor1();
            long dr = Color.red(candidateColor) - targetR;
            long dg = Color.green(candidateColor) - targetG;
            long db = Color.blue(candidateColor) - targetB;
            long distance = dr * dr + dg * dg + db * db;
            if (distance < bestDistance) {
                bestDistance = distance;
                bestId = candidate.id;
            }
        }
        return bestId;
    }

'''
    if insert_anchor not in pc:
        print("ERROR: PeerColorActivity NFT helper insertion point not found", file=sys.stderr)
        sys.exit(1)
    pc = pc.replace(insert_anchor, method + insert_anchor, 1)
# Telega profile-color NFT selection must preserve the collectible ID.
# Load the current profile-color collectible so it stays selected after reopening the picker.
profile_setup_old = """                    selectedEmojiCollectible = user != null && user.emoji_status instanceof TLRPC.TL_emojiStatusCollectible ? (TLRPC.TL_emojiStatusCollectible) user.emoji_status : null;
                    selectedPeerCollectible = null;"""
profile_setup_new = """                    selectedEmojiCollectible = user != null && user.emoji_status instanceof TLRPC.TL_emojiStatusCollectible ? (TLRPC.TL_emojiStatusCollectible) user.emoji_status : null;
                    selectedPeerCollectible = user != null && user.profile_color instanceof TLRPC.TL_peerColorCollectible ? (TLRPC.TL_peerColorCollectible) user.profile_color : null;"""
if profile_setup_old in pc:
    pc = pc.replace(profile_setup_old, profile_setup_new, 1)
elif "user.profile_color instanceof TLRPC.TL_peerColorCollectible ? (TLRPC.TL_peerColorCollectible) user.profile_color" not in pc:
    print("ERROR: profile NFT restore-on-open anchor missing", file=sys.stderr)
    sys.exit(1)

owned_nft_old = """                        if (type == PAGE_NAME) {
                            if (!(gift.peer_color instanceof TLRPC.TL_peerColorCollectible)) return;
                            selectedEmoji = 0;
                            selectedColor = -1;
                            selectedResaleGift = null;
                            selectedEmojiCollectible = null;
                            selectedPeerCollectible = (TLRPC.TL_peerColorCollectible) gift.peer_color;
                        } else {
                            selectedEmoji = 0;
                            selectedColor = -1;
                            selectedResaleGift = null;
                            selectedEmojiCollectible = MessagesController.emojiStatusCollectibleFromGift(gift);
                            selectedPeerCollectible = null;
                        }"""
owned_nft_new = """                        // TELEGA_PROFILE_COLOR_NFT_SELECTION_V2
                        if (type == PAGE_NAME) {
                            if (!(gift.peer_color instanceof TLRPC.TL_peerColorCollectible)) return;
                            selectedEmoji = 0;
                            selectedColor = -1;
                            selectedResaleGift = null;
                            selectedEmojiCollectible = null;
                            selectedPeerCollectible = (TLRPC.TL_peerColorCollectible) gift.peer_color;
                        } else if (gift.peer_color instanceof TLRPC.TL_peerColorCollectible) {
                            selectedEmoji = 0;
                            selectedColor = -1;
                            selectedResaleGift = null;
                            selectedPeerCollectible = (TLRPC.TL_peerColorCollectible) gift.peer_color;
                        } else {
                            selectedEmoji = 0;
                            selectedColor = -1;
                            selectedResaleGift = null;
                            selectedEmojiCollectible = MessagesController.emojiStatusCollectibleFromGift(gift);
                            selectedPeerCollectible = null;
                        }"""
if owned_nft_old in pc:
    pc = pc.replace(owned_nft_old, owned_nft_new, 1)
elif "TELEGA_PROFILE_COLOR_NFT_SELECTION_V2" not in pc:
    print("ERROR: owned NFT selection anchor missing in PeerColorActivity", file=sys.stderr)
    sys.exit(1)

resale_nft_old = """                        if (type == PAGE_NAME) {
                            if (!(gift.peer_color instanceof TLRPC.TL_peerColorCollectible)) return;
                            selectedEmoji = 0;
                            selectedColor = -1;
                            selectedEmojiCollectible = null;
                            selectedPeerCollectible = (TLRPC.TL_peerColorCollectible) gift.peer_color;
                        } else {
                            selectedEmoji = 0;
                            selectedColor = -1;
                            selectedEmojiCollectible = MessagesController.emojiStatusCollectibleFromGift(gift);
                            selectedPeerCollectible = null;
                        }
                        selectedResaleGift = gift;"""
resale_nft_new = """                        // TELEGA_PROFILE_COLOR_NFT_RESALE_V2
                        if (type == PAGE_NAME) {
                            if (!(gift.peer_color instanceof TLRPC.TL_peerColorCollectible)) return;
                            selectedEmoji = 0;
                            selectedColor = -1;
                            selectedEmojiCollectible = null;
                            selectedPeerCollectible = (TLRPC.TL_peerColorCollectible) gift.peer_color;
                        } else if (gift.peer_color instanceof TLRPC.TL_peerColorCollectible) {
                            selectedEmoji = 0;
                            selectedColor = -1;
                            selectedPeerCollectible = (TLRPC.TL_peerColorCollectible) gift.peer_color;
                        } else {
                            selectedEmoji = 0;
                            selectedColor = -1;
                            selectedEmojiCollectible = MessagesController.emojiStatusCollectibleFromGift(gift);
                            selectedPeerCollectible = null;
                        }
                        selectedResaleGift = gift;"""
if resale_nft_old in pc:
    pc = pc.replace(resale_nft_old, resale_nft_new, 1)
elif "TELEGA_PROFILE_COLOR_NFT_RESALE_V2" not in pc:
    print("ERROR: resale NFT selection anchor missing in PeerColorActivity", file=sys.stderr)
    sys.exit(1)

# The profile page has independent color and emoji-status collectible fields.
profile_unsaved_old = """                    return !(selectedColor == (me.emoji_status instanceof TLRPC.TL_emojiStatusCollectible ? -1 : UserObject.getProfileColorId(me)) && selectedEmoji == (me.emoji_status instanceof TLRPC.TL_emojiStatusCollectible ? 0 : UserObject.getOnlyProfileEmojiId(me)) && eq(me.emoji_status instanceof TLRPC.TL_emojiStatusCollectible ? (TLRPC.TL_emojiStatusCollectible) me.emoji_status : null , selectedEmojiCollectible));"""
profile_unsaved_alt = """                    final boolean a = selectedColor == (me.emoji_status instanceof TLRPC.TL_emojiStatusCollectible ? -1 : UserObject.getProfileColorId(me));
                    final boolean b = selectedEmoji == (me.emoji_status instanceof TLRPC.TL_emojiStatusCollectible ? 0 : UserObject.getOnlyProfileEmojiId(me));
                    final boolean c = eq(me.emoji_status instanceof TLRPC.TL_emojiStatusCollectible ? (TLRPC.TL_emojiStatusCollectible) me.emoji_status : null , selectedEmojiCollectible);
                    return !(a && b && c);"""
profile_unsaved_new = """                    final boolean a = selectedColor == (me.profile_color instanceof TLRPC.TL_peerColorCollectible ? -1 : UserObject.getProfileColorId(me));
                    final boolean b = selectedEmoji == (me.profile_color instanceof TLRPC.TL_peerColorCollectible ? 0 : UserObject.getOnlyProfileEmojiId(me));
                    final boolean c = eq(me.profile_color instanceof TLRPC.TL_peerColorCollectible ? (TLRPC.TL_peerColorCollectible) me.profile_color : null, selectedPeerCollectible);
                    final boolean d = eq(me.emoji_status instanceof TLRPC.TL_emojiStatusCollectible ? (TLRPC.TL_emojiStatusCollectible) me.emoji_status : null, selectedEmojiCollectible);
                    return !(a && b && c && d);"""
if profile_unsaved_old in pc:
    pc = pc.replace(profile_unsaved_old, profile_unsaved_new, 1)
elif profile_unsaved_alt in pc:
    pc = pc.replace(profile_unsaved_alt, profile_unsaved_new, 1)
elif "final boolean c = eq(me.profile_color instanceof TLRPC.TL_peerColorCollectible" not in pc:
    print("ERROR: profile NFT unsaved-state anchor missing", file=sys.stderr)
    sys.exit(1)

# Include profile color collectible IDs in the submit condition; status emoji is submitted separately.
compare_old = """profilePage.selectedColor != UserObject.getProfileColorId(me) ||
                            profilePage.selectedEmoji != UserObject.getOnlyProfileEmojiId(me) ||
                            (profilePage.selectedEmojiCollectible == null ? 0 : profilePage.selectedEmojiCollectible.collectible_id) != UserObject.getProfileCollectibleId(me)"""
compare_new = """profilePage.selectedColor != (me.profile_color instanceof TLRPC.TL_peerColorCollectible ? -1 : UserObject.getProfileColorId(me)) ||
                            profilePage.selectedEmoji != (me.profile_color instanceof TLRPC.TL_peerColorCollectible ? 0 : UserObject.getOnlyProfileEmojiId(me)) ||
                            (profilePage.selectedPeerCollectible == null ? 0 : profilePage.selectedPeerCollectible.collectible_id) != (me.profile_color instanceof TLRPC.TL_peerColorCollectible ? me.profile_color.collectible_id : 0)"""
if compare_new not in pc:
    if compare_old not in pc:
        print("ERROR: profile color comparison anchor missing", file=sys.stderr)
        sys.exit(1)
    pc = pc.replace(compare_old, compare_new, 1)

# The profile-color API accepts an InputPeerColorCollectible. Preserve the original ordinary-color path otherwise.
if "TELEGA_PROFILE_COLOR_APPLY_V2" not in pc:
    profile_apply_start = pc.find("                if (profilePage.selectedColor < 0) {", pc.find("req.for_profile = true;"))
    profile_apply_end = pc.find("                getConnectionsManager().sendRequest(req, null);", profile_apply_start)
    if profile_apply_start < 0 or profile_apply_end < 0:
        print("ERROR: profile color application block anchor missing", file=sys.stderr)
        sys.exit(1)
    original_body = pc[profile_apply_start:profile_apply_end]
    indented_original = "\n".join("    " + line for line in original_body.split("\n"))
    apply_body = """                // TELEGA_PROFILE_COLOR_APPLY_V2
                if (profilePage.selectedPeerCollectible != null) {
                    req.flags |= 4;
                    TLRPC.TL_inputPeerColorCollectible telegaInputProfileColor = new TLRPC.TL_inputPeerColorCollectible();
                    telegaInputProfileColor.collectible_id = profilePage.selectedPeerCollectible.collectible_id;
                    req.color = telegaInputProfileColor;
                    me.profile_color = profilePage.selectedPeerCollectible;
                } else {
                    if (me.profile_color instanceof TLRPC.TL_peerColorCollectible) {
                        me.profile_color = new TLRPC.TL_peerColor();
                    }
""" + indented_original + """
                }
"""
    pc = pc[:profile_apply_start] + apply_body + pc[profile_apply_end:]

# Render the profile color collectible separately from any emoji-status collectible.
preview_old = """                if (selectedEmojiCollectible != null) {
                    profilePreview.setStatusEmoji(selectedEmojiCollectible.document_id, true, animated);
                    profilePreview.setColor(MessagesController.PeerColor.fromCollectible(selectedEmojiCollectible), animated);
                    profilePreview.setEmoji(selectedEmojiCollectible.pattern_document_id, true, animated);
                } else {"""
preview_new = """                if (selectedEmojiCollectible != null) {
                    profilePreview.setStatusEmoji(selectedEmojiCollectible.document_id, true, animated);
                    if (type == PAGE_PROFILE && selectedPeerCollectible != null) {
                        profilePreview.setColor(MessagesController.PeerColor.fromPeerCollectible(selectedPeerCollectible), animated);
                        profilePreview.setEmoji(selectedPeerCollectible.background_emoji_id, false, animated);
                    } else {
                        profilePreview.setColor(MessagesController.PeerColor.fromCollectible(selectedEmojiCollectible), animated);
                        profilePreview.setEmoji(selectedEmojiCollectible.pattern_document_id, true, animated);
                    }
                } else {"""
if preview_old in pc:
    pc = pc.replace(preview_old, preview_new, 1)
elif "profilePreview.setColor(MessagesController.PeerColor.fromPeerCollectible(selectedPeerCollectible), animated);" not in pc:
    print("ERROR: preview NFT color branch anchor missing", file=sys.stderr)
    sys.exit(1)

preview_normal_old = """                    profilePreview.setColor(selectedColor, animated);
                    profilePreview.setEmoji(selectedEmoji, false, animated);"""
preview_normal_new = """                    if (type == PAGE_PROFILE && selectedPeerCollectible != null) {
                        profilePreview.setColor(MessagesController.PeerColor.fromPeerCollectible(selectedPeerCollectible), animated);
                        profilePreview.setEmoji(selectedPeerCollectible.background_emoji_id, false, animated);
                    } else {
                        profilePreview.setColor(selectedColor, animated);
                        profilePreview.setEmoji(selectedEmoji, false, animated);
                    }"""
if preview_normal_old in pc:
    pc = pc.replace(preview_normal_old, preview_normal_new, 1)
elif "profilePreview.setColor(selectedColor, animated);" in pc:
    print("ERROR: ordinary profile preview branch was not updated", file=sys.stderr)
    sys.exit(1)

color_bar_old = """            if (type == PAGE_PROFILE && colorBar != null) {
                if (selectedEmojiCollectible != null) {
                    colorBar.setColor(MessagesController.PeerColor.fromCollectible(selectedEmojiCollectible), animated);
                } else {
                    colorBar.setColor(currentAccount, selectedColor, animated);
                }
            }"""
color_bar_new = """            if (type == PAGE_PROFILE && colorBar != null) {
                if (selectedPeerCollectible != null) {
                    colorBar.setColor(MessagesController.PeerColor.fromPeerCollectible(selectedPeerCollectible), animated);
                } else if (selectedEmojiCollectible != null) {
                    colorBar.setColor(MessagesController.PeerColor.fromCollectible(selectedEmojiCollectible), animated);
                } else {
                    colorBar.setColor(currentAccount, selectedColor, animated);
                }
            }"""
if color_bar_old in pc:
    pc = pc.replace(color_bar_old, color_bar_new, 1)
elif "colorBar.setColor(MessagesController.PeerColor.fromPeerCollectible(selectedPeerCollectible), animated);" not in pc:
    print("ERROR: profile NFT color bar anchor missing", file=sys.stderr)
    sys.exit(1)

peer_color_path.write_text(pc, encoding="utf-8")

# Render real NFT peer-color palettes instead of returning an empty preview color.
mc = controller_path.read_text(encoding="utf-8")
peer_collectible_anchor = """            // TODO
            return peerColor;
        }

        public static PeerColor fromCollectible(TLRPC.EmojiStatus status) {"""
peer_collectible_replacement = """            int telegaFallbackColor = color.accent_color | 0xFF000000;
            int telegaColorCount = color.colors == null ? 0 : color.colors.size();
            for (int i = 0; i < peerColor.colors.length; i++) {
                int raw = telegaColorCount > 0
                        ? color.colors.get(Math.min(i, telegaColorCount - 1))
                        : color.accent_color;
                peerColor.colors[i] = raw | 0xFF000000;
            }
            int telegaDarkCount = color.dark_colors == null ? 0 : color.dark_colors.size();
            int telegaDarkAccent = color.dark_accent_color != 0
                    ? color.dark_accent_color | 0xFF000000 : telegaFallbackColor;
            for (int i = 0; i < peerColor.darkColors.length; i++) {
                int raw = telegaDarkCount > 0
                        ? color.dark_colors.get(Math.min(i, telegaDarkCount - 1))
                        : (color.dark_accent_color != 0 ? telegaDarkAccent : peerColor.colors[i]);
                peerColor.darkColors[i] = raw | 0xFF000000;
            }
            peerColor.patternColor = telegaFallbackColor;
            peerColor.textColor = telegaFallbackColor;
            return peerColor;
        }

        public static PeerColor fromCollectible(TLRPC.EmojiStatus status) {"""
if peer_collectible_anchor in mc:
    mc = mc.replace(peer_collectible_anchor, peer_collectible_replacement, 1)
elif "int telegaFallbackColor = color.accent_color | 0xFF000000;" not in mc:
    print("ERROR: PeerColor.fromPeerCollectible implementation anchor missing", file=sys.stderr)
    sys.exit(1)
controller_path.write_text(mc, encoding="utf-8")


# The native profile and name fields remain independent; render hidden name metadata on other Telega clients.
pr = profile_path.read_text(encoding="utf-8")
name_hook = "int telegaNameColor = userInfo == null ? -1 : TelegaLocalStatus.getNameColor(userInfo.about);"
if name_hook not in pr:
    profile_style_hook = "int telegaProfileColor = TelegaLocalStatus.getProfileColor(userInfo.about);"
    if profile_style_hook not in pr:
        profile_style_hook = "int telegaProfileColor = userInfo == null ? -1 : TelegaLocalStatus.getProfileColor(userInfo.about);"
    ix = pr.find(profile_style_hook)
    if ix < 0:
        print("ERROR: shared profile color renderer anchor missing", file=sys.stderr)
        sys.exit(1)
    block_end = pr.find("            }", ix)
    # Use the outer viewed-user style block's beginning marker; insert immediately before the enclosing block ends is brittle,
    # so inject independent name metadata after the complete existing shared-style block, before the next layout guard.
    guard = "        if (avatarContainer == null || nameTextView == null || getParentActivity() == null) {"
    after_guard = pr.find(guard)
    if after_guard >= 0:
        close = pr.find("        }", after_guard + len(guard))
        if close >= 0:
            # Already a guard, don't alter it; add the name metadata application right after this guard block.
            end_guard = pr.find("\n        }", after_guard)
            if end_guard >= 0:
                end_guard += len("\n        }")
                name_code = r'''
 
        if (userInfo != null && userId != 0) {
            TLRPC.User telegaNameUser = getMessagesController().getUser(userId);
            int telegaNameColor = TelegaLocalStatus.getNameColor(userInfo.about);
            long telegaNameEmoji = TelegaLocalStatus.getNameEmoji(userInfo.about);
            boolean telegaHasLocalNameStyle = false;
            if (telegaNameUser != null && userId == UserConfig.getInstance(currentAccount).getClientUserId()) {
                android.content.SharedPreferences telegaNamePrefs = ApplicationLoader.applicationContext.getSharedPreferences("telega_profile_style_" + userId, 0);
                telegaHasLocalNameStyle = telegaNamePrefs.contains("nameColor");
                if (telegaHasLocalNameStyle) {
                    telegaNameColor = telegaNamePrefs.getInt("nameColor", -1);
                    telegaNameEmoji = telegaNamePrefs.getLong("nameEmoji", 0);
                }
            }
            if (telegaNameUser != null && (telegaNameColor >= 0 || telegaNameEmoji > 0 || telegaHasLocalNameStyle)
                    && !(telegaNameUser.color instanceof TLRPC.TL_peerColorCollectible)) {
                if (telegaNameUser.color == null || !(telegaNameUser.color instanceof TLRPC.TL_peerColor)) {
                    telegaNameUser.color = new TLRPC.TL_peerColor();
                }
                TLRPC.TL_peerColor telegaPeerNameColor = (TLRPC.TL_peerColor) telegaNameUser.color;
                if (telegaNameColor >= 0) {
                    telegaPeerNameColor.flags |= 1;
                    telegaPeerNameColor.color = telegaNameColor;
                } else if (telegaHasLocalNameStyle) {
                    telegaPeerNameColor.flags &= ~1;
                    telegaPeerNameColor.color = 0;
                }
                if (telegaNameEmoji > 0) {
                    telegaPeerNameColor.flags |= 2;
                    telegaPeerNameColor.background_emoji_id = telegaNameEmoji;
                } else if (telegaHasLocalNameStyle) {
                    telegaPeerNameColor.flags &= ~2;
                    telegaPeerNameColor.background_emoji_id = 0;
                }
            }
        }
'''
                # Insert at the end of the existing updateProfileData guard block so names and profile remain separate.
                pr = pr[:end_guard] + name_code + pr[end_guard:]
    else:
        print("ERROR: profile update guard anchor missing for name-style renderer", file=sys.stderr)
        sys.exit(1)
profile_path.write_text(pr, encoding="utf-8")
peer_color_path.write_text(pc, encoding="utf-8")

print("Telega settings, Ghost mode, Auto Archive/Anti sound, article/sticker transports, profile style and deleted-message rendering patches applied.")
