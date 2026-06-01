package com.warren.shortdrama.core.interaction;

import com.warren.shortdrama.core.model.HighlightManifest;
import com.warren.shortdrama.core.model.InteractionModels;
import com.warren.shortdrama.core.network.ApiService;
import com.warren.shortdrama.core.network.RetrofitClient;

import java.util.Collections;
import java.util.HashSet;
import java.util.Set;

import retrofit2.Call;
import retrofit2.Callback;
import retrofit2.Response;

public class InteractionRepository {

    public interface ManifestCallback {
        void onSuccess(HighlightManifest manifest);
        void onError(Throwable error);
    }

    public interface ReportCallback {
        void onSuccess(InteractionModels.InteractionResponse stats);
        void onError(Throwable error);
    }

    private final ApiService apiService;
    private Call<HighlightManifest> manifestCall;
    private final Set<Call<InteractionModels.InteractionResponse>> reportCalls =
            Collections.synchronizedSet(new HashSet<>());

    public InteractionRepository() {
        this(RetrofitClient.api());
    }

    public InteractionRepository(ApiService apiService) {
        this.apiService = apiService;
    }

    public void fetchManifest(int episodeId, ManifestCallback callback) {
        if (manifestCall != null) manifestCall.cancel();
        manifestCall = apiService.getManifest(episodeId);
        manifestCall.enqueue(new Callback<HighlightManifest>() {
            @Override
            public void onResponse(Call<HighlightManifest> call, Response<HighlightManifest> response) {
                if (call.isCanceled()) return;
                if (response.isSuccessful() && response.body() != null) {
                    callback.onSuccess(response.body());
                    return;
                }
                callback.onError(new IllegalStateException("Failed to load manifest: " + response.code()));
            }

            @Override
            public void onFailure(Call<HighlightManifest> call, Throwable t) {
                if (call.isCanceled()) return;
                callback.onError(t);
            }
        });
    }

    public void reportInteraction(int episodeId, String highlightId, String action, ReportCallback callback) {
        InteractionModels.InteractionRequest request =
                new InteractionModels.InteractionRequest(episodeId, highlightId, action);

        Call<InteractionModels.InteractionResponse> reportCall = apiService.reportInteraction(request);
        reportCalls.add(reportCall);
        reportCall.enqueue(new Callback<InteractionModels.InteractionResponse>() {
            @Override
            public void onResponse(
                    Call<InteractionModels.InteractionResponse> call,
                    Response<InteractionModels.InteractionResponse> response
            ) {
                reportCalls.remove(call);
                if (call.isCanceled()) return;
                if (response.isSuccessful() && response.body() != null) {
                    callback.onSuccess(response.body());
                    return;
                }
                callback.onError(new IllegalStateException("Failed to report interaction: " + response.code()));
            }

            @Override
            public void onFailure(Call<InteractionModels.InteractionResponse> call, Throwable t) {
                reportCalls.remove(call);
                if (call.isCanceled()) return;
                callback.onError(t);
            }
        });
    }

    public void cancelAll() {
        if (manifestCall != null) manifestCall.cancel();
        synchronized (reportCalls) {
            for (Call<InteractionModels.InteractionResponse> reportCall : reportCalls) {
                reportCall.cancel();
            }
            reportCalls.clear();
        }
        manifestCall = null;
    }
}
