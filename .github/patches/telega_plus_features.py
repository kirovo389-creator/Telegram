#!/usr/bin/env python3
"""Telega extras: shared identity badge, local message effects, and turbo download queues."""
from pathlib import Path
import re
import sys

ROOT = Path("TMessagesProj/src/main/java/org/telegram")
status_path = ROOT / "messenger" / "TelegaLocalStatus.java"
features_path = ROOT / "messenger" / "TelegaFeatures.java"
settings_path = ROOT / "ui" / "TelegaSettingsActivity.java"
bio_path = ROOT / "ui" / "ChangeBioActivity.java"
dialog_cell_path = ROOT / "ui" / "Cells" / "DialogCell.java"
message_cell_path = ROOT / "ui" / "Cells" / "ChatMessageCell.java"
queue_path = ROOT / "messenger" / "FileLoaderPriorityQueue.java"
profile_path = ROOT / "ui" / "ProfileActivity.java"

required = [status_path, features_path, settings_path, bio_path, dialog_cell_path, message_cell_path, queue_path, profile_path]
for path in required:
    if not path.exists():
        print(f"ERROR: required source file missing: {path}", file=sys.stderr)
        sys.exit(1)

def replace_once(source, old, new, label):
    if old not in source:
        if new in source:
            return source
        print(f"ERROR: {label} anchor not found", file=sys.stderr)
        sys.exit(1)
    return source.replace(old, new, 1)

def find_matching_brace(source, open_brace):
    depth = 0
    state = "code"
    escaped = False
    i = open_brace
    while i < len(source):
        ch = source[i]
        nxt = source[i + 1] if i + 1 < len(source) else ""
        if state == "line_comment":
            if ch == "\n":
                state = "code"
        elif state == "block_comment":
            if ch == "*" and nxt == "/":
                state = "code"
                i += 1
        elif state in ("string", "char"):
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif (state == "string" and ch == '"') or (state == "char" and ch == "'"):
                state = "code"
        else:
            if ch == "/" and nxt == "/":
                state = "line_comment"
                i += 1
            elif ch == "/" and nxt == "*":
                state = "block_comment"
                i += 1
            elif ch == '"':
                state = "string"
            elif ch == "'":
                state = "char"
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    return i
        i += 1
    return -1

# 1) Add the shared badge bit to the existing compact BIO payload. It is opt-in:
# enabling the badge writes a hidden Telega-only marker to the account's BIO.
s = status_path.read_text(encoding="utf-8")
if "public static boolean hasUserBadge(String about)" not in s:
    enc_start = s.find("    private static String encodePayload(")
    color_start = s.find("    public static int getProfileColor(", enc_start)
    if enc_start < 0 or color_start < 0:
        print("ERROR: shared profile metadata encoder anchors not found", file=sys.stderr)
        sys.exit(1)
    block = r'''    private static String encodePayload(String clean, long documentId, int until, int color, long backgroundEmojiId, boolean telegaUser) {
        if (documentId == 0 && color < 0 && backgroundEmojiId == 0 && !telegaUser) return clean;
        String payload = PREFIX + Long.toString(Math.max(0, documentId), 36)
                + "." + Integer.toString(Math.max(0, until), 36)
                + "." + Integer.toString(color + 1, 36)
                + "." + Long.toString(Math.max(0, backgroundEmojiId), 36)
                + "." + (telegaUser ? "1" : "0");
        StringBuilder hidden = new StringBuilder();
        for (int i = 0; i < payload.length(); i++) hidden.appendCodePoint(TAG_BASE + payload.charAt(i));
        hidden.appendCodePoint(TAG_END);
        return clean + hidden;
    }

    public static String update(String about, long documentId, int until) {
        String source = about == null ? "" : about;
        int color = getProfileColor(source);
        long backgroundEmojiId = getProfileEmoji(source);
        boolean telegaUser = hasUserBadge(source);
        return encodePayload(strip(source), documentId, until, color, backgroundEmojiId, telegaUser);
    }

    public static String updateProfileStyle(String about, int color, long backgroundEmojiId) {
        String source = about == null ? "" : about;
        long documentId = getDocumentId(source);
        int until = getUntil(source);
        boolean telegaUser = hasUserBadge(source);
        return encodePayload(strip(source), documentId, until, color, backgroundEmojiId, telegaUser);
    }

    public static boolean hasUserBadge(String about) {
        String[] parts = getParts(about);
        return parts != null && parts.length >= 6 && "1".equals(parts[5]);
    }

    public static String updateUserBadge(String about, boolean enabled) {
        String source = about == null ? "" : about;
        return encodePayload(strip(source), getDocumentId(source), getUntil(source),
                getProfileColor(source), getProfileEmoji(source), enabled);
    }

    public static String updateBio(String visibleAbout, String previousAbout) {
        String old = previousAbout == null ? "" : previousAbout;
        String clean = strip(visibleAbout == null ? "" : visibleAbout);
        return encodePayload(clean, getDocumentId(old), getUntil(old), getProfileColor(old),
                getProfileEmoji(old), hasUserBadge(old));
    }

'''
    s = s[:enc_start] + block + s[color_start:]
    status_path.write_text(s, encoding="utf-8")

