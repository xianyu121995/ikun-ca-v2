/** The root voice dock owns the sole Tracking EventSource; pages observe its events. */
type Listener=(event:Event)=>void;
const listeners=new Set<Listener>();
export function publishTrackingEvent(event:Event){for(const listener of listeners)listener(event);}
export function subscribeTrackingEvents(listener:Listener){listeners.add(listener);return()=>{listeners.delete(listener);};}
