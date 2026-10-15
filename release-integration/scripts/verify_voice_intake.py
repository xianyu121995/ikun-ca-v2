#!/usr/bin/env python3
"""Exact frozen voice library increment and four explicit integration patches."""
import difflib
import json
from receive_b3 import ROOT, at, sha

SOURCE='684d4013d97118612cdfbdc77d32adfc22704af8'
CONTROL='6f6ba3c4e5ca0fcea4b98873faf340da64082eac'
BASE='f46ca183775f9824a6bfe0920f91dd9c3c0ab5fc'
WIRES={
    'apps/website/app/tracking/page.tsx':True,
    'apps/website/components/tracking-live.tsx':True,
    'apps/website/components/tracking-voice.tsx':False,
    'apps/website/lib/tracking-voice-metadata.ts':False,
}


def patch(path):
    before=at(BASE,path) if WIRES[path] else b''
    after=(ROOT/path).read_bytes()
    content=''.join(difflib.unified_diff(before.decode().splitlines(True),after.decode().splitlines(True),n=0,
                                      fromfile='a/'+path if WIRES[path] else '/dev/null',tofile='b/'+path)).encode()
    return before,after,content


def verify():
    frozen=json.loads(at(CONTROL,'docs/progress/voice-freeze.json'))
    assert frozen['source_commit']==SOURCE and frozen['accepted_frozen'] is True
    assert sha(at(SOURCE,frozen['manifest_path']))==frozen['manifest_sha256']
    for path,expected in frozen['files_sha256'].items():
        assert sha(at(SOURCE,path))==expected==sha((ROOT/path).read_bytes()),path
    assert (ROOT/frozen['manifest_path']).read_bytes()==at(SOURCE,frozen['manifest_path'])
    base=at(frozen['base_UI_commit'],'packages/ui/src/index.ts')
    assert (ROOT/'packages/ui/src/index.ts').read_bytes()==base+b'export * from "./voice/index.js";\n'
    binding=json.loads((ROOT/'release-integration/night/voice-source-binding.json').read_text())
    assert binding['source_commit']==SOURCE and binding['control_commit']==CONTROL
    assert binding['frozen_files_sha256']==frozen['files_sha256'] and set(binding['site_patches'])==set(WIRES)
    targets={}
    for path,row in binding['site_patches'].items():
        before,after,body=patch(path)
        assert row['baseline_commit']==(BASE if WIRES[path] else None)
        assert row['baseline_sha256']==sha(before) and row['target_sha256']==sha(after)
        assert (ROOT/row['patch_path']).read_bytes()==body and row['patch_sha256']==sha(body)
        targets[path]=row
    override={'packages/ui/src/index.ts':{'sha256':sha((ROOT/'packages/ui/src/index.ts').read_bytes()),'source_commit':SOURCE,'control_commit':CONTROL}}
    return override,set(frozen['allowed_paths'])|set(WIRES),targets


def bind():
    frozen=json.loads(at(CONTROL,'docs/progress/voice-freeze.json'))
    rows={}
    for index,path in enumerate(WIRES,1):
        before,after,body=patch(path)
        target='release-integration/night/patches/voice-'+str(index)+'.patch'
        (ROOT/target).write_bytes(body)
        rows[path]={'baseline_commit':BASE if WIRES[path] else None,'baseline_sha256':sha(before),
                    'target_sha256':sha(after),'patch_path':target,'patch_sha256':sha(body)}
    record={'source_commit':SOURCE,'control_commit':CONTROL,'frozen_files_sha256':frozen['files_sha256'],
            'manifest_sha256':frozen['manifest_sha256'],'site_patches':rows,'original_77_checks_remain':True,
            'immutable_source_exception':'packages/ui/src/index.ts exact single appended export only'}
    (ROOT/'release-integration/night/voice-source-binding.json').write_text(json.dumps(record,indent=2)+'\n')
    verify()
    print(json.dumps({'frozen_voice_files':16,'integration_patches':4,'index_delta':'one exact export'}))


if __name__=='__main__':bind()
