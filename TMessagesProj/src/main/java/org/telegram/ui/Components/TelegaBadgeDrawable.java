package org.telegram.ui.Components;

import android.graphics.Canvas;
import android.graphics.Color;
import android.graphics.Paint;
import android.graphics.Path;
import android.graphics.Rect;
import android.graphics.drawable.Drawable;
import android.os.SystemClock;

import org.telegram.messenger.AndroidUtilities;

/** Small animated Telega paper-plane badge. No external assets or network resources. */
public final class TelegaBadgeDrawable extends Drawable {
    private final Paint paint = new Paint(Paint.ANTI_ALIAS_FLAG);
    private final Path plane = new Path();
    private final Runnable frame = this::invalidateSelf;
    private final long startedAt = SystemClock.uptimeMillis();

    @Override
    public void draw(Canvas canvas) {
        Rect bounds = getBounds();
        if (bounds.width() <= 0 || bounds.height() <= 0) return;
        float cx = bounds.exactCenterX();
        float cy = bounds.exactCenterY();
        float unit = Math.min(bounds.width(), bounds.height()) / 20.0f;
        float phase = (SystemClock.uptimeMillis() - startedAt) % 1200L / 1200.0f;

        canvas.save();
        canvas.translate(cx, cy);
        float ringRadius = (6.6f + phase * 3.0f) * unit;
        paint.setStyle(Paint.Style.STROKE);
        paint.setStrokeWidth(1.2f * unit);
        paint.setColor(Color.argb((int) (105 * (1.0f - phase)), 35, 151, 245));
        canvas.drawCircle(0, 0, ringRadius, paint);

        paint.setStyle(Paint.Style.FILL);
        paint.setColor(Color.rgb(35, 151, 245));
        canvas.drawCircle(0, 0, 6.5f * unit, paint);

        plane.reset();
        plane.moveTo(-4.2f * unit, -0.1f * unit);
        plane.lineTo(4.1f * unit, -3.2f * unit);
        plane.lineTo(1.9f * unit, 3.4f * unit);
        plane.lineTo(0.3f * unit, 1.2f * unit);
        plane.lineTo(-1.7f * unit, 2.6f * unit);
        plane.lineTo(-1.2f * unit, 0.6f * unit);
        plane.close();
        paint.setColor(Color.WHITE);
        canvas.drawPath(plane, paint);
        canvas.restore();

        scheduleSelf(frame, SystemClock.uptimeMillis() + 40);
    }

    @Override public void setAlpha(int alpha) {}
    @Override public void setColorFilter(android.graphics.ColorFilter filter) {}
    @Override public int getOpacity() { return android.graphics.PixelFormat.TRANSLUCENT; }
    @Override public int getIntrinsicWidth() { return AndroidUtilities.dp(20); }
    @Override public int getIntrinsicHeight() { return AndroidUtilities.dp(20); }
}
