#!/usr/bin/env python3
"""Add GitHub Releases OTA checking, APK download and user-approved PackageInstaller flow."""
from pathlib import Path
import re
import sys

root = Path("TMessagesProj/src/main/java/org/telegram")
launch = root / "ui" / "LaunchActivity.java"
manifest = Path("TMessagesProj/src/main/AndroidManifest.xml")
if not launch.exists() or not manifest.exists():
    print("ERROR: LaunchActivity or AndroidManifest is missing", file=sys.stderr)
    sys.exit(1)

helper = root / "messenger" / "TelegaOtaUpdater.java"
helper.write_text(r'''package org.telegram.messenger;

import android.app.Activity;
import android.app.AlertDialog;
import android.app.PendingIntent;
import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.content.pm.PackageInstaller;
import android.net.Uri;
import android.os.Build;
import android.os.Environment;
import android.os.Handler;
import android.os.Looper;
import android.provider.Settings;
import android.util.Log;
import android.widget.Toast;

import org.json.JSONArray;
import org.json.JSONObject;

import java.io.BufferedInputStream;
import java.io.BufferedOutputStream;
import java.io.File;
import java.io.FileInputStream;
import java.io.FileOutputStream;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.security.MessageDigest;
import java.util.Locale;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

public final class TelegaOtaUpdater {
    private static final String TAG = "TelegaOTA";
    private static final String RELEASES_API =
            "https://api.github.com/repos/kirovo389-creator/Telegram/releases?per_page=10";
    private static final String RELEASE_PREFIX =
            "https://github.com/kirovo389-creator/Telegram/releases/download/";
    private static final String PREFS = "telega_ota";
    private static final long CHECK_INTERVAL = 6L * 60L * 60L * 1000L;
    private static final long MAX_APK_BYTES = 300L * 1024L * 1024L;
    private static final ExecutorService EXECUTOR = Executors.newSingleThreadExecutor();
    private static final Handler MAIN = new Handler(Looper.getMainLooper());

    private TelegaOtaUpdater() {}

    private static SharedPreferences prefs(Context context) {
        return context.getApplicationContext().getSharedPreferences(PREFS, Context.MODE_PRIVATE);
    }

    public static void check(Context activityContext) {
        if (!(activityContext instanceof Activity)) return;
        final Activity activity = (Activity) activityContext;
        final Context app = activity.getApplicationContext();
        if (System.currentTimeMillis() - prefs(app).getLong("last_check", 0) < CHECK_INTERVAL) return;

        EXECUTOR.execute(() -> {
            HttpURLConnection connection = null;
            try {
                connection = (HttpURLConnection) new URL(RELEASES_API).openConnection();
                connection.setConnectTimeout(8000);
                connection.setReadTimeout(10000);
                connection.setRequestProperty("Accept", "application/vnd.github+json");
                connection.setRequestProperty("X-GitHub-Api-Version", "2022-11-28");
                connection.setRequestProperty("User-Agent", "Telega-Beta-OTA");
                int status = connection.getResponseCode();
                if (status != 200) return;
                StringBuilder body = new StringBuilder();
                try (InputStream stream = connection.getInputStream();
                     BufferedInputStream input = new BufferedInputStream(stream)) {
                    byte[] buffer = new byte[8192];
                    int read;
                    while ((read = input.read(buffer)) != -1) body.append(new String(buffer, 0, read, "UTF-8"));
                }
                prefs(app).edit().putLong("last_check", System.currentTimeMillis()).apply();
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
                    JSONObject apkAsset = null;
                    for (int j = 0; j < assets.length(); j++) {
                        JSONObject asset = assets.optJSONObject(j);
                        if (asset != null && asset.optString("name", "").equalsIgnoreCase("Telega-debug.apk")) {
                            apkAsset = asset;
                            break;
                        }
                    }
                    if (apkAsset != null && candidateVersion > newestVersion) {
                        String url = apkAsset.optString("browser_download_url", "");
                        if (!url.startsWith(RELEASE_PREFIX)) continue;
                        newestVersion = candidateVersion;
                        newest = new JSONObject(release.toString());
                        newest.put("_telega_apk_url", url);
                        newest.put("_telega_version_code", candidateVersion);
                        newest.put("_telega_size", apkAsset.optLong("size", -1));
                        newest.put("_telega_digest", apkAsset.optString("digest", ""));
                    }
                }
                if (newest == null) return;
                String tag = newest.optString("tag_name", "");
                if (tag.equals(prefs(app).getString("dismissed_tag", ""))) return;
                JSONObject found = newest;
                MAIN.post(() -> {
                    if (!activity.isFinishing() && !activity.isDestroyed()) showUpdateDialog(activity, app, found);
                });
            } catch (Throwable error) {
                Log.d(TAG, "GitHub update check failed; current app remains usable", error);
            } finally {
                if (connection != null) connection.disconnect();
            }
        });
    }

    private static void showUpdateDialog(Activity activity, Context app, JSONObject release) {
        try {
            String tag = release.optString("tag_name", "new version");
            String notes = release.optString("body", "");
            if (notes.length() > 700) notes = notes.substring(0, 700) + "…";
            String message = "Доступна новая версия Telega Beta: " + tag
                    + "\n\n" + (notes.isEmpty() ? "Исправления и улучшения." : notes)
                    + "\n\nAPK будет загружен из GitHub Releases. Для установки Android может запросить разрешение. Системный диалог установки нужно подтвердить.";
            String url = release.optString("_telega_apk_url", "");
            String digest = release.optString("_telega_digest", "");
            long expectedSize = release.optLong("_telega_size", -1);
            new AlertDialog.Builder(activity)
                    .setTitle("Обновление Telega")
                    .setMessage(message)
                    .setNegativeButton("Позже", (dialog, which) ->
                            prefs(app).edit().putString("dismissed_tag", tag).apply())
                    .setNeutralButton("Релиз", (dialog, which) ->
                            openReleasePage(activity, release.optString("html_url",
                                    "https://github.com/kirovo389-creator/Telegram/releases")))
                    .setPositiveButton("Скачать и установить", (dialog, which) ->
                            downloadApk(activity, url, digest, expectedSize, tag))
                    .show();
        } catch (Throwable error) {
            Log.w(TAG, "Unable to show update dialog", error);
        }
    }

    private static void downloadApk(Activity activity, String url, String digest, long expectedSize, String tag) {
        if (url == null || !url.startsWith(RELEASE_PREFIX)) return;
        Toast.makeText(activity, "Загружаю обновление Telega…", Toast.LENGTH_SHORT).show();
        final Context app = activity.getApplicationContext();
        EXECUTOR.execute(() -> {
            HttpURLConnection connection = null;
            File apk = null;
            try {
                connection = (HttpURLConnection) new URL(url).openConnection();
                connection.setConnectTimeout(12000);
                connection.setReadTimeout(20000);
                connection.setRequestProperty("User-Agent", "Telega-Beta-OTA");
                connection.setInstanceFollowRedirects(true);
                if (connection.getResponseCode() != 200) throw new IllegalStateException("GitHub returned HTTP " + connection.getResponseCode());
                long declared = connection.getContentLengthLong();
                if (declared > MAX_APK_BYTES || expectedSize > MAX_APK_BYTES) throw new IllegalStateException("APK exceeds allowed size");
                File dir = new File(app.getFilesDir(), "ota");
                if (!dir.exists() && !dir.mkdirs()) throw new IllegalStateException("Cannot create update directory");
                apk = new File(dir, "Telega-update.apk");
                MessageDigest sha = MessageDigest.getInstance("SHA-256");
                long written = 0;
                try (InputStream input = new BufferedInputStream(connection.getInputStream());
                     OutputStream output = new BufferedOutputStream(new FileOutputStream(apk, false))) {
                    byte[] buffer = new byte[32768];
                    int count;
                    while ((count = input.read(buffer)) != -1) {
                        written += count;
                        if (written > MAX_APK_BYTES) throw new IllegalStateException("APK exceeds allowed size");
                        sha.update(buffer, 0, count);
                        output.write(buffer, 0, count);
                    }
                }
                if (expectedSize > 0 && written != expectedSize) throw new IllegalStateException("APK size mismatch");
                String actualDigest = toHex(sha.digest());
                if (digest != null && digest.startsWith("sha256:") &&
                        !actualDigest.equalsIgnoreCase(digest.substring("sha256:".length()))) {
                    throw new SecurityException("APK checksum mismatch");
                }
                prefs(app).edit().putString("pending_file", apk.getAbsolutePath())
                        .putString("pending_tag", tag).putBoolean("awaiting_unknown_sources", false).apply();
                MAIN.post(() -> {
                    Toast.makeText(app, "Обновление загружено. Подготавливаю установку…", Toast.LENGTH_LONG).show();
                    installPending(activity);
                });
            } catch (Throwable error) {
                if (apk != null) apk.delete();
                Log.e(TAG, "Update download/verification failed", error);
                MAIN.post(() -> Toast.makeText(app, "Не удалось загрузить обновление. Текущая версия сохранена.", Toast.LENGTH_LONG).show());
            } finally {
                if (connection != null) connection.disconnect();
            }
        });
    }

    /** Called on resume so installation can continue after the user grants unknown-source permission. */
    public static void installPending(Activity activity) {
        if (activity == null || activity.isFinishing() || activity.isDestroyed()) return;
        Context app = activity.getApplicationContext();
        SharedPreferences preferences = prefs(app);
        String path = preferences.getString("pending_file", "");
        if (path.isEmpty()) return;
        File file = new File(path);
        if (!file.isFile() || file.length() < 1024) {
            preferences.edit().remove("pending_file").apply();
            return;
        }
        if (Build.VERSION.SDK_INT >= 26 && !app.getPackageManager().canRequestPackageInstalls()) {
            if (preferences.getBoolean("awaiting_unknown_sources", false)) return;
            preferences.edit().putBoolean("awaiting_unknown_sources", true).apply();
            new AlertDialog.Builder(activity)
                    .setTitle("Разрешение на обновление")
                    .setMessage("Чтобы установить APK из GitHub Releases, разреши Telega устанавливать обновления из этого источника. Android покажет системный экран разрешений.")
                    .setNegativeButton("Позже", (dialog, which) -> {})
                    .setPositiveButton("Открыть настройки", (dialog, which) -> {
                        try {
                            Intent intent = new Intent(Settings.ACTION_MANAGE_UNKNOWN_APP_SOURCES,
                                    Uri.parse("package:" + app.getPackageName()));
                            activity.startActivity(intent);
                        } catch (Throwable error) {
                            Log.w(TAG, "Could not open install-source settings", error);
                        }
                    })
                    .show();
            return;
        }
        preferences.edit().putBoolean("awaiting_unknown_sources", false).apply();
        try {
            installWithPackageInstaller(app, file);
        } catch (Throwable error) {
            Log.e(TAG, "Android installer session failed", error);
            Toast.makeText(app, "Не удалось открыть системный установщик. APK сохранён в данных приложения.", Toast.LENGTH_LONG).show();
        }
    }

    private static void installWithPackageInstaller(Context context, File file) throws Exception {
        PackageInstaller installer = context.getPackageManager().getPackageInstaller();
        PackageInstaller.SessionParams params = new PackageInstaller.SessionParams(PackageInstaller.SessionParams.MODE_FULL_INSTALL);
        params.setAppPackageName(context.getPackageName());
        int sessionId = installer.createSession(params);
        try (PackageInstaller.Session session = installer.openSession(sessionId);
             InputStream input = new FileInputStream(file);
             OutputStream output = session.openWrite("Telega-update.apk", 0, file.length())) {
            byte[] buffer = new byte[32768];
            int read;
            while ((read = input.read(buffer)) != -1) output.write(buffer, 0, read);
            session.fsync(output);
            Intent result = new Intent(context, TelegaInstallReceiver.class);
            result.putExtra("sessionId", sessionId);
            int flags = PendingIntent.FLAG_UPDATE_CURRENT;
            if (Build.VERSION.SDK_INT >= 31) flags |= PendingIntent.FLAG_MUTABLE;
            PendingIntent pending = PendingIntent.getBroadcast(context, sessionId, result, flags);
            session.commit(pending.getIntentSender());
        }
    }

    private static String toHex(byte[] bytes) {
        StringBuilder result = new StringBuilder(bytes.length * 2);
        for (byte b : bytes) result.append(String.format(Locale.US, "%02x", b & 0xff));
        return result.toString();
    }

    private static void openReleasePage(Context context, String url) {
        if (url == null || !url.startsWith("https://github.com/kirovo389-creator/Telegram/releases")) return;
        try {
            Intent intent = new Intent(Intent.ACTION_VIEW, Uri.parse(url));
            intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
            context.startActivity(intent);
        } catch (Throwable error) {
            Log.w(TAG, "Unable to open GitHub release page", error);
        }
    }
}
''', encoding="utf-8")

