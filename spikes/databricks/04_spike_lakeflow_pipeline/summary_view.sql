-- Spike 04 (DA-02): a persisted view created from a pipeline SQL file.
-- Pass: after the update, `${spike.catalog}.gold.spike_summary` is visible in Unity Catalog
-- (information_schema.tables, table_type = 'VIEW'). Fallback: a materialized view, through /iterate.
CREATE VIEW ${spike.catalog}.gold.spike_summary AS
SELECT
  household_id,
  CAST(sum(reading_count) AS INT) AS observed_readings,
  sum(total_energy_kwh) AS total_energy_kwh
FROM ${spike.catalog}.gold.spike_daily
GROUP BY household_id;
