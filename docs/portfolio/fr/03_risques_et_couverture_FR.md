# Analyse des risques et couverture de tests

| ID | Risque | Impact | Probabilité | Priorité | Contrôle principal |
|---|---|---:|---:|---:|---|
| R01 | Perte silencieuse de lignes pendant une jointure | 5 | 3 | Critique | Réconciliation Raw/Silver/Quarantine |
| R02 | Une ancienne version remplace la mise à jour la plus récente | 4 | 4 | Haute | Test latest-wins sur `updated_at` |
| R03 | Réservation et paiement incohérents | 5 | 3 | Critique | Règles transverses et comparaison des montants |
| R04 | Dérive de schéma ou type incompatible | 4 | 3 | Haute | Tests de contrat et négatifs |
| R05 | Calcul de chiffre d’affaires incorrect | 5 | 3 | Critique | Oracle SQL indépendant de l’implémentation |
| R06 | Une relance du batch crée des doublons | 4 | 3 | Haute | Test d’idempotence |
| R07 | Clé offre ou réservation orpheline | 4 | 2 | Haute | Anti-join et quarantaine |
| R08 | Dégradation du temps de traitement avec le volume | 3 | 3 | Moyenne | Baseline 10k/100k/500k |
| R09 | Identifiant personnel conservé dans Gold | 5 | 2 | Haute | Contrôle d’absence du `client_id` brut |

## Défaut d’implémentation contrôlé

Une anomalie de code est introduite volontairement : la déduplication conserve la version la plus ancienne d’une réservation au lieu de la plus récente.

Cycle de preuve :

1. contrôle pytest en échec ;
2. quality gate CI bloqué ;
3. BUG-001 avec preuve SQL ;
4. correction sur une branche ;
5. retest et régression ;
6. pipeline réussi ;
7. bilan qualité mis à jour.

Les lignes incorrectes placées volontairement dans les sources synthétiques constituent des jeux de tests négatifs, et non des anomalies applicatives.
