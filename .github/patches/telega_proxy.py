#!/usr/bin/env python3
"""Add opt-in Auto Proxy that scans the public ProxyMTProto channel and manages MTProto proxies."""
from pathlib import Path
import sys

root = Path("TMessagesProj/src/main/java/org/telegram")
settings = root / "ui" / "TelegaSettingsActivity.java"
launch = root / "ui" / "LaunchActivity.java"
if not settings.exists() or not launch.exists():
    print("ERROR: Telega settings or LaunchActivity is missing; run telega_features.py and telega_ota.py first", file=sys.stderr)
    sys.exit(1)

helper = root / "messenger" / "TelegaAutoProxy.java"
helper.write_text(r'''package org.telegram.messenger;

import android.content.Context;
import android.content.SharedPreferences;
import android.net.Uri;
import android.text.TextUtils;
import android.util.Log;

import org.telegram.tgnet.ConnectionsManager;

import java.io.BufferedReader;
import java.io.InputStream;
import java.io.InputStreamReader;
import java.lang.reflect.Constructor;
import java.lang.reflect.Field;
import java.lang.reflect.Method;
import java.lang.reflect.Proxy;
import java.net.HttpURLConnection;
import java.net.URL;
import java.net.URLDecoder;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.ArrayList;
import java.util.HashSet;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Locale;
import java.util.Set;
import java.util.concurrent.Executors;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.ScheduledFuture;
import java.util.concurrent.TimeUnit;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

/** Opt-in MTProto auto-proxy watcher for the public @ProxyMTProto channel. */
public final class TelegaAutoProxy {
    private static final String TAG = "TelegaAutoProxy";
    private static final String PREFS = "telega_auto_proxy";
    private static final String CHANNEL = "https://t.me/s/ProxyMTProto";
    private static final Pattern LINKS = Pattern.compile(
            "(?i)(?:https?://t\\.me/proxy\\?[^\\\"'<>\\s]+|tg://proxy\\?[^\\\"'<>\\s]+)");
    private static final ScheduledExecutorService EXECUTOR = Executors.newSingleThreadScheduledExecutor();
    private static ScheduledFuture<?> future;

    private TelegaAutoProxy() {}

    private static SharedPreferences prefs() {
        return ApplicationLoader.applicationContext.getSharedPreferences(PREFS, Context.MODE_PRIVATE);
    }

    public static boolean isEnabled() {
        return prefs().getBoolean("enabled", false);
    }

    public static synchronized void setEnabled(Context context, boolean enabled) {
        prefs().edit().putBoolean("enabled", enabled).apply();
        if (enabled) start(context);
        else if (future != null) {
            future.cancel(true);
            future = null;
        }
    }

    public static synchronized void init(Context context) {
        if (isEnabled()) start(context);
    }

    private static synchronized void start(Context context) {
        if (context == null || future != null && !future.isCancelled()) return;
        Context app = context.getApplicationContext();
        future = EXECUTOR.scheduleWithFixedDelay(() -> {
            if (!isEnabled()) return;
            scan(app);
            checkStoredProxies(app);
        }, 0, 30, TimeUnit.MINUTES);
    }

    private static void scan(Context context) {
        HttpURLConnection connection = null;
        try {
            connection = (HttpURLConnection) new URL(CHANNEL).openConnection();
            connection.setConnectTimeout(10000);
            connection.setReadTimeout(12000);
            connection.setRequestProperty("User-Agent", "Mozilla/5.0 (Linux; Android) TelegaBeta");
            connection.setRequestProperty("Accept", "text/html");
            int status = connection.getResponseCode();
            if (status != 200) return;
            StringBuilder html = new StringBuilder();
            try (InputStream stream = connection.getInputStream();
                 BufferedReader reader = new BufferedReader(new InputStreamReader(stream, StandardCharsets.UTF_8))) {
                String line;
                while ((line = reader.readLine()) != null) html.append(line);
            }
            String page = html.toString().replace("&amp;", "&").replace("&#38;", "&");
            Matcher matcher = LINKS.matcher(page);
            LinkedHashSet<String> found = new LinkedHashSet<>();
            while (matcher.find() && found.size() < 20) {
                ProxyEntry entry = parseLink(matcher.group());
                if (entry != null) found.add(entry.key());
            }
            if (found.isEmpty()) return;

            Set<String> known = new HashSet<>(prefs().getStringSet("known", new HashSet<>()));
            ArrayList<String> fresh = new ArrayList<>();
            for (String key : found) {
                if (!known.contains(key)) fresh.add(key);
            }
            if (fresh.isEmpty()) return;

            // Add the newest link first, then stop: the page is ordered newest-first.
            for (String key : fresh) {
                ProxyEntry entry = parseKey(key);
                if (entry == null) continue;
                addToNativeProxyList(entry);
                known.add(key);
                prefs().edit().putStringSet("known", new HashSet<>(known))
                        .putInt("fail_" + hash(key), 0).apply();
                activate(entry);
                checkProxy(entry, 0);
                break;
            }
        } catch (Throwable error) {
            Log.d(TAG, "Proxy channel check failed; existing connection is left unchanged", error);
        } finally {
            if (connection != null) connection.disconnect();
        }
    }

    private static ProxyEntry parseLink(String link) {
        try {
            Uri uri = Uri.parse(link);
            String server = uri.getQueryParameter("server");
            String portText = uri.getQueryParameter("port");
            String secret = uri.getQueryParameter("secret");
            if (TextUtils.isEmpty(server) || TextUtils.isEmpty(portText) || TextUtils.isEmpty(secret)) return null;
            int port = Integer.parseInt(portText);
            if (port < 1 || port > 65535 || secret.length() < 8 || secret.length() > 512) return null;
            server = URLDecoder.decode(server, "UTF-8").trim();
            secret = URLDecoder.decode(secret, "UTF-8").trim();
            if (server.isEmpty() || server.equalsIgnoreCase("unknown")) return null;
            return new ProxyEntry(server, port, secret);
        } catch (Throwable ignore) {
            return null;
        }
    }

    private static ProxyEntry parseKey(String key) {
        String[] parts = key.split("\\|", 3);
        if (parts.length != 3) return null;
        try { return new ProxyEntry(parts[0], Integer.parseInt(parts[1]), parts[2]); }
        catch (Throwable ignore) { return null; }
    }

    private static void addToNativeProxyList(ProxyEntry entry) {
        try {
            Class<?> settingsClass = Class.forName("org.telegram.proxy.ProxySettings");
            Object builder = settingsClass.getMethod("builder").invoke(null);
            invokeBuilder(builder, "setAddress", String.class, entry.server);
            invokeBuilder(builder, "setPort", int.class, entry.port);
            invokeBuilder(builder, "setUser", String.class, "");
            invokeBuilder(builder, "setPassword", String.class, "");
            invokeBuilder(builder, "setSecret", String.class, entry.secret);
            try {
                Class<?> typeClass = null;
                for (Class<?> nested : settingsClass.getDeclaredClasses()) {
                    if (nested.isEnum() && nested.getSimpleName().equals("Type")) typeClass = nested;
                }
                if (typeClass != null) {
                    @SuppressWarnings({"rawtypes", "unchecked"})
                    Object mtproto = Enum.valueOf((Class<? extends Enum>) typeClass, "MTPROTO");
                    Method setType = builder.getClass().getMethod("setType", typeClass);
                    setType.invoke(builder, mtproto);
                }
            } catch (Throwable ignored) {}

            Object settings = builder.getClass().getMethod("build").invoke(builder);
            Class<?> infoClass = Class.forName("org.telegram.messenger.SharedConfig$ProxyInfo");
            Object info = infoClass.getConstructor(settingsClass).newInstance(settings);
            Field listField = Class.forName("org.telegram.messenger.SharedConfig").getField("proxyList");
            Object value = listField.get(null);
            if (value instanceof List) {
                @SuppressWarnings("unchecked") List<Object> list = (List<Object>) value;
                synchronized (list) {
                    if (!containsProxy(list, entry)) list.add(info);
                }
            }
            try { Class.forName("org.telegram.messenger.SharedConfig").getMethod("saveConfig").invoke(null); }
            catch (Throwable ignored) {}
        } catch (Throwable error) {
            Log.w(TAG, "Could not mirror the proxy into Telegram's in-memory list; active connection still uses the proxy", error);
        }
    }

    private static void invokeBuilder(Object builder, String methodName, Class<?> argType, Object value) throws Exception {
        Method method = builder.getClass().getMethod(methodName, argType);
        method.invoke(builder, value);
    }

    private static boolean containsProxy(List<Object> list, ProxyEntry target) {
        for (Object info : list) {
            try {
                Object settings = fieldValue(info, "settings");
                String address = null;
                int port = -1;
                String secret = "";
                if (settings != null) {
                    address = stringMethod(settings, "getAddress");
                    Object portValue = method(settings, "getPort");
                    if (portValue instanceof Number) port = ((Number) portValue).intValue();
                    secret = stringMethod(settings, "getSecret");
                }
                if (address == null) {
                    address = stringField(info, "address");
                    port = intField(info, "port");
                    secret = stringField(info, "secret");
                }
                if (target.server.equals(address) && target.port == port && target.secret.equals(secret)) return true;
            } catch (Throwable ignored) {}
        }
        return false;
    }

    private static void activate(ProxyEntry entry) {
        try {
            SharedPreferences main = ApplicationLoader.applicationContext.getSharedPreferences("mainconfig", Context.MODE_PRIVATE);
            main.edit().putString("proxy_ip", entry.server).putString("proxy_pass", "")
                    .putString("proxy_user", "").putInt("proxy_port", entry.port)
                    .putString("proxy_secret", entry.secret).putBoolean("proxy_enabled", true)
                    .putBoolean("proxy_enabled_calls", false).apply();

            // Keep compatibility with old and new proxy-settings API versions.
            Class<?> manager = Class.forName("org.telegram.tgnet.ConnectionsManager");
            for (Method method : manager.getMethods()) {
                if (!method.getName().equals("setProxySettings") || method.getParameterTypes().length != 6) continue;
                method.invoke(null, true, entry.server, entry.port, "", "", entry.secret);
                break;
            }
            try {
                Class<?> nc = Class.forName("org.telegram.messenger.NotificationCenter");
                int event = nc.getField("proxySettingsChanged").getInt(null);
                Object global = nc.getMethod("getGlobalInstance").invoke(null);
                for (Method m : nc.getMethods()) {
                    if (m.getName().equals("postNotificationName") && m.getParameterTypes().length == 1) {
                        m.invoke(global, event);
                        break;
                    }
                }
            } catch (Throwable ignored) {}
            Log.i(TAG, "Activated newly found MTProto proxy " + entry.server + ":" + entry.port);
        } catch (Throwable error) {
            Log.w(TAG, "Unable to activate imported MTProto proxy", error);
        }
    }

    private static void checkStoredProxies(Context context) {
        Set<String> known = new HashSet<>(prefs().getStringSet("known", new HashSet<>()));
        for (String key : known) {
            ProxyEntry entry = parseKey(key);
            if (entry != null) checkProxy(entry, 0);
        }
    }

    private static void checkProxy(ProxyEntry entry, int attempt) {
        try {
            Class<?> managerClass = Class.forName("org.telegram.tgnet.ConnectionsManager");
            Object manager = managerClass.getMethod("getInstance", int.class).invoke(null, UserConfig.selectedAccount);
            for (Method method : managerClass.getMethods()) {
                if (!method.getName().equals("checkProxy") || method.getParameterTypes().length != 6) continue;
                Class<?> callbackType = method.getParameterTypes()[5];
                if (!callbackType.isInterface()) continue;
                Object callback = Proxy.newProxyInstance(callbackType.getClassLoader(), new Class[]{callbackType},
                        (proxy, called, args) -> {
                            if (args != null && args.length > 0 && args[0] instanceof Number) {
                                long ping = ((Number) args[0]).longValue();
                                if (ping >= 0) {
                                    prefs().edit().putInt("fail_" + hash(entry.key()), 0).apply();
                                } else if (attempt == 0) {
                                    EXECUTOR.schedule(() -> checkProxy(entry, 1), 20, TimeUnit.SECONDS);
                                } else {
                                    removeFailedProxy(entry);
                                }
                            }
                            return null;
                        });
                method.invoke(manager, entry.server, entry.port, "", "", entry.secret, callback);
                return;
            }
        } catch (Throwable error) {
            Log.d(TAG, "Proxy health-check API unavailable; keeping proxy instead of deleting it", error);
        }
    }

    private static void removeFailedProxy(ProxyEntry entry) {
        try {
            String key = entry.key();
            SharedPreferences.Editor editor = prefs().edit();
            Set<String> known = new HashSet<>(prefs().getStringSet("known", new HashSet<>()));
            known.remove(key);
            editor.putStringSet("known", known).remove("fail_" + hash(key)).apply();

            Class<?> config = Class.forName("org.telegram.messenger.SharedConfig");
            Object value = config.getField("proxyList").get(null);
            if (value instanceof List) {
                @SuppressWarnings("unchecked") List<Object> list = (List<Object>) value;
                synchronized (list) { list.removeIf(info -> containsProxy(java.util.Collections.singletonList(info), entry)); }
            }
            try { config.getMethod("saveConfig").invoke(null); } catch (Throwable ignored) {}

            SharedPreferences main = ApplicationLoader.applicationContext.getSharedPreferences("mainconfig", Context.MODE_PRIVATE);
            boolean active = entry.server.equals(main.getString("proxy_ip", ""))
                    && entry.port == main.getInt("proxy_port", 0)
                    && entry.secret.equals(main.getString("proxy_secret", ""));
            if (active) {
                main.edit().putBoolean("proxy_enabled", false).apply();
                Class<?> manager = Class.forName("org.telegram.tgnet.ConnectionsManager");
                for (Method method : manager.getMethods()) {
                    if (method.getName().equals("setProxySettings") && method.getParameterTypes().length == 6) {
                        method.invoke(null, false, "", 0, "", "", "");
                        break;
                    }
                }
                try {
                    Class<?> nc = Class.forName("org.telegram.messenger.NotificationCenter");
                    int event = nc.getField("proxySettingsChanged").getInt(null);
                    Object global = nc.getMethod("getGlobalInstance").invoke(null);
                    for (Method m : nc.getMethods()) if (m.getName().equals("postNotificationName") && m.getParameterTypes().length == 1) { m.invoke(global, event); break; }
                } catch (Throwable ignored) {}
            }
            Log.i(TAG, "Removed repeatedly unavailable auto-proxy " + entry.server + ":" + entry.port);
        } catch (Throwable error) {
            Log.w(TAG, "Could not remove unavailable auto-proxy", error);
        }
    }

    private static Object fieldValue(Object target, String name) throws Exception {
        Field field = target.getClass().getField(name);
        return field.get(target);
    }
    private static String stringField(Object target, String name) {
        try { Object v = target.getClass().getField(name).get(target); return v == null ? "" : String.valueOf(v); }
        catch (Throwable ignore) { return ""; }
    }
    private static int intField(Object target, String name) {
        try { return target.getClass().getField(name).getInt(target); } catch (Throwable ignore) { return -1; }
    }
    private static String stringMethod(Object target, String name) {
        Object value = method(target, name);
        return value == null ? "" : String.valueOf(value);
    }
    private static Object method(Object target, String name) {
        try { return target.getClass().getMethod(name).invoke(target); } catch (Throwable ignore) { return null; }
    }
    private static String hash(String text) {
        try {
            byte[] bytes = MessageDigest.getInstance("SHA-256").digest(text.getBytes(StandardCharsets.UTF_8));
            StringBuilder result = new StringBuilder();
            for (int i = 0; i < 8; i++) result.append(String.format(Locale.US, "%02x", bytes[i]));
            return result.toString();
        } catch (Throwable ignore) { return Integer.toHexString(text.hashCode()); }
    }

    private static final class ProxyEntry {
        final String server;
        final int port;
        final String secret;
        ProxyEntry(String server, int port, String secret) {
            this.server = server;
            this.port = port;
            this.secret = secret;
        }
        String key() { return server + "|" + port + "|" + secret; }
    }
}
''', encoding="utf-8")

