package com.warren.shortdrama.core.player;

import android.content.Context;

import androidx.media3.common.MediaItem;
import androidx.media3.common.Player;
import androidx.media3.exoplayer.ExoPlayer;
import androidx.media3.ui.PlayerView;

public class DramaPlayer {

    private static final String FALLBACK_VIDEO_URL = "https://storage.googleapis.com/gtv-videos-bucket/sample/BigBuckBunny.mp4";

    private ExoPlayer player;
    private OnProgressUpdateListener progressListener;

    public interface OnProgressUpdateListener {
        void onProgressUpdate(long currentPosition, long duration);
    }

    public DramaPlayer(Context context, PlayerView playerView, String videoUrl) {
        initPlayer(context, playerView, videoUrl);
    }

    private void initPlayer(Context context, PlayerView playerView, String videoUrl) {
        player = new ExoPlayer.Builder(context).build();
        playerView.setPlayer(player);

        String uri = videoUrl == null || videoUrl.isEmpty() ? FALLBACK_VIDEO_URL : videoUrl;
        MediaItem mediaItem = MediaItem.fromUri(uri);
        player.setMediaItem(mediaItem);
        player.prepare();
        player.play();

        player.addListener(new Player.Listener() {
            @Override
            public void onEvents(Player player, Player.Events events) {
                if (progressListener != null) {
                    progressListener.onProgressUpdate(player.getCurrentPosition(), player.getDuration());
                }
            }
        });
    }

    public void setOnProgressUpdateListener(OnProgressUpdateListener listener) {
        this.progressListener = listener;
    }

    public long getCurrentPosition() {
        return player != null ? player.getCurrentPosition() : 0;
    }

    public void pause() {
        if (player != null) player.pause();
    }

    public void play() {
        if (player != null) player.play();
    }

    public void release() {
        if (player != null) {
            player.release();
            player = null;
        }
    }
}
