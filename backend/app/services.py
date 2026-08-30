from datetime import date


def calculate_inventory_health(inventory_rows):
    if not inventory_rows:
        return 0.0

    total = sum(row["on_hand"] for row in inventory_rows)
    total_risk = sum(max(0, row["safety_stock"] - row["on_hand"]) for row in inventory_rows)
    return round(max(0.0, 100.0 - (total_risk / max(total, 1) * 100.0)), 2)


def build_dashboard_summary(inventory_rows, shipments, suppliers):
    active_shipments = sum(1 for shipment in shipments if shipment["status"] != "delivered")
    delayed_shipments = sum(1 for shipment in shipments if shipment["delay_days"] > 0)
    stockout_risk = sum(1 for row in inventory_rows if row["on_hand"] <= row["reorder_point"])

    supplier_quality = round(
        sum(float(supplier["reliability_score"]) for supplier in suppliers) / max(len(suppliers), 1),
        2,
    )

    return {
        "inventory_health": calculate_inventory_health(inventory_rows),
        "active_shipments": active_shipments,
        "stockout_risk": stockout_risk,
        "delayed_shipments": delayed_shipments,
        "supplier_quality": supplier_quality,
        "generated_on": date.today().isoformat(),
    }
