package com.warren.shortdrama.feature.drama_list;

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
import com.warren.shortdrama.core.network.RetrofitClient;
import com.warren.shortdrama.feature.episode_list.EpisodeListActivity;

import java.util.ArrayList;
import java.util.List;

import retrofit2.Call;
import retrofit2.Callback;
import retrofit2.Response;

public class DramaListActivity extends AppCompatActivity {

    private RecyclerView rvDramaList;
    private TextView tvStatus;
    private DramaAdapter adapter;
    private Call<List<Drama>> dramasCall;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(R.layout.activity_drama_list);

        rvDramaList = findViewById(R.id.rv_drama_list);
        tvStatus = findViewById(R.id.tv_status);
        rvDramaList.setLayoutManager(new LinearLayoutManager(this));

        adapter = new DramaAdapter(new ArrayList<>(), this::openDrama);
        rvDramaList.setAdapter(adapter);
        loadDramas();
    }

    private void loadDramas() {
        tvStatus.setVisibility(View.VISIBLE);
        tvStatus.setText("Loading dramas from backend...");
        if (dramasCall != null) dramasCall.cancel();
        dramasCall = RetrofitClient.api().getDramas();
        dramasCall.enqueue(new Callback<List<Drama>>() {
            @Override
            public void onResponse(Call<List<Drama>> call, Response<List<Drama>> response) {
                if (call.isCanceled()) return;
                if (response.isSuccessful() && response.body() != null && !response.body().isEmpty()) {
                    adapter.submitList(response.body());
                    tvStatus.setVisibility(View.GONE);
                } else {
                    showError("Backend returned no dramas.");
                }
            }

            @Override
            public void onFailure(Call<List<Drama>> call, Throwable t) {
                if (call.isCanceled()) return;
                showError("Backend is offline.");
            }
        });
    }

    private void openDrama(Drama drama) {
        Intent intent = new Intent(DramaListActivity.this, EpisodeListActivity.class);
        intent.putExtra("drama", drama);
        startActivity(intent);
    }

    private void showError(String message) {
        tvStatus.setVisibility(View.VISIBLE);
        tvStatus.setText(message);
        Toast.makeText(this, message, Toast.LENGTH_SHORT).show();
    }

    @Override
    protected void onDestroy() {
        super.onDestroy();
        if (dramasCall != null) dramasCall.cancel();
    }
}
