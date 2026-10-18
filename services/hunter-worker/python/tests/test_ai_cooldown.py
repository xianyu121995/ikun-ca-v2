import json,time
import pytest,httpx
from hunterradar import gemini

def test_daily_quota_persists_and_prevents_new_network_calls(tmp_path,monkeypatch):
    path=tmp_path/'config/ai.json';path.parent.mkdir();path.write_text(json.dumps({'api_key':'SyntheticKeyForTestsOnly123','model':'test-model'}))
    monkeypatch.setenv('IKUN_AI_CONFIG',str(path))
    calls=[]
    class Client:
        def __init__(self,**kwargs):pass
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def post(self,*args,**kwargs):
            calls.append(1)
            return httpx.Response(429,json={'error':{'details':[{'retryDelay':'55000s'},{'violations':[{'quotaId':'GenerateRequestsPerDayPerProjectPerModel-FreeTier'}]}]}})
    monkeypatch.setattr(gemini.httpx,'Client',Client)
    with pytest.raises(gemini.AIUnavailable,match='ai_rate_limited'):gemini.generate_json('test')
    assert gemini.cooling() and not gemini.enabled()
    assert json.loads(gemini.cooldown_path().read_text())['until']>=time.time()+54990
    with pytest.raises(gemini.AIUnavailable):gemini.generate_json('test')
    assert len(calls)==1
    assert 'SyntheticKey' not in gemini.cooldown_path().read_text()
