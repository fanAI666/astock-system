import urllib.request, json, base64, re, os, sys
from urllib.parse import quote

token = None
for p in ['.github_remote']:
    if os.path.exists(p):
        s = open(p, encoding='utf-8').read().strip()
        m = re.search(r'https://([^@]+)@github\.com/([^/]+)/([^/\s\.]+)', s)
        if m:
            token = m.group(1); owner = m.group(2); repo = m.group(3)
if not token:
    print('NO_TOKEN'); sys.exit(1)
if token.startswith('x-access-token:'):
    token = token.split(':', 1)[1]
print('repo=', owner, repo)

BRANCH = 'main'

def api(method, url, data=None):
    r = urllib.request.Request(url, method=method, data=(json.dumps(data).encode() if data else None))
    r.add_header('Authorization', 'Bearer ' + token)
    r.add_header('Accept', 'application/vnd.github+json')
    if data:
        r.add_header('Content-Type', 'application/json')
    return json.loads(urllib.request.urlopen(r, timeout=60).read().decode())

files = [
    ('选股结果/buy_signal.json', '选股结果/buy_signal.json'),
    ('选股结果/chuang_signals.json', '选股结果/chuang_signals.json'),
]
for path, local in files:
    url = f'https://api.github.com/repos/{owner}/{repo}/contents/{quote(path)}'
    try:
        cur = api('GET', url + '?ref=' + BRANCH)
        sha = cur.get('sha')
    except Exception as e:
        print('GET fail', path, e); sha = None
    content = base64.b64encode(open(local, 'rb').read()).decode()
    body = {'message': f'sync {path} 2026-08-28 (api->main)', 'content': content, 'branch': BRANCH}
    if sha:
        body['sha'] = sha
    try:
        res = api('PUT', url, body)
        print('PUT ok', path, res['commit']['sha'][:7])
    except Exception as e:
        print('PUT fail', path, e)
