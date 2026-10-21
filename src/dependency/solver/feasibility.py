def check_plan(*, required_units:int, finished_units:int, assembly_units:int,
               materials_available:bool=True, route_on_time:bool=True, approved:bool=True)->dict:
    failures=[]
    if not materials_available: failures.append({'type':'MATERIAL_TIMING'})
    if not route_on_time: failures.append({'type':'ROUTE_TIMING'})
    if not approved: failures.append({'type':'NOT_APPROVED'})
    available=max(0,finished_units)+max(0,assembly_units)
    if available<required_units: failures.append({'type':'CAPACITY','required':required_units,'available':available})
    return {'feasible':not failures,'available_units':available,'shortage_units':max(0,required_units-available),'constraint_failures':failures}
