# Salesforce Customer To PostgreSQL Mapping, Version 1

## Audit Scope

This document maps the version 1 Salesforce customer event contract to the
Life365 PostgreSQL database. The audit was performed on 2026-09-09 against the
`inkloud-portal` database with read-only transactions.

The contract is defined in
[`SALESFORCE_CUSTOMER_EVENTS_V1.md`](SALESFORCE_CUSTOMER_EVENTS_V1.md), and its
canonical create fixture is stored in
[`customer-created-v1.json`](../../tests/fixtures/integrations/salesforce/customer-created-v1.json).

The audit covered:

- `public.customers` columns, defaults, identity settings, constraints,
  indexes, triggers, and incoming foreign keys;
- `regions`, `countries`, `categories`, `agents`, `sales_channels`,
  `payment_types`, and `shop_groups`;
- observed JSON shapes, array reference values, timestamp behavior, login and
  credential behavior;
- existing customer create, update, authentication, and delete code in
  `life365-portal-api`.

No database data or schema was changed.

## Mapping Status

| Status | Meaning |
|---|---|
| Direct | One customer column with a defined conversion. |
| JSON | One JSONB customer column with a defined shape conversion. |
| Lookup | A value that must resolve to a related table identifier. |
| Descriptive | A snapshot supplied for the remote system; it does not select or update a local row. |
| Metadata | Synchronization processing data that is not stored in `customers`. |
| Transport | A stored value derived from the trusted HTTP request context rather than the event payload. |
| Problem | No safe mapping is possible from the current contract. |
| Decision | A plausible mapping needs a confirmed business rule. |

## Database Findings

`public.customers` has 60 active columns. It has no column comments and no
table triggers. Its primary key is an integer identity generated `BY DEFAULT`,
so create operations can let PostgreSQL allocate an ID or provide one.

The non-null columns are:

```text
id
login
pass
address_street
address_city
email
notes_open
disable_box_discount
vies
```

The table has a primary key on `id`, a unique constraint on `login`, and
foreign keys from `agent_id`, `region_id`, `delivery_region_id`,
`preferred_payment_type`, and `sales_channel_id`. All five foreign keys use
`ON DELETE RESTRICT`.

There are no check constraints for email syntax, country codes, numeric ranges,
coordinates, note counts, or array members. The application must validate
these values.

The login constraint is case-sensitive, while authentication uses
`LOWER(login)`. The database has 20,470 exact unique logins but only 20,457
case-folded unique logins. Thus, 13 case-insensitive duplicate pairs exist. New
synchronization code must reject a login that conflicts after case folding;
the existing duplicates need a separate cleanup or an explicit authentication
rule.

Twenty tables reference `customers`. Eighteen use `ON DELETE RESTRICT`,
including `orders`, `contracts`, `rmas`, `tickets`, and `customer_notes`.
`mail_queue` and `mkt_events` use `ON DELETE SET NULL`. Thus,
`customer.deleted` cannot reliably perform a physical delete for customers
with business history. The contract needs a logical-delete policy or an
explicit conflict response.

## Event Envelope Mapping

| Contract path | Database destination | Status | Conversion and validation |
|---|---|---|---|
| `schemaVersion` | None currently | Metadata | Accept integer `1`; store it in a future processed-event table. |
| `eventId` | None currently | Problem | Durable idempotency storage does not exist. Store the UUID before writes are enabled. |
| `occurredAt` | None currently | Decision | Store as `timestamptz` with processed-event metadata for audit and ordering. |
| `eventType` | Service dispatch | Metadata | Accept the three contract values and store the selected value with event metadata. |
| `referenceId` | `customers.id` | Direct | Positive integer. Omit on create to use the identity; require for update and delete. Explicit create IDs are technically supported. |
| `data` | Multiple destinations | Metadata | Complete for create, partial for update, and absent for delete. |

## Customer Data Mapping

### Credentials And Company

