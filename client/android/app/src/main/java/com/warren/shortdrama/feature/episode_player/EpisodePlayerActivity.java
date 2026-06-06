package com.warren.shortdrama.feature.episode_player;

import android.os.Bundle;
import android.widget.TextView;

import androidx.appcompat.app.AppCompatActivity;
import androidx.media3.ui.PlayerView;

import com.warren.shortdrama.R;
import com.warren.shortdrama.core.interaction.InteractionRepository;
import com.warren.shortdrama.core.interaction.InteractionScheduler;
import com.warren.shortdrama.core.model.HighlightManifest;
import com.warren.shortdrama.core.model.HighlightPoint;
import com.warren.shortdrama.core.model.InteractionModels;
import com.warren.shortdrama.core.player.DramaPlayer;

public class EpisodePlayerActivity extends AppCompatActivity {

    private DramaPlayer dramaPlayer;
    private TextView tvTitle;

    private InteractionScheduler scheduler;
    private InteractionRepository interactionRepository;
    private InteractionOverlayController overlayController;
    private String currentContentId = "";
    private boolean playbackReady;
    private boolean resumed;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(R.layout.activity_main);

        interactionRepository = new InteractionRepository(this);
        overlayController = new InteractionOverlayController(findViewById(R.id.main));

        PlayerView playerView = findViewById(R.id.player_view);
        tvTitle = findViewById(R.id.tv_player_drama_title);

        String dramaTitle = getIntent().getStringExtra(getString(R.string.extra_drama_title));
        String episodeTitle = getIntent().getStringExtra(getString(R.string.extra_episode_title));
        if (episodeTitle == null || episodeTitle.isEmpty()) {
            episodeTitle = getString(R.string.player_default_episode_title);
        }
        if (dramaTitle != null && !dramaTitle.isEmpty()) {
            tvTitle.setText(getString(R.string.player_title_format, dramaTitle, episodeTitle));
        } else {
            tvTitle.setText(episodeTitle);
        }

        String videoUrl = getIntent().getStringExtra(getString(R.string.extra_episode_video_url));
        dramaPlayer = new DramaPlayer(this, playerView, videoUrl);

        String contentId = getIntent().getStringExtra(getString(R.string.extra_episode_content_id));
        if (contentId != null && !contentId.isEmpty()) {
            currentContentId = contentId;
            fetchManifest(contentId);
        } else {
            allowPlayback();
        }
    }

    private void fetchManifest(String contentId) {
        interactionRepository.fetchManifest(contentId, new InteractionRepository.ManifestCallback() {
            @Override
            public void onSuccess(HighlightManifest manifest) {
                setupScheduler(manifest);
                allowPlayback();
            }

            @Override
            public void onError(Throwable error) {
                allowPlayback();
            }
        });
    }

    private void setupScheduler(HighlightManifest manifest) {
        scheduler = new InteractionScheduler(
                dramaPlayer,
                manifest,
                new InteractionScheduler.InteractionListener() {
                    @Override
                    public boolean onShowHighlight(HighlightPoint highlight) {
                        return overlayController.showHighlight(highlight, EpisodePlayerActivity.this::reportInteraction);
                    }

                    @Override
                    public void onHideHighlight(String highlightId) {
                        runOnUiThread(() -> overlayController.hide());
                    }
                },
                getResources().getInteger(R.integer.interaction_scheduler_tick_ms)
        );
        if (resumed) scheduler.start();
    }

    private void allowPlayback() {
        playbackReady = true;
        if (resumed && dramaPlayer != null) dramaPlayer.play();
    }

    private void reportInteraction(String highlightId, String actionKey, String actionLabel) {
        overlayController.setActionsEnabled(false);

        interactionRepository.reportInteraction(currentContentId, highlightId, actionKey, new InteractionRepository.ReportCallback() {
            @Override
            public void onSuccess(InteractionModels.InteractionResponse stats) {
                overlayController.showFeedback(actionLabel, stats);
            }

            @Override
            public void onError(Throwable error) {
                overlayController.showSimpleFeedback();
            }
        });
    }

    @Override
    protected void onPause() {
        super.onPause();
        resumed = false;
        if (dramaPlayer != null) dramaPlayer.pause();
        if (scheduler != null) scheduler.stop();
    }

    @Override
    protected void onResume() {
        super.onResume();
        resumed = true;
        if (playbackReady && dramaPlayer != null) dramaPlayer.play();
        if (scheduler != null) scheduler.start();
    }

    @Override
    protected void onDestroy() {
        super.onDestroy();
        if (scheduler != null) scheduler.stop();
        if (interactionRepository != null) interactionRepository.cancelAll();
        if (overlayController != null) overlayController.release();
        if (dramaPlayer != null) dramaPlayer.release();
    }
}
