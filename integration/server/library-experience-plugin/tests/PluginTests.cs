using MediaBrowser.Common.Configuration;
using MediaBrowser.Controller;
using MediaBrowser.Model.Serialization;
using Microsoft.Extensions.DependencyInjection;
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

    [Fact]
    public void ServiceRegistratorMakesRatingsIndexResolvable()
    {
        var paths = new Mock<IApplicationPaths>();
        paths.SetupGet(path => path.PluginConfigurationsPath).Returns("/tmp/plugin-fixture/config");
        var services = new ServiceCollection();
        services.AddSingleton(paths.Object);
        new ServiceRegistrator().RegisterServices(services, Mock.Of<IServerApplicationHost>());
        using var provider = services.BuildServiceProvider();

        Assert.IsType<RatingsIndex>(provider.GetRequiredService<RatingsIndex>());
    }
}
