# Plan d’exécution sur trois à quatre jours

## Jour 1 — compréhension et premier flux

Étudier la mission, le flux, les critères d’acceptation et les risques. Générer les sources synthétiques, exécuter le pipeline correct de Bronze à Gold, réaliser les contrôles SQL manuels et capturer les premières preuves.

**Résultat :** flux fonctionnel et explication claire de ce qui est testé et pourquoi.

## Jour 2 — automatisation et cycle de l’anomalie

Étudier les tests de schéma, d’intégration, E2E et d’idempotence. Exécuter la déduplication volontairement erronée, enregistrer BUG-001, corriger, effectuer le retest et lancer la régression complète avec rapports exploitables par la CI.

**Résultat :** test en échec → investigation → correction → régression réussie.

## Jour 3 — CI/CD, performance et reporting

Exécuter un quality gate CI réel, mesurer des volumes contrôlés, générer le rapport qualité et formuler une recommandation GO/NO-GO fondée sur les preuves.

**Résultat :** quality gate automatisé et bilan qualité mesurable.

## Jour 4 — Kubernetes optionnel et portfolio

Exécuter un Job Kubernetes uniquement si un cluster local réel est disponible. Sinon, marquer le manifeste comme proposition non exécutée. Assembler le portfolio bilingue et préparer des présentations de 60 secondes et de deux minutes.

**Résultat :** preuves prêtes pour l’entretien sans surestimer l’expérience.

## Condition d’intégrité

Chaque capture doit provenir d’une exécution réelle. Aucune interface GitLab, terminal, Kubernetes ou outil interne n’est recréée.
