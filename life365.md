# Life365: sincronizzazione di customer, prodotti e ordini verso Salesforce

Questa guida è rivolta agli sviluppatori Life365 che devono notificare a
Salesforce la creazione o la modifica di un customer, prodotto o ordine già
presente in Life365. Per i prodotti è disponibile anche la disattivazione
della rappresentazione Salesforce; per gli ordini la marcatura remota come
eliminati, senza cancellazione fisica dello storico.

Il chiamante fornisce soltanto l'ID Life365 e un token di autenticazione
Life365. Questa API legge il database, costruisce il payload condiviso,
gestisce l'autenticazione verso Salesforce e attende la risposta remota.
Non occorre costruire il DTO, generare un `eventId` o ottenere direttamente
un access token Salesforce.

La direzione descritta qui è **Life365 → Salesforce**.
[romi.md](romi.md) documenta invece la direzione **Salesforce → Life365**.

## Ambienti disponibili

| Ambiente Life365 | URL base | Dati letti |
|---|---|---|
| Produzione | `https://b2b.life365.eu/public-api` | Database configurato per l'applicazione di produzione |
| Sandbox | `https://b2b.life365.eu/public-api/sandbox` | Solo il database locale al server `life365_sandbox` |

**Entrambi gli ambienti inviano richieste reali alla stessa API Salesforce
configurata, attualmente la sua sandbox UAT.** Il termine "produzione" nella
tabella identifica l'ambiente e i dati Life365, non una diversa destinazione
Salesforce. La destinazione UAT attuale è:

```text
https://java-nosoftware-4269--partial.sandbox.my.salesforce.com
```

La sandbox Life365 non è quindi una simulazione dell'invio. Customer con lo
stesso ID nei due database possono identificare lo stesso Account Salesforce;
analogamente, prodotti con lo stesso ID possono identificare lo stesso Product2.
Lo stesso vale per gli ordini: un ID condiviso identifica lo stesso Order remoto.
Una chiamata dalla sandbox può sovrascrivere quel record remoto. Scegliere
consapevolmente i dati da esportare e non inviare dati sensibili per errore.

Il prefisso `/sandbox` non viene aggiunto automaticamente. Se un ID manca nel
database sandbox, non viene cercato nel database di produzione.

Gli esempi seguenti utilizzano la sandbox sul dominio di produzione e
richiedono `curl` e `jq`. Per eseguire le stesse chiamate su un server locale,
usare `API_URL='http://127.0.0.1:8000/sandbox'` e autenticarsi su quel server.

## Autenticazione

Le operazioni di sincronizzazione richiedono un utente Life365 con ruolo
**admin**, autenticato con `principal_type: "user"`. Il token da inviare è il
JWT restituito da questa API, non il token OAuth di Salesforce.

### Sandbox

Il database di esempio include l'utente `salesforce`, password `romi`, con
ruolo admin. Sono credenziali sintetiche della sandbox: non funzionano per
autenticarsi nell'ambiente Life365 di produzione e non sono credenziali OAuth
Salesforce.

```bash
API_URL='https://b2b.life365.eu/public-api/sandbox'

AUTH_TOKEN=$(curl --fail-with-body -sS -X POST "$API_URL/auth/login" \
  -H 'Content-Type: application/json' \
  --data-raw '{
    "username": "salesforce",
    "password": "romi",
    "principal_type": "user"
  }' | jq -er '.access_token')
```

Il login riuscito restituisce HTTP `200`. Oltre ad `access_token`, la risposta
contiene `token_type`, `expires_at` e `user`. Usare `expires_at` per conoscere
la scadenza del JWT e non registrare il token nei log.

### Produzione Life365

Per leggere ed esportare dati reali Life365, cambiare URL base e autenticarsi
di nuovo con un account admin di produzione. Sostituire i due placeholder;
le credenziali reali devono essere fornite separatamente e non salvate nel
repository.

