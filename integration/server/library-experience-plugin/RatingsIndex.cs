using System.Globalization;
using System.Text.Json;
using MediaBrowser.Common.Configuration;

namespace Jellyfin.Plugin.LibraryExperience;

/// <summary>Reads the locally generated, bounded IMDb ratings index without making network requests.</summary>
public sealed class RatingsIndex
{
    private const long MaximumBytes = 2 * 1024 * 1024;
    private static readonly TimeSpan MaximumAge = TimeSpan.FromDays(14);
    private const string OfficialRatingsDatasetUrl = "https://datasets.imdbws.com/title.ratings.tsv.gz";
    private readonly IApplicationPaths _applicationPaths;
    private readonly TimeProvider _timeProvider;
    private readonly object _gate = new();
    private DateTime _lastWriteUtc = DateTime.MinValue;
    private RatingSnapshot _snapshot = new(Empty, null);

    private static readonly IReadOnlyDictionary<string, ImdbRating> Empty = new Dictionary<string, ImdbRating>();

    /// <summary>Initializes an index using the system UTC clock.</summary>
    public RatingsIndex(IApplicationPaths applicationPaths)
        : this(applicationPaths, TimeProvider.System)
    {
    }

    /// <summary>Initializes an index with a supplied clock for deterministic freshness checks.</summary>
    public RatingsIndex(IApplicationPaths applicationPaths, TimeProvider timeProvider)
    {
        _applicationPaths = applicationPaths;
        _timeProvider = timeProvider;
    }

    /// <summary>Gets a current, validated snapshot. Invalid, missing, oversized, or stale input is omitted.</summary>
    public IReadOnlyDictionary<string, ImdbRating> GetRatings()
        => GetSnapshot().Ratings;

    /// <summary>Gets ratings together with their local dataset fetch time, if the index is valid.</summary>
    public RatingSnapshot GetSnapshot()
    {
        var path = Path.Combine(_applicationPaths.PluginConfigurationsPath, "library-experience", "imdb-library-ratings.json");
        FileInfo info;
        try
        {
            info = new FileInfo(path);
            if (!info.Exists || info.Length > MaximumBytes)
            {
                return new RatingSnapshot(Empty, null);
            }
        }
        catch (IOException)
        {
            return new RatingSnapshot(Empty, null);
        }
        catch (UnauthorizedAccessException)
        {
            return new RatingSnapshot(Empty, null);
        }

        var lastWriteUtc = info.LastWriteTimeUtc;
        lock (_gate)
        {
            if (lastWriteUtc == _lastWriteUtc)
            {
                return IsFresh(_snapshot) ? _snapshot : new RatingSnapshot(Empty, null);
            }

            _snapshot = Read(path);
            _lastWriteUtc = lastWriteUtc;
            return _snapshot;
        }
    }

    private RatingSnapshot Read(string path)
    {
        try
        {
            using var stream = new FileStream(path, FileMode.Open, FileAccess.Read, FileShare.Read);
            if (stream.Length > MaximumBytes)
            {
                return new RatingSnapshot(Empty, null);
            }

            using var document = JsonDocument.Parse(stream);
            var root = document.RootElement;
            if (root.ValueKind != JsonValueKind.Object
                || !root.TryGetProperty("schema", out var schema) || schema.GetInt32() != 1
                || !root.TryGetProperty("fetched_at", out var fetchedAtElement)
                || !DateTimeOffset.TryParse(fetchedAtElement.GetString(), CultureInfo.InvariantCulture, DateTimeStyles.AssumeUniversal, out var fetchedAt)
                || !IsFresh(fetchedAt)
                || !root.TryGetProperty("source_url", out var sourceElement)
                || !IsAllowedSource(sourceElement.GetString())
                || !root.TryGetProperty("ratings", out var ratings) || ratings.ValueKind != JsonValueKind.Object)
            {
                return new RatingSnapshot(Empty, null);
            }

            var result = new Dictionary<string, ImdbRating>(StringComparer.Ordinal);
            foreach (var property in ratings.EnumerateObject())
            {
                if (!IsImdbId(property.Name) || property.Value.ValueKind != JsonValueKind.Object
                    || !property.Value.TryGetProperty("rating", out var ratingElement)
                    || !property.Value.TryGetProperty("votes", out var votesElement)
                    || !ratingElement.TryGetDouble(out var rating)
                    || !votesElement.TryGetInt64(out var votes)
                    || double.IsNaN(rating) || double.IsInfinity(rating) || rating < 0 || rating > 10 || votes < 1)
                {
                    return new RatingSnapshot(Empty, null);
                }

                result.Add(property.Name, new ImdbRating(rating, votes));
            }

            return new RatingSnapshot(result, fetchedAt);
        }
        catch (IOException)
        {
            return new RatingSnapshot(Empty, null);
        }
        catch (UnauthorizedAccessException)
        {
            return new RatingSnapshot(Empty, null);
        }
        catch (JsonException)
        {
            return new RatingSnapshot(Empty, null);
        }
        catch (InvalidOperationException)
        {
            return new RatingSnapshot(Empty, null);
        }
        catch (FormatException)
        {
            return new RatingSnapshot(Empty, null);
        }
        catch (OverflowException)
        {
            return new RatingSnapshot(Empty, null);
        }
        catch (ArgumentException)
        {
            return new RatingSnapshot(Empty, null);
        }
    }

    private static bool IsAllowedSource(string? source)
        => string.Equals(source, OfficialRatingsDatasetUrl, StringComparison.Ordinal);

    private bool IsFresh(DateTimeOffset fetchedAt)
        => fetchedAt <= _timeProvider.GetUtcNow().AddMinutes(5)
            && _timeProvider.GetUtcNow() - fetchedAt <= MaximumAge;

    private bool IsFresh(RatingSnapshot snapshot)
        => snapshot.FetchedAt is { } fetchedAt && IsFresh(fetchedAt);

    private static bool IsImdbId(string value)
        => value.Length is >= 3 and <= 32 && value.StartsWith("tt", StringComparison.Ordinal)
            && value[2..].All(char.IsAsciiDigit);
}

/// <summary>A locally indexed IMDb rating.</summary>
public sealed record ImdbRating(double Rating, long Votes);

/// <summary>A validated local ratings index and its source dataset fetch timestamp.</summary>
public sealed record RatingSnapshot(IReadOnlyDictionary<string, ImdbRating> Ratings, DateTimeOffset? FetchedAt);
