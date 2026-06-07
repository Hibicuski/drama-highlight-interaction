package com.warren.shortdrama.feature.episode_player;

import android.animation.Animator;
import android.animation.AnimatorListenerAdapter;
import android.animation.ObjectAnimator;
import android.animation.PropertyValuesHolder;
import android.graphics.drawable.GradientDrawable;
import android.content.res.ColorStateList;
import android.content.res.Resources;
import android.content.res.TypedArray;
import android.os.Handler;
import android.os.Looper;
import android.util.TypedValue;
import android.view.Gravity;
import android.view.View;
import android.view.ViewGroup;
import android.view.animation.DecelerateInterpolator;
import android.widget.Button;
import android.widget.LinearLayout;
import android.widget.TextView;

import com.google.android.material.card.MaterialCardView;
import com.google.android.material.button.MaterialButton;
import com.warren.shortdrama.R;
import com.warren.shortdrama.core.model.HighlightPoint;
import com.warren.shortdrama.core.model.InteractionModels;

import java.util.ArrayList;
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
    private final ViewGroup rootContainer;
    private final int[] defaultButtonColors;
    private final MaterialCardView layoutInteraction;
    private final TextView tvInteractionBadge;
    private final TextView tvInteractionTitle;
    private final LinearLayout layoutActions;
    private final List<MaterialButton> actionButtons;
    private final TextView tvInteractionStats;
    private final Handler handler = new Handler(Looper.getMainLooper());

    private ObjectAnimator pulseAnimator;
    private boolean released;
    private String activeTemplate = "";
    private String activeEffect = "";
    private int[] activeButtonColors;
    private final List<View> effectViews = new ArrayList<>();
    private final Map<String, String> activeActionLabels = new HashMap<>();
    private final Map<String, MaterialButton> activeActionButtons = new HashMap<>();

    public InteractionOverlayController(View root) {
        resources = root.getResources();
        rootContainer = root instanceof ViewGroup ? (ViewGroup) root : null;
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
        activeActionButtons.clear();
        layoutActions.animate().cancel();
        layoutActions.setAlpha(1f);
        layoutActions.setTranslationY(0f);
        layoutActions.setScaleX(1f);
        layoutActions.setScaleY(1f);

        handler.removeCallbacksAndMessages(null);
        layoutInteraction.animate().cancel();
        clearTransientEffects();
        stopPulseAnimation();

        applyVisualStyle(highlight, actionCount);
        tvInteractionBadge.setText(buildBadgeText(highlight));
        tvInteractionTitle.setText(highlight.getPayload().getTitle());
        bindActionButtons(highlight, actions, actionCount, listener);

        tvInteractionStats.animate().cancel();
        tvInteractionStats.setAlpha(1f);
        tvInteractionStats.setScaleX(1f);
        tvInteractionStats.setScaleY(1f);
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

        playEntryEffect();
        return true;
    }

    public void hide() {
        if (released) return;
        stopPulseAnimation();
        clearTransientEffects();
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

    public void showFeedback(String actionKey, InteractionModels.InteractionResponse stats) {
        if (released) return;
        stopPulseAnimation();

        tvInteractionStats.setText(buildStatsText(stats));
        tvInteractionStats.setVisibility(View.VISIBLE);
        tvInteractionStats.setAlpha(0f);

        setActionsEnabled(false);
        playFeedbackEffect(actionKey);

        handler.postDelayed(() -> hide(), integer(R.integer.interaction_auto_hide_delay_ms));
    }

    public void showSimpleFeedback() {
        if (released) return;
        stopPulseAnimation();
        tvInteractionStats.setText(R.string.interaction_feedback_simple);
        tvInteractionStats.setVisibility(View.VISIBLE);
        tvInteractionStats.setAlpha(0f);
        setActionsEnabled(false);
        playFeedbackEffect("");
        handler.postDelayed(() -> hide(), integer(R.integer.interaction_auto_hide_delay_ms));
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
                activeActionButtons.put(action.getKey(), button);
                button.animate().cancel();
                button.setAlpha(1f);
                button.setTranslationY(0f);
                button.setScaleX(1f);
                button.setScaleY(1f);
                bindActionButton(button, highlight, action, listener);
                applyButtonLayout(button, i, actionCount);
                button.setBackgroundTintList(ColorStateList.valueOf(actionColor(action, i)));
                button.setVisibility(View.VISIBLE);
            } else {
                button.animate().cancel();
                button.setVisibility(View.GONE);
                button.setOnClickListener(null);
                button.setIcon(null);
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
        button.setTextColor(color(R.color.white));
        applyActionIcon(button, action);
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
            MaterialButton button = actionButtons.get(i);
            button.setBackgroundTintList(ColorStateList.valueOf(buttonColors[i % buttonColors.length]));
            button.setTextSize(
                    TypedValue.COMPLEX_UNIT_PX,
                    resources.getDimension(actionCount >= 3 ? R.dimen.text_m : R.dimen.text_l)
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

    private void applyActionIcon(MaterialButton button, HighlightPoint.Action action) {
        int iconResId = actionIconResId(action.getIcon());
        if (iconResId == 0) {
            button.setIcon(null);
            return;
        }
        button.setIconResource(iconResId);
        button.setIconTint(ColorStateList.valueOf(color(R.color.white)));
        button.setIconGravity(MaterialButton.ICON_GRAVITY_TEXT_START);
        button.setIconSize(dimensionPixelSize(R.dimen.interaction_button_icon_size));
        button.setIconPadding(dimensionPixelSize(R.dimen.interaction_button_icon_padding));
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

    private int actionIconResId(String icon) {
        String normalizedIcon = normalize(icon);
        if ("heart".equals(normalizedIcon)) return R.drawable.ic_interaction_heart;
        if ("fire".equals(normalizedIcon)) return R.drawable.ic_interaction_fire;
        if ("shock".equals(normalizedIcon)) return R.drawable.ic_interaction_shock;
        if ("laugh".equals(normalizedIcon)) return R.drawable.ic_interaction_laugh;
        if ("question".equals(normalizedIcon)) return R.drawable.ic_interaction_question;
        if ("check".equals(normalizedIcon)) return R.drawable.ic_interaction_check;
        if ("boost".equals(normalizedIcon)) return R.drawable.ic_interaction_boost;
        return 0;
    }

    private void playEntryEffect() {
        if ("ratio-reveal".equals(activeEffect)) {
            playRatioRevealEffect();
            return;
        }
        if ("pulse".equals(activeEffect)) {
            startPulseAnimation();
        }
    }

    private void playFeedbackEffect(String actionKey) {
        MaterialButton selectedButton = activeActionButtons.get(actionKey);
        clearTransientEffects();
        playSelectedButtonEffect(selectedButton);
        playImpactRingEffect(selectedButton == null ? layoutInteraction : selectedButton);
        playStatsRevealEffect();
        if ("particle-burst".equals(activeEffect)) {
            layoutInteraction.post(() -> playParticleBurstEffect(selectedButton));
            return;
        }
        if ("ratio-reveal".equals(activeEffect)) {
            playRatioRevealEffect();
            return;
        }
        if ("pulse".equals(activeEffect)) {
            playButtonPulseEffect(selectedButton);
        }
    }

    private void playSelectedButtonEffect(MaterialButton selectedButton) {
        for (MaterialButton button : actionButtons) {
            button.animate().cancel();
            if (button == selectedButton) {
                button.setAlpha(1f);
                button.animate()
                        .scaleX(1.12f)
                        .scaleY(1.12f)
                        .setDuration(220)
                        .setInterpolator(new DecelerateInterpolator())
                        .withEndAction(() -> button.animate()
                                .scaleX(1f)
                                .scaleY(1f)
                                .setDuration(260)
                                .setInterpolator(new DecelerateInterpolator())
                                .start())
                        .start();
            } else if (button.getVisibility() == View.VISIBLE) {
                button.animate().alpha(0.35f).setDuration(260).start();
            }
        }
    }

    private void playButtonPulseEffect(MaterialButton selectedButton) {
        if (selectedButton == null) {
            startPulseAnimation();
            return;
        }
        ObjectAnimator animator = ObjectAnimator.ofPropertyValuesHolder(
                selectedButton,
                PropertyValuesHolder.ofFloat("scaleX", 1f, 1.18f, 0.96f, 1.12f, 1f),
                PropertyValuesHolder.ofFloat("scaleY", 1f, 1.18f, 0.96f, 1.12f, 1f)
        );
        animator.setDuration(780);
        animator.setInterpolator(new DecelerateInterpolator());
        animator.start();
    }

    private void playImpactRingEffect(View originView) {
        if (released || rootContainer == null || originView == null || originView.getWidth() == 0) return;

        int[] rootLocation = new int[2];
        int[] originLocation = new int[2];
        rootContainer.getLocationOnScreen(rootLocation);
        originView.getLocationOnScreen(originLocation);

        int width = originView.getWidth() + dp(22);
        int height = originView.getHeight() + dp(22);
        float startX = originLocation[0] - rootLocation[0] + originView.getWidth() / 2f - width / 2f;
        float startY = originLocation[1] - rootLocation[1] + originView.getHeight() / 2f - height / 2f;

        View ring = new View(rootContainer.getContext());
        GradientDrawable background = new GradientDrawable();
        background.setShape(GradientDrawable.RECTANGLE);
        background.setCornerRadius(dp(18));
        background.setColor(0x00FFFFFF);
        background.setStroke(dp(3), color(R.color.white));
        ring.setBackground(background);
        ring.setAlpha(0.92f);
        ring.setScaleX(0.86f);
        ring.setScaleY(0.86f);

        rootContainer.addView(ring, new ViewGroup.LayoutParams(width, height));
        effectViews.add(ring);
        ring.setX(startX);
        ring.setY(startY);
        ring.animate()
                .scaleX(1.72f)
                .scaleY(1.72f)
                .alpha(0f)
                .setDuration(820)
                .setInterpolator(new DecelerateInterpolator())
                .withEndAction(() -> removeEffectView(ring))
                .start();
    }

    private void playStatsRevealEffect() {
        tvInteractionStats.animate().cancel();
        tvInteractionStats.setScaleX(0.82f);
        tvInteractionStats.setScaleY(0.82f);
        tvInteractionStats.animate()
                .alpha(1f)
                .scaleX(1.08f)
                .scaleY(1.08f)
                .setDuration(integer(R.integer.interaction_stats_fade_ms))
                .setInterpolator(new DecelerateInterpolator())
                .withEndAction(() -> tvInteractionStats.animate()
                        .scaleX(1f)
                        .scaleY(1f)
                        .setDuration(260)
                        .setInterpolator(new DecelerateInterpolator())
                        .start())
                .start();
    }

    private void playParticleBurstEffect(View originView) {
        if (released || rootContainer == null || layoutInteraction.getWidth() == 0) return;

        int[] rootLocation = new int[2];
        int[] originLocation = new int[2];
        rootContainer.getLocationOnScreen(rootLocation);
        View origin = originView == null ? layoutInteraction : originView;
        origin.getLocationOnScreen(originLocation);

        float centerX = originLocation[0] - rootLocation[0] + origin.getWidth() / 2f;
        float centerY = originLocation[1] - rootLocation[1] + origin.getHeight() / 2f;
        int[] particleColors = {
                color(R.color.white),
                color(R.color.interaction_effect_particle_warm),
                color(R.color.interaction_effect_particle_cool)
        };

        for (int i = 0; i < 32; i++) {
            int size = dp(8 + (i % 5) * 2);
            View particle = new View(rootContainer.getContext());
            GradientDrawable background = new GradientDrawable();
            background.setShape(GradientDrawable.OVAL);
            background.setColor(particleColors[i % particleColors.length]);
            particle.setBackground(background);
            particle.setAlpha(1f);
            particle.setScaleX(0.55f);
            particle.setScaleY(0.55f);

            ViewGroup.LayoutParams params = new ViewGroup.LayoutParams(size, size);
            rootContainer.addView(particle, params);
            effectViews.add(particle);

            float startX = centerX - size / 2f;
            float startY = centerY - size / 2f;
            particle.setX(startX);
            particle.setY(startY);

            double angle = -Math.PI + i * Math.PI * 2 / 32;
            float distance = dp(88 + (i % 7) * 14);
            float targetX = (float) Math.cos(angle) * distance;
            float targetY = (float) Math.sin(angle) * distance - dp(10);
            particle.animate()
                    .x(startX + targetX)
                    .y(startY + targetY)
                    .scaleX(1.5f)
                    .scaleY(1.5f)
                    .alpha(0f)
                    .setStartDelay(i * 8L)
                    .setDuration(1200)
                    .setInterpolator(new DecelerateInterpolator())
                    .withEndAction(() -> removeEffectView(particle))
                    .start();
        }
    }

    private void playRatioRevealEffect() {
        layoutActions.animate().cancel();
        layoutActions.setAlpha(0.48f);
        layoutActions.setTranslationY(dp(18));
        layoutActions.setScaleX(0.9f);
        layoutActions.setScaleY(0.9f);
        layoutActions.animate()
                .alpha(1f)
                .translationY(0f)
                .scaleX(1f)
                .scaleY(1f)
                .setDuration(680)
                .setInterpolator(new DecelerateInterpolator())
                .start();

        for (int i = 0; i < actionButtons.size(); i++) {
            MaterialButton button = actionButtons.get(i);
            if (button.getVisibility() != View.VISIBLE) continue;
            button.animate().cancel();
            button.setAlpha(0.42f);
            button.setTranslationY(dp(18));
            button.setScaleX(0.86f);
            button.setScaleY(0.86f);
            button.animate()
                    .alpha(1f)
                    .translationY(0f)
                    .scaleX(1f)
                    .scaleY(1f)
                    .setStartDelay(120L * i)
                    .setDuration(560)
                    .setInterpolator(new DecelerateInterpolator())
                    .start();
        }
    }

    private void clearTransientEffects() {
        for (View view : new ArrayList<>(effectViews)) {
            view.animate().cancel();
            removeEffectView(view);
        }
    }

    private void removeEffectView(View view) {
        effectViews.remove(view);
        if (rootContainer != null && view.getParent() == rootContainer) {
            rootContainer.removeView(view);
        }
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

    private int dp(int value) {
        return Math.round(TypedValue.applyDimension(
                TypedValue.COMPLEX_UNIT_DIP,
                value,
                resources.getDisplayMetrics()
        ));
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
        clearTransientEffects();
        stopPulseAnimation();
        layoutInteraction.animate().cancel();
    }
}