```bash
PRODUCTION_API_URL='https://b2b.life365.eu/public-api'

PRODUCTION_AUTH_TOKEN=$(curl --fail-with-body -sS -X POST "$PRODUCTION_API_URL/auth/login" \
  -H 'Content-Type: application/json' \
  --data-raw '{
    "username": "<USERNAME_ADMIN_LIFE365>",
    "password": "<PASSWORD_ADMIN_LIFE365>",
    "principal_type": "user"
  }' | jq -er '.access_token')
```

Un JWT sandbox non funziona sugli endpoint di produzione e viceversa:
la risposta è HTTP `401`. Quando si cambia ambiente, eseguire nuovamente
il login relativo a quell'ambiente.

Le variabili `PRODUCTION_API_URL` e `PRODUCTION_AUTH_TOKEN` sono separate:
questo esempio non cambia `API_URL` e `AUTH_TOKEN` della sandbox, usati nei
comandi successivi. Per adattare quei comandi alla produzione, usare le due
variabili di produzione e scegliere gli ID reali appropriati, non quelli del
campione sandbox. Controllare sempre URL, token e ID prima dell'invio.

## Sincronizzazione dei customer

| Operazione | Metodo e percorso | Successo |
|---|---|---|
| Notificare la creazione | `POST /integrations/salesforce/customers/{customer_id}` | HTTP 201 |
| Inviare i dati aggiornati | `PUT /integrations/salesforce/customers/{customer_id}` | HTTP 200 |

`customer_id` è l'ID del customer nel database Life365 selezionato. Non è
l'ID dell'Account Salesforce. Il customer deve già esistere ed essere stato
salvato: la POST crea la sua rappresentazione in Salesforce, non un nuovo
customer in Life365. Nessuna delle due operazioni modifica il customer locale.

Le chiamate non accettano un body. Per scegliere un customer di esempio,
si può prima consultare l'elenco nell'ambiente selezionato:

```bash
curl --fail-with-body -sS "$API_URL/customers?limit=10&offset=0" \
  -H "Authorization: Bearer $AUTH_TOKEN" | jq
```

Negli esempi usiamo il customer sandbox `3`. Verificare che il suo utilizzo
sia appropriato anche sul lato Salesforce, oppure sostituirlo con un altro ID.
La presenza nel campione non implica che il record remoto sia ancora assente:
per riallineare un customer già sincronizzato usare PUT.

### Notificare la creazione

```bash
CUSTOMER_ID=3

curl --fail-with-body -sS -X POST \
  "$API_URL/integrations/salesforce/customers/$CUSTOMER_ID" \
  -H "Authorization: Bearer $AUTH_TOKEN" | jq
```

### Inviare un aggiornamento

Dopo aver modificato e completato il commit del customer in Life365:

```bash
curl --fail-with-body -sS -X PUT \
  "$API_URL/integrations/salesforce/customers/$CUSTOMER_ID" \
  -H "Authorization: Bearer $AUTH_TOKEN" | jq
```

La PUT invia **tutti i campi condivisi**, non soltanto quelli modificati.
I valori esportati da Life365 prevalgono su quelli Salesforce, comprese le
cancellazioni esplicite tramite `null` e gli array vuoti, secondo le regole
di mapping e normalizzazione già implementate.

Entrambe le operazioni restituiscono questa struttura:

```json
{
  "success": true,
  "eventId": "<UUID_EVENTO_GENERATO_DALL_API>",
  "referenceId": 3,
  "accountId": "<ID_ACCOUNT_SALESFORCE>"
}
```

`referenceId` è l'ID Life365; `accountId` è l'ID dell'Account Salesforce.
Non è previsto un endpoint DELETE per i customer.

## Sincronizzazione dei prodotti

| Operazione | Metodo e percorso | Successo |
|---|---|---|
| Notificare la creazione | `POST /integrations/salesforce/products/{product_id}` | HTTP 201 |
| Inviare i dati aggiornati | `PUT /integrations/salesforce/products/{product_id}` | HTTP 200 |
| Disattivare in Salesforce | `DELETE /integrations/salesforce/products/{product_id}` | HTTP 200 |

