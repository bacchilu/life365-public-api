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
| `eventType` | `string` | Yes | One of `customer.created`, `customer.updated`, or `customer.deleted`. |
| `referenceId` | `number` | By event | Positive integer Life365 customer ID. |
| `data` | `object` | By event | Complete customer data or a customer patch. |

The valid property combinations are:

| `eventType` | `referenceId` | `data` |
|---|---|---|
| `customer.created` | Optional | Required and complete |
| `customer.updated` | Required | Required patch; it can be an empty object |
| `customer.deleted` | Required | Must be absent |

For `customer.created`, Salesforce omits `referenceId` when the Life365
customer does not exist. Life365 returns the new customer ID in the response.
Salesforce can provide `referenceId` when the Life365 customer ID is already
known.

## Create Data

The `data` property of a `customer.created` event contains a complete
`IntegrationCustomerData` object. Every property listed below is required in a
create event. A property whose type includes `null` must still be present, but
its value can be `null`.

### `credentials`

| Property | JSON type | Nullable | Description |
|---|---|---|---|
| `login` | `string` | No | Customer login. |
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
| `registrationIp` | `string` | Yes | IP address used during registration. |
| `verified` | `boolean` | Yes | Customer verification state. |
| `lastLoginAt` | RFC 3339 `string` | Yes | Date and time of the latest login. |

### `commercial`

| Property | JSON type | Nullable | Description |
|---|---|---|---|
| `preferredCategories` | `IntegrationCategory[]` | No | Complete list of preferred product categories. |
| `salesChannel` | `IntegrationSalesChannel` | Yes | Assigned sales channel. |
| `assignedAgent` | `IntegrationAgent` | Yes | Assigned commercial agent. |
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
| `openCount` | `number` | No | Non-negative integer count of open notes. |
| `administrativeNote` | `string` | Yes | Internal administrative note. |

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
| `countryCode` | `string` | Yes | Country code used by the integration. |

### `IntegrationAgent`

| Property | JSON type | Nullable | Description |
|---|---|---|---|
| `name` | `string` | No | Agent display name. |
| `email` | `string` | No | Agent email address. |
| `phone` | `string` | Yes | Agent telephone number. |

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

## Scalar Rules

- UUID values use the standard hyphenated string representation.
- Date-time values use RFC 3339 and include `Z` or an explicit UTC offset.
- `referenceId`, `paymentDays`, `paymentDaysEndOfMonth`, and `openCount` are
  JSON integers. `referenceId` is positive and `openCount` is non-negative.
- Financial and tax decimal values are JSON strings, such as `"10000.00"`, so
  JSON number conversion cannot lose decimal precision.
- Country and language values are strings. Their supported-code mapping is a
  Life365 persistence concern and is not defined by this structural contract.
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

The contract does not yet specify the database mapping, conflict policy,
stale-event policy, or durable idempotency storage. Those rules must be defined
before PostgreSQL writes are enabled.
