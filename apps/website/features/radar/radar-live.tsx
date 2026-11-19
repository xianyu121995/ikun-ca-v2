'use client';

import {useEffect, useState} from 'react';
import {sealWatermark, seenKey, type RadarPageModel} from '../../lib/radar-view';
import {RadarBoard} from './radar-board';

export function RadarLive({userId}: {userId: string}) {
  const [model, setModel] = useState<RadarPageModel | null>(null);
  const [problem, setProblem] = useState('');
  useEffect(() => {
    let stopped = false;
    const load = () => {
      fetch('/api/v1/radar/snapshot', {credentials: 'same-origin', cache: 'no-store'})
        .then(async response => {
          if (response.status === 401 || response.status === 403) throw new Error('会话无效');
          const body = await response.json();
          if (!body?.data) throw new Error('快照无效');
          return body.data as RadarPageModel;
        })
        .then(data => {
          if (stopped) return;
          setModel(data);
          setProblem('');
          const key = seenKey(userId);
          if (!key) return;
          const next = String(Math.max(sealWatermark(window.localStorage.getItem(key), data.latestEventId), data.latestEventId));
          window.localStorage.setItem(key, next);
          window.dispatchEvent(new Event('radar-seen'));
        })
        .catch(() => { if (!stopped) setProblem('暂时读不到雷达快照。已打开的说明会保留，不会改成示例数据。'); });
    };
    load();
    const timer = window.setInterval(load, 20000);
    return () => { stopped = true; window.clearInterval(timer); };
  }, [userId]);
  return <>
    {problem && <p className="radar-banner" role="status">{problem}</p>}
    {model ? <RadarBoard model={model}/> : <p className="radar-footnote">正在读取本机雷达…</p>}
  </>;
}
