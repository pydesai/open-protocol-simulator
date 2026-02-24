# REST API Examples

## Health

```bash
curl -s http://localhost:8080/api/v1/health | jq
```

## Switch Profile

```bash
curl -s -X PUT http://localhost:8080/api/v1/profiles/active \
  -H 'content-type: application/json' \
  -d '{"profile":"cleco"}' | jq
```

## List Sessions

```bash
curl -s http://localhost:8080/api/v1/sessions | jq
```

## Inject Tightening Event

```bash
curl -s -X POST http://localhost:8080/api/v1/events/tightening \
  -H 'content-type: application/json' \
  -d '{"payload":{"torque_nm":12.7,"angle_deg":144.0,"ok":true}}' | jq
```

## Run Scenario

```bash
curl -s -X POST http://localhost:8080/api/v1/scenarios/run \
  -H 'content-type: application/json' \
  -d '{"name":"tightening_burst","payload":{}}' | jq
```

## Mutate Domain State

```bash
curl -s -X PUT http://localhost:8080/api/v1/state/tool \
  -H 'content-type: application/json' \
  -d '{"payload":{"enabled":false,"primary_tool":"01","calibration_value":"0.00","paired":false}}' | jq
```