receiver = root / "messenger" / "TelegaInstallReceiver.java"
receiver.write_text(r'''package org.telegram.messenger;

import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.content.pm.PackageInstaller;
import android.os.Build;
import android.util.Log;
import android.widget.Toast;

/** Forwards PackageInstaller's pending-user-action intent to the system installer UI. */
public final class TelegaInstallReceiver extends BroadcastReceiver {
    @Override
    public void onReceive(Context context, Intent intent) {
        int status = intent.getIntExtra(PackageInstaller.EXTRA_STATUS, PackageInstaller.STATUS_FAILURE);
        if (status == PackageInstaller.STATUS_PENDING_USER_ACTION) {
            Intent confirmation = intent.getParcelableExtra(Intent.EXTRA_INTENT);
            if (confirmation != null) {
                confirmation.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
                try { context.startActivity(confirmation); }
                catch (Throwable error) { Log.e("TelegaOTA", "Could not open installer confirmation", error); }
            }
        } else if (status == PackageInstaller.STATUS_SUCCESS) {
            context.getSharedPreferences("telega_ota", Context.MODE_PRIVATE).edit().remove("pending_file").apply();
            Toast.makeText(context, "Обновление Telega установлено", Toast.LENGTH_LONG).show();
        } else {
            int detail = intent.getIntExtra(PackageInstaller.EXTRA_STATUS_MESSAGE, 0);
            Log.w("TelegaOTA", "Install failed, status=" + status + ", detail=" + detail);
            Toast.makeText(context, "Android не установил обновление. Проверь подпись APK и попробуй позже.", Toast.LENGTH_LONG).show();
        }
    }
}
''', encoding="utf-8")

