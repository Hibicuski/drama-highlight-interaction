package com.warren.shortdrama.core.model;

import com.google.gson.annotations.SerializedName;

import java.io.Serializable;

public class Episode implements Serializable {
    private int id;

    @SerializedName("drama_id")
    private int dramaId;

    @SerializedName("episode_index")
    private int index;

    private String title;

    @SerializedName("video_url")
    private String videoUrl;

    @SerializedName("duration_ms")
    private long durationMs;

    public Episode(int id, int dramaId, int index, String title, String videoUrl, long durationMs) {
        this.id = id;
        this.dramaId = dramaId;
        this.index = index;
        this.title = title;
        this.videoUrl = videoUrl;
        this.durationMs = durationMs;
    }

    public int getId() { return id; }
    public int getDramaId() { return dramaId; }
    public int getIndex() { return index; }
    public String getTitle() { return title; }
    public String getVideoUrl() { return videoUrl; }
    public long getDurationMs() { return durationMs; }
}
