using MediaBrowser.Common.Api;
using MediaBrowser.Controller.Library;
using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc;

namespace Jellyfin.Plugin.LiveTvCategories.Controllers;

/// <summary>Registers bounded provider category names without the legacy slug route.</summary>
[ApiController]
[Authorize(Policy = Policies.RequiresElevation)]
[Route("VenomCategories/Maintenance")]
public sealed class VenomCategoryMaintenanceController(ILibraryManager libraryManager) : ControllerBase
{
    [HttpPost("Register")]
    public IActionResult Register([FromBody] string[] names)
    {
        if (names.Length > 1000 || names.Any(name => string.IsNullOrWhiteSpace(name)
            || !name.StartsWith("Venom: ", StringComparison.Ordinal)
            || name.Length > 512 || name.Any(char.IsControl)))
        {
            return BadRequest("Expected at most 1000 bounded Venom category names.");
        }

        var registered = 0;
        foreach (var name in names.Distinct(StringComparer.Ordinal))
        {
            libraryManager.GetGenre(name);
            registered++;
        }

        return Ok(new { Registered = registered });
    }
}
