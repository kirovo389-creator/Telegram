package org.telegram.ui;

import android.content.Context;
import android.graphics.Color;
import android.graphics.drawable.GradientDrawable;
import android.view.Gravity;
import android.view.View;
import android.widget.CompoundButton;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.Switch;
import android.widget.TextView;
import android.widget.Toast;

import org.telegram.messenger.AndroidUtilities;
import org.telegram.messenger.R;
import org.telegram.messenger.TelegaFeatures;
import org.telegram.ui.ActionBar.ActionBar;
import org.telegram.ui.ActionBar.BaseFragment;
import org.telegram.ui.ActionBar.Theme;

/** Telega-specific behavior toggles. */
public class TelegaSettingsActivity extends BaseFragment {

    @Override
    public View createView(Context context) {
        actionBar.setBackButtonImage(R.drawable.ic_ab_back);
        actionBar.setAllowOverlayTitle(true);
        actionBar.setTitle("Настройки Telega");
        actionBar.setActionBarMenuOnItemClick(new ActionBar.ActionBarMenuOnItemClick() {
            @Override
            public void onItemClick(int id) {
                if (id == -1) finishFragment();
            }
        });

        ScrollView scroll = new ScrollView(context);
        scroll.setFillViewport(true);
        scroll.setBackgroundColor(Theme.getColor(Theme.key_windowBackgroundGray));
        LinearLayout list = new LinearLayout(context);
        list.setOrientation(LinearLayout.VERTICAL);
        list.setPadding(0, AndroidUtilities.dp(8), 0, AndroidUtilities.dp(20));
        // TELEGA_BETA_SETTINGS_HEADER
        TextView pageTitle = new TextView(context);
        pageTitle.setText("TELEGA BETA");
        pageTitle.setTextSize(23);
        pageTitle.setTypeface(android.graphics.Typeface.DEFAULT, android.graphics.Typeface.BOLD);
        pageTitle.setTextColor(Theme.getColor(Theme.key_windowBackgroundWhiteBlackText));
        pageTitle.setPadding(AndroidUtilities.dp(20), AndroidUtilities.dp(14), AndroidUtilities.dp(20), 0);
        list.addView(pageTitle, new LinearLayout.LayoutParams(-1, -2));
        TextView pageSubtitle = new TextView(context);
        pageSubtitle.setText("Приватность, автоматизация и дополнительные возможности");
        pageSubtitle.setTextSize(13);
        pageSubtitle.setTextColor(Theme.getColor(Theme.key_windowBackgroundWhiteGrayText2));
        pageSubtitle.setPadding(AndroidUtilities.dp(20), AndroidUtilities.dp(4), AndroidUtilities.dp(20), AndroidUtilities.dp(14));
        list.addView(pageSubtitle, new LinearLayout.LayoutParams(-1, -2));

        scroll.addView(list, new ScrollView.LayoutParams(-1, -2));

        addToggle(context, list, "Удалённые сообщения",
                "Оставлять у себя сообщения, которые собеседник удалил для всех.",
                TelegaFeatures.isDeletedMessagesEnabled(currentAccount),
                (button, enabled) -> TelegaFeatures.setDeletedMessagesEnabled(enabled));
        addToggle(context, list, "Призрак",
                "Не отправлять отметки о прочтении и не обновлять онлайн-статус. Серверные ограничения всё равно действуют.",
                TelegaFeatures.isGhostModeEnabled(),
                (button, enabled) -> TelegaFeatures.setGhostModeEnabled(enabled));
        addToggle(context, list, "Auto Proxy",
                "Автоматически переключается между сохранёнными прокси при проблемах с соединением. Нужно минимум два прокси, добавленных тобой.",
                TelegaFeatures.isAutoProxyEnabled(),
                (button, enabled) -> {
                    if (!TelegaFeatures.setAutoProxyEnabled(enabled)) {
                        button.setChecked(false);
                        Toast.makeText(context, "Добавь минимум два прокси в настройках прокси Telegram", Toast.LENGTH_LONG).show();
                    }
                });

        addToggle(context, list, "Auto Archive",
                "Автоматически архивировать новые группы, каналы и ботов и отключать им звук.",
                TelegaFeatures.isAutoArchiveEnabled(),
                (button, enabled) -> TelegaFeatures.setAutoArchiveEnabled(enabled));
        addToggle(context, list, "Анти звук",
                "Автоматически отключать уведомления у новых групп, каналов и ботов.",
                TelegaFeatures.isAntiSoundEnabled(),
                (button, enabled) -> TelegaFeatures.setAntiSoundEnabled(enabled));

        addToggle(context, list, "Значок Telega",
                "Пульсирующий значок рядом с твоим именем в собственном профиле.",
                TelegaFeatures.isBadgeEnabled(),
                (button, enabled) -> TelegaFeatures.setBadgeEnabled(enabled));

        fragmentView = scroll;
        return fragmentView;
    }

    private void addToggle(Context context, LinearLayout parent, String title, String summary,
                           boolean checked, CompoundButton.OnCheckedChangeListener listener) {
        LinearLayout row = new LinearLayout(context);
        row.setOrientation(LinearLayout.HORIZONTAL);
        row.setGravity(Gravity.CENTER_VERTICAL);
        row.setPadding(AndroidUtilities.dp(16), AndroidUtilities.dp(13), AndroidUtilities.dp(16), AndroidUtilities.dp(13));
        GradientDrawable rowBackground = new GradientDrawable();
        rowBackground.setColor(Theme.getColor(Theme.key_windowBackgroundWhite));
        rowBackground.setCornerRadius(AndroidUtilities.dp(12));
        row.setBackground(rowBackground);
        LinearLayout textColumn = new LinearLayout(context);
        textColumn.setOrientation(LinearLayout.VERTICAL);
        TextView titleView = new TextView(context);
        titleView.setText(title);
        titleView.setTextSize(16);
        titleView.setTextColor(Theme.getColor(Theme.key_windowBackgroundWhiteBlackText));
        TextView summaryView = new TextView(context);
        summaryView.setText(summary);
        summaryView.setTextSize(13);
        summaryView.setLineSpacing(AndroidUtilities.dp(2), 1.0f);
        summaryView.setTextColor(Theme.getColor(Theme.key_windowBackgroundWhiteGrayText2));
        LinearLayout.LayoutParams titleParams = new LinearLayout.LayoutParams(-1, -2);
        textColumn.addView(titleView, titleParams);
        LinearLayout.LayoutParams summaryParams = new LinearLayout.LayoutParams(-1, -2);
        summaryParams.topMargin = AndroidUtilities.dp(4);
        textColumn.addView(summaryView, summaryParams);
        row.addView(textColumn, new LinearLayout.LayoutParams(0, -2, 1f));
        Switch toggle = new Switch(context);
        toggle.setChecked(checked);
        toggle.setOnCheckedChangeListener(listener);
        LinearLayout.LayoutParams toggleParams = new LinearLayout.LayoutParams(-2, -2);
        toggleParams.leftMargin = AndroidUtilities.dp(12);
        row.addView(toggle, toggleParams);
        row.setOnClickListener(v -> toggle.setChecked(!toggle.isChecked()));
        LinearLayout.LayoutParams rowParams = new LinearLayout.LayoutParams(-1, -2);
        rowParams.setMargins(AndroidUtilities.dp(12), 0, AndroidUtilities.dp(12), AndroidUtilities.dp(8));
        parent.addView(row, rowParams);
    }
}
