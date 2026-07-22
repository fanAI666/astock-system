import json, glob, os

# 读取 tdx MCP 工具返回的超大结果文件，抽取上证指数真实日K，重写为 index_sh.json
base = r'C:/Users/fanfan/.workbuddy/projects/d-WorkBuddy'
files = glob.glob(os.path.join(base, '**', 'mcp-connector-proxy-tdx-connector_tdx_kline-*.txt'), recursive=True)
files.sort(key=os.path.getmtime, reverse=True)
src = files[0]
print('reading', os.path.basename(src), os.path.getsize(src), 'bytes')

txt = open(src, encoding='utf-8').read()
i = txt.find('{'); j = txt.rfind('}')
obj = json.loads(txt[i:j+1])
rows = obj['Rows']
ai = obj.get('AttachInfo', {})
print('name:', ai.get('Name'), '| rows:', len(rows), '| 首:', rows[-1]['Data'], '末:', rows[0]['Data'])

bars = []
for r in rows:
    bars.append([
        r['Data'],                     # 0 date YYYYMMDD
        float(r['Open']),             # 1 开
        float(r['Close']),            # 2 收
        float(r['High']),             # 3 高
        float(r['Low']),              # 4 低
        float(r['Volume']),           # 5 量
    ])
bars.sort(key=lambda b: b[0])  # 升序

out = {
    'name': ai.get('Name', '上证指数'),
    'code': obj.get('Code', '000001'),
    'setcode': obj.get('Setcode', 1),
    'bars': bars,
}
with open('选股结果/index_sh.json', 'w', encoding='utf-8') as f:
    json.dump(out, f, ensure_ascii=False)

print('wrote 选股结果/index_sh.json | bars:', len(bars))
print('range:', bars[0][0], '~', bars[-1][0])
print('close range: %.2f ~ %.2f' % (min(b[2] for b in bars), max(b[2] for b in bars)))
