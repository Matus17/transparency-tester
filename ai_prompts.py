from openai import AsyncOpenAI
from dotenv import load_dotenv
import os

load_dotenv()

PROMPTS = {
    #OCHRANA OSOBNÝCH ÚDAJOV
    "gdpr": """  
Si hodnotiteľ textov o ochrane osobných údajov (GDPR).
Tvojou úlohou je ohodnotiť zadaný text podľa 3 kritérií v 
rozsahu od 0 do 10. Text môže obsahovať navigáciu, pätičku 
alebo nerelevantný obsah ten ignoruj. Zameraj sa iba na obsah 
týkajúci sa ochrany osobných údajov. Hodnoť len na základe toho 
čo je uvedené v texte, nie zo svojich znalostí.

Hodnotenie:
-> 0 = informácia úplne chýba
- 1–5 = informácia je uvedená čiastočne
-> 6–10 = informácia je jasne a dobre vysvetlená

Kritériá:
1. what_data: kategórie osobných údajov, ktoré sa zbierajú
2. why: účel spracovania údajov
3. rights: práva používateľa (prístup, vymazanie, ...)


Výstup:
Odpovedz IBA v JSON formáte bez iného textu:
Nevracaj žiadny ďalší text ani vysvetlenie.
{{
    "what_data": <0-10>,
    "why": <0-10>,
    "rights": <0-10>,
    "priemer": <0-10>
}}
Text: 
{text}
""",

#ÚRADNÁ TABUĽA
"tabula": """
Si hodnotiteľ obsahu úradej tabule.
Ohodnoť text podľa kritérií úradnej tabule (0-10). Text 
môže obsahovať navigáciu, pätičku 
alebo nerelevantný obsah ten ignoruj. Zameraj sa iba na obsah 
týkajúci sa elektronickej úradnej tabule.
Hodnoť len na základe toho čo je v texte, ak informácia 
chýba daj 0, ak je čiastočná daj 1-5, ak je dobrá daj 6-10.

Hodnotenie:
-> 0 = informácia úplne chýba
- 1–5 = informácia je uvedená čiastočne
-> 6–10 = informácia je jasne a dobre vysvetlená

Kritériá:
1. documents: Sú zverejnené elektronické dokumenty orgánu verejnej moci?
2. date: Je pri dokumentoch uvedený dátum zverejnenia?
3. up_to_date: Sú dokumenty aktuálne a zverejnené bez zbytočného odkladu?


Výstup:
Odpovedz IBA v JSON formáte bez iného textu:
Nevracaj žiadny ďalší text ani vysvetlenie.
{{
    "documents": <0-10>,
    "date": <0-10>,
    "up_to_date": <0-10>,
    "priemer": <0-10>
}}

Text: 
{text}
""",
# SPRÁVCA
"spravca": 
"""Si používateľ informačného systému verejnej správy. Našiel si 
stránku s textom, ktorý je uvedený úplne dole a chceš v ňom nájsť 
správcu obsahu, ktorý zodpovedá za obsah. Hladame niečo 
na tento štýl, :
        KONTAKT
        Ministerstvo vnútra SR
        Pribinova 2
        812 72 Bratislava
        Telefón: +421 2 5094 1111
        Fax: +421 2 5094 4397
        E-mail: public@minv.sk
        ...
Tu by si vybral "Ministerstvo vnútra SR". Vyberaj 
konkrétne a oficiálne názvy bez adresy, čísel a mailov.


Výstup:
Odpovedz IBA v JSON formáte bez iného textu:
Nevracaj žiadny ďalší text ani vysvetlenie.
{{
    "spravca"
}}
Teraz zhodnoť tento text: 
{text}
""",

# PREVÁDZKOVATEĽ
"prevadzkovatel": 
"""Si používateľ informačného systému verejnej správy. Našiel si 
stránku s textom, ktorý je uvedený úplne dole a chceš v ňom nájsť 
tecnického prevádzovatela obsahu, ktorý zodpovedá za fungovanie 
stránky alebo systému.


Výstup:
Odpovedz IBA v JSON formáte bez iného textu:
Nevracaj žiadny ďalší text ani vysvetlenie.
{{
    "prevadzkovatel"
}}
Teraz zhodnoť tento text: 
{text}
"""

}

agent = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))

