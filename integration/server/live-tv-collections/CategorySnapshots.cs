using System;
using System.Collections.Generic;
using System.Linq;
using System.Security.Cryptography;
using System.Text;
using Jellyfin.Plugin.LiveTvCategories.Models;

namespace Jellyfin.Plugin.LiveTvCategories.Services;

internal sealed record IndexedChannel(Guid InternalId, string? GroupName);

internal sealed class CategoryRecord
{
    public CategoryRecord(string id, string name, IReadOnlyList<Guid> channelIds)
    {
        Id = id;
        Name = name;
        ChannelIds = channelIds;
    }

    public string Id { get; }

    public string Name { get; }

    public IReadOnlyList<Guid> ChannelIds { get; }
}

internal sealed class CategorySnapshot
{
    private readonly IReadOnlyList<CategoryRecord> _categories;

    public CategorySnapshot(DateTimeOffset generatedAtUtc, IReadOnlyList<CategoryRecord> categories, int unmatchedChannelCount)
    {
        GeneratedAtUtc = generatedAtUtc;
        _categories = categories;
        UnmatchedChannelCount = unmatchedChannelCount;
    }

    public DateTimeOffset GeneratedAtUtc { get; }

    public int UnmatchedChannelCount { get; }

    public int TotalChannelCount => _categories.Sum(category => category.ChannelIds.Count);

    public UserCategorySnapshot CreateUserView(IReadOnlySet<Guid> visibleChannelIds)
    {
        var visibleCategories = new List<CategoryRecord>(_categories.Count);
        foreach (var category in _categories)
        {
            var ids = category.ChannelIds.Where(visibleChannelIds.Contains).ToArray();
            if (ids.Length > 0)
            {
                visibleCategories.Add(new CategoryRecord(category.Id, category.Name, ids));
            }
        }

        return new UserCategorySnapshot(this, visibleCategories);
    }
}

public sealed class UserCategorySnapshot
{
    private readonly IReadOnlyDictionary<string, CategoryRecord> _categoriesById;

    internal UserCategorySnapshot(CategorySnapshot source, IReadOnlyList<CategoryRecord> categories)
    {
        Source = source;
        Categories = categories
            .Select(category => new LiveTvCategorySummary(category.Id, category.Name, category.ChannelIds.Count))
            .ToArray();
        _categoriesById = categories.ToDictionary(category => category.Id, StringComparer.Ordinal);
    }

    internal CategorySnapshot Source { get; }

    public IReadOnlyList<LiveTvCategorySummary> Categories { get; }

    public CategoryIdPage? GetPage(string categoryId, int startIndex, int limit)
    {
        if (!_categoriesById.TryGetValue(categoryId, out var category))
        {
            return null;
        }

        var items = category.ChannelIds.Skip(startIndex).Take(limit).ToArray();
        return new CategoryIdPage(items, startIndex, category.ChannelIds.Count);
    }
}

public sealed record CategoryIdPage(IReadOnlyList<Guid> Items, int StartIndex, int TotalRecordCount);

internal static class CategorySnapshotBuilder
{
    private const string CategoryPrefix = "category:";
    private const string UncategorisedKey = "uncategorised:";
    private const string UncategorisedName = "Uncategorised";

    public static CategorySnapshot Build(
        IEnumerable<IndexedChannel> channels,
        DateTimeOffset generatedAtUtc,
        int unmatchedChannelCount = 0,
        IReadOnlyList<string>? categoryOrder = null,
        IReadOnlyList<CategoryRecord>? collections = null)
    {
        ArgumentNullException.ThrowIfNull(channels);

        var groups = new Dictionary<string, MutableCategory>(StringComparer.Ordinal);
        var seenChannels = new HashSet<Guid>();

        foreach (var channel in channels)
        {
            if (channel.InternalId == Guid.Empty || !seenChannels.Add(channel.InternalId))
            {
                continue;
            }

            var hasGroup = !string.IsNullOrWhiteSpace(channel.GroupName);
            var name = hasGroup ? channel.GroupName! : UncategorisedName;
            var key = hasGroup ? CategoryPrefix + name : UncategorisedKey;

            if (!groups.TryGetValue(key, out var category))
            {
                category = new MutableCategory(CreateCategoryId(key, hasGroup), name);
                groups.Add(key, category);
            }

            category.ChannelIds.Add(channel.InternalId);
        }

        var ranks = (categoryOrder ?? Array.Empty<string>()).Select((name, index) => (name, index))
            .GroupBy(pair => pair.name, StringComparer.Ordinal)
            .ToDictionary(group => group.Key, group => group.First().index, StringComparer.Ordinal);
        var categories = groups.Values
            // Dictionary insertion order follows the tuner playlist. Keep the
            // provider/gateway sequence; alphabetical ordering moved temporary
            // event groups to the top and destroyed the source's navigation.
            .OrderBy(category => ranks.GetValueOrDefault(category.Name, int.MaxValue))
            .Select(category => new CategoryRecord(category.Id, category.Name, category.ChannelIds.ToArray()))
            .ToArray();

        if (collections is not null)
        {
            categories = collections.Select(collection => new CategoryRecord(collection.Id, collection.Name,
                    collection.ChannelIds.Where(seenChannels.Contains).Distinct().ToArray()))
                .Where(collection => collection.ChannelIds.Count > 0)
                .Concat(categories).ToArray();
        }

        return new CategorySnapshot(generatedAtUtc, categories, unmatchedChannelCount);
    }

    private static string CreateCategoryId(string key, bool hasGroup)
    {
        var hash = SHA256.HashData(Encoding.UTF8.GetBytes(key));
        var digest = Convert.ToBase64String(hash)
            .TrimEnd('=')
            .Replace('+', '-')
            .Replace('/', '_');
        return (hasGroup ? "category-" : "uncategorised-") + digest;
    }

    private sealed class MutableCategory
    {
        public MutableCategory(string id, string name)
        {
            Id = id;
            Name = name;
        }

        public string Id { get; }

        public string Name { get; }

        public List<Guid> ChannelIds { get; } = new();
    }
}
