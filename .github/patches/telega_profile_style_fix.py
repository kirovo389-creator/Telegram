#!/usr/bin/env python3
"""Repair the profile-style patch against current upstream source."""
from pathlib import Path
import sys

root = Path("TMessagesProj/src/main/java/org/telegram")
profile = root / "ui" / "ProfileActivity.java"
color_activity = root / "ui" / "PeerColorActivity.java"

p = profile.read_text(encoding="utf-8")
# The earlier patch accidentally inserted the literal characters \n before this block.
bad_start = r"\n            if (userInfo != null) {"
if bad_start in p:
    start = p.index(bad_start)
    end = p.find("if (avatarContainer == null", start)
    if end < 0:
        print("ERROR: malformed profile-style block end not found", file=sys.stderr)
        sys.exit(1)
    p = p[:start] + "\n        " + p[end:]


# Apply style only where the local variable user exists.
anchor = """if (userId != 0) {
            TLRPC.User user = getMessagesController().getUser(userId);
            if (user == null) {
                return;
            }"""
style = """if (userInfo != null) {
                int telegaProfileColor = TelegaLocalStatus.getProfileColor(userInfo.about);
                long telegaBackgroundEmoji = TelegaLocalStatus.getProfileEmoji(userInfo.about);
                if (telegaProfileColor >= 0 || telegaBackgroundEmoji != 0) {
                    if (user.profile_color == null) user.profile_color = new TLRPC.TL_peerColor();
                    if (telegaProfileColor >= 0) {
                        user.profile_color.flags |= 1;
                        user.profile_color.color = telegaProfileColor;
                    }
                    if (telegaBackgroundEmoji != 0) {
                        user.profile_color.flags |= 2;
                        user.profile_color.background_emoji_id = telegaBackgroundEmoji;
                    }
                }
            }"""
if "int telegaProfileColor = TelegaLocalStatus.getProfileColor(userInfo.about);" not in p:
    if anchor not in p:
        print("ERROR: ProfileActivity viewed-user anchor not found", file=sys.stderr)
        sys.exit(1)
    p = p.replace(anchor, anchor + "\n            " + style, 1)
profile.write_text(p, encoding="utf-8")

c = color_activity.read_text(encoding="utf-8")
c = c.replace('FileLog.e("Telega profile style save failed: " + error.text);',
              'Log.e("Telega", "Profile style save failed: " + error.text);')
c = c.replace('}), ConnectionsManager.RequestFlagFailOnServerErrors);', '}));')
color_activity.write_text(c, encoding="utf-8")
print("Telega profile-style compile fixes applied.")


# TELEGА_DETAILED_FIXES_V1
# Refresh shared profile color/background emoji whenever a Telega profile is redrawn.
# The style payload lives in the viewed user's profile bio, so apply it to the
# actual viewed user, not just this device's own profile.
status_import = "import org.telegram.messenger.TelegaLocalStatus;"
if status_import not in p:
    import_anchor = "import org.telegram.messenger.UserConfig;"
    if import_anchor not in p:
        print("ERROR: TelegaLocalStatus import anchor missing", file=sys.stderr)
        sys.exit(1)
    p = p.replace(import_anchor, import_anchor + "\\n" + status_import, 1)
guard = """if (avatarContainer == null || nameTextView == null || getParentActivity() == null) {
            return;
        }"""
shared_style = """if (userInfo != null) {
            TLRPC.User telegaViewedUser = getMessagesController().getUser(userId);
            if (telegaViewedUser != null) {
                int telegaSharedColor = TelegaLocalStatus.getProfileColor(userInfo.about);
                long telegaSharedEmoji = TelegaLocalStatus.getProfileEmoji(userInfo.about);
                if (telegaSharedColor >= 0 || telegaSharedEmoji > 0) {
                    if (telegaViewedUser.profile_color == null) {
                        telegaViewedUser.profile_color = new TLRPC.TL_peerColor();
                    }
                    if (telegaSharedColor >= 0) {
                        telegaViewedUser.profile_color.flags |= 1;
                        telegaViewedUser.profile_color.color = telegaSharedColor;
                    }
                    if (telegaSharedEmoji > 0) {
                        telegaViewedUser.profile_color.flags |= 2;
                        telegaViewedUser.profile_color.background_emoji_id = telegaSharedEmoji;
                    }
                }
            }
        }"""
if "int telegaSharedColor = TelegaLocalStatus.getProfileColor(userInfo.about);" not in p:
    if guard not in p:
        print("ERROR: updateProfileData guard anchor missing", file=sys.stderr)
        sys.exit(1)
    p = p.replace(guard, guard + "\\n\\n        " + shared_style, 1)
profile.write_text(p, encoding="utf-8")

# Remove Stars balance widgets from Telega's Stars purchase/profile UI. This
# hides the display only; it does not modify the account balance or purchases.
stars_path = Path("TMessagesProj/src/main/java/org/telegram/ui/Stars/StarsIntroActivity.java")
stars = stars_path.read_text(encoding="utf-8")
stars_original = stars
stars = stars.replace(
    "StarsBalanceView balanceView = new StarsBalanceView(context, currentAccount, resourcesProvider);",
    "StarsBalanceView balanceView = new StarsBalanceView(context, currentAccount, resourcesProvider);\\n        balanceView.setVisibility(android.view.View.GONE);"
)
stars = stars.replace(
    "        starBalanceTextView.setTextSize(dp(32));",
    "        starBalanceTextView.setTextSize(dp(32));\\n        starBalanceTextView.setVisibility(android.view.View.GONE);"
)
stars = stars.replace(
    "        starBalanceTitleView.setText(LocaleController.getString(R.string.YourStarsBalance));",
    "        starBalanceTitleView.setText(LocaleController.getString(R.string.YourStarsBalance));\\n        starBalanceTitleView.setVisibility(android.view.View.GONE);"
)
if stars == stars_original:
    print("ERROR: Stars balance anchors not found", file=sys.stderr)
    sys.exit(1)
stars_path.write_text(stars, encoding="utf-8")

# Keep premium sticker packs visible in Telega's picker. The local Premium UI
# patch makes the client-side isPremium check true; Telegram may still reject
# sending if its server-side account entitlement does not allow it.
emoji_path = Path("TMessagesProj/src/main/java/org/telegram/ui/Components/EmojiView.java")
emoji = emoji_path.read_text(encoding="utf-8")
filter_line = "packs = MessagesController.getInstance(currentAccount).filterPremiumStickers(packs);"
if filter_line in emoji:
    emoji = emoji.replace(filter_line, "// Telega: show premium sticker packs in the picker.\\n            // " + filter_line, 1)
elif "// Telega: show premium sticker packs in the picker." not in emoji:
    print("ERROR: premium sticker filter anchor not found", file=sys.stderr)
    sys.exit(1)
emoji_path.write_text(emoji, encoding="utf-8")

print("Telega detailed profile, Stars balance, and premium sticker picker fixes applied.")
