package com.warren.shortdrama.feature.episode_list;

import android.view.LayoutInflater;
import android.view.View;
import android.view.ViewGroup;
import android.widget.TextView;

import androidx.annotation.NonNull;
import androidx.recyclerview.widget.RecyclerView;

import com.warren.shortdrama.R;
import com.warren.shortdrama.core.model.Episode;

import java.util.ArrayList;
import java.util.List;
import java.util.Locale;

public class EpisodeAdapter extends RecyclerView.Adapter<EpisodeAdapter.ViewHolder> {

    private List<Episode> episodes = new ArrayList<>();
    private final OnEpisodeClickListener listener;

    public interface OnEpisodeClickListener {
        void onEpisodeClick(Episode episode);
    }

    public EpisodeAdapter(OnEpisodeClickListener listener) {
        this.listener = listener;
    }

    public void submitList(List<Episode> newList) {
        this.episodes = newList != null ? newList : new ArrayList<>();
        notifyDataSetChanged();
    }

    @NonNull
    @Override
    public ViewHolder onCreateViewHolder(@NonNull ViewGroup parent, int viewType) {
        View view = LayoutInflater.from(parent.getContext()).inflate(R.layout.item_episode, parent, false);
        return new ViewHolder(view);
    }

    @Override
    public void onBindViewHolder(@NonNull ViewHolder holder, int position) {
        Episode episode = episodes.get(position);
        holder.bind(episode, listener);
    }

    @Override
    public int getItemCount() {
        return episodes.size();
    }

    static class ViewHolder extends RecyclerView.ViewHolder {
        private final TextView tvIndex;
        private final TextView tvTitle;
        private final TextView tvDuration;

        public ViewHolder(@NonNull View itemView) {
            super(itemView);
            tvIndex = itemView.findViewById(R.id.tv_episode_index);
            tvTitle = itemView.findViewById(R.id.tv_episode_title);
            tvDuration = itemView.findViewById(R.id.tv_episode_duration);
        }

        public void bind(Episode episode, OnEpisodeClickListener listener) {
            tvIndex.setText(String.format(Locale.getDefault(), "Episode %d", episode.getIndex()));
            tvTitle.setText(episode.getTitle());

            long seconds = episode.getDurationMs() / 1000;
            long minutes = seconds / 60;
            long remainingSeconds = seconds % 60;
            tvDuration.setText(String.format(Locale.getDefault(), "Duration: %02d:%02d", minutes, remainingSeconds));

            itemView.setOnClickListener(v -> listener.onEpisodeClick(episode));
        }
    }
}
