import json


def calculate():
    with open("keywords_report.json", "r", encoding="utf-8") as f:
        data1 = json.load(f)
    with open("main_page_report.json", "r", encoding="utf-8") as f:
        data2 = json.load(f)
        
    
    usability_elements = {k: v for k, v in data2.items() if k not in ["spravca", "prevadzkovatel"]}
    total_usability = len(usability_elements)
    true_usability = sum(1 for v in usability_elements.values() if v is True)
    
    keywords = data1["keywords"]
    total_keywords = len(keywords)
    sub2depth_keywords = [w for w in keywords.values() if w["depth"] is not None and w["depth"] <= 2]



    final = round((true_usability + len(sub2depth_keywords)) / (total_usability + total_keywords) * 100,2)
    return final