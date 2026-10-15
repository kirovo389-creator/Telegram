#!/usr/bin/env python3
"""Harden the generated OTA implementation after the upstream Telega patches run."""
from pathlib import Path
import re
import sys

root = Path("TMessagesProj/src/main/java/org/telegram")
updater = root / "messenger" / "TelegaOtaUpdater.java"
launch = root / "ui" / "LaunchActivity.java"
settings = root / "ui" / "TelegaSettingsActivity.java"
for path in (updater, launch, settings):
    if not path.exists():
        sys.exit(f"ERROR: required source file missing: {path}")

def require_replace(text, old, new, name):
    if text.count(old) != 1:
        sys.exit(f"ERROR: expected exactly one {name} anchor, got {text.count(old)}")
    return text.replace(old, new, 1)

u = updater.read_text(encoding="utf-8")
u = u.replace("import android.app.PendingIntent;", "import android.app.PendingIntent;\nimport android.app.ProgressDialog;", 1)
if "import android.content.pm.PackageInfo;" not in u:
    u = u.replace("import android.content.pm.PackageInstaller;", "import android.content.pm.PackageInstaller;\nimport android.content.pm.PackageInfo;", 1)
u = u.replace('"https://api.github.com/repos/kirovo389-creator/Telegram/releases?per_page=10"',
              '"https://api.github.com/repos/kirovo389-creator/Telegram/releases/latest"', 1)
u = u.replace("    private static final long CHECK_INTERVAL = 6L * 60L * 60L * 1000L;\n", "", 1)
if "private static volatile boolean checkStarted;" not in u:
    u = require_replace(u, "    private static final Handler MAIN = new Handler(Looper.getMainLooper());",
                        "    private static final Handler MAIN = new Handler(Looper.getMainLooper());\n    private static volatile boolean checkStarted;\n    private static volatile long lastAttemptAt;\n    private static final long MIN_CHECK_INTERVAL = 5L * 60L * 1000L;", "process check guard")

old_gate = """        final Activity activity = (Activity) activityContext;
        final Context app = activity.getApplicationContext();
        if (System.currentTimeMillis() - prefs(app).getLong("last_check", 0) < CHECK_INTERVAL) return;

        EXECUTOR.execute(() -> {"""
new_gate = """        final Activity activity = (Activity) activityContext;
        final Context app = activity.getApplicationContext();
        if (!isEnabled(app)) return;
        synchronized (TelegaOtaUpdater.class) {
            long now = System.currentTimeMillis();
            if (checkStarted || now - lastAttemptAt < MIN_CHECK_INTERVAL) return;
            checkStarted = true;
            lastAttemptAt = now;
        }

        EXECUTOR.execute(() -> {"""
u = require_replace(u, old_gate, new_gate, "cold-start check gate")
u = u.replace('''                if (status != 200) return;''', '''                if (status != 200) {
                    Log.w(TAG, "GitHub Releases returned HTTP " + status
                            + (status == 403 ? " (rate limit or access restriction)" : ""));
                    return;
                }''', 1)
u = u.replace('''                prefs(app).edit().putLong("last_check", System.currentTimeMillis()).apply();
                JSONArray releases = new JSONArray(body.toString());''',
              '''                JSONObject release = new JSONObject(body.toString());''', 1)

start = u.find("                long installedVersion;")
end = u.find("                JSONObject found = newest;", start)
if start < 0 or end < 0:
    sys.exit("ERROR: cannot find the current release/version selection block")
version_block = r"""                PackageInfo installedInfo;
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
                if (tag.equals(prefs(app).getString("dismissed_tag", ""))) return;
"""
u = u[:start] + version_block + u[end:]

helpers = r"""
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

"""
if "public static boolean isEnabled(Context context)" not in u:
    u = require_replace(u, "    public static void check(Context activityContext) {",
                        helpers + "    public static void check(Context activityContext) {", "OTA preferences and version helpers")

old_dialog = r'''            String tag = release.optString("tag_name", "new version");
            String notes = release.optString("body", "");
            if (notes.length() > 700) notes = notes.substring(0, 700) + "…";
            String message = "Доступна новая версия Telega Beta: " + tag
                    + "\n\n" + (notes.isEmpty() ? "Исправления и улучшения." : notes)
                    + "\n\nAPK будет загружен из GitHub Releases. Для установки Android может запросить разрешение. Системный диалог установки нужно подтвердить.";
            String url = release.optString("_telega_apk_url", "");
            String digest = release.optString("_telega_digest", "");
            long expectedSize = release.optLong("_telega_size", -1);'''
