package com.warren.shortdrama.feature.episode_player;

import android.os.Bundle;
import android.widget.TextView;

import androidx.appcompat.app.AppCompatActivity;
import androidx.core.content.IntentCompat;
import androidx.media3.ui.PlayerView;

import com.warren.shortdrama.R;
import com.warren.shortdrama.core.interaction.InteractionRepository;
import com.warren.shortdrama.core.interaction.InteractionScheduler;
import com.warren.shortdrama.core.model.Drama;
import com.warren.shortdrama.core.model.Episode;
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
    private int currentEpisodeId = -1;
    private boolean playbackReady;
    private boolean resumed;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(R.layout.activity_main);

        interactionRepository = new InteractionRepository();
        overlayController = new InteractionOverlayController(findViewById(R.id.main));

        PlayerView playerView = findViewById(R.id.player_view);
        tvTitle = findViewById(R.id.tv_player_drama_title);

        Drama drama = IntentCompat.getSerializableExtra(getIntent(), "drama", Drama.class);
        Episode episode = IntentCompat.getSerializableExtra(getIntent(), "episode", Episode.class);
        if (drama != null) {
            String episodeTitle = episode == null ? "Episode 1" : episode.getTitle();
            tvTitle.setText(drama.getTitle() + " - " + episodeTitle);
        }

        String videoUrl = episode == null ? "" : episode.getVideoUrl();
        dramaPlayer = new DramaPlayer(this, playerView, videoUrl);

        if (episode != null) {
            currentEpisodeId = episode.getId();
            fetchManifest(episode.getId());
        } else {
            allowPlayback();
        }
    }

    private void fetchManifest(int episodeId) {
        interactionRepository.fetchManifest(episodeId, new InteractionRepository.ManifestCallback() {
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
        scheduler = new InteractionScheduler(dramaPlayer, manifest, new InteractionScheduler.InteractionListener() {
            @Override
            public boolean onShowHighlight(HighlightPoint highlight) {
                return overlayController.showHighlight(highlight, EpisodePlayerActivity.this::reportInteraction);
            }

            @Override
            public void onHideHighlight(String highlightId) {
                runOnUiThread(() -> overlayController.hide());
            }
        });
        if (resumed) scheduler.start();
    }

    private void allowPlayback() {
        playbackReady = true;
        if (resumed && dramaPlayer != null) dramaPlayer.play();
    }

    private void reportInteraction(String highlightId, String actionKey, String actionLabel) {
        overlayController.setActionsEnabled(false);

        interactionRepository.reportInteraction(currentEpisodeId, highlightId, actionKey, new InteractionRepository.ReportCallback() {
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
