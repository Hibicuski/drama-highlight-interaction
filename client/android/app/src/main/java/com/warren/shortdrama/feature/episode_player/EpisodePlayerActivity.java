package com.warren.shortdrama.feature.episode_player;

import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.view.View;
import android.widget.Button;
import android.widget.TextView;

import androidx.appcompat.app.AppCompatActivity;
import androidx.core.content.IntentCompat;
import androidx.media3.ui.PlayerView;

import com.warren.shortdrama.R;
import com.warren.shortdrama.core.interaction.InteractionScheduler;
import com.warren.shortdrama.core.model.Drama;
import com.warren.shortdrama.core.model.Episode;
import com.warren.shortdrama.core.model.HighlightManifest;
import com.warren.shortdrama.core.model.HighlightPoint;
import com.warren.shortdrama.core.model.InteractionModels;
import com.warren.shortdrama.core.network.ApiService;
import com.warren.shortdrama.core.network.RetrofitClient;
import com.warren.shortdrama.core.player.DramaPlayer;

import java.util.List;

import retrofit2.Call;
import retrofit2.Callback;
import retrofit2.Response;

public class EpisodePlayerActivity extends AppCompatActivity {

    private DramaPlayer dramaPlayer;
    private View layoutInteraction;
    private TextView tvInteractionTitle;
    private Button btnAction1;
    private Button btnAction2;
    private TextView tvInteractionStats;
    private TextView tvFeedback;
    private TextView tvTitle;

    private InteractionScheduler scheduler;
    private ApiService apiService;
    private int currentEpisodeId = -1;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(R.layout.activity_main);

        apiService = RetrofitClient.api();

        PlayerView playerView = findViewById(R.id.player_view);
        layoutInteraction = findViewById(R.id.layout_interaction);
        tvInteractionTitle = findViewById(R.id.tv_interaction_title);
        btnAction1 = findViewById(R.id.btn_action_1);
        btnAction2 = findViewById(R.id.btn_action_2);
        tvInteractionStats = findViewById(R.id.tv_interaction_stats);
        tvFeedback = findViewById(R.id.tv_interaction_feedback);
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
        }
    }

    private void fetchManifest(int episodeId) {
        apiService.getManifest(episodeId).enqueue(new Callback<HighlightManifest>() {
            @Override
            public void onResponse(Call<HighlightManifest> call, Response<HighlightManifest> response) {
                if (response.isSuccessful() && response.body() != null) {
                    setupScheduler(response.body());
                }
            }

            @Override
            public void onFailure(Call<HighlightManifest> call, Throwable t) {
                // Ignore for now
            }
        });
    }

    private void setupScheduler(HighlightManifest manifest) {
        scheduler = new InteractionScheduler(dramaPlayer, manifest, new InteractionScheduler.InteractionListener() {
            @Override
            public boolean onShowHighlight(HighlightPoint highlight) {
                return showHighlightUI(highlight);
            }

            @Override
            public void onHideHighlight(String highlightId) {
                runOnUiThread(() -> layoutInteraction.setVisibility(View.GONE));
            }
        });
        scheduler.start();
    }

    private boolean showHighlightUI(HighlightPoint highlight) {
        if (highlight == null || highlight.getPayload() == null || highlight.getPayload().getActions() == null) {
            return false;
        }

        List<HighlightPoint.Action> actions = highlight.getPayload().getActions();
        if (actions.isEmpty()) {
            return false;
        }

        tvInteractionTitle.setText(highlight.getPayload().getTitle());

        // Handle first action
        HighlightPoint.Action action1 = actions.get(0);
        btnAction1.setText(action1.getLabel());
        btnAction1.setVisibility(View.VISIBLE);
        btnAction1.setOnClickListener(v -> reportInteraction(highlight.getId(), action1.getKey()));

        // Handle second action if exists
        if (actions.size() >= 2) {
            HighlightPoint.Action action2 = actions.get(1);
            btnAction2.setText(action2.getLabel());
            btnAction2.setVisibility(View.VISIBLE);
            btnAction2.setOnClickListener(v -> reportInteraction(highlight.getId(), action2.getKey()));
        } else {
            btnAction2.setVisibility(View.GONE);
        }

        tvInteractionStats.setVisibility(View.GONE);
        layoutInteraction.setVisibility(View.VISIBLE);
        btnAction1.setEnabled(true);
        btnAction2.setEnabled(true);
        return true;
    }

    private void reportInteraction(String highlightId, String actionKey) {
        // Disable buttons immediately to prevent double-clicking
        btnAction1.setEnabled(false);
        btnAction2.setEnabled(false);

        InteractionModels.InteractionRequest request = new InteractionModels.InteractionRequest(currentEpisodeId, highlightId, actionKey);
        apiService.reportInteraction(request).enqueue(new Callback<InteractionModels.InteractionResponse>() {
            @Override
            public void onResponse(Call<InteractionModels.InteractionResponse> call, Response<InteractionModels.InteractionResponse> response) {
                if (response.isSuccessful() && response.body() != null) {
                    showFeedback(response.body());
                } else {
                    // Handle server errors (e.g., 400, 500)
                    showSimpleFeedback();
                }
            }

            @Override
            public void onFailure(Call<InteractionModels.InteractionResponse> call, Throwable t) {
                // Handle network failures
                showSimpleFeedback();
            }
        });
    }

    private void showFeedback(InteractionModels.InteractionResponse stats) {
        tvFeedback.setVisibility(View.VISIBLE);
        tvInteractionStats.setText("Total interactions: " + stats.getCount());
        tvInteractionStats.setVisibility(View.VISIBLE);
        btnAction1.setEnabled(false);
        btnAction2.setEnabled(false);

        new Handler(Looper.getMainLooper()).postDelayed(() -> {
            tvFeedback.setVisibility(View.GONE);
            layoutInteraction.setVisibility(View.GONE);
            btnAction1.setEnabled(true);
            btnAction2.setEnabled(true);
        }, 2000);
    }

    private void showSimpleFeedback() {
        tvFeedback.setVisibility(View.VISIBLE);
        new Handler(Looper.getMainLooper()).postDelayed(() -> tvFeedback.setVisibility(View.GONE), 2000);
        layoutInteraction.setVisibility(View.GONE);
    }

    @Override
    protected void onPause() {
        super.onPause();
        if (dramaPlayer != null) dramaPlayer.pause();
        if (scheduler != null) scheduler.stop();
    }

    @Override
    protected void onResume() {
        super.onResume();
        if (dramaPlayer != null) dramaPlayer.play();
        if (scheduler != null) scheduler.start();
    }

    @Override
    protected void onDestroy() {
        super.onDestroy();
        if (dramaPlayer != null) dramaPlayer.release();
        if (scheduler != null) scheduler.stop();
    }
}
