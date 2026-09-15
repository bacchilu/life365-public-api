# Salesforce Customer Event Contract, Version 1

## Status And Scope

This document is the authoritative version 1 contract for customer events sent
from Salesforce to Life365 through:

```http
POST /integrations/salesforce/events
```

The canonical full create example is stored in
[`tests/fixtures/integrations/salesforce/customer-created-v1.json`](../../tests/fixtures/integrations/salesforce/customer-created-v1.json).
It contains synthetic data and can be used in API and contract tests.

The contract uses camelCase JSON property names. A breaking contract change
requires a new `schemaVersion`.

## Event Envelope

Every request is one customer event.

| Property | JSON type | Required | Description |
|---|---|---|---|
| `schemaVersion` | `number` | Yes | Contract version. The only version defined here is integer `1`. |
| `eventId` | `string` | Yes | UUID that identifies one event and supports idempotent retries. |
| `occurredAt` | `string` | Yes | RFC 3339 timestamp with a UTC offset. |
| `resourceVersion` | `number` | Yes | Positive integer sequence for this customer resource. |
| `eventType` | `string` | Yes | One of `customer.created` or `customer.updated`. |
| `referenceId` | `number` | By event | Positive integer Life365 customer ID. |
| `data` | `object` | By event | Complete customer data or a customer patch. |

The valid property combinations are:

| `eventType` | `referenceId` | `data` |
|---|---|---|
| `customer.created` | Must be absent | Required and complete |
| `customer.updated` | Required | Required patch; it can be an empty object |

For `customer.created`, Salesforce must omit `referenceId`. Life365 allocates
the customer ID and returns it in the response. A create event that supplies a
`referenceId` is invalid; retries use the original `eventId` rather than a
caller-selected customer ID.

For `customer.updated`, `referenceId` identifies the existing Life365
customer. Life365 returns a missing-resource error when that customer does not
exist and does not create it implicitly.

Customer deletion is outside the version 1 synchronization scope. Version 1
does not accept `customer.deleted`; deletion can be designed in a future
contract version without implying physical or cascading database deletion.

## Event Identity And Ordering

`eventId` provides idempotency. Replaying the same complete event with the same
`eventId` returns the stored result without applying another mutation. Reusing
an `eventId` with different event content is a conflict.

`resourceVersion` provides ordering independently of `occurredAt`:

- A create event uses `resourceVersion: 1`.
- An update must use the previous accepted version plus one.
- A lower or equal version is stale and is rejected.
- A version greater than the next expected value has a gap and is rejected.
- A valid replay identified by `eventId` returns its stored result before the
  version check causes another mutation.

`occurredAt` remains audit information. Clock differences, equal timestamps,
and delayed delivery make it unsuitable as the ordering key.

## Create Data

The `data` property of a `customer.created` event contains a complete
`IntegrationCustomerData` object. Every property listed below is required in a
create event. A property whose type includes `null` must still be present, but
its value can be `null`.

### `credentials`

| Property | JSON type | Nullable | Description |
|---|---|---|---|
| `login` | `string` | No | Customer login. Life365 trims outer whitespace and enforces case-insensitive uniqueness. |
| `password` | `string` | No | Customer password value accepted by the integration. It is sensitive and must not be logged. |

### `company`

| Property | JSON type | Nullable | Description |
|---|---|---|---|
| `name` | `string` | No | Customer company or business name. |
| `website` | `string` | Yes | Company website URL. |
| `primaryPhone` | `string` | Yes | Main company telephone number. |
| `secondaryPhone` | `string` | Yes | Additional company telephone number. |

### `primaryContact`

| Property | JSON type | Nullable | Description |
|---|---|---|---|
| `fullName` | `string` | No | Full name of the main customer contact. |
| `email` | `string` | No | Main customer email address. |
| `additionalEmails` | `IntegrationAdditionalEmail[]` | No | Complete list of additional email records. |
| `certifiedEmail` | `string` | Yes | Certified email address, such as an Italian PEC address. |
| `preferredLanguage` | `string` | Yes | Preferred language code or value. |

### `billingAddress`

`billingAddress` is a required `IntegrationAddress` object.

### `delivery`

