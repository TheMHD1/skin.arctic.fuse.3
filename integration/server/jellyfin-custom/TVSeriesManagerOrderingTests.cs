using System;
using System.Collections.Generic;
using System.Linq;
using Emby.Server.Implementations.TV;
using Jellyfin.Database.Implementations.Entities;
using MediaBrowser.Controller.Configuration;
using MediaBrowser.Controller.Dto;
using MediaBrowser.Controller.Entities;
using MediaBrowser.Controller.Entities.TV;
using MediaBrowser.Controller.Library;
using MediaBrowser.Controller.Persistence;
using MediaBrowser.Model.Configuration;
using MediaBrowser.Model.Entities;
using MediaBrowser.Model.Querying;
using Moq;
using Xunit;

namespace Jellyfin.Server.Implementations.Tests.Item;

/// <summary>Regression coverage for activity ordering and one-card-per-series Next Up.</summary>
public sealed class TVSeriesManagerOrderingTests : IDisposable
{
    private readonly User _user = new("test", "auth-provider", "reset-provider");
    private readonly ILibraryManager? _previousLibraryManager = BaseItem.LibraryManager;

    public void Dispose()
        => BaseItem.LibraryManager = _previousLibraryManager!;

    [Fact]
    public void GetNextUp_PreservesAuthoritativeSeriesActivityOrder()
    {
        var recentNext = Episode("recent-next", 2);
        var olderNext = Episode("older-next", 2);
        var recentLast = Episode("recent-last", 1);
        var olderLast = Episode("older-last", 1);

        // The service has already ranked "recent" first from all playback rows. The
        // furthest completed episode is not necessarily the episode played most recently,
        // so its own timestamp must not be used to reorder the series afterward.
        var manager = CreateManager(
            ["recent", "older"],
            new Dictionary<string, NextUpEpisodeBatchResult>
            {
                ["recent"] = new() { LastWatched = recentLast, NextUp = recentNext },
                ["older"] = new() { LastWatched = olderLast, NextUp = olderNext }
            },
            new Dictionary<Guid, DateTime?>
            {
                [recentLast.Id] = new DateTime(2026, 1, 1, 0, 0, 0, DateTimeKind.Utc),
                [olderLast.Id] = new DateTime(2026, 2, 1, 0, 0, 0, DateTimeKind.Utc)
            });

        var result = manager.GetNextUp(Query(), Array.Empty<BaseItem>(), new DtoOptions());

        Assert.Equal([recentNext.Id, olderNext.Id], result.Items.Select(i => i.Id));

        var page = manager.GetNextUp(Query(startIndex: 1, limit: 1), Array.Empty<BaseItem>(), new DtoOptions());

        Assert.Equal(2, page.TotalRecordCount);
        Assert.Single(page.Items);
        Assert.Equal(olderNext.Id, page.Items[0].Id);
    }

    [Fact]
    public void GetNextUp_RewatchingReturnsOneEpisodePerSeriesAndRecentRewindWins()
    {
        var normalNext = Episode("normal-next", 8);
        var replayNext = Episode("replay-next", 3);
        var furthestCompleted = Episode("furthest-completed", 7);
        var recentlyReplayed = Episode("recently-replayed", 2);

        var manager = CreateManager(
            ["series"],
            new Dictionary<string, NextUpEpisodeBatchResult>
            {
                ["series"] = new()
                {
                    LastWatched = furthestCompleted,
                    NextUp = normalNext,
                    LastWatchedForRewatching = recentlyReplayed,
                    NextPlayedForRewatching = replayNext
                }
            },
            new Dictionary<Guid, DateTime?>
            {
                [furthestCompleted.Id] = new DateTime(2026, 1, 1, 0, 0, 0, DateTimeKind.Utc),
                [recentlyReplayed.Id] = new DateTime(2026, 2, 1, 0, 0, 0, DateTimeKind.Utc)
            });

        var result = manager.GetNextUp(Query(enableRewatching: true), Array.Empty<BaseItem>(), new DtoOptions());

        Assert.Single(result.Items);
        Assert.Equal(replayNext.Id, result.Items[0].Id);
        Assert.Equal(1, result.TotalRecordCount);
    }

    private TVSeriesManager CreateManager(
        IReadOnlyList<string> seriesKeys,
        IReadOnlyDictionary<string, NextUpEpisodeBatchResult> batch,
        IReadOnlyDictionary<Guid, DateTime?> playedDates)
    {
        var userData = new Mock<IUserDataManager>();
        userData
            .Setup(m => m.GetUserDataBatch(It.IsAny<IReadOnlyList<BaseItem>>(), It.IsAny<User>()))
            .Returns((IReadOnlyList<BaseItem> items, User _) => items.ToDictionary(
                item => item.Id,
                item => new UserItemData
                {
                    Key = item.Id.ToString("N"),
                    LastPlayedDate = playedDates.GetValueOrDefault(item.Id)
                }));

        var library = new Mock<ILibraryManager>();
        library
            .Setup(m => m.GetNextUpSeriesKeys(
                It.IsAny<InternalItemsQuery>(),
                It.IsAny<IReadOnlyCollection<BaseItem>>(),
                It.IsAny<DateTime>()))
            .Returns(seriesKeys);
        library
            .Setup(m => m.GetNextUpEpisodesBatch(
                It.IsAny<InternalItemsQuery>(),
                It.IsAny<IReadOnlyList<string>>(),
                It.IsAny<bool>(),
                It.IsAny<bool>()))
            .Returns(batch);
        library.Setup(m => m.GetLinkedAlternateVersions(It.IsAny<Video>())).Returns(Array.Empty<Video>());
        library.Setup(m => m.GetLocalAlternateVersionIds(It.IsAny<Video>())).Returns(Array.Empty<Guid>());
        BaseItem.LibraryManager = library.Object;

        var configuration = new Mock<IServerConfigurationManager>();
        configuration.SetupGet(m => m.Configuration).Returns(new ServerConfiguration());

        return new TVSeriesManager(userData.Object, library.Object, configuration.Object);
    }

    private NextUpQuery Query(bool enableRewatching = false, int? startIndex = null, int? limit = null)
        => new()
        {
            User = _user,
            EnableTotalRecordCount = true,
            EnableResumable = true,
            EnableRewatching = enableRewatching,
            StartIndex = startIndex,
            Limit = limit
        };

    private static Episode Episode(string name, int index)
        => new()
        {
            Id = Guid.NewGuid(),
            Name = name,
            IndexNumber = index,
            ParentIndexNumber = 1
        };
}
