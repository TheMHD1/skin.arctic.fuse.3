# Version-locked LinuxServer operational candidate.  Build context is generated
# privately from the proven 12.4 artifacts; never substitute a floating tag.
ARG BASE_IMAGE=lscr.io/linuxserver/jellyfin@sha256:50b431edbea22045f97c5d662b4ab22a48e0aeab1e186702ec2a02bf70dd0eec
FROM ${BASE_IMAGE}

COPY Emby.Naming.dll /usr/lib/jellyfin/bin/Emby.Naming.dll
COPY Emby.Server.Implementations.dll /usr/lib/jellyfin/bin/Emby.Server.Implementations.dll
COPY Jellyfin.Server.Implementations.dll /usr/lib/jellyfin/bin/Jellyfin.Server.Implementations.dll
COPY Jellyfin.Plugin.LibraryExperience.dll /opt/habibi-plugin/Jellyfin.Plugin.LibraryExperience.dll
COPY LibraryExperience.meta.json /opt/habibi-plugin/meta.json
COPY plugins/ /opt/habibi-plugins/
COPY jellyfin-web/ /usr/share/jellyfin/web/
COPY root/ /

RUN chmod 0755 /custom-cont-init.d/60-habibi-jellyfin-candidate \
 && chown -R root:root /opt/habibi-plugin /opt/habibi-plugins /usr/share/jellyfin/web

ENV PATH="/usr/lib/jellyfin-ffmpeg:${PATH}" \
    HABIBI_JF_EPISODE_VERSION_EXCLUDED_DIRECTORIES="One Pace"
LABEL org.habibi.jellyfin.server-revision="83d0d0e7f76e23e2e085c8ff67d28b772d35967d" \
      org.habibi.jellyfin.linuxserver-base="12.4ubu2604-ls57" \
      org.habibi.jellyfin.web-revision="0a580ce8df89282dfd120b6d5efb8e106da23bd5"
