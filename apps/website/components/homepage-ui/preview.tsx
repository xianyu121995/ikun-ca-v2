'use client';
import {useState} from 'react';
import {HomepageUIProvider,previewUI} from './ui-port';
import HomepagePrototype from './homepage-prototype';
import {demoStore} from './model/demo-store';
import './homepage.css';
export default function HomepagePreview(){
  const [readOnly,setReadOnly]=useState(false);
  return <HomepageUIProvider components={previewUI}>
    <div className="hp-preview-role"><span>独立 UI 演示 · 未连接认证或业务 API</span><label>界面权限演示<select value={readOnly?'user':'superadmin'} onChange={event=>setReadOnly(event.target.value==='user')} aria-label="界面权限演示"><option value="superadmin">演示 superadmin（可编辑）</option><option value="user">演示 user（只读）</option></select></label></div>
    <HomepagePrototype store={demoStore} readOnly={readOnly}/>
  </HomepageUIProvider>;
}
