using System.Security.Claims;
using Jellyfin.Data.Enums;
using Jellyfin.Database.Implementations;
using Jellyfin.Database.Implementations.Entities;
using Jellyfin.Database.Implementations.Locking;
using Jellyfin.Database.Providers.Sqlite;
using Jellyfin.Plugin.LibraryExperience.Controllers;
using MediaBrowser.Common.Configuration;
using MediaBrowser.Controller.Entities;
using MediaBrowser.Controller.Entities.Movies;
using MediaBrowser.Controller.Library;
using MediaBrowser.Controller.Persistence;
using Microsoft.AspNetCore.Http;
using Microsoft.AspNetCore.Mvc;
using Moq;
using Microsoft.Data.Sqlite;
using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.Logging.Abstractions;
using Xunit;

namespace Jellyfin.Plugin.LibraryExperience.Tests;

public sealed class LibraryRatingsControllerTests : IDisposable
{
    private readonly string _directory = Path.Combine(Path.GetTempPath(), "library-ratings-" + Guid.NewGuid().ToString("N"));
    private readonly SqliteConnection _connection;
    private readonly DbContextOptions<JellyfinDbContext> _options;

    public LibraryRatingsControllerTests()
    {
        _connection = new SqliteConnection("Data Source=:memory:");
        _connection.Open();
        _options = new DbContextOptionsBuilder<JellyfinDbContext>().UseSqlite(_connection).Options;
        using var context = CreateContext();
        context.Database.EnsureCreated();
    }

    public void Dispose()
    {
        if (Directory.Exists(_directory))
        {
            Directory.Delete(_directory, recursive: true);
        }

        _connection.Dispose();
    }

    [Fact]
    public void RatingsIndex_RejectsStaleOrInvalidRatings()
    {
        WriteIndex("{\"schema\":1,\"fetched_at\":\"2000-01-01T00:00:00Z\",\"source_url\":\"https://datasets.imdbws.com/title.ratings.tsv.gz\",\"ratings\":{\"tt123\":{\"rating\":8.2,\"votes\":4}}}");
        Assert.Empty(Index().GetRatings());

        WriteIndex("{\"schema\":\"one\",\"fetched_at\":\"" + DateTimeOffset.UtcNow.ToString("O") + "\",\"source_url\":\"https://datasets.imdbws.com/title.ratings.tsv.gz\",\"ratings\":{\"tt123\":{\"rating\":8.2,\"votes\":4}}}");
        Assert.Empty(Index().GetRatings());

        WriteIndex("{\"schema\":1,\"fetched_at\":\"" + DateTimeOffset.UtcNow.ToString("O") + "\",\"source_url\":\"https://datasets.imdbws.com/title.ratings.tsv.gz\",\"ratings\":{\"tt123\":{\"rating\":8.2,\"votes\":4},\"tt123\":{\"rating\":8.3,\"votes\":5}}}");
        Assert.Empty(Index().GetRatings());

        WriteIndex("{\"schema\":1,\"fetched_at\":\"" + DateTimeOffset.UtcNow.ToString("O") + "\",\"source_url\":\"https://invalid.example/\",\"ratings\":{\"tt123\":{\"rating\":8.2,\"votes\":4}}}");
        Assert.Empty(Index().GetRatings());
    }

    [Fact]
    public void RatingsIndex_ReadsValidatedLocalData()
    {
        WriteIndex("{\"schema\":1,\"fetched_at\":\"" + DateTimeOffset.UtcNow.ToString("O") + "\",\"source_url\":\"https://datasets.imdbws.com/title.ratings.tsv.gz\",\"ratings\":{\"tt123\":{\"rating\":8.2,\"votes\":4}}}");
        var rating = Assert.Single(Index().GetRatings());
        Assert.Equal("tt123", rating.Key);
        Assert.Equal(8.2, rating.Value.Rating);
    }

    [Fact]
    public void RatingsIndex_ExpiresAnUnchangedCachedSnapshot()
    {
        var now = DateTimeOffset.UtcNow;
        WriteIndex("{\"schema\":1,\"fetched_at\":\"" + now.ToString("O") + "\",\"source_url\":\"https://datasets.imdbws.com/title.ratings.tsv.gz\",\"ratings\":{\"tt123\":{\"rating\":8.2,\"votes\":4}}}");
        var clock = new TestTimeProvider(now);
        var index = Index(clock);
        Assert.Single(index.GetRatings());

        clock.UtcNow = now.AddDays(14).AddSeconds(1);
        Assert.Empty(index.GetRatings());
    }

