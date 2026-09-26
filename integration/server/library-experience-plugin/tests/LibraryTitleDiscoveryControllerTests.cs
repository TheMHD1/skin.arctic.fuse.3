using System.Reflection;
using Jellyfin.Data.Enums;
using Jellyfin.Plugin.LibraryExperience.Controllers;
using MediaBrowser.Common.Api;
using MediaBrowser.Controller.Entities;
using MediaBrowser.Controller.Entities.Movies;
using MediaBrowser.Controller.Entities.TV;
using MediaBrowser.Controller.Library;
using MediaBrowser.Controller.Providers;
using MediaBrowser.Model.Entities;
using MediaBrowser.Model.IO;
using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc;
using Moq;
using Xunit;

namespace Jellyfin.Plugin.LibraryExperience.Tests;

public sealed class LibraryTitleDiscoveryControllerTests : IDisposable
{
    private readonly string _root = Path.Combine(Path.GetTempPath(), "title-discovery-" + Guid.NewGuid().ToString("N"));
    private readonly Mock<ILibraryManager> _manager = new(MockBehavior.Strict);
    private readonly Mock<IProviderManager> _providers = new(MockBehavior.Strict);
    private readonly Mock<IFileSystem> _files = new(MockBehavior.Strict);
    private readonly CollectionFolder _library;
    private readonly Folder _parent;
    private readonly Series _title;
    private BaseItem? _stored;

    public LibraryTitleDiscoveryControllerTests()
    {
        Directory.CreateDirectory(_root);
        Directory.CreateDirectory(Path.Combine(_root, "Fixture title"));
        _parent = new Folder { Id = Guid.NewGuid(), Path = _root };
        _library = new CollectionFolder { Id = Guid.NewGuid(), CollectionType = CollectionType.tvshows,
            PhysicalLocationsList = [_root], PhysicalFolderIds = [_parent.Id] };
        _title = new Series { Id = Guid.NewGuid(), Path = Path.Combine(_root, "Fixture title") };
        _manager.SetupGet(m => m.IsScanRunning).Returns(false);
        _manager.Setup(m => m.GetItemById(_library.Id)).Returns(_library);
        _manager.Setup(m => m.GetItemById(_title.Id)).Returns(() => _stored);
        _manager.Setup(m => m.FindByPath(_root, true)).Returns(_parent);
        _manager.Setup(m => m.FindByPath(_title.Path, null)).Returns(() => _stored);
        _files.Setup(f => f.GetDirectoryInfo(_title.Path)).Returns(new FileSystemMetadata
        { FullName = _title.Path, Name = "Fixture title", Exists = true, IsDirectory = true });
        _manager.Setup(m => m.ResolvePath(It.IsAny<FileSystemMetadata>(), _parent,
            It.IsAny<IDirectoryService>(), CollectionType.tvshows)).Returns(_title);
        _manager.Setup(m => m.CreateItems(It.IsAny<IReadOnlyList<BaseItem>>(), _parent, It.IsAny<CancellationToken>()))
            .Callback<IReadOnlyList<BaseItem>, BaseItem?, CancellationToken>((items, parent, token) => _stored = Assert.Single(items));
        _providers.Setup(p => p.QueueRefresh(_title.Id, It.IsAny<MetadataRefreshOptions>(), RefreshPriority.High));
        _providers.Setup(p => p.GetRefreshQueue()).Returns([]);
        _providers.Setup(p => p.GetRefreshProgress(_parent.Id)).Returns((double?)null);
        _providers.Setup(p => p.GetRefreshProgress(_library.Id)).Returns((double?)null);
    }

    private LibraryTitleDiscoveryController Controller() => new(_manager.Object, _providers.Object, _files.Object);
    private LibraryTitleDiscoveryController.DiscoveryRequest Request() => new()
    {
        LibraryId = _library.Id, ExpectedParentPath = _root, DirectoryName = "Fixture title", Kind = "Series",
        ProviderIds = new() { ["Tmdb"] = "12345", ["Tvdb"] = "67890" }
    };

