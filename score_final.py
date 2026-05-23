import score_accessibility as a
import score_inf as i
import score_usability as u
import json

def calc():
    results = {
        "pristupnost": a.calculate(),
        "pouzitelnost": u.calculate(),
        "informativnost": i.calculate(),
        "transparentnost": None
    }

    with open("final_score.json", "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)

    weight = {
        "pristupnost": 20,
        "pouzitelnost": 30,
        "informativnost": 50
    }

    results["transparentnost"] = round(sum(results[w] * weight[w] for w in weight) / 100)
    with open("final_score.json", "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
