#!/usr/bin/env python3
"""Generate the TelegaSync remote, read-only JSON catalog client."""
from pathlib import Path

root = Path("TMessagesProj/src/main/java/org/telegram")
target = root / "messenger" / "TelegaRemoteCatalog.java"
target.parent.mkdir(parents=True, exist_ok=True)
target.write_text(r'''package org.telegram.messenger;

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
''', encoding="utf-8")

emoji_data = root / "messenger" / "EmojiData.java"
emoji_source = emoji_data.read_text(encoding="utf-8")
if "applyRemoteUnicodeCatalog" not in emoji_source:
    emoji_source = emoji_source.replace(
        "import java.util.HashSet;",
        "import java.util.HashSet;\nimport java.util.ArrayList;\nimport java.util.LinkedHashSet;\nimport org.json.JSONArray;\nimport org.json.JSONObject;",
        1
    )
    merge_method = r'''
    /**
     * Replaces Telegram's static emoji keyboard categories with the fully-qualified entries
     * from the verified remote Unicode catalog. Native categories remain as offline fallback
     * until a catalog has been downloaded successfully.
     */
    public static synchronized int applyRemoteUnicodeCatalog(String catalogJson) {
        if (catalogJson == null || catalogJson.isEmpty()) return 0;
        try {
            JSONObject root = new JSONObject(catalogJson);
            if (root.optInt("schema_version", -1) != 1) return 0;
            JSONArray emojis = root.optJSONArray("emojis");
            if (emojis == null) return 0;

            ArrayList<LinkedHashSet<String>> categories = new ArrayList<>(data.length);
            for (int i = 0; i < data.length; i++) {
                categories.add(new LinkedHashSet<>());
            }

            for (int i = 0; i < emojis.length(); i++) {
                JSONObject item = emojis.optJSONObject(i);
                if (item == null || !"fully-qualified".equals(item.optString("qualification"))) continue;
                String sequence = item.optString("sequence");
                if (sequence.isEmpty()) continue;
                int category = remoteEmojiCategory(item.optString("group"));
                if (category >= 0 && category < categories.size()) {
                    categories.get(category).add(sequence);
                }
            }

            int total = 0;
            for (LinkedHashSet<String> category : categories) total += category.size();
            if (total < 1000) return 0;

            for (int i = 0; i < data.length; i++) {
                String[] values = categories.get(i).toArray(new String[0]);
                data[i] = values;
                if (i < dataColored.length) {
                    dataColored[i] = values.clone();
                }
                for (String sequence : values) {
                    for (int offset = 0; offset < sequence.length();) {
                        int codePoint = sequence.codePointAt(offset);
                        if (codePoint >= 0x203C && codePoint <= 0x3299) {
                            dataCharsMap.put((char) codePoint, true);
                        }
                        offset += Character.charCount(codePoint);
                    }
                }
            }
            return total;
        } catch (Exception error) {
            FileLog.e("TelegaSync: invalid Unicode catalog " + error);
            return 0;
        }
    }

    private static int remoteEmojiCategory(String group) {
        if ("Smileys & Emotion".equals(group) || "People & Body".equals(group)) return 0;
        if ("Animals & Nature".equals(group)) return 1;
        if ("Food & Drink".equals(group)) return 2;
        if ("Activities".equals(group)) return 3;
        if ("Travel & Places".equals(group)) return 4;
        if ("Objects".equals(group)) return 5;
        if ("Symbols".equals(group)) return 6;
        if ("Flags".equals(group)) return 7;
        return -1;
    }

'''
    if "    static {" not in emoji_source:
        raise SystemExit("EmojiData static initializer anchor missing")
    emoji_source = emoji_source.replace("    static {", merge_method + "    static {", 1)
    emoji_data.write_text(emoji_source, encoding="utf-8")

app_loader = root / "messenger" / "ApplicationLoader.java"
loader_source = app_loader.read_text(encoding="utf-8")
if "TelegaRemoteCatalog.syncIfStale(applicationContext)" not in loader_source:
    anchor = "        SharedConfig.loadConfig();"
    if anchor not in loader_source:
        raise SystemExit("ApplicationLoader startup anchor missing")
    loader_source = loader_source.replace(
        anchor,
        anchor + "\n        TelegaRemoteCatalog.applyCachedCatalog(applicationContext);"
                + "\n        TelegaRemoteCatalog.syncIfStale(applicationContext);",
        1
    )
    app_loader.write_text(loader_source, encoding="utf-8")


print(f"Wrote {target}")
