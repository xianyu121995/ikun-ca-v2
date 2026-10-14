// Add as app/hunterradar/page.tsx in the NEW website candidate.
// /api/hunterradar/v1/* must route to the authenticated gateway, never directly to port 8766.
export default function HunterRadarPage() {
  return <iframe src="/api/hunterradar/v1/page" title="HunterRadar 猎手监控"
    style={{width:'100%',height:'calc(100vh - 100px)',minHeight:680,border:0,borderRadius:12}}
    referrerPolicy="same-origin" />;
}
