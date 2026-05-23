import httpx
from urllib.parse import urlparse
import json
def check_open_data_sparql(input):
    name = input.strip().lower()
    
    query = f"""
PREFIX dcterms: <http://purl.org/dc/terms/>
PREFIX dcat:    <http://www.w3.org/ns/dcat#>
PREFIX foaf:    <http://xmlns.com/foaf/0.1/>

SELECT DISTINCT
    ?nazov ?poskytovatelMeno
    ?accessURL ?format
    ?uprava
    WHERE {{
    GRAPH ?g {{
        ?dataset a dcat:Dataset ;
        dcterms:title ?nazov ;
        dcterms:publisher ?poskytovatel ;
        dcat:distribution ?dist .

        OPTIONAL {{ ?dataset dcterms:modified ?uprava . }}
        
        ?dist dcat:accessURL ?accessURL ;
            dcterms:format ?format .

        ?poskytovatel foaf:name ?poskytovatelMeno .
        FILTER(CONTAINS(LCASE(STR(?poskytovatelMeno)), "{name}"))
    }}
    }}
    ORDER BY DESC(?uprava)
    LIMIT 10
    """

    with httpx.Client(timeout=100) as c:
        r = c.get(
            "https://data.slovensko.sk/api/sparql",
            params={"query": query},
            headers={"Accept": "application/sparql-results+json"},
        )
    data = r.json()

    results = data.get("results", {}).get("bindings",[])
    with open("dataset_report.json", "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)

    datasets = []
    for row in results:
        datasets.append({
            "nazov": row.get("nazov", {}).get("value", ""),
            "poskytovatel": row.get("poskytovatelMeno", {}).get("value", ""),
            "accessURL": row.get("accessURL", {}).get("value", ""),
            "format": row.get("format", {}).get("value", ""),
            "uprava": row.get("uprava", {}).get("value", ""),
        })

    return {
        "has_open_data": len(datasets) > 0,
        "datasets": datasets
    }

