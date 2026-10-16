package org.telegram.messenger;

import android.app.Activity;
import org.telegram.ui.ActionBar.AlertDialog;
import android.app.PendingIntent;
import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.content.pm.PackageInstaller;
import android.content.pm.PackageInfo;
import android.content.pm.PackageManager;
import android.content.pm.Signature;
import android.net.Uri;
import android.os.Build;
import android.os.Environment;
import android.os.Handler;
import android.os.Looper;
import android.provider.Settings;
import android.util.Log;
import android.widget.Toast;
import android.view.View;
import android.view.Gravity;
import android.widget.LinearLayout;
import android.widget.ProgressBar;
import android.widget.TextView;

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
            "https://api.github.com/repos/kirovo389-creator/Telegram/releases/latest";
    private static final String RELEASE_PREFIX =
            "https://github.com/kirovo389-creator/Telegram/releases/download/";
    private static final String PREFS = "telega_ota";
    private static final long MAX_APK_BYTES = 300L * 1024L * 1024L;
    private static final ExecutorService EXECUTOR = Executors.newSingleThreadExecutor();
    private static final Handler MAIN = new Handler(Looper.getMainLooper());
    private static volatile boolean checkStarted;
    private static volatile long lastAttemptAt;
    private static final long MIN_CHECK_INTERVAL = 5L * 60L * 1000L;

    private TelegaOtaUpdater() {}

    private static SharedPreferences prefs(Context context) {
        return context.getApplicationContext().getSharedPreferences(PREFS, Context.MODE_PRIVATE);
    }


    public static boolean isEnabled(Context context) {
        return prefs(context).getBoolean("enabled", true);
    }

    public static void setEnabled(Context context, boolean enabled) {
        prefs(context).edit().putBoolean("enabled", enabled).apply();
        if (enabled && context instanceof Activity) check(context);
    }

    private static long parseVersionCode(String body) {
        if (body == null) return -1L;
        for (String line : body.split("\\n")) {
            String prefix = "Telega-Version-Code:";
            if (!line.startsWith(prefix)) continue;
            try {
                return Long.parseLong(line.substring(prefix.length()).trim());
            } catch (NumberFormatException ignored) {
                return -1L;
            }
        }
        return -1L;
    }

    private static long versionCodeFromTag(String tag) {
        if (tag == null) return -1L;
        String prefix;
        long versionBase;
        if (tag.startsWith("telega-v2-build-")) {
            prefix = "telega-v2-build-";
            versionBase = 7274L;
        } else if (tag.startsWith("telega-build-")) {
            prefix = "telega-build-";
            versionBase = 7175L;
        } else {
            return -1L;
        }
        try {
            long run = Long.parseLong(tag.substring(prefix.length()));
            return (versionBase + run) * 10L + 9L;
        } catch (NumberFormatException ignored) {
            return -1L;
        }
    }

    public static void check(Context activityContext) {
        if (!(activityContext instanceof Activity)) return;
        final Activity activity = (Activity) activityContext;
        final Context app = activity.getApplicationContext();
        if (!isEnabled(app)) return;
        synchronized (TelegaOtaUpdater.class) {
            long now = System.currentTimeMillis();
            if (checkStarted || now - lastAttemptAt < MIN_CHECK_INTERVAL) return;
            checkStarted = true;
            lastAttemptAt = now;
        }

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
                if (status != 200) {
                    Log.w(TAG, "GitHub Releases returned HTTP " + status
                            + (status == 403 ? " (rate limit or access restriction)" : ""));
                    return;
                }
                StringBuilder body = new StringBuilder();
                try (InputStream stream = connection.getInputStream();
                     BufferedInputStream input = new BufferedInputStream(stream)) {
                    byte[] buffer = new byte[8192];
                    int read;
                    while ((read = input.read(buffer)) != -1) body.append(new String(buffer, 0, read, "UTF-8"));
                }
                JSONObject release = new JSONObject(body.toString());

                PackageInfo installedInfo;
                String installedVersionName;
                long installedVersionCode;
                try {
                    installedInfo = app.getPackageManager().getPackageInfo(app.getPackageName(), 0);
                    installedVersionName = installedInfo.versionName == null ? "" : installedInfo.versionName;
                    installedVersionCode = Build.VERSION.SDK_INT >= 28
                            ? installedInfo.getLongVersionCode() : installedInfo.versionCode;
                } catch (Throwable error) {
                    Log.w(TAG, "Unable to read installed version", error);
                    return;
                }

                String tag = release.optString("tag_name", "");
                if (tag.isEmpty() || release.optBoolean("draft", false) || release.optBoolean("prerelease", false)) return;
                long candidateVersionCode = parseVersionCode(release.optString("body", ""));
                if (candidateVersionCode <= 0) candidateVersionCode = versionCodeFromTag(tag);
                if (tag.equals(installedVersionName) && candidateVersionCode <= 0) return;
                if (candidateVersionCode <= installedVersionCode) return;

                JSONArray assets = release.optJSONArray("assets");
                if (assets == null) return;
                JSONObject apkAsset = null;
                for (int j = 0; j < assets.length(); j++) {
                    JSONObject asset = assets.optJSONObject(j);
                    if (asset == null) continue;
                    String assetName = asset.optString("name", "");
                    if (assetName.equalsIgnoreCase("Telega-Beta.apk")
                            || assetName.equalsIgnoreCase("Telega-debug.apk")
                            || assetName.equalsIgnoreCase("Telega.apk")) {
                        apkAsset = asset;
                        break;
                    }
                }
                if (apkAsset == null) return;
                String url = apkAsset.optString("browser_download_url", "");
                if (!url.startsWith(RELEASE_PREFIX)) return;
                JSONObject newest = new JSONObject(release.toString());
                newest.put("_telega_apk_url", url);
                newest.put("_telega_version_code", candidateVersionCode);
                newest.put("_telega_size", apkAsset.optLong("size", -1));
                newest.put("_telega_digest", apkAsset.optString("digest", ""));
                String deferredTag = prefs(app).getString("deferred_tag", "");
                long deferredAt = prefs(app).getLong("deferred_at", 0L);
                if (tag.equals(deferredTag)
                        && System.currentTimeMillis() - deferredAt < 6L * 60L * 60L * 1000L) return;
                JSONObject found = newest;
                MAIN.post(() -> {
                    if (!activity.isFinishing() && !activity.isDestroyed()) showUpdateDialog(activity, app, found);
                });
            } catch (Throwable error) {
                Log.d(TAG, "GitHub update check failed; current app remains usable", error);
            } finally {
                if (connection != null) connection.disconnect();
                synchronized (TelegaOtaUpdater.class) {
                    checkStarted = false;
                }
            }
        });
    }

    private static void showUpdateDialog(Activity activity, Context app, JSONObject release) {
        try {
            String tag = release.optString("tag_name", "new version");
            String notes = release.optString("body", "");
            notes = notes.replaceAll("(?m)^Telega-Version-Code:.*(?:\\R|$)", "").trim();
            if (notes.length() > 700) notes = notes.substring(0, 700) + "…";
            long expectedSize = release.optLong("_telega_size", -1);
            String sizeLabel = expectedSize > 0
                    ? String.format(Locale.US, "%.2f MB", expectedSize / (1024.0 * 1024.0))
                    : "неизвестен";
            String message = "Доступна новая версия Telega Beta: " + tag
                    + "\n\n" + (notes.isEmpty() ? "Исправления и улучшения." : notes)
                    + "\n\nРазмер APK: " + sizeLabel
                    + "\n\nДля установки Android может запросить разрешение. Подтверди установку в системном окне.";
            String url = release.optString("_telega_apk_url", "");
            String digest = release.optString("_telega_digest", "");
            new AlertDialog.Builder(activity)
                    .setTitle("Обновление Telega")
                    .setMessage(message)
                    .setNegativeButton("Позже", (dialog, which) ->
                            prefs(app).edit().putString("deferred_tag", tag)
                                    .putLong("deferred_at", System.currentTimeMillis()).apply())
                    .setPositiveButton("Обновить", (dialog, which) ->
                            downloadApk(activity, url, digest, expectedSize, tag))
                    .show();
        } catch (Throwable error) {
            Log.w(TAG, "Unable to show update dialog", error);
        }
    }

    private static void downloadApk(Activity activity, String url, String digest, long expectedSize, String tag) {
        if (url == null || !url.startsWith(RELEASE_PREFIX)) return;
        final LinearLayout progressContent = new LinearLayout(activity);
        progressContent.setOrientation(LinearLayout.VERTICAL);
        progressContent.setPadding(AndroidUtilities.dp(24), AndroidUtilities.dp(8), AndroidUtilities.dp(24), AndroidUtilities.dp(12));
        TextView progressLabel = new TextView(activity);
        progressLabel.setText("Загрузка обновления Telega");
        progressLabel.setTextSize(15);
        progressLabel.setTextColor(org.telegram.ui.ActionBar.Theme.getColor(org.telegram.ui.ActionBar.Theme.key_dialogTextBlack));
        progressContent.addView(progressLabel, new LinearLayout.LayoutParams(-1, -2));
        ProgressBar progressBar = new ProgressBar(activity, null, android.R.attr.progressBarStyleHorizontal);
        progressBar.setIndeterminate(true);
        LinearLayout.LayoutParams barParams = new LinearLayout.LayoutParams(-1, AndroidUtilities.dp(4));
        barParams.topMargin = AndroidUtilities.dp(18);
        progressContent.addView(progressBar, barParams);
        TextView progressDetail = new TextView(activity);
        progressDetail.setText("Подготавливаем загрузку…");
        progressDetail.setTextSize(13);
        progressDetail.setTextColor(org.telegram.ui.ActionBar.Theme.getColor(org.telegram.ui.ActionBar.Theme.key_dialogTextBlack));
        LinearLayout.LayoutParams detailParams = new LinearLayout.LayoutParams(-1, -2);
        detailParams.topMargin = AndroidUtilities.dp(10);
        progressContent.addView(progressDetail, detailParams);
        final AlertDialog progress = new AlertDialog.Builder(activity)
                .setTitle("Обновление Telega")
                .setView(progressContent)
                .create();
        progress.setCancelable(false);
        progress.setCanceledOnTouchOutside(false);
        try {
            progress.show();
        } catch (Throwable error) {
            Log.w(TAG, "Unable to show download progress", error);
            return;
        }
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
                final long totalBytes = declared > 0 ? declared : expectedSize;
                if (declared > MAX_APK_BYTES || expectedSize > MAX_APK_BYTES) throw new IllegalStateException("APK exceeds allowed size");
                if (totalBytes > 0) {
                    MAIN.post(() -> {
                        try {
                            if (progress.isShowing()) {
                                progressBar.setIndeterminate(false);
                                progressBar.setMax(100);
                                progressDetail.setText("Скачано 0%");
                            }
                        } catch (Throwable ignored) {}
                    });
                }
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
                        if (totalBytes > 0) {
                            final int percent = (int) Math.min(100L, (written * 100L) / totalBytes);
                            MAIN.post(() -> {
                                try {
                                    if (progress.isShowing()) { progressBar.setProgress(percent); progressDetail.setText("Загрузка APK — " + percent + "%"); }
                                } catch (Throwable ignored) {}
                            });
                        }
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
                    dismissProgress(progress);
                    Toast.makeText(app, "APK загружен. Проверяю пакет и готовлю установку…", Toast.LENGTH_LONG).show();
                    if (!activity.isFinishing() && !activity.isDestroyed()) installPending(activity);
                });
            } catch (Throwable error) {
                if (apk != null) apk.delete();
                Log.e(TAG, "Update download/verification failed", error);
                MAIN.post(() -> {
                    dismissProgress(progress);
                    Toast.makeText(app, "Не удалось загрузить обновление. Текущая версия сохранена.", Toast.LENGTH_LONG).show();
                });
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
                    .setMessage("Разреши Telega устанавливать обновления из этого источника. Android откроет системный экран разрешений.")
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
            preferences.edit().remove("pending_file").remove("pending_tag")
                    .putBoolean("awaiting_unknown_sources", false).apply();
            // Do not leave a failed update APK behind in app storage.
            //noinspection ResultOfMethodCallIgnored
            file.delete();
            String reason = error.getMessage() == null ? "" : error.getMessage();
            String userMessage;
            if (reason.contains("Подпись загруженного APK")) {
                userMessage = "Не удалось обновить Telega: подпись APK отличается от установленной версии. Не удаляй приложение, иначе можно потерять локальные данные; нужна сборка с прежним ключом подписи.";
            } else if (reason.contains("not newer than the installed version")) {
                userMessage = "Эта версия Telega уже установлена или APK старее. Проверь, есть ли более новое обновление.";
            } else if (reason.contains("package does not match")) {
                userMessage = "Этот APK собран для другого варианта Telega. Установка отменена.";
            } else {
                userMessage = "Не удалось подготовить установку обновления. Проверь свободное место и повтори попытку.";
            }
            Toast.makeText(app, userMessage, Toast.LENGTH_LONG).show();
        }
    }

    private static void installWithPackageInstaller(Context context, File file) throws Exception {
        android.content.pm.PackageInfo archiveInfo = context.getPackageManager().getPackageArchiveInfo(file.getAbsolutePath(), 0);
        if (archiveInfo == null || !context.getPackageName().equals(archiveInfo.packageName)) {
            throw new SecurityException("Downloaded APK package does not match the installed Telega variant");
        }
        long archiveVersion = Build.VERSION.SDK_INT >= 28
                ? archiveInfo.getLongVersionCode() : archiveInfo.versionCode;
        PackageInfo installedInfo = context.getPackageManager().getPackageInfo(context.getPackageName(), 0);
        long installedVersion = Build.VERSION.SDK_INT >= 28
                ? installedInfo.getLongVersionCode() : installedInfo.versionCode;
        if (archiveVersion <= installedVersion) {
            throw new IllegalStateException("Downloaded APK is not newer than the installed version");
        }
        if (!hasSameSigningCertificate(context, file)) {
            throw new SecurityException("Подпись загруженного APK отличается от установленной версии. Android не разрешит обновление поверх неё.");
        }
        PackageInstaller installer = context.getPackageManager().getPackageInstaller();
        PackageInstaller.SessionParams params = new PackageInstaller.SessionParams(PackageInstaller.SessionParams.MODE_FULL_INSTALL);
        params.setAppPackageName(context.getPackageName());
        params.setSize(file.length());
        int sessionId = installer.createSession(params);
        try (PackageInstaller.Session session = installer.openSession(sessionId)) {
            // Close the APK output stream before commit. Committing while the
            // session's write stream is still open can make PackageInstaller
            // reject an otherwise completely downloaded APK.
            try (InputStream input = new FileInputStream(file);
                 OutputStream output = session.openWrite("Telega-update.apk", 0, file.length())) {
                byte[] buffer = new byte[32768];
                int read;
                while ((read = input.read(buffer)) != -1) output.write(buffer, 0, read);
                session.fsync(output);
            }
            Intent result = new Intent(context, TelegaInstallReceiver.class);
            result.putExtra("sessionId", sessionId);
            int flags = PendingIntent.FLAG_UPDATE_CURRENT;
            if (Build.VERSION.SDK_INT >= 31) flags |= PendingIntent.FLAG_MUTABLE;
            PendingIntent pending = PendingIntent.getBroadcast(context, sessionId, result, flags);
            session.commit(pending.getIntentSender());
        } catch (Exception error) {
            try {
                installer.abandonSession(sessionId);
            } catch (Throwable ignored) {
            }
            throw error;
        }
    }


    private static boolean hasSameSigningCertificate(Context context, File apk) throws Exception {
        PackageManager manager = context.getPackageManager();
        int flags = Build.VERSION.SDK_INT >= 28
                ? PackageManager.GET_SIGNING_CERTIFICATES : PackageManager.GET_SIGNATURES;
        PackageInfo installed = manager.getPackageInfo(context.getPackageName(), flags);
        PackageInfo downloaded = manager.getPackageArchiveInfo(apk.getAbsolutePath(), flags);
        if (downloaded == null) return false;
        Signature[] installedSignatures;
        Signature[] downloadedSignatures;
        if (Build.VERSION.SDK_INT >= 28) {
            if (installed.signingInfo == null || downloaded.signingInfo == null) return false;
            installedSignatures = installed.signingInfo.getApkContentsSigners();
            downloadedSignatures = downloaded.signingInfo.getApkContentsSigners();
        } else {
            installedSignatures = installed.signatures;
            downloadedSignatures = downloaded.signatures;
        }
        if (installedSignatures == null || downloadedSignatures == null
                || installedSignatures.length == 0
                || installedSignatures.length != downloadedSignatures.length) {
            return false;
        }
        java.util.Arrays.sort(installedSignatures, (a, b) -> a.toCharsString().compareTo(b.toCharsString()));
        java.util.Arrays.sort(downloadedSignatures, (a, b) -> a.toCharsString().compareTo(b.toCharsString()));
        for (int i = 0; i < installedSignatures.length; i++) {
            if (!installedSignatures[i].equals(downloadedSignatures[i])) return false;
        }
        return true;
    }

    private static void dismissProgress(AlertDialog progress) {
        try {
            if (progress != null && progress.isShowing()) progress.dismiss();
        } catch (Throwable ignored) {}
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
