# Mapping worker PoC

Bezpečný vertical-slice PoC: worker namapuje názvy polí z mock dokumentu na schválený slovník a vrátí **návrh ke schválení**. Nikdy nepřepisuje zdrojové dokumenty.

Schválený slovník: `customer_id`, `contract_number`, `service_address`.

## Co je hotové

- `POST /map` přijme seznam názvů (`variables`) nebo mock `document` (použijí se jen klíče)
- první vrstva mapuje programově; LLM se volá jen na zbytek (v testech a bez klíče je mock)
- každá položka má `source_variable`, `suggested_variable`, `confidence`, `reason`, `needs_review`
- návrh se uloží jako `pending`; `write_performed` je vždy `false`
- člověk schválí nebo zamítne přes `POST /proposals/{id}/approve` a `/reject` — mění se jen stav návrhu

## Co PoC záměrně nedělá

- nečte firemní DB ani produkční soubory
- nemá apply/write endpoint na dokumenty
- neposílá hodnoty polí do LLM
- není napojený na Make ani interní GPU model

## Spuštění

Python 3.12+.

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -e ".[dev]"
uvicorn src.api:app --reload
```

Demo v prohlížeči: [http://127.0.0.1:8000](http://127.0.0.1:8000) — dokumenty A/B/C, nejasné i citlivé vstupy, schválení bez zápisu.

Příklad:

```bash
curl -X POST http://127.0.0.1:8000/map ^
  -H "Content-Type: application/json" ^
  -d "{\"actor_id\":\"user-1\",\"variables\":[\"customerId\",\"vatId\"]}"
```

Schválení (pořád bez zápisu do dokumentu):

```bash
curl -X POST http://127.0.0.1:8000/proposals/<proposal_id>/approve ^
  -H "X-Actor-Id: approver-1"
```

Volitelné LLM: zkopíruj `.env.example` do `.env` a nastav `LLM_API_KEY`. Bez klíče zůstane mock.

## Testy

```bash
pytest
```

Pokrytí: jasné mapování, nejasné mapování, neznámá proměnná, citlivý vstup (422), timeout LLM (502), fixtures A/B/C, approval `pending` → `approved` a druhé approve → 409.

## Co v repozitáři nikdy nesmí být

- `.env` a reálné API klíče / tokeny
- produkční nebo zákaznické dokumenty
- PII (rodná čísla, adresy, čísla smluv)
- interní credentials