new_dialog = r'''            String tag = release.optString("tag_name", "new version");
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
                    + "\n\nAPK будет загружен из GitHub Releases. Для установки Android может запросить разрешение. Системный диалог установки нужно подтвердить.";
            String url = release.optString("_telega_apk_url", "");
            String digest = release.optString("_telega_digest", "");'''
u = require_replace(u, old_dialog, new_dialog, "update dialog")

u = require_replace(u, '''        if (url == null || !url.startsWith(RELEASE_PREFIX)) return;
        Toast.makeText(activity, "Загружаю обновление Telega…", Toast.LENGTH_SHORT).show();
        final Context app = activity.getApplicationContext();''',
'''        if (url == null || !url.startsWith(RELEASE_PREFIX)) return;
        final ProgressDialog progress = new ProgressDialog(activity);
        progress.setTitle("Обновление Telega");
        progress.setMessage("Загрузка APK из GitHub Releases…");
        progress.setProgressStyle(ProgressDialog.STYLE_HORIZONTAL);
        progress.setIndeterminate(true);
        progress.setCancelable(false);
        try {
            progress.show();
        } catch (Throwable error) {
            Log.w(TAG, "Unable to show download progress", error);
            return;
        }
        final Context app = activity.getApplicationContext();''', "download progress dialog")
u = require_replace(u, '''                long declared = connection.getContentLengthLong();
                if (declared > MAX_APK_BYTES || expectedSize > MAX_APK_BYTES) throw new IllegalStateException("APK exceeds allowed size");''',
'''                long declared = connection.getContentLengthLong();
                final long totalBytes = declared > 0 ? declared : expectedSize;
                if (declared > MAX_APK_BYTES || expectedSize > MAX_APK_BYTES) throw new IllegalStateException("APK exceeds allowed size");
                if (totalBytes > 0) {
                    MAIN.post(() -> {
                        try {
                            if (progress.isShowing()) {
                                progress.setIndeterminate(false);
                                progress.setMax(100);
                            }
                        } catch (Throwable ignored) {}
                    });
                }''', "progress byte count")
u = require_replace(u, '''                        sha.update(buffer, 0, count);
                        output.write(buffer, 0, count);
                    }''',
'''                        sha.update(buffer, 0, count);
                        output.write(buffer, 0, count);
                        if (totalBytes > 0) {
                            final int percent = (int) Math.min(100L, (written * 100L) / totalBytes);
                            MAIN.post(() -> {
                                try {
                                    if (progress.isShowing()) progress.setProgress(percent);
                                } catch (Throwable ignored) {}
                            });
                        }
                    }''', "progress increment")
u = require_replace(u, '''                MAIN.post(() -> {
                    Toast.makeText(app, "Обновление загружено. Подготавливаю установку…", Toast.LENGTH_LONG).show();
                    installPending(activity);
                });''',
'''                MAIN.post(() -> {
                    dismissProgress(progress);
                    Toast.makeText(app, "Обновление загружено. Подготавливаю установку…", Toast.LENGTH_LONG).show();
                    if (!activity.isFinishing() && !activity.isDestroyed()) installPending(activity);
                });''', "download success")
u = require_replace(u, '''                MAIN.post(() -> Toast.makeText(app, "Не удалось загрузить обновление. Текущая версия сохранена.", Toast.LENGTH_LONG).show());''',
'''                MAIN.post(() -> {
                    dismissProgress(progress);
                    Toast.makeText(app, "Не удалось загрузить обновление. Текущая версия сохранена.", Toast.LENGTH_LONG).show();
                });''', "download error")
if "private static void dismissProgress(ProgressDialog progress)" not in u:
    u = require_replace(u, "    private static String toHex(byte[] bytes) {",
'''    private static void dismissProgress(ProgressDialog progress) {
        try {
            if (progress != null && progress.isShowing()) progress.dismiss();
        } catch (Throwable ignored) {}
    }

    private static String toHex(byte[] bytes) {''', "progress dismissal")

u = u.replace("""            } finally {
                if (connection != null) connection.disconnect();
            }""",
"""            } finally {
                if (connection != null) connection.disconnect();
                synchronized (TelegaOtaUpdater.class) {
                    checkStarted = false;
                }
            }""", 1)
