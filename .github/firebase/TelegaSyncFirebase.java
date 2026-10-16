package org.telegram.messenger;

import android.content.Context;
import android.util.Log;

import com.google.firebase.FirebaseApp;
import com.google.firebase.FirebaseOptions;

import org.json.JSONArray;
import org.json.JSONObject;

import java.io.InputStream;
import java.nio.charset.StandardCharsets;

/**
 * Initializes TelegaSync's Firebase project independently of the legacy Telegram Firebase app.
 * The legacy google-services.json and default FirebaseApp are never modified.
 */
public final class TelegaSyncFirebase {
    private static final String TAG = "TelegaSyncFirebase";
    private static final String APP_NAME = "TelegaSync";
    private static volatile FirebaseApp instance;

    private TelegaSyncFirebase() {}

    public static FirebaseApp initialize(Context context) {
        FirebaseApp current = instance;
        if (current != null) {
            return current;
        }
        synchronized (TelegaSyncFirebase.class) {
            if (instance != null) {
                return instance;
            }
            Context appContext = context.getApplicationContext();
            try {
                try {
                    instance = FirebaseApp.getInstance(APP_NAME);
                    return instance;
                } catch (IllegalStateException notInitialized) {
                    // Continue and initialize the dedicated secondary app.
                }

                JSONObject root;
                try (InputStream input = appContext.getAssets().open("telega-sync-google-services.json")) {
                    byte[] bytes = new byte[input.available()];
                    int offset = 0;
                    while (offset < bytes.length) {
                        int count = input.read(bytes, offset, bytes.length - offset);
                        if (count < 0) {
                            break;
                        }
                        offset += count;
                    }
                    root = new JSONObject(new String(bytes, 0, offset, StandardCharsets.UTF_8));
                }

                JSONObject projectInfo = root.getJSONObject("project_info");
                JSONArray clients = root.getJSONArray("client");
                JSONObject selectedClient = null;
                String packageName = appContext.getPackageName();
                for (int i = 0; i < clients.length(); i++) {
                    JSONObject candidate = clients.getJSONObject(i);
                    String candidatePackage = candidate.getJSONObject("client_info")
                            .getJSONObject("android_client_info").optString("package_name", "");
                    if (packageName.equals(candidatePackage)) {
                        selectedClient = candidate;
                        break;
                    }
                }
                if (selectedClient == null && clients.length() > 0) {
                    selectedClient = clients.getJSONObject(0);
                    Log.w(TAG, "No Firebase client entry matches " + packageName
                            + "; using the first TelegaSync client configuration.");
                }
                if (selectedClient == null) {
                    throw new IllegalStateException("No Firebase Android client is configured");
                }

                String applicationId = selectedClient.getJSONObject("client_info")
                        .getString("mobilesdk_app_id");
                JSONArray keys = selectedClient.getJSONArray("api_key");
                if (keys.length() == 0) {
                    throw new IllegalStateException("Firebase API key is missing");
                }
                String apiKey = keys.getJSONObject(0).getString("current_key");

                FirebaseOptions.Builder options = new FirebaseOptions.Builder()
                        .setApplicationId(applicationId)
                        .setApiKey(apiKey)
                        .setProjectId(projectInfo.getString("project_id"));
                String bucket = projectInfo.optString("storage_bucket", "");
                if (!bucket.isEmpty()) {
                    options.setStorageBucket(bucket);
                }

                instance = FirebaseApp.initializeApp(appContext, options.build(), APP_NAME);
                Log.i(TAG, "Dedicated TelegaSync Firebase instance initialized.");
                return instance;
            } catch (Exception error) {
                Log.e(TAG, "Could not initialize the secondary Firebase app.", error);
                return null;
            }
        }
    }

    public static FirebaseApp getInstance(Context context) {
        FirebaseApp result = instance;
        return result != null ? result : initialize(context);
    }
}
