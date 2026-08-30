-- LakeQuality - controles SQL independants (DuckDB)
--
-- Objectif : fournir des preuves manuelles reproductibles pour AC01-AC10 et R09.
-- Les controles utilisent uniquement les tables DuckDB produites par le pipeline.
-- L'oracle Gold (AC06/AC10) est recalcule directement depuis Bronze, sans reutiliser
-- Silver ni la logique d'agregation du pipeline.
--
-- Execution depuis la racine du projet :
--   duckdb data/lakequality.duckdb < sql/validation.sql
--
-- Tous les objets crees ci-dessous sont TEMPORARY : la base du laboratoire reste
-- en lecture seule du point de vue fonctionnel.

SET VARIABLE target_batch = 'BATCH_DEMO_001';

CREATE OR REPLACE TEMP TABLE validation_results (
    check_id       VARCHAR,
    control_name   VARCHAR,
    priority       VARCHAR,
    status         VARCHAR,
    actual_value   VARCHAR,
    expected_value VARCHAR,
    details        VARCHAR
);

-- ---------------------------------------------------------------------------
-- AC01 - Integrite Bronze : manifest, volumes et metadonnees techniques
-- ---------------------------------------------------------------------------

CREATE OR REPLACE TEMP VIEW _bronze_actual_counts AS
SELECT source_file, COUNT(*)::BIGINT AS actual_row_count
FROM bronze_bookings
WHERE batch_id = getvariable('target_batch')
GROUP BY source_file
UNION ALL
SELECT source_file, COUNT(*)::BIGINT AS actual_row_count
FROM bronze_payments
WHERE batch_id = getvariable('target_batch')
GROUP BY source_file
UNION ALL
SELECT source_file, COUNT(*)::BIGINT AS actual_row_count
FROM bronze_offers
WHERE batch_id = getvariable('target_batch')
GROUP BY source_file;

INSERT INTO validation_results
WITH anomalies AS (
    SELECT COUNT(*) AS n
    FROM bronze_manifest m
    FULL OUTER JOIN _bronze_actual_counts a
      ON a.source_file = m.source_file
    WHERE COALESCE(m.batch_id, getvariable('target_batch')) = getvariable('target_batch')
      AND (
          m.source_file IS NULL
          OR a.source_file IS NULL
          OR m.row_count IS DISTINCT FROM a.actual_row_count
          OR NULLIF(TRIM(m.checksum), '') IS NULL
          OR NULLIF(TRIM(m.bronze_copy), '') IS NULL
      )
)
SELECT
    'AC01A',
    'Manifest Bronze et volumes par fichier',
    'CRITIQUE',
    CASE WHEN n = 0 THEN 'PASS' ELSE 'FAIL' END,
    n::VARCHAR || ' anomalie(s)',
    '0 anomalie',
    'Chaque source doit etre tracee dans le manifest avec checksum, copie Bronze et row_count exact.'
FROM anomalies;

INSERT INTO validation_results
WITH all_bronze_metadata AS (
    SELECT batch_id, source_file, source_checksum FROM bronze_bookings
    WHERE batch_id = getvariable('target_batch')
    UNION ALL
    SELECT batch_id, source_file, source_checksum FROM bronze_payments
    WHERE batch_id = getvariable('target_batch')
    UNION ALL
    SELECT batch_id, source_file, source_checksum FROM bronze_offers
    WHERE batch_id = getvariable('target_batch')
), anomalies AS (
    SELECT COUNT(*) AS n
    FROM all_bronze_metadata b
    LEFT JOIN bronze_manifest m
      ON m.batch_id = b.batch_id
     AND m.source_file = b.source_file
    WHERE b.batch_id IS NULL
       OR NULLIF(TRIM(b.source_file), '') IS NULL
       OR NULLIF(TRIM(b.source_checksum), '') IS NULL
       OR m.source_file IS NULL
       OR b.source_checksum IS DISTINCT FROM m.checksum
)
SELECT
    'AC01B',
    'Metadonnees techniques sur chaque ligne Bronze',
    'CRITIQUE',
    CASE WHEN n = 0 THEN 'PASS' ELSE 'FAIL' END,
    n::VARCHAR || ' ligne(s) non tracee(s)',
    '0 ligne non tracee',
    'batch_id, source_file et checksum doivent etre presents et coherents avec le manifest.'
