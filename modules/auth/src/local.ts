/** Local OS-authorized account administration. Never imported by website handlers. */
import { AuthStore } from './store.js';
import { AuthError, digest, hashPassword, password, username, verifyPassword } from './security.js';

export class LocalAccounts extends AuthStore {
  private named(name: string) {
    const row=this.db.prepare('SELECT id FROM auth_users WHERE username=?').get(username(name));
    if (!row) throw new AuthError(404,'NOT_FOUND','用户不存在');
    return this.target(String(row.id));
  }
  private adminSlot(excluding?:string) {
    // Policy for B1; schema keeps a role column and supports multiple admins in a future release.
    if(this.db.prepare("SELECT 1 FROM auth_users WHERE role='superadmin' AND enabled=1 AND id<>?").get(excluding??''))
      throw new AuthError(409,'CONFLICT','当前阶段只允许一个有效超级管理员');
  }
  list() {
    return this.db.prepare('SELECT id AS user_id,username,role,enabled,must_change_password,version AS revision FROM auth_users ORDER BY created_at,id').all();
  }
  async bootstrap(name:string,value:string) {
    name=username(name);password(value);
    const hash=await hashPassword(value);
    return this.tx(()=>{
      if(this.db.prepare("SELECT 1 FROM auth_users WHERE role='superadmin'").get())
        throw new AuthError(409,'CONFLICT','初始管理员已存在，请使用 recover-admin');
      const result=this.addUser(name,hash,'superadmin',true);
      this.audit('local_bootstrap',null,result.id);return result;
    });
  }
  async create(name:string,value:string) {
    name=username(name);password(value);const hash=await hashPassword(value);
    return this.tx(()=>{
      if(!this.db.prepare("SELECT 1 FROM auth_users WHERE role='superadmin' AND enabled=1").get())
        throw new AuthError(409,'CONFLICT','请先初始化或恢复超级管理员');
      const result=this.addUser(name,hash,'user',true);this.audit('local_create',null,result.id);return result;
    });
  }
  setEnabled(name:string,enabled:boolean) {
    return this.tx(()=>{
      const row=this.named(name);
      if(row.role==='superadmin') {
        if(enabled)this.adminSlot(row.id);
        else if(row.enabled && Number(this.db.prepare("SELECT count(*) AS n FROM auth_users WHERE role='superadmin' AND enabled=1").get()?.n)<=1)
          throw new AuthError(409,'CONFLICT','不能禁用最后一个有效超级管理员');
      }
      if(Boolean(row.enabled)!==enabled) {
        this.db.prepare('UPDATE auth_users SET enabled=?,version=version+1,updated_at=? WHERE id=?').run(Number(enabled),this.now(),row.id);
        this.db.prepare('DELETE FROM auth_sessions WHERE user_id=?').run(row.id);
        this.audit(enabled?'local_enable':'local_disable',null,row.id);
      }
      const {password_hash,...safe}=this.named(name);return safe;
    });
  }
  async reset(name:string,value:string,recoverAdmin=false) {
    password(value);const before=this.named(name);
    if(recoverAdmin && before.role!=='superadmin') throw new AuthError(409,'CONFLICT','恢复命令仅适用于超级管理员');
    if(await verifyPassword(before.password_hash,value)) throw new AuthError(422,'VALIDATION_ERROR','新密码不能与当前密码相同');
    const hash=await hashPassword(value);
    return this.tx(()=>{
      const current=this.named(name);
      if(current.version!==before.version) throw new AuthError(409,'VERSION_CONFLICT','账号已变更，请重新执行命令');
      if(recoverAdmin)this.adminSlot(current.id);
      this.db.prepare('UPDATE auth_users SET password_hash=?,must_change_password=1,enabled=?,version=version+1,updated_at=? WHERE id=?')
        .run(hash,recoverAdmin?1:current.enabled,this.now(),current.id);
      this.db.prepare('DELETE FROM auth_sessions WHERE user_id=?').run(current.id);
      this.db.prepare('DELETE FROM auth_login_limits WHERE key=? OR key=?').run('account:'+digest(current.username),'account:'+digest('change:'+current.id));
      this.audit(recoverAdmin?'local_recover_admin':'local_reset_password',null,current.id);
      return {user_id:current.id,must_change_password:true};
    });
  }
}
