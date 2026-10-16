#!/usr/bin/env python3
"""Install the independent TelegaSync Firebase client and move profile style sync off Telegram bio."""
from pathlib import Path
import sys

root = Path(".")
template_dir = root / ".github" / "firebase"
source_root = root / "TMessagesProj" / "src" / "main"
java_root = source_root / "java" / "org" / "telegram" / "messenger"
ui_root = source_root / "java" / "org" / "telegram" / "ui"

for required in (
    template_dir / "TelegaSyncFirebase.java",
    template_dir / "TelegaProfileSync.java",
    template_dir / "telega-sync-google-services.json",
):
    if not required.is_file():
        print(f"ERROR: required TelegaSync Firebase source is missing: {required}", file=sys.stderr)
        sys.exit(1)

java_root.mkdir(parents=True, exist_ok=True)
(java_root / "TelegaSyncFirebase.java").write_text(
    (template_dir / "TelegaSyncFirebase.java").read_text(encoding="utf-8"), encoding="utf-8"
)
(java_root / "TelegaProfileSync.java").write_text(
    (template_dir / "TelegaProfileSync.java").read_text(encoding="utf-8"), encoding="utf-8"
)
assets = source_root / "assets"
assets.mkdir(parents=True, exist_ok=True)
(assets / "telega-sync-google-services.json").write_text(
    (template_dir / "telega-sync-google-services.json").read_text(encoding="utf-8"), encoding="utf-8"
)

# Keep the legacy Google Services configuration untouched; Firestore and Auth use the named app.
gradle_path = root / "TMessagesProj" / "build.gradle"
gradle = gradle_path.read_text(encoding="utf-8")
if "com.google.firebase:firebase-firestore" not in gradle:
    anchor = "dependencies {"
    index = gradle.find(anchor)
    if index < 0:
        print("ERROR: TMessagesProj/build.gradle dependencies block not found", file=sys.stderr)
        sys.exit(1)
    insert_at = index + len(anchor)
    firebase_deps = """
    implementation platform('com.google.firebase:firebase-bom:35.0.1')
    implementation 'com.google.firebase:firebase-auth'
    implementation 'com.google.firebase:firebase-firestore'
"""
    gradle = gradle[:insert_at] + firebase_deps + gradle[insert_at:]
    gradle_path.write_text(gradle, encoding="utf-8")

# Initialize the secondary Firebase app at startup. The default Firebase app remains unchanged.
loader_path = java_root / "ApplicationLoader.java"
loader = loader_path.read_text(encoding="utf-8")
if "TelegaSyncFirebase.initialize(this);" not in loader:
    on_create = loader.find("    public void onCreate() {")
    super_call = loader.find("        super.onCreate();", on_create)
    if on_create < 0 or super_call < 0:
        print("ERROR: ApplicationLoader.onCreate initialization anchor not found", file=sys.stderr)
        sys.exit(1)
    super_end = super_call + len("        super.onCreate();")
    loader = loader[:super_end] + "\n        TelegaSyncFirebase.initialize(this);" + loader[super_end:]
    loader_path.write_text(loader, encoding="utf-8")

# The existing style patch stores a bio transport helper for other features; profile style itself
# must not read or write that metadata. Replace only the profile-style persistence method.
color_path = ui_root / "PeerColorActivity.java"
color = color_path.read_text(encoding="utf-8")
method_start = color.find("    private void syncTelegaProfileStyleMetadata(")
method_end = color.find("    private int telegaClosestPeerColorId(", method_start)
if method_start < 0 or method_end < 0:
    print("ERROR: profile-style metadata method anchors not found in PeerColorActivity.java", file=sys.stderr)
    sys.exit(1)
replacement = """    private void syncTelegaProfileStyleMetadata(TLRPC.UserFull full, int color, long backgroundEmojiId) {
        if (full == null || !applyingProfile) {
            getNotificationCenter().postNotificationName(NotificationCenter.updateInterfaces, MessagesController.UPDATE_MASK_ALL);
            return;
        }
        TelegaProfileSync.saveProfileStyle(
                ApplicationLoader.applicationContext, full.id, color, backgroundEmojiId,
                style -> getNotificationCenter().postNotificationName(
                        NotificationCenter.updateInterfaces, MessagesController.UPDATE_MASK_ALL)
        );
    }

"""
color = color[:method_start] + replacement + color[method_end:]
color_path.write_text(color, encoding="utf-8")

