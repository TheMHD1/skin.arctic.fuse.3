# Original XC functions extracted from the reviewed Dispatcharr 0.31 image.
# Test-only fixture; not an installable server module.
from django.http import JsonResponse, Http404, HttpResponse, HttpResponseRedirect

@api_view(["GET"])
@permission_classes([AllowAny])
def stream_xc_movie(request, username, password, stream_id, extension):
    if not network_access_allowed(request, "STREAMS"):
        return JsonResponse({"error": "Forbidden"}, status=403)

    from apps.vod.models import M3UMovieRelation

    session_id = request.GET.get('session_id')
    profile_id = request.GET.get('profile_id')

    user = get_object_or_404(User, username=username)

    if not network_access_allowed(request, 'STREAMS', user):
        return Response({"error": "Forbidden"}, status=403)

    custom_properties = user.custom_properties or {}

    if "xc_password" not in custom_properties:
        return Response({"error": "Invalid credentials"}, status=401)

    if custom_properties["xc_password"] != password:
        return Response({"error": "Invalid credentials"}, status=401)

    if not is_vod_movies_enabled(user=user):
        return JsonResponse({"error": "Forbidden"}, status=403)

    # Users with movie access get it from all active M3U accounts
    filters = {"movie_id": stream_id, "m3u_account__is_active": True}

    try:
        # Order by account priority to get the best relation when multiple exist
        movie_relation = M3UMovieRelation.objects.select_related('movie').filter(**filters).order_by('-m3u_account__priority', 'id').first()
        if not movie_relation:
            return JsonResponse({"error": "Movie not found"}, status=404)
    except (M3UMovieRelation.DoesNotExist, M3UMovieRelation.MultipleObjectsReturned):
        return JsonResponse({"error": "Movie not found"}, status=404)

    return stream_vod(request._request, 'movie', movie_relation.movie.uuid, session_id, profile_id, user)

@api_view(["GET"])
@permission_classes([AllowAny])
def stream_xc_episode(request, username, password, stream_id, extension):
    if not network_access_allowed(request, "STREAMS"):
        return JsonResponse({"error": "Forbidden"}, status=403)

    from apps.vod.models import M3UEpisodeRelation

    session_id = request.GET.get('session_id')
    profile_id = request.GET.get('profile_id')

    user = get_object_or_404(User, username=username)

    if not network_access_allowed(request, 'STREAMS', user):
        return Response({"error": "Forbidden"}, status=403)

    custom_properties = user.custom_properties or {}

    if "xc_password" not in custom_properties:
        return Response({"error": "Invalid credentials"}, status=401)

    if custom_properties["xc_password"] != password:
        return Response({"error": "Invalid credentials"}, status=401)

    if not is_vod_series_enabled(user=user):
        return JsonResponse({"error": "Forbidden"}, status=403)

    # Users with series access get episodes from all active M3U accounts
    filters = {"episode_id": stream_id, "m3u_account__is_active": True}

    episode_relation = M3UEpisodeRelation.objects.select_related('episode').filter(**filters).order_by('-m3u_account__priority', 'id').first()
    if not episode_relation:
        return JsonResponse({"error": "Episode not found"}, status=404)

    return stream_vod(request._request, 'episode', episode_relation.episode.uuid, session_id, profile_id, user)
