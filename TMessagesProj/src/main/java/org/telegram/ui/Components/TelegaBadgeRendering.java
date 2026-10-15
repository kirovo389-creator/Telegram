package org.telegram.ui.Components;

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
