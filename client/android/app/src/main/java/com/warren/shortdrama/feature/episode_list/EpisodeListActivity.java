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
import com.warren.shortdrama.core.model.Drama;
import com.warren.shortdrama.core.model.Episode;
import com.warren.shortdrama.core.network.RetrofitClient;
import com.warren.shortdrama.feature.episode_player.EpisodePlayerActivity;

import java.util.List;

import retrofit2.Call;
import retrofit2.Callback;
import retrofit2.Response;

public class EpisodeListActivity extends AppCompatActivity {

    private Drama drama;
    private RecyclerView rvEpisodeList;
    private TextView tvStatus;
    private EpisodeAdapter adapter;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(R.layout.activity_episode_list);

        drama = (Drama) getIntent().getSerializableExtra("drama");
        if (drama == null) {
            finish();
            return;
        }

        TextView tvTitle = findViewById(R.id.tv_drama_title_header);
        TextView tvDesc = findViewById(R.id.tv_drama_description);
        tvTitle.setText(drama.getTitle());
        tvDesc.setText(drama.getDescription());

        rvEpisodeList = findViewById(R.id.rv_episode_list);
        tvStatus = findViewById(R.id.tv_status);
        rvEpisodeList.setLayoutManager(new LinearLayoutManager(this));

        adapter = new EpisodeAdapter(this::openPlayer);
        rvEpisodeList.setAdapter(adapter);

        loadEpisodes();
    }

    private void loadEpisodes() {
        tvStatus.setVisibility(View.VISIBLE);
        tvStatus.setText("Loading episodes...");
        RetrofitClient.api().getEpisodes(drama.getId()).enqueue(new Callback<List<Episode>>() {
            @Override
            public void onResponse(Call<List<Episode>> call, Response<List<Episode>> response) {
                tvStatus.setVisibility(View.GONE);
                if (response.isSuccessful() && response.body() != null) {
                    adapter.submitList(response.body());
                } else {
                    Toast.makeText(EpisodeListActivity.this, "Failed to load episodes", Toast.LENGTH_SHORT).show();
                }
            }

            @Override
            public void onFailure(Call<List<Episode>> call, Throwable t) {
                tvStatus.setVisibility(View.GONE);
                Toast.makeText(EpisodeListActivity.this, "Network error", Toast.LENGTH_SHORT).show();
            }
        });
    }

    private void openPlayer(Episode episode) {
        Intent intent = new Intent(this, EpisodePlayerActivity.class);
        intent.putExtra("drama", drama);
        intent.putExtra("episode", episode);
        startActivity(intent);
    }
}
