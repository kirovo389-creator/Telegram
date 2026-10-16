package org.telegram.messenger;

import android.content.Context;
import android.content.SharedPreferences;
import android.util.Log;

import com.google.firebase.FirebaseApp;
import com.google.firebase.Timestamp;
import com.google.firebase.auth.FirebaseAuth;
import com.google.firebase.auth.FirebaseUser;
import com.google.firebase.firestore.DocumentSnapshot;
import com.google.firebase.firestore.FieldValue;
import com.google.firebase.firestore.FirebaseFirestore;
import com.google.firebase.firestore.QuerySnapshot;
import com.google.firebase.firestore.SetOptions;

import java.util.HashMap;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;

/**
 * Cloud sync for Telega profile accent color and background emoji.
 *
 * Profiles are indexed by Telegram user id for discovery, but each authenticated Firebase
 * user can only write the document whose id is their own Firebase uid (see firestore.rules).
 * This is client-side convenience syncing, not cryptographic proof of Telegram identity.
 */
public final class TelegaProfileSync {
    private static final String TAG = "TelegaProfileSync";
    private static final String COLLECTION = "profile_styles";
    private static final String PREFS = "telega_profile_cloud_cache";
    private static final long MIN_FETCH_INTERVAL_MS = 60_000L;
    private static final ConcurrentHashMap<Long, Long> lastFetchAt = new ConcurrentHashMap<>();

    private TelegaProfileSync() {}

    public interface Callback {
        void onLoaded(ProfileStyle style);
    }

    public static final class ProfileStyle {
        public final int profileColor;
        public final long backgroundEmojiId;
        public final boolean exists;

        public ProfileStyle(int profileColor, long backgroundEmojiId, boolean exists) {
            this.profileColor = profileColor;
            this.backgroundEmojiId = backgroundEmojiId;
            this.exists = exists;
        }
    }

    public static void saveProfileStyle(Context context, long telegramUserId, int profileColor,
                                        long backgroundEmojiId, Callback callback) {
        if (context == null || telegramUserId <= 0) {
            deliver(callback, null);
            return;
        }
        Context appContext = context.getApplicationContext();
        ProfileStyle style = new ProfileStyle(profileColor, Math.max(0L, backgroundEmojiId), true);
        saveCache(appContext, telegramUserId, style);
        lastFetchAt.put(telegramUserId, System.currentTimeMillis());
        deliver(callback, style);

        ensureSignedIn(appContext, user -> {
            if (user == null) {
                Log.w(TAG, "Cloud save skipped: Firebase Auth is unavailable or anonymous sign-in is disabled.");
                return;
            }
            FirebaseApp app = TelegaSyncFirebase.getInstance(appContext);
            if (app == null) {
                return;
            }
            Map<String, Object> data = new HashMap<>();
            data.put("ownerUid", user.getUid());
            data.put("telegramUserId", telegramUserId);
            data.put("profileColor", profileColor);
            data.put("backgroundEmojiId", Math.max(0L, backgroundEmojiId));
            data.put("updatedAt", FieldValue.serverTimestamp());

            FirebaseFirestore.getInstance(app).collection(COLLECTION).document(user.getUid())
                    .set(data, SetOptions.merge())
                    .addOnSuccessListener(unused -> Log.i(TAG, "Profile style saved to Firestore for Telega user "
                            + telegramUserId))
                    .addOnFailureListener(error -> Log.w(TAG, "Firestore profile-style save failed", error));
        });
    }

