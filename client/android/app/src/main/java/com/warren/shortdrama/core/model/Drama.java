package com.warren.shortdrama.core.model;

import com.google.gson.annotations.SerializedName;

import java.io.Serializable;
import java.util.Collections;
import java.util.List;

public class Drama implements Serializable {
    private int id;
    private String title;

    @SerializedName("poster")
    private String coverUrl;

    private List<String> tags;
    private String description;

    public Drama(int id, String title, String coverUrl, String description) {
        this(id, title, coverUrl, Collections.emptyList(), description);
    }

    public Drama(int id, String title, String coverUrl, List<String> tags, String description) {
        this.id = id;
        this.title = title;
        this.coverUrl = coverUrl;
        this.tags = tags;
        this.description = description;
    }

    public int getId() { return id; }
    public String getTitle() { return title; }
    public String getCoverUrl() { return coverUrl; }
    public List<String> getTags() { return tags == null ? Collections.emptyList() : tags; }
    public String getDescription() { return description; }
}