# Keep all hidden metadata (emoji status, profile style, badge) when editing the BIO.
b = bio_path.read_text(encoding="utf-8")
new_name_pattern = re.compile(r'final String newName = TelegaLocalStatus\.update\(firstNameField\.getText\(\)\.toString\(\)\.replace\("\\n", ""\), TelegaLocalStatus\.getDocumentId\(userFull\.about\), TelegaLocalStatus\.getUntil\(userFull\.about\)\);')
if "TelegaLocalStatus.updateBio(firstNameField.getText().toString().replace" not in b:
    b, count = new_name_pattern.subn(
        r'final String newName = TelegaLocalStatus.updateBio(firstNameField.getText().toString().replace("\n", ""), userFull.about);',
        b, count=1)
    if count != 1:
        print("ERROR: ChangeBioActivity metadata-preserving save anchor not found", file=sys.stderr)
        sys.exit(1)
bio_path.write_text(b, encoding="utf-8")

# 2) Opt-in badge marker syncs through the existing profile BIO API.
badge_sync_path = ROOT / "messenger" / "TelegaBadgeSync.java"
badge_sync_path.write_text(r'''package org.telegram.messenger;

import android.util.Log;

import org.telegram.tgnet.ConnectionsManager;
import org.telegram.tgnet.TLRPC;
import org.telegram.tgnet.TL_account;

/** Writes the user's opt-in Telega identity flag into the hidden BIO metadata. */
public final class TelegaBadgeSync {
    private TelegaBadgeSync() {}

    public static void update(int account, boolean enabled) {
        try {
            TLRPC.User self = UserConfig.getInstance(account).getCurrentUser();
            if (self == null || self.id == 0) return;
            TLRPC.TL_users_getFullUser load = new TLRPC.TL_users_getFullUser();
            load.id = MessagesController.getInstance(account).getInputUser(self);
            ConnectionsManager.getInstance(account).sendRequest(load, (response, error) -> {
                if (error != null || !(response instanceof TLRPC.TL_users_userFull)) {
                    if (error != null) Log.w("Telega", "Could not load BIO before syncing badge: " + error.text);
                    return;
                }
                TLRPC.UserFull full = ((TLRPC.TL_users_userFull) response).full_user;
                if (full == null) return;
                String oldAbout = full.about == null ? "" : full.about;
                String newAbout = TelegaLocalStatus.updateUserBadge(oldAbout, enabled);
                if (oldAbout.equals(newAbout)) return;
                TL_account.updateProfile request = new TL_account.updateProfile();
                request.flags |= 4;
                request.about = newAbout;
                ConnectionsManager.getInstance(account).sendRequest(request, (updateResponse, updateError) ->
                        AndroidUtilities.runOnUIThread(() -> {
                            if (updateError != null) {
                                Log.w("Telega", "Badge metadata save failed: " + updateError.text);
                                return;
                            }
                            full.about = newAbout;
                            NotificationCenter.getInstance(account).postNotificationName(
                                    NotificationCenter.updateInterfaces, MessagesController.UPDATE_MASK_ALL);
                        }));
            });
        } catch (Throwable error) {
            Log.w("Telega", "Unable to sync Telega badge metadata", error);
        }
    }
}
''', encoding="utf-8")