FROM anomalies;

-- ---------------------------------------------------------------------------
-- AC02 - Contrat, NULL et quarantaine explicite
-- ---------------------------------------------------------------------------

INSERT INTO validation_results
WITH invalid_silver AS (
    SELECT COUNT(*) AS n
    FROM silver_bookings
    WHERE batch_id = getvariable('target_batch')
      AND (
          NULLIF(TRIM(booking_id), '') IS NULL
          OR NULLIF(TRIM(offer_id), '') IS NULL
          OR NULLIF(TRIM(client_id_hash), '') IS NULL
          OR NULLIF(TRIM(source_channel), '') IS NULL
          OR booking_ts IS NULL
          OR service_date IS NULL
          OR gross_amount IS NULL
          OR NULLIF(TRIM(currency), '') IS NULL
          OR updated_at IS NULL
      )
), invalid_payments AS (
    SELECT COUNT(*) AS n
    FROM silver_payments
    WHERE batch_id = getvariable('target_batch')
      AND (
          NULLIF(TRIM(payment_id), '') IS NULL
          OR NULLIF(TRIM(booking_id), '') IS NULL
          OR NULLIF(TRIM(payment_status), '') IS NULL
          OR amount IS NULL
          OR NULLIF(TRIM(currency), '') IS NULL
          OR (payment_status IN ('PAID', 'REFUNDED') AND paid_at IS NULL)
      )
)
SELECT
    'AC02A',
    'Champs obligatoires apres normalisation',
    'CRITIQUE',
    CASE WHEN b.n + p.n = 0 THEN 'PASS' ELSE 'FAIL' END,
    (b.n + p.n)::VARCHAR || ' ligne(s) invalide(s) dans Silver',
    '0 ligne invalide',
    'Une valeur obligatoire invalide ne doit jamais atteindre Silver.'
FROM invalid_silver b
CROSS JOIN invalid_payments p;

INSERT INTO validation_results
WITH quarantine_anomalies AS (
    SELECT COUNT(*) AS n
    FROM quarantine_records
    WHERE batch_id = getvariable('target_batch')
      AND (
          NULLIF(TRIM(source_entity), '') IS NULL
          OR NULLIF(TRIM(record_id), '') IS NULL
          OR NULLIF(TRIM(reason_code), '') IS NULL
          OR reason_code NOT IN (
              'MISSING_REQUIRED',
              'INVALID_STATUS',
              'INVALID_DATE_ORDER',
              'NEGATIVE_AMOUNT',
              'UNSUPPORTED_CURRENCY',
              'UNKNOWN_OFFER',
              'MISSING_PAYMENT',
              'AMOUNT_MISMATCH'
          )
      )
), quarantine_volume AS (
    SELECT COUNT(*) AS n
    FROM quarantine_records
    WHERE batch_id = getvariable('target_batch')
)
SELECT
    'AC02B',
    'Quarantaine explicite des jeux negatifs',
    'CRITIQUE',
    CASE WHEN a.n = 0 AND v.n > 0 THEN 'PASS' ELSE 'FAIL' END,
    v.n::VARCHAR || ' ligne(s), ' || a.n::VARCHAR || ' anomalie(s) de reason_code',
    '> 0 ligne et 0 reason_code invalide',
    'Le batch DEMO contient volontairement des cas negatifs ; chaque rejet doit avoir une cause du contrat.'
FROM quarantine_anomalies a
CROSS JOIN quarantine_volume v;

