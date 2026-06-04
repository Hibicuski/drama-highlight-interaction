package com.warren.shortdrama.core.model;

import com.google.gson.annotations.SerializedName;
import java.io.Serializable;
import java.util.List;

public class HighlightPoint implements Serializable {
    @SerializedName("id")
    private String id;

    @SerializedName("start_ms")
    private long startMs;

    @SerializedName("end_ms")
    private long endMs;

    @SerializedName("type")
    private String type;

    @SerializedName("template")
    private String template;

    @SerializedName("payload")
    private Payload payload;

    public static class Payload implements Serializable {
        @SerializedName("title")
        private String title;

        @SerializedName("actions")
        private List<Action> actions;

        @SerializedName("effect")
        private String effect;

        public String getTitle() { return title; }
        public List<Action> getActions() { return actions; }
        public String getEffect() { return effect; }
    }

    public static class Action implements Serializable {
        @SerializedName("key")
        private String key;

        @SerializedName("label")
        private String label;

        @SerializedName("tone")
        private String tone;

        @SerializedName("icon")
        private String icon;

        public String getKey() { return key; }
        public String getLabel() { return label; }
        public String getTone() { return tone; }
        public String getIcon() { return icon; }
    }

    public String getId() { return id; }
    public long getStartMs() { return startMs; }
    public long getEndMs() { return endMs; }
    public String getType() { return type; }
    public String getTemplate() { return template; }
    public Payload getPayload() { return payload; }
}
