using Jellyfin.Plugin.LiveTvCategories.Services;
using Xunit;

namespace Jellyfin.Plugin.LiveTvCategories.Tests;

public class ChannelCollectionTests
{
    [Fact]
    public void TunerRemovalDropsStaleCollectionMembershipAndRestoreKeepsId()
    {
        var id=Guid.NewGuid();
        var collection=new[]{new CategoryRecord("collection-news","News",new[]{id})};
        var visible=new HashSet<Guid>{id};
        var removed=CategorySnapshotBuilder.Build(Array.Empty<IndexedChannel>(),DateTimeOffset.UtcNow,0,null,collection);
        Assert.Empty(removed.CreateUserView(visible).Categories);
        var restored=CategorySnapshotBuilder.Build(new[]{new IndexedChannel(id,"Provider news")},DateTimeOffset.UtcNow,0,null,collection);
        Assert.Equal(new[]{id},restored.CreateUserView(visible).GetPage("collection-news",0,50)!.Items);
        Assert.Empty(restored.CreateUserView(new HashSet<Guid>()).Categories);
    }

    [Fact]
    public void CollectionsPinnedAndRealProviderOrderOverridesGateway()
    {
        var a=Guid.NewGuid();var b=Guid.NewGuid();var absent=Guid.NewGuid();
        var channels=new[]{new IndexedChannel(a,"Tunisia"),new IndexedChannel(b,"Arabic News")};
        var collections=new[]{new CategoryRecord("collection-news","أخبار",new[]{b,b,absent})};
        var snapshot=CategorySnapshotBuilder.Build(channels,DateTimeOffset.UtcNow,0,new[]{"Arabic News","Tunisia"},collections);
        var view=snapshot.CreateUserView(new HashSet<Guid>{a,b});
        Assert.Equal(new[]{"أخبار","Arabic News","Tunisia"},view.Categories.Select(c=>c.Name));
        Assert.Equal(new[]{b},view.GetPage("collection-news",0,50)!.Items);
        var restricted=snapshot.CreateUserView(new HashSet<Guid>{a});
        Assert.Equal("Tunisia",Assert.Single(restricted.Categories).Name);
    }

    [Fact]
    public void InvalidCollectionFileRejected()
    {
        var path=Path.GetTempFileName();
        try
        {
            File.WriteAllText(path,"{\"provider_order\":[],\"groups\":[{\"id\":\"../bad\",\"name\":\"x\",\"channels\":[]}]}");
            Assert.Throws<InvalidDataException>(()=>ChannelCollectionFile.Read(path));
        }
        finally {File.Delete(path);}
    }
}
