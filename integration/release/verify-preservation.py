#!/usr/bin/env python3
"""Verify preserved release source in a clone or Git-free source archive.

Maintainers: stage the reviewed file set, then --write to regenerate the source
inventory. This hashes files only; it never changes Kodi or server runtime state.
"""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import subprocess

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / "integration/release/source-manifest.json"
EXTRA = {
    ".gitignore", ".gitattributes", ".github/workflows/integration.yml", "addon.xml", "LICENSE.txt", "README.md", "AGENTS.md",
    "1080i/Includes_Search.xml", "shortcuts/generator/data/setup/search_path.xml",
    "1080i/Includes_Labels.xml", "1080i/Includes_Layouts.xml", "1080i/Includes_Objects.xml",
    "shortcuts/generator/data/base/search_selector.xml",
    "shortcuts/generator/data/base/search_selector_wall.xml",
    "shortcuts/generator/data/base/search_selector_venom.xml",
    "shortcuts/generator/data/base/search_selector_wall_venom.xml",
    "shortcuts/skinvariables-generator.json",
    "shortcuts/skinvariables-shortcut-searchwidgets.json",
}


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def sources():
    names = subprocess.check_output(["git", "ls-files", "-z"], cwd=ROOT).decode().split("\0")
    return sorted(n for n in names if n and (n.startswith("integration/") or n in EXTRA)
                  and n != MANIFEST.relative_to(ROOT).as_posix())


def relevant(name):
    return name.startswith("integration/") or name in EXTRA


def unstaged_sources():
    untracked = subprocess.check_output(
        ["git", "ls-files", "--others", "--exclude-standard", "-z"], cwd=ROOT).decode().split("\0")
    unstaged = subprocess.check_output(
        ["git", "diff", "--name-only", "-z"], cwd=ROOT).decode().split("\0")
    manifest_name = MANIFEST.relative_to(ROOT).as_posix()
    return sorted({name for name in untracked + unstaged
                   if name and relevant(name) and name != manifest_name})


