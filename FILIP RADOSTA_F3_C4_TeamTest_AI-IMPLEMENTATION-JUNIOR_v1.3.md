**F3 C4 Team Test – AI Implementation Junior**

**CANDIDATE SHARED**

Verze: v1.3

Jméno kandidáta: Filip Radosta

https://github.com/f-radosta/prestonet-demo

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

Pro mock dokumenty A, B a C worker vrátí mapování na schválený slovník customer\_id, contract\_number, service\_address.

Každá položka má povinná pole: source\_variable, suggested\_variable, confidence, reason, needs\_review.

Jednoznačné varianty (customerId → customer\_id) se namapují s vysokým confidence a needs\_review: false.

Nejasné / neznámé názvy mají needs\_review: true a nejsou tiše „domyšlené“ do slovníku.

Výstup je návrh (proposal). Worker nikdy nepřepíše zdrojový dokument.

Aplikace změny existuje jen jako oddělený krok se explicitním lidským schválením.

Povinných 5 testů z bodu 5 prochází.

V repu nejsou secrets, reálné dokumenty ani produkční data.

## **2\. Komponenty a datový tok**

\- Jak se vstup dostane k workerovi?

Není specifikováno \- pro PoC zvolím A, možná předmět dotazu.

A) zaměstnanec s oprávněním přístupu k workeru vloží dokument ke kterému má on sám přístup a worker vrátí dokument se správným mapováním.   
B) worker má přístup k dokumentům v db a zaměstnanec říká které se mají zpracovat \- v takovém případě by se muselo řešit zda k těm dokumentům má přístup jak zaměstnanec tak worker.

\- Kde proběhne AI volání?

Ve workeru v moment kdy přečte a zpracuje dokument. První vrstva mapování nepotřebuje AI volání, pokusí se mapovat programově a v případě neúspěchu deleguje na LLM.

\- Co je interní a co externí?

Interní: data, dokumenty, worker  
Externí: LLM

\- Kde je validation/approval krok?  
Validace výstupu workera (automatická)

Worker vrátí JSON. Před odesláním se zkontroluje:

suggested\_variable je ze schváleného slovníku, nebo null

confidence je 0–1

needs\_review \= true, pokud confidence \< práh (např. 0.8), mapování chybí, nebo existuje víc kandidátů

Approval (člověk)

Worker nezapisuje do dokumentů. To co se s dokumentem děje dál je mimo PoC.

\- Co se loguje?

request\_id, actor\_id, document\_id (mock), počet proměnných, mapování, confidence, needs\_review, zda šlo LLM volání, latenci, chybový kód.  \- předmět dotazu.

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
Jen payload daného requestu: názvy proměnných / mock dokument, který volající poslal. Žádný scan disku, žádná produkční DB, žádné cizí dokumenty. 

\- Co worker nesmí zapisovat?

Zdrojové dokumenty, produkční úložiště, cílový slovník, cokoliv mimo proposal \+ audit log. Žádný „apply“ bez explicitního approval. 

\- Kde jsou secrets?

Pouze v env / secret manageru (`LLM_API_KEY`). V repu jen `.env.example` bez hodnot. Klíče se nelogují a neposílají klientovi. 

\- Jak se řeší dev/test/prod?

* test: fixture dokumenty A/B/C, LLM mockovaný, žádné síťové volání  
* dev: oddělený klíč, jen mock data  
* prod: v tomto PoC není

\- Jak se zabrání nechtěnému přepisu?

Worker nemá write cestu k dokumentům

Apply endpoint v PoC neexistuje

Cílový slovník je allowlist v kódu, ne z requestu

\- Kdo schvaluje změnu?

Člověk s rolí approver (v PoC operátor / hodnotitel). Worker neschvaluje sám sebe. 

## **5\. Test cases**

Navrhni alespoň 5 testů:

\- jasné mapování,

\- nejasné mapování,

\- neznámá proměnná,

\- citlivý/nepovolený vstup,

\- chyba externího modelu nebo timeout.

\#	případ	vstup	očekávání

1

jasné mapování

customerId

→ customer\_id, vysoké confidence, needs\_review: false, bez LLM

2

