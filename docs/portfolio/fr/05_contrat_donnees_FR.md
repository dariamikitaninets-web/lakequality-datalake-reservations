# Contrat de données v1.1 — hypothèse de simulation

Ce contrat est inventé pour l’exercice et ne représente aucun schéma client réel.

## `bookings.csv`

| Champ | Type logique | Obligatoire | Règle |
|---|---|---:|---|
| `booking_id` | string | oui | `BKG-XXXXXX` ; plusieurs versions autorisées en Bronze |
| `offer_id` | string | oui | Doit identifier une offre active |
| `client_id` | string | oui | Brut uniquement en Bronze ; pseudonymisé en Silver ; absent de Gold |
| `source_channel` | enum | oui | `WEB`, `AGENCY` ou `B2B_API` |
| `booking_ts` | timestamp UTC | oui | Date de création de la réservation |
| `service_date` | date | oui | Postérieure ou égale à la date de `booking_ts` |
| `booking_status` | enum | oui | `PENDING`, `CONFIRMED` ou `CANCELLED` |
| `gross_amount` | decimal(12,2) | oui | Valeur >= 0 |
| `currency` | string | oui | `EUR` dans le périmètre v1.1 |
| `updated_at` | timestamp UTC | oui | La version la plus récente devient courante |

## `payments.jsonl`

| Champ | Type logique | Obligatoire | Règle |
|---|---|---:|---|
| `payment_id` | string | oui | Unique |
| `booking_id` | string | oui | Doit identifier une réservation |
| `payment_status` | enum | oui | `PAID`, `DECLINED` ou `REFUNDED` |
| `amount` | decimal(12,2) | oui | Valeur >= 0 et concordance à 0,01 EUR |
| `currency` | string | oui | `EUR` dans le périmètre v1.1 |
| `paid_at` | timestamp UTC | conditionnel | Obligatoire pour `PAID` et `REFUNDED` |

## `offers.csv`

| Champ | Type logique | Obligatoire | Règle |
|---|---|---:|---|
| `offer_id` | string | oui | Unique |
| `destination` | string | oui | Non vide |
| `commission_rate` | decimal(5,4) | oui | Entre 0 et 1 |
| `active` | boolean | oui | Seules les offres actives atteignent Gold |

## Règles Gold

Une réservation contribue au revenu lorsque sa version courante est `CONFIRMED`, que son paiement est `PAID`, que les montants concordent et que l’offre est active.

| Mesure | Calcul |
|---|---|
| `gross_revenue_eur` | Somme des `gross_amount` éligibles |
| `commission_revenue_eur` | Somme de `gross_amount * commission_rate` |
| `net_revenue_eur` | Revenu brut moins commission |
| `confirmed_bookings` | Nombre distinct d’identifiants de réservation éligibles |

## Codes de quarantaine

`MISSING_REQUIRED`, `INVALID_STATUS`, `INVALID_DATE_ORDER`, `NEGATIVE_AMOUNT`, `UNSUPPORTED_CURRENCY`, `UNKNOWN_OFFER`, `MISSING_PAYMENT` et `AMOUNT_MISMATCH`.

Aucune ligne source ne doit disparaître sans être classée comme courante, remplacée ou mise en quarantaine.
