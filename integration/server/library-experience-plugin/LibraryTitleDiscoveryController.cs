using System.ComponentModel.DataAnnotations;
using System.Text.RegularExpressions;
using Jellyfin.Data.Enums;
using MediaBrowser.Common.Api;
using MediaBrowser.Controller.Entities;
using MediaBrowser.Controller.Entities.Movies;
using MediaBrowser.Controller.Entities.TV;
using MediaBrowser.Controller.Library;
using MediaBrowser.Controller.Providers;
using MediaBrowser.Model.Entities;
using MediaBrowser.Model.IO;
using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Http;
using Microsoft.AspNetCore.Mvc;

namespace Jellyfin.Plugin.LibraryExperience.Controllers;

/// <summary>Discover one imported title without validating its library root.</summary>
[ApiController]
[Authorize(Policy = Policies.RequiresElevation)]
[Route("Habibi/LibraryExperience")]
public sealed class LibraryTitleDiscoveryController(
    ILibraryManager libraryManager,
    IProviderManager providerManager,
    IFileSystem fileSystem) : ControllerBase
{
    private static readonly SemaphoreSlim DiscoveryLock = new(1, 1);
    private static readonly Version SupportedControllerVersion = new(12, 1, 0, 0);

    [HttpPost("DiscoverTitle")]
    public async Task<ActionResult<DiscoveryResult>> DiscoverTitle(
        [FromBody, Required] DiscoveryRequest request, CancellationToken cancellationToken)
    {
        if (!IsSupportedServer(typeof(ILibraryManager).Assembly.GetName().Version))
        {
            return StatusCode(StatusCodes.Status503ServiceUnavailable, "Rebuild this plugin for the installed Jellyfin version.");
        }

        if (request.LibraryId == Guid.Empty || !IsExactLocalPath(request.ExpectedParentPath)
            || !IsDirectoryName(request.DirectoryName) || request.Kind is not ("Series" or "Movie")
            || !ValidProviderIds(request.ProviderIds))
        {
            return BadRequest("An exact library root, one directory name, title kind and valid provider IDs are required.");
        }

        if (!await DiscoveryLock.WaitAsync(0, cancellationToken).ConfigureAwait(false))
        {
            return Conflict("Another title discovery is in progress; retry later.");
        }

        try
        {
            if (libraryManager.IsScanRunning)
            {
                return Conflict("A library scan is active; defer this scoped discovery.");
            }

            if (libraryManager.GetItemById(request.LibraryId) is not CollectionFolder library
                || library.IsVirtualItem
                || !library.PhysicalLocations.Contains(request.ExpectedParentPath, StringComparer.Ordinal)
                || libraryManager.FindByPath(request.ExpectedParentPath, true) is not Folder parent
                || parent is CollectionFolder or AggregateFolder
                || parent.IsVirtualItem
                || !string.Equals(parent.Path, request.ExpectedParentPath, StringComparison.Ordinal)
                || !library.PhysicalFolderIds.Contains(parent.Id)
                || library.CollectionType != (request.Kind == "Series" ? CollectionType.tvshows : CollectionType.movies))
            {
                return Conflict("The physical parent does not belong to the selected library and content type.");
            }

            var queuedRefreshes = providerManager.GetRefreshQueue();
            if (queuedRefreshes.Contains(parent.Id) || queuedRefreshes.Contains(library.Id)
                || providerManager.GetRefreshProgress(parent.Id).HasValue
                || providerManager.GetRefreshProgress(library.Id).HasValue)
            {
                return Conflict("The selected library root is being refreshed; defer this scoped discovery.");
            }

            var directory = Path.Combine(request.ExpectedParentPath, request.DirectoryName);
            if (!IsRealDirectory(request.ExpectedParentPath) || !IsRealDirectory(directory))
            {
                return Conflict("The imported directory is absent or is a symbolic link.");
            }

            // Resolve only this directory using stock resolvers. Do not enumerate or
            // validate parent.Children: that would traverse unrelated titles.
            var service = new DirectoryService(fileSystem);
            var resolved = libraryManager.ResolvePath(
                fileSystem.GetDirectoryInfo(directory), parent, service, library.CollectionType);
            if (resolved is null || resolved.Id == Guid.Empty || !MatchesTitle(resolved, request.Kind, directory))
            {
                return Conflict("The directory did not resolve to the expected local title type.");
            }

            // Stable native resolver IDs make retries and process restarts idempotent,
            // including movies whose native Path is the file inside the directory.
            var existing = libraryManager.GetItemById(resolved.Id)
                ?? libraryManager.FindByPath(resolved.Path, null);
            var created = existing is null;
            var item = existing ?? resolved;
            if (!MatchesTitle(item, request.Kind, directory)
                || item.Id != resolved.Id
                || (existing is not null && item.ParentId != parent.Id)
                || (request.ProviderIds ?? []).Any(pair =>
                    !string.IsNullOrEmpty(item.GetProviderId(pair.Key))
                    && !string.Equals(item.GetProviderId(pair.Key), pair.Value, StringComparison.Ordinal)))
            {
                return Conflict("Existing title identity, parent, path or provider IDs conflict.");
            }

            if (created)
            {
                foreach (var pair in request.ProviderIds ?? [])
                {
                    // Seed verified numeric IDs before metadata lookup; never overwrite
                    // an existing provider ID or accept a remote URL from the caller.
                    if (string.IsNullOrEmpty(item.GetProviderId(pair.Key))) item.SetProviderId(pair.Key, pair.Value);
                }

                item.SetParent(parent);
                libraryManager.CreateItems([item], parent, cancellationToken);
            }

            providerManager.QueueRefresh(item.Id, new MetadataRefreshOptions(service)
            {
                MetadataRefreshMode = MetadataRefreshMode.Default,
                ImageRefreshMode = MetadataRefreshMode.Default,
                ReplaceAllMetadata = false,
                ReplaceAllImages = false,
                IsAutomated = true
            }, RefreshPriority.High);
            return Accepted(new DiscoveryResult(item.Id, true, created));
        }
        catch (Exception error) when (error is IOException or UnauthorizedAccessException)
        {
            return Conflict("The imported directory could not be safely read; retry later.");
        }
        finally
        {
            DiscoveryLock.Release();
        }
    }

    private static bool IsDirectoryName(string? name)
        => !string.IsNullOrWhiteSpace(name) && name.Length <= 255
            && name is not ("." or "..") && name == name.Trim()
            && !name.Contains('/') && !name.Contains('\\') && !name.Contains('\0');

    private static bool IsSupportedServer(Version? version) => version == SupportedControllerVersion;

    private static bool IsExactLocalPath(string? path)
        => !string.IsNullOrWhiteSpace(path) && path.StartsWith('/') && path != "/"
            && !path.Contains('\0') && !path.Contains('\\') && Path.IsPathFullyQualified(path)
            && string.Equals(Path.GetFullPath(path), path, StringComparison.Ordinal)
            && !path.EndsWith('/');

    private static bool IsRealDirectory(string path)
        => Directory.Exists(path) && new DirectoryInfo(path).LinkTarget is null;

    private static bool MatchesTitle(BaseItem item, string kind, string directory)
    {
        if (item.IsVirtualItem || !IsExactLocalPath(item.Path)) return false;
        if (kind == "Series") return item is Series && item.Path == directory;
        if (item is not Movie || string.Equals(Path.GetExtension(item.Path), ".strm", StringComparison.OrdinalIgnoreCase)) return false;
        if (item.Path == directory) return IsRealDirectory(directory);
        return Path.GetDirectoryName(item.Path) == directory && System.IO.File.Exists(item.Path)
            && new FileInfo(item.Path).LinkTarget is null;
    }

    private static bool ValidProviderIds(Dictionary<string, string>? ids)
        => ids is null || (ids.Count <= 3 && ids.All(pair => pair.Key switch
        {
            "Tmdb" or "Tvdb" => pair.Value is not null && Regex.IsMatch(pair.Value, "\\A[1-9][0-9]{0,11}\\z", RegexOptions.CultureInvariant),
            "Imdb" => pair.Value is not null && Regex.IsMatch(pair.Value, "\\Att[0-9]{5,12}\\z", RegexOptions.CultureInvariant),
            _ => false
        }));

    public sealed class DiscoveryRequest
    {
        public Guid LibraryId { get; set; }
        public string ExpectedParentPath { get; set; } = string.Empty;
        public string DirectoryName { get; set; } = string.Empty;
        public string Kind { get; set; } = string.Empty;
        public Dictionary<string, string>? ProviderIds { get; set; }
    }

    public sealed record DiscoveryResult(Guid ItemId, bool Queued, bool Created);
}
