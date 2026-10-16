package org.telegram.ui;

import android.content.Context;
import android.graphics.drawable.GradientDrawable;
import android.view.Gravity;
import android.widget.CompoundButton;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.Switch;
import android.widget.TextView;

import org.telegram.messenger.AndroidUtilities;
import org.telegram.messenger.R;
import org.telegram.messenger.TelegaFeatures;
import org.telegram.messenger.TelegaOtaUpdater;
import org.telegram.ui.ActionBar.ActionBar;
import org.telegram.ui.ActionBar.BaseFragment;
import org.telegram.ui.ActionBar.Theme;

/** Telega-specific settings, grouped by purpose and backed by real feature state. */
public class TelegaSettingsActivity extends BaseFragment {

    @Override
    public android.view.View createView(Context context) {
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
        scroll.setClipToPadding(false);
        scroll.setBackgroundColor(Theme.getColor(Theme.key_windowBackgroundGray));

        LinearLayout list = new LinearLayout(context);
        list.setOrientation(LinearLayout.VERTICAL);
        list.setPadding(0, AndroidUtilities.dp(8), 0, AndroidUtilities.dp(24));

        TextView pageTitle = new TextView(context);
        pageTitle.setText("TELEGA BETA");
        pageTitle.setTextSize(24);
        pageTitle.setTypeface(android.graphics.Typeface.DEFAULT, android.graphics.Typeface.BOLD);
        pageTitle.setLetterSpacing(0.035f);
        pageTitle.setTextColor(Theme.getColor(Theme.key_windowBackgroundWhiteBlackText));
        pageTitle.setPadding(AndroidUtilities.dp(20), AndroidUtilities.dp(14), AndroidUtilities.dp(20), 0);
        list.addView(pageTitle, new LinearLayout.LayoutParams(-1, -2));

        TextView pageSubtitle = new TextView(context);
        pageSubtitle.setText("Управляй функциями, приватностью и производительностью");
        pageSubtitle.setTextSize(13);
        pageSubtitle.setLineSpacing(AndroidUtilities.dp(2), 1.0f);
        pageSubtitle.setTextColor(Theme.getColor(Theme.key_windowBackgroundWhiteGrayText2));
        pageSubtitle.setPadding(AndroidUtilities.dp(20), AndroidUtilities.dp(5), AndroidUtilities.dp(20), AndroidUtilities.dp(12));
        list.addView(pageSubtitle, new LinearLayout.LayoutParams(-1, -2));

        addSection(context, list, "ПРИВАТНОСТЬ");
        addToggle(context, list, "Удалённые сообщения",
                "Сохранять локальную отметку о сообщениях, удалённых собеседником для всех.",
                TelegaFeatures.isDeletedMessagesEnabled(currentAccount),
                (button, enabled) -> TelegaFeatures.setDeletedMessagesEnabled(enabled));
        addToggle(context, list, "Призрак",
                "Ограничивает отправку отметок о прочтении и обновление онлайн-статуса там, где это позволяет сервер.",
                TelegaFeatures.isGhostModeEnabled(),
                (button, enabled) -> TelegaFeatures.setGhostModeEnabled(enabled));

        addSection(context, list, "СЕТЬ И ОБНОВЛЕНИЯ");
        addToggle(context, list, "Автообновление",
                "Проверять новые стабильные сборки и предлагать обновление. Установка всё равно подтверждается Android.",
                TelegaOtaUpdater.isEnabled(context),
                (button, enabled) -> TelegaOtaUpdater.setEnabled(context, enabled));

        addSection(context, list, "АВТОМАТИЗАЦИЯ");
        addToggle(context, list, "Auto Archive",
                "Автоматически архивировать новые группы, каналы и ботов и отключать им звук.",
                TelegaFeatures.isAutoArchiveEnabled(),
                (button, enabled) -> TelegaFeatures.setAutoArchiveEnabled(enabled));
        addToggle(context, list, "Анти звук",
                "Отключать уведомления у новых групп, каналов и ботов.",
                TelegaFeatures.isAntiSoundEnabled(),
                (button, enabled) -> TelegaFeatures.setAntiSoundEnabled(enabled));

        addSection(context, list, "ВИД И ЭФФЕКТЫ");
        addToggle(context, list, "Значок Telega",
                "Скрытая отметка в BIO отображает значок другим пользователям Telega Beta.",
                TelegaFeatures.isBadgeEnabled(),
                (button, enabled) -> TelegaFeatures.setBadgeEnabled(enabled));
        addToggle(context, list, "Эффекты сообщений",
                "Локальные анимации для отдельных эмодзи при появлении сообщения; ничего дополнительно не отправляется.",
                TelegaFeatures.isMessageEffectsEnabled(),
                (button, enabled) -> TelegaFeatures.setMessageEffectsEnabled(enabled));

        addSection(context, list, "ПРОИЗВОДИТЕЛЬНОСТЬ");
        addToggle(context, list, "Турбо-загрузка",
                "Увеличивает число параллельных загрузок. Реальная скорость зависит от сети и серверов.",
                TelegaFeatures.isTurboDownloadEnabled(),
                (button, enabled) -> TelegaFeatures.setTurboDownloadEnabled(enabled));

        scroll.addView(list, new ScrollView.LayoutParams(-1, -2));
        fragmentView = scroll;
        return fragmentView;
    }

