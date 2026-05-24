package com.warren.shortdrama.core.model;

import com.google.gson.annotations.SerializedName;
import java.util.Map;

public class InteractionModels {

    public static class InteractionRequest {
        @SerializedName("episode_id")
        private int episodeId;

        @SerializedName("highlight_id")
        private String highlightId;

        @SerializedName("action")
        private String action;

        public InteractionRequest(int episodeId, String highlightId, String action) {
            this.episodeId = episodeId;
            this.highlightId = highlightId;
            this.action = action;
        }
    }

    public static class InteractionResponse {
        @SerializedName("count")
        private int count;

        @SerializedName("actions")
        private Map<String, Integer> actions;

        public int getCount() { return count; }
        public Map<String, Integer> getActions() { return actions; }
    }
}
