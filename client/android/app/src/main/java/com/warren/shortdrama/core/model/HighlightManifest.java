package com.warren.shortdrama.core.model;

import com.google.gson.annotations.SerializedName;
import java.io.Serializable;
import java.util.List;

public class HighlightManifest implements Serializable {
    @SerializedName("episode_id")
    private int episodeId;

    @SerializedName("version")
    private String version;

    @SerializedName("highlights")
    private List<HighlightPoint> highlights;

    public int getEpisodeId() { return episodeId; }
    public List<HighlightPoint> getHighlights() { return highlights; }
}
