import urllib.request
import re

url = 'https://trafficguard-vishesh9910.vercel.app'
req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
res = urllib.request.urlopen(req)
html = res.read().decode('utf-8')
print('HTTP Status:', res.status)

css_matches = re.findall(r'href="(/assets/[^"]+\.css)"', html)
js_matches = re.findall(r'src="(/assets/[^"]+\.js)"', html)
print('CSS file:', css_matches)
print('JS file:', js_matches)

if css_matches:
    css_res = urllib.request.urlopen(urllib.request.Request(url + css_matches[0], headers={'User-Agent': 'Mozilla/5.0'}))
    css_content = css_res.read()
    print('CSS length:', len(css_content), 'bytes')
    print('Has Tailwind classes (grid-cols, flex, rounded-xl):', b'grid-cols' in css_content and b'rounded-xl' in css_content)

if js_matches:
    js_res = urllib.request.urlopen(urllib.request.Request(url + js_matches[0], headers={'User-Agent': 'Mozilla/5.0'}))
    js_content = js_res.read()
    print('JS length:', len(js_content), 'bytes')
    print('Has cloudEngine simulation:', b'cloudEngine' in js_content or b'Backend Alpha' in js_content)