| Property | JSON type | Nullable | Description |
|---|---|---|---|
| `businessName` | `string` | Yes | Business name used for delivery. |
| `contactName` | `string` | Yes | Delivery contact name. |
| `phone` | `string` | Yes | Delivery telephone number. |
| `address` | `IntegrationAddress` | Yes | Delivery address. |

### `taxProfile`

| Property | JSON type | Nullable | Description |
|---|---|---|---|
| `fiscalCode` | `string` | Yes | Customer fiscal or tax code. |
| `vatCountryCode` | `string` | Yes | Country code associated with the VAT number. |
| `vatNumber` | `string` | Yes | VAT registration number. |
| `viesValidated` | `boolean` | No | Whether the VAT data passed VIES validation. |
| `fiscalAgentCode` | `string` | Yes | Fiscal or accounting agent code. |
| `secondaryTaxValue` | decimal `string` | Yes | Exact secondary tax value. |

### `communicationPreferences`

| Property | JSON type | Nullable | Description |
|---|---|---|---|
| `newsletter` | `boolean` | Yes | Newsletter subscription preference. |
| `privacyRegistered` | `boolean` | Yes | Privacy acceptance or registration state. |
| `rulesRegistered` | `boolean` | Yes | Terms or registration-rules acceptance state. |

### `registration`

| Property | JSON type | Nullable | Description |
|---|---|---|---|
| `registeredAt` | RFC 3339 `string` | Yes | Customer registration date and time. |
| `verified` | `boolean` | Yes | Customer verification state. |
| `lastLoginAt` | RFC 3339 `string` | Yes | Date and time of the latest login. |

`registrationIp` is intentionally not part of the integration payload. When
Life365 processes a `customer.created` event, it obtains the client IPv4
address from the trusted HTTP request context and stores it in
`customers.registration_ip`. A later `customer.updated` event does not change
that value.

When the API runs behind a reverse proxy, Life365 must accept a forwarded
client address only from a configured trusted proxy. It must validate that the
selected address is IPv4 before it writes the value. Arbitrary forwarded
headers supplied by an untrusted client must not determine the stored address.

### `commercial`

| Property | JSON type | Nullable | Description |
|---|---|---|---|
| `preferredCategories` | `IntegrationCategory[]` | No | Complete list of preferred product categories. |
| `salesChannel` | `IntegrationSalesChannel` | Yes | Assigned sales channel. |
| `assignedAgent` | `IntegrationAgent` | Yes | Assigned Life365 commercial agent. `null` delegates assignment to Life365. |
| `paymentAgreement` | `string` | Yes | Text that describes the payment agreement. |
| `preferredPaymentTypeCode` | `string` | Yes | Shared payment type code. |
| `paymentDays` | `number` | Yes | Integer number of payment days. |
| `paymentDaysEndOfMonth` | `number` | Yes | Integer end-of-month payment adjustment. |
| `creditGranted` | decimal `string` | Yes | Exact granted credit amount. |
| `creditValue` | decimal `string` | Yes | Exact current customer credit value. |

### `banking`

| Property | JSON type | Nullable | Description |
|---|---|---|---|
| `abi` | `string` | Yes | Italian bank ABI code. |
| `cab` | `string` | Yes | Italian bank branch CAB code. |
| `iban` | `string` | Yes | Customer bank account IBAN. |

### `shop`

| Property | JSON type | Nullable | Description |
|---|---|---|---|
| `latitude` | `number` | Yes | Shop geographic latitude. |
| `longitude` | `number` | Yes | Shop geographic longitude. |
| `groups` | `IntegrationShopGroup[]` | No | Complete list of assigned shop groups. |

### `operationalSettings`

| Property | JSON type | Nullable | Description |
|---|---|---|---|
| `disableBoxDiscount` | `boolean` | No | Disables complete-box discounts. |
| `disableQuantityDelivery` | `boolean` | Yes | Disables quantity-related delivery behavior. |
| `prepaidReturns` | `boolean` | Yes | Indicates whether return shipments are prepaid. |
| `disableSaleLimit` | `boolean` | Yes | Disables sale-limit enforcement. |

### `notes`

| Property | JSON type | Nullable | Description |
|---|---|---|---|
| `items` | `IntegrationCustomerNote[]` | No | Complete list of structured customer notes. |
| `administrativeNote` | `string` | Yes | Internal administrative note. |

