import json
import requests

#files = ['files/storageevidence.json', 'files/vmevidence.json']
files = ['/app/test_files/storageraw.json', '/app/test_files/vmraw.json']

url = 'http://127.0.0.1:8000/api/clouditor2dt/'

dts = []
for f in files:

    try:
        with open(f, 'r') as json_data:
            payload = json.loads(json_data.read())
            json_data.close()

        r = requests.post(url, data=json.dumps(payload), headers={'Content-Type': 'application/json'})
        x = json.loads(r.text)
        for i in x:
            dts.append(i)

        '''
        if r.status_code == 200:
            payload = r.json()
            print(payload)
            with open(f.replace(".json","") + '-Thing.json', 'w', encoding='utf-8') as f:
                json.dump(json.loads(payload), f, ensure_ascii=False, indent=4)
        '''
    except Exception as e:
        print(e)
print(json.dumps(dts))
with open('/app/sdt_output/things-created.json', 'w', encoding='utf-8') as f:
    json.dump(dts, f, ensure_ascii=False, indent=4)