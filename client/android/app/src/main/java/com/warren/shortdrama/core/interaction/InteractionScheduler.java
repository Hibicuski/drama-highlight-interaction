package com.warren.shortdrama.core.interaction;

import android.os.Handler;
import android.os.Looper;

import com.warren.shortdrama.core.model.HighlightManifest;
import com.warren.shortdrama.core.model.HighlightPoint;
import com.warren.shortdrama.core.player.DramaPlayer;

import java.util.HashSet;
import java.util.Set;

public class InteractionScheduler {

    public interface InteractionListener {
        boolean onShowHighlight(HighlightPoint highlight);
        void onHideHighlight(String highlightId);
    }

    private final DramaPlayer player;
    private final HighlightManifest manifest;
    private final InteractionListener listener;
    private final int tickIntervalMs;
    private final Handler handler = new Handler(Looper.getMainLooper());
    private final Set<String> shownHighlights = new HashSet<>();
    private String activeHighlightId = null;
    private boolean running = false;

    private final Runnable tickRunnable = new Runnable() {
        @Override
        public void run() {
            if (!running) return;
            checkProgress();
            if (running) {
                handler.postDelayed(this, tickIntervalMs);
            }
        }
    };

    public InteractionScheduler(
            DramaPlayer player,
            HighlightManifest manifest,
            InteractionListener listener,
            int tickIntervalMs
    ) {
        this.player = player;
        this.manifest = manifest;
        this.listener = listener;
        this.tickIntervalMs = tickIntervalMs;
    }

    public void start() {
        if (running) return;
        running = true;
        handler.post(tickRunnable);
    }

    public void stop() {
        running = false;
        handler.removeCallbacks(tickRunnable);
    }

    private void checkProgress() {
        if (player == null || manifest == null || manifest.getHighlights() == null) return;

        long currentPos = player.getCurrentPosition();

        // Check for highlight to show
        for (HighlightPoint hl : manifest.getHighlights()) {
            if (hl == null || hl.getId() == null) continue;

            if (currentPos >= hl.getStartMs() && currentPos <= hl.getEndMs()) {
                if (!hl.getId().equals(activeHighlightId) && !shownHighlights.contains(hl.getId())) {
                    showHighlight(hl);
                }
                return; // Only one active highlight at a time for simplicity
            }
        }

        // Hide active highlight if outside bounds
        if (activeHighlightId != null) {
            hideHighlight();
        }
    }

    private void showHighlight(HighlightPoint hl) {
        activeHighlightId = hl.getId();
        boolean shown = false;
        if (listener != null) {
            shown = listener.onShowHighlight(hl);
        }
        if (shown) {
            shownHighlights.add(hl.getId());
        } else {
            activeHighlightId = null;
        }
    }

    private void hideHighlight() {
        if (listener != null && activeHighlightId != null) {
            listener.onHideHighlight(activeHighlightId);
        }
        activeHighlightId = null;
    }
}
