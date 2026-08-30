# Brief de mission simulée

## Contexte fictif

Une entreprise de services touristiques consolide chaque nuit les réservations issues de trois canaux : son site web, des agences partenaires et une API B2B. Les données de réservation, de paiement et d’offre alimentent un Datalake puis un rapport quotidien de chiffre d’affaires par destination.

La version 1.1 introduit un chargement incrémental et une nouvelle règle de déduplication. Elle doit être qualifiée avant sa mise en production.

## Objectif de la semaine simulée

Produire une recommandation GO/NO-GO fondée sur des preuves concernant :

- l’intégrité des fichiers reçus ;
- les schémas, les types et les champs obligatoires ;
- la réconciliation entre source et cible ;
- la sélection de la version la plus récente d’une réservation ;
- les relations entre réservations, paiements et offres ;
- les règles de reconnaissance du revenu ;
- l’idempotence de la relance d’un même batch ;
- le temps de traitement sur plusieurs volumes contrôlés.

## Sources

| Source | Format | Contenu principal |
|---|---|---|
| Réservations | CSV | identifiant, offre, client, statut, dates, montant, devise et mise à jour |
| Paiements | JSONL | identifiant, réservation, statut, montant, devise et date de paiement |
| Offres | CSV | identifiant, destination, taux de commission et indicateur d’activité |

## Couches cibles

- **Bronze** — copie immuable des sources avec identifiant de batch, nom de fichier et checksum.
- **Silver** — données valides, normalisées et dédupliquées ; la version la plus récente est conservée.
- **Quarantine** — enregistrements inexploitables avec un code de motif explicite.
- **Gold** — indicateurs quotidiens de chiffre d’affaires par destination.

## Hors périmètre

- données réelles ou accès à un système d’entreprise ;
- streaming Kafka et orchestration Airflow ;
- haute disponibilité, exploitation de production et SLA client réel ;
- administration d’un cluster Kubernetes.

## Parties prenantes simulées

Les rôles de Product Owner, Data Engineer, DevOps Engineer et Business Analyst servent uniquement à structurer les questions, les hypothèses et les décisions. Aucun échange avec une équipe réelle n’est présenté comme ayant eu lieu.
