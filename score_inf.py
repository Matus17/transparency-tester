import json


def calculate():
    with open("keywords_report.json", "r", encoding="utf-8") as f:
        data = json.load(f)

    keywords = data["keywords"]
    total_keywords = len(keywords)
    sum = 0


    for v in keywords.values():
        priemer = v.get("priemer") or 0
        if priemer >= 5:
            sum += priemer

    final = round((sum / (total_keywords * 10)) * 100, 2)

    return final