| Contract path | Database destination | Status | Conversion and validation |
|---|---|---|---|
| `credentials.login` | `customers.login` | Direct | Required, maximum 50 characters. Reject overlength and case-insensitive conflicts; do not truncate. |
| `credentials.password` | `customers.pass` | Direct | Required, maximum 50 characters. Never log it. Existing authentication compares the stored value directly and also accepts an MD5 of it as input. |
| `company.name` | `customers.business_name` | Direct | Maximum 120 characters. The contract requires it although the column is nullable. |
| `company.website` | `customers.website` | Direct | Nullable, maximum 100 characters. Validate URL syntax if URL semantics are required. |
| `company.primaryPhone` | `customers.phone` | Direct | Nullable, maximum 50 characters. |
| `company.secondaryPhone` | `customers.phone2` | Direct | Nullable, maximum 50 characters. |

The password profile contains no bcrypt-like, MD5-hex, or SHA1-hex stored
values. Stored lengths range from 1 to 35 characters. Together with the
authentication query, this indicates that current storage expects the original
password value. The mapper must preserve this behavior until credential
storage changes.

### Primary Contact And Additional Emails

| Contract path | Database destination | Status | Conversion and validation |
|---|---|---|---|
| `primaryContact.fullName` | `customers.business_contact_name` | Direct | Maximum 100 characters. The contract requires it although the column is nullable. |
| `primaryContact.email` | `customers.email` | Direct | Required, maximum 120 characters. The database does not validate email syntax. |
| `primaryContact.additionalEmails` | `customers.additional_emails` | JSON | Serialize the complete array as JSONB. Use `[]` for an explicit empty list. |
| `primaryContact.additionalEmails[].email` | JSON key `email` | JSON | Required email string. |
| `primaryContact.additionalEmails[].commercial` | JSON key `commercial` | JSON | Required JSON boolean. |
| `primaryContact.additionalEmails[].marketing` | JSON key `marketing` | JSON | Required JSON boolean. |
| `primaryContact.additionalEmails[].skype` | JSON key `skype` | JSON | Nullable string; preserve explicit `null`. |
| `primaryContact.certifiedEmail` | `customers.pec` | Direct | Nullable, maximum 100 characters. |
| `primaryContact.preferredLanguage` | `customers.preferred_language` | Direct | Nullable, maximum 50 characters. No language lookup exists. |

Observed `additional_emails` values are arrays or SQL `NULL`, and all array
elements are objects. Legacy objects are not uniform: some omit contract keys.
New writes should normalize supplied items to the complete version 1 shape.

### Billing Address

| Contract path | Database destination | Status | Conversion and validation |
|---|---|---|---|
| `billingAddress.street` | `customers.address_street` | Direct | Required, maximum 100 characters. |
| `billingAddress.city` | `customers.address_city` | Direct | Required, maximum 50 characters. |
| `billingAddress.postalCode` | `customers.address_zip_code` | Direct | Nullable, maximum 50 characters. |
| `billingAddress.countryCode` | `countries.iso_alpha_2` through `customers.region_id` | Lookup | Required uppercase ISO 3166-1 alpha-2 code. Use it with `regionName` to resolve one enabled region. |
| `billingAddress.regionName` | `regions.region_name` through `customers.region_id` | Lookup | Required exact value from the Life365 region catalog. Resolve it together with `countryCode`; do not use fuzzy matching. |

Every current customer has a billing region, although `region_id` is nullable.
A region links to a country through `regions.country_id`. The database enforces
uniqueness for `(region_name, country_id)`, and the current 279 region names are
also globally unique. The contract nevertheless uses both `countryCode` and
`regionName` because global name uniqueness is not guaranteed by the schema.
Only enabled rows belong to the catalog exposed to Salesforce; disabled rows
remain historical database values and cannot be selected by new events.

The adapter resolves the billing region with an exact match equivalent to:

```sql
SELECT r.id
FROM regions AS r
JOIN countries AS c ON c.id = r.country_id
WHERE upper(c.iso_alpha_2) = :country_code
  AND r.region_name = :region_name
  AND r.enabled = true;
```