    [Fact]
    public async Task CreatesOneNativeTitleWithProviderIdsBeforeQueuingOnlyItsRefresh()
    {
        _manager.Setup(m => m.CreateItems(It.IsAny<IReadOnlyList<BaseItem>>(), _parent, It.IsAny<CancellationToken>()))
            .Callback<IReadOnlyList<BaseItem>, BaseItem?, CancellationToken>((items, parent, token) =>
            {
                var item = Assert.Single(items);
                Assert.Equal(_title.Id, item.Id);
                Assert.Equal(_parent.Id, item.ParentId);
                Assert.Equal("12345", item.GetProviderId("Tmdb"));
                _stored = item;
            });
        var response = await Controller().DiscoverTitle(Request(), CancellationToken.None);
        var accepted = Assert.IsType<AcceptedResult>(response.Result);
        var result = Assert.IsType<LibraryTitleDiscoveryController.DiscoveryResult>(accepted.Value);
        Assert.Equal(_title.Id, result.ItemId);
        Assert.True(result.Created);
        Assert.True(result.Queued);
        _providers.Verify(p => p.QueueRefresh(_title.Id,
            It.Is<MetadataRefreshOptions>(o => !o.ReplaceAllMetadata && !o.ReplaceAllImages && o.IsAutomated),
            RefreshPriority.High), Times.Once);
        // Strict mocks have no root refresh or library validation expectations.
        _manager.Verify(m => m.CreateItems(It.Is<IReadOnlyList<BaseItem>>(items => items.Count == 1),
            _parent, It.IsAny<CancellationToken>()), Times.Once);
    }

    [Fact]
    public async Task RetryAcrossControllerInstancesNeverCreatesDuplicateOrOverwritesProviderIds()
    {
        await Controller().DiscoverTitle(Request(), CancellationToken.None);
        var response = await Controller().DiscoverTitle(Request(), CancellationToken.None);
        var result = Assert.IsType<LibraryTitleDiscoveryController.DiscoveryResult>(Assert.IsType<AcceptedResult>(response.Result).Value);
        Assert.False(result.Created);
        _manager.Verify(m => m.CreateItems(It.IsAny<IReadOnlyList<BaseItem>>(), _parent, It.IsAny<CancellationToken>()), Times.Once);
        var conflict = Request();
        conflict.ProviderIds!["Tmdb"] = "99999";
        Assert.IsType<ConflictObjectResult>((await Controller().DiscoverTitle(conflict, CancellationToken.None)).Result);
        Assert.Equal("12345", _stored!.GetProviderId("Tmdb"));
    }

