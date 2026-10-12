"""Exact-source Dispatcharr 0.31 native XC HEAD compatibility build."""
import argparse
import ast
import hashlib
from pathlib import Path

SOURCE_SHA256 = "915398069f95d0bfa6ac11e4125a9b3cb4485cbbc34e101cf1e955af0e0efec5"


def transform(source):
    if hashlib.sha256(source).hexdigest() != SOURCE_SHA256:
        raise ValueError("Unreviewed VOD source; rebase required")
    return rewrite(source.decode()).encode()


def rewrite(text):
    old = "from django.http import JsonResponse, Http404, HttpResponse, HttpResponseRedirect"
    assert text.count(old + "\n") == 1
    text = text.replace(old + "\n", old + ", StreamingHttpResponse\n", 1)
    for name, kind, relation in (("stream_xc_movie", "movie", "movie_relation.movie.uuid"),
                                 ("stream_xc_episode", "episode", "episode_relation.episode.uuid")):
        decorator = '@api_view(["GET"])\n@permission_classes([AllowAny])\ndef ' + name + "("
        assert text.count(decorator) == 1
        text = text.replace(decorator, decorator.replace('["GET"]', '["GET", "HEAD"]'), 1)
        line = "    return stream_vod(request._request, '%s', %s, session_id, profile_id, user)" % (kind, relation)
        assert text.count(line) == 1
        head = '''    # Kodi's Stat must not turn into a slot-reserving GET probe.
    # Authentication, network, entitlement and active relation checks above
    # still apply. No provider request, redirect, session or slot is created.
    # StreamingHttpResponse avoids middleware inventing Content-Length: 0
    # for an unknown-size metadata response. Actual GET owns size/range data.
    if request.method == 'HEAD':
        response = StreamingHttpResponse(iter(()), content_type=(
            infer_content_type_from_url('file.' + extension) or 'application/octet-stream'))
        response['Accept-Ranges'] = 'bytes'
        return response

'''
        text = text.replace(line, head + line, 1)
    ast.parse(text)
    return text


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    data = transform(args.source.read_bytes())
    if args.output.exists(): raise SystemExit("Output exists; use a fresh build path")
    args.output.write_bytes(data)
    print("Built guarded VOD overlay SHA256=" + hashlib.sha256(data).hexdigest())