nejasné mapování

addr nebo cislo

needs\_review: true, nízké/střední confidence, žádný tichý zápis

3

neznámá proměnná

vatId

suggested\_variable: null, needs\_review: true

4

citlivý/nepovolený vstup

hodnota typu rodné číslo / „prod contract dump“

422 sensitive\_input\_blocked, nic se neloguje z hodnot

5

chyba LLM / timeout

LLM timeout u ID\_ZAKAZNIKA

HTTP 200 s částečným výsledkem nebo 502 s llm\_unavailable; programmatic hit zůstane; zbytek needs\_review: true; write\_performed: false

## **6\. GitHub/repo struktura**

Navrhni minimální strukturu repozitáře a co má být v README. Uveď, co v repozitáři nikdy nesmí být.

prestonet-demo/

  README.md

  .env.example

  .gitignore

  src/

    api.py

    worker.py

    mapper.py          \# deterministic vrstva

    llm\_client.py      \# oddělené, v testu mock

    dictionary.py      \# schválený slovník

    schemas.py

  tests/

    test\_mapping.py

    test\_security.py

    fixtures/

      doc\_a.json

      doc\_b.json

      doc\_c.json

  docs/

    DESIGN.md

## **7\. Dokumentace a handover**

Připrav krátké shrnutí pro tým:

\- co je hotové,

\- co je jen předpoklad,

\- jaká jsou rizika,

\- co vyžaduje review,

\- jaký je další krok.

* Hotové (až se postaví slice): API návrh → proposal JSON, deterministic mapping \+ LLM fallback, flag `needs_review`, testy 1–5, žádný auto-write.  
* Předpoklad: vstup je POST s mock proměnnými (varianta A); slovník jsou jen 3 termíny; LLM je externí.  
* Rizika: LLM halucinace mimo slovník (řeší allowlist); timeout (řeší partial \+ review); někdo omylem pošle reálná data (řeší 422 \+ nelogovat hodnoty); později by hrozil apply bez approval, proto apply v PoC není.  
* Vyžaduje review: práh confidence, aliasy (zejména CZ: `ID_ZAKAZNIKA`), kdo je approver, zda vůbec kdy existuje apply. Ideální by bylo provést test na několika reálných dokumentech, nastavit správně práh, otestovat několik LLM z hlediska kvality a ceny.  
* Další krok: napojit Make na `proposal_ready` \+ lidský approve modul; teprve pak řešit čtení z reálného úložiště (varianta B).

## **8\. Budoucí rozšíření**

Stručně uveď:

\- jak by se worker napojil na Make,

\- co by se změnilo při použití interního modelu na vlastním GPU,

\- co bys zatím nedělal/a.

Make:

Make pošle HTTP na worker → dostane proposal → modul Approve/Reject (email/Slack) → teprve při Approve volá jiný endpoint. Worker v Make scénáři pořád nic nezapisuje.

Interní model na GPU:

Stejný API kontrakt. Změní se jen llm\_client (URL, auth, žádná data ven). Deterministic vrstva a approval zůstanou. Zmizí riziko odtoku dat k třetí straně.

Zatím bych nedělal: auto-apply do produkce, trénink na interních dokumentech, plný firemní glossary, DB crawler, UI editor dokumentů, multi-tenant IAM, streaming celých smluv do LLM.

# **Použití AI**

AI je povolená jako pomocník. Na konci uveď:

\- k čemu jsi AI použil/a,

Implementace, část tohoto dokumentu

\- co jsi převzal/a,

\- co jsi změnil/a,

\- jak jsi výstup ověřil/a.

Nejprve kratkou diskuzi s agentem, precteni implementacniho planu, specialni agent zkontroloval funkcnost a dalsi bezpecnost.

# **Co není cílem**

\- Nemusíš dodat běžící produkční systém.

\- Nemusíš znát naše interní systémy.

\- Nemáš používat reálné interní nebo citlivé dokumenty.

\- Nemáš navrhnout automatický produkční write bez approval.

\- Nemáš zveřejňovat reálné tokeny nebo secrets.

Hodnotitel může klást doplňující otázky, ale nesmí kandidátovi nadiktovat řešení.

