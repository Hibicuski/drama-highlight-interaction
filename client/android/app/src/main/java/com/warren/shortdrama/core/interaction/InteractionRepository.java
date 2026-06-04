package com.warren.shortdrama.core.interaction;

import android.content.Context;

import com.warren.shortdrama.R;
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
    private final String manifestLoadErrorFormat;
    private final String reportInteractionErrorFormat;
    private Call<HighlightManifest> manifestCall;
    private final Set<Call<InteractionModels.InteractionResponse>> reportCalls =
            Collections.synchronizedSet(new HashSet<>());

    public InteractionRepository(Context context) {
        Context appContext = context.getApplicationContext();
        this.apiService = RetrofitClient.api(appContext);
        this.manifestLoadErrorFormat = appContext.getString(R.string.error_manifest_load_failed);
        this.reportInteractionErrorFormat = appContext.getString(R.string.error_interaction_report_failed);
    }

    public InteractionRepository(
            ApiService apiService,
            String manifestLoadErrorFormat,
            String reportInteractionErrorFormat
    ) {
        this.apiService = apiService;
        this.manifestLoadErrorFormat = manifestLoadErrorFormat;
        this.reportInteractionErrorFormat = reportInteractionErrorFormat;
    }

    public void fetchManifest(String contentId, ManifestCallback callback) {
        if (manifestCall != null) manifestCall.cancel();
        manifestCall = apiService.getManifest(contentId);
        manifestCall.enqueue(new Callback<HighlightManifest>() {
            @Override
            public void onResponse(Call<HighlightManifest> call, Response<HighlightManifest> response) {
                if (call.isCanceled()) return;
                if (response.isSuccessful() && response.body() != null) {
                    callback.onSuccess(response.body());
                    return;
                }
                callback.onError(new IllegalStateException(
                        String.format(manifestLoadErrorFormat, response.code())
                ));
            }

            @Override
            public void onFailure(Call<HighlightManifest> call, Throwable t) {
                if (call.isCanceled()) return;
                callback.onError(t);
            }
        });
    }

    public void reportInteraction(String contentId, String highlightId, String action, ReportCallback callback) {
        InteractionModels.InteractionRequest request =
                new InteractionModels.InteractionRequest(contentId, highlightId, action);

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
                callback.onError(new IllegalStateException(
                        String.format(reportInteractionErrorFormat, response.code())
                ));
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
