# 0002. Aiven Kafka with SASL_SSL SCRAM and credentials in a secret scope

| Attribute | Value |
|---|---|
| **Status** | Accepted |
| **Date** | 2026-10-15 |
| **Deciders** | Christian |
| **Related** | METER_INGESTION; FR-03, FR-05, FR-15, NFR-05; AC-07, AC-10, AC-29; D-11, D-12, D-13; ADR 0001, 0006 |

Status values: `Proposed`, `Accepted`, `Superseded by NNNN`, `Deprecated`.

## Context

Post-cutoff readings travel from a local replay producer (Docker) to Databricks through topic
`meter-readings` (contract `docs/contracts/meter-readings.yaml`). The broker must be free of
charge and permanent (D-12: Aiven free tier; Confluent Cloud and Redpanda Serverless are trials).
Serverless compute has no keystore files or init scripts, so the authentication method must work
with options passed to the Spark Kafka source. Golden rule 2 forbids credentials in code,
configuration, notebooks and commits. Serverless reached the broker over TCP (A-01, 2026-10-06);
the SASL mechanism (A-06), inline PEM truststore (A-03) and secret scopes on Free Edition (DA-09)
are still to be confirmed (ADR 0001).

## Decision drivers

- Zero cost and no expiry of the broker.
- No client keystore files on serverless.
- Credentials never in tracked files (NFR-05, AC-29).
- One set of values for the producer and the consumer, stored in two places only: the Databricks
  secret scope and the git-ignored local `.env`.

## Options considered

| Option | Pros | Cons |
|---|---|---|
| **Aiven free tier, SASL_SSL with SCRAM-SHA-256, CA as inline PEM, secrets in scope `smart_meter`** | Username and password only; CA certificate is public data; works with Spark options | Mechanism availability and inline PEM support to be proven (A-03, A-06) |
| Aiven with mutual TLS (client certificate and key) | Aiven default for service users | Needs a client keystore or key material on serverless; a private key would have to be handled as a file |
| SASL/PLAIN over TLS | Simplest configuration | Password sent to the broker in clear inside TLS; weaker than SCRAM |

## Decision

We will use the Aiven free-tier Kafka service with `security.protocol = SASL_SSL` and
`sasl.mechanism = SCRAM-SHA-256` (bundle variable `kafka_sasl_mechanism`, so a different SCRAM
variant is a configuration change), pass the project CA as inline PEM
(`kafka.ssl.truststore.type = PEM`), and read the bootstrap servers, SASL username, SASL password
and CA PEM from the Databricks secret scope `smart_meter` (keys `kafka-bootstrap-servers`,
`kafka-sasl-username`, `kafka-sasl-password`, `kafka-ca-pem`). The local producer reads the same
values from the git-ignored `.env` (`KAFKA_BOOTSTRAP`, `KAFKA_USERNAME`, `KAFKA_PASSWORD`,
`KAFKA_SASL_MECHANISM`, `KAFKA_CA_PATH`). The JAAS configuration is built at run time from secret
values and never printed. The producer is idempotent with `acks=all`; end-to-end delivery is
at-least-once and Silver deduplicates (ADR 0005).

## Consequences

- **Positive:** No key material on serverless; credential rotation is a secret update, not a
  deploy; the repository scan of AC-29 has nothing to find.
- **Negative:** The free service powers off after inactivity and must be powered on before a run
  (runbook step); short retention means the topic is not a replay source (ADR 0006).
- **What would make us revisit this:** Aiven removing SCRAM from the free plan, inline PEM being
  rejected (fallback: CA file in a Volume, ADR 0001), or a move to a managed broker with
  workload identity.
