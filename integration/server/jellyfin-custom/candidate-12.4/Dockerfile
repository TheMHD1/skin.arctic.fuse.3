# Build context is deliberately generated outside this repository. It contains
# freshly built 12.4 DLLs plus the separately compiled local plugin.
ARG BASE_IMAGE=jellyfin/jellyfin:12.4@sha256:fea863d0cd9ec445985d9c75fc6ed64e38a1d2766cf0c250a33d553f4fc1b771
FROM ${BASE_IMAGE}

COPY Emby.Naming.dll /usr/lib/jellyfin/bin/Emby.Naming.dll
COPY Emby.Server.Implementations.dll /usr/lib/jellyfin/bin/Emby.Server.Implementations.dll
COPY Jellyfin.Server.Implementations.dll /usr/lib/jellyfin/bin/Jellyfin.Server.Implementations.dll
COPY Jellyfin.Plugin.LibraryExperience.dll /opt/habibi-plugin/Jellyfin.Plugin.LibraryExperience.dll
COPY LibraryExperience.meta.json /opt/habibi-plugin/meta.json
COPY entrypoint-12.4.sh /usr/local/bin/habibi-jellyfin-entrypoint

RUN chmod 0755 /usr/local/bin/habibi-jellyfin-entrypoint \
 && mkdir -p /opt/habibi-plugin \
 && chown -R root:root /opt/habibi-plugin

ENV HABIBI_JF_EPISODE_VERSION_EXCLUDED_DIRECTORIES="One Pace"
LABEL org.habibi.jellyfin.server-revision="83d0d0e7f76e23e2e085c8ff67d28b772d35967d" \
      org.habibi.jellyfin.library-experience="12.4-candidate"

ENTRYPOINT ["/usr/local/bin/habibi-jellyfin-entrypoint"]
CMD []