Salesforce must select `regionName` from the catalog supplied by Life365.
Values such as `Forlì-Cesena`, `Venezia - laguna`, and `Roma - fuori GRA` must
retain their exact spelling. An unknown pair is a validation error.

### Delivery

| Contract path | Database destination | Status | Conversion and validation |
|---|---|---|---|
| `delivery.businessName` | `customers.delivery_business_name` | Direct | Nullable, maximum 120 characters. |
| `delivery.contactName` | `customers.delivery_contact_name` | Direct | Nullable, maximum 100 characters. |
| `delivery.phone` | `customers.delivery_phone` | Direct | Nullable, maximum 50 characters. |
| `delivery.address` | Delivery address columns | Direct | When `null`, clear all delivery address columns, subject to update policy. |
| `delivery.address.street` | `customers.delivery_address` | Direct | Maximum 100 characters. |
| `delivery.address.city` | `customers.delivery_city` | Direct | Maximum 50 characters. |
| `delivery.address.postalCode` | `customers.delivery_zip_code` | Direct | Nullable, maximum 50 characters. |
| `delivery.address.countryCode` | `countries.iso_alpha_2` through `customers.delivery_region_id` | Lookup | Required when `delivery.address` is present. Use it with `regionName` to resolve one enabled region. |
| `delivery.address.regionName` | `regions.region_name` through `customers.delivery_region_id` | Lookup | Required when `delivery.address` is present. It must be an exact catalog value for `countryCode`. |

`delivery_region_id` is nullable, and 357 current customers have no value. The
complete `delivery.address` object is nullable. When the object is present, its
country and region pair resolves `delivery_region_id` with the same exact rule
used for the billing address.

### Tax Profile

| Contract path | Database destination | Status | Conversion and validation |
|---|---|---|---|
| `taxProfile.fiscalCode` | `customers.fiscal_code` | Direct | Nullable, maximum 20 characters. |
| `taxProfile.vatCountryCode` | `customers.vat_country` | Direct | Nullable, maximum 2 characters. Normalize to uppercase. No foreign key validates it. |
| `taxProfile.vatNumber` | `customers.vat_number` | Direct | Nullable, maximum 20 characters. |
| `taxProfile.viesValidated` | `customers.vies` | Direct | Required boolean. The column is not nullable and defaults to `false`. |
| `taxProfile.fiscalAgentCode` | `customers.fiscal_agent_code` | Direct | Nullable, maximum 45 characters. |
| `taxProfile.secondaryTaxValue` | `customers.tax2` | Direct | Parse with `Decimal`, quantize to 2 places, and enforce `numeric(18,2)` range. Do not parse through `float`. |

The existing creator requires at least one of fiscal code or VAT number. That
rule is not a database constraint and must be confirmed for synchronization.

### Communication Preferences

| Contract path | Database destination | Status | Conversion and validation |
|---|---|---|---|
| `communicationPreferences.newsletter` | `customers.newsletter` | Direct | Nullable boolean. Default is `true`; explicit `null` remains SQL `NULL`. |
| `communicationPreferences.privacyRegistered` | `customers.reg_privacy` | Direct | Nullable boolean. |
| `communicationPreferences.rulesRegistered` | `customers.reg_rules` | Direct | Nullable boolean. |

### Registration

| Contract path | Database destination | Status | Conversion and validation |
|---|---|---|---|
| `registration.registeredAt` | `customers.registration_date` | Direct | Parse RFC 3339, convert to UTC, then store the UTC wall time in `timestamp without time zone`. |
| Trusted HTTP request client IPv4 | `customers.registration_ip` | Transport | Not present in the payload. On `customer.created`, extract and validate the request IPv4 and store its canonical string form. Do not overwrite it on `customer.updated`. |
| `registration.verified` | `customers.verified` | Direct | Nullable boolean. Default is `false`. |
| `registration.lastLoginAt` | `customers.last_login_date` | Direct | Apply the same UTC conversion. Confirm that Salesforce can change this operational value. |

The database session timezone is UTC. Both customer timestamp columns omit
timezone information, so the adapter must convert explicitly before storage.

