'use strict';

// Response DTOs only: never change the TypeORM entities used by subscribers.
function ownRequest(request, viewerId) {
  return request && Number(request.requestedBy?.id) === viewerId;
}

function isRequest(value) {
  return value && typeof value === 'object' &&
    (value.type === 'tv' || value.type === 'movie') &&
    Object.prototype.hasOwnProperty.call(value, 'requestedBy') &&
    Object.prototype.hasOwnProperty.call(value, 'is4k') &&
    Object.prototype.hasOwnProperty.call(value, 'media');
}

function filterRequests(value, viewerId) {
  if (value === null || typeof value !== 'object') return value;
  if (Array.isArray(value)) {
    return value.filter(item => !isRequest(item) || ownRequest(item, viewerId))
      .map(item => filterRequests(item, viewerId));
  }
  if (isRequest(value) && !ownRequest(value, viewerId)) return null;
  const result = {};
  for (const [key, item] of Object.entries(value)) {
    // The public user directory/profile exposes User.requestCount. Keep the
    // profile public but omit another person's request activity count.
    if (key === 'requestCount' && Number(value.id) !== viewerId) continue;
    // Media relations have a stable name even when request fields are reduced.
    result[key] = key === 'requests' && Array.isArray(item)
      ? item.filter(request => ownRequest(request, viewerId))
        .map(request => filterRequests(request, viewerId))
      : filterRequests(item, viewerId);
  }
  return result;
}

function requestPrivacy(Permission) {
  return function requestPrivacyMiddleware(req, res, next) {
    const user = req.user;
    if (!user || user.hasPermission(
      [Permission.MANAGE_REQUESTS, Permission.REQUEST_VIEW], { type: 'or' }
    )) return next();
    const viewerId = Number(user.id);
    if (!Number.isSafeInteger(viewerId) || viewerId <= 0) {
      return next(new Error('Request privacy requires a valid authenticated user'));
    }
    const originalJson = res.json;
    res.json = function privateJson(body) {
      // Materialize exactly the DTO that JSON serialization would expose,
      // retaining Date/toJSON semantics without copying entity prototypes.
      const serialized = JSON.stringify(body);
      const dto = serialized === undefined ? body : JSON.parse(serialized);
      return originalJson.call(this, filterRequests(dto, viewerId));
    };
    return next();
  };
}

module.exports = { requestPrivacy, filterRequests, isRequest };