`openCount` is intentionally not part of the integration payload. Life365
derives `customers.notes_open` from the number of items whose `open` value is
`true`. A create derives the value from the complete `items` array. An update
recalculates it only when `notes.items` is supplied.

### `extensions`

| Property | JSON type | Nullable | Description |
|---|---|---|---|
| `parameters` | JSON object | Yes | Customer-specific configuration values outside the stable contract. |
| `extraData` | JSON object | Yes | Additional customer attributes outside the stable contract. |

## Shared Nested Objects

### `IntegrationAdditionalEmail`

| Property | JSON type | Nullable | Description |
|---|---|---|---|
| `email` | `string` | No | Additional email address. |
| `commercial` | `boolean` | No | Whether the address accepts commercial communication. |
| `marketing` | `boolean` | No | Whether the address accepts marketing communication. |
| `skype` | `string` | Yes | Skype identifier associated with the address. |

### `IntegrationAddress`

| Property | JSON type | Nullable | Description |
|---|---|---|---|
| `street` | `string` | No | Street and building information. |
| `city` | `string` | No | City name. |
| `postalCode` | `string` | Yes | Postal or ZIP code. |
| `countryCode` | `string` | No | Uppercase ISO 3166-1 alpha-2 country code. |
| `regionName` | `string` | No | Exact Life365 region name associated with `countryCode`. |

Salesforce must populate `regionName` with a value from the enabled Life365
region catalog supplied for the selected country. The pair
`(countryCode, regionName)` identifies one Life365 region. For example:

```json
{
  "street": "Via Roma 10",
  "city": "Forli",
  "postalCode": "47121",
  "countryCode": "IT",
  "regionName": "Forlì-Cesena"
}
```

The region name is a controlled integration value, not unrestricted address
text. Salesforce can store it in a dedicated controlled field or translate
its internal state or province value through an explicit mapping. It must not
assume that a standard Salesforce state value is a valid Life365 region name.
Life365 includes specialized values such as `Venezia - laguna` and
`Roma - fuori GRA` that do not necessarily correspond to standard political
subdivisions.

The receiver matches both values exactly against an enabled Life365 region.
Disabled historical rows are not valid catalog options. An unknown country and
region pair is a mapping error; the receiver must not use fuzzy matching or
silently select another region.

### `IntegrationAgent`

| Property | JSON type | Nullable | Description |
|---|---|---|---|
| `referenceId` | `number` | No | Positive integer Life365 `agents.id`; this is the authoritative agent identity. |
| `userLogin` | `string` | No | Current Life365 agent login supplied as descriptive data. |
| `name` | `string` | No | Current agent display name supplied as descriptive data. |
| `email` | `string` | No | Current agent email address supplied as descriptive data. |
| `phone` | `string` | Yes | Current agent telephone number supplied as descriptive data. |

Life365 resolves an incoming agent using only `referenceId`. The other fields
are snapshots that let Salesforce display useful agent information. They do
not participate in identity matching, and an inbound customer event must not
use them to update the `agents` table. Life365 populates them from the current
agent row when it sends customer data to Salesforce.

The `assignedAgent` property is required in `customer.created`, but its value
can be `null`. A complete object selects the agent identified by `referenceId`.
`null` delegates the assignment to Life365, which applies its configured
fallback-agent policy.

In a `customer.updated` patch, omitting `assignedAgent` leaves the assignment
unchanged. A complete object changes it to the referenced agent, while `null`
asks Life365 to apply its fallback-agent policy. A non-null object containing
an unknown `referenceId` is a mapping error and does not activate the fallback.

### `IntegrationCategory`

| Property | JSON type | Nullable | Description |
|---|---|---|---|
| `code` | `string` | No | Stable integration category code. |
| `label` | `string` | No | Human-readable category label. |

### `IntegrationSalesChannel`

| Property | JSON type | Nullable | Description |
|---|---|---|---|
| `code` | `string` | No | Stable integration sales-channel code. |
| `label` | `string` | No | Human-readable sales-channel label. |

### `IntegrationShopGroup`

| Property | JSON type | Nullable | Description |
|---|---|---|---|
| `code` | `string` | No | Stable integration shop-group code. |
| `label` | `string` | No | Human-readable shop-group label. |

### `IntegrationCustomerNote`

| Property | JSON type | Nullable | Description |
|---|---|---|---|
| `occurredAt` | RFC 3339 `string` | No | Date and time associated with the note. |
| `text` | `string` | No | Note content. |
| `open` | `boolean` | No | Whether the note is open. |