def write():
    pending = unstaged_sources()
    if pending:
        raise SystemExit("Review and stage sources before recording them:\n" + "\n".join(pending))
    payload = {
        "schema": 1,
        "release": "2026-10-28-media-maintenance-source-candidates",
        "meaning": "Reviewed source bytes, not a runtime credential/settings backup or proof of deployment",
        "status": {
            "october28_next_episode_payload": "patched-player-now-emitted-and-hash-guarded-both-live-clients-already-match-ordinary-eof-next-accepted-stop-cancel-terminal-pending",
            "october28_artwork_publication": "ct103-source-deployed-effective-both-entrypoints-verified-existing-primary-live-no-post-pass-and-isolated12.4-real-queue-missing-primary-native-arrival-pass-live-future-import-pending",
            "october28_reviewed_artwork_reliability": "deployed-both-service-paths-native-origin-readiness-pass-real-existing-primary-three-get-zero-post-same-digest-full-run1376-total602-preserved774-unmatched-zero-errors-zero-pending-exit0-missing-primary-crash-windows-fixture-tested",
            "october28_local_restricted_receiver": "deployed-exact-three-directory-destination-fix-real-backup-exit0-new-completion-marker-source-copy-matches14-sqlite-quickchecks-pass-restricted-key-and-package-receiver-unchanged-remote-not-applicable",
            "october28_local_backup_receiver_guard": "accepted-fresh-native-backup-invocation-marker-worker-and14database-checks-full-local75-parent-no-changes-historical-manifest-preserved-remote-absence-only",
            "october28_venom_image_pressure": "deployed-metadata-only-catalogue-refresh-original-poster-absence-cause-not-proven",
            "october28_arctic3410": "paired3-full-backup-parent-schema3-exactofficial-tmdb6192-715file-payload-verified-local-isolated-generation-accepted-settings-order-fix-runtime-proved-resource-preflight-rejected-only-jellyfin-connection-timestamp-before-stop-schema2-parent-projection-source-corrected-credentials-and-raw-immediate-cas-exact-fresh-source-bound-generation-live-image-resources-and-paired-skin-ui-av-acceptance-pending",
            "october28_jellyfin124": "candidate-build-plugin-web-and-isolated-native-tests-pass-actual-guarded-production-rollout-rejected-inherited-parental-rating-migration-regression-upstream18227-exact121-image-config-restored-six-database-continuity-groups-and-native-health-pass-hold-until-fixed-or-independently-rehydrated-and-policy-canary-verified-external-recovery-retained-no-media-photo-deletion",
            "october28_enhanced1213": "candidate-priority-bounded-watcher-backend864-js5-tests-and-actual12.4-initialization-pass-production-pending",
            "october28_seerr351": "deployed-pinned-privacy-overlay-owner-twoordinary-native-route-and-existing629-request-permission-settings-continuity-and-arabic-webhook-test-pass",
            "october28_dispatcharr033": "deployed-exact-patched4156cb52-image-full-six-module-behaviors-django63-focused79-broader-pass-stopped-data-nginx-rollback-external-sha-zstd-verified-channel-provider-profile-continuity-and-native-ui-authorized-head-pass-client-provider-playback-pending",
            "local_kodi_r6": "deployed-and-accepted",
            "local_kodi_r7": "deployed-source-and-live-api-accepted",
            "remote_kodi_r6": "deployed-headless-https-and-category-api-accepted-physical-playback-pending",
            "remote_kodi_r7": "deployed-headless-home-search-ratings-and-ordering-accepted",
            "remote_kodi_rating_default": "deployed-two-file-repair-clean-startup-idempotent",
            "remote_backup_policy": "deployed-preserves-bundled-dependency-source",
            "jellyfin_nextup": "deployed-26-account-readonly-audit-passed",
            "web_search": "deployed-mobile-browser-verified",
            "web_library_home": "deployed-owned-only-favorites-recently-watched-and-top-rated-browser-verified",
            "my_media_order": "supported-preference-updated-and-verified-26-accounts",
            "imdb_ratings": "deployed-optional-fail-open-201-of-202-distinct-ids",
            "kodi_search_ratings": "deployed-device-api-30-ratings-55ms-physical-badge-visual-pending",
            "request_ready": "timer-deployed-no-real-completion-delivery-yet",
            "scoped_import_publication": "deployed-live-indexing-and-isolated-real-jellyfin-e2e-passed",
            "subtitle_publication": "deployed-live-provider-replay-and-managed-verification-passed",
            "library_discovery_plugin": "1.2-deployed-active-exact-jellyfin-12.1-guard",
            "arr_request_search": "deployed-unit-tested-no-live-dropped-search-recovery-needed",
            "seerr_request_privacy": "3.5.1-deployed-owner-and-ordinary-user-api-existing-request-and-settings-continuity-verified",
            "remote_original_p7": "deployed-layout-gated-movie-and-episode-selection-byte-reads-accepted-onsite-av-wan-pending",
            "remote_private_access": "restricted-tailnet-key-only-ssh-and-private-nfs-deployed-restart-verified",
            "coreelec_update": "local-standalone-sd-20261028-nightly-actual-new-boot-and-frozen-postboot-acceptance-passed-preserved804-operational-entries-no-extra-reboot-full-physical-av-pending",
            "remote_coreelec_update": "20261028-standalone-sd-stage-and-controlled-reboot-request-complete-currently-offline-network-return-new-boot-and-postboot-acceptance-pending-no-duplicate-reboot",
            "remote_ui_reliability": "deployed-on-screen-keyboard-search-and-rating-badges-verified-bounded-iptv-playback",
            "remote_ui_catchup": "deployed-zero59-file-drift-category-grid-and-stop-reopen-accepted-upstream503-one-stream",
            "remote_shared_repair_baseline": "remote-complete-guarded-layer-installed-local58-offline-source-installed-live-acceptance-pending",
            "shared_am9_release": "complete-parent-chain-local58-live-source-hashes-verified-remote-existing-deployment-unchanged",
            "shared_am9_ux": "complete-parent-chain-in-local58-offline-source-installed-remote-existing-live-acceptance-in-ux-runbook",
            "shared_am9_performance": "complete-parent-chain-in-local58-offline-source-installed-remote-existing-ui-tests-unchanged",
            "shared_am9_venom_entry": "20261008.4-local-actual-home-entry-category-grid-and-playback-accepted-remote-existing-home-entry-accepted",
            "shared_am9_venom_lifecycle": "20261008.5-local-switching-stop-home-reopen-accepted-remote-existing-transitions-accepted",
            "shared_am9_collection_removal": "20261008.6-in-local58-offline-source-installed-paired-worker-regressions-remote-existing-live-startup-accepted",
            "shared_am9_sync_transactions": "20261008.7-local58-offline-source-installed-idempotent-live-acceptance-pending-remote62-existing-accepted-record",
            "venom_series_identity_freshness": "deployed-revision-aware-export-two-stale-series-refreshed-real-episode-to-live-accepted-remaining-catalogue-bounded-timer-in-progress",
            "proxmox_arc_budget": "8g-max-2g-min-live-and-module-config-running-initramfs-verified-no-host-reboot",
            "jellystat_query_budget": "native-own-role-database-policy-applied-cleanup-0.927s-old-workers-cleared",
            "enhanced_visible_card_tags": "native-policy-applied-home-rating-badges-preserved-whole-cache-transfer-removed",
            "enhanced_search_watcher": "bounded-coalesced-source-patch-net10-built-active-private-config-preserved",
            "shared_am9_awake": "six-settings-eight-cec-ids-match-remote-live-load-traced-physical-tv-cycle-pending",
            "local_backup_dependency_repair": "rooted-rsync-filter-and-optional-regdomain-offline-source-installed-live-backup-run-pending",
            "local_am9_filesystem_recovery": "physical-and-independent-image-filesystem-checks-passed-14-databases-checked-own-config-restored-usb-hardware-still-unreliable",
            "offline_am9_installer": "eight-regressions-passed-full-paired-planner-preserved-exact-maintenance-host-mount-uuid-serial-guard",
            "local_sd_only_conversion": "original-card-live-boot-storage-mounts-october12-payload-and-local58-verified-bounded-kodi-venom-accepted-full-physical-av-pending",
            "sd_only_conversion_helpers": "13-regressions-passed-private-exact-media-wrapper-and-off-card-backups-no-format-or-resident-migrator-remote-already-standalone-unchanged",
            "sd_boot_integrity": "six-readonly-regressions-passed-truncation-mixed-release-and-link-rejection-no-resident-updater-both-cohorts-applicable-remote-media-unchanged",
            "local_sd_powercut_repair": "october12-live-kernel-system-hashes-empty-update-card-mounts-local58-home-and-venom-accepted-full-physical-av-pending",
            "local_venom_network_access": "exact-client-xc-streams-only-persistent-policy-repaired-existing-reservation-verified-playlist-account-pvr-home-grid-two-channels-switch-stop-home-reopen-accepted",
            "arabic_keyboard": "paired-native-policy-local-built-in-arabic-added-english-preserved-runtime-and-saved-setting-verified-remote-not-deployed-onscreen-switch-pending",
            "native_vod_xc_head": "guarded-overlay-deployed-ten-real-function-regressions-authorized-invalid-password-missing-episode-head-and-unchanged-counter-appliance-range-get206-with65536-media-bytes-passed-full-native-kodi-ui-playback-pending-owner-playing-4k-library-copy",
            "native_media_mount_recovery": "server-deployed-eight-regressions-native-unit-validation-idempotent-readonly-mounts-nfs-and-actual-local-kodi-vfs-read-passed-host-reboot-and-remote-client-pending",
            "remote_network_backup": "deployed-off-device-checksum-59-sources-nine-databases-and-device-network-verified",
            "remote_wifi_canada": "october8-fresh-boot-ca-and-5ghz-verified-without-network-change",
            "remote_wifi_5ghz_policy": "installed-hashes-timer-and-missing-ap-fail-open-verified-5ghz-router-ap-absent-playback-and-boot-acceptance-pending",
            "local_wifi_5ghz_policy": "same-generic-source-available-not-deployed-own-profile-and-radio-acceptance-required",
            "remote_partial_title_search": "typed-full-and-partial-title-owned-ui-match-final-hidden-selector-message-verified",
            "remote_startup_policy": "native-unused-pvr-wait-disabled-runtime-and-persistent-readback-ui-verified-local-pvr-not-applicable",
            "live_tv_curated_collections": "october8-remote-account-37-nonempty-curated-plus302-provider-groups-present",
            "live_tv_collection_promotion": "october2-failure-historical-current37-groups-api-present-worker-not-rechecked",
            "provider_403_retry": "deployed-fixture-tested-not-live-recovery-proven",
            "dovi_companion_provenance": "known-gap-not-fixed",
        },
        "upstream": {
            "jellyfin-kodi": "a1aeda1352eb49c16d8da877121ea2068a7a7508",
            "jellyfin-server": "ee91c75e777da41a9c4f4855e70adc604fbf2ef8",
            "jellyfin-web": "fae41f33eb7cd636a9ef68984adb82bb247a6e1b",
        },
        "files": {n: digest(ROOT / n) for n in sources()},
    }
    MANIFEST.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    print(f"Recorded {len(payload['files'])} source hashes; stage the manifest with this reviewed release.")


