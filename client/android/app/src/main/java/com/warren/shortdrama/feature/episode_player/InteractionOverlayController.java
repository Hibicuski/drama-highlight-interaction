package com.warren.shortdrama.feature.episode_player;

import android.animation.Animator;
import android.animation.AnimatorListenerAdapter;
import android.animation.ObjectAnimator;
import android.animation.PropertyValuesHolder;
import android.content.res.ColorStateList;
import android.content.res.Resources;
import android.content.res.TypedArray;
import android.os.Handler;
import android.os.Looper;
import android.util.TypedValue;
import android.view.Gravity;
import android.view.View;
import android.view.animation.AnticipateOvershootInterpolator;
import android.view.animation.DecelerateInterpolator;
import android.widget.Button;
import android.widget.LinearLayout;
import android.widget.TextView;

import com.google.android.material.card.MaterialCardView;
import com.google.android.material.button.MaterialButton;
import com.warren.shortdrama.R;
import com.warren.shortdrama.core.model.HighlightPoint;
import com.warren.shortdrama.core.model.InteractionModels;

import java.util.Arrays;
import java.util.HashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;

public class InteractionOverlayController {

    public interface ActionListener {
        void onAction(String highlightId, String actionKey, String actionLabel);
    }

    private final Resources resources;
    private final int[] defaultButtonColors;
    private final MaterialCardView layoutInteraction;
    private final TextView tvInteractionBadge;
    private final TextView tvInteractionTitle;
    private final LinearLayout layoutActions;
    private final List<MaterialButton> actionButtons;
    private final TextView tvInteractionStats;
    private final TextView tvFeedback;
    private final Handler handler = new Handler(Looper.getMainLooper());

    private ObjectAnimator pulseAnimator;
    private boolean released;
    private String activeTemplate = "";
    private String activeEffect = "";
    private int[] activeButtonColors;
    private final Map<String, String> activeActionLabels = new HashMap<>();

    public InteractionOverlayController(View root) {
        resources = root.getResources();
        defaultButtonColors = getColorArray(R.array.interaction_default_button_colors);
        activeButtonColors = defaultButtonColors;
        layoutInteraction = root.findViewById(R.id.layout_interaction);
        tvInteractionBadge = root.findViewById(R.id.tv_interaction_badge);
        tvInteractionTitle = root.findViewById(R.id.tv_interaction_title);
        layoutActions = root.findViewById(R.id.layout_actions);
        actionButtons = Arrays.asList(
                root.findViewById(R.id.btn_action_1),
                root.findViewById(R.id.btn_action_2),
                root.findViewById(R.id.btn_action_3)
        );
        tvInteractionStats = root.findViewById(R.id.tv_interaction_stats);
        tvFeedback = root.findViewById(R.id.tv_interaction_feedback);
    }

    public boolean showHighlight(HighlightPoint highlight, ActionListener listener) {
        if (released) return false;
        if (highlight == null || highlight.getPayload() == null || highlight.getPayload().getActions() == null) {
            return false;
        }

        List<HighlightPoint.Action> actions = highlight.getPayload().getActions();
        if (actions.isEmpty()) {
            return false;
        }
        int actionCount = Math.min(actions.size(), actionButtons.size());
        activeTemplate = normalize(highlight.getTemplate());
        activeEffect = normalize(highlight.getPayload().getEffect());
        activeActionLabels.clear();

        handler.removeCallbacksAndMessages(null);
        layoutInteraction.animate().cancel();
        tvFeedback.animate().cancel();
        tvFeedback.setVisibility(View.GONE);

        applyVisualStyle(highlight, actionCount);
        tvInteractionBadge.setText(buildBadgeText(highlight));
        tvInteractionTitle.setText(highlight.getPayload().getTitle());
        bindActionButtons(highlight, actions, actionCount, listener);

        tvInteractionStats.setVisibility(View.GONE);
        setActionsEnabled(true);

        // --- 动画效果 ---
        layoutInteraction.setVisibility(View.VISIBLE);
        layoutInteraction.setAlpha(0f);
        layoutInteraction.setTranslationY(resources.getDimension(R.dimen.interaction_overlay_translation_y));
        layoutInteraction.animate()
                .alpha(1f)
                .translationY(0f)
                .setDuration(integer(R.integer.interaction_overlay_show_ms))
                .setInterpolator(new DecelerateInterpolator())
                .start();

        if (!"particle-burst".equals(activeEffect)) {
            startPulseAnimation();
        }
        return true;
    }

