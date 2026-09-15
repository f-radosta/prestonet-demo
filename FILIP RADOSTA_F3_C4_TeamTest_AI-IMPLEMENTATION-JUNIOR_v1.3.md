**F3 C4 Team Test – AI Implementation Junior**

**CANDIDATE SHARED**

Verze: v1.3

Jméno kandidáta: Filip Radosta

# **Co je F3**

F3 je online praktická ukázka s hodnotitelem. Cílem není dodat produkční kód ani navrhnout celou firemní AI platformu. Cílem je ukázat, jak převádíte konkrétní use-case do bezpečného technického PoC, API/worker návrhu, testů a dokumentace.

# **Časový rámec**

Celkem 70–80 minut:

\- 10 minut: pochopení zadání a otázky,

\- 35–40 minut: návrh a technický výstup,

\- 10 minut: bezpečnostní review vlastního řešení,

\- 10–15 minut: prezentace a diskuse.

# **Scénář**

Firma má dokumenty a šablony, ve kterých se stejná informace označuje různými názvy proměnných.

## **Ukázkové vstupy:**

Dokument A: customer\_id, contract\_number, service\_address

Dokument B: customerId, contractNo, address\_service

Dokument C: ID\_ZAKAZNIKA, cisloSmlouvy, adresaSluzby

## **Schválený cílový slovník pro PoC:**

customer\_id

contract\_number

service\_address

## **Má vzniknout AI worker, který:**

\- přečte mock dokument nebo seznam proměnných,

\- navrhne mapování na cílový slovník,

\- uvede důvod a confidence,

\- označí nejasné případy,

\- připraví návrh změn,

\- nesmí automaticky přepsat produkční dokumenty,

\- před změnou vyžaduje lidské schválení.

# **Tvůj úkol**

Navrhni první bezpečný vertical-slice PoC.

# **Povinné výstupy**

## **1\. Scope a acceptance criteria**

\- Co worker přesně řeší?

Firma různé dokumenty s různými klíčovými slovy a je potřeba to sjednotit do schváleného cílového slovníku. Samotný worker čte mock dokument a navrhuje mapování do 3 klíčových slov, uvádí reasoning a confidence, flaguje nejasné případy a navrhuje změny na lidské schválení.

\- Co neřeší?

Nepřepisuje produkční dokumenty, vyžaduje schválení návrhů

\- Jak poznáme, že PoC funguje?

## **2\. Komponenty a datový tok**

\- Jak se vstup dostane k workerovi?

Není specifikováno \- nutné zjistit. 

A) zaměstnanec s oprávněním přístupu k workeru vloží dokument ke kterému má on sám přístup a worker vrátí dokument se správným mapováním.   
B) worker má přístup k dokumentům v db a zaměstnanec říká které se mají zpracovat \- v takovém případě by se muselo řešit zda k těm dokumentům má přístup jak zaměstnanec tak worker.

\- Kde proběhne AI volání?

Ve workeru v moment kdy přečte a zpracuje dokument. První vrstva mapování nepotřebuje AI volání, pokusí se mapovat programově a v případě neúspěchu deleguje na LLM.

\- Co je interní a co externí?

Interní: data, dokumenty, worker  
Externí: LLM

\- Kde je validation/approval krok?  
Pokud je to myšleno jako validace výstupu workera tak on vrátí 

\- Co se loguje?

Kdo který dokument zpracoval, confidence, výsledek klíčových slov. předmět dotazu.

## **3\. API kontrakt nebo pseudokód**

Navrhni minimálně:

\- vstupní JSON,

\- výstupní JSON,

\- chybový stav,

\- pseudokód nebo krátkou ukázku funkce v jazyce podle volby.

## **Výstup má obsahovat minimálně:**

source\_variable

suggested\_variable

confidence

reason

needs\_review

## **4\. Bezpečnost a oprávnění**

\- Jaká data worker smí číst?

\- Co worker nesmí zapisovat?

\- Kde jsou secrets?

\- Jak se řeší dev/test/prod?

\- Jak se zabrání nechtěnému přepisu?

\- Kdo schvaluje změnu?

## **5\. Test cases**

Navrhni alespoň 5 testů:

\- jasné mapování,

\- nejasné mapování,

\- neznámá proměnná,

\- citlivý/nepovolený vstup,

\- chyba externího modelu nebo timeout.

## **6\. GitHub/repo struktura**

Navrhni minimální strukturu repozitáře a co má být v README. Uveď, co v repozitáři nikdy nesmí být.

## **7\. Dokumentace a handover**

Připrav krátké shrnutí pro tým:

\- co je hotové,

\- co je jen předpoklad,

\- jaká jsou rizika,

\- co vyžaduje review,

\- jaký je další krok.

## **8\. Budoucí rozšíření**

Stručně uveď:

\- jak by se worker napojil na Make,

\- co by se změnilo při použití interního modelu na vlastním GPU,

\- co bys zatím nedělal/a.

# **Použití AI**

AI je povolená jako pomocník. Na konci uveď:

\- k čemu jsi AI použil/a,

\- co jsi převzal/a,

\- co jsi změnil/a,

\- jak jsi výstup ověřil/a.

# **Co není cílem**

\- Nemusíš dodat běžící produkční systém.

\- Nemusíš znát naše interní systémy.

\- Nemáš používat reálné interní nebo citlivé dokumenty.

\- Nemáš navrhnout automatický produkční write bez approval.

\- Nemáš zveřejňovat reálné tokeny nebo secrets.

Hodnotitel může klást doplňující otázky, ale nesmí kandidátovi nadiktovat řešení.