`product_id` identifica il prodotto di catalogo, cioè `products.id`. **Non
usare `product_stocks.id`**, l'ISIN/SKU, un EAN o l'ID Product2 Salesforce.
Il prodotto deve esistere nel database Life365 selezionato. Anche queste
chiamate non accettano un body e non modificano dati Life365.

Per consultare il catalogo dell'ambiente selezionato:

```bash
curl --fail-with-body -sS "$API_URL/products?limit=10&offset=0" \
  -H "Authorization: Bearer $AUTH_TOKEN" | jq
```

Il campione sandbox include il prodotto `101`, codice `SAMLTD116L`.
Come per i customer, verificare la corrispondenza remota prima di inviare
le chiamate di esempio.

### Notificare la creazione

```bash
PRODUCT_ID=101

curl --fail-with-body -sS -X POST \
  "$API_URL/integrations/salesforce/products/$PRODUCT_ID" \
  -H "Authorization: Bearer $AUTH_TOKEN" | jq
```

### Inviare un aggiornamento

```bash
curl --fail-with-body -sS -X PUT \
  "$API_URL/integrations/salesforce/products/$PRODUCT_ID" \
  -H "Authorization: Bearer $AUTH_TOKEN" | jq
```

POST e PUT inviano il DTO minimale completo: SKU, nome, descrizione, marca,
EAN, categoria, URL prodotto, URL immagine e stato di attivazione. Il servizio
sceglie automaticamente il primo EAN valido e la categoria più specifica
assegnata. Non occorre risolvere questi dati nel chiamante.

Anche per i prodotti la PUT non è una patch: invia tutti i campi condivisi,
inclusi i valori `null`. I valori Life365 prevalgono sui corrispondenti campi
Salesforce. Il contratto Salesforce tratta create e update prodotto come
upsert: se il record remoto manca, può essere creato anche da un update.

### Disattivare il prodotto in Salesforce

```bash
curl --fail-with-body -sS -X DELETE \
  "$API_URL/integrations/salesforce/products/$PRODUCT_ID" \
  -H "Authorization: Bearer $AUTH_TOKEN" | jq
```

Salesforce imposta `IsActive=false`, conservando il prodotto per lo storico
degli ordini. Il prodotto Life365 e il suo campo `enabled` restano invariati.
La disattivazione richiede soltanto l'esistenza del prodotto locale: dati
descrittivi incompleti non la impediscono.

Per riattivare la rappresentazione Salesforce, verificare che il prodotto
abbia `enabled=true` in Life365 e richiamare PUT. Un successivo aggiornamento
da Life365 può quindi riattivare un prodotto precedentemente disattivato
soltanto sul lato Salesforce.

Tutte e tre le operazioni restituiscono questa struttura:

```json
{
  "success": true,
  "eventId": "<UUID_EVENTO_GENERATO_DALL_API>",
  "referenceId": 101,
  "recordId": "<ID_PRODUCT2_SALESFORCE>"
}
```

`referenceId` è l'ID prodotto Life365; `recordId` è l'ID Product2 Salesforce.
Il campo remoto si chiama quindi `recordId`, non `accountId` come per i customer.

## Sincronizzazione degli ordini

| Operazione | Metodo e percorso | Successo |
|---|---|---|
| Notificare la creazione | `POST /integrations/salesforce/orders/{order_id}` | HTTP 201 |
| Inviare i dati aggiornati | `PUT /integrations/salesforce/orders/{order_id}` | HTTP 200 |
| Marcare come eliminato in Salesforce | `DELETE /integrations/salesforce/orders/{order_id}` | HTTP 200 |

