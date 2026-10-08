"""Read one Kodi TCP RPC response without confusing announcements with replies."""
import codecs
import json

def read_response(sock,expected_id=1,max_bytes=8_000_000):
    text='';received=0;utf8=codecs.getincrementaldecoder('utf-8')();decoder=json.JSONDecoder()
    while True:
        chunk=sock.recv(65536)
        if not chunk:raise RuntimeError('Incomplete Kodi RPC response')
        received+=len(chunk)
        if received>max_bytes:raise RuntimeError('Kodi RPC response exceeded byte limit')
        text+=utf8.decode(chunk)
        while text.strip():
            text=text.lstrip()
            try:value,end=decoder.raw_decode(text)
            except json.JSONDecodeError:break
            text=text[end:]
            if isinstance(value,dict) and value.get('id')==expected_id and ('result' in value or 'error' in value):
                return value
            # Kodi can concatenate asynchronous Player announcements and the
            # requested response on the same TCP stream. Discard only complete
            # unrelated messages; preserve incomplete UTF-8/JSON for next recv.
