"""Think HERMES — source-linked analytics built from the same DB as answers.

No caller SQL, no LLM-fabricated chart numbers, no state updates. Every
figure is from a stored event, modeled graph route or SKU commitment.
"""
from __future__ import annotations

from collections import defaultdict

from dependency.assistant.expeditor import answer_expeditor
from dependency.graph.app_views import event_context
from dependency.graph.event_impact import trace_business_event_impact
from dependency.graph.dependency_view import product_dependency_graph


def grounded_think(*, question: str, event_id: str | None = None,
                   sku: str | None = None, facility_id: str | None = None,
                   object_id: str | None = None) -> dict:
    original = answer_expeditor(
        question=question,event_id=event_id,sku=sku,
        facility_id=facility_id,object_id=object_id,
    )
    charts, evidence, metrics = [], [], []
    selected_sku = original.get("sku") or sku

    if event_id:
        event = event_context(event_id=event_id)
        tasks = event.get("evidence_tasks") or []
        e = event.get("event") or {}
        evidence.append({
            "kind":"SOURCE_EVENT", "id":event_id,
            "label":e.get("title"),"source":e.get("source"),
            "occurred_at":e.get("occurred_at"),
            "url":e.get("source_url"),
            "provenance":e.get("provenance_class"),
            "missing_evidence_count":len(tasks),
        })
        metrics.append({"name":"Open confirmation tasks","value":len(tasks),
                        "unit":"tasks","provenance":"INFERRED"})
        impact = trace_business_event_impact(event_id=event_id,radius_km=150)
        t = impact.get("totals") or {}
        for name,key,unit in [
            ("Connected products","products_impacted","SKUs"),
            ("Potential committed units","commitment_units","units"),
            ("Connected modeled revenue","revenue_eur","EUR")
        ]:
            metrics.append({
                "name":name, "value":float(t.get(key) or 0), "unit":unit,
                "provenance":"SIMULATED_PRIVATE",
                "meaning":"POTENTIAL_EXPOSURE_NOT_CONFIRMED_LOSS",
            })
        products = sorted(
            (impact.get("products") or []),
            key=lambda r: (-float(r.get("commitment_units") or 0),r.get("sku") or "")
        )[:12]
        if products:
            charts.append({
                "id":"event_products","kind":"bar",
                "title":"Potentially connected commitments by SKU",
                "unit":"units",
                "provenance":"SIMULATED_PRIVATE",
                "limitation":"Model-connected demand, NOT confirmed lost production.",
                "data":[{"label":p["sku"],
                         "value":float(p.get("commitment_units") or 0),
                         "entity_id":"product:"+p["sku"]} for p in products],
            })
        if not selected_sku and len(products)==1:
            selected_sku=products[0].get("sku")
        evidence.extend([
            {"kind":"EVIDENCE_TASK", "id":task["task_id"],
             "label":task.get("required_fact"),"target_id":task.get("target_id"),
             "provenance":"INFERRED"}
            for task in tasks[:15]
        ])

    if selected_sku:
        graph=product_dependency_graph(sku=selected_sku)
        summary=graph.get("summary") or {}
        metrics.extend([
            {"name":"BOM materials", "value":summary.get("material_count",0),
             "unit":"materials","provenance":"SIMULATED_PRIVATE"},
            {"name":"Qualified allocations", "value":len(graph.get("allocation_routes") or []),
             "unit":"routes","provenance":"SIMULATED_PRIVATE"},
            {"name":"Connected customer commitments",
             "value":summary.get("commitment_count",0),
             "unit":"orders","provenance":"SIMULATED_PRIVATE"},
        ])
        orders = [n for n in graph.get("nodes",[])
                  if n.get("node_type")=="CUSTOMER_COMMITMENT"]
        demand = defaultdict(float)
        for order in orders:
            demand[str(order.get("market") or "Unknown market")]+=float(order.get("qty") or 0)
        if demand:
            charts.append({
                "id":"orders_by_market","kind":"bar","title":"SKU commitments by market",
                "unit":"units","provenance":"SIMULATED_PRIVATE",
                "limitation":"Orders are linked to the SKU, not allocated to a named supplier.",
                "data":[{"label":key,"value":round(value,2)} for key,value in
                        sorted(demand.items(),key=lambda t:(-t[1],t[0]))[:12]],
            })
        routes=graph.get("allocation_routes") or []
        if routes:
            charts.append({
                "id":"source_material_routes","kind":"routes",
                "title":"Approved modeled material supply paths",
                "provenance":"SIMULATED_PRIVATE",
                "limitation":"No confirmed supplier inventory or order shipment assignment.",
                "data":[{
                    "source":r["source_facility_name"],
                    "material":r["material_name"],
                    "destination":r["destination_facility_name"],
                    "allocation_share_pct":round(100*float(r.get("allocation_share") or 0),1),
                    "material_id":r["material_id"],
                    "source_facility_id":r["source_facility_id"],
                    "destination_facility_id":r["destination_facility_id"],
                } for r in routes[:24]],
            })
        evidence.extend([
            {"kind":"MODELED_ORDER","id":order["commitment_id"],
             "label":order.get("label"),"qty":order.get("qty"),
             "due_date":order.get("due_date"),
             "provenance":"SIMULATED_PRIVATE"}
            for order in orders[:15]
        ])

    return {
        **original,"experience":"GROUNDED_ANALYTICS",
        "visualizations": charts, "metrics":metrics, "evidence":evidence,
        "visualization_count":len(charts),
        "truth_contract":(
            "Charts use only selected event and SKU data in PostgreSQL. "
            "Connected monetary value is not proven loss; SKU commitments "
            "are not supplier-assigned shipments. Missing facts stay unknown."
        ),
    }
