package org.telegram.ui.Components;

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