source = launch.read_text(encoding="utf-8")
create_anchor = "    protected void onCreate(Bundle savedInstanceState) {"
if create_anchor not in source:
    print("ERROR: LaunchActivity.onCreate anchor not found", file=sys.stderr)
    sys.exit(1)
if "TelegaOtaUpdater.check(this)" not in source:
    start = source.find(create_anchor)
    end = source.find("\n    }", start)
    body = source[start:end]
    super_anchor = "        super.onCreate(savedInstanceState);"
    if start < 0 or end < 0 or super_anchor not in body:
        print("ERROR: LaunchActivity super.onCreate anchor not found", file=sys.stderr)
        sys.exit(1)
    body = body.replace(super_anchor, super_anchor + "\n        org.telegram.messenger.TelegaOtaUpdater.check(this);", 1)
    source = source[:start] + body + source[end:]

# Retry installation when returning from Android's per-app unknown-source settings.
if "TelegaOtaUpdater.installPending(this)" not in source:
    method_match = re.search(r"(?m)^    (?:public|protected) void onResume\\(\\)\\s*\\{", source)
    if not method_match:
        print("ERROR: LaunchActivity.onResume anchor not found", file=sys.stderr)
        sys.exit(1)
    start = method_match.start()
    end = source.find("\n    }", start)
    body = source[start:end]
    super_resume = "        super.onResume();"
    if end < 0 or super_resume not in body:
        print("ERROR: LaunchActivity super.onResume anchor not found", file=sys.stderr)
        sys.exit(1)
    body = body.replace(super_resume, super_resume + "\n        org.telegram.messenger.TelegaOtaUpdater.installPending(this);", 1)
    source = source[:start] + body + source[end:]
launch.write_text(source, encoding="utf-8")

xml = manifest.read_text(encoding="utf-8")
if "android.permission.INTERNET" not in xml:
    xml = re.sub(r"(<manifest\\b[^>]*>)", r'\\1\n    <uses-permission android:name="android.permission.INTERNET" />', xml, count=1)
if "android.permission.REQUEST_INSTALL_PACKAGES" not in xml:
    xml = re.sub(r'(    <uses-permission android:name="android\\.permission\\.INTERNET"\\s*/>)',
                 r'\\1\n    <uses-permission android:name="android.permission.REQUEST_INSTALL_PACKAGES" />', xml, count=1)
if "TelegaInstallReceiver" not in xml:
    app_close = xml.find("</application>")
    if app_close < 0:
        print("ERROR: AndroidManifest application closing tag not found", file=sys.stderr)
        sys.exit(1)
    xml = xml[:app_close] + '''
        <receiver
            android:name="org.telegram.messenger.TelegaInstallReceiver"
            android:enabled="true"
            android:exported="false" />
''' + xml[app_close:]
manifest.write_text(xml, encoding="utf-8")

print("GitHub Releases OTA download, integrity check, and user-confirmed PackageInstaller flow applied.")
