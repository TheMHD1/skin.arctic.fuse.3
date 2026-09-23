using MediaBrowser.Common.Configuration;
using MediaBrowser.Model.Serialization;
using Moq;
using Xunit;

namespace Jellyfin.Plugin.LibraryExperience.Tests;

public sealed class PluginTests
{
    [Fact]
    public void DashboardPluginInfoHasInitializedAssemblyAttributes()
    {
        var paths = new Mock<IApplicationPaths>();
        paths.SetupGet(path => path.PluginsPath).Returns("/tmp/plugin-fixture/plugins");
        var plugin = new Plugin(paths.Object, Mock.Of<IXmlSerializer>());
        var info = plugin.GetPluginInfo();
        Assert.Equal("Library Experience Maintenance", info.Name);
        Assert.NotNull(plugin.Version);
        Assert.False(string.IsNullOrEmpty(plugin.AssemblyFilePath));
    }
}
