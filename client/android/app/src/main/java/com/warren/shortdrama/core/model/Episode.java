package com.warren.shortdrama.core.model;

import com.google.gson.annotations.SerializedName;

import java.io.Serializable;

public class Episode implements Serializable {
    private int id;

    @SerializedName("content_id")
    private String contentId;

    @SerializedName("drama_id")
    private int dramaId;

    @SerializedName("episode_index")
    private int index;

    private String title;

    @SerializedName("video_url")
    private String videoUrl;

    @SerializedName("poster")
    private String posterUrl;

    @SerializedName("duration_ms")
    private long durationMs;

    public Episode(int id, String contentId, int dramaId, int index, String title, String videoUrl, long durationMs) {
        this(id, contentId, dramaId, index, title, videoUrl, "", durationMs);
    }

    public Episode(int id, String contentId, int dramaId, int index, String title, String videoUrl, String posterUrl, long durationMs) {
        this.id = id;
        this.contentId = contentId;
        this.dramaId = dramaId;
        this.index = index;
        this.title = title;
        this.videoUrl = videoUrl;
        this.posterUrl = posterUrl;
        this.durationMs = durationMs;
    }

    public int getId() { return id; }
    public String getContentId() { return contentId; }
    public int getDramaId() { return dramaId; }
    public int getIndex() { return index; }
    public String getTitle() { return title; }
    public String getVideoUrl() { return videoUrl; }
    public String getPosterUrl() { return posterUrl; }
    public long getDurationMs() { return durationMs; }
}