-- ---------------------------------------------------------------------------
-- AC03 - Reconciliation sans disparition silencieuse
-- ---------------------------------------------------------------------------

INSERT INTO validation_results
WITH counts AS (
    SELECT
        (SELECT COUNT(*) FROM bronze_bookings
         WHERE batch_id = getvariable('target_batch')) AS raw_count,
        (SELECT COUNT(*) FROM silver_bookings
         WHERE batch_id = getvariable('target_batch')) AS current_count,
        (SELECT COUNT(*) FROM superseded_bookings
         WHERE batch_id = getvariable('target_batch')) AS superseded_count,
        (SELECT COUNT(*) FROM quarantine_records
         WHERE batch_id = getvariable('target_batch')
           AND source_entity = 'bookings') AS quarantined_count
)
SELECT
    'AC03',
    'Reconciliation des reservations',
    'CRITIQUE',
    CASE
        WHEN raw_count = current_count + superseded_count + quarantined_count
        THEN 'PASS' ELSE 'FAIL'
    END,
    'raw=' || raw_count::VARCHAR
        || '; current=' || current_count::VARCHAR
        || '; superseded=' || superseded_count::VARCHAR
        || '; quarantined=' || quarantined_count::VARCHAR
        || '; ecart=' || (raw_count-current_count-superseded_count-quarantined_count)::VARCHAR,
    'ecart=0',
    'Formule : Bronze = Silver courant + versions remplacees + quarantaine.'
FROM counts;

-- ---------------------------------------------------------------------------
-- AC04 - Unicite et regle latest-wins
-- ---------------------------------------------------------------------------

INSERT INTO validation_results
WITH duplicate_groups AS (
    SELECT COUNT(*) AS n
    FROM (
        SELECT booking_id
        FROM silver_bookings
        WHERE batch_id = getvariable('target_batch')
        GROUP BY booking_id
        HAVING COUNT(*) > 1
    ) d
)
SELECT
    'AC04A',
    'Une seule version courante par booking_id',
    'HAUTE',
    CASE WHEN n = 0 THEN 'PASS' ELSE 'FAIL' END,
    n::VARCHAR || ' booking_id duplique(s)',
    '0 booking_id duplique',
    'Silver doit contenir une seule ligne courante par cle metier.'
FROM duplicate_groups;

INSERT INTO validation_results
WITH all_accepted_versions AS (
    SELECT booking_id, updated_at, TRUE AS is_current
    FROM silver_bookings
    WHERE batch_id = getvariable('target_batch')
    UNION ALL
    SELECT booking_id, updated_at, FALSE AS is_current
    FROM superseded_bookings
    WHERE batch_id = getvariable('target_batch')
), expected_latest AS (
    SELECT booking_id, MAX(updated_at) AS max_updated_at
    FROM all_accepted_versions
    GROUP BY booking_id
), stale_current AS (
    SELECT COUNT(*) AS n
    FROM silver_bookings s
    JOIN expected_latest e USING (booking_id)
    WHERE s.batch_id = getvariable('target_batch')
      AND s.updated_at IS DISTINCT FROM e.max_updated_at
)
SELECT
    'AC04B',
    'Deduplication latest-wins',
    'HAUTE',
    CASE WHEN n = 0 THEN 'PASS' ELSE 'FAIL' END,
    n::VARCHAR || ' version(s) courante(s) obsolete(s)',
    '0 version obsolete',
    'Le updated_at courant doit etre le MAX parmi les versions acceptees.'
FROM stale_current;

-- ---------------------------------------------------------------------------
-- AC05 - Integrite transverse reservation / paiement / offre
-- ---------------------------------------------------------------------------

CREATE OR REPLACE TEMP VIEW _active_source_offers AS
SELECT DISTINCT offer_id
FROM bronze_offers
WHERE batch_id = getvariable('target_batch')
  AND NULLIF(TRIM(offer_id), '') IS NOT NULL
  AND TRY_CAST(active AS BOOLEAN) = TRUE;

