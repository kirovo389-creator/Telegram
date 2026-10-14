#!/usr/bin/env python3
"""Follow-up Telega fixes: automatic reaction read, saved-proxy rotation, text article fallback, and changelog."""
from pathlib import Path
import sys

ROOT = Path("TMessagesProj/src/main/java/org/telegram")
features = ROOT / "messenger" / "TelegaFeatures.java"
settings = ROOT / "ui" / "TelegaSettingsActivity.java"
dialog_cell = ROOT / "ui" / "Cells" / "DialogCell.java"
action_cell = ROOT / "ui" / "Cells" / "ChatActionCell.java"
launch = ROOT / "ui" / "LaunchActivity.java"
rich_editor = ROOT / "ui" / "iv" / "RichEditor.java"
rich_layout = ROOT / "ui" / "iv" / "ChatAttachAlertRichLayout.java"

for p in [features, settings, dialog_cell, action_cell, launch, rich_editor, rich_layout]:
    if not p.exists():
        print(f"ERROR: source file missing: {p}", file=sys.stderr)
        sys.exit(1)

# 1) The Auto Proxy option rotates only among proxies the user has already saved.
f = features.read_text(encoding="utf-8")
anchor = "    public static boolean isBadgeEnabled() {"
methods = r'''    public static boolean isAutoProxyEnabled() {
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

'''
if "public static boolean isAutoProxyEnabled()" not in f:
    if anchor not in f:
        print("ERROR: TelegaFeatures badge method anchor missing", file=sys.stderr)
        sys.exit(1)
    f = f.replace(anchor, methods + anchor, 1)
# Ghost mode must not block the read-reactions request that clears the badge.
f = f.replace('                || name.contains("readreactions")\n', '')
features.write_text(f, encoding="utf-8")

# 2) Modernize the Telega settings screen and add Auto Proxy toggle.
s = settings.read_text(encoding="utf-8")
if "import android.widget.Toast;" not in s:
    s = s.replace("import android.widget.TextView;", "import android.widget.TextView;\nimport android.widget.Toast;", 1)
if "TELEGA_BETA_SETTINGS_HEADER" not in s:
    header_anchor = "        list.setPadding(0, AndroidUtilities.dp(8), 0, AndroidUtilities.dp(20));"
    header = header_anchor + r'''
        // TELEGA_BETA_SETTINGS_HEADER
        TextView pageTitle = new TextView(context);
        pageTitle.setText("TELEGA BETA");
        pageTitle.setTextSize(23);
        pageTitle.setTypeface(android.graphics.Typeface.DEFAULT, android.graphics.Typeface.BOLD);
        pageTitle.setTextColor(Theme.getColor(Theme.key_windowBackgroundWhiteBlackText));
        pageTitle.setPadding(AndroidUtilities.dp(20), AndroidUtilities.dp(14), AndroidUtilities.dp(20), 0);
        list.addView(pageTitle, new LinearLayout.LayoutParams(-1, -2));
        TextView pageSubtitle = new TextView(context);
        pageSubtitle.setText("Приватность, автоматизация и дополнительные возможности");
        pageSubtitle.setTextSize(13);
        pageSubtitle.setTextColor(Theme.getColor(Theme.key_windowBackgroundWhiteGrayText2));
        pageSubtitle.setPadding(AndroidUtilities.dp(20), AndroidUtilities.dp(4), AndroidUtilities.dp(20), AndroidUtilities.dp(14));
        list.addView(pageSubtitle, new LinearLayout.LayoutParams(-1, -2));
'''
    if header_anchor not in s:
        print("ERROR: settings header insertion anchor missing", file=sys.stderr)
        sys.exit(1)
    s = s.replace(header_anchor, header, 1)
