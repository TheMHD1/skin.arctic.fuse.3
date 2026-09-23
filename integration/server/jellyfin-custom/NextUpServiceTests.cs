using System;
using System.Linq;
using Emby.Server.Implementations.Data;
using Jellyfin.Database.Implementations;
using Jellyfin.Database.Implementations.Entities;
using Jellyfin.Server.Implementations.Item;
using MediaBrowser.Controller.Entities;
using MediaBrowser.Model.Entities;
using Xunit;
using LinkedChildType = Jellyfin.Database.Implementations.Entities.LinkedChildType;

namespace Jellyfin.Server.Implementations.Tests.Item;

/// <summary>
/// Covers Next Up over episodes with alternate versions: the episode that was watched is the one
/// whose alternate carries the played row, so an episode already seen must not be offered again.
/// </summary>
public sealed class NextUpServiceTests : SqliteDbTestFixture
{
    private const string SeriesKey = "next-up-series";
    private const string EpisodeType = "MediaBrowser.Controller.Entities.TV.Episode";

    private readonly NextUpService _service;
    private readonly User _user = new("test", "auth-provider", "reset-provider");

    private readonly Guid _playedViaAlternate = Guid.NewGuid();
    private readonly Guid _unplayed = Guid.NewGuid();

    public NextUpServiceTests()
    {
        var itemTypeLookup = new ItemTypeLookup();

        using (var context = CreateDbContext())
        {
            Seed(context);
        }

        _service = new NextUpService(
            CreateDbContextFactory(),
            itemTypeLookup,
            CreateBaseItemRepository(itemTypeLookup));
    }

    [Fact]
    public void GetNextUpEpisodesBatch_EpisodePlayedThroughItsAlternateVersion_OffersTheOneAfterIt()
    {
        var batch = _service.GetNextUpEpisodesBatch(
            new InternalItemsQuery(_user),
            [SeriesKey],
            includeSpecials: false,
            includeWatchedForRewatching: false)[SeriesKey];

        Assert.Equal(_playedViaAlternate, batch.LastWatched?.Id);
        Assert.Equal(_unplayed, batch.NextUp?.Id);
    }

    [Fact]
    public void GetNextUpSeriesKeys_AppliesAccessRulesBeforeRankingActivity()
    {
        var topParentId = Guid.NewGuid();
        var visibleId = Guid.NewGuid();
        var hiddenId = Guid.NewGuid();
        const string VisibleKey = "visible-series";
        const string HiddenKey = "hidden-series";

        using (var context = CreateDbContext())
        {
            AddActivityEpisode(
                context,
                visibleId,
                VisibleKey,
                topParentId,
                parentalRating: 5,
                new DateTime(2026, 1, 1, 0, 0, 0, DateTimeKind.Utc));
            AddActivityEpisode(
                context,
                hiddenId,
                HiddenKey,
                topParentId,
                parentalRating: 18,
                new DateTime(2026, 2, 1, 0, 0, 0, DateTimeKind.Utc));
            context.SaveChanges();
        }

        var keys = _service.GetNextUpSeriesKeys(
            new InternalItemsQuery(_user)
            {
                TopParentIds = [topParentId],
                MaxParentalRating = new ParentalRatingScore(10, null)
            },
            DateTime.MinValue);

        Assert.Equal([VisibleKey], keys);
    }

    private void Seed(JellyfinDbContext context)
    {
        context.Users.Add(_user);

        AddEpisode(context, _playedViaAlternate, 1);
        AddEpisode(context, _unplayed, 2);

        // The second file of the first episode, and the only row the playback was recorded against.
        // It presents under its primary's key, which is what keeps it out of the candidate list.
        var alternateId = Guid.NewGuid();
        context.BaseItems.Add(new BaseItemEntity
        {
            Id = alternateId,
            Type = EpisodeType,
            Name = "Episode 1 4K",
            SeriesPresentationUniqueKey = SeriesKey,
            ParentIndexNumber = 1,
            IndexNumber = 1,
            PresentationUniqueKey = _playedViaAlternate.ToString("N"),
            PrimaryVersionId = _playedViaAlternate
        });

        context.SaveChanges();

        // The link the scanner writes alongside PrimaryVersionId, and the hop the played state
        // reaches the alternate through.
        context.LinkedChildren.Add(new LinkedChildEntity
        {
            ParentId = _playedViaAlternate,
            ChildId = alternateId,
            ChildType = LinkedChildType.LocalAlternateVersion,
            SortOrder = 0
        });

        context.UserData.Add(new UserData
        {
            ItemId = alternateId,
            UserId = _user.Id,
            CustomDataKey = alternateId.ToString("N"),
            Played = true,
            Item = null!,
            User = null!
        });

        context.SaveChanges();
    }

    private void AddEpisode(JellyfinDbContext context, Guid id, int indexNumber)
        => context.BaseItems.Add(new BaseItemEntity
        {
            Id = id,
            Type = EpisodeType,
            Name = $"Episode {indexNumber}",
            SeriesPresentationUniqueKey = SeriesKey,
            ParentIndexNumber = 1,
            IndexNumber = indexNumber,
            PresentationUniqueKey = id.ToString("N")
        });

    private void AddActivityEpisode(
        JellyfinDbContext context,
        Guid id,
        string seriesKey,
        Guid topParentId,
        int parentalRating,
        DateTime lastPlayedDate)
    {
        context.BaseItems.Add(new BaseItemEntity
        {
            Id = id,
            Type = EpisodeType,
            Name = seriesKey,
            SeriesPresentationUniqueKey = seriesKey,
            ParentIndexNumber = 1,
            IndexNumber = 1,
            PresentationUniqueKey = id.ToString("N"),
            TopParentId = topParentId,
            InheritedParentalRatingValue = parentalRating
        });
        context.UserData.Add(new UserData
        {
            ItemId = id,
            UserId = _user.Id,
            CustomDataKey = id.ToString("N"),
            Played = true,
            LastPlayedDate = lastPlayedDate,
            Item = null!,
            User = null!
        });
    }
}
