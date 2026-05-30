package com.warren.shortdrama.core.network;

import com.warren.shortdrama.BuildConfig;

import okhttp3.OkHttpClient;
import okhttp3.logging.HttpLoggingInterceptor;
import retrofit2.Retrofit;
import retrofit2.converter.gson.GsonConverterFactory;

public class RetrofitClient {

    // Android emulator maps host localhost to 10.0.2.2.
    private static final String BASE_URL = "http://10.0.2.2:3000/api/";
    private static Retrofit retrofit;

    public static Retrofit get() {
        if (retrofit == null) {
            OkHttpClient.Builder clientBuilder = new OkHttpClient.Builder();
            if (BuildConfig.DEBUG) {
                HttpLoggingInterceptor log = new HttpLoggingInterceptor();
                log.setLevel(HttpLoggingInterceptor.Level.BODY);
                clientBuilder.addInterceptor(log);
            }
            OkHttpClient client = clientBuilder.build();

            retrofit = new Retrofit.Builder()
                    .baseUrl(BASE_URL)
                    .client(client)
                    .addConverterFactory(GsonConverterFactory.create())
                    .build();
        }
        return retrofit;
    }

    public static ApiService api() {
        return get().create(ApiService.class);
    }
}