    public void hide() {
        if (released) return;
        stopPulseAnimation();
        layoutInteraction.animate()
                .alpha(0f)
                .translationY(resources.getDimension(R.dimen.interaction_overlay_translation_y))
                .setDuration(integer(R.integer.interaction_overlay_hide_ms))
                .setListener(new AnimatorListenerAdapter() {
                    @Override
                    public void onAnimationEnd(Animator animation) {
                        layoutInteraction.setVisibility(View.GONE);
                        layoutInteraction.animate().setListener(null);
                    }
                })
                .start();
    }

    public void showFeedback(String actionLabel, InteractionModels.InteractionResponse stats) {
        if (released) return;
        stopPulseAnimation();

        if (actionLabel != null) {
            tvFeedback.setText(resources.getString(R.string.interaction_feedback_selected_format, actionLabel));
        }

        // 显示反馈文字动画
        tvFeedback.setVisibility(View.VISIBLE);
        tvFeedback.setScaleX(0.5f);
        tvFeedback.setScaleY(0.5f);
        tvFeedback.setAlpha(0f);
        tvFeedback.animate()
                .scaleX(1.2f)
                .scaleY(1.2f)
                .alpha(1f)
                .setDuration(integer(R.integer.interaction_feedback_show_ms))
                .setInterpolator(new AnticipateOvershootInterpolator())
                .withEndAction(() -> {
                    tvFeedback.animate()
                            .alpha(0f)
                            .setStartDelay(integer(R.integer.interaction_feedback_hide_delay_ms))
                            .setDuration(integer(R.integer.interaction_feedback_hide_ms))
                            .withEndAction(() -> tvFeedback.setVisibility(View.GONE))
                            .start();
                })
                .start();

        // 更新统计信息并淡入显示
        tvInteractionStats.setText(buildStatsText(stats));
        tvInteractionStats.setVisibility(View.VISIBLE);
        tvInteractionStats.setAlpha(0f);
        tvInteractionStats.animate().alpha(1f).setDuration(integer(R.integer.interaction_stats_fade_ms)).start();

        setActionsEnabled(false);

        handler.postDelayed(() -> hide(), integer(R.integer.interaction_auto_hide_delay_ms));
    }

    public void showSimpleFeedback() {
        if (released) return;
        tvFeedback.setText(R.string.interaction_feedback_simple);
        tvFeedback.setVisibility(View.VISIBLE);
        tvFeedback.animate().alpha(1f).setDuration(integer(R.integer.interaction_simple_feedback_show_ms)).withEndAction(() -> {
            handler.postDelayed(() -> {
                tvFeedback.animate()
                        .alpha(0f)
                        .setDuration(integer(R.integer.interaction_simple_feedback_hide_ms))
                        .withEndAction(() -> tvFeedback.setVisibility(View.GONE))
                        .start();
                hide();
            }, integer(R.integer.interaction_simple_feedback_delay_ms));
        }).start();
    }

    public void setActionsEnabled(boolean enabled) {
        if (released) return;
        for (Button button : actionButtons) {
            button.setEnabled(enabled);
        }
    }

    private void bindActionButtons(
            HighlightPoint highlight,
            List<HighlightPoint.Action> actions,
            int actionCount,
            ActionListener listener
    ) {
        layoutActions.setOrientation(actionCount == 1 ? LinearLayout.VERTICAL : LinearLayout.HORIZONTAL);
        layoutActions.setGravity(Gravity.CENTER);

        for (int i = 0; i < actionButtons.size(); i++) {
            MaterialButton button = actionButtons.get(i);
            if (i < actionCount) {
                HighlightPoint.Action action = actions.get(i);
                activeActionLabels.put(action.getKey(), action.getLabel());
                bindActionButton(button, highlight, action, listener);
                applyButtonLayout(button, i, actionCount);
                button.setBackgroundTintList(ColorStateList.valueOf(actionColor(action, i)));
                button.setVisibility(View.VISIBLE);
            } else {
                button.setVisibility(View.GONE);
                button.setOnClickListener(null);
            }
        }
    }

    private void bindActionButton(
            MaterialButton button,
            HighlightPoint highlight,
            HighlightPoint.Action action,
            ActionListener listener
    ) {
        button.setText(buildActionText(action));
        button.setOnClickListener(v -> {
            setActionsEnabled(false);

            // 点击缩放动画
            v.animate()
                    .scaleX(0.9f)
                    .scaleY(0.9f)
                    .setDuration(integer(R.integer.interaction_button_press_ms))
                    .withEndAction(() -> {
                        v.animate()
                                .scaleX(1.0f)
                                .scaleY(1.0f)
                                .setDuration(integer(R.integer.interaction_button_press_ms))
                                .start();
                        listener.onAction(highlight.getId(), action.getKey(), action.getLabel());
                    })
                    .start();
        });
    }

