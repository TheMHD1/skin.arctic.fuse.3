using System.Reflection;
using Jellyfin.Database.Implementations;
using Jellyfin.Database.Implementations.Entities;
using Jellyfin.Database.Implementations.Locking;
using Jellyfin.Database.Providers.Sqlite;
using Jellyfin.Plugin.LibraryExperience.Controllers;
using MediaBrowser.Common.Api;
using MediaBrowser.Common.Configuration;
using MediaBrowser.Controller.Entities;
using MediaBrowser.Controller.Entities.Movies;
using MediaBrowser.Controller.Entities.TV;
using MediaBrowser.Controller.Library;
using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc;
using Microsoft.Data.Sqlite;
using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.Logging.Abstractions;
using Moq;
using Xunit;

namespace Jellyfin.Plugin.LibraryExperience.Tests;

public sealed class LibraryImportDateControllerTests : IDisposable
{
    private static readonly DateTime OldDate = new(2020, 1, 1, 0, 0, 0, DateTimeKind.Utc);
    private static readonly DateTime NewDate = new(2025, 1, 1, 0, 0, 0, DateTimeKind.Utc);
    private readonly SqliteConnection _connection;
    private readonly DbContextOptions<JellyfinDbContext> _options;
    private readonly Mock<ILibraryManager> _libraryManager = new();

    public LibraryImportDateControllerTests()
    {
        _connection = new SqliteConnection("Data Source=:memory:");
        _connection.Open();
        _options = new DbContextOptionsBuilder<JellyfinDbContext>()
            .UseSqlite(_connection)
            .Options;
        using var context = CreateContext();
        context.Database.EnsureCreated();
    }

    public void Dispose() => _connection.Dispose();

    [Fact]
    public async Task UpdateImportDate_ChangesOnlyDatabaseAndCacheDateCreated()
    {
        var id = Guid.NewGuid();
        const string Path = "/media/movies/example.mkv";
        var dateModified = new DateTime(2024, 6, 1, 0, 0, 0, DateTimeKind.Utc);
        Seed(new BaseItemEntity
        {
            Id = id,
            Type = typeof(Movie).FullName!,
            Path = Path,
            DateCreated = OldDate,
            DateModified = dateModified,
            DateLastMediaAdded = new DateTime(2023, 1, 1, 0, 0, 0, DateTimeKind.Utc),
            Name = "Keep title",
            Overview = "Keep overview",
            Data = "{\"keep\":true}"
        });
        var item = new Movie { Id = id, Path = Path, DateCreated = OldDate, Name = "Keep title", Overview = "Keep overview" };
        ReturnItem(item);

        var result = await Controller().UpdateImportDate(id, Request(Path), CancellationToken.None);

        Assert.IsType<NoContentResult>(result);
        Assert.Equal(NewDate, item.DateCreated);
        using var verify = CreateContext();
        var row = verify.BaseItems.AsNoTracking().Single(entity => entity.Id == id);
        Assert.Equal(NewDate.Ticks, row.DateCreated?.Ticks);
        Assert.Equal(dateModified.Ticks, row.DateModified?.Ticks);
        Assert.Equal(new DateTime(2023, 1, 1).Ticks, row.DateLastMediaAdded?.Ticks);
        Assert.Equal("Keep title", row.Name);
        Assert.Equal("Keep overview", row.Overview);
        Assert.Equal("{\"keep\":true}", row.Data);
    }

    [Theory]
    [InlineData(true, false)]
    [InlineData(false, true)]
    public async Task UpdateImportDate_RejectsDatabaseIdentityDrift(bool pathDrift, bool dateDrift)
    {
        var id = Guid.NewGuid();
        const string ExpectedPath = "/media/movies/example.mkv";
        Seed(new BaseItemEntity
        {
            Id = id,
            Type = typeof(Movie).FullName!,
            Path = pathDrift ? "/media/movies/replaced.mkv" : ExpectedPath,
            DateCreated = dateDrift ? OldDate.AddSeconds(1) : OldDate,
            Name = "Unchanged"
        });
        var item = new Movie { Id = id, Path = ExpectedPath, DateCreated = OldDate };
        ReturnItem(item);

        var result = await Controller().UpdateImportDate(id, Request(ExpectedPath), CancellationToken.None);

        Assert.IsType<ConflictObjectResult>(result);
        Assert.Equal(OldDate, item.DateCreated);
        using var verify = CreateContext();
        var row = verify.BaseItems.AsNoTracking().Single(entity => entity.Id == id);
        Assert.NotEqual(NewDate.Ticks, row.DateCreated?.Ticks);
        Assert.Equal("Unchanged", row.Name);
    }

    [Theory]
    [InlineData(true, false)]
    [InlineData(false, true)]
    public async Task UpdateImportDate_RejectsDatabaseTypeOrVirtualDrift(bool typeDrift, bool virtualDrift)
    {
        var id = Guid.NewGuid();
        const string Path = "/media/movies/example.mkv";
        Seed(new BaseItemEntity
        {
            Id = id,
            Type = typeDrift ? typeof(Series).FullName! : typeof(Movie).FullName!,
            IsVirtualItem = virtualDrift,
            Path = Path,
            DateCreated = OldDate
        });
        var item = new Movie { Id = id, Path = Path, DateCreated = OldDate };
        ReturnItem(item);
        var result = await Controller().UpdateImportDate(id, Request(Path), CancellationToken.None);
        Assert.IsType<ConflictObjectResult>(result);
        Assert.Equal(OldDate, item.DateCreated);
        using var verify = CreateContext();
        Assert.Equal(OldDate.Ticks, verify.BaseItems.Single(entity => entity.Id == id).DateCreated?.Ticks);
    }

