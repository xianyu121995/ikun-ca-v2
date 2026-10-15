"""Authorized, read-only tracking-ratings-v1 projection over one Projects snapshot."""
import hashlib
import secrets
from datetime import datetime, timezone

from .db import DomainError
from .queries import canonical
from .transport import SCOPE

CONTRACT='tracking-ratings-v1'


class RatingsCatalog:
    def __init__(self,credential_context=''):
        self._boot=secrets.token_hex(32)
        self._credential=hashlib.sha256(credential_context.encode()).hexdigest()

    def lookup(self,con,query):
        sequence=con.execute('SELECT COALESCE(MAX(sequence),0) FROM project_changes WHERE tenant_id=?',(SCOPE,)).fetchone()[0]
        version=hashlib.sha256(canonical([CONTRACT,SCOPE,self._boot,self._credential,sequence]).encode()).hexdigest()
        expected=query['expected_catalog_version']
        if expected is not None and not secrets.compare_digest(expected.encode(),version.encode()):
            raise DomainError(409,'VERSION_CONFLICT','项目评分版本已变化，请重新查询')
        ids=query['project_ids'];rows={}
        if ids:
            rows={row['id']:row for row in con.execute('SELECT id,rating,version FROM projects WHERE tenant_id=? AND id IN ('+','.join('?' for _ in ids)+')',[SCOPE,*ids])}
        items=[]
        for project_id in ids:
            row=rows.get(project_id)
            if row is None:
                items.append({'project_id':project_id,'state':'missing','rating':None,'revision':None})
            else:
                if row['rating'] not in ('S','A','B','C','D','unrated') or type(row['version']) is not int or row['version']<1:
                    raise DomainError(503,'DB_UNAVAILABLE','项目评分数据暂不可用')
                items.append({'project_id':project_id,'state':'found','rating':None if row['rating']=='unrated' else row['rating'],'revision':row['version']})
        return {'contract':CONTRACT,'catalog_version':version,
                'checked_at':datetime.now(timezone.utc).isoformat(timespec='milliseconds').replace('+00:00','Z'),'items':items}
