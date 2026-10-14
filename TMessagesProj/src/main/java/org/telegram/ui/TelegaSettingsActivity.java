package org.telegram.ui;

import android.content.Context;
import android.graphics.Color;
import android.view.Gravity;
import android.view.View;
import android.widget.CompoundButton;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.Switch;
import android.widget.TextView;

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
        scroll.addView(list, new ScrollView.LayoutParams(-1, -2));

        addToggle(context, list, "Удалённые сообщения",
                "Оставлять у себя сообщения, которые собеседник удалил для всех.",
                TelegaFeatures.isDeletedMessagesEnabled(currentAccount),
                (button, enabled) -> TelegaFeatures.setDeletedMessagesEnabled(enabled));
        addToggle(context, list, "Призрак",
                "Не отправлять отметки о прочтении и не обновлять онлайн-статус. Серверные ограничения всё равно действуют.",
                TelegaFeatures.isGhostModeEnabled(),
                (button, enabled) -> TelegaFeatures.setGhostModeEnabled(enabled));
        addToggle(context, list, "Auto Archive",
                "Автоматически архивировать новые группы, каналы и ботов и отключать им звук.",
                TelegaFeatures.isAutoArchiveEnabled(),
                (button, enabled) -> TelegaFeatures.setAutoArchiveEnabled(enabled));
        addToggle(context, list, "Анти звук",
                "Автоматически отключать уведомления у новых групп, каналов и ботов.",
                TelegaFeatures.isAntiSoundEnabled(),
                (button, enabled) -> TelegaFeatures.setAntiSoundEnabled(enabled));

        fragmentView = scroll;
        return fragmentView;
    }

    private void addToggle(Context context, LinearLayout parent, String title, String summary,
                           boolean checked, CompoundButton.OnCheckedChangeListener listener) {
        LinearLayout row = new LinearLayout(context);
        row.setOrientation(LinearLayout.HORIZONTAL);
        row.setGravity(Gravity.CENTER_VERTICAL);
        row.setPadding(AndroidUtilities.dp(16), AndroidUtilities.dp(13), AndroidUtilities.dp(16), AndroidUtilities.dp(13));
        row.setBackgroundColor(Theme.getColor(Theme.key_windowBackgroundWhite));
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
        rowParams.bottomMargin = AndroidUtilities.dp(1);
        parent.addView(row, rowParams);
    }
}