    /**
     * Returns a local cached style immediately (when present) and refreshes it from Firestore.
     * Repeated profile redraws are throttled, so updates do not create a redraw/network loop.
     */
    public static void loadProfileStyle(Context context, long telegramUserId, Callback callback) {
        if (context == null || telegramUserId <= 0) {
            deliver(callback, null);
            return;
        }
        Context appContext = context.getApplicationContext();
        ProfileStyle cached = readCache(appContext, telegramUserId);
        if (cached != null) {
            deliver(callback, cached);
        }

        long now = System.currentTimeMillis();
        Long last = lastFetchAt.get(telegramUserId);
        if (last != null && now - last < MIN_FETCH_INTERVAL_MS) {
            if (cached == null) {
                deliver(callback, null);
            }
            return;
        }
        lastFetchAt.put(telegramUserId, now);

        ensureSignedIn(appContext, user -> {
            if (user == null) {
                if (cached == null) deliver(callback, null);
                Log.w(TAG, "Cloud load skipped: Firebase Auth is unavailable or anonymous sign-in is disabled.");
                return;
            }
            FirebaseApp app = TelegaSyncFirebase.getInstance(appContext);
            if (app == null) {
                if (cached == null) deliver(callback, null);
                return;
            }
            FirebaseFirestore.getInstance(app).collection(COLLECTION)
                    .whereEqualTo("telegramUserId", telegramUserId)
                    .get()
                    .addOnSuccessListener(snapshot -> {
                        ProfileStyle latest = findLatest(snapshot);
                        if (latest != null) {
                            saveCache(appContext, telegramUserId, latest);
                        }
                        deliver(callback, latest);
                    })
                    .addOnFailureListener(error -> {
                        Log.w(TAG, "Firestore profile-style load failed for Telega user "
                                + telegramUserId, error);
                        if (cached == null) deliver(callback, null);
                    });
        });
    }

    private static ProfileStyle findLatest(QuerySnapshot snapshot) {
        if (snapshot == null || snapshot.isEmpty()) {
            return null;
        }
        DocumentSnapshot latestDocument = null;
        long latestTime = Long.MIN_VALUE;
        for (DocumentSnapshot document : snapshot.getDocuments()) {
            long time = Long.MIN_VALUE;
            Object updated = document.get("updatedAt");
            if (updated instanceof Timestamp) {
                time = ((Timestamp) updated).getSeconds();
            }
            if (latestDocument == null || time >= latestTime) {
                latestDocument = document;
                latestTime = time;
            }
        }
        if (latestDocument == null) {
            return null;
        }
        long backgroundEmojiId = latestDocument.getLong("backgroundEmojiId") == null
                ? 0L : latestDocument.getLong("backgroundEmojiId");
        Long colorValue = latestDocument.getLong("profileColor");
        int color = colorValue == null ? -1 : colorValue.intValue();
        return new ProfileStyle(color, Math.max(0L, backgroundEmojiId), true);
    }

    private static void ensureSignedIn(Context context, AuthCallback callback) {
        FirebaseApp app = TelegaSyncFirebase.getInstance(context);
        if (app == null) {
            callback.onReady(null);
            return;
        }
        FirebaseAuth auth = FirebaseAuth.getInstance(app);
        FirebaseUser currentUser = auth.getCurrentUser();
        if (currentUser != null) {
            callback.onReady(currentUser);
            return;
        }
        auth.signInAnonymously()
                .addOnSuccessListener(result -> callback.onReady(result.getUser()))
                .addOnFailureListener(error -> {
                    Log.w(TAG, "Firebase anonymous sign-in failed. Enable the Anonymous provider in Firebase Authentication.", error);
                    callback.onReady(null);
                });
    }

    private interface AuthCallback {
        void onReady(FirebaseUser user);
    }

    private static void deliver(Callback callback, ProfileStyle style) {
        if (callback != null) {
            AndroidUtilities.runOnUIThread(() -> callback.onLoaded(style));
        }
    }

    private static void saveCache(Context context, long telegramUserId, ProfileStyle style) {
        prefs(context).edit()
                .putBoolean("has_" + telegramUserId, style != null && style.exists)
                .putInt("color_" + telegramUserId, style == null ? -1 : style.profileColor)
                .putLong("emoji_" + telegramUserId, style == null ? 0L : style.backgroundEmojiId)
                .putLong("cached_at_" + telegramUserId, System.currentTimeMillis())
                .apply();
    }

    private static ProfileStyle readCache(Context context, long telegramUserId) {
        SharedPreferences preferences = prefs(context);
        if (!preferences.getBoolean("has_" + telegramUserId, false)) {
            return null;
        }
        return new ProfileStyle(preferences.getInt("color_" + telegramUserId, -1),
                preferences.getLong("emoji_" + telegramUserId, 0L), true);
    }

    private static SharedPreferences prefs(Context context) {
        return context.getSharedPreferences(PREFS, Context.MODE_PRIVATE);
    }
}
