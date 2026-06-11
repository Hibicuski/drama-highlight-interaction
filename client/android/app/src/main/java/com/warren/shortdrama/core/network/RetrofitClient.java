package com.warren.shortdrama.core.network;

import android.content.Context;

import com.warren.shortdrama.BuildConfig;
import com.warren.shortdrama.R;

import okhttp3.OkHttpClient;
import okhttp3.logging.HttpLoggingInterceptor;
import retrofit2.Retrofit;
import retrofit2.converter.gson.GsonConverterFactory;

public class RetrofitClient {

    private static Retrofit retrofit;
    private static String activeBaseUrl;

    public static Retrofit get(Context context) {
        Context appContext = context.getApplicationContext();
        String baseUrl = appContext.getString(R.string.config_api_base_url);
        if (retrofit == null || !baseUrl.equals(activeBaseUrl)) {
            OkHttpClient.Builder clientBuilder = new OkHttpClient.Builder();
            if (BuildConfig.DEBUG) {
                HttpLoggingInterceptor log = new HttpLoggingInterceptor();
                log.setLevel(HttpLoggingInterceptor.Level.BODY);
                clientBuilder.addInterceptor(log);
            }
            OkHttpClient client = clientBuilder.build();

            retrofit = new Retrofit.Builder()
                    .baseUrl(baseUrl)
                    .client(client)
                    .addConverterFactory(GsonConverterFactory.create())
                    .build();
            activeBaseUrl = baseUrl;
        }
        return retrofit;
    }

    public static ApiService api(Context context) {
        return get(context).create(ApiService.class);
    }
}
