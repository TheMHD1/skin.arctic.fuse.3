using Jellyfin.Plugin.LiveTvCategories.Controllers;
using MediaBrowser.Common.Api;
using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc;
using Xunit;

namespace Jellyfin.Plugin.LiveTvCategories.Tests;

public class VenomCategoryMaintenanceTests
{
    [Theory]
    [InlineData("Drama")]
    [InlineData("")]
    [InlineData("Venom: bad\nname")]
    public void InvalidNamesRejectedBeforeLibraryAccess(string name)
    {
        Assert.IsType<BadRequestObjectResult>(new VenomCategoryMaintenanceController(null!).Register([name]));
    }

    [Fact]
    public void OversizedBatchRejected()
    {
        Assert.IsType<BadRequestObjectResult>(new VenomCategoryMaintenanceController(null!).Register(Enumerable.Repeat("Venom: Drama", 1001).ToArray()));
    }

    [Fact]
    public void RequiresAdministrator()
    {
        var authorization = Assert.Single(typeof(VenomCategoryMaintenanceController).GetCustomAttributes(typeof(AuthorizeAttribute), true));
        Assert.Equal(Policies.RequiresElevation, ((AuthorizeAttribute)authorization).Policy);
    }
}
