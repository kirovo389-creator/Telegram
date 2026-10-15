package org.telegram.ui.Components;

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
