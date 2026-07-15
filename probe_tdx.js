// 临时探针：解析一个 tdx txt，确认 JSON 结构与列顺序
const fs = require('fs');

const F = 'C:/Users/fanfan/.workbuddy/projects/d-WorkBuddy/e0b70369-9b1d-4187-a9f3-62e9dcb5fced/tool-results/mcp-connector-proxy-tdx-connector_tdx_kline-1783761066925-3ec324.txt';
const txt = fs.readFileSync(F, 'utf8');

// 头部文本（前 1500 字符）
console.log('===== 头部文本(前1200字符) =====');
console.log(txt.slice(0, 1200));

// 找 JSON 起点：第一个 '{'
const jStart = txt.indexOf('{');
console.log('\n===== JSON 起点位置 =====', jStart);
let obj = null;
try { obj = JSON.parse(txt.slice(jStart)); } catch (e) { console.log('整段解析失败:', e.message); }

if (obj) {
  console.log('\n===== JSON 顶层 keys =====');
  console.log(Object.keys(obj));
  // 常见字段
  ['Code','Name','code','name','Count','count','KLine','Data','List','Rows','ItemHead','AttachInfo','Period','Right'].forEach(k=>{
    if (obj[k] !== undefined) {
      const v = obj[k];
      console.log(`-- ${k}:`, Array.isArray(v) ? `Array(${v.length})` : typeof v === 'object' ? 'object' : JSON.stringify(v));
    }
  });
  if (obj.ItemHead) console.log('\nItemHead =', JSON.stringify(obj.ItemHead));
  if (obj.AttachInfo) console.log('AttachInfo =', JSON.stringify(obj.AttachInfo).slice(0,300));

  // 找数据数组
  let dataArr = null;
  for (const k of ['Data','KLine','List','Rows','data','list']) {
    if (Array.isArray(obj[k])) { dataArr = obj[k]; console.log(`\n发现数据数组字段: ${k} (len=${dataArr.length})`); break; }
  }
  if (!dataArr && obj.KLine) {
    const kl = obj.KLine;
    if (Array.isArray(kl.Data)) { dataArr = kl.Data; console.log('\n发现 obj.KLine.Data (len='+dataArr.length+')'); }
  }
  if (dataArr && dataArr.length) {
    console.log('\n首行 =', JSON.stringify(dataArr[0]));
    console.log('末行 =', JSON.stringify(dataArr[dataArr.length-1]));
    // 验证 OHLC 合理性：high>=max(open,close)>=min(open,close)>=low
    let bad=0;
    for (let i=0;i<Math.min(50,dataArr.length);i++){
      const r = dataArr[i];
      const open=r[2], high=r[3], low=r[4], close=r[5];
      if (!(high>=Math.max(open,close) && Math.min(open,close)>=low)) bad++;
    }
    console.log('前50行 OHLC 一致性(bad=',bad,') — 若0说明 索引[2]=开,[3]=高,[4]=低,[5]=收');
  }
}
