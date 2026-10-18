import httpx
from hunterradar import site_reader as reader

def client(monkeypatch, handler):
    original = httpx.Client
    monkeypatch.setattr(reader.httpx, 'Client', lambda **kwargs: original(transport=httpx.MockTransport(handler), **kwargs))
    monkeypatch.setattr(reader, 'public_host', lambda host: host == 'public.example')

def test_redirect_to_private_is_rejected_before_request(monkeypatch):
    calls=[]
    def handler(req):
        calls.append(str(req.url))
        return httpx.Response(302, headers={'location':'http://127.0.0.1/private'})
    client(monkeypatch,handler)
    assert reader.fetch('https://public.example',None)==(None,'')
    assert len(calls)==1

def test_decoded_size_is_capped(monkeypatch):
    client(monkeypatch,lambda req:httpx.Response(200,headers={'content-type':'text/html'},content=b'x'*(reader.MAX_BYTES+100000)))
    url,text=reader.fetch('https://public.example',None)
    assert url and len(text)==reader.MAX_BYTES

def test_total_deadline_returns_empty(monkeypatch):
    client(monkeypatch,lambda req:httpx.Response(200,headers={'content-type':'text/html'},text='hello'))
    ticks=iter([0,0,13]);monkeypatch.setattr(reader.time,'monotonic',lambda:next(ticks,13))
    assert reader.fetch('https://public.example',None)==(None,'')