INSERT INTO validation_results
WITH orphan_offers AS (
    SELECT COUNT(*) AS n
    FROM silver_bookings b
    LEFT JOIN _active_source_offers o USING (offer_id)
    WHERE b.batch_id = getvariable('target_batch')
      AND o.offer_id IS NULL
), orphan_payments AS (
    SELECT COUNT(*) AS n
    FROM silver_payments p
    LEFT JOIN silver_bookings b
      ON b.batch_id = p.batch_id
     AND b.booking_id = p.booking_id
    WHERE p.batch_id = getvariable('target_batch')
      AND b.booking_id IS NULL
), orphan_gold AS (
    SELECT COUNT(*) AS n
    FROM gold_revenue_detail g
    LEFT JOIN silver_bookings b
      ON b.booking_id = g.booking_id
    LEFT JOIN silver_payments p
      ON p.payment_id = g.payment_id
    WHERE b.booking_id IS NULL OR p.payment_id IS NULL
)
SELECT
    'AC05',
    'Anti-joins transverses avant Gold',
    'HAUTE',
    CASE WHEN o.n + p.n + g.n = 0 THEN 'PASS' ELSE 'FAIL' END,
    o.n::VARCHAR || ' offre(s) orpheline(s); '
        || p.n::VARCHAR || ' paiement(s) orphelin(s); '
        || g.n::VARCHAR || ' relation(s) orpheline(s) dans Gold',
    '0 offre orpheline; 0 paiement orphelin; 0 relation orpheline dans Gold',
    'Aucune relation non resolue ne doit alimenter le calcul Gold.'
FROM orphan_offers o
CROSS JOIN orphan_payments p
CROSS JOIN orphan_gold g;

-- ---------------------------------------------------------------------------
-- Oracle independant depuis Bronze pour AC06 et AC10
-- ---------------------------------------------------------------------------

CREATE OR REPLACE TEMP VIEW _oracle_offers AS
SELECT
    offer_id,
    TRIM(destination) AS destination,
    TRY_CAST(commission_rate AS DECIMAL(9, 6)) AS commission_rate
FROM bronze_offers
WHERE batch_id = getvariable('target_batch')
  AND NULLIF(TRIM(offer_id), '') IS NOT NULL
  AND NULLIF(TRIM(destination), '') IS NOT NULL
  AND TRY_CAST(commission_rate AS DECIMAL(9, 6)) BETWEEN 0 AND 1
  AND TRY_CAST(active AS BOOLEAN) = TRUE;

CREATE OR REPLACE TEMP VIEW _oracle_valid_booking_versions AS
SELECT
    b.booking_id,
    b.offer_id,
    UPPER(TRIM(b.source_channel)) AS source_channel,
    UPPER(TRIM(b.booking_status)) AS booking_status,
    TRY_CAST(b.booking_ts AS TIMESTAMP) AS booking_ts,
    TRY_CAST(b.service_date AS DATE) AS service_date,
    TRY_CAST(b.gross_amount AS DECIMAL(18, 2)) AS gross_amount,
    UPPER(TRIM(b.currency)) AS currency,
    TRY_CAST(b.updated_at AS TIMESTAMP) AS updated_at,
    o.destination,
    o.commission_rate,
    ROW_NUMBER() OVER (
        PARTITION BY b.booking_id
        ORDER BY TRY_CAST(b.updated_at AS TIMESTAMP) DESC, b.source_row_number DESC
    ) AS version_rank