`order_id` è `orders.id` nel database Life365 selezionato, non il numero della
fattura o l'ID Salesforce. L'ordine deve già essere salvato. Le tre chiamate
richiedono il JWT di un admin Life365, non accettano un body e non modificano
ordini, righe o storico eventi nel database locale.

**Prima sincronizzare il customer dell'ordine.** Salesforce richiede che
`customerReferenceId` identifichi un Account già sincronizzato; altrimenti
risponde con un errore esposto come HTTP `404`. Non vengono esportati customer
automaticamente. Secondo il contratto ROMI, prodotti mancanti possono invece
essere creati da Salesforce come provvisori e completati tramite l'API prodotti.

Per individuare un ordine e il suo customer:

```bash
curl --fail-with-body -sS "$API_URL/orders?limit=10&offset=0" \
  -H "Authorization: Bearer $AUTH_TOKEN" | jq
```

Il campione iniziale contiene l'ordine `1001`, associato al customer `4`.
Verificare sempre la corrispondenza Salesforce prima di inviare questi ID.
Se il customer non è ancora sincronizzato, usare prima la sua POST:

```bash
ORDER_ID=1001
ORDER_CUSTOMER_ID=4

curl --fail-with-body -sS -X POST \
  "$API_URL/integrations/salesforce/customers/$ORDER_CUSTOMER_ID" \
  -H "Authorization: Bearer $AUTH_TOKEN" | jq

curl --fail-with-body -sS -X POST \
  "$API_URL/integrations/salesforce/orders/$ORDER_ID" \
  -H "Authorization: Bearer $AUTH_TOKEN" | jq
```

Dopo aver completato una modifica dell'ordine nel database Life365, inviare
nuovamente tutti i dati condivisi con PUT:

```bash
curl --fail-with-body -sS -X PUT \
  "$API_URL/integrations/salesforce/orders/$ORDER_ID" \
  -H "Authorization: Bearer $AUTH_TOKEN" | jq
```

La PUT invia anche tutte le righe: Salesforce sostituisce l'elenco remoto,
non applica una patch. I valori Life365 prevalgono. Create e update sono
documentati da ROMI come upsert, quindi un update può creare l'ordine remoto
se manca e il customer è già sincronizzato.

Per marcare soltanto la rappresentazione Salesforce come eliminata:

```bash
curl --fail-with-body -sS -X DELETE \
  "$API_URL/integrations/salesforce/orders/$ORDER_ID" \
  -H "Authorization: Bearer $AUTH_TOKEN" | jq
```

Salesforce imposta `Life365_Status__c=deleted` e conserva lo storico. Lo stato
logistico e tutte le righe Life365 restano invariati. La DELETE richiede solo
l'esistenza locale, anche quando i dati descrittivi non sono esportabili.

La risposta delle tre operazioni ha questa forma:

```json
{
  "success": true,
  "eventId": "<UUID_EVENTO_GENERATO_DALL_API>",
  "referenceId": 1001,
  "recordId": "<ID_ORDER_SALESFORCE>"
}
```

### Dati economici e stato

- `status` contiene esattamente `orders.logistic_state`, senza conversione in
  `pending` o `accepted`. Lo stato standard Salesforce resta gestito da ROMI.
- Le route di export accettano qualsiasi stato logistico non vuoto e nessun
  intervallo temporale. L'elenco GET `/orders` mantiene invece il filtro
  esistente su `CONFIRMED`, `DELIVERED` e `UNDELIVERABLE`.
- Ogni riga usa il vero `products.id`, risolto attraverso `product_stocks`,
  lo SKU di catalogo e la descrizione storica di `order_details`.
- Gli sconti rimangono righe separate: un prezzo Life365 di `-10.00` diventa
  `unitPrice: "10.00"` e `lineTotal: "-10.00"` per quantità `1`. Non vengono
  riapplicate le percentuali di sconto già contabilizzate nelle righe.