f = features_path.read_text(encoding="utf-8")
if "TelegaBadgeSync.update(UserConfig.selectedAccount, enabled);" not in f:
    f = replace_once(
        f,
        '        prefs().edit().putBoolean("telega_badge", enabled).apply();',
        '        prefs().edit().putBoolean("telega_badge", enabled).apply();\n        TelegaBadgeSync.update(UserConfig.selectedAccount, enabled);',
        "badge BIO sync")
if "public static boolean isTurboDownloadEnabled()" not in f:
    anchor = "    public static boolean isBadgeEnabled() {"
    methods = r'''    public static boolean isTurboDownloadEnabled() {
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

'''
    f = replace_once(f, anchor, methods + anchor, "Telega extras preferences")
features_path.write_text(f, encoding="utf-8")

# 3) Custom badge drawable can coexist with the animated emoji status drawable.
pair_path = ROOT / "ui" / "Components" / "TelegaBadgePairDrawable.java"
pair_path.write_text(r'''package org.telegram.ui.Components;

import android.graphics.Canvas;
import android.graphics.ColorFilter;
import android.graphics.PixelFormat;
import android.graphics.Rect;
import android.graphics.drawable.Drawable;

import org.telegram.messenger.AndroidUtilities;

/** Composes the existing right-side status drawable with the Telega badge. */
public final class TelegaBadgePairDrawable extends Drawable {
    private final Drawable primary;
    private final Drawable badge;

    public TelegaBadgePairDrawable(Drawable primary, Drawable badge) {
        this.primary = primary;
        this.badge = badge;
    }

    public Drawable getPrimaryDrawable() {
        return primary;
    }

    @Override
    public void draw(Canvas canvas) {
        Rect bounds = getBounds();
        int badgeWidth = badge == null ? 0 : Math.min(AndroidUtilities.dp(20), bounds.height());
        int primaryWidth = primary == null ? 0 : Math.min(primary.getIntrinsicWidth() > 0 ? primary.getIntrinsicWidth() : bounds.height(), bounds.width() - badgeWidth);
        if (primary != null && primaryWidth > 0) {
            int top = bounds.centerY() - Math.min(bounds.height(), Math.max(1, primary.getIntrinsicHeight())) / 2;
            int height = Math.min(bounds.height(), Math.max(1, primary.getIntrinsicHeight()));
            primary.setBounds(bounds.left, top, bounds.left + primaryWidth, top + height);
            primary.draw(canvas);
        }
        if (badge != null && badgeWidth > 0) {
            int left = bounds.right - badgeWidth;
            int top = bounds.centerY() - badgeWidth / 2;
            badge.setBounds(left, top, left + badgeWidth, top + badgeWidth);
            badge.draw(canvas);
        }
    }

    @Override public void setAlpha(int alpha) {
        if (primary != null) primary.setAlpha(alpha);
        if (badge != null) badge.setAlpha(alpha);
    }
    @Override public void setColorFilter(ColorFilter filter) {
        if (primary != null) primary.setColorFilter(filter);
        if (badge != null) badge.setColorFilter(filter);
    }
    @Override public int getOpacity() { return PixelFormat.TRANSLUCENT; }
    @Override public int getIntrinsicWidth() {
        return (primary == null ? 0 : Math.max(AndroidUtilities.dp(14), primary.getIntrinsicWidth()))
                + (badge == null ? 0 : AndroidUtilities.dp(20))
                + (primary != null && badge != null ? AndroidUtilities.dp(2) : 0);
    }
    @Override public int getIntrinsicHeight() {
        int first = primary == null ? 0 : primary.getIntrinsicHeight();
        int second = badge == null ? 0 : badge.getIntrinsicHeight();
        return Math.max(AndroidUtilities.dp(20), Math.max(first, second));
    }
}
''', encoding="utf-8")

