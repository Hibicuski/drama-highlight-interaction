package com.warren.shortdrama.core.model;

import com.google.gson.annotations.SerializedName;
import java.util.Map;

public class InteractionModels {

    public static class InteractionRequest {
        @SerializedName("content_id")
        private String contentId;

        @SerializedName("highlight_id")
        private String highlightId;

        @SerializedName("action")
        private String action;

        public InteractionRequest(String contentId, String highlightId, String action) {
            this.contentId = contentId;
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
