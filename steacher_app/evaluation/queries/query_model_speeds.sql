SELECT
    r.value ->> 'model' as model_name,
    COUNT(*) as response_count,
    ROUND(AVG(COALESCE(
        (r.value -> 'metadata' ->> 'response_time_seconds')::numeric,
        (r.value -> 'metadata' ->> 'time_taken')::numeric
    ))::numeric, 3) as avg_response_time_sec,
    ROUND(MIN(COALESCE(
        (r.value -> 'metadata' ->> 'response_time_seconds')::numeric,
        (r.value -> 'metadata' ->> 'time_taken')::numeric
    ))::numeric, 3) as min_response_time_sec,
    ROUND(MAX(COALESCE(
        (r.value -> 'metadata' ->> 'response_time_seconds')::numeric,
        (r.value -> 'metadata' ->> 'time_taken')::numeric
    ))::numeric, 3) as max_response_time_sec,
    ROUND(AVG((r.value -> 'metadata' -> 'usage' ->> 'completion_tokens')::int)::numeric, 1) as avg_completion_tokens,
    ROUND(AVG((r.value -> 'metadata' -> 'usage' ->> 'completion_tokens')::numeric /
        NULLIF(COALESCE(
            (r.value -> 'metadata' ->> 'response_time_seconds')::numeric,
            (r.value -> 'metadata' ->> 'time_taken')::numeric
        ), 0))::numeric, 1) as avg_tokens_per_second
FROM evaluation_modelcomparisoneval e
CROSS JOIN LATERAL jsonb_each(e.model_responses) r
WHERE COALESCE(
        (r.value -> 'metadata' ->> 'response_time_seconds')::numeric,
        (r.value -> 'metadata' ->> 'time_taken')::numeric
    ) IS NOT NULL
GROUP BY r.value ->> 'model'
ORDER BY avg_response_time_sec ASC;


-- | model_name                       | response_count | avg_response_time_sec | min_response_time_sec | max_response_time_sec | avg_completion_tokens | avg_tokens_per_second |
-- | -------------------------------- | -------------- | --------------------- | --------------------- | --------------------- | --------------------- | --------------------- |
-- | google/gemini-2.5-flash          | 6              | 0.867                 | 0.707                 | 1.226                 | 56.8                  | 67.0                  |
-- | meta-llama/llama-3.1-8b-instruct | 5              | 2.132                 | 0.675                 | 4.046                 | 104.0                 | 63.0                  |
-- | openai/gpt-oss-120b              | 4              | 4.150                 | 1.075                 | 7.499                 | 281.8                 | 92.9                  |
-- | gemini-2.5-flash                 | 48             | 4.198                 | 0.507                 | 15.310                | 83.0                  | 27.7                  |
-- | swiss-ai/apertus-70b-instruct    | 4              | 4.301                 | 2.467                 | 6.269                 | 180.0                 | 40.2                  |
-- | google/gemini-3-pro-preview      | 6              | 12.969                | 7.186                 | 22.695                | 1103.8                | 81.3                  |
-- | GDX/gpt-oss:120b                 | 3              | 20.814                | 3.490                 | 34.341                | 133.3                 | 11.8                  |
-- | moonshotai/kimi-k2-thinking      | 10             | 45.975                | 3.524                 | 188.856               | 1424.2                | 76.1                  |