`registration_ip` has a maximum length of 15 characters, which is sufficient
for canonical IPv4 values. If the API runs behind a reverse proxy, the API
layer must derive the client address only from proxy information that the
deployment explicitly trusts. The application service passes the validated
IPv4 value to the persistence operation separately from the Salesforce event
data. This value identifies the source of the synchronization request; it is
not an address supplied by Salesforce in the customer DTO.

### Commercial Data

| Contract path | Database destination | Status | Conversion and validation |
|---|---|---|---|
| `commercial.preferredCategories` | `customers.preferred_categories` | Lookup | Replace with an `integer[]` of resolved category IDs. Validate every code because array members have no foreign keys. |
| `commercial.preferredCategories[].code` | Adapter category map | Lookup | Stable identity used to obtain `categories.id`; no code column exists. |
| `commercial.preferredCategories[].label` | No customer column | Lookup | Descriptive value that can validate the selected category; do not select by label alone. |
| `commercial.salesChannel` | `customers.sales_channel_id` | Lookup | Resolve to one `sales_channels.id`. Default is ID 1; all current customers have a value. |
| `commercial.salesChannel.code` | Prefix in `sales_channels.c_name` | Lookup | Values such as `N13` prefix the name; no dedicated code column exists. Use an explicit adapter map. |
| `commercial.salesChannel.label` | Remaining `sales_channels.c_name` text | Lookup | Descriptive validation value. Existing whitespace is not canonical. |
| `commercial.assignedAgent` | `customers.agent_id` | Lookup | Required but nullable on create. An object resolves its `referenceId`; `null` applies the Life365 fallback-agent policy. Omission in an update leaves the assignment unchanged. |
| `commercial.assignedAgent.referenceId` | `agents.id` | Lookup | Required positive integer. This is the only field used to resolve the agent; reject the event when no row has this ID. |
| `commercial.assignedAgent.userLogin` | None | Descriptive | Current `agents.user_login` snapshot for Salesforce. Do not use it for lookup or update the agent row from it. |
| `commercial.assignedAgent.name` | None | Descriptive | Current `agents.contact_name` snapshot for Salesforce. Do not use it for lookup or update the agent row from it. |
| `commercial.assignedAgent.email` | None | Descriptive | Current `agents.email` snapshot for Salesforce. Do not use it for lookup or update the agent row from it. |
| `commercial.assignedAgent.phone` | None | Descriptive | Nullable current `agents.phone` snapshot for Salesforce. Do not use it for lookup or update the agent row from it. |
| `commercial.paymentAgreement` | `customers.payment_agreement` | Direct | Nullable, maximum 100 characters. |
| `commercial.preferredPaymentTypeCode` | `customers.preferred_payment_type` | Lookup | Must match the `payment_types.payment_type` primary key, maximum 50 characters. |
| `commercial.paymentDays` | `customers.payment_days` | Direct | Nullable integer. Default is `0`; no range constraint exists. |
| `commercial.paymentDaysEndOfMonth` | `customers.payment_days_eom` | Direct | Nullable integer. Default is `-1`; define its meaning and valid range. |
| `commercial.creditGranted` | `customers.fido_granted` | Direct | Parse with `Decimal`, use 2 places, and enforce `numeric(10,2)` range. |
| `commercial.creditValue` | `customers.fido` | Decision | A direct column exists, but current edit logic recalculates it from invoices and granted credit. Confirm ownership before accepting writes. |

The current category map inferred from the contract and live labels is:

| Integration code | Category ID | Current English label |
|---|---:|---|
| `cartridge-toner` | 1 | Cartridge&Toner |
| `smart-solutions` | 2 | Smart Solutions |
| `networking` | 14 | Network&Security |
| `myphone` | 23 | Myphone |
| `solar-energy` | 25 | Solar Energy |
| `lighting` | 27 | Lighting |
| `electric-parts` | 28 | Electric parts |
| `special-business` | 29 | Special business |
| `power-tools` | 30 | Power tools |

These are the only category IDs currently used in `preferred_categories`, and
all resolve to category rows. The infrastructure adapter should own this map;
it must not infer identifiers from labels for each request.

