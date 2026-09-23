using System.Security.Claims;
using System.Text.Json.Serialization;
using Jellyfin.Data.Enums;
using Jellyfin.Database.Implementations;
using MediaBrowser.Controller.Entities;
using MediaBrowser.Controller.Library;
using MediaBrowser.Controller.Persistence;
using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Http;
using Microsoft.AspNetCore.Mvc;
using Microsoft.EntityFrameworkCore;

namespace Jellyfin.Plugin.LibraryExperience.Controllers;

/// <summary>Returns local ratings for exact, accessible library movies and series only.</summary>
[ApiController]
[Authorize]
[Route("Habibi/LibraryExperience/Ratings")]
public sealed class LibraryRatingsController(
    ILibraryManager libraryManager,
    IUserManager userManager,
    IDbContextFactory<JellyfinDbContext> dbProvider,
    IItemQueryHelpers queryHelpers,
    RatingsIndex ratingsIndex) : ControllerBase
{
    private const string UserIdClaim = "Jellyfin-UserId";

    /// <summary>Gets a permission-scoped ratings subset for up to 100 exact item ids.</summary>
    [HttpGet]
    [ProducesResponseType(typeof(RatingsResponse), StatusCodes.Status200OK)]
    [ProducesResponseType(StatusCodes.Status400BadRequest)]
    [ProducesResponseType(StatusCodes.Status401Unauthorized)]
    public ActionResult<RatingsResponse> GetRatings([FromQuery] string? ids)
    {
        Response.Headers.CacheControl = "private, no-store";
        Response.Headers.Vary = "Authorization";
        if (!TryParseIds(ids, out var itemIds))
        {
            return BadRequest("Supply between 1 and 100 comma-delimited Jellyfin item GUIDs.");
        }

        if (!Guid.TryParse(User.FindFirstValue(UserIdClaim), out var userId) || userId == Guid.Empty)
        {
            // API keys without a concrete user must never become an administrator/global query.
            return Unauthorized();
        }

        var user = userManager.GetUserById(userId);
        if (user is null)
        {
            return Unauthorized();
        }

        // In 12.1 ItemIds bypasses GetItemList's library-scope filter. Apply the same stock
        // access filter used by SearchManager before loading those exact IDs through the manager.
        var accessQuery = new InternalItemsQuery(user);
        libraryManager.ConfigureUserAccess(accessQuery, user);
        using var dbContext = dbProvider.CreateDbContext();
        var allowedIds = queryHelpers.ApplyAccessFiltering(
                dbContext,
                dbContext.BaseItems.AsNoTracking().Where(entity => itemIds.Contains(entity.Id)),
                accessQuery)
            .Where(entity => !entity.IsVirtualItem
                && (entity.Type == typeof(MediaBrowser.Controller.Entities.Movies.Movie).FullName
                    || entity.Type == typeof(MediaBrowser.Controller.Entities.TV.Series).FullName))
            .Select(entity => entity.Id)
            .ToArray();
        if (allowedIds.Length == 0)
        {
            return Ok(new RatingsResponse(new Dictionary<string, RatingItem>(), "IMDb non-commercial datasets", ratingsIndex.GetSnapshot().FetchedAt));
        }

        var accessible = libraryManager.GetItemList(new InternalItemsQuery(user)
        {
            ItemIds = allowedIds,
            IncludeItemTypes = [BaseItemKind.Movie, BaseItemKind.Series],
            IsVirtualItem = false,
            Recursive = true,
        });
        var index = ratingsIndex.GetSnapshot();
        var result = new Dictionary<string, RatingItem>(StringComparer.Ordinal);
        foreach (var item in accessible)
        {
            if (item is not MediaBrowser.Controller.Entities.Movies.Movie
                && item is not MediaBrowser.Controller.Entities.TV.Series)
            {
                continue;
            }

            item.ProviderIds.TryGetValue("Imdb", out var imdbId);
            ImdbRatingDto? imdb = imdbId is not null && index.Ratings.TryGetValue(imdbId, out var indexed)
                ? new ImdbRatingDto(indexed.Rating, indexed.Votes)
                : null;
            float? community = item.CommunityRating is { } rating && rating >= 0 && rating <= 10 ? rating : null;
            if (imdb is not null || community is not null)
            {
                result[item.Id.ToString("N")] = new RatingItem(imdb, community);
            }
        }

        return Ok(new RatingsResponse(result, "IMDb non-commercial datasets", index.FetchedAt));
    }

    private static bool TryParseIds(string? value, out Guid[] ids)
    {
        ids = [];
        if (string.IsNullOrWhiteSpace(value))
        {
            return false;
        }

        var parsed = new HashSet<Guid>();
        foreach (var part in value.Split(',', StringSplitOptions.None))
        {
            if (!Guid.TryParse(part, out var id) || id == Guid.Empty)
            {
                return false;
            }

            parsed.Add(id);
            if (parsed.Count > 100)
            {
                return false;
            }
        }

        ids = parsed.ToArray();
        return ids.Length > 0;
    }

    /// <summary>Compact response with no library, user, path, or provider provenance details.</summary>
    public sealed record RatingsResponse(
        [property: JsonPropertyName("items")] IReadOnlyDictionary<string, RatingItem> Items,
        [property: JsonPropertyName("source")] string Source,
        [property: JsonPropertyName("fetchedAt")] DateTimeOffset? FetchedAt);

    /// <summary>Ratings carried by an accessible item; community is Jellyfin item metadata.</summary>
    public sealed record RatingItem(
        [property: JsonPropertyName("imdb")] ImdbRatingDto? Imdb,
        [property: JsonPropertyName("community")] float? Community);

    /// <summary>IMDb score and vote count from the local non-commercial dataset index.</summary>
    public sealed record ImdbRatingDto(
        [property: JsonPropertyName("rating")] double Rating,
        [property: JsonPropertyName("votes")] long Votes);
}
