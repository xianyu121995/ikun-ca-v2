'use client';
import {createContext,useContext,useEffect,useRef,type ComponentPropsWithRef,type ButtonHTMLAttributes,type ComponentType,type HTMLAttributes,type InputHTMLAttributes,type SelectHTMLAttributes,type TextareaHTMLAttributes} from 'react';

export interface HomepageDialogProps {title:string;close:()=>void;children:React.ReactNode;pending?:boolean}
// Adapters to the v2 shared UI are supplied by the website UI owner at integration.
// There is intentionally no provider fallback for the real homepage.
export interface HomepageUIComponents {
  Button:ComponentType<ButtonHTMLAttributes<HTMLButtonElement>>;
  Input:ComponentType<ComponentPropsWithRef<'input'>>;
  Select:ComponentType<SelectHTMLAttributes<HTMLSelectElement>>;
  Textarea:ComponentType<TextareaHTMLAttributes<HTMLTextAreaElement>>;
  Badge:ComponentType<HTMLAttributes<HTMLSpanElement>>;
  Dialog:ComponentType<HomepageDialogProps>;
}
const Context=createContext<HomepageUIComponents|null>(null);
export function HomepageUIProvider({components,children}:{components:HomepageUIComponents;children:React.ReactNode}){return <Context.Provider value={components}>{children}</Context.Provider>;}
function useUI(){const value=useContext(Context);if(!value)throw new Error('Homepage UI requires an explicit v2 public UI adapter.');return value;}
export function Button(props:ButtonHTMLAttributes<HTMLButtonElement>){const UI=useUI();return <UI.Button {...props}/>;}
export function Input(props:ComponentPropsWithRef<'input'>){const UI=useUI();return <UI.Input {...props}/>;}
export function Select(props:SelectHTMLAttributes<HTMLSelectElement>){const UI=useUI();return <UI.Select {...props}/>;}
export function Textarea(props:TextareaHTMLAttributes<HTMLTextAreaElement>){const UI=useUI();return <UI.Textarea {...props}/>;}
export function Badge(props:HTMLAttributes<HTMLSpanElement>){const UI=useUI();return <UI.Badge {...props}/>;}
export function Modal(props:HomepageDialogProps){const UI=useUI();return <UI.Dialog {...props}/>;}

// Preview-only native controls, authored for this new candidate. Not a shared UI package.
function PreviewDialog({title,close,children,pending=false}:HomepageDialogProps){
  const dialog=useRef<HTMLDialogElement>(null);
  const trigger=useRef(typeof document==='undefined'?null:document.activeElement as HTMLElement|null);
  useEffect(()=>{
    const element=dialog.current;
    element?.showModal();
    element?.querySelector<HTMLElement>('[data-initial-focus]')?.focus();
    return ()=>{const target=trigger.current;requestAnimationFrame(()=>{if(target?.isConnected)target.focus();});};
  },[]);
  useEffect(()=>{if(pending)dialog.current?.focus();},[pending]);
  return <dialog ref={dialog} tabIndex={-1} className="hp-dialog" aria-label={title} aria-busy={pending||undefined} onCancel={event=>{event.preventDefault();if(!pending)close();}} onKeyDown={event=>{
    if(event.key!=='Tab')return;
    const controls=Array.from(dialog.current?.querySelectorAll<HTMLElement>('button:not(:disabled),input:not(:disabled),select:not(:disabled),textarea:not(:disabled),a[href],[tabindex="0"]')||[]).filter(element=>element.offsetParent!==null);
    if(!controls.length){event.preventDefault();dialog.current?.focus();return;}
    const first=controls[0],last=controls[controls.length-1];
    if(event.shiftKey&&document.activeElement===first){event.preventDefault();last?.focus();}
    else if(!event.shiftKey&&document.activeElement===last){event.preventDefault();first?.focus();}
  }}>
    <header className="hp-dialog-heading"><div><span>HOMEPAGE UI / DEMO</span><h2>{title}</h2></div><button className="hp-close" type="button" aria-label="关闭" disabled={pending} onClick={close}>×</button></header>{children}
  </dialog>;
}
export const previewUI:HomepageUIComponents={
  Button:props=><button type="button" {...props}/>,
  Input:props=><input {...props}/>,
  Select:props=><select {...props}/>,
  Textarea:props=><textarea {...props}/>,
  Badge:props=><span {...props}/>,
  Dialog:PreviewDialog,
};