u = require_replace(u, '''                if (tag.equals(prefs(app).getString("dismissed_tag", ""))) return;''',
'''                String deferredTag = prefs(app).getString("deferred_tag", "");
                long deferredAt = prefs(app).getLong("deferred_at", 0L);
                if (tag.equals(deferredTag)
                        && System.currentTimeMillis() - deferredAt < 6L * 60L * 60L * 1000L) return;''',
"defer previously postponed update")
u = require_replace(u, '''                    .setNegativeButton("Позже", (dialog, which) ->
                            prefs(app).edit().putString("dismissed_tag", tag).apply())''',
'''                    .setNegativeButton("Позже", (dialog, which) ->
                            prefs(app).edit().putString("deferred_tag", tag)
                                    .putLong("deferred_at", System.currentTimeMillis()).apply())''',
"remember Later choice for six hours")

# Keep all OTA prompts inside Telegram's themed dialog system and avoid exposing
# GitHub implementation details in user-facing copy.
u = u.replace("import android.app.AlertDialog;", "import org.telegram.ui.ActionBar.AlertDialog;", 1)
u = u.replace("APK будет загружен из GitHub Releases. Для установки Android может запросить разрешение. Системный диалог установки нужно подтвердить.",
              "Для установки Android может запросить разрешение. Подтверди установку в системном окне.")
u = u.replace('progress.setMessage("Загрузка APK из GitHub Releases…");',
              'progress.setMessage("Скачивание новой версии…");')
u = u.replace('''                    .setNeutralButton("Релиз", (dialog, which) ->
                            openReleasePage(activity, release.optString("html_url",
                                    "https://github.com/kirovo389-creator/Telegram/releases")))
''', "")
u = u.replace('.setPositiveButton("Скачать и установить",', '.setPositiveButton("Обновить",')
u = u.replace("Чтобы установить APK из GitHub Releases, разреши Telega устанавливать обновления из этого источника. Android покажет системный экран разрешений.",
              "Разреши Telega устанавливать обновления из этого источника. Android откроет системный экран разрешений.")
# The settings row is part of this patch's generated source, so keep its copy provider-neutral too.
settings_text = settings.read_text(encoding="utf-8")
settings_text = settings_text.replace(
    "Проверять GitHub Releases при каждом запуске приложения и предлагать установить новую версию.",
    "Проверять наличие новой версии при запуске приложения и предлагать установить обновление."
)
settings.write_text(settings_text, encoding="utf-8")

updater.write_text(u, encoding="utf-8")

l = launch.read_text(encoding="utf-8")
l = re.sub(r"(?m)^[ \t]*org\.telegram\.messenger\.TelegaOtaUpdater\.check\(this\);\n", "", l)
resume_match = re.search(r"(?m)^    (?:public|protected) void onResume\(\)\s*\{", l)
if not resume_match:
    sys.exit("ERROR: LaunchActivity.onResume not found")
resume_end = l.find("\n    }", resume_match.start())
if resume_end < 0:
    sys.exit("ERROR: LaunchActivity.onResume body end not found")
resume_body = l[resume_match.start():resume_end]
super_resume = "        super.onResume();"
if super_resume not in resume_body:
    sys.exit("ERROR: LaunchActivity super.onResume anchor not found")
resume_body = resume_body.replace(super_resume, super_resume + "\n        getWindow().getDecorView().postDelayed(() -> org.telegram.messenger.TelegaOtaUpdater.check(this), 2500);", 1)
l = l[:resume_match.start()] + resume_body + l[resume_end:]
if l.count("TelegaOtaUpdater.check(this)") != 1:
    sys.exit("ERROR: OTA check must be wired exactly once")
launch.write_text(l, encoding="utf-8")

s = settings.read_text(encoding="utf-8")
if "import org.telegram.messenger.TelegaOtaUpdater;" not in s:
    s = s.replace("import org.telegram.messenger.TelegaFeatures;",
                  "import org.telegram.messenger.TelegaFeatures;\nimport org.telegram.messenger.TelegaOtaUpdater;", 1)
if 'addToggle(context, list, "Автообновление"' not in s:
    anchor = '        addToggle(context, list, "Auto Archive",'
    row = '''        addToggle(context, list, "Автообновление",
                "Проверять GitHub Releases при каждом запуске приложения и предлагать установить новую версию.",
                TelegaOtaUpdater.isEnabled(context),
                (button, enabled) -> TelegaOtaUpdater.setEnabled(context, enabled));

'''
    s = require_replace(s, anchor, row + anchor, "OTA settings toggle")
settings.write_text(s, encoding="utf-8")

print("OTA patch hardened: latest release API, cold-start checks, version metadata, download progress and settings toggle.")