    [Fact]
    public void GetRatings_UsesCurrentClaimAndOnlyPermissionScopedMovies()
    {
        var userId = Guid.NewGuid();
        var allowedId = Guid.NewGuid();
        var hiddenId = Guid.NewGuid();
        var library = new Mock<ILibraryManager>();
        var scopeId = Guid.NewGuid();
        library.Setup(manager => manager.ConfigureUserAccess(It.IsAny<InternalItemsQuery>(), It.IsAny<User>()))
            .Callback<InternalItemsQuery, User>((query, _) => query.TopParentIds = [scopeId]);
        library.Setup(manager => manager.GetItemList(It.IsAny<InternalItemsQuery>()))
            .Returns((InternalItemsQuery query) =>
            {
                Assert.NotNull(query.User);
                Assert.Equal(userId, query.User!.Id);
                Assert.Equal([BaseItemKind.Movie, BaseItemKind.Series], query.IncludeItemTypes);
                Assert.Equal([allowedId], query.ItemIds);
                return [new Movie
                {
                    Id = allowedId,
                    ProviderIds = new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase) { ["Imdb"] = "tt123" },
                    CommunityRating = 7.7f
                }];
            });
        var users = new Mock<IUserManager>();
        users.Setup(manager => manager.GetUserById(userId)).Returns(new User("test", "test", "test") { Id = userId });
        WriteIndex("{\"schema\":1,\"fetched_at\":\"" + DateTimeOffset.UtcNow.ToString("O") + "\",\"source_url\":\"https://datasets.imdbws.com/title.ratings.tsv.gz\",\"ratings\":{\"tt123\":{\"rating\":8.2,\"votes\":4}}}");
        Seed(new BaseItemEntity { Id = allowedId, Type = typeof(Movie).FullName! });
        var queryHelpers = new Mock<IItemQueryHelpers>();
        queryHelpers.Setup(helper => helper.ApplyAccessFiltering(It.IsAny<JellyfinDbContext>(), It.IsAny<IQueryable<BaseItemEntity>>(), It.IsAny<InternalItemsQuery>()))
            .Returns((JellyfinDbContext _, IQueryable<BaseItemEntity> query, InternalItemsQuery access) =>
            {
                Assert.Equal([scopeId], access.TopParentIds);
                return query;
            });
        var controller = new LibraryRatingsController(library.Object, users.Object, new ContextFactory(CreateContext), queryHelpers.Object, Index())
        {
            ControllerContext = new ControllerContext
            {
                HttpContext = new DefaultHttpContext
                {
                    User = new ClaimsPrincipal(new ClaimsIdentity([new Claim("Jellyfin-UserId", userId.ToString())], "test"))
                }
            }
        };

        var result = controller.GetRatings(allowedId + "," + allowedId + "," + hiddenId);

        var ok = Assert.IsType<OkObjectResult>(result.Result);
        var payload = Assert.IsType<LibraryRatingsController.RatingsResponse>(ok.Value);
        var item = Assert.Single(payload.Items);
        Assert.Equal(allowedId.ToString("N"), item.Key);
        Assert.Equal(8.2, item.Value.Imdb!.Rating);
        Assert.Equal(7.7f, item.Value.Community);
        Assert.NotNull(payload.FetchedAt);
        Assert.Equal("private, no-store", controller.Response.Headers.CacheControl);
    }

    [Fact]
    public void GetRatings_RejectsMissingCurrentUserOrUnboundedInput()
    {
        var controller = new LibraryRatingsController(Mock.Of<ILibraryManager>(), Mock.Of<IUserManager>(), Mock.Of<IDbContextFactory<JellyfinDbContext>>(), Mock.Of<IItemQueryHelpers>(), Index())
        {
            ControllerContext = new ControllerContext { HttpContext = new DefaultHttpContext() }
        };

        Assert.IsType<UnauthorizedResult>(controller.GetRatings(Guid.NewGuid().ToString()).Result);
        Assert.IsType<BadRequestObjectResult>(controller.GetRatings("not-a-guid").Result);
    }

    private RatingsIndex Index()
        => Index(TimeProvider.System);

    private RatingsIndex Index(TimeProvider timeProvider)
    {
        var paths = new Mock<IApplicationPaths>();
        paths.SetupGet(path => path.PluginConfigurationsPath).Returns(_directory);
        return new RatingsIndex(paths.Object, timeProvider);
    }

    private void WriteIndex(string json)
    {
        var directory = Path.Combine(_directory, "library-experience");
        Directory.CreateDirectory(directory);
        File.WriteAllText(Path.Combine(directory, "imdb-library-ratings.json"), json);
    }

    private JellyfinDbContext CreateContext()
    {
        var paths = new Mock<IApplicationPaths>();
        return new JellyfinDbContext(
            _options,
            NullLogger<JellyfinDbContext>.Instance,
            new SqliteDatabaseProvider(paths.Object, NullLogger<SqliteDatabaseProvider>.Instance),
            new NoLockBehavior(NullLogger<NoLockBehavior>.Instance));
    }

    private void Seed(BaseItemEntity entity)
    {
        using var context = CreateContext();
        context.BaseItems.Add(entity);
        context.SaveChanges();
    }

    private sealed class ContextFactory(Func<JellyfinDbContext> factory) : IDbContextFactory<JellyfinDbContext>
    {
        public JellyfinDbContext CreateDbContext() => factory();

        public Task<JellyfinDbContext> CreateDbContextAsync(CancellationToken cancellationToken = default)
            => Task.FromResult(factory());
    }

    private sealed class TestTimeProvider(DateTimeOffset utcNow) : TimeProvider
    {
        public DateTimeOffset UtcNow { get; set; } = utcNow;

        public override DateTimeOffset GetUtcNow() => UtcNow;
    }
}
