from openai import AsyncOpenAI
from dotenv import load_dotenv
import os

load_dotenv()

PROMPTS = {
    #OCHRANA OSOBNÝCH ÚDAJOV
    "gdpr": """  
Si hodnotiteľ textov o ochrane osobných údajov (GDPR).
Tvojou úlohou je ohodnotiť zadaný text podľa 3 kritérií v 
rozsahu (0-10). Text môže obsahovať navigáciu, pätičku 
alebo nerelevantný obsah ten ignoruj. Zameraj sa iba na obsah 
týkajúci sa ochrany osobných údajov. Hodnoť len na základe toho 
čo je uvedené v texte, nie zo svojich znalostí.

Hodnotenie:
-> 0 = informácia úplne chýba
- 1–5 = informácia je uvedená čiastočne
-> 6–10 = informácia je jasne a dobre vysvetlená



Kritériá:
1. ake_udaje: kategórie osobných údajov, ktoré sa zbierajú
2. preco: účel spracovania údajov
3. prava: práva používateľa (prístup k dátam, vymazanie dát, ...)


Výstup:
Odpovedz IBA v JSON formáte bez iného textu:
Nevracaj žiadny ďalší text ani vysvetlenie.
{{
    "ake_udaje": <0-10>,
    "preco": <0-10>,
    "prava": <0-10>,
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
Hodnoť len na základe toho čo je v texte. Ak text obsahuje iba 
jeden dokument alebo detail jednej zmluvy/oznamu a ni cely zoznam, 
vráť priemer 0. 

Znenie zákona:
(1)Elektronická úradná tabuľa je elektronické úložisko, na ktoré sú zasielané a na ktorom sú zverejňované elektronické úradné dokumenty, ak to ustanovuje zákon.
(2)Elektronické úradné dokumenty, ktoré sú podľa tohto zákona z hľadiska právnych účinkov totožné s dokumentom v listinnej podobe, o ktorom osobitné predpisy ustanovujú, že sa doručuje vyvesením na úradnej tabuli orgánu verejnej moci, verejnou vyhláškou alebo iným obdobným spôsobom zverejnenia pre neurčitý okruh osôb, orgán verejnej moci ich zverejňuje na elektronickej úradnej tabuli

Hodnotenie:
-> 0 = nexistuje tu zoznam s informáciami o dokumentoch úplne chýbajú/ nachádza sa tu len jeden dokument, ak ide len o jeden dokument, vyhodnoť preimer ako 0
- 1–5 = informácie sú uvedené čiastočne
-> 6–10 = informácie o oznamoch sú jasne definované

Kritériá:
1. dokumenty: Je zverejnený ZOZNAM elektronických dokumentov? (ak je len jeden/dva = 0)
2. datum: Je pri dokumentoch uvedený dátum zverejnenia?
3. aktualnost: Sú dokumenty aktuálne?


Výstup:
Odpovedz IBA v JSON formáte bez iného textu:
Nevracaj žiadny ďalší text ani vysvetlenie.
{{
    "dokumenty": <0-10>,
    "datum": <0-10>,
    "aktualnost": <0-10>,
    "priemer": <0-10>
}}

Text: 
{text}
""",
# SPRÁVCA
"spravca": 
"""Si používateľ informačného systému verejnej správy. Našiel si 
stránku s textom, ktorý je uvedený dole a chceš v ňom nájsť 
správcu obsahu, ktorý zodpovedá za obsah. Kto to spravuje?
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
stránky alebo systému. Kto je to? Cheme presný názov organizácie.


Výstup:
Odpovedz IBA v JSON formáte bez iného textu:
Nevracaj žiadny ďalší text ani vysvetlenie.
{{
    "prevadzkovatel"
}}
Teraz zhodnoť tento text: 
{text}
""",

#FAKTÚRY
"faktury": """
Si hodnotiteľ obsahu stránky povinne zverejňovaných faktúr.
Ohodnoť text podľa kritérií §5b písm. b) infozákona 211/2000. Text môže obsahovať navigáciu, pätičku
alebo nerelevantný obsah, ten ignoruj. Zameraj sa iba na obsah týkajúci sa faktúr.
Hodnoť len na základe toho čo je v texte, ak informácia chýba daj 0, ak je čiastočná daj 1-5, ak je dobrá daj 6-10.

Znenie zákona:
Povinná osoba zverejňuje na svojom webovom sídle, ak ho má zriadené, v štruktúrovanej a prehľadnej forme najmä tieto údaje:
b)o faktúre za tovary, služby a práce
1.identifikačný údaj faktúry, ak povinná osoba vedie číselník faktúr,
2.popis fakturovaného plnenia, tak ako je uvedený na faktúre,
3.celkovú hodnotu fakturovaného plnenia v sume, ako je uvedená na faktúre, ako aj údaj o tom, či je suma vrátane dane z pridanej hodnoty, alebo či je suma bez dane z pridanej hodnoty,
4.identifikáciu zmluvy, ak faktúra súvisí s povinne zverejňovanou zmluvou, (toto nevieme určiť - nehodnotí sa)
5.identifikáciu objednávky, ak faktúra súvisí s objednávkou, (toto nevieme určiť - nehodnotí sa)
6.dátum doručenia faktúry,
7.identifikačné údaje dodávateľa fakturovaného plnenia:
7a.meno a priezvisko fyzickej osoby, obchodné meno fyzickej osoby-podnikateľa alebo obchodné meno alebo názov právnickej osoby,
7b.adresu trvalého pobytu fyzickej osoby, miesto podnikania fyzickej osoby-podnikateľa alebo sídlo právnickej osoby,
7c.identifikačné číslo, ak ho má dodávateľ fakturovaného plnenia pridelené.
Hodnotenie:
-> 0 = informácia úplne chýba
-> 1-5 = informácie sú uvedené čiastočne
-> 6-10 = informácie sú jasne a úplne uvedené

Kritériá:
1. cislo_faktury: Je uvedené číslo alebo identifikátor faktúry?
2. popis_plnenia: Je uvedený popis fakturovaného plnenia?
3. hodnota: Je uvedená celková hodnota faktúry vrátane informácie o DPH?
4. datum_dorucenia: Je uvedený dátum doručenia faktúry?
5. dodavatel: Sú uvedené identifikačné údaje dodávateľa (názov, adresa, IČO)?

Výstup:
Odpovedz IBA v JSON formáte bez iného textu.
Nevracaj žiadny ďalší text ani vysvetlenie.
{{
    "cislo_faktury": <0-10>,
    "popis_plnenia": <0-10>,
    "hodnota": <0-10>,
    "datum_dorucenia": <0-10>,
    "dodavatel": <0-10>,
    "priemer": <0-10>
}}

Text:
{text}
""",

#OBJEDNÁVKY
"objednavky": """
Si hodnotiteľ obsahu stránky povinne zverejňovaných objednávok.
Ohodnoť text podľa kritérií §5b písm. a) infozákona 211/2000. Text môže obsahovať navigáciu, pätičku
alebo nerelevantný obsah, ten ignoruj. Zameraj sa iba na obsah týkajúci sa objednávok.
Hodnoť len na základe toho čo je v texte, ak informácia chýba daj 0, ak je čiastočná daj 1-5, ak je dobrá daj 6-10.

Znenie zákona:

Povinná osoba zverejňuje na svojom webovom sídle, ak ho má zriadené, v štruktúrovanej a prehľadnej forme najmä tieto údaje:
a)o vyhotovenej objednávke tovarov, služieb a prác
1.identifikačný údaj objednávky, ak povinná osoba vedie číselník objednávok,
2.popis objednaného plnenia,
3.celkovú hodnotu objednaného plnenia v sume, ako je uvedená na objednávke, alebo maximálnu odhadovanú hodnotu objednaného plnenia, ako aj údaj o tom, či je suma vrátane dane z pridanej hodnoty, alebo či je suma bez dane z pridanej hodnoty,
4.identifikáciu zmluvy, ak objednávka súvisí s povinne zverejňovanou zmluvou (toto nevieme určiť - nehodnotí sa)
5.dátum vyhotovenia objednávky,
6.identifikačné údaje dodávateľa objednaného plnenia:
6a.meno a priezvisko fyzickej osoby, obchodné meno fyzickej osoby-podnikateľa alebo obchodné meno alebo názov právnickej osoby,
6b.adresu trvalého pobytu fyzickej osoby, miesto podnikania fyzickej osoby-podnikateľa alebo sídlo právnickej osoby,
6c.identifikačné číslo, ak ho má dodávateľ objednaného plnenia pridelené,
7.údaje o fyzickej osobe, ktorá objednávku podpísala:
7a.meno a priezvisko fyzickej osoby,
7b.funkciu fyzickej osoby, ak takáto funkcia existuje,

Hodnotenie:
-> 0 = informácia úplne chýba
-> 1-5 = informácie sú uvedené čiastočne
-> 6-10 = informácie sú jasne a úplne uvedené

Kritériá:
1. cislo_objednavky: Je uvedené číslo alebo identifikátor objednávky?
2. popis_plnenia: Je uvedený popis objednaného plnenia?
3. hodnota: Je uvedená celková hodnota plnenia vrátane informácie o DPH?
4. datum_vyhotovenia: Je uvedený dátum vyhotovenia objednávky?
5. dodavatel: Sú uvedené identifikačné údaje dodávateľa (názov, adresa, IČO)?
6. podpisatel: Je uvedené meno a funkcia osoby ktorá objednávku podpísala?

Výstup:
Odpovedz IBA v JSON formáte bez iného textu.
Nevracaj žiadny ďalší text ani vysvetlenie.
{{
    "cislo_objednavky": <0-10>,
    "popis_plnenia": <0-10>,
    "hodnota": <0-10>,
    "datum_vyhotovenia": <0-10>,
    "dodavatel": <0-10>,
    "podpisatel": <0-10>,
    "priemer": <0-10>
}}

Text:
{text}
""",

#SLUŽBY
"sluzby": """
Si hodnotiteľ zverejňovania poskytovaných elektronických služieb na webovom sídle verejnej správy.
Ohodnoť text na danej stránke podľa kritérií (0-10). Text 
môže obsahovať navigáciu, pätičku 
alebo nerelevantný obsah ten ignoruj. Zameraj sa iba na obsah 
týkajúci sa vymenovaniu kompetencií a poskytovaných služieb.
Hodnoť len na základe toho čo je v texte, ak informácia 
chýba daj 0, ak je čiastočná daj 1-5, ak je dobrá daj 6-10.

Znenie zákona:
Štandardom minimálnych požiadaviek obsahu webového sídla je
uvedenie informácií týkajúcich sa kompetencií a poskytovaných služieb správcu obsahu, ktoré vyplývajú z osobitných predpisov, a to na jednej webovej stránke webového sídla,

Hodnotenie:
-> 0 = informácia úplne chýba/ nachádza sa tu len jeden dokument
- 1–5 = informácie sú uvedené čiastočne
-> 6–10 = informácie o oznamoch sú jasne definované

Kritériá:
1. služby: Je zverejnený zoznam poskytovaných služieb?
2. kompetencie: Sú určené kompetencie správcu?
3. up_to_date: Sú dokumenty aktuálne?


Výstup:
Odpovedz IBA v JSON formáte bez iného textu:
Nevracaj žiadny ďalší text ani vysvetlenie.
{{
    "sluzby": <0-10>,
    "kompetencie": <0-10>,
    "priemer": <0-10>
}}

Text: 
{text}
""",


#PRÍSTUPNOSŤ
"vyhlaseniePristupnost": """
Si hodnotiteľ zverejňovania Vyhlásenia o prístupnosti na webovom sídle verejnej správy.
Ohodnoť text na danej stránke podľa kritérií (0-10). Text 
môže obsahovať navigáciu, pätičku 
alebo nerelevantný obsah ten ignoruj. Zameraj sa iba na obsah 
týkajúci sa vyhláseniu o prístupnosti.
Hodnoť len na základe toho čo je v texte, ak informácia 
chýba daj 0, ak je čiastočná daj 1-5, ak je dobrá daj 6-10.

Znenie zákona:
Štandardy prístupnosti a funkčnosti webových sídiel a mobilných aplikácií
§ 14 Prístupnosť webových sídiel a mobilných aplikácií
(1)Štandardom prístupnosti webových sídiel je zabezpečenie vnímateľnosti, ovládateľnosti, zrozumiteľnosti a robustnosti webových sídiel, a to dodržiavaním pravidiel podľa slovenskej technickej normy,4) najmä pravidiel úrovní A a AA osobitnej špecifikácie World Wide Web Consortium (W3C) pre prístupnosť webového obsahu vo verzii 2.1.
§ 15 Minimálne požiadavky obsahu webového sídla
(1)Štandardom minimálnych požiadaviek obsahu webového sídla je
a)uvedenie zrozumiteľného a aktuálneho vyhlásenia o prístupnosti webového sídla alebo jeho časti v prístupnom formáte podľa pravidiel uvedených v § 14 ods. 1, pričom vyhlásenie obsahuje najmenej
1.opis nesplnenia konkrétnych bodov alebo pravidiel prístupnosti webových stránok,
2.opis nedodržania pravidiel prístupnosti týkajúci sa konkrétnych častí obsahu webového sídla, najmä v podobe uvedenia konkrétnych nedodržaných pravidiel, uvedenie dôvodov ich nedodržania a opis poskytnutých prístupných alternatív, ak existujú,
3.opis mechanizmu s uvedením odkazu naň, prostredníctvom ktorého môže každá osoba oznámiť správcovi obsahu webového sídla zlyhanie webového sídla, ak ide o plnenie požiadaviek na prístupnosť podľa § 14 a požiadať o informáciu, ktoré časti webového sídla nemusia spĺňať štandardy prístupnosti a z akého dôvodu,
4.odkaz na postup vykonania nápravy, ak použitie mechanizmu podľa tretieho bodu neviedlo k náprave,
Hodnotenie:
-> 0 = informácia úplne chýba/ nachádza sa tu len jeden dokument
- 1–5 = informácie sú uvedené čiastočne
-> 6–10 = informácie o oznamoch sú jasne definované

Kritériá:
1. nesplnenie: Sú opísané konkrétne body pravidiel?
2. dovod: Sú uvedené dôvody nesplnenia pravidiel?
3. oznamenie: Opisuje mechanizmus na nahlásenie zlyhanie webového sídla?


Výstup:
Odpovedz IBA v JSON formáte bez iného textu:
Nevracaj žiadny ďalší text ani vysvetlenie.
{{
    "nesplnenie": <0-10>,
    "dovod": <0-10>,
    "oznamenie": <0-10>,
    "priemer": <0-10>
}}

Text: 
{text}
"""


}

agent = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))

