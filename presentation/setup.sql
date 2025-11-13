CREATE TABLE IF NOT EXISTS trip_simple AS
SELECT
  trip_id,
  start_time AS time,

  -- pickup point (longitude, latitude)
  ST_SetSRID(
    ST_MakePoint(
      ((polyline_json -> 0)::json->>0)::numeric,
      ((polyline_json -> 0)::json->>1)::numeric
    ),
    4326
  ) AS pickup,

  -- dropoff point
  ST_SetSRID(
    ST_MakePoint(
      ((polyline_json -> (jsonb_array_length(polyline_json) - 1))::json->>0)::numeric,
      ((polyline_json -> (jsonb_array_length(polyline_json) - 1))::json->>1)::numeric
    ),
    4326
  ) AS dropoff,

  -- is_weekend flag
  CASE
    WHEN EXTRACT(DOW FROM start_time) IN (0, 6) THEN TRUE
    ELSE FALSE
  END AS is_weekend

FROM trip;

-- Add indexes for faster queries
CREATE INDEX IF NOT EXISTS idx_trip_simple_time ON trip_simple(time);
CREATE INDEX IF NOT EXISTS idx_trip_simple_pickup ON trip_simple USING GIST(pickup);
CREATE INDEX IF NOT EXISTS idx_trip_simple_dropoff ON trip_simple USING GIST(dropoff);
CREATE INDEX IF NOT EXISTS idx_trip_simple_is_weekend ON trip_simple(is_weekend);