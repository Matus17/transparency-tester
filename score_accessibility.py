import json
def calculate():
    with open("accessibility_report.json", "r", encoding="utf-8") as f:
        data = json.load(f)

    # 24 unikatnych wcag tagov v axe-core
    accessibility_score = round(((24 -data["wcag"]["count"]) / 24) * 100, 2)

    return accessibility_score

