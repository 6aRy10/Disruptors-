import urllib.request
req=urllib.request.Request('http://localhost:8000/demo/reset',method='POST')
print(urllib.request.urlopen(req).read().decode())
