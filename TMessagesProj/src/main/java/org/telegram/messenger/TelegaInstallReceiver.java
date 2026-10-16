package org.telegram.messenger;

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
            clearPendingUpdate(context);
            Toast.makeText(context, "Обновление Telega установлено", Toast.LENGTH_LONG).show();
        } else {
            String detail = intent.getStringExtra(PackageInstaller.EXTRA_STATUS_MESSAGE);
            clearPendingUpdate(context);
            Log.w("TelegaOTA", "Install failed, status=" + status + ", detail=" + detail);
            String message = "Android не установил обновление";
            if (detail != null && !detail.trim().isEmpty()) {
                message += ": " + detail;
            } else {
                message += ". Проверь, что APK подписан тем же ключом, что и установленная версия.";
            }
            Toast.makeText(context, message, Toast.LENGTH_LONG).show();
        }
    }    
    private static void clearPendingUpdate(Context context) {
        android.content.SharedPreferences preferences = context.getSharedPreferences("telega_ota", Context.MODE_PRIVATE);
        String pendingPath = preferences.getString("pending_file", "");
        if (pendingPath != null && !pendingPath.isEmpty()) {
            //noinspection ResultOfMethodCallIgnored
            new java.io.File(pendingPath).delete();
        }
        preferences.edit().remove("pending_file").remove("pending_tag")
                .putBoolean("awaiting_unknown_sources", false).apply();
    }

}