# Remove both bio-reading wrappers inserted by the older patch, using balanced braces so nested
# blocks are removed safely and no unrelated ProfileActivity code is touched.
profile_path = ui_root / "ProfileActivity.java"
profile = profile_path.read_text(encoding="utf-8")

def matching_brace(text, opening):
    depth = 0
    for index in range(opening, len(text)):
        if text[index] == "{":
            depth += 1
        elif text[index] == "}":
            depth -= 1
            if depth == 0:
                return index
    return -1

for needle in (
    "TelegaLocalStatus.getProfileColor(userInfo.about)",
    "TelegaLocalStatus.getProfileColor(about)",
    "TelegaLocalStatus.getProfileEmoji(userInfo.about)",
):
    while needle in profile:
        occurrence = profile.find(needle)
        start = profile.rfind("if (userInfo != null) {", 0, occurrence)
        if start < 0:
            print(f"ERROR: could not locate bio metadata wrapper for {needle}", file=sys.stderr)
            sys.exit(1)
        opening = profile.find("{", start)
        closing = matching_brace(profile, opening)
        if closing < 0 or closing < occurrence:
            print(f"ERROR: malformed bio metadata wrapper for {needle}", file=sys.stderr)
            sys.exit(1)
        profile = profile[:start] + profile[closing + 1:]

guard = """if (avatarContainer == null || nameTextView == null || getParentActivity() == null) {
            return;
        }"""
cloud_loader = """if (userId != 0) {
            TelegaProfileSync.loadProfileStyle(ApplicationLoader.applicationContext, userId, telegaCloudStyle -> {
                if (telegaCloudStyle == null || getParentActivity() == null) {
                    return;
                }
                TLRPC.User telegaCloudUser = getMessagesController().getUser(userId);
                if (telegaCloudUser == null) {
                    return;
                }
                int oldFlags = telegaCloudUser.profile_color == null ? 0 : telegaCloudUser.profile_color.flags;
                int oldColor = telegaCloudUser.profile_color == null ? 0 : telegaCloudUser.profile_color.color;
                long oldEmoji = telegaCloudUser.profile_color == null ? 0L : telegaCloudUser.profile_color.background_emoji_id;
                int newFlags = oldFlags & ~3;
                if (telegaCloudStyle.profileColor >= 0) {
                    newFlags |= 1;
                }
                if (telegaCloudStyle.backgroundEmojiId > 0) {
                    newFlags |= 2;
                }
                int newColor = telegaCloudStyle.profileColor >= 0 ? telegaCloudStyle.profileColor : 0;
                long newEmoji = Math.max(0L, telegaCloudStyle.backgroundEmojiId);
                if (oldFlags != newFlags || oldColor != newColor || oldEmoji != newEmoji) {
                    if (telegaCloudUser.profile_color == null) {
                        telegaCloudUser.profile_color = new TLRPC.TL_peerColor();
                    }
                    telegaCloudUser.profile_color.flags = newFlags;
                    telegaCloudUser.profile_color.color = newColor;
                    telegaCloudUser.profile_color.background_emoji_id = newEmoji;
                    getMessagesController().putUser(telegaCloudUser, false);
                    getNotificationCenter().postNotificationName(
                            NotificationCenter.updateInterfaces, MessagesController.UPDATE_MASK_ALL);
                }
            });
        }"""
if "TelegaProfileSync.loadProfileStyle(ApplicationLoader.applicationContext, userId" not in profile:
    if guard not in profile:
        print("ERROR: ProfileActivity profile redraw guard not found", file=sys.stderr)
        sys.exit(1)
    profile = profile.replace(guard, guard + "\n\n        " + cloud_loader, 1)
profile_path.write_text(profile, encoding="utf-8")

print("Secondary TelegaSync Firebase installed; profile accent/background emoji sync no longer uses profile-bio metadata.")