proxy_anchor = '        addToggle(context, list, "Auto Archive",'
proxy_row = r'''        addToggle(context, list, "Auto Proxy",
                "Автоматически переключается между сохранёнными прокси при проблемах с соединением. Нужно минимум два прокси, добавленных тобой.",
                TelegaFeatures.isAutoProxyEnabled(),
                (button, enabled) -> {
                    if (!TelegaFeatures.setAutoProxyEnabled(enabled)) {
                        button.setChecked(false);
                        Toast.makeText(context, "Добавь минимум два прокси в настройках прокси Telegram", Toast.LENGTH_LONG).show();
                    }
                });

'''
if 'addToggle(context, list, "Auto Proxy"' not in s:
    if proxy_anchor not in s:
        print("ERROR: Auto Proxy settings anchor missing", file=sys.stderr)
        sys.exit(1)
    s = s.replace(proxy_anchor, proxy_row + proxy_anchor, 1)
settings.write_text(s, encoding="utf-8")

# 3) Hide the unread-reaction counter and read those reactions through Telegram's API.
d = dialog_cell.read_text(encoding="utf-8")
hide_anchor = "            if (dialogsType == DialogsActivity.DIALOGS_TYPE_ADD_USERS_TO) {"
if "// Telega: reaction counters are auto-read and hidden." not in d:
    if hide_anchor not in d:
        print("ERROR: DialogCell reaction badge insertion anchor missing", file=sys.stderr)
        sys.exit(1)
    d = d.replace(hide_anchor, "            // Telega: reaction counters are auto-read and hidden.\n            reactionMentionCount = 0;\n" + hide_anchor, 1)
dialog_cell.write_text(d, encoding="utf-8")

a = action_cell.read_text(encoding="utf-8")
check_anchor = """        if (y > clipTop && y + reactionsLayoutInBubble.height - AndroidUtilities.dp(16) < clipBottom) {
            return true;
        }"""
check_replacement = """        if (y > clipTop && y + reactionsLayoutInBubble.height - AndroidUtilities.dp(16) < clipBottom) {
            markReactionsAsRead();
            return false;
        }"""
if "markReactionsAsRead();\n            return false;" not in a:
    if check_anchor in a:
        a = a.replace(check_anchor, check_replacement, 1)
    else:
        print("WARNING: ChatActionCell auto-read visibility anchor not found; global unread sweep remains enabled.", file=sys.stderr)
action_cell.write_text(a, encoding="utf-8")

# 4) Publish simple text articles/lists through the normal message pipeline even if
# the account has local Premium UI enabled. Rich-only blocks still use the rich path.
re = rich_editor.read_text(encoding="utf-8")
simple_anchor = """        if (!listView.isWithinLimits()) { updateSendButtonEnabled(); return; }
        if (!MessagesController.getInstance(currentAccount).richEditorAllowed()) {"""
simple_fallback = r'''        if (listView.isSimpleConvertible()) {
            final ChatActivityEnterView telegaFallbackEnterView = chatActivity.getChatActivityEnterView();
            if (telegaFallbackEnterView != null) {
                sent = true;
                if (onSentCallback != null) onSentCallback.run();
                telegaFallbackEnterView.sendConvertedRichAsSimple(
                        org.telegram.messenger.TelegaFeatures.encodeArticle(listView.toSimpleMessage().toString()),
                        notify, scheduleDate, scheduleRepeatPeriod);
                finishFragment();
                return;
            }
        }
'''
if "telegaFallbackEnterView" not in re:
    if simple_anchor not in re:
        print("ERROR: RichEditor simple article fallback anchor missing", file=sys.stderr)
        sys.exit(1)
    re = re.replace(simple_anchor, "        if (!listView.isWithinLimits()) { updateSendButtonEnabled(); return; }\n" + simple_fallback + "        if (!MessagesController.getInstance(currentAccount).richEditorAllowed()) {", 1)
rich_editor.write_text(re, encoding="utf-8")

rl = rich_layout.read_text(encoding="utf-8")
layout_anchor = """        if (!MessagesController.getInstance(currentAccount).richEditorAllowed()) {
            // non-premium user with non-lossy content: send it as a simple message via the composer"""
