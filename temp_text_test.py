import urllib.parse
import urllib.request

url = 'http://127.0.0.1:8001/ranking'
data = urllib.parse.urlencode({
    'resume_text': 'This is a test resume text.',
    'user_level': 'beginner',
    'top_n': '2'
}).encode('utf-8')
req = urllib.request.Request(
    url,
    data=data,
    headers={
        'Content-Type': 'application/x-www-form-urlencoded',
        'Accept': 'application/json',
    },
)
try:
    resp = urllib.request.urlopen(req, timeout=30)
    print('STATUS', resp.status)
    print(resp.read().decode('utf-8'))
except Exception as e:
    print('ERROR', type(e).__name__, e)
