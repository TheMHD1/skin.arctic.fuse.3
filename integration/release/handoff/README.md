# Bounded live HTTP-403 retry profile

`profile_update.py` preserves the reviewed Dispatcharr profile-6 change without
embedding credentials. It reads the existing container-local credential file,
requires an idle relay and the exact original or rollback parameter string,
checks the installed FFmpeg options, locks the row, writes a mode-0600 backup,
updates only `parameters`, and performs a read-back. It does not change limits,
codecs, mapping, output format, selected profile, containers, or credentials.

Run from the repository root through the existing Dispatcharr Django shell:

```sh
# read-only preflight
docker exec -i -e VENOM_RETRY_CHECK=1 -w /app dispatcharr python manage.py shell \
  < integration/release/handoff/profile_update.py

# apply only after preflight and an idle check
docker exec -i -e VENOM_RETRY_APPLY=1 -w /app dispatcharr python manage.py shell \
  < integration/release/handoff/profile_update.py

# exact rollback
docker exec -i -e VENOM_RETRY_ROLLBACK=1 -w /app dispatcharr python manage.py shell \
  < integration/release/handoff/profile_update.py
```

The retry is limited to HTTP 403 with four retries, seven-second individual
delay cap and eleven-second scheduled-delay cap. Network/open time is additional,
and current FFmpeg does not propagate these options into every nested HLS fetch.
On an FFmpeg build exposing these options, the localhost integration test checks
the top-level behavior only; it does not prove provider recovery or authorize
bypassing a permanent denial. An unsupported local FFmpeg reports a test skip.
