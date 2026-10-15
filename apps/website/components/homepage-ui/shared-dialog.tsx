'use client';
import {useCallback,useLayoutEffect,useRef,type ReactNode} from 'react';
import {Dialog} from '@ikun/ui';

// Page composition only; keyboard, modal state and focus trapping belong to @ikun/ui.
export function HomepageDialog({title,close,children,pending=false,destructive=false}:{title:string;close:()=>void;children:ReactNode;pending?:boolean;destructive?:boolean}){
  const initialFocus=useRef<HTMLElement|null>(null);
  useLayoutEffect(()=>{
    const trigger=document.activeElement as HTMLElement|null;
    // This page removes closed editors from the tree. Restore after that commit,
    // when the write trigger is enabled again; the public Dialog owns focus while open.
    return ()=>{requestAnimationFrame(()=>{if(trigger?.isConnected&&!trigger.matches(':disabled'))trigger.focus();});};
  },[]);
  const captureFocus=useCallback((node:HTMLDivElement|null)=>{initialFocus.current=node?.querySelector<HTMLElement>('[data-initial-focus]')||null;},[]);
  return <Dialog open title={title} pending={pending} destructive={destructive} initialFocusRef={initialFocus} onOpenChange={open=>{if(!open&&!pending)close();}}>
    <div ref={captureFocus} className="hp2-dialog-content">{children}</div>
  </Dialog>;
}