    private void applyVisualStyle(HighlightPoint highlight, int actionCount) {
        String template = activeTemplate;
        String type = normalize(highlight.getType());
        int cardColor = color(R.color.interaction_card_default);
        int strokeColor = color(R.color.interaction_stroke_default);
        int[] buttonColors = defaultButtonColors;

        if ("poll".equals(template)) {
            cardColor = color(R.color.interaction_card_poll);
            strokeColor = color(R.color.interaction_stroke_poll);
            buttonColors = getColorArray(R.array.interaction_poll_button_colors);
        } else if ("tap-boost".equals(template)) {
            cardColor = color(R.color.interaction_card_tap_boost);
            strokeColor = color(R.color.interaction_stroke_tap_boost);
            buttonColors = getColorArray(R.array.interaction_tap_boost_button_colors);
        } else if ("twist".equals(type)) {
            cardColor = color(R.color.interaction_card_twist);
            strokeColor = color(R.color.interaction_stroke_twist);
        } else if ("slap-face".equals(type) || "revenge".equals(type)) {
            cardColor = color(R.color.interaction_card_slap_face);
            strokeColor = color(R.color.interaction_stroke_slap_face);
        } else if ("funny".equals(type)) {
            cardColor = color(R.color.interaction_card_funny);
            strokeColor = color(R.color.interaction_stroke_funny);
        }

        layoutInteraction.setCardBackgroundColor(cardColor);
        layoutInteraction.setStrokeColor(strokeColor);
        activeButtonColors = buttonColors;
        for (int i = 0; i < actionButtons.size(); i++) {
            actionButtons.get(i).setBackgroundTintList(ColorStateList.valueOf(buttonColors[i % buttonColors.length]));
            actionButtons.get(i).setTextSize(
                    TypedValue.COMPLEX_UNIT_PX,
                    resources.getDimension(actionCount >= 3 ? R.dimen.text_s : R.dimen.text_m)
            );
        }
    }

    private void applyButtonLayout(MaterialButton button, int index, int actionCount) {
        LinearLayout.LayoutParams params;
        if (actionCount == 1) {
            params = new LinearLayout.LayoutParams(
                    LinearLayout.LayoutParams.MATCH_PARENT,
                    dimensionPixelSize(R.dimen.interaction_action_button_height)
            );
            params.setMargins(0, 0, 0, 0);
        } else {
            params = new LinearLayout.LayoutParams(
                    0,
                    dimensionPixelSize(R.dimen.interaction_action_button_height),
                    1f
            );
            int start = index == 0 ? 0 : dimensionPixelSize(R.dimen.interaction_button_spacing);
            int end = index == actionCount - 1 ? 0 : dimensionPixelSize(R.dimen.interaction_button_spacing);
            params.setMargins(start, 0, end, 0);
        }
        button.setLayoutParams(params);
    }

    private String buildBadgeText(HighlightPoint highlight) {
        String template = activeTemplate;
        String type = normalize(highlight.getType());
        String prefix;
        if ("poll".equals(template)) {
            prefix = resources.getString(R.string.interaction_badge_poll);
        } else if ("tap-boost".equals(template)) {
            prefix = resources.getString(R.string.interaction_badge_tap_boost);
        } else if ("twist".equals(type)) {
            prefix = resources.getString(R.string.interaction_badge_twist);
        } else if ("slap-face".equals(type) || "revenge".equals(type)) {
            prefix = resources.getString(R.string.interaction_badge_slap_face);
        } else if ("funny".equals(type)) {
            prefix = resources.getString(R.string.interaction_badge_funny);
        } else {
            prefix = resources.getString(R.string.interaction_badge_default);
        }
        return prefix;
    }

    private String buildActionText(HighlightPoint.Action action) {
        return action.getLabel();
    }

