using MediaBrowser.Common.Plugins;
using MediaBrowser.Common.Configuration;
using MediaBrowser.Model.Plugins;
using MediaBrowser.Model.Serialization;

namespace Jellyfin.Plugin.LibraryExperience;

/// <summary>Provides scoped date maintenance, ratings and title discovery endpoints.</summary>
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
    public override string Description => "Scoped import-date repair, user-library ratings and single-title discovery.";

    /// <inheritdoc />
    public override Guid Id => Guid.Parse("872004df-ed6b-4fa5-bf31-201ca4e27019");
}
