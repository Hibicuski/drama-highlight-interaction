package com.warren.shortdrama.feature.episode_list;

import android.content.Intent;
import android.os.Bundle;
import android.view.View;
import android.widget.TextView;
import android.widget.Toast;

import androidx.appcompat.app.AppCompatActivity;
import androidx.recyclerview.widget.LinearLayoutManager;
import androidx.recyclerview.widget.RecyclerView;

import com.warren.shortdrama.R;
import com.warren.shortdrama.core.model.Episode;
import com.warren.shortdrama.core.network.RetrofitClient;
import com.warren.shortdrama.feature.episode_player.EpisodePlayerActivity;

import java.util.List;

import retrofit2.Call;
import retrofit2.Callback;
import retrofit2.Response;

public class EpisodeListActivity extends AppCompatActivity {

    private int dramaId;
    private String dramaTitle;
    private RecyclerView rvEpisodeList;
    private TextView tvStatus;
    private EpisodeAdapter adapter;
    private Call<List<Episode>> episodesCall;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(R.layout.activity_episode_list);

        dramaId = getIntent().getIntExtra(getString(R.string.extra_drama_id), -1);
        dramaTitle = getIntent().getStringExtra(getString(R.string.extra_drama_title));
        String dramaDescription = getIntent().getStringExtra(getString(R.string.extra_drama_description));
        if (dramaId < 0) {
            finish();
            return;
        }

        TextView tvTitle = findViewById(R.id.tv_drama_title_header);
        TextView tvDesc = findViewById(R.id.tv_drama_description);
        tvTitle.setText(dramaTitle == null ? "" : dramaTitle);
        tvDesc.setText(dramaDescription == null ? "" : dramaDescription);

        rvEpisodeList = findViewById(R.id.rv_episode_list);
        tvStatus = findViewById(R.id.tv_status);
        rvEpisodeList.setLayoutManager(new LinearLayoutManager(this));

        adapter = new EpisodeAdapter(this::openPlayer);
        rvEpisodeList.setAdapter(adapter);

        loadEpisodes();
    }

    private void loadEpisodes() {
        tvStatus.setVisibility(View.VISIBLE);
        tvStatus.setText(R.string.status_loading_episodes);
        if (episodesCall != null) episodesCall.cancel();
        episodesCall = RetrofitClient.api(this).getEpisodes(dramaId);
        episodesCall.enqueue(new Callback<List<Episode>>() {
            @Override
            public void onResponse(Call<List<Episode>> call, Response<List<Episode>> response) {
                if (call.isCanceled()) return;
                tvStatus.setVisibility(View.GONE);
                if (response.isSuccessful() && response.body() != null) {
                    adapter.submitList(response.body());
                } else {
                    Toast.makeText(EpisodeListActivity.this, R.string.error_load_episodes_failed, Toast.LENGTH_SHORT).show();
                }
            }

            @Override
            public void onFailure(Call<List<Episode>> call, Throwable t) {
                if (call.isCanceled()) return;
                tvStatus.setVisibility(View.GONE);
                Toast.makeText(EpisodeListActivity.this, R.string.error_network, Toast.LENGTH_SHORT).show();
            }
        });
    }

    private void openPlayer(Episode episode) {
        Intent intent = new Intent(this, EpisodePlayerActivity.class);
        intent.putExtra(getString(R.string.extra_drama_title), dramaTitle);
        intent.putExtra(getString(R.string.extra_episode_content_id), episode.getContentId());
        intent.putExtra(getString(R.string.extra_episode_title), episode.getTitle());
        intent.putExtra(getString(R.string.extra_episode_video_url), episode.getVideoUrl());
        startActivity(intent);
    }

    @Override
    protected void onDestroy() {
        super.onDestroy();
        if (episodesCall != null) episodesCall.cancel();
    }
}
