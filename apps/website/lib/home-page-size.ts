type Storage=Pick<globalThis.Storage,'getItem'|'setItem'>;
export const homeRowsKey=(height:number)=>'ikun.home.rows.v1.'+Math.round(height/100);
export function readHomeRows(storage:Storage,height:number):number{
  try{const raw=storage.getItem(homeRowsKey(height));const n=raw===null?NaN:Number(raw);if(Number.isInteger(n)&&n>=5&&n<=100)return n;}catch{}
  return 9;
}
export function saveHomeRows(storage:Storage,height:number,rows:number){try{storage.setItem(homeRowsKey(height),String(rows));}catch{}}
export function significantRowChange(previous:number,next:number){return Math.abs(previous-next)>=Math.max(2,Math.ceil(previous*.25));}
