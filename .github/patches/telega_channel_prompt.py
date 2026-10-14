#!/usr/bin/env python3
"""Offer an opt-in link to the TelegaForks channel after an account is signed in."""
from pathlib import Path
import sys

path = Path("TMessagesProj/src/main/java/org/telegram/ui/LaunchActivity.java")
if not path.exists():
    print("ERROR: LaunchActivity.java not found", file=sys.stderr)
    sys.exit(1)

s = path.read_text(encoding="utf-8")
method = r'''
    private void showTelegaChannelPromptIfNeeded() {
        int account = currentAccount;
        long userId = UserConfig.getInstance(account).getClientUserId();
        if (userId == 0 || isFinishing() || isDestroyed() || passcodeDialog != null) return;
        String prefKey = "shown_" + account + "_" + userId;
        android.content.SharedPreferences prefs = ApplicationLoader.applicationContext.getSharedPreferences("telega_channel_prompt", 0);
        if (prefs.getBoolean(prefKey, false)) return;
        // Mark before showing to avoid duplicate prompts on rapid resume events.
        prefs.edit().putBoolean(prefKey, true).apply();
        new AlertDialog.Builder(this)
                .setTitle("Поддержать Telega Beta")
                .setMessage("Хочешь подписаться на канал TelegaForks и получать новости сборок?")
                .setNegativeButton("Не сейчас", null)
                .setPositiveButton("Открыть канал", (dialog, which) -> {
                    try {
                        startActivity(new android.content.Intent(android.content.Intent.ACTION_VIEW,
                                android.net.Uri.parse("https://t.me/TelegaForks")));
                    } catch (Exception e) {
                        android.util.Log.e("Telega", "Unable to open TelegaForks channel", e);
                    }
                })
                .show();
    }

'''
anchor = "    @Override\n    protected void onResume() {"
if "private void showTelegaChannelPromptIfNeeded()" not in s:
    if anchor not in s:
        print("ERROR: LaunchActivity onResume anchor not found", file=sys.stderr)
        sys.exit(1)
    s = s.replace(anchor, method + anchor, 1)

call_anchor = "        updateCurrentConnectionState(currentAccount);"
if "postDelayed(this::showTelegaChannelPromptIfNeeded" not in s:
    if call_anchor not in s:
        print("ERROR: LaunchActivity resume call anchor not found", file=sys.stderr)
        sys.exit(1)
    s = s.replace(call_anchor, call_anchor + "\n        getWindow().getDecorView().postDelayed(this::showTelegaChannelPromptIfNeeded, 900);", 1)

path.write_text(s, encoding="utf-8")
print("TelegaForks opt-in channel prompt patch applied.")