- Quando `delivery_cost` è positivo, viene aggiunta una riga quantità `1`,
  descrizione «Spese di spedizione», SKU `ADMGST` e ID risolto nel database
  selezionato. È la convenzione già usata dal portale Life365. Un prodotto
  mancante o ambiguo causa HTTP `422`: nessun ID è inventato o cercato altrove.
- `net` è la somma delle righe con il loro segno, più spedizione; `gross` è
  `orders.total`; `tax` è `gross - net`. Sono imposte complessive, non una
  ricostruzione dell'aliquota IVA. Non si applicano aliquote attuali né si
  aggiunge di nuovo `tax2`. Gli importi sono stringhe decimali a due cifre.
- Un bollo già presente come normale riga rimane una riga. Un `stamp_duty`
  di testata diverso da zero viene invece rifiutato con HTTP `422`, perché
  non è chiarita la sua inclusione nel lordo storico. Non viene sommato o ignorato.
- Fattura e indirizzo provengono dai dati salvati nell'ordine, non dal customer
  attuale. Senza fattura si invia `null`; non viene inventato un URL del PDF.
  In assenza completa dell'indirizzo di consegna si usa quello di fatturazione
  dell'ordine, oppure `null` se anch'esso assente. Un indirizzo parziale o una
  regione non risolvibile vengono rifiutati.

Il campione iniziale ha importi semplificati e imposte risultanti pari a zero:
non è un esempio di calcolo fiscale reale. L'inizializzazione aggiunge un
prodotto di servizio sintetico `ADMGST` con ID locale generato. Per una sandbox
già avviata prima di questa modifica, applicare lo script additivo descritto
nella [guida tecnica ordini](docs/integrations/SALESFORCE_ORDER_EXPORT.md), senza
riavviare PostgreSQL o perdere i dati temporanei.

## Quando richiamare la sincronizzazione

1. Creare o modificare il record attraverso gli strumenti Life365 esistenti.
2. Completare il commit della transazione nel database Life365.
3. Richiamare POST oppure PUT dell'API di sincronizzazione, passando l'ID locale.
4. Attendere la risposta e gestire esplicitamente un eventuale errore.

Non chiamare la sincronizzazione prima del commit: questa API legge tramite
una propria connessione e non può vedere le modifiche ancora non confermate.
La lettura del database e la successiva chiamata Salesforce non costituiscono
una transazione distribuita. Un errore di invio **non annulla** una modifica
già salvata in Life365.

La sincronizzazione non parte automaticamente dal solo salvataggio del record:
va richiamata esplicitamente nei punti opportuni dell'applicazione.
Non usare questi endpoint per modificare il database Life365 e non inviare
il DTO o un evento nel body, neppure per un aggiornamento parziale.

Inviare una chiamata alla volta per lo stesso customer, prodotto o ordine e attendere
il successo prima della successiva. Risorse diverse possono essere
sincronizzate contemporaneamente.

## Errori e gestione dei tentativi

| HTTP | Significato e comportamento del chiamante |
|---|---|
| 201 su POST / 200 su PUT e DELETE | Salesforce ha confermato l'operazione e la risposta è coerente con l'evento inviato |
| 401 | JWT Life365 assente, scaduto o non valido per questo ambiente; autenticarsi nuovamente |
| 403 | Utente Life365 senza ruolo admin; verificare l'account utilizzato |
| 404 | Record assente nel database Life365 selezionato; per gli ordini anche customer Salesforce non sincronizzato; per DELETE prodotto/ordine può mancare il record remoto |
| 409 | Conflitto segnalato da Salesforce; verificare la corrispondenza remota e i vincoli di univocità |
| 422 | ID non valido, body presente o dati Life365 non rappresentabili nel DTO; correggere la richiesta o i dati sorgente |
| 502 | Errore di autenticazione Salesforce, invio o risposta remota non valida; richiedere una verifica tecnica |
| 503 | Database non disponibile o configurazione Salesforce non valida; richiedere una verifica tecnica |
| 504 | Timeout verso Salesforce; l'esito dell'invio può essere incerto |

