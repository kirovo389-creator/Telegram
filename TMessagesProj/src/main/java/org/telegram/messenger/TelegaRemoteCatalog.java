package org.telegram.messenger;

import android.content.Context;
import android.content.SharedPreferences;
import android.util.Log;

import org.json.JSONArray;
import org.json.JSONObject;

import java.io.ByteArrayOutputStream;
import java.io.InputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.charset.StandardCharsets;

/**
 * Fetches public, versioned TelegaSync catalogs. This is deliberately read-only:
 * no GitHub credentials, Telegram session data, or personal settings are uploaded.
 */
public final class TelegaRemoteCatalog {
    private static final String TAG = "TelegaSync";
    private static final String PREFS = "telega_remote_catalog";
    private static final String MANIFEST_URL =
            "https://raw.githubusercontent.com/kirovo389-creator/TelegaSync/main/config/v1/manifest.json";
    private static final int MAX_BYTES = 4 * 1024 * 1024;
    private static volatile boolean syncing;

    private TelegaRemoteCatalog() {}

    public interface Callback {
        void onComplete(boolean success, String message);
    }

    public static boolean isSyncing() {
        return syncing;
    }

    public static long getLastSyncTime(Context context) {
        return prefs(context).getLong("last_sync", 0L);
    }

    /** Refresh public catalogs at most once per day; read the last known cache immediately. */
    public static void syncIfStale(Context context) {
        long lastSync = getLastSyncTime(context);
        if (lastSync <= 0L || System.currentTimeMillis() - lastSync >= 24L * 60L * 60L * 1000L) {
            sync(context, null);
        }
    }

    public static String getUnicodeCatalog(Context context) {
        return prefs(context).getString("unicode_json", "");
    }

    public static String getCustomEmojiCatalog(Context context) {
        return prefs(context).getString("custom_emoji_json", "");
    }

    public static void sync(Context context, Callback callback) {
        final Context appContext = context.getApplicationContext();
        synchronized (TelegaRemoteCatalog.class) {
            if (syncing) {
                if (callback != null) callback.onComplete(false, "Синхронизация уже выполняется");
                return;
            }
            syncing = true;
        }
        Utilities.globalQueue.postRunnable(() -> {
            boolean success = false;
            int catalogCount = 0;
            String message = "Не удалось загрузить каталоги";
            try {
                JSONObject manifest = new JSONObject(download(MANIFEST_URL));
                if (manifest.optInt("schema_version", -1) != 1) {
                    throw new IllegalStateException("Неподдерживаемая версия манифеста");
                }
                JSONObject catalogs = manifest.getJSONObject("catalogs");
                String unicodeUrl = catalogs.getString("unicode");
                String customEmojiUrl = catalogs.getString("custom_emoji");
                requireTrustedUrl(unicodeUrl);
                requireTrustedUrl(customEmojiUrl);
                String unicode = download(unicodeUrl);
                String customEmoji = download(customEmojiUrl);
                JSONObject unicodeJson = new JSONObject(unicode);
                JSONObject customJson = new JSONObject(customEmoji);
                if (unicodeJson.optInt("schema_version", -1) != 1
                        || customJson.optInt("schema_version", -1) != 1
                        || !unicodeJson.has("emojis")
                        || !customJson.has("emojis")) {
                    throw new IllegalStateException("Некорректная структура каталога");
                }
                prefs(appContext).edit()
                        .putString("manifest_json", manifest.toString())
                        .putString("unicode_json", unicodeJson.toString())
                        .putString("custom_emoji_json", customJson.toString())
                        .putLong("last_sync", System.currentTimeMillis())
                        .apply();
                catalogCount = EmojiData.applyRemoteUnicodeCatalog(unicodeJson.toString());
                success = true;
                message = "Каталоги TelegaSync обновлены";
            } catch (Exception error) {
                Log.w(TAG, "Remote catalog sync failed; cached catalogs are retained", error);
                message = "Ошибка сети или каталога. Сохранённые данные не удалены";
            } finally {
                syncing = false;
            }
            final boolean result = success;
            final int resultCount = catalogCount;
            final String resultMessage = message;
            AndroidUtilities.runOnUIThread(() -> {
                if (result) {
                    Log.i(TAG, "Remote Unicode catalog applied; entries=" + resultCount);
                    if (callback != null) callback.onComplete(true,
                            "Каталоги обновлены. Эмодзи в каталоге: " + resultCount
                                    + ". Перезапусти Telega, чтобы обновились уже открытые панели.");
                } else if (callback != null) {
                    callback.onComplete(false, resultMessage);
                }
            });
        });
    }

