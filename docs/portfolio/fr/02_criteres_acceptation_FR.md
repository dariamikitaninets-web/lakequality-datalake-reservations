# Critères d’acceptation

| ID | Critère | Priorité | Preuve attendue |
|---|---|---:|---|
| AC01 | Chaque fichier source est copié en Bronze avec identifiant de batch, nom et checksum. Aucun fichier ne disparaît silencieusement. | Critique | Manifeste du batch et contrôle automatisé |
| AC02 | Une colonne obligatoire absente ou un type invalide provoque un échec contrôlé ou une mise en quarantaine avec un code de motif. | Critique | Test négatif et contenu de Quarantine |
| AC03 | La réconciliation est exacte : raw = accepted + superseded + quarantined ; l’écart vaut 0. | Critique | Requête SQL et rapport qualité |
| AC04 | Silver contient une seule ligne courante par identifiant de réservation et conserve le plus grand `updated_at`. | Haute | SQL d’unicité et test de déduplication |
| AC05 | Aucune relation orpheline réservation-paiement ou réservation-offre n’atteint Gold. | Haute | Anti-join SQL et test d’intégration |
| AC06 | Le revenu est reconnu uniquement pour CONFIRMED + PAID. CANCELLED, REFUNDED et DECLINED contribuent pour zéro. | Critique | Oracle SQL indépendant |
| AC07 | Les montants réservation-paiement concordent à 0,01 EUR et les statuts appartiennent aux catalogues autorisés. | Haute | Contrôles paramétrés |
| AC08 | `service_date` est postérieure ou égale à `booking_ts`. | Moyenne | Contrôle de validité temporelle |
| AC09 | La relance du même batch est idempotente : le nombre, la somme et le hash de Gold ne changent pas. | Haute | Double exécution et comparaison |
| AC10 | L’agrégat Gold correspond à un calcul de contrôle indépendant depuis les sources valides. | Critique | Réconciliation source-cible |
| AC11 | Le rapport qualité contient les volumes, motifs de quarantaine, doublons, écart, taux de réussite et durée. | Haute | Rapport JSON/HTML |
| AC12 | La CI/CD bloque le quality gate lorsqu’un contrôle critique échoue et publie les rapports. | Critique | Preuves de pipeline rouge puis vert |
| AC13 | Baseline de laboratoire : 100 000 lignes en moins de 30 secondes, sans erreur et avec un écart nul. | Moyenne | Mesure horodatée ; seuil fictif explicite |
| AC14 | Extension optionnelle : le Job Kubernetes atteint `Completed` avec un code de sortie 0. | Optionnelle | Preuve `kubectl` uniquement si réellement exécutée |

AC13 est une hypothèse de laboratoire, et non un SLA client.
