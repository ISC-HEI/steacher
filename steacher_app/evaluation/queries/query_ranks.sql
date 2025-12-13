




WITH parsed_rankings AS (
    SELECT 
        e.id as eval_id,
        r.key as response_key,
        r.value ->> 'model' as model_name,
        rank.value::int as rank
    FROM evaluation_modelcomparisoneval e
    CROSS JOIN LATERAL jsonb_each(e.model_responses) r
    CROSS JOIN LATERAL jsonb_each_text(e.rankings) rank
    WHERE NOT e.skipped
      AND rank.key = r.key
      AND r.value ->> 'model' IS NOT NULL
),
ranking_stats AS (
    SELECT
        pr.eval_id,
        pr.response_key,
        pr.model_name,
        pr.rank,
        COUNT(*) OVER (PARTITION BY pr.eval_id) as total_responses,
        MIN(pr.rank) OVER (PARTITION BY pr.eval_id) as best_rank_in_eval,
        MAX(pr.rank) OVER (PARTITION BY pr.eval_id) as worst_rank_in_eval
    FROM parsed_rankings pr
)
SELECT 
    model_name,
    COUNT(*) as total_evaluations,
    COUNT(*) FILTER (WHERE rank = 1) as first_place_count,
    COUNT(*) FILTER (WHERE rank = best_rank_in_eval) as best_rank_count,
    ROUND(AVG(rank)::numeric, 2) as avg_rank,
    ROUND(AVG(rank::numeric / total_responses)::numeric, 3) as avg_relative_rank,
    COUNT(*) FILTER (WHERE rank = worst_rank_in_eval) as worst_rank_count,
    COUNT(*) FILTER (WHERE rank = total_responses) as last_place_count
FROM ranking_stats
GROUP BY model_name
ORDER BY avg_rank ASC, first_place_count DESC;

-- | model_name                       | total_evaluations | first_place_count | best_rank_count | avg_rank | avg_relative_rank | worst_rank_count | last_place_count |
-- | -------------------------------- | ----------------- | ----------------- | --------------- | -------- | ----------------- | ---------------- | ---------------- |
-- | moonshotai/kimi-k2-thinking      | 23                | 17                | 17              | 1.35     | 0.337             | 6                | 0                |
-- | gemini-2.5-flash                 | 30                | 22                | 22              | 1.37     | 0.342             | 8                | 0                |
-- | google/gemini-3-pro-preview      | 13                | 8                 | 8               | 1.69     | 0.423             | 3                | 2                |
-- | meta-llama/llama-3.1-8b-instruct | 12                | 6                 | 6               | 2.08     | 0.521             | 7                | 3                |
-- | openai/gpt-oss-120b              | 14                | 4                 | 4               | 2.36     | 0.589             | 8                | 2                |
-- | GDX/gpt-oss:120b                 | 8                 | 1                 | 1               | 2.75     | 0.688             | 6                | 2                |
-- | swiss-ai/apertus-70b-instruct    | 11                | 2                 | 2               | 3.27     | 0.818             | 10               | 8                |