    /** Applies the last successfully downloaded Unicode catalog without requiring network access. */
    public static void applyCachedCatalog(Context context) {
        String json = getUnicodeCatalog(context);
        if (json == null || json.isEmpty()) return;
        final String cached = json;
        Utilities.globalQueue.postRunnable(() -> {
            int count = EmojiData.applyRemoteUnicodeCatalog(cached);
            Log.i(TAG, "Applied cached Unicode catalog; entries=" + count);
        });
    }

    public static int getCustomEmojiCount(Context context) {
        try {
            JSONObject json = new JSONObject(getCustomEmojiCatalog(context));
            JSONArray emojis = json.optJSONArray("emojis");
            return emojis == null ? 0 : emojis.length();
        } catch (Exception ignored) {
            return 0;
        }
    }

    /** Looks up an explicitly curated fallback -> document ID mapping from the remote catalog. */
    public static long findCustomEmojiDocumentId(Context context, String fallback) {
        if (fallback == null || fallback.isEmpty()) return 0L;
        try {
            JSONArray emojis = new JSONObject(getCustomEmojiCatalog(context)).optJSONArray("emojis");
            if (emojis == null) return 0L;
            for (int i = 0; i < emojis.length(); i++) {
                JSONObject item = emojis.optJSONObject(i);
                if (item != null && fallback.equals(item.optString("fallback"))
                        && item.optLong("document_id", 0L) > 0L) {
                    return item.optLong("document_id", 0L);
                }
            }
        } catch (Exception ignored) {
        }
        return 0L;
    }

    private static SharedPreferences prefs(Context context) {
        return context.getSharedPreferences(PREFS, Context.MODE_PRIVATE);
    }

    private static void requireTrustedUrl(String value) {
        if (value == null || !(value.startsWith("https://raw.githubusercontent.com/kirovo389-creator/TelegaSync/"))) {
            throw new IllegalArgumentException("Untrusted catalog URL");
        }
    }

    private static String download(String address) throws Exception {
        HttpURLConnection connection = null;
        try {
            connection = (HttpURLConnection) new URL(address).openConnection();
            connection.setConnectTimeout(10000);
            connection.setReadTimeout(15000);
            connection.setRequestMethod("GET");
            connection.setInstanceFollowRedirects(false);
            connection.setRequestProperty("Accept", "application/json");
            int status = connection.getResponseCode();
            if (status != HttpURLConnection.HTTP_OK) {
                throw new IllegalStateException("HTTP " + status);
            }
            int length = connection.getContentLength();
            if (length > MAX_BYTES) throw new IllegalStateException("Response too large");
            try (InputStream input = connection.getInputStream();
                 ByteArrayOutputStream output = new ByteArrayOutputStream()) {
                byte[] buffer = new byte[8192];
                int total = 0;
                int count;
                while ((count = input.read(buffer)) != -1) {
                    total += count;
                    if (total > MAX_BYTES) throw new IllegalStateException("Response too large");
                    output.write(buffer, 0, count);
                }
                return new String(output.toByteArray(), StandardCharsets.UTF_8);
            }
        } finally {
            if (connection != null) connection.disconnect();
        }
    }
}