# Add a name decorator so cached BIO statuses/badges can appear in chat-list rows.
render_path = ROOT / "ui" / "Components" / "TelegaBadgeRendering.java"
render_path.write_text(r'''package org.telegram.ui.Components;

import android.graphics.Paint;
import android.graphics.drawable.Drawable;
import android.text.SpannableStringBuilder;
import android.text.Spanned;
import android.text.TextPaint;
import android.text.style.ImageSpan;

import org.telegram.messenger.MessagesController;
import org.telegram.messenger.TelegaLocalStatus;
import org.telegram.tgnet.TLRPC;

public final class TelegaBadgeRendering {
    private TelegaBadgeRendering() {}

    public static CharSequence decorateDialogName(CharSequence name, int account, TLRPC.User user, TextPaint paint) {
        if (user == null || name == null) return name;
        TLRPC.UserFull full = MessagesController.getInstance(account).getUserFull(user.id);
        String about = full == null ? null : full.about;
        long statusDocumentId = TelegaLocalStatus.getDocumentId(about);
        boolean hasBadge = TelegaLocalStatus.hasUserBadge(about);
        if (statusDocumentId <= 0 && !hasBadge) return name;

        SpannableStringBuilder result = new SpannableStringBuilder(name);
        if (statusDocumentId > 0) {
            result.append(" ");
            int start = result.length();
            result.append("\uFFFC");
            AnimatedEmojiSpan statusSpan = new AnimatedEmojiSpan(statusDocumentId, paint.getFontMetricsInt());
            statusSpan.cacheType = AnimatedEmojiDrawable.CACHE_TYPE_MESSAGES;
            result.setSpan(statusSpan, start, result.length(), Spanned.SPAN_EXCLUSIVE_EXCLUSIVE);
        }
        if (hasBadge) {
            result.append(" ");
            int start = result.length();
            result.append("\uFFFC");
            TelegaBadgeDrawable drawable = new TelegaBadgeDrawable();
            int size = org.telegram.messenger.AndroidUtilities.dp(18);
            drawable.setBounds(0, 0, size, size);
            result.setSpan(new ImageSpan(drawable, ImageSpan.ALIGN_BASELINE), start, result.length(), Spanned.SPAN_EXCLUSIVE_EXCLUSIVE);
        }
        return result;
    }
}
''', encoding="utf-8")

# In DialogCell, decorate only the direct-user display name; group/topic titles are untouched.
d = dialog_cell_path.read_text(encoding="utf-8")
if "TelegaBadgeRendering.decorateDialogName" not in d:
    d = replace_once(
        d,
        '                        nameString = AndroidUtilities.escape(UserObject.getUserName(user));',
        '                        nameString = AndroidUtilities.escape(UserObject.getUserName(user));\n                        nameString = org.telegram.ui.Components.TelegaBadgeRendering.decorateDialogName(nameString, currentAccount, user, Theme.dialogs_namePaint[paintIndex]);',
        "DialogCell name decoration")
dialog_cell_path.write_text(d, encoding="utf-8")

