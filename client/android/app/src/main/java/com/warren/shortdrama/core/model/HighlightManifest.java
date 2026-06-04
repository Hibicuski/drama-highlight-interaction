package com.warren.shortdrama.core.model;

import com.google.gson.annotations.SerializedName;
import java.io.Serializable;
import java.util.List;

public class HighlightManifest implements Serializable {
    @SerializedName("content_id")
    private String contentId;

    @SerializedName("version")
    private String version;

    @SerializedName("highlights")
    private List<HighlightPoint> highlights;

    public String getContentId() { return contentId; }
    public List<HighlightPoint> getHighlights() { return highlights; }
}
