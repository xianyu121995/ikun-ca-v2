import importlib.util
from pathlib import Path
import pytest
s=importlib.util.spec_from_file_location('migration',Path(__file__).with_name('migrate_v2_launchdaemons.py'));m=importlib.util.module_from_spec(s);s.loader.exec_module(m)

def test_conversion_preserves_commands_and_scheduling():
    original={'Label':m.PREFIX+'backup','ProgramArguments':['python','unchanged.py','backup'],'EnvironmentVariables':{'ONE':'unchanged'},'StartCalendarInterval':{'Hour':4,'Minute':0},'LimitLoadToSessionType':'Aqua'}
    converted=m.normalize(original)
    assert converted['ProgramArguments']==original['ProgramArguments']
    assert converted['StartCalendarInterval']==original['StartCalendarInterval']
    assert converted['UserName']=='lvlei' and converted['GroupName']=='staff'
    assert converted['EnvironmentVariables']['ONE']=='unchanged'
    assert converted['Umask']==0o077 and 'LimitLoadToSessionType' not in converted
    assert original['LimitLoadToSessionType']=='Aqua'

def test_conversion_rejects_unowned_job():
    with pytest.raises(AssertionError):m.normalize({'Label':'unrelated.old.tunnel'})
