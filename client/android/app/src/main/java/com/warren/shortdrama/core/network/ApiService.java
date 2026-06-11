package com.warren.shortdrama.core.network;

import com.warren.shortdrama.core.model.Drama;
import com.warren.shortdrama.core.model.Episode;
import com.warren.shortdrama.core.model.HighlightManifest;
import com.warren.shortdrama.core.model.InteractionModels;

import java.util.List;

import retrofit2.Call;
import retrofit2.http.Body;
import retrofit2.http.GET;
import retrofit2.http.POST;
import retrofit2.http.Path;

public interface ApiService {

    @GET("dramas")
    Call<List<Drama>> getDramas();

    @GET("dramas/{id}/episodes")
    Call<List<Episode>> getEpisodes(@Path("id") int dramaId);

    @GET("contents/{id}/manifest")
    Call<HighlightManifest> getManifest(@Path("id") String contentId);

    @POST("interactions")
    Call<InteractionModels.InteractionResponse> reportInteraction(@Body InteractionModels.InteractionRequest request);

    @GET("highlights/{id}/aggregate")
    Call<InteractionModels.InteractionResponse> getAggregation(@Path("id") String highlightId);
}
