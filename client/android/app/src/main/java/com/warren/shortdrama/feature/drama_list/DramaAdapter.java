package com.warren.shortdrama.feature.drama_list;

import android.view.LayoutInflater;
import android.view.View;
import android.view.ViewGroup;
import android.widget.ImageView;
import android.widget.TextView;

import androidx.annotation.NonNull;
import androidx.recyclerview.widget.RecyclerView;

import com.warren.shortdrama.R;
import com.warren.shortdrama.core.model.Drama;
import com.bumptech.glide.Glide;

import java.util.List;

public class DramaAdapter extends RecyclerView.Adapter<DramaAdapter.ViewHolder> {

    private List<Drama> dramas;
    private final OnDramaClickListener listener;

    public interface OnDramaClickListener {
        void onDramaClick(Drama drama);
    }

    public DramaAdapter(List<Drama> dramas, OnDramaClickListener listener) {
        this.dramas = dramas;
        this.listener = listener;
    }

    public void submitList(List<Drama> newList) {
        this.dramas = newList;
        notifyDataSetChanged();
    }

    @NonNull
    @Override
    public ViewHolder onCreateViewHolder(@NonNull ViewGroup parent, int viewType) {
        View view = LayoutInflater.from(parent.getContext()).inflate(R.layout.item_drama, parent, false);
        return new ViewHolder(view);
    }

    @Override
    public void onBindViewHolder(@NonNull ViewHolder holder, int position) {
        Drama drama = dramas.get(position);
        holder.bind(drama, listener);
    }

    @Override
    public int getItemCount() {
        return dramas == null ? 0 : dramas.size();
    }

    public static class ViewHolder extends RecyclerView.ViewHolder {
        private final TextView tvTitle;
        private final TextView tvDesc;
        private final ImageView ivCover;

        ViewHolder(View itemView) {
            super(itemView);
            tvTitle = itemView.findViewById(R.id.tv_drama_title);
            tvDesc = itemView.findViewById(R.id.tv_drama_desc);
            ivCover = itemView.findViewById(R.id.iv_drama_cover);
        }

        void bind(Drama drama, OnDramaClickListener listener) {
            tvTitle.setText(drama.getTitle());
            tvDesc.setText(drama.getDescription());
            Glide.with(ivCover)
                    .load(drama.getCoverUrl())
                    .placeholder(android.R.color.darker_gray)
                    .error(android.R.color.darker_gray)
                    .centerCrop()
                    .into(ivCover);
            itemView.setOnClickListener(v -> {
                if (listener != null) listener.onDramaClick(drama);
            });
        }
    }
}
