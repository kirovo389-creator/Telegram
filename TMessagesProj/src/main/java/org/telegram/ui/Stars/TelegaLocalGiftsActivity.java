package org.telegram.ui.Stars;

import android.content.Context;
import android.content.SharedPreferences;
import android.graphics.Typeface;
import android.os.Bundle;
import android.view.Gravity;
import android.view.View;
import android.widget.LinearLayout;
import android.widget.TextView;

import org.telegram.ui.ActionBar.AlertDialog;

import org.telegram.messenger.AndroidUtilities;
import org.telegram.messenger.ApplicationLoader;
import org.telegram.messenger.SendMessagesHelper;
import org.telegram.messenger.UserConfig;
import org.telegram.ui.ActionBar.BaseFragment;
import org.telegram.ui.ActionBar.Theme;
import org.telegram.ui.DialogsActivity;
import org.telegram.messenger.MessagesStorage;
import org.telegram.ui.Components.LayoutHelper;

import java.util.ArrayList;

public class TelegaLocalGiftsActivity extends BaseFragment {
    private static final String PREFS = "telega_local_stars_wallet";
    private static final int INITIAL_BALANCE = 1000;

    private static final String[] GIFT_NAMES = {"Rose", "Golden Trophy", "Dragon NFT"};
    private static final String[] GIFT_EMOJI = {"🌹", "🏆", "🐉"};
    private static final int[] GIFT_PRICES = {100, 250, 500};

    public TelegaLocalGiftsActivity() {
        super();
    }

    private static SharedPreferences prefs(int account) {
        Context context = ApplicationLoader.applicationContext;
        return context.getSharedPreferences(PREFS + "_" + account, Context.MODE_PRIVATE);
    }

    public static int getBalance(int account) {
        SharedPreferences p = prefs(account);
        if (!p.getBoolean("initialized", false)) {
            p.edit().putBoolean("initialized", true).putInt("balance", INITIAL_BALANCE).apply();
            return INITIAL_BALANCE;
        }
        return p.getInt("balance", INITIAL_BALANCE);
    }

    private static boolean spend(int account, int amount) {
        SharedPreferences p = prefs(account);
        int balance = getBalance(account);
        if (amount < 0 || balance < amount) return false;
        p.edit().putInt("balance", balance - amount).apply();
        return true;
    }

    @Override
    public View createView(Context context) {
        actionBar.setTitle("Telega Stars");
        actionBar.setBackButtonImage(org.telegram.messenger.R.drawable.ic_ab_back);
        actionBar.setAllowOverlayTitle(true);

        LinearLayout layout = new LinearLayout(context);
        layout.setOrientation(LinearLayout.VERTICAL);
        layout.setPadding(AndroidUtilities.dp(20), AndroidUtilities.dp(24), AndroidUtilities.dp(20), AndroidUtilities.dp(24));
        layout.setBackgroundColor(Theme.getColor(Theme.key_windowBackgroundWhite, resourceProvider));

        TextView balance = new TextView(context);
        balance.setText("⭐  " + getBalance(currentAccount) + " Telega Stars");
        balance.setTextSize(25);
        balance.setTypeface(Typeface.DEFAULT_BOLD);
        balance.setGravity(Gravity.CENTER);
        balance.setTextColor(Theme.getColor(Theme.key_windowBackgroundWhiteBlackText, resourceProvider));
        layout.addView(balance, LayoutHelper.createLinear(LayoutHelper.MATCH_PARENT, LayoutHelper.WRAP_CONTENT, 0, 0, 0, 18));

        TextView note = new TextView(context);
        note.setText("Локальный баланс для подарков Telega Beta. Он отделён от официальных Telegram Stars. Подарки отправляются как сообщения и видны другим пользователям Telega Beta.");
        note.setTextSize(14);
        note.setGravity(Gravity.CENTER);
        note.setTextColor(Theme.getColor(Theme.key_windowBackgroundWhiteGrayText, resourceProvider));
        layout.addView(note, LayoutHelper.createLinear(LayoutHelper.MATCH_PARENT, LayoutHelper.WRAP_CONTENT, 0, 0, 0, 20));

        for (int i = 0; i < GIFT_NAMES.length; i++) {
            final int index = i;
            TextView button = new TextView(context);
            button.setText(GIFT_EMOJI[i] + "  " + GIFT_NAMES[i] + "  ·  " + GIFT_PRICES[i] + " ⭐");
            button.setTextSize(16);
            button.setGravity(Gravity.CENTER_VERTICAL);
            button.setPadding(AndroidUtilities.dp(16), 0, AndroidUtilities.dp(16), 0);
            button.setTextColor(Theme.getColor(Theme.key_windowBackgroundWhiteBlackText, resourceProvider));
            button.setBackground(Theme.createRoundRectDrawable(AndroidUtilities.dp(14), Theme.getColor(Theme.key_dialogBackground, resourceProvider)));
            button.setOnClickListener(v -> confirmPurchase(index));
            layout.addView(button, LayoutHelper.createLinear(LayoutHelper.MATCH_PARENT, 54, 0, 0, 0, 10));
        }

        TextView disclaimer = new TextView(context);
        disclaimer.setText("Это локальные коллекционные подарки, а не реальные NFT в блокчейне. Не покупайте их за реальные деньги.");
        disclaimer.setTextSize(12);
        disclaimer.setGravity(Gravity.CENTER);
        disclaimer.setTextColor(Theme.getColor(Theme.key_windowBackgroundWhiteGrayText2, resourceProvider));
        layout.addView(disclaimer, LayoutHelper.createLinear(LayoutHelper.MATCH_PARENT, LayoutHelper.WRAP_CONTENT, 0, 20, 0, 0));

        fragmentView = layout;
        return fragmentView;
    }