All 20 sales channels use an `N<number>` prefix that matches their current ID,
with gaps at IDs 16 and 17. No database constraint enforces that pattern.

The database has 11 payment types. Their code is the primary key. Invisible
types still exist and need a rule if Salesforce submits one.

The payload uses the Life365 agent ID as its authoritative reference. This is
intentional Life365 coupling: Salesforce stores the reference and returns it
with later customer events. Agent names, emails, and phone numbers are not
unique in the current data and must never be used as fallback identity keys.
For example, agent IDs 52 and 76 have the same normalized name, email, and
phone, but they represent different rows. A payload containing
`assignedAgent.referenceId: 117` resolves the `Mario Xia` agent directly even
if Salesforce has an older descriptive snapshot.

When `assignedAgent` is `null`, the application applies its configured
fallback-agent policy instead of storing SQL `NULL`. Version 1 uses agent ID 1,
which matches the existing Life365 creator and the database default. On create,
the mapper can omit `agent_id` so its default applies. On update, the mapper
sets the configured fallback explicitly. A supplied but unknown
`assignedAgent.referenceId` is rejected rather than converted to the fallback.

### Banking

| Contract path | Database destination | Status | Conversion and validation |
|---|---|---|---|
| `banking.abi` | `customers.payment_abi` | Direct | Nullable, maximum 5 characters. Preserve leading zeroes. |
| `banking.cab` | `customers.payment_cab` | Direct | Nullable, maximum 5 characters. Preserve leading zeroes. |
| `banking.iban` | `customers.payment_iban` | Direct | Nullable, maximum 34 characters. Existing specialized writes validate and compact it; synchronization should do the same. |

### Shop

| Contract path | Database destination | Status | Conversion and validation |
|---|---|---|---|
| `shop.latitude` | `customers.shop_location_lat` | Direct | Convert to `Decimal`, enforce `-90..90`, and fit `numeric(18,10)`. |
| `shop.longitude` | `customers.shop_location_lng` | Direct | Convert to `Decimal`, enforce `-180..180`, and fit `numeric(18,10)`. |
| `shop.groups` | `customers.shop_group_ids` | Lookup | Replace with an `integer[]`; validate every code because array members have no foreign key. |
| `shop.groups[].code` | Adapter shop-group map | Lookup | Stable integration code. No code column exists in `shop_groups`. |
| `shop.groups[].label` | `shop_groups.group_name` for validation | Lookup | Descriptive value. The name is unique, but the code should identify the row. |

The current shop-group map is:

| Integration code | Group ID | Current group name | Sales channel ID |
|---|---:|---|---:|
| `rei-la-rete` | 1 | R.E.I. - LA RETE | 2 |
| `geser-prodigix` | 2 | Geser - Prodigix | 3 |
| `professional-group` | 3 | Professional Group | 3 |
| `closed-activity` | 36 | closed activity | None |

Existing edits can change `sales_channel_id` when a new shop group has a
related channel. Synchronization must define whether the explicit sales channel
wins or this side effect applies.

### Operational Settings

| Contract path | Database destination | Status | Conversion and validation |
|---|---|---|---|
| `operationalSettings.disableBoxDiscount` | `customers.disable_box_discount` | Direct | Required boolean. Column is not nullable and defaults to `false`. |
| `operationalSettings.disableQuantityDelivery` | `customers.disable_qty_delivery` | Direct | Nullable boolean, default `false`. |
| `operationalSettings.prepaidReturns` | `customers.rma_prepaid` | Direct | Nullable boolean, default `true`. |
| `operationalSettings.disableSaleLimit` | `customers.disable_limit_sale` | Direct | Nullable boolean, default `false`. |

### Notes