Un'operazione viene dichiarata riuscita soltanto dopo la risposta remota e
la verifica di `success`, `eventId`, `referenceId` e identificativo Salesforce.
Questo non equivale a una verifica tramite lettura di ogni singolo campo
salvato in Salesforce.

### Token Salesforce

Il chiamante non deve ottenere o rinnovare il token OAuth Salesforce:
il servizio lo conserva in memoria e lo riutilizza. Se Salesforce rifiuta
l'invio con HTTP `401`, il servizio rinnova il token e ritenta **una sola volta**,
mantenendo identici `eventId`, timestamp e payload.

Questo HTTP `401` remoto è distinto dal `401` restituito per un JWT Life365
non valido. Se Salesforce continua a rifiutare il token dopo il tentativo
previsto, il chiamante riceve un errore `502`.

### Timeout e chiamate ripetute

In questa direzione non esistono una coda, uno storico persistente degli
eventi in uscita o un meccanismo generale di retry automatico. Ogni nuova
chiamata del client genera un **nuovo `eventId`** e legge i dati Life365 attuali.
Non è quindi un retry idempotente della precedente chiamata.

Dopo un timeout o una connessione interrotta, Salesforce potrebbe aver già
applicato l'operazione. Non ripetere automaticamente la chiamata senza prima
verificare l'esito remoto. Conservare, quando disponibili, `eventId`,
`referenceId` e identificativo Salesforce della risposta; in caso di errore
comunicare anche metodo, ID Life365, orario, stato HTTP e messaggio ricevuto
per consentire la ricerca nei log.

**Non applicare a questi endpoint le regole di retry di `romi.md`**: quelle
riguardano gli eventi ricevuti da Salesforce, con un `eventId` fornito dal
chiamante e uno storico persistente. Qui il chiamante non fornisce un evento
e non può riutilizzare direttamente l'ID generato dalla chiamata precedente.

## Logout e durata della sandbox

Per revocare il JWT Life365 della sessione corrente:

```bash
curl --fail-with-body -sS -X POST "$API_URL/auth/logout" \
  -H "Authorization: Bearer $AUTH_TOKEN" | jq

unset AUTH_TOKEN
```

Per chiudere la sessione di produzione creata nell'esempio separato, usare
invece `PRODUCTION_API_URL` e `PRODUCTION_AUTH_TOKEN` per la stessa chiamata,
poi rimuovere il token dalla variabile.

Le sessioni sandbox sono separate da quelle dell'applicazione normale e sono
in memoria: dopo un riavvio dell'API occorre autenticarsi nuovamente.

Il PostgreSQL locale usa memoria temporanea. Fermare il suo container elimina
i dati sandbox; al successivo avvio viene ricaricato il campione iniziale.
Questo reset **non elimina né ripristina** i record già inviati a Salesforce:
prima di ripetere gli esempi controllare nuovamente le corrispondenze remote.

## Documentazione interattiva e approfondimenti

- [Swagger di produzione](https://b2b.life365.eu/public-api/docs).
- [Swagger della sandbox](https://b2b.life365.eu/public-api/sandbox/docs).
- [Guida tecnica di esportazione customer](docs/integrations/SALESFORCE_CUSTOMER_EXPORT.md).
- [Guida tecnica di esportazione prodotti](docs/integrations/SALESFORCE_PRODUCT_EXPORT.md).
- [Guida tecnica di esportazione ordini](docs/integrations/SALESFORCE_ORDER_EXPORT.md).
- [Configurazione e isolamento della sandbox](docs/SANDBOX_API.md).
- [Guida ROMI per la direzione Salesforce verso Life365](romi.md).

Da Swagger, eseguire il login nell'ambiente scelto, copiare `access_token`
e inserirlo tramite **Authorize**. Le chiamate di sincronizzazione eseguite
da Swagger inviano realmente i dati a Salesforce, anche nella sandbox.