    private int actionColor(HighlightPoint.Action action, int index) {
        String tone = normalize(action.getTone());
        if ("positive".equals(tone)) return color(R.color.interaction_tone_positive);
        if ("negative".equals(tone)) return color(R.color.interaction_tone_negative);
        if ("shocked".equals(tone)) return color(R.color.interaction_tone_shocked);
        if ("funny".equals(tone)) return color(R.color.interaction_tone_funny);
        if ("confused".equals(tone)) return color(R.color.interaction_tone_confused);
        if ("support".equals(tone)) return color(R.color.interaction_tone_support);
        if ("calm".equals(tone)) return color(R.color.interaction_tone_calm);
        return activeButtonColors[index % activeButtonColors.length];
    }

    private String iconText(String icon) {
        String normalizedIcon = normalize(icon);
        if ("heart".equals(normalizedIcon)) return resources.getString(R.string.interaction_icon_heart);
        if ("fire".equals(normalizedIcon)) return resources.getString(R.string.interaction_icon_fire);
        if ("shock".equals(normalizedIcon)) return resources.getString(R.string.interaction_icon_shock);
        if ("laugh".equals(normalizedIcon)) return resources.getString(R.string.interaction_icon_laugh);
        if ("question".equals(normalizedIcon)) return resources.getString(R.string.interaction_icon_question);
        if ("check".equals(normalizedIcon)) return resources.getString(R.string.interaction_icon_check);
        if ("boost".equals(normalizedIcon)) return resources.getString(R.string.interaction_icon_boost);
        return "";
    }

    private String buildStatsText(InteractionModels.InteractionResponse stats) {
        if (stats == null) return resources.getString(R.string.interaction_stats_received);
        if ("poll".equals(activeTemplate) && stats.getActions() != null && !stats.getActions().isEmpty()) {
            return resources.getString(
                    R.string.interaction_stats_poll_format,
                    buildTopActionText(stats.getActions()),
                    stats.getCount()
            );
        }
        if ("tap-boost".equals(activeTemplate)) {
            return resources.getString(R.string.interaction_stats_boost_format, stats.getCount());
        }
        return resources.getString(R.string.interaction_stats_default_format, stats.getCount());
    }

    private String buildTopActionText(Map<String, Integer> actions) {
        String topKey = "";
        int topCount = 0;
        int total = 0;
        for (Map.Entry<String, Integer> entry : actions.entrySet()) {
            int value = entry.getValue() == null ? 0 : entry.getValue();
            total += value;
            if (value > topCount) {
                topCount = value;
                topKey = entry.getKey();
            }
        }
        if (total <= 0 || topKey.isEmpty()) {
            return resources.getString(R.string.interaction_stats_no_ratio);
        }
        int percent = Math.round(topCount * 100f / total);
        String topLabel = activeActionLabels.containsKey(topKey) ? activeActionLabels.get(topKey) : topKey;
        return resources.getString(R.string.interaction_stats_top_action_format, topLabel, percent);
    }

    private String normalize(String value) {
        return value == null ? "" : value.trim().toLowerCase(Locale.US);
    }

    private int color(int colorResId) {
        return resources.getColor(colorResId, null);
    }

    private int dimensionPixelSize(int dimenResId) {
        return resources.getDimensionPixelSize(dimenResId);
    }

    private int integer(int integerResId) {
        return resources.getInteger(integerResId);
    }

    private int[] getColorArray(int arrayResId) {
        TypedArray array = resources.obtainTypedArray(arrayResId);
        int[] colors = new int[array.length()];
        for (int i = 0; i < array.length(); i++) {
            colors[i] = array.getColor(i, 0);
        }
        array.recycle();
        return colors;
    }

    private void startPulseAnimation() {
        if (pulseAnimator != null) pulseAnimator.cancel();
        pulseAnimator = ObjectAnimator.ofPropertyValuesHolder(
                tvInteractionTitle,
                PropertyValuesHolder.ofFloat("scaleX", 1.0f, 1.05f),
                PropertyValuesHolder.ofFloat("scaleY", 1.0f, 1.05f)
        );
        pulseAnimator.setDuration(integer(R.integer.interaction_pulse_ms));
        pulseAnimator.setRepeatCount(ObjectAnimator.INFINITE);
        pulseAnimator.setRepeatMode(ObjectAnimator.REVERSE);
        pulseAnimator.start();
    }

    private void stopPulseAnimation() {
        if (pulseAnimator != null) {
            pulseAnimator.cancel();
            tvInteractionTitle.setScaleX(1.0f);
            tvInteractionTitle.setScaleY(1.0f);
        }
    }

    public void release() {
        if (released) return;
        released = true;
        handler.removeCallbacksAndMessages(null);
        stopPulseAnimation();
        layoutInteraction.animate().cancel();
        tvFeedback.animate().cancel();
    }
}
