# transparency-tester

Aplikácia na testovanie transparentnosti informačných systémov verejnej správy SR.

# Required -------

- Python 3.11+
- pip
- stiahnutie axe-core, napríklad zo stránky: https://cdnjs.cloudflare.com/ajax/libs/axe-core/4.10.3/axe.min.js
- OpenAI API kľúč uložený v .env súbore
              OPENAI_API_KEY=tajne_api
  
# Installation ----

pip install -r requirements.txt
playwright install

# Run app ---------

streamlit run app.py