# Replace the earlier own-profile-only badge block with a shared, non-conflicting version.
p = profile_path.read_text(encoding="utf-8")
marker = "        if (nameTextView != null && nameTextView.length > 0 && nameTextView[0] != null) {"
if marker in p:
    start = p.index(marker)
    opening = p.find("{", start)
    close = find_matching_brace(p, opening)
    if close < 0:
        print("ERROR: ProfileActivity badge block brace mismatch", file=sys.stderr)
        sys.exit(1)
    replacement = r'''        if (nameTextView != null && nameTextView.length > 0 && nameTextView[0] != null) {
            boolean telegaOwnProfile = userId == UserConfig.getInstance(currentAccount).getClientUserId();
            boolean telegaSharedBadge = userInfo != null && org.telegram.messenger.TelegaLocalStatus.hasUserBadge(userInfo.about);
            boolean telegaShowBadge = telegaSharedBadge || (telegaOwnProfile && org.telegram.messenger.TelegaFeatures.isBadgeEnabled());
            org.telegram.ui.ActionBar.SimpleTextView telegaNameView = nameTextView[0];
            android.graphics.drawable.Drawable telegaRight = telegaNameView.getRightDrawable();
            android.graphics.drawable.Drawable telegaPrimary = telegaRight;
            if (telegaRight instanceof org.telegram.ui.Components.TelegaBadgePairDrawable) {
                telegaPrimary = ((org.telegram.ui.Components.TelegaBadgePairDrawable) telegaRight).getPrimaryDrawable();
            } else if (telegaRight instanceof org.telegram.ui.Components.TelegaBadgeDrawable) {
                telegaPrimary = null;
            }
            if (telegaShowBadge) {
                telegaNameView.setRightDrawable(new org.telegram.ui.Components.TelegaBadgePairDrawable(
                        telegaPrimary, new org.telegram.ui.Components.TelegaBadgeDrawable()));
            } else if (telegaRight instanceof org.telegram.ui.Components.TelegaBadgePairDrawable
                    || telegaRight instanceof org.telegram.ui.Components.TelegaBadgeDrawable) {
                telegaNameView.setRightDrawable(telegaPrimary);
            }
        }'''
    p = p[:start] + replacement + p[close + 1:]
else:
    print("WARNING: old ProfileActivity badge block absent; shared badge still renders in dialogs.", file=sys.stderr)
profile_path.write_text(p, encoding="utf-8")