layout_fallback = r'''        if (listView.isSimpleConvertible() && parentAlert.baseFragment instanceof ChatActivity) {
            final ChatActivityEnterView telegaFallbackEnterView = ((ChatActivity) parentAlert.baseFragment).getChatActivityEnterView();
            if (telegaFallbackEnterView != null) {
                telegaFallbackEnterView.sendConvertedRichAsSimple(
                        org.telegram.messenger.TelegaFeatures.encodeArticle(listView.toSimpleMessage().toString()),
                        notify, scheduleDate, scheduleRepeatPeriod);
                parentAlert.dismiss(true);
                return true;
            }
        }
'''
if "telegaFallbackEnterView" not in rl:
    if layout_anchor not in rl:
        print("ERROR: rich layout article fallback anchor missing", file=sys.stderr)
        sys.exit(1)
    rl = rl.replace(layout_anchor, layout_fallback + layout_anchor, 1)
rich_layout.write_text(rl, encoding="utf-8")

# 5) Changelog popup once after each installed build version. This is intentionally
# separate from OTA's pre-install update prompt.
l = launch.read_text(encoding="utf-8")
if "showTelegaChangelogIfNeeded()" not in l:
    resume_anchor = "    @Override\n    protected void onResume() {"
    if resume_anchor not in l:
        print("ERROR: LaunchActivity onResume anchor for changelog missing", file=sys.stderr)
        sys.exit(1)
    method = r'''
    private void showTelegaChangelogIfNeeded() {
        if (isFinishing() || isDestroyed() || passcodeDialog != null
                || org.telegram.messenger.UserConfig.getInstance(currentAccount).getClientUserId() == 0) return;
        final android.content.SharedPreferences prefs = ApplicationLoader.applicationContext.getSharedPreferences("telega_changelog", 0);
        long version;
        try {
            android.content.pm.PackageInfo info = getPackageManager().getPackageInfo(getPackageName(), 0);
            version = android.os.Build.VERSION.SDK_INT >= 28 ? info.getLongVersionCode() : info.versionCode;
        } catch (Throwable error) {
            version = org.telegram.messenger.BuildVars.BUILD_VERSION_STRING.hashCode();
        }
        if (prefs.getLong("last_version", Long.MIN_VALUE) == version) return;
        prefs.edit().putLong("last_version", version).apply();
        new AlertDialog.Builder(this)
                .setTitle("Что нового в Telega Beta")
                .setMessage("• Обновлён раздел «Настройки Telega».\n\n"
                        + "• Auto Proxy переключает только между прокси, которые ты сам сохранил.\n\n"
                        + "• Счётчик непрочитанных реакций скрывается, а приложение отправляет запрос на их прочтение.\n\n"
                        + "• Обычные статьи и списки отправляются через совместимый текстовый режим.\n\n"
                        + "• Исправления стабильности и интерфейса.")
                .setNeutralButton("Канал TelegaForks", (dialog, which) -> {
                    try {
                        startActivity(new android.content.Intent(android.content.Intent.ACTION_VIEW,
                                android.net.Uri.parse("https://t.me/TelegaForks")));
                    } catch (Throwable error) {
                        android.util.Log.w("Telega", "Unable to open channel link", error);
                    }
                })
                .setPositiveButton("Понятно", null)
                .show();
    }

'''
    l = l.replace(resume_anchor, method + resume_anchor, 1)
    call_anchor = "        updateCurrentConnectionState(currentAccount);"
    if call_anchor not in l:
        print("ERROR: LaunchActivity connection-state resume anchor missing", file=sys.stderr)
        sys.exit(1)
    l = l.replace(call_anchor, call_anchor + "\n        getWindow().getDecorView().postDelayed(this::showTelegaChangelogIfNeeded, 1200);\n        getWindow().getDecorView().postDelayed(() -> org.telegram.messenger.TelegaFeatures.markAllUnreadReactionsAsRead(currentAccount), 1800);", 1)
launch.write_text(l, encoding="utf-8")

print("Telega advanced fixes applied: Auto Proxy, automatic reaction read, simple article fallback, settings refresh, changelog.")
