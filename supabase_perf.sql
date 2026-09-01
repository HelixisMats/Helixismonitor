-- ============================================================
--  Helixis LC Monitor — performance pack
--  Run once in the Supabase SQL Editor (Database → SQL Editor → New query).
--
--  Why: the app currently pulls RAW rows and aggregates in Python.
--  The 90-day overview alone can mean ~750 000 rows fetched 1000 at a
--  time — that is the slow first open of the History tab. These three
--  functions do the aggregation inside Postgres and return a few
--  hundred rows instead.
--
--  Safe to re-run. Creates nothing that the old code depends on, so the
--  app keeps working before and after; it detects the functions and
--  uses them automatically once they exist.
-- ============================================================

-- ── 1. Index for time-range scans ────────────────────────────
-- BRIN is tiny (a few KB) and ideal for append-only time series:
-- rows arrive in created_at order, so block ranges stay tight.
CREATE INDEX IF NOT EXISTS idx_sr_created_at_brin
  ON sensor_readings USING BRIN (created_at);

ANALYZE sensor_readings;


-- ── 2. Daily energy overview (replaces the 90-day raw pull) ──
-- Returns one row per day. Trapezoid integration of power → kWh,
-- partitioned per local day so it matches what the Python version
-- computed (which grouped by day first, then integrated).
--
-- max_gap_minutes: if set, segments longer than this are treated as an
-- outage and skipped instead of being integrated across. Leave NULL for
-- exact parity with the current numbers; set to e.g. 60 if you would
-- rather not have long dropouts inflate a day's kWh.
CREATE OR REPLACE FUNCTION daily_energy_summary(
  days_back       int DEFAULT 90,
  max_gap_minutes int DEFAULT NULL
)
RETURNS TABLE (day date, kwh numeric, peak_irr numeric)
LANGUAGE sql
STABLE
AS $$
  WITH p AS (
    SELECT
      (created_at AT TIME ZONE 'Europe/Stockholm')::date AS d,
      created_at,
      value,
      lag(created_at) OVER (
        PARTITION BY (created_at AT TIME ZONE 'Europe/Stockholm')::date
        ORDER BY created_at) AS prev_t,
      lag(value) OVER (
        PARTITION BY (created_at AT TIME ZONE 'Europe/Stockholm')::date
        ORDER BY created_at) AS prev_v
    FROM sensor_readings
    WHERE sensor = 'power'
      AND created_at >= now() - make_interval(days => days_back)
  ),
  seg AS (
    SELECT
      d,
      ((value + prev_v) / 2.0)
        * (extract(epoch FROM (created_at - prev_t)) / 3600.0) AS kwh_seg
    FROM p
    WHERE prev_t IS NOT NULL
      AND (max_gap_minutes IS NULL
           OR created_at - prev_t <= make_interval(mins => max_gap_minutes))
  ),
  e AS (
    SELECT d, greatest(0.0, sum(kwh_seg)) AS kwh
    FROM seg GROUP BY d
  ),
  i AS (
    SELECT
      (created_at AT TIME ZONE 'Europe/Stockholm')::date AS d,
      max(value) AS peak_irr
    FROM sensor_readings
    WHERE sensor = 'irradiance'
      AND created_at >= now() - make_interval(days => days_back)
    GROUP BY 1
  )
  SELECT
    d                                          AS day,
    round(coalesce(e.kwh, 0)::numeric, 2)      AS kwh,
    round(coalesce(i.peak_irr, 0)::numeric, 0) AS peak_irr
  FROM e FULL JOIN i USING (d)
  ORDER BY 1;
$$;


-- ── 3. Bucketed history (replaces the raw range pull) ────────
-- Averages readings into fixed time buckets so a month of data comes
-- back as ~1000 points per sensor instead of ~250 000 rows.
--
-- Returns ONE json row on purpose: PostgREST's max-rows limit (1000 on
-- this project) applies to function results too, and a single json
-- value slips under it without needing pagination.
CREATE OR REPLACE FUNCTION history_bucketed_json(
  t_from         timestamptz,
  t_to           timestamptz,
  bucket_seconds int    DEFAULT 60,
  sensors        text[] DEFAULT NULL
)
RETURNS json
LANGUAGE sql
STABLE
AS $$
  SELECT coalesce(json_agg(row_to_json(t) ORDER BY t.b, t.s), '[]'::json)
  FROM (
    SELECT
      to_timestamp(
        floor(extract(epoch FROM created_at) / bucket_seconds) * bucket_seconds
      ) AS b,
      sensor            AS s,
      avg(value)::real  AS v
    FROM sensor_readings
    WHERE created_at >= t_from
      AND created_at <= t_to
      AND (sensors IS NULL OR sensor = ANY(sensors))
    GROUP BY 1, 2
  ) t;
$$;


-- ── 4. Exact per-sensor stats for the summary table ──────────
-- Bucket averages would flatten real peaks, so min/max/mean for the
-- summary table come straight from the raw rows — still one cheap
-- aggregate query rather than a full download.
CREATE OR REPLACE FUNCTION sensor_window_stats(
  t_from timestamptz,
  t_to   timestamptz
)
RETURNS TABLE (sensor text, v_min real, v_max real, v_mean real)
LANGUAGE sql
STABLE
AS $$
  SELECT sensor,
         min(value)::real  AS v_min,
         max(value)::real  AS v_max,
         avg(value)::real  AS v_mean
  FROM sensor_readings
  WHERE created_at >= t_from AND created_at <= t_to
  GROUP BY sensor;
$$;


-- ── 5. Let the app call them ─────────────────────────────────
-- Match whichever role your app key uses. anon = public anon key,
-- authenticated = logged-in users. Harmless if a role is unused.
GRANT EXECUTE ON FUNCTION daily_energy_summary(int, int)                     TO anon, authenticated;
GRANT EXECUTE ON FUNCTION history_bucketed_json(timestamptz, timestamptz, int, text[]) TO anon, authenticated;
GRANT EXECUTE ON FUNCTION sensor_window_stats(timestamptz, timestamptz)      TO anon, authenticated;


-- ── Check it worked ──────────────────────────────────────────
-- SELECT * FROM daily_energy_summary(7);
-- SELECT json_array_length(history_bucketed_json(now() - interval '1 day', now(), 300));
-- SELECT * FROM sensor_window_stats(now() - interval '1 day', now());
