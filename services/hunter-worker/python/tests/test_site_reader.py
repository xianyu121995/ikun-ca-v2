import httpx
from hunterradar import site_reader as reader

def client(monkeypatch, handler):
    original = httpx.Client
    monkeypatch.setattr(reader.httpx, 'Client', lambda **kwargs: original(transport=httpx.MockTransport(handler), **kwargs))
    monkeypatch.setattr(reader, 'public_host', lambda host, proxy=None: host == 'public.example')

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

def test_fake_ip_requires_public_dns_and_rejects_private_answers(monkeypatch):
    monkeypatch.setattr(reader.socket,'getaddrinfo',lambda *a,**k:[(None,None,None,None,('198.18.0.3',443))])
    assert not reader.public_host('project.example')
    original=httpx.Client
    answer={'data':'93.184.216.34','type':1}
    monkeypatch.setattr(reader.httpx,'Client',lambda **kwargs:original(transport=httpx.MockTransport(lambda req:httpx.Response(200,json={'Answer':[answer]}))))
    assert reader.public_host('project.example','http://127.0.0.1:7897')
    answer['data']='127.0.0.1'
    assert not reader.public_host('project.example','http://127.0.0.1:7897')