    [Fact]
    public async Task MovieUsesNativeFileIdInsideTheRequestedDirectoryAndIsIdempotent()
    {
        var moviePath = Path.Combine(_title.Path, "Fixture.mkv");
        File.WriteAllBytes(moviePath, [0]);
        var movie = new Movie { Id = Guid.NewGuid(), Path = moviePath };
        _library.CollectionType = CollectionType.movies;
        _manager.Setup(m => m.ResolvePath(It.IsAny<FileSystemMetadata>(), _parent,
            It.IsAny<IDirectoryService>(), CollectionType.movies)).Returns(movie);
        _manager.Setup(m => m.GetItemById(movie.Id)).Returns(() => _stored);
        _manager.Setup(m => m.FindByPath(moviePath, null)).Returns(() => _stored);
        _providers.Setup(p => p.QueueRefresh(movie.Id, It.IsAny<MetadataRefreshOptions>(), RefreshPriority.High));
        var request = Request(); request.Kind = "Movie";
        var first = await Controller().DiscoverTitle(request, CancellationToken.None);
        Assert.True(Assert.IsType<LibraryTitleDiscoveryController.DiscoveryResult>(Assert.IsType<AcceptedResult>(first.Result).Value).Created);
        var second = await Controller().DiscoverTitle(request, CancellationToken.None);
        Assert.False(Assert.IsType<LibraryTitleDiscoveryController.DiscoveryResult>(Assert.IsType<AcceptedResult>(second.Result).Value).Created);
        Assert.Equal(moviePath, _stored!.Path);
        Assert.Equal("12345", _stored.GetProviderId("Tmdb"));
        _manager.Verify(m => m.CreateItems(It.IsAny<IReadOnlyList<BaseItem>>(), _parent, It.IsAny<CancellationToken>()), Times.Once);
    }

    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public async Task MovieRejectsStrmAndSymlinkFiles(bool symlink)
    {
        var moviePath = Path.Combine(_title.Path, symlink ? "Fixture.mkv" : "Fixture.strm");
        if (symlink)
        {
            var outsidePath = Path.Combine(_root, "Outside.mkv");
            File.WriteAllBytes(outsidePath, [0]);
            File.CreateSymbolicLink(moviePath, outsidePath);
        }
        else File.WriteAllBytes(moviePath, [0]);
        var movie = new Movie { Id = Guid.NewGuid(), Path = moviePath };
        _library.CollectionType = CollectionType.movies;
        _manager.Setup(m => m.ResolvePath(It.IsAny<FileSystemMetadata>(), _parent,
            It.IsAny<IDirectoryService>(), CollectionType.movies)).Returns(movie);
        var request = Request(); request.Kind = "Movie";
        Assert.IsType<ConflictObjectResult>((await Controller().DiscoverTitle(request, CancellationToken.None)).Result);
        _manager.Verify(m => m.CreateItems(It.IsAny<IReadOnlyList<BaseItem>>(), It.IsAny<BaseItem>(), It.IsAny<CancellationToken>()), Times.Never);
        _providers.Verify(p => p.QueueRefresh(It.IsAny<Guid>(), It.IsAny<MetadataRefreshOptions>(), It.IsAny<RefreshPriority>()), Times.Never);
    }

    [Fact]
    public async Task GlobalScanDefersBeforeFilesystemResolution()
    {
        _manager.SetupGet(m => m.IsScanRunning).Returns(true);
        Assert.IsType<ConflictObjectResult>((await Controller().DiscoverTitle(Request(), CancellationToken.None)).Result);
        _manager.Verify(m => m.ResolvePath(It.IsAny<FileSystemMetadata>(), It.IsAny<Folder>(),
            It.IsAny<IDirectoryService>(), It.IsAny<CollectionType?>()), Times.Never);
    }

    [Fact]
    public async Task NativeRootRefreshDefersEvenWhenGlobalScanFlagIsFalse()
    {
        _providers.Setup(p => p.GetRefreshProgress(_parent.Id)).Returns(50);
        Assert.IsType<ConflictObjectResult>((await Controller().DiscoverTitle(Request(), CancellationToken.None)).Result);
        _providers.Verify(p => p.QueueRefresh(It.IsAny<Guid>(), It.IsAny<MetadataRefreshOptions>(), It.IsAny<RefreshPriority>()), Times.Never);
    }

    [Theory]
    [InlineData("../other")]
    [InlineData("/absolute")]
    [InlineData("nested/title")]
    [InlineData("nested\\title")]
    [InlineData(".")]
    [InlineData("..")]
    public async Task RejectsArbitraryDirectories(string name)
    {
        var request = Request(); request.DirectoryName = name;
        Assert.IsType<BadRequestObjectResult>((await Controller().DiscoverTitle(request, CancellationToken.None)).Result);
    }

    [Theory]
    [InlineData("https://provider.invalid/123")]
    [InlineData("123\n")]
    [InlineData("0")]
    public async Task RejectsInvalidProviderIdentity(string id)
    {
        var request = Request(); request.ProviderIds!["Tmdb"] = id;
        Assert.IsType<BadRequestObjectResult>((await Controller().DiscoverTitle(request, CancellationToken.None)).Result);
    }

