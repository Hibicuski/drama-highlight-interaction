package com.warren.shortdrama.feature.episode_player;

import android.animation.Animator;
import android.animation.AnimatorListenerAdapter;
import android.animation.ObjectAnimator;
import android.animation.PropertyValuesHolder;
import android.os.Handler;
import android.os.Looper;
import android.view.View;
import android.view.animation.AnticipateOvershootInterpolator;
import android.view.animation.DecelerateInterpolator;
import android.widget.Button;
import android.widget.TextView;

import com.warren.shortdrama.R;
import com.warren.shortdrama.core.model.HighlightPoint;
import com.warren.shortdrama.core.model.InteractionModels;

import java.util.List;

public class InteractionOverlayController {

    public interface ActionListener {
        void onAction(String highlightId, String actionKey, String actionLabel);
    }

    private final View layoutInteraction;
    private final TextView tvInteractionTitle;
    private final Button btnAction1;
    private final Button btnAction2;
    private final TextView tvInteractionStats;
    private final TextView tvFeedback;
    private final Handler handler = new Handler(Looper.getMainLooper());

    private ObjectAnimator pulseAnimator;
    private boolean released;

    public InteractionOverlayController(View root) {
        layoutInteraction = root.findViewById(R.id.layout_interaction);
        tvInteractionTitle = root.findViewById(R.id.tv_interaction_title);
        btnAction1 = root.findViewById(R.id.btn_action_1);
        btnAction2 = root.findViewById(R.id.btn_action_2);
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

        handler.removeCallbacksAndMessages(null);
        layoutInteraction.animate().cancel();
        tvFeedback.animate().cancel();
        tvFeedback.setVisibility(View.GONE);

        tvInteractionTitle.setText(highlight.getPayload().getTitle());
        bindActionButton(btnAction1, highlight, actions.get(0), listener);

        if (actions.size() >= 2) {
            bindActionButton(btnAction2, highlight, actions.get(1), listener);
            btnAction2.setVisibility(View.VISIBLE);
        } else {
            btnAction2.setVisibility(View.GONE);
        }

        tvInteractionStats.setVisibility(View.GONE);
        setActionsEnabled(true);

        // --- 动画效果 ---
        layoutInteraction.setVisibility(View.VISIBLE);
        layoutInteraction.setAlpha(0f);
        layoutInteraction.setTranslationY(100f);
        layoutInteraction.animate()
                .alpha(1f)
                .translationY(0f)
                .setDuration(500)
                .setInterpolator(new DecelerateInterpolator())
                .start();

        startPulseAnimation();
        return true;
    }

    public void hide() {
        if (released) return;
        stopPulseAnimation();
        layoutInteraction.animate()
                .alpha(0f)
                .translationY(100f)
                .setDuration(400)
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
            tvFeedback.setText("已选: " + actionLabel);
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
                .setDuration(400)
                .setInterpolator(new AnticipateOvershootInterpolator())
                .withEndAction(() -> {
                    tvFeedback.animate()
                            .alpha(0f)
                            .setStartDelay(1000)
                            .setDuration(500)
                            .withEndAction(() -> tvFeedback.setVisibility(View.GONE))
                            .start();
                })
                .start();

        // 更新统计信息并淡入显示
        tvInteractionStats.setText("已有 " + stats.getCount() + " 人参与互动");
        tvInteractionStats.setVisibility(View.VISIBLE);
        tvInteractionStats.setAlpha(0f);
        tvInteractionStats.animate().alpha(1f).setDuration(500).start();

        setActionsEnabled(false);

        handler.postDelayed(() -> hide(), 2500);
    }

    public void showSimpleFeedback() {
        if (released) return;
        tvFeedback.setText("感谢参与！");
        tvFeedback.setVisibility(View.VISIBLE);
        tvFeedback.animate().alpha(1f).setDuration(300).withEndAction(() -> {
            handler.postDelayed(() -> {
                tvFeedback.animate()
                        .alpha(0f)
                        .setDuration(300)
                        .withEndAction(() -> tvFeedback.setVisibility(View.GONE))
                        .start();
                hide();
            }, 1000);
        }).start();
    }

    public void setActionsEnabled(boolean enabled) {
        if (released) return;
        btnAction1.setEnabled(enabled);
        btnAction2.setEnabled(enabled);
    }

    private void bindActionButton(
            Button button,
            HighlightPoint highlight,
            HighlightPoint.Action action,
            ActionListener listener
    ) {
        button.setText(action.getLabel());
        button.setVisibility(View.VISIBLE);
        button.setOnClickListener(v -> {
            setActionsEnabled(false);

            // 点击缩放动画
            v.animate()
                    .scaleX(0.9f)
                    .scaleY(0.9f)
                    .setDuration(100)
                    .withEndAction(() -> {
                        v.animate().scaleX(1.0f).scaleY(1.0f).setDuration(100).start();
                        listener.onAction(highlight.getId(), action.getKey(), action.getLabel());
                    })
                    .start();
        });
    }

    private void startPulseAnimation() {
        if (pulseAnimator != null) pulseAnimator.cancel();
        pulseAnimator = ObjectAnimator.ofPropertyValuesHolder(
                tvInteractionTitle,
                PropertyValuesHolder.ofFloat("scaleX", 1.0f, 1.05f),
                PropertyValuesHolder.ofFloat("scaleY", 1.0f, 1.05f)
        );
        pulseAnimator.setDuration(800);
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
