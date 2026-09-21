# HTTP examples — Agent JSON Reliability

Local default:

```bash
export PUBLIC_BASE_URL="${PUBLIC_BASE_URL:-http://127.0.0.1:8770}"
```

Do not substitute a temporary tunnel hostname into git as the canonical URL.

## Positive: fenced JSON with trailing comma

```bash
curl -s -X POST "${PUBLIC_BASE_URL}/v1/json/reliable" \
  -H "content-type: application/json" \
  -d '{"text":"```json\n{\"name\":\"alice\",\"age\":30,}\n```","schema":{"type":"object","required":["name","age"]}}'
```

Expect `valid_original=false`, `repaired=true`, `valid_final=true`.

## Refusal: truncated object

```bash
curl -s -X POST "${PUBLIC_BASE_URL}/v1/json/reliable" \
  -H "content-type: application/json" \
  -d '{"text":"{\"user\":"}'
```

Expect `valid_final=false` and `unsafe_or_ambiguous=true` or `repaired=false`.

## Optional source tag

```bash
curl -s "${PUBLIC_BASE_URL}/?source=github"
```
