import json, urllib.request
base='http://localhost:8000'
msg={'text':'Capacity has declined to 5,500 pairs per week until 2026-11-04.'}
req=urllib.request.Request(base+'/demo/supplier/parse-reply',data=json.dumps(msg).encode(),headers={'Content-Type':'application/json'},method='POST')
parsed=json.loads(urllib.request.urlopen(req).read().decode()); print('parsed',parsed)
confirm={'capacity_units':parsed['capacity_units'],'effective_until':parsed['effective_until']}
req=urllib.request.Request(base+'/demo/supplier/confirm',data=json.dumps(confirm).encode(),headers={'Content-Type':'application/json'},method='POST')
print(urllib.request.urlopen(req).read().decode())
