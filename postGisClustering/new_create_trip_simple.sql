CREATE TABLE trip_simple AS
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