FROM bronze_bookings b
JOIN _oracle_offers o USING (offer_id)
WHERE b.batch_id = getvariable('target_batch')
  AND NULLIF(TRIM(b.booking_id), '') IS NOT NULL
  AND NULLIF(TRIM(b.offer_id), '') IS NOT NULL
  AND NULLIF(TRIM(b.client_id), '') IS NOT NULL
  AND UPPER(TRIM(b.source_channel)) IN ('WEB', 'AGENCY', 'B2B_API')
  AND UPPER(TRIM(b.booking_status)) IN ('PENDING', 'CONFIRMED', 'CANCELLED')
  AND TRY_CAST(b.booking_ts AS TIMESTAMP) IS NOT NULL
  AND TRY_CAST(b.service_date AS DATE) IS NOT NULL
  AND TRY_CAST(b.updated_at AS TIMESTAMP) IS NOT NULL
  AND TRY_CAST(b.gross_amount AS DECIMAL(18, 2)) >= 0
  AND UPPER(TRIM(b.currency)) = 'EUR'
  AND TRY_CAST(b.service_date AS DATE) >= CAST(TRY_CAST(b.booking_ts AS TIMESTAMP) AS DATE);

CREATE OR REPLACE TEMP VIEW _oracle_latest_bookings AS
SELECT * EXCLUDE (version_rank)
FROM _oracle_valid_booking_versions
WHERE version_rank = 1;

CREATE OR REPLACE TEMP VIEW _oracle_valid_payment_versions AS
SELECT
    p.payment_id,
    p.booking_id,
    UPPER(TRIM(p.payment_status)) AS payment_status,
    TRY_CAST(p.amount AS DECIMAL(18, 2)) AS amount,
    UPPER(TRIM(p.currency)) AS currency,
    TRY_CAST(p.paid_at AS TIMESTAMP) AS paid_at,
    ROW_NUMBER() OVER (
        PARTITION BY p.booking_id
        ORDER BY TRY_CAST(p.paid_at AS TIMESTAMP) DESC NULLS LAST,
                 p.source_row_number DESC
    ) AS payment_rank
FROM bronze_payments p
WHERE p.batch_id = getvariable('target_batch')
  AND NULLIF(TRIM(p.payment_id), '') IS NOT NULL
  AND NULLIF(TRIM(p.booking_id), '') IS NOT NULL
  AND UPPER(TRIM(p.payment_status)) IN ('PAID', 'DECLINED', 'REFUNDED')
  AND TRY_CAST(p.amount AS DECIMAL(18, 2)) >= 0
  AND UPPER(TRIM(p.currency)) = 'EUR'
  AND (
      UPPER(TRIM(p.payment_status)) = 'DECLINED'
      OR TRY_CAST(p.paid_at AS TIMESTAMP) IS NOT NULL
  );

CREATE OR REPLACE TEMP VIEW _oracle_latest_payments AS
SELECT * EXCLUDE (payment_rank)
FROM _oracle_valid_payment_versions
WHERE payment_rank = 1;

CREATE OR REPLACE TEMP VIEW _oracle_joined AS
SELECT
    b.booking_id,
    b.service_date AS business_date,
    b.destination,
    b.booking_status,
    p.payment_status,
    b.gross_amount,
    b.commission_rate,
    b.currency,
    CASE
        WHEN b.booking_status = 'CONFIRMED'
         AND p.payment_status = 'PAID'
         AND ABS(b.gross_amount - p.amount) <= 0.01
         AND b.currency = p.currency
        THEN TRUE ELSE FALSE
    END AS is_revenue_eligible
FROM _oracle_latest_bookings b
LEFT JOIN _oracle_latest_payments p USING (booking_id);

CREATE OR REPLACE TEMP VIEW _oracle_gold AS
SELECT
    business_date,
    destination,
    COUNT(DISTINCT booking_id)::BIGINT AS confirmed_bookings,
    ROUND(SUM(gross_amount), 2) AS gross_revenue_eur,
    ROUND(SUM(gross_amount * commission_rate), 2) AS commission_revenue_eur,
    ROUND(
        ROUND(SUM(gross_amount), 2)
        - ROUND(SUM(gross_amount * commission_rate), 2),
        2
    ) AS net_revenue_eur,
    getvariable('target_batch')::VARCHAR AS batch_id
