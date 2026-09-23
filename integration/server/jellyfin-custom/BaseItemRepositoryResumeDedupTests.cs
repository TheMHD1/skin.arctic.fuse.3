using System;
using System.Linq;
using Emby.Server.Implementations.Data;
using Jellyfin.Data.Enums;
using Jellyfin.Database.Implementations;
using Jellyfin.Database.Implementations.Entities;
using Jellyfin.Database.Implementations.Enums;
using Jellyfin.Server.Implementations.Item;
using MediaBrowser.Controller.Entities;
using Xunit;
using ItemSortBy = Jellyfin.Data.Enums.ItemSortBy;

namespace Jellyfin.Server.Implementations.Tests.Item;

/// <summary>Tests the server-wide one-card-per-series Continue Watching policy.</summary>
public sealed class BaseItemRepositoryResumeDedupTests : SqliteDbTestFixture
{
    private const string MovieType = "MediaBrowser.Controller.Entities.Movies.Movie";
    private const string EpisodeType = "MediaBrowser.Controller.Entities.TV.Episode";
    private readonly User _user = new("test", "auth-provider", "reset-provider");
    private readonly User _otherUser = new("other", "auth-provider", "reset-provider");
    private readonly BaseItemRepository _repository;
    private readonly (Guid First, Guid Second) _staleSeries;
    private readonly (Guid First, Guid Second) _rewatchSeries;
    private readonly (Guid First, Guid Second) _legacySeries;
    private readonly (Guid First, Guid Second) _tieSeries;
    private readonly Guid _legacyFavouriteResume;
    private readonly Guid _movie = Guid.NewGuid();

    public BaseItemRepositoryResumeDedupTests()
    {
        using (var context = CreateDbContext())
        {
            context.Users.Add(_user);
            context.Users.Add(_otherUser);
            _staleSeries = AddSeries(context, "Stale", olderResumeIsLatest: false);
            _rewatchSeries = AddSeries(context, "Rewatch", olderResumeIsLatest: true);
            _legacySeries = AddLegacySeries(context, "Legacy");
            _tieSeries = AddTieSeries(context, "Tie");
            _legacyFavouriteResume = AddFavouriteOnlySeries(context, "Favourite ignored");
            AddMovieResume(context, _movie);
            context.SaveChanges();
        }

        _repository = CreateBaseItemRepository(new ItemTypeLookup());
    }

    [Fact]
    public void IsResumable_UsesNewestActivityOncePerSeries()
    {
        var resumable = _repository.GetItemList(new InternalItemsQuery(_user) { IsResumable = true })
            .Select(i => i.Id)
            .ToHashSet();

        // A later completed episode hides both stale earlier resume points.
        Assert.DoesNotContain(_staleSeries.First, resumable);
        Assert.DoesNotContain(_staleSeries.Second, resumable);

        // Revisiting the earlier episode later is intentional and keeps that point.
        Assert.Contains(_rewatchSeries.First, resumable);
        Assert.DoesNotContain(_rewatchSeries.Second, resumable);

        // A favourite-only row has no playback activity and cannot hide legacy resume.
        Assert.Contains(_legacyFavouriteResume, resumable);

        // Timestamp-less migrated rows select the furthest progressed episode;
        // a later legacy completion clears stale resume points altogether.
        Assert.DoesNotContain(_legacySeries.First, resumable);
        Assert.DoesNotContain(_legacySeries.Second, resumable);

        // Equal-time updates must stay deterministic and prefer the later episode.
        Assert.DoesNotContain(_tieSeries.First, resumable);
        Assert.Contains(_tieSeries.Second, resumable);

        // The rule never changes non-series resume behaviour.
        Assert.Contains(_movie, resumable);

        // Filtering happens before paging, so a duplicate series cannot consume
        // a page slot or inflate TotalRecordCount for any client.
        var page = _repository.GetItems(new InternalItemsQuery(_user)
        {
            IsResumable = true,
            OrderBy = [(ItemSortBy.DatePlayed, SortOrder.Descending)],
            StartIndex = 1,
            Limit = 1,
            EnableTotalRecordCount = true
        });
        Assert.Equal(4, page.TotalRecordCount);
        Assert.Single(page.Items);
        Assert.Equal(_tieSeries.Second, page.Items[0].Id);

        // Activity for another account must never change this account's card.
        var otherResumable = _repository.GetItemList(new InternalItemsQuery(_otherUser) { IsResumable = true })
            .Select(i => i.Id)
            .ToHashSet();
        Assert.Contains(_rewatchSeries.Second, otherResumable);
        Assert.DoesNotContain(_rewatchSeries.First, otherResumable);
    }

