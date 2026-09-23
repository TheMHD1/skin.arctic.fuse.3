using System.ComponentModel.DataAnnotations;
using Jellyfin.Database.Implementations;
using Jellyfin.Database.Implementations.Entities;
using MediaBrowser.Common.Api;
using MediaBrowser.Controller.Entities;
using MediaBrowser.Controller.Entities.Movies;
using MediaBrowser.Controller.Entities.TV;
using MediaBrowser.Controller.Library;
using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Http;
using Microsoft.AspNetCore.Mvc;
using Microsoft.EntityFrameworkCore;

namespace Jellyfin.Plugin.LibraryExperience.Controllers;

/// <summary>Guarded import-date repair without replacing unrelated metadata.</summary>
[ApiController]
[Authorize(Policy = Policies.RequiresElevation)]
[Route("Habibi/LibraryImportDate")]
public sealed class LibraryImportDateController(
    ILibraryManager libraryManager,
    IDbContextFactory<JellyfinDbContext> dbProvider) : ControllerBase
{
    private static readonly DateTime EarliestImportDate = new(2000, 1, 1, 0, 0, 0, DateTimeKind.Utc);
    private static readonly Version SupportedControllerVersion = new(12, 1, 0, 0);

    /// <summary>Change only DateCreated for an exactly identified local movie or episode.</summary>
    /// <param name="itemId">Item identifier.</param>
    /// <param name="request">Expected identity, previous timestamp and verified import timestamp.</param>
    /// <param name="cancellationToken">Request cancellation token.</param>
    /// <returns>No content, or a validation/conflict response without modifying the item.</returns>
    [HttpPost("{itemId:guid}")]
    [ProducesResponseType(StatusCodes.Status204NoContent)]
    [ProducesResponseType(StatusCodes.Status400BadRequest)]
    [ProducesResponseType(StatusCodes.Status404NotFound)]
    [ProducesResponseType(StatusCodes.Status409Conflict)]
    public async Task<ActionResult> UpdateImportDate(
        Guid itemId,
        [FromBody, Required] ImportDateUpdate request,
        CancellationToken cancellationToken)
    {
        if (!IsSupportedServer())
        {
            return StatusCode(StatusCodes.Status503ServiceUnavailable, "This plugin must be rebuilt for the installed Jellyfin version.");
        }

        var item = libraryManager.GetItemById<BaseItem>(itemId);
        if (item is null)
        {
            return NotFound();
        }

        if ((item is not Movie && item is not Episode)
            || !IsLocalMedia(item)
            || request.DateCreated.Kind != DateTimeKind.Utc
            || request.ExpectedDateCreated.Kind != DateTimeKind.Utc
            || request.DateCreated < EarliestImportDate
            || request.DateCreated > DateTime.UtcNow.AddMinutes(5))
        {
            return BadRequest("A local movie/episode and a valid UTC import date are required.");
        }

        if (!string.Equals(item.Path, request.ExpectedPath, StringComparison.Ordinal)
            || item.DateCreated != request.ExpectedDateCreated)
        {
            return Conflict("Item path or date changed; create a fresh repair plan.");
        }

        await using var context = await dbProvider.CreateDbContextAsync(cancellationToken).ConfigureAwait(false);
        await using var transaction = await context.Database.BeginTransactionAsync(cancellationToken).ConfigureAwait(false);
        var affected = await context.BaseItems
            .Where(entity => entity.Id == itemId
                && entity.Path == request.ExpectedPath
                && entity.Type == item.GetType().FullName
                && !entity.IsVirtualItem
                && entity.DateCreated == request.ExpectedDateCreated)
            .ExecuteUpdateAsync(
                setters => setters.SetProperty(entity => entity.DateCreated, request.DateCreated),
                cancellationToken)
            .ConfigureAwait(false);

        if (affected != 1)
        {
            return Conflict("Database identity or date changed; create a fresh repair plan.");
        }

        await transaction.CommitAsync(cancellationToken).ConfigureAwait(false);

        // ExecuteUpdate bypasses tracking and Jellyfin's object cache. Mirror exactly the one
        // committed field only after the transaction is durable; do not invoke metadata savers.
        item.DateCreated = request.DateCreated;
        return NoContent();
    }

    /// <summary>Recompute series latest-media dates after a guarded episode-date repair batch.</summary>
    /// <param name="request">The exact series identifiers touched by the repair plan.</param>
    /// <param name="cancellationToken">Request cancellation token.</param>
    /// <returns>The number of series recomputed from their current local episodes.</returns>
    [HttpPost("RefreshLatestDates")]
    [ProducesResponseType(StatusCodes.Status200OK)]
    [ProducesResponseType(StatusCodes.Status400BadRequest)]
    [ProducesResponseType(StatusCodes.Status404NotFound)]
    [ProducesResponseType(StatusCodes.Status409Conflict)]
    public async Task<ActionResult<RefreshLatestDatesResult>> RefreshLatestDates(
        [FromBody, Required] RefreshLatestDatesRequest request,
        CancellationToken cancellationToken)
    {
        if (!IsSupportedServer())
        {
            return StatusCode(StatusCodes.Status503ServiceUnavailable, "This plugin must be rebuilt for the installed Jellyfin version.");
        }

        if (request.SeriesIds is not { Length: > 0 and <= 500 }
            || request.SeriesIds.Any(id => id == Guid.Empty))
        {
            return BadRequest("Expected between 1 and 500 submitted non-empty series identifiers.");
        }

        var seriesIds = request.SeriesIds.Distinct().ToArray();

        var cachedSeries = new Dictionary<Guid, Series>(seriesIds.Length);
        foreach (var seriesId in seriesIds)
        {
            if (libraryManager.GetItemById<BaseItem>(seriesId) is not Series series || series.IsVirtualItem)
            {
                return NotFound($"Series {seriesId:N} was not found or is virtual.");
            }

            cachedSeries.Add(seriesId, series);
        }

        await using var context = await dbProvider.CreateDbContextAsync(cancellationToken).ConfigureAwait(false);
        await using var transaction = await context.Database.BeginTransactionAsync(cancellationToken).ConfigureAwait(false);

        var parentSnapshots = await context.BaseItems
            .AsNoTracking()
            .Where(entity => seriesIds.Contains(entity.Id)
                && entity.Type == typeof(Series).FullName
                && !entity.IsVirtualItem)
            .Select(entity => new { entity.Id, entity.DateLastMediaAdded })
            .ToDictionaryAsync(entity => entity.Id, cancellationToken)
            .ConfigureAwait(false);
        if (parentSnapshots.Count != seriesIds.Length)
        {
            return Conflict("A series database row changed; create a fresh repair plan.");
        }

        var episodeRows = await context.BaseItems
            .AsNoTracking()
            .Where(entity => entity.SeriesId.HasValue
                && seriesIds.Contains(entity.SeriesId.Value)
                && entity.Type == typeof(Episode).FullName
                && !entity.IsVirtualItem
                && entity.DateCreated.HasValue)
            .Select(entity => new { entity.SeriesId, entity.Path, entity.DateCreated })
            .ToListAsync(cancellationToken)
            .ConfigureAwait(false);

        var latestBySeries = episodeRows
            .Where(entity => IsLocalPath(entity.Path))
            .GroupBy(entity => entity.SeriesId!.Value)
            .ToDictionary(group => group.Key, group => group.Max(entity => entity.DateCreated!.Value));
        if (seriesIds.Any(seriesId => !latestBySeries.ContainsKey(seriesId)))
        {
            return BadRequest("Every requested series must contain at least one dated local episode.");
        }

        foreach (var seriesId in seriesIds)
        {
            var previous = parentSnapshots[seriesId].DateLastMediaAdded;
            var latest = latestBySeries[seriesId];
            var affected = await context.BaseItems
                .Where(entity => entity.Id == seriesId
                    && entity.Type == typeof(Series).FullName
                    && !entity.IsVirtualItem
                    && entity.DateLastMediaAdded == previous)
                .ExecuteUpdateAsync(
                    setters => setters.SetProperty(entity => entity.DateLastMediaAdded, latest),
                    cancellationToken)
                .ConfigureAwait(false);
            if (affected != 1)
            {
                return Conflict("A series latest-media date changed; retry from a fresh snapshot.");
            }
        }

        await transaction.CommitAsync(cancellationToken).ConfigureAwait(false);
        foreach (var (seriesId, series) in cachedSeries)
        {
            series.DateLastMediaAdded = latestBySeries[seriesId];
        }

        return Ok(new RefreshLatestDatesResult(seriesIds.Length));
    }

    private static bool IsLocalMedia(BaseItem item)
        => !item.IsVirtualItem && IsLocalPath(item.Path);

    private static bool IsSupportedServer()
        => typeof(ILibraryManager).Assembly.GetName().Version == SupportedControllerVersion;

    private static bool IsLocalPath(string? path)
        => !string.IsNullOrEmpty(path)
            && Path.IsPathFullyQualified(path)
            && !string.Equals(Path.GetExtension(path), ".strm", StringComparison.OrdinalIgnoreCase);

    /// <summary>Exact-match import-date repair, containing no other editable metadata.</summary>
    public sealed class ImportDateUpdate
    {
        /// <summary>Gets or sets the expected current path.</summary>
        [Required]
        public string ExpectedPath { get; set; } = string.Empty;

        /// <summary>Gets or sets the expected current UTC date.</summary>
        public DateTime ExpectedDateCreated { get; set; }

        /// <summary>Gets or sets the verified UTC import date.</summary>
        public DateTime DateCreated { get; set; }
    }

    /// <summary>Bounded request to refresh derived series latest-media dates.</summary>
    public sealed class RefreshLatestDatesRequest
    {
        /// <summary>Gets or sets the affected series identifiers.</summary>
        [Required]
        public Guid[] SeriesIds { get; set; } = [];
    }

    /// <summary>Result of a derived series-date refresh.</summary>
    /// <param name="UpdatedSeries">Number of series refreshed.</param>
    public sealed record RefreshLatestDatesResult(int UpdatedSeries);
}