    private void addToggle(Context context, LinearLayout parent, String title, String summary,
                           boolean checked, CompoundButton.OnCheckedChangeListener listener) {
        LinearLayout row = new LinearLayout(context);
        row.setOrientation(LinearLayout.HORIZONTAL);
        row.setGravity(Gravity.CENTER_VERTICAL);
        row.setPadding(AndroidUtilities.dp(16), AndroidUtilities.dp(14), AndroidUtilities.dp(14), AndroidUtilities.dp(14));

        GradientDrawable rowBackground = new GradientDrawable();
        rowBackground.setColor(Theme.getColor(Theme.key_windowBackgroundWhite));
        rowBackground.setCornerRadius(AndroidUtilities.dp(14));
        row.setBackground(rowBackground);
        row.setFocusable(true);
        row.setClickable(true);

        LinearLayout textColumn = new LinearLayout(context);
        textColumn.setOrientation(LinearLayout.VERTICAL);

        TextView titleView = new TextView(context);
        titleView.setText(title);
        titleView.setTextSize(15);
        titleView.setTypeface(android.graphics.Typeface.DEFAULT, android.graphics.Typeface.BOLD);
        titleView.setTextColor(Theme.getColor(Theme.key_windowBackgroundWhiteBlackText));

        TextView summaryView = new TextView(context);
        summaryView.setText(summary);
        summaryView.setTextSize(12);
        summaryView.setLineSpacing(AndroidUtilities.dp(2), 1.0f);
        summaryView.setTextColor(Theme.getColor(Theme.key_windowBackgroundWhiteGrayText2));

        textColumn.addView(titleView, new LinearLayout.LayoutParams(-1, -2));
        LinearLayout.LayoutParams summaryParams = new LinearLayout.LayoutParams(-1, -2);
        summaryParams.topMargin = AndroidUtilities.dp(5);
        textColumn.addView(summaryView, summaryParams);
        row.addView(textColumn, new LinearLayout.LayoutParams(0, -2, 1f));

        Switch toggle = new Switch(context);
        toggle.setChecked(checked);
        toggle.setOnCheckedChangeListener(listener);
        LinearLayout.LayoutParams toggleParams = new LinearLayout.LayoutParams(-2, -2);
        toggleParams.leftMargin = AndroidUtilities.dp(10);
        row.addView(toggle, toggleParams);
        row.setOnClickListener(v -> toggle.setChecked(!toggle.isChecked()));

        LinearLayout.LayoutParams rowParams = new LinearLayout.LayoutParams(-1, -2);
        rowParams.setMargins(AndroidUtilities.dp(12), 0, AndroidUtilities.dp(12), AndroidUtilities.dp(8));
        parent.addView(row, rowParams);
    }
    private void addSection(Context context, LinearLayout parent, String title) {
        TextView heading = new TextView(context);
        heading.setText(title);
        heading.setTextSize(11);
        heading.setTypeface(android.graphics.Typeface.DEFAULT, android.graphics.Typeface.BOLD);
        heading.setLetterSpacing(0.08f);
        heading.setTextColor(Theme.getColor(Theme.key_windowBackgroundWhiteGrayText2));
        heading.setPadding(AndroidUtilities.dp(20), AndroidUtilities.dp(18), AndroidUtilities.dp(20), AndroidUtilities.dp(9));
        parent.addView(heading, new LinearLayout.LayoutParams(-1, -2));
    }

}