Category, sales-channel, and shop-group catalogs are integration reference
data. Their `code` values are stable identifiers and their `label` values are
descriptive. Version 1 does not define these catalogs as closed JSON enums, so
a receiver must report an unsupported code as a mapping error instead of
rejecting the event as structurally invalid.

Every non-null reference must resolve exactly one supported Life365 value.
Unknown regions, agents, categories, sales channels, payment types, and shop
groups reject the complete event. The implementation must not guess an ID,
select the first match, or apply a fallback unless this contract explicitly
defines one. `assignedAgent: null` is the explicit agent-fallback case.

## Update Semantics

The `data` property of a `customer.updated` event is a recursive partial form
of `IntegrationCustomerData`:

- A missing property leaves the stored value unchanged.
- A property present with a non-null value sets that value.
- A property present with `null` requests that the value be cleared.
- A nested object contains only the nested properties to change.
- An array present in a patch replaces the complete stored array.
- An empty array clears the stored array.
- An empty `data` object makes no customer changes.

Examples:

```json
{}
```

The example above makes no change.

```json
{
  "company": {
    "website": null
  }
}
```

The example above clears only `company.website`.

```json
{
  "company": {
    "name": "ACME Italia SRL"
  }
}
```

The example above changes only `company.name`.

JSON has no `undefined` value. In generated client types, an optional property
represents an omitted property; `null` represents an explicit clear request.
Whether a database constraint permits a specific clear request is part of the
Life365 mapping rules and can produce a validation error.

A field or section whose create definition is not nullable cannot be cleared
by an update. This includes credentials, required company and contact values,
the billing address, address country and region values, required booleans, and
required arrays. Supplying `null` for one of these values rejects the complete
event. Empty arrays remain the valid way to clear required collection values.
Fields explicitly marked nullable can be cleared unless a field-specific rule,
such as the fallback rule for `assignedAgent`, defines another meaning.

## Extension Patch Rules

`extensions.parameters` and `extensions.extraData` use recursive JSON Merge
Patch semantics during updates:

- An omitted extension property remains unchanged.
- A top-level `null` stores SQL `NULL` for that extension object.
- A supplied object merges recursively with the existing JSON object.
- An omitted nested key remains unchanged.
- A nested key set to `null` is removed.
- A supplied array replaces the complete existing array at that key.

The implementation must preserve unknown keys that the patch does not mention.

## Scalar Rules

- UUID values use the standard hyphenated string representation.
- Date-time values use RFC 3339 and include `Z` or an explicit UTC offset.
- Customer and agent `referenceId` values, `resourceVersion`, `paymentDays`,
  and `paymentDaysEndOfMonth` are JSON integers. Reference identifiers and
  `resourceVersion` are positive.
- Financial and tax decimal values are JSON strings, such as `"10000.00"`, so
  JSON number conversion cannot lose decimal precision.
- Country codes use uppercase ISO 3166-1 alpha-2 values. Address region names
  use the exact controlled values supplied in the Life365 region catalog.
- Language values are strings. Their supported-code mapping is a Life365
  persistence concern and is not defined by this structural contract.
- Empty arrays are valid. Empty strings are values and are not equivalent to
  `null`.

## Response

A successful event returns:

```json
{
  "success": true,
  "eventId": "726c7c74-287d-44f2-b060-81fefa3d235d",
  "referenceId": 42
}
```

`eventId` identifies the accepted event. `referenceId` is the affected
Life365 customer ID, including the new ID allocated for a create event that
omitted it.

## Contract Boundaries

This contract describes integration data. It does not expose Salesforce
`Account` or `Contact` field names, and it does not require Salesforce to know
Life365 table relationships. The Life365 infrastructure adapter is responsible
for translating reference objects and values into local database identifiers.

The contract defines validation, conflict, idempotency, and ordering behavior.
The durable processed-event and resource-version storage required to enforce
those rules must be implemented before PostgreSQL writes are enabled.

The current database mapping audit and its remaining implementation
prerequisites are documented in
[`SALESFORCE_CUSTOMER_POSTGRESQL_MAPPING_V1.md`](SALESFORCE_CUSTOMER_POSTGRESQL_MAPPING_V1.md).
