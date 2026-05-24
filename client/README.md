# Client

## Android

Android Studio project location:

```text
client/android
```

Current demo flow:

1. `DramaListActivity` loads `GET /api/dramas`.
2. Tap a drama to load `GET /api/dramas/{id}/episodes`.
3. `EpisodePlayerActivity` plays the first episode with Media3 ExoPlayer.
4. If the backend is not running, the app falls back to local demo data and `res/raw/sample.mp4`.

For Android Emulator, the API base URL is:

```text
http://10.0.2.2:3000/api/
```

If testing on a real phone, change `RetrofitClient.BASE_URL` to your computer's LAN IP.
