# Simulated mission brief

## Fictional context

A travel-services company consolidates bookings from three channels every night: its website, partner agencies, and a B2B API. Booking, payment, and offer data feeds a Datalake and a daily revenue report by destination.

Version 1.1 introduces incremental loading and a new deduplication rule. It must be qualified before release.

## Simulated weekly objective

Produce an evidence-based GO/NO-GO recommendation covering:

- received-file integrity;
- schemas, types, and mandatory fields;
- source-to-target reconciliation;
- selection of the latest booking version;
- relationships between bookings, payments, and offers;
- revenue-recognition rules;
- idempotent reprocessing of the same batch;
- processing time at several controlled volumes.

## Sources

| Source | Format | Main content |
|---|---|---|
| Bookings | CSV | booking ID, offer, client, status, dates, amount, currency, update time |
| Payments | JSONL | payment ID, booking ID, status, amount, currency, payment time |
| Offers | CSV | offer ID, destination, commission rate, active flag |

## Target layers

- **Bronze** — immutable copy of source data with batch ID, filename, and checksum.
- **Silver** — normalized and deduplicated valid data; the most recent version is retained.
- **Quarantine** — unusable records with an explicit reason code.
- **Gold** — daily revenue indicators by destination.

## Out of scope

- real data or access to an enterprise system;
- Kafka streaming and Airflow orchestration;
- infrastructure high availability, production operations, and a real client SLA;
- Kubernetes cluster administration.

## Simulated stakeholders

Product Owner, Data Engineer, DevOps Engineer, and Business Analyst roles are used only to structure questions, assumptions, and decisions. No interaction with a real delivery team is represented as having occurred.
