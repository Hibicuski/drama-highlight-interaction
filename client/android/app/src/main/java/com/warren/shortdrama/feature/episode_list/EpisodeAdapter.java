package com.warren.shortdrama.feature.episode_list;

import android.view.LayoutInflater;
import android.view.View;
import android.view.ViewGroup;
import android.widget.ImageView;
import android.widget.TextView;

import androidx.annotation.NonNull;
import androidx.recyclerview.widget.RecyclerView;

import com.warren.shortdrama.R;
import com.warren.shortdrama.core.model.Episode;
import com.bumptech.glide.Glide;

import java.util.ArrayList;
import java.util.List;

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
        private final ImageView ivPoster;

        public ViewHolder(@NonNull View itemView) {
            super(itemView);
            ivPoster = itemView.findViewById(R.id.iv_episode_poster);
            tvIndex = itemView.findViewById(R.id.tv_episode_index);
            tvTitle = itemView.findViewById(R.id.tv_episode_title);
            tvDuration = itemView.findViewById(R.id.tv_episode_duration);
        }

        public void bind(Episode episode, OnEpisodeClickListener listener) {
            tvIndex.setText(tvIndex.getContext().getString(R.string.episode_index_format, episode.getIndex()));
            tvTitle.setText(episode.getTitle());

            long seconds = episode.getDurationMs() / 1000;
            long minutes = seconds / 60;
            long remainingSeconds = seconds % 60;
            tvDuration.setText(tvDuration.getContext().getString(
                    R.string.episode_duration_format,
                    minutes,
                    remainingSeconds
            ));
            Glide.with(ivPoster)
                    .load(episode.getPosterUrl())
                    .placeholder(android.R.color.darker_gray)
                    .error(android.R.color.darker_gray)
                    .centerCrop()
                    .into(ivPoster);

            itemView.setOnClickListener(v -> listener.onEpisodeClick(episode));
        }
    }
}