    [Fact]
    public void IsResumable_TopParentFilter_DoesNotLetHiddenActivitySuppressAllowedResume()
    {
        var allowedTopParent = Guid.NewGuid();
        var hiddenTopParent = Guid.NewGuid();
        var seriesId = Guid.NewGuid();
        var seriesKey = seriesId.ToString("N");
        var allowedResume = Guid.NewGuid();
        var hiddenLaterEpisode = Guid.NewGuid();

        using (var context = CreateDbContext())
        {
            AddEpisode(context, allowedResume, seriesId, seriesKey, 1, "Allowed episode", allowedTopParent);
            AddEpisode(context, hiddenLaterEpisode, seriesId, seriesKey, 2, "Hidden episode", hiddenTopParent);
            AddResume(context, allowedResume, new DateTime(2026, 9, 20, 12, 0, 0, DateTimeKind.Utc));
            AddPlayed(context, hiddenLaterEpisode, new DateTime(2026, 9, 20, 13, 0, 0, DateTimeKind.Utc));
            context.SaveChanges();
        }

        var items = _repository.GetItemList(new InternalItemsQuery(_user)
        {
            IsResumable = true,
            IncludeItemTypes = [BaseItemKind.Episode],
            TopParentIds = [allowedTopParent]
        });

        Assert.Contains(items, item => item.Id.Equals(allowedResume));
        Assert.DoesNotContain(items, item => item.Id.Equals(hiddenLaterEpisode));
    }

    private (Guid First, Guid Second) AddSeries(JellyfinDbContext context, string name, bool olderResumeIsLatest)
    {
        var seriesId = Guid.NewGuid();
        var first = Guid.NewGuid();
        var second = Guid.NewGuid();
        var third = Guid.NewGuid();
        var seriesKey = seriesId.ToString("N");
        var early = new DateTime(2026, 9, 20, 12, 0, 0, DateTimeKind.Utc);
        var late = early.AddHours(1);

        AddEpisode(context, first, seriesId, seriesKey, 1, name + " 1");
        AddEpisode(context, second, seriesId, seriesKey, 2, name + " 2");
        AddEpisode(context, third, seriesId, seriesKey, 3, name + " 3");
        AddResume(context, first, olderResumeIsLatest ? late : early);
        AddResume(context, second, early);
        AddPlayed(context, third, olderResumeIsLatest ? early : late);
        if (olderResumeIsLatest)
        {
            AddResume(context, second, late.AddHours(1), _otherUser);
        }

        return (first, second);
    }

    private (Guid First, Guid Second) AddLegacySeries(JellyfinDbContext context, string name)
    {
        var seriesId = Guid.NewGuid();
        var first = Guid.NewGuid();
        var second = Guid.NewGuid();
        var third = Guid.NewGuid();
        var key = seriesId.ToString("N");
        AddEpisode(context, first, seriesId, key, 1, name + " 1");
        AddEpisode(context, second, seriesId, key, 2, name + " 2");
        AddEpisode(context, third, seriesId, key, 3, name + " 3");
        AddResume(context, first, null);
        AddResume(context, second, null);
        AddPlayed(context, third, null);
        return (first, second);
    }

    private (Guid First, Guid Second) AddTieSeries(JellyfinDbContext context, string name)
    {
        var seriesId = Guid.NewGuid();
        var first = Guid.NewGuid();
        var second = Guid.NewGuid();
        var key = seriesId.ToString("N");
        var sameTime = new DateTime(2026, 9, 21, 12, 0, 0, DateTimeKind.Utc);
        AddEpisode(context, first, seriesId, key, 1, name + " 1");
        AddEpisode(context, second, seriesId, key, 2, name + " 2");
        AddResume(context, first, sameTime);
        AddResume(context, second, sameTime);
        return (first, second);
    }

    private Guid AddFavouriteOnlySeries(JellyfinDbContext context, string name)
    {
        var seriesId = Guid.NewGuid();
        var resume = Guid.NewGuid();
        var favourite = Guid.NewGuid();
        var key = seriesId.ToString("N");
        AddEpisode(context, resume, seriesId, key, 1, name + " 1");
        AddEpisode(context, favourite, seriesId, key, 2, name + " 2");
        AddResume(context, resume, null);
        context.UserData.Add(new UserData { ItemId = favourite, UserId = _user.Id, CustomDataKey = favourite.ToString("N"), IsFavorite = true, Item = null!, User = null! });
        return resume;
    }

    private static void AddEpisode(
        JellyfinDbContext context,
        Guid id,
        Guid seriesId,
        string seriesKey,
        int index,
        string name,
        Guid? topParentId = null)
        => context.BaseItems.Add(new BaseItemEntity
        {
            Id = id, Type = EpisodeType, Name = name, SortName = name,
            PresentationUniqueKey = id.ToString("N"), SeriesId = seriesId,
            SeriesPresentationUniqueKey = seriesKey, ParentIndexNumber = 1, IndexNumber = index,
            TopParentId = topParentId
        });

    private void AddMovieResume(JellyfinDbContext context, Guid id)
    {
        context.BaseItems.Add(new BaseItemEntity { Id = id, Type = MovieType, Name = "Movie", SortName = "Movie", PresentationUniqueKey = id.ToString("N") });
        AddResume(context, id, new DateTime(2026, 9, 22, 12, 0, 0, DateTimeKind.Utc));
    }

    private void AddResume(JellyfinDbContext context, Guid itemId, DateTime? lastPlayed, User? user = null)
        => context.UserData.Add(new UserData { ItemId = itemId, UserId = (user ?? _user).Id, CustomDataKey = itemId.ToString("N"), PlaybackPositionTicks = 10_000_000, LastPlayedDate = lastPlayed, Item = null!, User = null! });

    private void AddPlayed(JellyfinDbContext context, Guid itemId, DateTime? lastPlayed)
        => context.UserData.Add(new UserData { ItemId = itemId, UserId = _user.Id, CustomDataKey = itemId.ToString("N"), Played = true, LastPlayedDate = lastPlayed, Item = null!, User = null! });
}
