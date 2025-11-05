CREATE TABLE trip_simple AS
SELECT
  trip_id,
  start_time AS time,
  polyline_json -> 0 AS first_coord,
  polyline_json -> (jsonb_array_length(polyline_json) - 1) AS last_coord,

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
  ) AS dropoff

FROM trip;
