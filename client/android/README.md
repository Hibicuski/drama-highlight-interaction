# Android Demo

Open this folder directly in Android Studio:

```text
client/android
```

The app is a migrated and cleaned-up version of `oldDemo`:

- drama list screen with `RecyclerView`
- backend API calls through Retrofit
- episode playback through Media3 ExoPlayer
- local fallback data and `res/raw/sample.mp4`
- simple timed highlight interaction after 10 seconds of playback

Run the backend from the repository root with:

```bash
cd server
npm start
```

Then run the Android app on an emulator. The emulator reaches the host backend at `http://10.0.2.2:3000/api/`.