FROM _oracle_joined
WHERE is_revenue_eligible
GROUP BY business_date, destination;

-- ---------------------------------------------------------------------------
-- AC06 - Regle de reconnaissance du revenu
-- ---------------------------------------------------------------------------

INSERT INTO validation_results
WITH oracle_total AS (
    SELECT
        COALESCE(SUM(confirmed_bookings), 0) AS bookings,
        COALESCE(SUM(gross_revenue_eur), 0) AS gross
    FROM _oracle_gold
), target_total AS (
    SELECT
        COALESCE(SUM(confirmed_bookings), 0) AS bookings,
        COALESCE(SUM(gross_revenue_eur), 0) AS gross
    FROM gold_daily_revenue
    WHERE batch_id = getvariable('target_batch')
), ineligible_detail AS (
    SELECT COUNT(*) AS n
    FROM gold_revenue_detail
    WHERE booking_status <> 'CONFIRMED'
       OR payment_status <> 'PAID'
)
SELECT
    'AC06',
    'Revenu uniquement pour CONFIRMED + PAID',
    'CRITIQUE',
    CASE
        WHEN o.bookings = t.bookings
         AND ABS(o.gross - t.gross) <= 0.01
         AND i.n = 0
        THEN 'PASS' ELSE 'FAIL'
    END,
    'Gold: bookings=' || t.bookings::VARCHAR || ', gross=' || t.gross::VARCHAR
        || ', contributions ineligibles=' || i.n::VARCHAR,
    'Oracle: bookings=' || o.bookings::VARCHAR || ', gross=' || o.gross::VARCHAR,
    'CANCELLED, DECLINED et REFUNDED valent zero dans l oracle recalcule depuis Bronze.'
FROM oracle_total o
CROSS JOIN target_total t
CROSS JOIN ineligible_detail i;

-- ---------------------------------------------------------------------------
-- AC07 - Catalogues et coherence des montants
-- ---------------------------------------------------------------------------

INSERT INTO validation_results
WITH invalid_statuses AS (
    SELECT
        (SELECT COUNT(*)
         FROM silver_bookings
         WHERE batch_id = getvariable('target_batch')
           AND booking_status NOT IN ('PENDING', 'CONFIRMED', 'CANCELLED'))
        +
        (SELECT COUNT(*)
         FROM silver_payments
         WHERE batch_id = getvariable('target_batch')
           AND payment_status NOT IN ('PAID', 'DECLINED', 'REFUNDED')) AS n
), amount_mismatches AS (
    SELECT COUNT(*) AS n
    FROM silver_payments p
    JOIN silver_bookings b
      ON b.batch_id = p.batch_id
     AND b.booking_id = p.booking_id
    WHERE p.batch_id = getvariable('target_batch')
      AND (
          ABS(b.gross_amount - p.amount) > 0.01
          OR b.currency IS DISTINCT FROM p.currency
      )
)
SELECT
    'AC07',
    'Statuts autorises et concordance des montants',
    'HAUTE',
    CASE WHEN s.n + m.n = 0 THEN 'PASS' ELSE 'FAIL' END,
    s.n::VARCHAR || ' statut(s) invalide(s); '
        || m.n::VARCHAR || ' montant(s) incoherent(s)',
    '0 statut invalide; 0 ecart > 0,01 EUR',
    'Le controle est execute sur les donnees Silver acceptees.'
FROM invalid_statuses s
CROSS JOIN amount_mismatches m;

-- ---------------------------------------------------------------------------
-- AC08 - Coherence temporelle
-- ---------------------------------------------------------------------------