# 4) Message effects are local UI animations triggered when a matching message cell is bound.
effects_path = ROOT / "ui" / "Components" / "TelegaMessageEffects.java"
effects_path.write_text(r'''package org.telegram.ui.Components;

import android.animation.Animator;
import android.animation.AnimatorListenerAdapter;
import android.animation.ValueAnimator;
import android.content.Context;
import android.graphics.Canvas;
import android.graphics.Paint;
import android.graphics.Rect;
import android.view.View;
import android.view.ViewGroup;
import android.view.animation.LinearInterpolator;

import org.telegram.messenger.AndroidUtilities;
import org.telegram.messenger.MessageObject;
import org.telegram.messenger.TelegaFeatures;

import java.util.ArrayList;
import java.util.LinkedHashSet;
import java.util.Random;
import java.util.Set;

/** Local, GPU-light message effect overlay. Matching messages trigger on both sender and receiver clients. */
public final class TelegaMessageEffects {
    private static final Set<String> SHOWN = new LinkedHashSet<>();
    private TelegaMessageEffects() {}

    public static void onMessageBound(View anchor, MessageObject message) {
        if (anchor == null || message == null || message.messageOwner == null
                || !TelegaFeatures.isMessageEffectsEnabled()) return;
        String text = message.messageOwner.message;
        if (text == null || text.length() == 0) return;

        String glyph;
        int kind;
        if (text.contains("🎉")) {
            glyph = "🎉"; kind = 0;
        } else if (text.contains("❤️") || text.contains("❤")) {
            glyph = "❤️"; kind = 1;
        } else if (text.contains("🔥")) {
            glyph = "🔥"; kind = 2;
        } else if (text.contains("👍")) {
            glyph = "👍"; kind = 3;
        } else {
            return;
        }

        String key = message.getDialogId() + ":" + message.getId();
        synchronized (SHOWN) {
            if (SHOWN.contains(key)) return;
            SHOWN.add(key);
            if (SHOWN.size() > 400) {
                String first = SHOWN.iterator().next();
                SHOWN.remove(first);
            }
        }

        final String effectGlyph = glyph;
        final int effectKind = kind;
        anchor.post(() -> {
            if (!anchor.isAttachedToWindow()) return;
            View root = anchor.getRootView();
            if (!(root instanceof ViewGroup) || root.getWidth() <= 0 || root.getHeight() <= 0) return;
            ViewGroup group = (ViewGroup) root;
            int[] rootLocation = new int[2];
            int[] anchorLocation = new int[2];
            root.getLocationOnScreen(rootLocation);
            anchor.getLocationOnScreen(anchorLocation);
            float originX = anchorLocation[0] - rootLocation[0] + anchor.getWidth() * 0.5f;
            float originY = anchorLocation[1] - rootLocation[1] + Math.min(anchor.getHeight() * 0.45f, AndroidUtilities.dp(54));
            EffectView effect = new EffectView(anchor.getContext(), effectGlyph, effectKind, originX, originY);
            effect.layout(0, 0, root.getWidth(), root.getHeight());
            group.getOverlay().add(effect);
            effect.start(group);
        });
    }

    private static final class Particle {
        float dx, dy, size, rotation, rotationSpeed, phase;
    }

    private static final class EffectView extends View {
        private final String glyph;
        private final int kind;
        private final float originX;
        private final float originY;
        private final Paint paint = new Paint(Paint.ANTI_ALIAS_FLAG);
        private final ArrayList<Particle> particles = new ArrayList<>();
        private final int[] colors = {0xFF2F9CF4, 0xFFFF5D9E, 0xFFFFB23E, 0xFF42C98B, 0xFF9A73EF};
        private float progress;
        private ValueAnimator animator;
        private ViewGroup overlayHost;

        EffectView(Context context, String glyph, int kind, float originX, float originY) {
            super(context);
            this.glyph = glyph;
            this.kind = kind;
            this.originX = originX;
            this.originY = originY;
            setClickable(false);
            setFocusable(false);
            Random random = new Random((glyph.hashCode() * 31L) ^ System.nanoTime());
            int count = kind == 0 ? 30 : 22;
            for (int i = 0; i < count; i++) {
                Particle particle = new Particle();
                double angle = (Math.PI * 2.0 * i / count) + (random.nextFloat() - 0.5f) * 0.55f;
                float distance = AndroidUtilities.dp(24 + random.nextInt(54));
                particle.dx = (float) Math.cos(angle) * distance;
                particle.dy = (float) Math.sin(angle) * distance - AndroidUtilities.dp(12 + random.nextInt(28));
                particle.size = AndroidUtilities.dp(kind == 0 ? 13 + random.nextInt(8) : 16 + random.nextInt(9));
                particle.rotation = random.nextFloat() * 360f;
                particle.rotationSpeed = (random.nextFloat() - 0.5f) * 480f;
                particle.phase = random.nextFloat() * 0.18f;
                particles.add(particle);
            }
        }

        void start(ViewGroup host) {
            overlayHost = host;
            animator = ValueAnimator.ofFloat(0f, 1f);
            animator.setDuration(1350L);
            animator.setInterpolator(new LinearInterpolator());
            animator.addUpdateListener(value -> {
                progress = (float) value.getAnimatedValue();
                invalidate();
            });
            animator.addListener(new AnimatorListenerAdapter() {
                @Override public void onAnimationEnd(Animator animation) {
                    if (overlayHost != null) overlayHost.getOverlay().remove(EffectView.this);
                }
            });
            animator.start();
        }

        @Override protected void onDraw(Canvas canvas) {
            super.onDraw(canvas);
            float fade = Math.max(0f, 1f - progress * progress);
            paint.setAlpha((int) (255 * fade));
            paint.setTextAlign(Paint.Align.CENTER);
            for (int i = 0; i < particles.size(); i++) {
                Particle particle = particles.get(i);
                float t = Math.max(0f, Math.min(1f, progress - particle.phase));
                if (t <= 0f) continue;
                float x = originX + particle.dx * t;
                float y = originY + particle.dy * t + AndroidUtilities.dp(34) * t * t;
                paint.setTextSize(particle.size);
                if (kind == 0) {
                    paint.setColor(colors[i % colors.length]);
                    canvas.save();
                    canvas.rotate(particle.rotation + particle.rotationSpeed * t, x, y);
                    canvas.drawRoundRect(x - particle.size * 0.23f, y - particle.size * 0.45f,
                            x + particle.size * 0.23f, y + particle.size * 0.45f,
                            particle.size * 0.12f, particle.size * 0.12f, paint);
                    canvas.restore();
                } else {
                    paint.setColor(colors[(i + kind) % colors.length]);
                    canvas.drawText(glyph, x, y, paint);
                }
            }
        }
    }
}
''', encoding="utf-8")

