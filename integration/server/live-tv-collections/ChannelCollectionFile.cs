using System.Text.Json;

namespace Jellyfin.Plugin.LiveTvCategories.Services;

internal static class ChannelCollectionFile
{
    public static (IReadOnlyList<string> Order, IReadOnlyList<CategoryRecord> Collections) Read(string path)
    {
        if (!File.Exists(path)) return (Array.Empty<string>(), Array.Empty<CategoryRecord>());
        if (new FileInfo(path).Length > 4 * 1024 * 1024) throw new InvalidDataException("Collection file exceeds limit");
        using var document = JsonDocument.Parse(File.ReadAllText(path));
        var root=document.RootElement;
        var order=root.GetProperty("provider_order").EnumerateArray().Select(x=>x.GetString()!).ToArray();
        if (order.Length>2000) throw new InvalidDataException("Too many groups");
        var collections=new List<CategoryRecord>();
        foreach (var group in root.GetProperty("groups").EnumerateArray())
        {
            var id=group.GetProperty("id").GetString() ?? throw new InvalidDataException("Missing ID");
            if (id.Length>80 || id.Any(c=>!char.IsAsciiLetterOrDigit(c) && c!='-')) throw new InvalidDataException("Invalid collection ID");
            var name=group.GetProperty("name").GetString() ?? throw new InvalidDataException("Missing name");
            var ids=group.GetProperty("channels").EnumerateArray().Select(c=>Guid.Parse(c.GetProperty("id").GetString()!)).ToArray();
            if (ids.Length>1000 || name.Length>256) throw new InvalidDataException("Collection exceeds limit");
            collections.Add(new CategoryRecord("collection-"+id,name,ids));
        }
        if (collections.Count>100 || collections.Select(c=>c.Id).Distinct().Count()!=collections.Count) throw new InvalidDataException("Invalid collection count or duplicate ID");
        return (order,collections);
    }
}
