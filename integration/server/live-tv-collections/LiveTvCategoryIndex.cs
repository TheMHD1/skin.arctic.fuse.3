using System;
using System.Collections.Concurrent;
using System.Collections.Generic;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using Jellyfin.Data.Enums;
using Jellyfin.Database.Implementations.Entities;
using MediaBrowser.Controller.Dto;
using MediaBrowser.Controller.LiveTv;
using MediaBrowser.Model.LiveTv;
using Microsoft.Extensions.Logging;

namespace Jellyfin.Plugin.LiveTvCategories.Services;

internal sealed class LiveTvCategoryIndex : ILiveTvCategoryIndex, IDisposable
{
    private static readonly TimeSpan CacheDuration = TimeSpan.FromMinutes(5);
    private readonly ITunerHostManager _tunerHostManager;
    private readonly ILiveTvManager _liveTvManager;
    private readonly ILogger<LiveTvCategoryIndex> _logger;
    private readonly SemaphoreSlim _buildLock = new(1, 1);
    private readonly ConcurrentDictionary<Guid, UserCategorySnapshot> _userViews = new();
    private CategorySnapshot? _snapshot;

    public LiveTvCategoryIndex(
        ITunerHostManager tunerHostManager,
        ILiveTvManager liveTvManager,
        ILogger<LiveTvCategoryIndex> logger)
    {
        _tunerHostManager = tunerHostManager;
        _liveTvManager = liveTvManager;
        _logger = logger;
    }

    public async Task<UserCategorySnapshot> GetForUserAsync(User user, CancellationToken cancellationToken)
    {
        ArgumentNullException.ThrowIfNull(user);

        var snapshot = await GetSnapshotAsync(cancellationToken).ConfigureAwait(false);
        if (_userViews.TryGetValue(user.Id, out var cached) && ReferenceEquals(cached.Source, snapshot))
        {
            return cached;
        }

        var options = CreateIndexDtoOptions();
        var visibleChannels = _liveTvManager.GetInternalChannels(
            new LiveTvChannelQuery
            {
                UserId = user.Id,
                EnableUserData = false,
                AddCurrentProgram = false,
                SortBy = Array.Empty<ItemSortBy>()
            },
            options,
            cancellationToken);
        var visibleIds = visibleChannels.Items
            .OfType<LiveTvChannel>()
            .Select(channel => channel.Id)
            .ToHashSet();

        var view = snapshot.CreateUserView(visibleIds);
        _userViews[user.Id] = view;
        return view;
    }

    public void Invalidate()
    {
        Volatile.Write(ref _snapshot, null);
        _userViews.Clear();
    }

    public void Dispose()
    {
        _buildLock.Dispose();
    }

    private static DtoOptions CreateIndexDtoOptions()
    {
        return new DtoOptions(false)
        {
            EnableImages = false,
            EnableUserData = false,
            AddCurrentProgram = false
        };
    }

    private async Task<CategorySnapshot> GetSnapshotAsync(CancellationToken cancellationToken)
    {
        var now = DateTimeOffset.UtcNow;
        var cached = Volatile.Read(ref _snapshot);
        if (cached is not null && now - cached.GeneratedAtUtc < CacheDuration)
        {
            return cached;
        }

        await _buildLock.WaitAsync(cancellationToken).ConfigureAwait(false);
        try
        {
            cached = Volatile.Read(ref _snapshot);
            now = DateTimeOffset.UtcNow;
            if (cached is not null && now - cached.GeneratedAtUtc < CacheDuration)
            {
                return cached;
            }

            var rebuilt = await BuildSnapshotAsync(now, cancellationToken).ConfigureAwait(false);
            Volatile.Write(ref _snapshot, rebuilt);
            _userViews.Clear();
            return rebuilt;
        }
        finally
        {
            _buildLock.Release();
        }
    }

    private async Task<CategorySnapshot> BuildSnapshotAsync(DateTimeOffset generatedAtUtc, CancellationToken cancellationToken)
    {
        var persistedChannels = _liveTvManager.GetInternalChannels(
            new LiveTvChannelQuery
            {
                EnableUserData = false,
                AddCurrentProgram = false,
                SortBy = Array.Empty<ItemSortBy>()
            },
            CreateIndexDtoOptions(),
            cancellationToken);

        var persistedByExternalId = new Dictionary<string, LiveTvChannel>(StringComparer.Ordinal);
        foreach (var channel in persistedChannels.Items.OfType<LiveTvChannel>())
        {
            if (!string.IsNullOrEmpty(channel.ExternalId))
            {
                persistedByExternalId.TryAdd(channel.ExternalId, channel);
            }
        }

        var indexed = new List<IndexedChannel>(persistedByExternalId.Count);
        var matchedIds = new HashSet<Guid>();
        var unmatched = 0;

        foreach (var tunerHost in _tunerHostManager.TunerHosts.Where(
                     host => host.IsSupported && string.Equals(host.Type, "m3u", StringComparison.OrdinalIgnoreCase)))
        {
            var tunerChannels = await tunerHost.GetChannels(true, cancellationToken).ConfigureAwait(false);
            foreach (var tunerChannel in tunerChannels)
            {
                if (string.IsNullOrEmpty(tunerChannel.Id)
                    || !persistedByExternalId.TryGetValue(tunerChannel.Id, out var persisted)
                    || !matchedIds.Add(persisted.Id))
                {
                    unmatched++;
                    continue;
                }

                indexed.Add(new IndexedChannel(persisted.Id, tunerChannel.ChannelGroup));
            }
        }

        IReadOnlyList<string> providerOrder=Array.Empty<string>();
        IReadOnlyList<CategoryRecord> collections=Array.Empty<CategoryRecord>();
        try
        {
            var path=System.IO.Path.Combine(System.IO.Path.GetDirectoryName(typeof(LiveTvCategoryIndex).Assembly.Location)!, "channel-collections.json");
            (providerOrder,collections)=ChannelCollectionFile.Read(path);
        }
        catch (Exception ex) when (ex is System.IO.IOException or System.Text.Json.JsonException or FormatException or InvalidOperationException or KeyNotFoundException or ArgumentException)
        {
            _logger.LogWarning("Channel collection configuration unavailable: {ErrorType}; preserving normal channels",ex.GetType().Name);
        }
        var snapshot = CategorySnapshotBuilder.Build(indexed, generatedAtUtc, unmatched,providerOrder,collections);
        _logger.LogInformation(
            "Built Live TV category index with {CategoryCount} categories, {ChannelCount} matched channels and {UnmatchedCount} unmatched tuner records",
            snapshot.CreateUserView(matchedIds).Categories.Count,
            snapshot.TotalChannelCount,
            snapshot.UnmatchedChannelCount);
        return snapshot;
    }
}
