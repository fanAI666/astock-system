const fs=require('fs');
const DIR='C:/Users/fanfan/.workbuddy/projects/d-WorkBuddy/e0b70369-9b1d-4187-a9f3-62e9dcb5fced/tool-results';
const files=fs.readdirSync(DIR).filter(f=>f.includes('tdx_kline')&&f.endsWith('.txt'));
const out=[];
for(const f of files){
  const st=fs.statSync(DIR+'/'+f);
  if(st.size<200000) continue; // only the 3-year pulls
  const raw=fs.readFileSync(DIR+'/'+f,'utf8');
  const js=raw.indexOf('{'); const lb=raw.lastIndexOf('}');
  let obj;
  try{ obj=JSON.parse(raw.slice(js,lb+1)); }catch(e){ out.push([f,'PARSE_ERR',e.message]); continue; }
  const rows=obj.Rows||[];
  const r0=rows[0]||{};
  out.push({
    file:f.slice(-11),
    code:obj.Code, setcode:obj.Setcode,
    n:rows.length,
    first:r0.Data, last:(rows[rows.length-1]||{}).Data,
    keys:Object.keys(r0).join(',')
  });
}
out.sort((a,b)=>String(a.code).localeCompare(String(b.code)));
for(const o of out){ console.log(JSON.stringify(o)); }
console.log('TOTAL_FILES(>=200k):',out.length);
