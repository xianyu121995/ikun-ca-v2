import { Panel,Skeleton } from '@ikun/ui';
import '@ikun/ui/styles.css';
export function AuthLoading(){return <div className="ik-theme" style={{padding:24,maxWidth:600,margin:'48px auto'}}><Panel title="正在加载"><Skeleton label="正在加载登录状态" lines={4} /></Panel></div>;}
