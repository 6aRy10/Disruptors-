from __future__ import annotations
import re

def parse_supplier_reply(text:str)->dict:
    cleaned=text.replace(',','')
    nums=[int(x) for x in re.findall(r'\b\d{3,6}\b',cleaned)]
    if not nums: return {'ok':False,'reason':'No capacity number found'}
    capacity=nums[0]
    date_match=re.search(r'\b(20\d{2}-\d{2}-\d{2})\b',cleaned)
    return {'ok':True,'capacity_units':capacity,'effective_until':date_match.group(1) if date_match else None,
            'requires_confirmation':True,'raw_message':text}