# Add a Telegram-like switch using the same row style as the other Telega options.
source = settings.read_text(encoding="utf-8")
anchor = "        fragmentView = scroll;"
row = '''        addToggle(context, list, "Auto Proxy",
                "Проверять публичный канал @ProxyMTProto каждые 30 минут, добавлять новый MTProto-прокси и проверять его дважды перед удалением. Прокси сторонние: их оператор может видеть ваш IP и время подключения.",
                org.telegram.messenger.TelegaAutoProxy.isEnabled(),
                (button, enabled) -> org.telegram.messenger.TelegaAutoProxy.setEnabled(context, enabled));

'''
if "org.telegram.messenger.TelegaAutoProxy.isEnabled()" not in source:
    if anchor not in source:
        print("ERROR: Telega settings insertion anchor not found", file=sys.stderr)
        sys.exit(1)
    source = source.replace(anchor, row + anchor, 1)
    settings.write_text(source, encoding="utf-8")

# Start the watcher when the application opens; it remains dormant unless the toggle is on.
source = launch.read_text(encoding="utf-8")
super_anchor = "        super.onCreate(savedInstanceState);"
call = "        org.telegram.messenger.TelegaAutoProxy.init(getApplicationContext());"
if call not in source:
    if super_anchor not in source:
        print("ERROR: LaunchActivity superclass onCreate anchor not found", file=sys.stderr)
        sys.exit(1)
    source = source.replace(super_anchor, super_anchor + "\n" + call, 1)
    launch.write_text(source, encoding="utf-8")

print("Telega Auto Proxy patch applied.")