| Contract path | Database destination | Status | Conversion and validation |
|---|---|---|---|
| `notes.items` | `customers._notes` | JSON | Replace with a JSONB array; use `[]` for an explicit empty list. |
| `notes.items[].occurredAt` | JSON key `date` | JSON | Parse RFC 3339 and serialize in the legacy date format selected for the adapter. |
| `notes.items[].text` | JSON key `note` | JSON | Required string. Define an application length limit. |
| `notes.items[].open` | JSON key `open` | JSON | Required JSON boolean. |
| `notes.openCount` | `customers.notes_open` | Direct | Required non-negative integer. Decide whether to trust it or derive it from items. |
| `notes.administrativeNote` | `customers.admin_note` | Direct | Nullable, maximum 250 characters. |

Observed `_notes` values are arrays or SQL `NULL`. Every observed element is an
object with keys `date`, `note`, and `open`.

A separate `customer_notes` table exists, but it requires `author_id` and
stores history. The contract supplies neither, so this table is not a direct
destination for `notes.items`.

### Extensions

| Contract path | Database destination | Status | Conversion and validation |
|---|---|---|---|
| `extensions.parameters` | `customers.parameters` | JSON | Nullable JSONB object. Create can store it directly; update needs merge or replacement rules. |
| `extensions.extraData` | `customers.extra_data` | JSON | Nullable JSONB object. Create can store it directly; update needs merge or replacement rules. |

Observed non-null values are objects. Common `parameters` keys include
`not_buyer`. Common `extra_data` keys include `origin`, `origin_id`,
`annual_revenue`, `business_type`, `employee_number`, `interests`,
`monthly_orders`, and `year_established`. Preserve unknown keys according to
the final update policy.

## Existing Write Behavior

- Customer creation checks exact duplicate logins, inserts the row, and then
  updates categories in one cursor context. It truncates several strings. New
  synchronization should reject overlength values instead.
- Normal creation lets PostgreSQL allocate the identity and then selects by
  login. New code should use `INSERT ... RETURNING id`.
- Creation stores `registration_date` as database `NOW()`.
- Creation uses agent ID 1 when an agent is missing. Current customers also
  have no null agent IDs.
- General editing uses separate updates. Credit edits recalculate `fido`, and
  shop-group edits can update the sales channel.
- A specialized IBAN update validates and compacts the value.
- Authentication matches login case-insensitively and accepts either the
  stored password or `md5(stored_password)` as input.
- Deletion performs a physical `DELETE` and lets foreign-key errors propagate.
- The legacy cursor context commits after successful completion.

The synchronization mapper should execute one event in one transaction. It
must not use independent commits for related field changes.

## Defaults And Null Handling

| Column | Default |
|---|---|
| `newsletter` | `true` |
| `preferred_payment_type` | `BONIFICO` |
| `fido_granted`, `fido`, `tax2` | `0.00` |
| `payment_days` | `0` |
| `payment_days_eom` | `-1` |
| `verified` | `false` |
| `agent_id` | `1` |
| `notes_open` | `0` |
| `disable_box_discount` | `false` |
| `disable_qty_delivery` | `false` |
| `rma_prepaid` | `true` |
| `disable_limit_sale` | `false` |
| `sales_channel_id` | `1` |
| `vies` | `false` |

An explicit JSON `null` normally becomes SQL `NULL` and does not activate a
default. A default applies only when the mapper omits the column. For updates,
an omitted field must not appear in SQL, an allowed explicit `null` becomes
SQL `NULL`, an empty array becomes an empty array, and `null` remains distinct
from an empty collection. `commercial.assignedAgent` is an explicit exception:
its `null` value requests the Life365 fallback-agent policy and never writes a
null `customers.agent_id`.

## Blocking And Open Decisions

1. Add durable processed-event storage for idempotency and event ordering.
2. Define logical deletion, physical deletion with conflict, or another clear
   behavior for `customer.deleted`.
3. Decide whether Salesforce can write `creditValue` or Life365 derives it.
4. Define how a null sales-channel object interacts with its database default.
5. Define whether a shop group can override the supplied sales channel.
6. Define whether `notes.openCount` is supplied or derived.
7. Define merge or replacement behavior for update patches in extensions.
8. Define case-insensitive login uniqueness and handle existing duplicates.

Every version 1 payload leaf has a database destination or an explicit mapping
problem in this document.
