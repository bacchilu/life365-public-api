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

## Ambiente sandbox

La sandbox espone gli stessi endpoint sotto `/sandbox`, ma usa esclusivamente il
database PostgreSQL locale `life365_sandbox`. Le chiamate senza questo prefisso
mantengono la configurazione esistente: non sono automaticamente chiamate di test.

Gli esempi di questa guida utilizzano la sandbox esposta sul dominio di produzione:

```bash
API_URL='https://b2b.life365.eu/public-api/sandbox'
```

| Operazione | URL sandbox |
|---|---|
| Autenticazione | `https://b2b.life365.eu/public-api/sandbox/auth/login` |
| Creazione e aggiornamento customer | `https://b2b.life365.eu/public-api/sandbox/integrations/salesforce/events` |
| Logout | `https://b2b.life365.eu/public-api/sandbox/auth/logout` |
| Swagger | `https://b2b.life365.eu/public-api/sandbox/docs` |

Per avviare l'ambiente, configurare le variabili `SANDBOX_DATABASE_HOST`,
`SANDBOX_DATABASE_PORT`, `SANDBOX_DB_PASSWORD`, `SANDBOX_JWT_SECRET_KEY` e
`SANDBOX_CUSTOMER_SYNC_FINGERPRINT_SECRET` come descritto nella
[guida della sandbox](docs/SANDBOX_API.md), quindi eseguire `make run` oppure
`make docker-dev-up`. Questi comandi avviano anche PostgreSQL. Non modificare il
`DATABASE_URL` di produzione. Se la configurazione sandbox manca o non è valida,
le sue operazioni restituiscono HTTP `503`, senza ripiegare sulla produzione.

Dietro il reverse proxy, il prefisso `/sandbox` segue quello dell'applicazione:
ad esempio `https://b2b.life365.eu/public-api/sandbox`. Questo URL è utilizzabile
solo dopo il deploy e la configurazione della sandbox su quell'ambiente;
l'esistenza del codice locale non ne garantisce la disponibilità remota.

## Credenziali locali Salesforce

Il seed del database locale include questo account applicativo:

| Campo | Valore |
|---|---|
| Username | `salesforce` |
| Password in chiaro | `romi` |
| `principal_type` | `user` |
| Ruolo | `admin` |

Sono **credenziali di esempio della sandbox**, non credenziali Salesforce OAuth
né credenziali di produzione. Non usare questo ambiente con dati sensibili e non
esporlo a utenti non autorizzati.

## Autenticazione

Gli esempi richiedono `curl` e si eseguono dalla cartella principale del
repository. Verificare che `API_URL` includa `/sandbox` prima di inviare i test.

```bash
API_URL='https://b2b.life365.eu/public-api/sandbox'

curl --fail-with-body -sS -X POST "$API_URL/auth/login" \
  -H 'Content-Type: application/json' \
  --data-raw '{
    "username": "salesforce",
    "password": "romi",
    "principal_type": "user"
  }'
```

Copiare il valore `access_token` dalla risposta:

```bash
AUTH_TOKEN='<ACCESS_TOKEN>'
```

Il token deve appartenere a un utente con ruolo **admin**. Le credenziali reali
di produzione devono essere fornite separatamente e non inserite nel repository.
Un token sandbox non funziona sugli endpoint esistenti e viceversa: la risposta
è HTTP `401`. Per cambiare ambiente occorre autenticarsi nuovamente sul relativo
endpoint.

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

## Logout dalla sandbox

```bash
curl --fail-with-body -sS -X POST "$API_URL/auth/logout" \
  -H "Authorization: Bearer $AUTH_TOKEN"
```

Il logout revoca soltanto la sessione sandbox corrente. Le sessioni sandbox sono
in memoria, separate dal file SQLite dell'applicazione esistente: dopo un riavvio
o reload dell'API occorre autenticarsi di nuovo. Usare un solo worker API.

## Limiti e durata dei dati sandbox

- Creazione, aggiornamenti e storico degli eventi vengono salvati solo nel
  database locale. Le operazioni di sincronizzazione richiedono il ruolo admin.
- Le raccomandazioni prodotto restituiscono HTTP `501`: non viene effettuata
  alcuna chiamata al servizio esterno. Gli eventi ricevuti non generano chiamate
  in uscita verso Salesforce.
- Eccezione esplicita: i nuovi endpoint `POST` e `PUT`
  `/sandbox/integrations/salesforce/customers/{id}` leggono un customer locale
  esistente e lo inviano realmente alla sandbox Salesforce. Non accettano un body
  e richiedono il ruolo admin. La `PUT` invia tutti i dati condivisi e li
  sovrascrive sul lato Salesforce. Vedi la
  [guida di esportazione](docs/integrations/SALESFORCE_CUSTOMER_EXPORT.md).
- PostgreSQL usa memoria temporanea: fermare il suo container elimina sia la
  sandbox sia il database separato dei test automatici. All'avvio successivo
  vengono ripristinati i dati di esempio, non le modifiche fatte durante i test.
- Dopo un reset del database, riavviare anche l'API e autenticarsi di nuovo.
  Lo storico degli eventi è perso: non reinviare vecchi eventi confidando nella
  precedente protezione dai duplicati.

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

La [Swagger UI della sandbox](https://b2b.life365.eu/public-api/sandbox/docs)
permette di consultare gli stessi schemi ed eseguire chiamate sul database
`life365_sandbox` locale al server che ospita l'API, non sul PostgreSQL della
propria workstation.
Autenticarsi con `salesforce` / `romi` tramite `/sandbox/auth/login`.

La [Swagger UI di produzione](https://b2b.life365.eu/public-api/docs)
usa invece l'ambiente esistente e richiede le sue credenziali, non quelle della
sandbox.

Eseguire `/auth/login`, copiare `access_token`, selezionare **Authorize** e
inserire il token. Le chiamate eseguite da Swagger modificano realmente i dati
dell'ambiente collegato.
