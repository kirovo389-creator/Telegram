from pathlib import Path

ROOT = Path("TMessagesProj/src/main/java")

def replace_once(path, old, new):
    source = path.read_text(encoding="utf-8")
    if new in source:
        return
    if old not in source:
        raise SystemExit(f"Glass Chats patch anchor not found in {path}: {old[:90]!r}")
    path.write_text(source.replace(old, new, 1), encoding="utf-8")

features = ROOT / "org/telegram/messenger/TelegaFeatures.java"
replace_once(
    features,
    "    public static boolean isBadgeEnabled() {",
    """    /** Optional translucent cards in the dialog list. Disabled by default. */
    public static boolean isGlassChatsEnabled() {
        return prefs().getBoolean("glass_chats", false);
    }
    public static void setGlassChatsEnabled(boolean enabled) {
        prefs().edit().putBoolean("glass_chats", enabled).apply();
        AndroidUtilities.runOnUIThread(() -> {
            try {
                NotificationCenter.getGlobalInstance().postNotificationName(
                        NotificationCenter.updateInterfaces, MessagesController.UPDATE_MASK_ALL);
            } catch (Throwable ignored) {}
        });
    }

    public static boolean isBadgeEnabled() {"""
)

settings = ROOT / "org/telegram/ui/TelegaSettingsActivity.java"
replace_once(
    settings,
    '        addToggle(context, list, "Значок Telega",',
    """        addToggle(context, list, "Стеклянные чаты",
                "Добавляет полупрозрачные карточки в списке диалогов. Можно выключить в любой момент; остальные функции и оформление не меняются.",
                TelegaFeatures.isGlassChatsEnabled(),
                (button, enabled) -> TelegaFeatures.setGlassChatsEnabled(enabled));

        addToggle(context, list, "Значок Telega","""
)

dialog = ROOT / "org/telegram/ui/Cells/DialogCell.java"
class_line = "public class DialogCell extends BaseCell implements StoriesListPlaceProvider.AvatarOverlaysView, Theme.Colorable {"
replace_once(
    dialog,
    class_line,
    class_line + "\n    private static final Paint glassChatPaint = new Paint(Paint.ANTI_ALIAS_FLAG);"
)
replace_once(
    dialog,
    "        float cornersRadius = dp(8) * cornerProgress;\n",
    """        float cornersRadius = dp(8) * cornerProgress;
        // TELEGA_GLASS_CHATS: opt-in translucent cards; dialog behavior remains unchanged.
        if (org.telegram.messenger.TelegaFeatures.isGlassChatsEnabled()
                && !isSelected && translationX == 0 && rightFragmentOpenedProgress == 0) {
            rect.set(dp(7), dp(3), getMeasuredWidth() - dp(7), getMeasuredHeight() - dp(3));
            int surfaceColor = Theme.getColor(Theme.key_windowBackgroundWhite, resourcesProvider);
            int glassAlpha = Theme.isCurrentThemeDark() ? 92 : 118;
            glassChatPaint.setColor(ColorUtils.setAlphaComponent(surfaceColor, glassAlpha));
            glassChatPaint.setStyle(Paint.Style.FILL);
            canvas.drawRoundRect(rect, dp(15), dp(15), glassChatPaint);
            glassChatPaint.setColor(ColorUtils.setAlphaComponent(
                    Theme.getColor(Theme.key_windowBackgroundWhite, resourcesProvider),
                    Theme.isCurrentThemeDark() ? 105 : 150));
            glassChatPaint.setStyle(Paint.Style.STROKE);
            glassChatPaint.setStrokeWidth(dp(0.7f));
            canvas.drawRoundRect(rect, dp(15), dp(15), glassChatPaint);
            glassChatPaint.setStyle(Paint.Style.FILL);
        }
"""
)
print("Glass Chats patch applied.")
