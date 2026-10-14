CREATE INDEX projects_tenant_updated ON projects(tenant_id, deleted_at, updated_at DESC, id);
CREATE INDEX projects_tenant_dates ON projects(tenant_id, deleted_at, token_date, id);
CREATE INDEX projects_tenant_progress ON projects(tenant_id, deleted_at, progress, id);
CREATE INDEX project_audit_tenant ON audit_log(tenant_id, project_id, id);
