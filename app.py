import streamlit as st
import subprocess, json
from sparql_test import check_open_data_sparql
st.title("Transparentnosť informačného systému verejnej správy")
tab1, tab2 = st.tabs(["Hodnotenie", "Otvorené dáta"])


####################################
# SCRAPING #########################
####################################
with tab1:
    url = st.text_input("URL")

    if st.button("Vyhodnotiť") and url:
        with st.spinner("Prebieha hodnotenie.."):
            subprocess.run(["python", "run.py", url])

        with open("final_score.json") as f:
            final = json.load(f)
        with open("keywords_report.json") as f:
            kw = json.load(f)["keywords"]
        with open("main_page_report.json", encoding="utf-8") as f:
            mp = json.load(f)
        with open("accessibility_report.json") as f:
            acc = json.load(f)

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Prístupnosť", f"{final['pristupnost']} %")
        c2.metric("Použiteľnosť", f"{final['pouzitelnost']} %")
        c3.metric("Informatívnosť", f"{final['informativnost']} %")
        c4.metric("TRANSPARENTNOSŤ", f"{final['transparentnost']} %")

        st.divider()
        st.header("Prístupnosť")
        st.write(f"**Navštívených stránok:** {acc['pages_visited']}, zlyhalo: {acc['pages_failed']}")
        st.write(f"Porušené WCAG pravidlá: {acc['wcag']['count']}")
        for rule, info in acc["wcag"]["rules"].items():
            with st.expander(rule):
                for desc in info["rule description"]:
                    st.write(desc)
                for u, count in info["url"].items():
                    st.write(f"{u} = {count}x")

        st.divider()
        st.header("Použiteľnosť")
        st.write(f"**HTTPS:** {mp['https']}")
        st.write(f"**Vyhľadávanie:** {mp['search_element']}")
        st.write(f"**Mapa stránky:** {mp['mapa_stranky']}")
        st.write(f"**Správca:** {mp['spravca'] or '—'}")
        st.write(f"**Prevádzkovateľ:** {mp['prevadzkovatel'] or '—'}")

        st.divider()
        st.header("Informatívnosť")
        keywords = {
            "gdpr": "GDPR",
            "tabula": "Úradná tabuľa",
            "vyhlaseniePristupnost": "Vyhlásenie o prístupnosti",
            "kompetencie": "Kompetencie",
            "objednavky": "Objednávky",
            "faktury": "Faktúry",
            "rss": "RSS kanál"
        }
        for key, label in keywords.items():
            val = kw.get(key, {})
            priemer = val.get("priemer") if val else None
            found_on = val.get("found_on") if val else None
            depth = val.get("depth") if val else None
            if priemer is not None:
                st.write(f"**{label}:** {priemer}/10  [Odkaz]({found_on}) (hĺbka {depth})")
            else:
                st.write(f"{label}: nenájdené")

        st.divider()
        st.subheader("Stiahnuť výstupné súbory")
        c1, c2, c3, c4 = st.columns(4)

        with open("scrape.log", encoding="utf-8") as f:
            c1.download_button("scrape.log", f.read(), "scrape.log", "plain/text")
        with open("keywords_report.json", encoding="utf-8") as f:
            c2.download_button("keywords_report.json", f.read(), "keywords_report.json", "application/json")
        with open("accessibility_report.json", encoding="utf-8") as f:
            c3.download_button("accessibility_report.json", f.read(), "accessibility_report.json", "application/json")
        with open("main_page_report.json", encoding="utf-8") as f:
            c4.download_button("main_page_report.json", f.read(), "main_page_report.json", "application/json")

####################################
# OTVORENÉ DÁTA ####################
####################################
with tab2:
    st.header("Otvorené dáta")
    nazov = st.text_input("Názov poskytovateľa", placeholder="Hlavné mesto SR Bratislava")
    if st.button("Hľadať") and nazov:
        with st.spinner("Hľadám...."):
            result = check_open_data_sparql(nazov)
        
        if result["has_open_data"]:
            for ds in result["datasets"]:
                with st.expander(ds["nazov"]):
                    st.write(f"**Poskytovateľ:** {ds['poskytovatel']}")
                    st.write(f"**Formát:** {ds['format']}")
                    st.write(f"**Aktualizácia:** {ds['uprava']}")
                    st.link_button("Otvoriť", ds["accessURL"])
        else:
            st.warning("Žiadne datasety ")