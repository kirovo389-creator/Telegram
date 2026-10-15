package org.telegram.messenger;

import android.util.Log;

import org.telegram.tgnet.ConnectionsManager;
import org.telegram.tgnet.TLRPC;
import org.telegram.tgnet.TL_account;

/** Writes the user's opt-in Telega identity flag into the hidden BIO metadata. */
public final class TelegaBadgeSync {
    private TelegaBadgeSync() {}

    public static void update(int account, boolean enabled) {
        try {
            TLRPC.User self = UserConfig.getInstance(account).getCurrentUser();
            if (self == null || self.id == 0) return;
            TLRPC.TL_users_getFullUser load = new TLRPC.TL_users_getFullUser();
            load.id = MessagesController.getInstance(account).getInputUser(self);
            ConnectionsManager.getInstance(account).sendRequest(load, (response, error) -> {
                if (error != null || !(response instanceof TLRPC.TL_users_userFull)) {
                    if (error != null) Log.w("Telega", "Could not load BIO before syncing badge: " + error.text);
                    return;
                }
                TLRPC.UserFull full = ((TLRPC.TL_users_userFull) response).full_user;
                if (full == null) return;
                String oldAbout = full.about == null ? "" : full.about;
                String newAbout = TelegaLocalStatus.updateUserBadge(oldAbout, enabled);
                if (oldAbout.equals(newAbout)) return;
                TL_account.updateProfile request = new TL_account.updateProfile();
                request.flags |= 4;
                request.about = newAbout;
                ConnectionsManager.getInstance(account).sendRequest(request, (updateResponse, updateError) ->
                        AndroidUtilities.runOnUIThread(() -> {
                            if (updateError != null) {
                                Log.w("Telega", "Badge metadata save failed: " + updateError.text);
                                return;
                            }
                            full.about = newAbout;
                            NotificationCenter.getInstance(account).postNotificationName(
                                    NotificationCenter.updateInterfaces, MessagesController.UPDATE_MASK_ALL);
                        }));
            });
        } catch (Throwable error) {
            Log.w("Telega", "Unable to sync Telega badge metadata", error);
        }
    }
}
