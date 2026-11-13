"""Small, documented local client for Codex and other development tools."""
import argparse,json,time,urllib.request
BASE='http://127.0.0.1:8782'
def get(path):
    with urllib.request.urlopen(BASE+'/api/'+path,timeout=10) as r:return json.load(r)
def post(path,data):
    token=get('config')['token']
    req=urllib.request.Request(BASE+'/api/'+path,json.dumps(data).encode(),headers={'Content-Type':'application/json','X-Forge-Token':token})
    with urllib.request.urlopen(req,timeout=10) as r:return json.load(r)
def wait(jid):
    for _ in range(60):
        d=get('desktop/job?id='+jid)
        if d['status']=='done':return d['result']
        if d['status']=='error':raise RuntimeError(d['error'])
        time.sleep(.2)
    raise TimeoutError('Editor non risponde: controlla finestre di dialogo o operazioni in corso')
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('action',choices=['inspect','capture','select','command']);p.add_argument('value',nargs='?');a=p.parse_args()
    if a.action=='inspect':result=get('desktop/state')
    elif a.action=='capture':result=wait(post('desktop/capture',{})['id'])
    elif a.action=='select':result=wait(post('desktop/select',{'id':a.value})['id'])
    else:result=wait(post('desktop/command',{'command':a.value})['id'])
    print(json.dumps(result,ensure_ascii=False,indent=2))
