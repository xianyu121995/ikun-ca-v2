'use client';
import {useEffect, useRef, useState, useSyncExternalStore} from 'react';
import {Button, createWebSpeechPort, type TrackingVoiceController} from '@ikun/ui';

/** One explicit local audition. It never creates a feed event or changes voice preferences. */
export function VoiceTest({controller}: {controller: TrackingVoiceController}) {
  const state=useSyncExternalStore(controller.subscribe,controller.getSnapshot,controller.getSnapshot);
  const [speech]=useState(()=>createWebSpeechPort());
  const [message,setMessage]=useState('点击试听可单独检查这台设备是否出声，无需等新推文。');
  const [busy,setBusy]=useState(false), [missingChinese,setMissingChinese]=useState(false);
  const generation=useRef(0), active=useRef(false), timer=useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  useEffect(()=>{
    let enabled=controller.getSnapshot().enabled;
    const stop=()=>{generation.current++;active.current=false;clearTimeout(timer.current);speech.cancel();};
    const unsubscribe=controller.subscribe(()=>{
      const next=controller.getSnapshot();
      if(next.status==='signed-out'||(enabled&&!next.enabled)) {stop();setBusy(false);setMessage('试听已停止。');}
      else if(next.queued>0&&active.current) {stop();setBusy(false);setMessage('实时播报优先，试听已停止。');}
      enabled=next.enabled;
    });
    return()=>{unsubscribe();stop();};
  },[controller,speech]);
  return <div className="ik-theme" style={{marginTop:12,borderTop:'1px solid #29424f',paddingTop:10}}>
    <Button size="sm" disabled={busy||state.queued>0||state.available!=='available'||state.status==='signed-out'} onClick={event=>{
      if(!speech.isUserGesture(event.nativeEvent)) return;
      const current=controller.getSnapshot();
      if(current.queued>0||current.status==='signed-out'||speech.availability()!=='available') return;
      const ticket=++generation.current;active.current=true;
      const finish=(text:string)=>{if(generation.current!==ticket)return;generation.current++;active.current=false;clearTimeout(timer.current);setBusy(false);setMessage(text);};
      setMissingChinese(!window.speechSynthesis.getVoices().some(v=>v.localService&&/^zh[-_]/i.test(v.lang)));
      setBusy(true);setMessage('正在请求浏览器播放试听…');
      timer.current=setTimeout(()=>{finish('浏览器未完成试听，请检查站点静音、Windows 音量和输出设备。');speech.cancel();},15_000);
      speech.speak('这是 ikun 语音测试。Voice test, one two three.',{
        start:()=>{if(generation.current===ticket)setMessage('浏览器正在播放试听。');},
        end:()=>finish('浏览器已完成试听；如果没有听见，请检查站点静音、Windows 音量和输出设备。'),
        error:()=>finish('浏览器播放试听失败，请检查声音设置和本机音色。'),
      });
    }}>{busy?'试听中…':'试听语音'}</Button>
    <p role="status" className="ik-hint">{message}</p>
    {missingChinese&&<p className="ik-hint">未发现本机中文音色；若只听见英文，需先安装中文语音。</p>}
  </div>;
}
