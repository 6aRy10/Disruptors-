from __future__ import annotations
import json, os
from urllib.request import Request, urlopen

def internal_risk_alert(*, risk_score:float, object_label:str, summary:str)->dict:
    return {'text':f'Risk {risk_score:.0f}/100 — {object_label}\n{summary}'}

def supplier_capacity_request(*, sku:str, current_capacity:int, facility_name:str)->dict:
    return {'text':(f'Dependency capacity confirmation: {facility_name} is the last approved independent backup for {sku}. '
                    f'Current system capacity: {current_capacity:,} units/week. Please reply with current weekly capacity and effective date.')}

def send_webhook(payload:dict, webhook_url:str|None=None)->None:
    url=webhook_url or os.getenv('SLACK_WEBHOOK_URL')
    if not url: return
    req=Request(url,data=json.dumps(payload).encode('utf-8'),headers={'Content-Type':'application/json'})
    with urlopen(req,timeout=10) as r: r.read()
