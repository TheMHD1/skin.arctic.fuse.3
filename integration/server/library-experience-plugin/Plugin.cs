using MediaBrowser.Common.Plugins;
using MediaBrowser.Common.Configuration;
using MediaBrowser.Model.Plugins;
using MediaBrowser.Model.Serialization;

namespace Jellyfin.Plugin.LibraryExperience;

/// <summary>Provides narrowly scoped library-date maintenance endpoints.</summary>
public sealed class Plugin : BasePlugin<BasePluginConfiguration>
{
    /// <summary>Initializes a new instance of the <see cref="Plugin"/> class.</summary>
    public Plugin(IApplicationPaths applicationPaths, IXmlSerializer xmlSerializer)
        : base(applicationPaths, xmlSerializer)
    {
    }

    /// <inheritdoc />
    public override string Name => "Library Experience Maintenance";

    /// <inheritdoc />
    public override string Description => "Guarded import-date repair without metadata or watch-history writes.";

    /// <inheritdoc />
    public override Guid Id => Guid.Parse("872004df-ed6b-4fa5-bf31-201ca4e27019");
}