    [Fact]
    public async Task RejectsWrongLibraryRootMembershipAndWrongResolverType()
    {
        _library.PhysicalLocationsList = [Path.Combine(_root, "different")];
        Assert.IsType<ConflictObjectResult>((await Controller().DiscoverTitle(Request(), CancellationToken.None)).Result);
        _library.PhysicalLocationsList = [_root];
        _manager.Setup(m => m.ResolvePath(It.IsAny<FileSystemMetadata>(), _parent,
            It.IsAny<IDirectoryService>(), CollectionType.tvshows)).Returns(new Folder { Id = Guid.NewGuid(), Path = _title.Path });
        Assert.IsType<ConflictObjectResult>((await Controller().DiscoverTitle(Request(), CancellationToken.None)).Result);
        _manager.Verify(m => m.CreateItems(It.IsAny<IReadOnlyList<BaseItem>>(), It.IsAny<BaseItem>(), It.IsAny<CancellationToken>()), Times.Never);
    }

    [Fact]
    public async Task RejectsPhysicalParentIdMismatchEvenWhenPathMatches()
    {
        _library.PhysicalFolderIds = [Guid.NewGuid()];
        Assert.IsType<ConflictObjectResult>((await Controller().DiscoverTitle(Request(), CancellationToken.None)).Result);
        _manager.Verify(m => m.CreateItems(It.IsAny<IReadOnlyList<BaseItem>>(), It.IsAny<BaseItem>(), It.IsAny<CancellationToken>()), Times.Never);
    }

    [Fact]
    public async Task RejectsSymlinkDirectory()
    {
        Directory.CreateSymbolicLink(Path.Combine(_root, "Linked title"), _title.Path);
        var request = Request(); request.DirectoryName = "Linked title";
        Assert.IsType<ConflictObjectResult>((await Controller().DiscoverTitle(request, CancellationToken.None)).Result);
    }

    [Fact]
    public async Task ConcurrentDiscoveryReturnsConflictRatherThanCreatingDuplicate()
    {
        using var entered = new ManualResetEventSlim();
        using var release = new ManualResetEventSlim();
        _manager.Setup(m => m.ResolvePath(It.IsAny<FileSystemMetadata>(), _parent,
            It.IsAny<IDirectoryService>(), CollectionType.tvshows)).Returns(() =>
            {
                entered.Set();
                Assert.True(release.Wait(TimeSpan.FromSeconds(10), TestContext.Current.CancellationToken));
                return _title;
            });
        var first = Task.Run(() => Controller().DiscoverTitle(Request(), CancellationToken.None), TestContext.Current.CancellationToken);
        Assert.True(entered.Wait(TimeSpan.FromSeconds(10), TestContext.Current.CancellationToken));
        try { Assert.IsType<ConflictObjectResult>((await Controller().DiscoverTitle(Request(), CancellationToken.None)).Result); }
        finally { release.Set(); }
        Assert.IsType<AcceptedResult>((await first).Result);
        _manager.Verify(m => m.CreateItems(It.IsAny<IReadOnlyList<BaseItem>>(), _parent, It.IsAny<CancellationToken>()), Times.Once);
    }

    [Fact]
    public void RequiresNativeElevationPolicyAndExactReviewedAbi()
    {
        var type = typeof(LibraryTitleDiscoveryController);
        Assert.Equal(Policies.RequiresElevation, Assert.Single(type.GetCustomAttributes<AuthorizeAttribute>()).Policy);
        Assert.Equal("Habibi/LibraryExperience", Assert.Single(type.GetCustomAttributes<RouteAttribute>()).Template);
        var guard = type.GetMethod("IsSupportedServer", BindingFlags.NonPublic | BindingFlags.Static)!;
        Assert.Equal(true, guard.Invoke(null, [new Version(12, 1, 0, 0)]));
        Assert.Equal(false, guard.Invoke(null, [new Version(12, 2, 0, 0)]));
    }

    public void Dispose() => Directory.Delete(_root, true);
}