INSERT INTO validation_results
WITH anomalies AS (
    SELECT COUNT(*) AS n
    FROM silver_bookings
    WHERE batch_id = getvariable('target_batch')
      AND service_date < CAST(booking_ts AS DATE)
)
SELECT
    'AC08',
    'Date de service posterieure ou egale a la reservation',
    'MOYENNE',
    CASE WHEN n = 0 THEN 'PASS' ELSE 'FAIL' END,
    n::VARCHAR || ' date(s) invalide(s)',
    '0 date invalide',
    'service_date doit etre >= DATE(booking_ts).'
FROM anomalies;

-- ---------------------------------------------------------------------------
-- AC09 - Non-duplication et empreinte a comparer apres la seconde execution
-- ---------------------------------------------------------------------------

CREATE OR REPLACE TEMP VIEW _gold_fingerprint AS
SELECT
    COUNT(*) AS row_count,
    ROUND(COALESCE(SUM(gross_revenue_eur), 0), 2) AS gross_sum,
    MD5(
        COALESCE(
            STRING_AGG(
                CONCAT_WS('|',
                    business_date::VARCHAR,
                    destination,
                    confirmed_bookings::VARCHAR,
                    gross_revenue_eur::VARCHAR,
                    commission_revenue_eur::VARCHAR,
                    net_revenue_eur::VARCHAR,
                    batch_id
                ),
                '||' ORDER BY business_date, destination, batch_id
            ),
            ''
        )
    ) AS gold_md5
FROM gold_daily_revenue
WHERE batch_id = getvariable('target_batch');

INSERT INTO validation_results
WITH duplicate_groups AS (
    SELECT COUNT(*) AS n
    FROM (
        SELECT business_date, destination, batch_id
        FROM gold_daily_revenue
        WHERE batch_id = getvariable('target_batch')
        GROUP BY business_date, destination, batch_id
        HAVING COUNT(*) > 1
    ) d
)
SELECT
    'AC09A',
    'Absence de doublons apres relance',
    'HAUTE',
    CASE WHEN d.n = 0 THEN 'PASS' ELSE 'FAIL' END,
    d.n::VARCHAR || ' groupe(s) Gold duplique(s); md5=' || f.gold_md5,
    '0 doublon; meme count/somme/hash avant et apres relance',
    'Le hash affiche doit etre capture avant puis apres la seconde execution du meme batch.'
FROM duplicate_groups d
CROSS JOIN _gold_fingerprint f;

-- ---------------------------------------------------------------------------
-- AC10 - Reconciliation complete de l oracle source avec Gold
-- ---------------------------------------------------------------------------

CREATE OR REPLACE TEMP VIEW _gold_differences AS
SELECT
    COALESCE(o.business_date, g.business_date) AS business_date,
    COALESCE(o.destination, g.destination) AS destination,
    o.confirmed_bookings AS expected_bookings,
    g.confirmed_bookings AS actual_bookings,
    o.gross_revenue_eur AS expected_gross,
    g.gross_revenue_eur AS actual_gross,
    o.commission_revenue_eur AS expected_commission,
    g.commission_revenue_eur AS actual_commission,
    o.net_revenue_eur AS expected_net,
    g.net_revenue_eur AS actual_net
FROM _oracle_gold o
FULL OUTER JOIN (
    SELECT *
    FROM gold_daily_revenue
    WHERE batch_id = getvariable('target_batch')
) g
  ON o.business_date = g.business_date
 AND o.destination = g.destination
 AND o.batch_id = g.batch_id
WHERE o.business_date IS NULL
   OR g.business_date IS NULL
   OR o.confirmed_bookings IS DISTINCT FROM g.confirmed_bookings
   OR o.gross_revenue_eur IS NULL
   OR g.gross_revenue_eur IS NULL
   OR o.commission_revenue_eur IS NULL
   OR g.commission_revenue_eur IS NULL
   OR o.net_revenue_eur IS NULL
   OR g.net_revenue_eur IS NULL
   OR ABS(o.gross_revenue_eur - g.gross_revenue_eur) > 0.01
   OR ABS(o.commission_revenue_eur - g.commission_revenue_eur) > 0.01
   OR ABS(o.net_revenue_eur - g.net_revenue_eur) > 0.01;