    [Theory]
    [InlineData("/media/venom/example.strm")]
    [InlineData("http://example.invalid/video")]
    public async Task UpdateImportDate_RejectsNonLocalMedia(string path)
    {
        var item = new Movie { Id = Guid.NewGuid(), Path = path, DateCreated = OldDate };
        ReturnItem(item);

        var result = await Controller().UpdateImportDate(item.Id, Request(path), CancellationToken.None);

        Assert.IsType<BadRequestObjectResult>(result);
    }

    [Fact]
    public async Task RefreshLatestDates_UsesNewestLocalEpisodeAndOnlyChangesDerivedColumn()
    {
        var seriesId = Guid.NewGuid();
        Seed(
            new BaseItemEntity
            {
                Id = seriesId,
                Type = typeof(Series).FullName!,
                Path = "/media/shows/example",
                DateCreated = OldDate,
                DateLastMediaAdded = null,
                Name = "Keep series title",
                Overview = "Keep series overview"
            },
            Episode(seriesId, "/media/shows/example/s01e01.mkv", NewDate.AddDays(-1)),
            Episode(seriesId, "/media/shows/example/s01e02.mkv", NewDate),
            Episode(seriesId, "/media/shows/example/remote.strm", NewDate.AddDays(1)));
        var series = new Series { Id = seriesId, Path = "/media/shows/example", DateLastMediaAdded = null };
        ReturnItem(series);

        var result = await Controller().RefreshLatestDates(
            new LibraryImportDateController.RefreshLatestDatesRequest { SeriesIds = [seriesId, seriesId] },
            CancellationToken.None);

        var ok = Assert.IsType<OkObjectResult>(result.Result);
        var payload = Assert.IsType<LibraryImportDateController.RefreshLatestDatesResult>(ok.Value);
        Assert.Equal(1, payload.UpdatedSeries);
        Assert.Equal(NewDate, series.DateLastMediaAdded);
        using var verify = CreateContext();
        var row = verify.BaseItems.AsNoTracking().Single(entity => entity.Id == seriesId);
        Assert.Equal(NewDate.Ticks, row.DateLastMediaAdded?.Ticks);
        Assert.Equal(OldDate.Ticks, row.DateCreated?.Ticks);
        Assert.Equal("Keep series title", row.Name);
        Assert.Equal("Keep series overview", row.Overview);
    }

    [Fact]
    public async Task RefreshLatestDates_RejectsMoreThanFiveHundredSubmittedIds()
    {
        var result = await Controller().RefreshLatestDates(
            new LibraryImportDateController.RefreshLatestDatesRequest
            {
                SeriesIds = Enumerable.Repeat(Guid.NewGuid(), 501).ToArray()
            },
            CancellationToken.None);

        Assert.IsType<BadRequestObjectResult>(result.Result);
    }

    [Fact]
    public void Controller_IsAdminOnlyApiWithStableRoutes()
    {
        var controllerType = typeof(LibraryImportDateController);
        Assert.NotNull(controllerType.GetCustomAttribute<ApiControllerAttribute>());
        var authorization = Assert.Single(controllerType.GetCustomAttributes<AuthorizeAttribute>());
        Assert.Equal(Policies.RequiresElevation, authorization.Policy);
        Assert.Equal("Habibi/LibraryImportDate", Assert.Single(controllerType.GetCustomAttributes<RouteAttribute>()).Template);

        var refresh = controllerType.GetMethod(nameof(LibraryImportDateController.RefreshLatestDates));
        Assert.Equal("RefreshLatestDates", Assert.Single(refresh!.GetCustomAttributes<HttpPostAttribute>()).Template);
    }

    private static LibraryImportDateController.ImportDateUpdate Request(string path) => new()
    {
        ExpectedPath = path,
        ExpectedDateCreated = OldDate,
        DateCreated = NewDate
    };

    private static BaseItemEntity Episode(Guid seriesId, string path, DateTime dateCreated) => new()
    {
        Id = Guid.NewGuid(),
        Type = typeof(Episode).FullName!,
        SeriesId = seriesId,
        Path = path,
        DateCreated = dateCreated
    };

    private void ReturnItem(BaseItem item)
        => _libraryManager.Setup(manager => manager.GetItemById<BaseItem>(item.Id)).Returns(item);

    private LibraryImportDateController Controller()
        => new(_libraryManager.Object, new ContextFactory(CreateContext));

    private void Seed(params BaseItemEntity[] entities)
    {
        using var context = CreateContext();
        context.BaseItems.AddRange(entities);
        context.SaveChanges();
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

    private sealed class ContextFactory(Func<JellyfinDbContext> factory) : IDbContextFactory<JellyfinDbContext>
    {
        public JellyfinDbContext CreateDbContext() => factory();

        public Task<JellyfinDbContext> CreateDbContextAsync(CancellationToken cancellationToken = default)
            => Task.FromResult(factory());
    }
}
