# ROMI: sincronizzazione dei customer Salesforce verso Life365

Questa guida descrive come autenticarsi e inviare eventi per creare o aggiornare
un customer Life365 da Salesforce.

## Documentazione di riferimento

Consultare i documenti in questo ordine:

1. [Contratto degli eventi](docs/integrations/SALESFORCE_CUSTOMER_EVENTS_V1.md):
   struttura completa del DTO, campi obbligatori, valori null e aggiornamenti
   parziali.
2. [Guida operativa](docs/integrations/SALESFORCE_CUSTOMER_SYNC_RUNBOOK.md):
   configurazione, esempi, retry e gestione degli errori.
3. [Payload completo di creazione](tests/fixtures/integrations/salesforce/customer-created-v1.json):
   esempio JSON con dati sintetici.

La [mappatura PostgreSQL](docs/integrations/SALESFORCE_CUSTOMER_POSTGRESQL_MAPPING_V1.md)
descrive come Life365 traduce i campi ricevuti nel proprio database.

## Autenticazione

Gli esempi richiedono `curl` e si eseguono dalla cartella principale del
repository. Prima dei test, verificare con Life365 che l'ambiente utilizzi il
database di collaudo.

```bash
API_URL='https://test.gnurun.com'

curl --fail-with-body -sS -X POST "$API_URL/auth/login" \
  -H 'Content-Type: application/json' \
  --data-raw '{
    "username": "<UTENTE_ADMIN>",
    "password": "<PASSWORD>",
    "principal_type": "user"
  }'
```

Copiare il valore `access_token` dalla risposta:

```bash
AUTH_TOKEN='<ACCESS_TOKEN>'
```

Il token deve appartenere a un utente con ruolo **admin**. Le credenziali reali
devono essere fornite separatamente e non inserite nel repository.

## Creare un customer

Preparare `customer-created.json` partendo dal payload completo collegato sopra.
Usare un nuovo `eventId` e dati di prova riconoscibili, con un login non ancora
utilizzato. La creazione **non deve contenere `referenceId`**.

```bash
curl --fail-with-body -sS -X POST \
  "$API_URL/integrations/salesforce/events" \
  -H "Authorization: Bearer $AUTH_TOKEN" \
  -H 'Content-Type: application/json' \
  --data-binary @customer-created.json
```

Il successo restituisce HTTP `200` con `success`, `eventId` e `referenceId`.
Conservare `referenceId`: identifica il customer Life365 e deve essere usato
negli aggiornamenti. Il successo viene restituito soltanto dopo il commit
dell'operazione nel backend PostgreSQL.

## Aggiornare un customer

Sostituire `<NUOVO_UUID>` con un nuovo UUID e `42` con il `referenceId` ricevuto
dalla creazione:

```bash
curl --fail-with-body -sS -X POST \
  "$API_URL/integrations/salesforce/events" \
  -H "Authorization: Bearer $AUTH_TOKEN" \
  -H 'Content-Type: application/json' \
  --data-raw '{
    "schemaVersion": 1,
    "eventId": "<NUOVO_UUID>",
    "occurredAt": "2026-10-22T10:00:00Z",
    "eventType": "customer.updated",
    "referenceId": 42,
    "data": {
      "company": {
        "name": "ROMI - Ragione sociale aggiornata",
        "website": null
      }
    }
  }'
```

Usare la data effettiva dell'evento. Questo esempio aggiorna il nome e cancella
il sito web; gli altri campi rimangono invariati. Anche un aggiornamento riuscito
restituisce HTTP `200` con `success`, `eventId` e `referenceId`.

## Regole da rispettare

- `schemaVersion` resta `1`. **Non inviare `resourceVersion`**: viene rifiutato
  con HTTP `422`.
- Un campo omesso rimane invariato; `null` cancella un valore soltanto dove
  consentito. Un array fornito sostituisce quello precedente; `[]` lo svuota.
- Inviare un evento alla volta per customer e attendere il successo. Customer
  diversi possono essere sincronizzati contemporaneamente.
- Dopo un timeout o un esito incerto, ritentare **lo stesso `eventId` con
  contenuto identico** prima di procedere. Non cambiare neppure `occurredAt`.
- Un evento completato restituisce il risultato originale; lo stesso ID con
  contenuto diverso genera HTTP `409`.
- `occurredAt` descrive l'evento, ma non determina l'ordine degli aggiornamenti.
- Gli eventi elaborati prima del reset dello storico hanno perso la protezione
  dai duplicati: non devono essere reinviati.

## Documentazione interattiva

La [Swagger UI dell'ambiente di test](https://test.gnurun.com/docs) permette di
consultare gli schemi e provare gli endpoint.

Eseguire `/auth/login`, copiare `access_token`, selezionare **Authorize** e
inserire il token. Le chiamate eseguite da Swagger modificano realmente i dati
dell'ambiente collegato.
