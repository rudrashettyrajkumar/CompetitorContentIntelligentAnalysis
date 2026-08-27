# Import format (`ImportAdapter`)

Use this when you already have a competitor's LinkedIn data from a manual export or a
third-party tool and want to feed it into the pipeline without any scraping.

## Directory layout

```
data/imports/
  <slug>/
    profile.json
    posts.json          # or posts.csv (JSON wins if both exist)
```

`<slug>` is the LinkedIn **company slug** — the last path segment of the company URL.
For `https://www.linkedin.com/company/nimbus-analytics` the slug is `nimbus-analytics`.

The base directory defaults to `data/imports/` and can be overridden:
`ImportAdapter(imports_dir="/path/to/exports")`.

## `profile.json`

A single JSON object. All fields are optional; unknown fields are ignored.

```json
{
  "name": "Nimbus Analytics",
  "linkedin_url": "https://www.linkedin.com/company/nimbus-analytics",
  "description": "Analytics platform for mid-market ops teams.",
  "industry": "Data & Analytics SaaS",
  "website": "https://www.nimbus-analytics.example",
  "followers": 48200,
  "geographies": ["North America", "United Kingdom"],
  "services": ["platform licensing", "professional services"],
  "target_audience": "mid-market operations leaders",
  "positioning": "The self-serve alternative to legacy BI."
}
```

`geographies` / `services` may also be given as a comma- or semicolon-separated string.

## `posts.json`

Either a JSON array of post objects, or `{ "posts": [ ... ] }`.

```json
[
  {
    "url": "https://www.linkedin.com/feed/update/urn:li:activity:7100000000000000000",
    "posted_at": "2026-08-01T14:30:00",
    "content": "Swipe through our Q3 benchmarks. #Analytics #Benchmarks",
    "media_type": "carousel",
    "reactions": 412,
    "comments": 37,
    "reposts": 12,
    "hashtags": ["Analytics", "Benchmarks"]
  }
]
```

| field | required | notes |
|-------|----------|-------|
| `url` | yes | must be unique — it is the dedupe key |
| `posted_at` | yes | ISO 8601 datetime |
| `content` | yes | post body text |
| `media_type` | no | one of `image, carousel, video, text, poll, article, document, unknown`; anything else becomes `unknown`; default `unknown` |
| `reactions`, `comments`, `reposts` | no | integers; omit or leave blank if unknown |
| `hashtags` | no | array, or comma/semicolon-separated string; if omitted, parsed from `content` |

## `posts.csv`

Same columns as the JSON fields, one post per row, with a header line:

```csv
url,posted_at,content,media_type,reactions,comments,reposts,hashtags
https://www.linkedin.com/feed/update/urn:li:activity:7100000000000000001,2026-08-02T09:00:00,"New guide is live. #Guide",document,208,11,6,Guide
```

Blank numeric cells are treated as "unknown". `hashtags` is comma- or
semicolon-separated.

## Behaviour

- `fetch_posts(url, since)` returns only posts with `posted_at >= since`, sorted oldest
  to newest.
- A missing directory or malformed file raises `ImportDataError`; the collector records
  it against the run and continues with the next competitor.
