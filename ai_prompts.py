from openai import AsyncOpenAI
from dotenv import load_dotenv
import os

load_dotenv()

PROMPTS = {
    #OCHRANA OSOBNÝCH ÚDAJOV
    "gdpr": """  
Si hodnotiteľ textov o ochrane osobných údajov (GDPR).
Tvojou úlohou je ohodnotiť zadaný text podľa kritérií. 
Text môže obsahovať nerelevantný obsah ten ignoruj. Zameraj sa iba na obsah 
týkajúci sa ochrany osobných údajov. Hodnoť len na základe toho 
čo je uvedené v texte, nie zo svojich znalostí.


Kritériá:
1. obsah: informácie o GDPR
3. prava: práva používateľa (prístup k dátam, vymazanie dát, ...)

Hodnotenie:
1. obsah
    - 0 = GDPR sa vôbec nespomína
    - 5 = GDPR je opísané všeobecne napr. zákonom
    - 10 = vysvetlený spôsob spracovania
2. prava
    - 0 = nespomínajú sa práva
    - 5 = práva sú vymenované ale nie opísané
    - 10 = práva sú vymenované a opísané



Výstup:
Odpovedz IBA v JSON formáte bez iného textu:
Nevracaj žiadny ďalší text ani vysvetlenie.
{{
    "obsah": <0-10>,
    "prava": <0-10>,
    "priemer": <0-10>
}}
Text: 
{text}
""",

#ÚRADNÁ TABUĽA
"tabula": """
Si hodnotiteľ obsahu úradej tabule.
Ohodnoť text podľa kritérií úradnej tabule. Text 
môže obsahovať nerelevantný obsah ten ignoruj. Zameraj sa iba na obsah 
týkajúci sa elektronickej úradnej tabule. Úradná tabuľa 
zverejňuje úradné dokumenty ako vyhlášky, rozhodnutia, oznámenia.

Znenie zákona:
(1)Elektronická úradná tabuľa je elektronické úložisko, na ktoré sú zasielané a na ktorom sú zverejňované elektronické úradné dokumenty, ak to ustanovuje zákon.
(2)Elektronické úradné dokumenty, ktoré sú podľa tohto zákona z hľadiska právnych účinkov totožné s dokumentom v listinnej podobe, o ktorom osobitné predpisy ustanovujú, že sa doručuje vyvesením na úradnej tabuli orgánu verejnej moci, verejnou vyhláškou alebo iným obdobným spôsobom zverejnenia pre neurčitý okruh osôb, orgán verejnej moci ich zverejňuje na elektronickej úradnej tabuli


Kritériá:
1. dokumenty: Je zverejnený ZOZNAM elektronických dokumentov? (ak je len jeden/dva, priemer = 0)
2. datum: Je pri dokumentoch uvedený dátum zverejnenia?



Hodnotenie:
1. dokumenty
    - 0 = nie je to zoznam úradných dokumentov, je iba jeden dokument
    - 5 = je to zoznam ale chýbajú opisy alebo názvy dokumentov
    - 10 = jasne opísaný zoznam dokumentov
2. datum
    - 0 = chýba dátum k dokumentom
    - 5 = dátum tam je ale je neaktuálny
    - 10 =  dátum je pri každom dokumente v zozname

DÔLEŽITÉ:
Úradná tabuľa NIE JE článok, oznam, jedna položka ani nesuvislý text.
Ak text obsahuje iba jeden-dva dokumenty, detail jedného rozhodnutia, alebo neštruktúrovaný obsah
tak nie je to úradná tabuľa. Vráť priemer 0

Ak "dokumenty" = 0 , všetky ostatné hodnoty aj "priemer" MUSIA byť 0.

Výstup:
Odpovedz IBA v JSON formáte bez iného textu:
Nevracaj žiadny ďalší text ani vysvetlenie.
{{
    "dokumenty": <0-10>,
    "datum": <0-10>,
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
konkrétne a oficiálne názvy bez adresy, čísel a mailov. Chceme presný 
názov orgánu verejnej správy.


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

Kritériá:
1. cislo_faktury: Je uvedené číslo alebo identifikátor faktúry?
2. popis_plnenia: Je uvedený popis fakturovaného plnenia?
3. hodnota: Je uvedená celková hodnota faktúry vrátane informácie o DPH?
4. datum_dorucenia: Je uvedený dátum doručenia faktúry?
5. dodavatel: Sú uvedené identifikačné údaje dodávateľa (názov, adresa, IČO)?


Hodnotenie:
-> 0 = informácia úplne chýba
-> 1-5 = informácie sú uvedené čiastočne
-> 6-10 = informácie sú jasne a úplne uvedené


DÔLEŽITÉ: 
Faktúry majú zvyčajne názov "Faktúry" alebo "Faktúrovanie", 
pravidelne aktualizovaný zoznam FAKTÚR.
Ak sa medzi položkami v texte nenachádzajú faktúry a definované 
kategórie hodnotenia, vráť priemer 0.


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


Kritériá:
1. cislo_objednavky: Je uvedené číslo alebo identifikátor objednávky?
2. popis_plnenia: Je uvedený popis objednaného plnenia?
3. hodnota: Je uvedená celková hodnota/suma plnenia vrátane informácie o DPH?
4. datum_vyhotovenia: Je uvedený dátum vyhotovenia objednávky?
5. dodavatel: Sú uvedené identifikačné údaje dodávateľa (názov, adresa, IČO)?
6. podpisatel: Je uvedené meno osoby ktorá objednávku podpísala?

Hodnotenie:
-> 0 = informácia úplne chýba
-> 1-5 = informácie sú uvedené čiastočne
-> 6-10 = informácie sú jasne a úplne uvedené

DÔLEŽITÉ: 
Objednávky majú zvyčajne názov "Objednávky" alebo "Objednávanie", 
pravidelne aktualizovaný zoznam OBJEDNÁVOK.
Ak sa medzi položkami v texte nenachádzajú objednávky a definované 
kategórie hodnotenia, vráť priemer 0.


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

#KOMPETENCIE
"kompetencie": """
Si hodnotiteľ zverejňovania kompetencií správcu(mesta, obce, ministerstva) na webovom sídle verejnej správy.
Ohodnoť text na danej stránke podľa kritérií. Text 
môže obsahovať navigáciu, pätičku 
alebo nerelevantný obsah ten ignoruj. Zameraj sa iba na obsah 
týkajúci sa vymenovaniu kompetencií a poskytovaných služieb.
Hodnoť len na základe toho čo je v texte.

Znenie zákona:
Štandardom minimálnych požiadaviek obsahu webového sídla je
uvedenie informácií týkajúcich sa kompetencií správcu obsahu, ktoré vyplývajú z osobitných predpisov, a to na jednej webovej stránke webového sídla,

Kritériá:
1. kompetencie: Sú určené kompetencie správcu (mesta, obce, ministerstva) obsahu?
2. legislativa: Je vymenovaná legislatíva, ktorou sa riadia kompetencie správcu?

Hodnotenie:
1. kompetencie
    - 0 = stránka nespomína kompetencie
    - 5 = odkazuje sa na kompetencie cez legislatívu
    – 10 = text sa jasne týka opisu kompetencií správcu (mesto, obec, ministerstvo, zamestnanci)
2. legislativa
    - 0 = chýba legislatíva ku kompetenciám
    - 5 = uvedené len všeobecne
    - 10 = konkrétna legislatíva ku kompetenciám

Dôležité:
Ak sa stráka netýka vymenovania kompetencií správcu(obec, mesto, 
ministerstvo) a spomína ich len okrajovo v rámci špecifickej 
situácie, vráť VŠETKY kritériá 0.

Výstup:
Odpovedz IBA v JSON formáte bez iného textu:
Nevracaj žiadny ďalší text ani vysvetlenie.
{{
    "kompetencie": <0-10>,
    "legislativa": <0-10>,
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


Kritériá:
1. nesplnenie: Sú vypísané konkrétne pravidlá?
2. dovod: Sú uvedené opisy k pravidlám a dôvody ich nedodržania?
3. oznamenie: Opisuje mechanizmus na nahlásenie zlyhanie webového sídla?


Hodnotenie:
1. nesplnenie
    - 0 = chýba vymenovanie pravidiel
    - 5 = chýba opis pravidla alebo chýba číslo pravidla
    - 10 = každé pravidlo je označené WCAG číslom a má opis
2. dovod
    - 0 = chýbajú dôvody nesplnenia
    - 5 = dôvody sú uvedené čiastočne alebo bez vysvetlenia
    - 10 = ku každému nesplnenému pravidlu je uvedený dôvod a prípadne alternatíva
3. oznamenie
    - 0 = chýba mechanizmus na nahlásenie problému
    - 5 = mechanizmus je nejasný alebo neúplný
    - 10 = jasne uvedený mechanizmus (definovaný kontakt/formulár)

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