# Hook once into ChatMessageCell's message binding so both outgoing and incoming messages use the same renderer.
m = message_cell_path.read_text(encoding="utf-8")
if "TelegaMessageEffects.onMessageBound(this," not in m:
    method_match = re.search(r'(?m)^(\s*)(?:public|protected)\s+void\s+setMessageObject\s*\(\s*MessageObject\s+(\w+)[^{;]*\)\s*\{', m)
    if not method_match:
        print("ERROR: ChatMessageCell.setMessageObject anchor not found", file=sys.stderr)
        sys.exit(1)
    parameter = method_match.group(2)
    injection = f'\n{method_match.group(1)}    org.telegram.ui.Components.TelegaMessageEffects.onMessageBound(this, {parameter});'
    m = m[:method_match.end()] + injection + m[method_match.end():]
message_cell_path.write_text(m, encoding="utf-8")

# Add the two new toggles to the existing Telega settings screen.
settings = settings_path.read_text(encoding="utf-8")
if "TelegaFeatures.isTurboDownloadEnabled()" not in settings:
    anchor = "        fragmentView = scroll;"
    rows = r'''        addToggle(context, list, "Турбо-загрузка",
                "Увеличивает число одновременно обрабатываемых загрузок до 10 на очередь. Скорость всё равно зависит от сети и серверов.",
                TelegaFeatures.isTurboDownloadEnabled(),
                (button, enabled) -> TelegaFeatures.setTurboDownloadEnabled(enabled));
        addToggle(context, list, "Эффекты сообщений",
                "Локальные анимации 🎉 ❤️ 🔥 👍 при появлении сообщения; данные для эффекта на сервер не отправляются.",
                TelegaFeatures.isMessageEffectsEnabled(),
                (button, enabled) -> TelegaFeatures.setMessageEffectsEnabled(enabled));

'''
    settings = replace_once(settings, anchor, rows + anchor, "Telega extra settings rows")
# Clarify that the badge is shared with Telega users when the toggle is enabled.
settings = settings.replace(
    "Пульсирующий значок рядом с твоим именем в собственном профиле.",
    "Скрытая отметка в BIO показывает значок другим пользователям Telega Beta."
)
settings_path.write_text(settings, encoding="utf-8")

# Increase the worker limit only when the user explicitly enables turbo mode.
q = queue_path.read_text(encoding="utf-8")
queue_anchor = "int max = type == TYPE_LARGE ? MessagesController.getInstance(currentAccount).largeQueueMaxActiveOperations : MessagesController.getInstance(currentAccount).smallQueueMaxActiveOperations;"
if "Telega turbo downloads" not in q:
    q = replace_once(
        q,
        queue_anchor,
        queue_anchor + "\n        // Telega turbo downloads: queue concurrency only; the MTProto transfer protocol is unchanged.\n        if (TelegaFeatures.isTurboDownloadEnabled()) max = Math.max(max, 10);",
        "FileLoaderPriorityQueue turbo limit")
queue_path.write_text(q, encoding="utf-8")

print("Telega shared badge/BIO metadata, chat-list status rendering, local message effects and turbo download toggle patches applied.")