INSERT INTO validation_results
WITH differences AS (
    SELECT COUNT(*) AS n FROM _gold_differences
)
SELECT
    'AC10',
    'Reconciliation source-cible avec oracle independant',
    'CRITIQUE',
    CASE WHEN n = 0 THEN 'PASS' ELSE 'FAIL' END,
    n::VARCHAR || ' groupe(s) different(s)',
    '0 difference',
    'L oracle parse, valide, deduplique et agrege Bronze sans reutiliser Silver.'
FROM differences;

-- ---------------------------------------------------------------------------
-- R09 - Protection des donnees personnelles
-- ---------------------------------------------------------------------------

INSERT INTO validation_results
WITH schema_anomalies AS (
    SELECT COUNT(*) AS n
    FROM (
        SELECT 'silver_bookings' AS table_name, LOWER(name) AS column_name
        FROM pragma_table_info('silver_bookings')
        UNION ALL
        SELECT 'gold_daily_revenue' AS table_name, LOWER(name) AS column_name
        FROM pragma_table_info('gold_daily_revenue')
    ) c
    WHERE column_name IN (
        'client_id', 'client_name', 'full_name', 'first_name', 'last_name',
        'email', 'phone', 'telephone', 'address', 'postal_address'
    )
), hash_anomalies AS (
    SELECT COUNT(*) AS n
    FROM silver_bookings
    WHERE batch_id = getvariable('target_batch')
      AND (
          client_id_hash IS NULL
          OR NOT REGEXP_FULL_MATCH(client_id_hash, '[0-9a-f]{64}')
      )
)
SELECT
    'R09',
    'Absence de client_id brut et pseudonymisation',
    'HAUTE',
    CASE WHEN s.n + h.n = 0 THEN 'PASS' ELSE 'FAIL' END,
    s.n::VARCHAR || ' colonne(s) sensible(s); '
        || h.n::VARCHAR || ' hash invalide(s)',
    '0 colonne sensible; SHA-256 sur 64 caracteres',
    'Bronze conserve la cle brute ; Silver la pseudonymise ; Gold ne contient aucune donnee client.'
FROM schema_anomalies s
CROSS JOIN hash_anomalies h;

-- ---------------------------------------------------------------------------
-- Sorties destinees au rapport et aux captures d ecran
-- ---------------------------------------------------------------------------

SELECT
    check_id,
    control_name,
    priority,
    status,
    actual_value,
    expected_value,
    details
FROM validation_results
ORDER BY check_id;

-- Resume global : une anomalie CRITIQUE ou HAUTE conduit a NO-GO.
-- AC09 exige en plus la preuve avant/apres relance.
SELECT
    COUNT(*) AS checks_total,
    COUNT(*) FILTER (WHERE status = 'PASS') AS checks_pass,
    COUNT(*) FILTER (WHERE status = 'FAIL') AS checks_fail,
    CASE
        WHEN COUNT(*) FILTER (
            WHERE priority IN ('CRITIQUE', 'HAUTE') AND status = 'FAIL'
        ) = 0
        THEN 'GO'
        ELSE 'NO-GO'
    END AS quality_gate_decision
FROM validation_results;

-- Preuves detaillees : ces jeux sont vides lorsque les controles passent.
SELECT * FROM _gold_differences
ORDER BY business_date, destination;

-- Empreinte AC09 a capturer avant et apres la relance du pipeline.
SELECT * FROM _gold_fingerprint;

-- Causes de quarantaine pour le reporting qualite.
SELECT
    source_entity,
    reason_code,
    COUNT(*) AS rejected_rows
FROM quarantine_records
WHERE batch_id = getvariable('target_batch')
GROUP BY source_entity, reason_code
ORDER BY source_entity, rejected_rows DESC, reason_code;
