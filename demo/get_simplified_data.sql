CREATE TABLE trip_simple AS
SELECT
  trip_id,
  start_time AS time,
  polyline_json -> 0 AS first_coord,
  polyline_json -> (jsonb_array_length(polyline_json) - 1) AS last_coord
FROM trip;
