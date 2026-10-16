package org.telegram.messenger;

import android.content.Context;
import android.content.SharedPreferences;
import android.util.Log;

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
    private static final int MAX_BYTES = 1024 * 1024;
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
                success = true;
                message = "Каталоги TelegaSync обновлены";
            } catch (Exception error) {
                Log.w(TAG, "Remote catalog sync failed; cached catalogs are retained", error);
                message = "Ошибка сети или каталога. Сохранённые данные не удалены";
            } finally {
                syncing = false;
            }
            final boolean result = success;
            final String resultMessage = message;
            AndroidUtilities.runOnUIThread(() -> {
                if (callback != null) callback.onComplete(result, resultMessage);
            });
        });
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
