-- gold.household_data_quality: whole-period summary per household, derived only from the
-- monthly table (contract docs/contracts/gold_household_data_quality.yaml). Facts only: no
-- threshold, no exclusion flag, no label (AC-25). A persisted view (DA-02 passed on Free Edition).
--
-- Names come from the pipeline configuration (smart_meter.catalog, smart_meter.gold_schema);
-- the pipeline substitutes ${...} before it runs the statement. A unit test substitutes the same
-- keys and runs the SELECT body on local Spark.
CREATE VIEW ${smart_meter.catalog}.${smart_meter.gold_schema}.household_data_quality AS
WITH totals AS (
  SELECT
    household_id,
    bool_or(has_household_record) AS has_household_record,
    CAST(sum(observed_readings) AS INT) AS observed_readings,
    CAST(sum(expected_readings) AS INT) AS expected_readings,
    CAST(sum(zero_readings) AS INT) AS zero_readings,
    CAST(sum(gap_count) AS INT) AS gap_count,
    min(first_reading_ts) AS first_reading_ts,
    max(last_reading_ts) AS last_reading_ts
  FROM ${smart_meter.catalog}.${smart_meter.gold_schema}.household_data_quality_monthly
  GROUP BY household_id
)
SELECT
  household_id,
  has_household_record,
  observed_readings,
  expected_readings,
  observed_readings / expected_readings AS coverage_ratio_study_period,
  CASE WHEN first_reading_ts IS NULL THEN NULL
       ELSE observed_readings
            / ((unix_seconds(last_reading_ts) - unix_seconds(first_reading_ts)) / 1800 + 1)
  END AS coverage_ratio_active_span,
  CASE WHEN observed_readings = 0 THEN NULL ELSE zero_readings / observed_readings END
    AS zero_share,
  gap_count,
  first_reading_ts,
  last_reading_ts
FROM totals;
