package org.telegram.messenger;

import android.app.AlertDialog;
import android.content.Context;
import android.content.Intent;
import android.net.Uri;
import android.os.Build;
import android.util.Log;

import org.json.JSONArray;
import org.json.JSONObject;

import java.io.BufferedReader;
import java.io.InputStream;
import java.io.InputStreamReader;
import java.net.HttpURLConnection;
import java.net.URL;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

/** Checks public GitHub prereleases and offers a user-confirmed APK update. */
public final class TelegaOtaUpdater {
    private static final String TAG = "TelegaOTA";
    private static final String RELEASES_API =
            "https://api.github.com/repos/kirovo389-creator/Telegram/releases?per_page=10";
    private static final String PREFS = "telega_ota";
    private static final ExecutorService EXECUTOR = Executors.newSingleThreadExecutor();

    private TelegaOtaUpdater() {}

    public static void check(Context context) {
        final Context app = context == null ? null : context.getApplicationContext();
        if (app == null) return;
        EXECUTOR.execute(() -> {
            HttpURLConnection connection = null;
            try {
                connection = (HttpURLConnection) new URL(RELEASES_API).openConnection();
                connection.setConnectTimeout(8000);
                connection.setReadTimeout(8000);
                connection.setRequestProperty("Accept", "application/vnd.github+json");
                connection.setRequestProperty("X-GitHub-Api-Version", "2022-11-28");
                connection.setRequestProperty("User-Agent", "Telega-Beta-OTA");
                int status = connection.getResponseCode();
                if (status != 200) return;
                StringBuilder body = new StringBuilder();
                try (InputStream stream = connection.getInputStream();
                     BufferedReader reader = new BufferedReader(new InputStreamReader(stream, "UTF-8"))) {
                    String line;
                    while ((line = reader.readLine()) != null) body.append(line);
                }
                JSONArray releases = new JSONArray(body.toString());
                long installedVersion;
                try {
                    if (Build.VERSION.SDK_INT >= 28) {
                        installedVersion = app.getPackageManager().getPackageInfo(app.getPackageName(), 0).getLongVersionCode();
                    } else {
                        installedVersion = app.getPackageManager().getPackageInfo(app.getPackageName(), 0).versionCode;
                    }
                } catch (Throwable ignored) {
                    installedVersion = 0;
                }
                JSONObject newest = null;
                long newestVersion = installedVersion;
                for (int i = 0; i < releases.length(); i++) {
                    JSONObject release = releases.optJSONObject(i);
                    if (release == null || release.optBoolean("draft", false)) continue;
                    String tag = release.optString("tag_name", "");
                    if (!tag.startsWith("telega-build-")) continue;
                    long run;
                    try { run = Long.parseLong(tag.substring("telega-build-".length())); }
                    catch (Throwable ignored) { continue; }
                    long candidateVersion = 7175L + run;
                    JSONArray assets = release.optJSONArray("assets");
                    if (assets == null) continue;
                    String apk = null;
                    for (int j = 0; j < assets.length(); j++) {
                        JSONObject asset = assets.optJSONObject(j);
                        if (asset != null && asset.optString("name", "").toLowerCase().endsWith(".apk")) {
                            apk = asset.optString("browser_download_url", null);
                            if (apk != null && !apk.isEmpty()) break;
                        }
                    }
                    if (apk != null && candidateVersion > newestVersion) {
                        newestVersion = candidateVersion;
                        newest = new JSONObject(release.toString());
                        newest.put("_telega_apk_url", apk);
                        newest.put("_telega_version_code", candidateVersion);
                    }
                }
                if (newest == null) return;
                JSONObject found = newest;
                android.os.Handler main = new android.os.Handler(app.getMainLooper());
                main.post(() -> showUpdateDialog(app, found));
            } catch (Throwable error) {
                Log.d(TAG, "Release check failed; current app remains usable", error);
            } finally {
                if (connection != null) connection.disconnect();
            }
        });
    }

    private static void showUpdateDialog(Context context, JSONObject release) {
        try {
            String tag = release.optString("tag_name", "new version");
            String notes = release.optString("body", "");
            if (notes.length() > 700) notes = notes.substring(0, 700) + "…";
            String message = "Доступна новая версия Telega Beta: " + tag
                    + "\n\n" + (notes.isEmpty() ? "Исправления и улучшения." : notes)
                    + "\n\nНажми «Скачать», чтобы открыть APK из GitHub Releases. Android попросит подтвердить установку.";
            String apkUrl = release.optString("_telega_apk_url", "");
            new AlertDialog.Builder(context)
                    .setTitle("Обновление Telega")
                    .setMessage(message)
                    .setNegativeButton("Позже", (dialog, which) -> {})
                    .setNeutralButton("Релиз", (dialog, which) -> openUrl(context,
                            release.optString("html_url", "https://github.com/kirovo389-creator/Telegram/releases")))
                    .setPositiveButton("Скачать", (dialog, which) -> openUrl(context, apkUrl))
                    .show();
        } catch (Throwable error) {
            Log.w(TAG, "Unable to show update dialog", error);
        }
    }

    private static void openUrl(Context context, String url) {
        if (url == null || !url.startsWith("https://github.com/kirovo389-creator/Telegram/releases")) return;
        try {
            Intent intent = new Intent(Intent.ACTION_VIEW, Uri.parse(url));
            intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
            context.startActivity(intent);
        } catch (Throwable error) {
            Log.w(TAG, "Unable to open release link", error);
        }
    }
}
