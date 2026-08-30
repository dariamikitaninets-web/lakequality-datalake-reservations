# Registre des preuves

Seule une preuve issue d’une exécution réelle peut recevoir le statut `CAPTURÉE`.

| ID | Étape | Preuve attendue | Statut initial |
|---|---|---|---|
| EV-001 | Preflight | Versions Python, Git, Docker, Java et JMeter sur macOS | À CAPTURER |
| EV-002 | Sources | Aperçu des trois sources synthétiques | À CAPTURER |
| EV-003 | Architecture | Diagramme Source-Bronze-Silver-Quarantine-Gold | À PRODUIRE |
| EV-004 | Premier batch | Résumé du pipeline correct et identifiant du batch | À CAPTURER |
| EV-005 | Complétude | Réconciliation SQL avec écart = 0 | À CAPTURER |
| EV-006 | Unicité | SQL recherchant les identifiants dupliqués en Silver | À CAPTURER |
| EV-007 | Quarantaine | Codes de motif et volume par cause | À CAPTURER |
| EV-008 | Latest wins | Échec contrôlé en mode buggy | À CAPTURER |
| EV-009 | Anomalie | BUG-001 dans GitHub Issues | À CAPTURER |
| EV-010 | Correction | Diff ou Pull Request montrant la correction | À CAPTURER |
| EV-011 | Régression | Rapport pytest complet et réussi | À CAPTURER |
| EV-012 | CI rouge | GitHub Actions bloqué en mode buggy | À CAPTURER |
| EV-013 | CI verte | GitHub Actions réussi en mode fixed | À CAPTURER |
| EV-014 | Performance | Mesures 10k/100k/500k et débit | À CAPTURER |
| EV-015 | Rapport qualité | Indicateurs et recommandation GO/NO-GO | À CAPTURER |
| EV-016 | GitLab | Pipeline GitLab réel si un compte est créé | OPTIONNEL |
| EV-017 | Kubernetes | `kubectl get jobs,pods` et logs du Job | OPTIONNEL |

## Convention de capture

- Nom : `EV-XXX_description_courte.png`.
- Montrer la commande ou la requête et son résultat principal.
- Masquer les tokens, adresses e-mail privées et chemins personnels inutiles.
- Ajouter la date, l’environnement, le SHA du commit et une interprétation en une phrase.
- Ne jamais recréer une interface ou un résultat non exécuté.