    private void confirmPurchase(int index) {
        if (getParentActivity() == null) return;
        if (getBalance(currentAccount) < GIFT_PRICES[index]) {
            new AlertDialog.Builder(getParentActivity())
                    .setTitle("Недостаточно Telega Stars")
                    .setMessage("Для этого подарка нужно " + GIFT_PRICES[index] + " локальных Telega Stars. Реальные деньги не используются.")
                    .setPositiveButton("Понятно", null)
                    .show();
            return;
        }
        new AlertDialog.Builder(getParentActivity())
                .setTitle("Купить " + GIFT_NAMES[index] + "?")
                .setMessage("Цена: " + GIFT_PRICES[index] + " локальных Telega Stars. После подтверждения выбери получателя. Это не официальные Telegram Stars и не настоящий NFT.")
                .setNegativeButton("Отмена", null)
                .setPositiveButton("Купить за " + GIFT_PRICES[index] + " ⭐", (dialog, which) -> selectRecipient(index))
                .show();
    }

    private void selectRecipient(int index) {
        if (getParentActivity() == null) return;
        if (getBalance(currentAccount) < GIFT_PRICES[index]) {
            new AlertDialog.Builder(getParentActivity())
                    .setTitle("Недостаточно Telega Stars")
                    .setMessage("Баланс можно пополнить только локально; реальные деньги не используются.")
                    .setPositiveButton("Понятно", null)
                    .show();
            return;
        }

        Bundle args = new Bundle();
        args.putInt("dialogsType", DialogsActivity.DIALOGS_TYPE_USERS_ONLY);
        args.putBoolean("onlySelect", true);
        args.putBoolean("allowGlobalSearch", true);
        DialogsActivity picker = new DialogsActivity(args);
        picker.setDelegate((fragment, dids, message, param, notify, scheduleDate, scheduleRepeatPeriod, topicsFragment) -> {
            if (dids == null || dids.isEmpty() || dids.get(0).dialogId <= 0) return false;
            long dialogId = dids.get(0).dialogId;
            if (!spend(currentAccount, GIFT_PRICES[index])) {
                return false;
            }
            String text = GIFT_EMOJI[index] + "  Telega Gift: " + GIFT_NAMES[index]
                    + "\nЛокальный коллекционный подарок · " + GIFT_PRICES[index] + " Telega Stars";
            SendMessagesHelper.getInstance(currentAccount).sendMessage(
                    SendMessagesHelper.SendMessageParams.of(text, dialogId, null, null, null, true, null, null, null, true, 0, 0, null, false)
            );
            fragment.finishFragment();
            finishFragment();
            return true;
        });
        presentFragment(picker);
    }
}