def verify():
    # Git-free source archives remain supported; in a clone also enforce exact
    # tracked inventory completeness and reject overlooked untracked sources.
    payload = json.loads(MANIFEST.read_text())
    if payload.get("schema") != 1 or not payload.get("files"):
        raise SystemExit("Invalid or empty source inventory")
    errors = []
    if (ROOT / ".git").exists():
        tracked = set(sources())
        listed = set(payload["files"])
        errors.extend(f"Unlisted tracked source: {name}" for name in sorted(tracked - listed))
        errors.extend(f"No longer tracked source: {name}" for name in sorted(listed - tracked))
        errors.extend(f"Unstaged source: {name}" for name in unstaged_sources())
    for name, expected in payload["files"].items():
        relative = PurePosixPath(name)
        if relative.is_absolute() or ".." in relative.parts:
            errors.append(f"Unsafe inventory path: {name}")
            continue
        path = ROOT / name
        if not path.is_file() or path.is_symlink():
            errors.append(f"Missing/non-regular source: {name}")
        elif digest(path) != expected:
            errors.append(f"Changed source: {name}")
    if errors:
        raise SystemExit("\n".join(errors))
    print(f"PASS: {len(payload['files'])} preserved source files match {payload['release']}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true", help="regenerate from explicitly staged/tracked sources")
    args = parser.parse_args()
    write() if args.write else verify()
