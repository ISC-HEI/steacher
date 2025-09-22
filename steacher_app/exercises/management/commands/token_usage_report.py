'''
Small script to report token usage and costs for a given channel.
Will need to be updated with latest pricing information.

python manage.py token_usage_report  --channel exercise_guidance
python manage.py token_usage_report  --channel authoring
'''

from collections import defaultdict
from dataclasses import dataclass
from decimal import Decimal
from typing import Dict, Iterable, Optional, Tuple

from django.core.management.base import BaseCommand
from django.contrib.contenttypes.models import ContentType
from django.db.models import Q
from django.utils import timezone

from exercises.models import Trace, Attempt, Exercise


@dataclass
class UsageCounts:
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    cached_tokens: int = 0

    def add(self, other: "UsageCounts") -> None:
        self.prompt_tokens += other.prompt_tokens
        self.completion_tokens += other.completion_tokens
        self.total_tokens += other.total_tokens
        self.cached_tokens += other.cached_tokens


def _extract_usage(meta: dict) -> UsageCounts:
    """
    Normalize token usage from assistant_metadata.

    Supports shapes used in this codebase:
    - assistant_metadata['usage'] with keys prompt_tokens, completion_tokens, total_tokens (OpenAI-like)
    - assistant_metadata['usage_data'] with keys prompt_token_count, candidates_token_count, total_token_count, cached_content_token_count (Gemini-like)
    - Fallback to zeros if missing.
    """
    if not isinstance(meta, dict):
        return UsageCounts()

    usage = meta.get("usage")
    usage_data = meta.get("usage_data")

    prompt = 0
    completion = 0
    total = 0
    cached = 0

    if isinstance(usage, dict):
        prompt = int(usage.get("prompt_tokens") or 0)
        completion = int(usage.get("completion_tokens") or 0)
        total = int(usage.get("total_tokens") or 0)
        cached = int(usage.get("cached_tokens") or 0)

    if isinstance(usage_data, dict):
        # Gemini naming
        prompt = int(usage_data.get("prompt_token_count") or prompt)
        completion = int(usage_data.get("candidates_token_count") or completion)
        total = int(usage_data.get("total_token_count") or (prompt + completion))
        cached = int(usage_data.get("cached_content_token_count") or cached)

    # Some traces in fetch_ai_guidance store usage under assistant_metadata.usage with Gemini names
    if isinstance(usage, dict) and total == 0 and (usage.get("total_token_count") is not None):
        prompt = int(usage.get("prompt_token_count") or prompt)
        completion = int(usage.get("candidates_token_count") or completion)
        total = int(usage.get("total_token_count") or (prompt + completion))
        cached = int(usage.get("cached_content_token_count") or cached)

    # Fallback compute total if still zero
    if total == 0 and (prompt or completion):
        total = prompt + completion

    return UsageCounts(
        prompt_tokens=prompt,
        completion_tokens=completion,
        total_tokens=total,
        cached_tokens=cached,
    )


def _price_per_token(model: Optional[str]) -> Tuple[Decimal, Decimal, Decimal]:
    """
    Return (input_price, output_price, cached_input_price) in USD per 1M tokens for the model name.
    Cached input price defaults to the same as input if not explicitly discounted.
    """
    # Prices per 1M tokens
    PRICES = {
        # Provided by user (per 1M tokens):
        # 2.5 Flash: $0.30 input, $2.50 output
        # 2.5 Pro:   $1.25 input, $10.00 output
        "gemini-2.5-flash": (Decimal("0.30"), Decimal("2.50"), Decimal("0.30")),
        "gemini-2.5-pro": (Decimal("1.25"), Decimal("10.00"), Decimal("1.25")),
        # Synonyms (if model names differ in metadata)
        "gpt-2.5-flash": (Decimal("0.30"), Decimal("2.50"), Decimal("0.30")),
        "gpt-2.5-pro": (Decimal("1.25"), Decimal("10.00"), Decimal("1.25")),
    }
    default = (Decimal("0.00"), Decimal("0.00"), Decimal("0.00"))
    if not model:
        print(f"No model name provided: {model!r}")
        return default
    # Find direct match or prefix match
    if model in PRICES:
        return PRICES[model]
    for key, val in PRICES.items():
        if model.startswith(key):
            return val
    return default


def _estimate_cost_usd(model: Optional[str], usage: UsageCounts) -> Decimal:
    in_price, out_price, cached_in_price = _price_per_token(model)
    # Convert tokens to thousands
    pt_m = Decimal(usage.prompt_tokens) / Decimal(1_000_000)
    ct_m = Decimal(usage.completion_tokens) / Decimal(1_000_000)
    cached_m = Decimal(usage.cached_tokens) / Decimal(1_000_000)
    return pt_m * in_price + ct_m * out_price - cached_m * in_price + cached_m * cached_in_price


class Command(BaseCommand):
    help = "Report token usage totals and averages per user and per question (attempt/exercise)."

    def add_arguments(self, parser):
        parser.add_argument("--since", type=str, default=None, help="ISO date/time (UTC) to filter traces created_at >= since")
        parser.add_argument("--until", type=str, default=None, help="ISO date/time (UTC) to filter traces created_at < until")
        parser.add_argument("--channel", action="append", default=None, help="Filter by channel (repeatable). e.g., --channel exercise_guidance")
        parser.add_argument("--per_user", action="store_true", help="Show per-user aggregates")
        parser.add_argument("--per_exercise", action="store_true", help="Show per-exercise aggregates")
        parser.add_argument("--per_attempt", action="store_true", help="Show per-attempt aggregates")
        parser.add_argument("--limit", type=int, default=None, help="Limit number of rows printed for detailed sections")

    def handle(self, *args, **options):
        qs = Trace.objects.all()

        # Date filtering
        since = options.get("since")
        until = options.get("until")
        if since:
            try:
                qs = qs.filter(created_at__gte=since)
            except Exception:
                pass
        if until:
            try:
                qs = qs.filter(created_at__lt=until)
            except Exception:
                pass

        # Channel filtering
        channels = options.get("channel") or []
        if channels:
            qs = qs.filter(channel__in=channels)

        # Aggregate totals
        total_usage = UsageCounts()
        total_cost = Decimal("0")
        num_traces = 0

        # Per user
        per_user_usage: Dict[int, UsageCounts] = defaultdict(UsageCounts)
        per_user_cost: Dict[int, Decimal] = defaultdict(lambda: Decimal("0"))

        # Per attempt and per exercise
        per_attempt_usage: Dict[int, UsageCounts] = defaultdict(UsageCounts)
        per_attempt_cost: Dict[int, Decimal] = defaultdict(lambda: Decimal("0"))
        per_exercise_usage: Dict[int, UsageCounts] = defaultdict(UsageCounts)
        per_exercise_cost: Dict[int, Decimal] = defaultdict(lambda: Decimal("0"))

        # Prefetch attempt/exercise mapping
        attempt_ct = ContentType.objects.get_for_model(Attempt)
        exercise_ct = ContentType.objects.get_for_model(Exercise)

        for tr in qs.iterator():
            meta = tr.assistant_metadata or {}
            usage = _extract_usage(meta)
            model_name = (meta or {}).get("model")

            total_usage.add(usage)
            cost = _estimate_cost_usd(model_name, usage)
            total_cost += cost
            num_traces += 1

            # Per user
            per_user_usage[tr.user_id].add(usage)
            per_user_cost[tr.user_id] += cost

            # Per attempt/exercise
            if tr.content_type_id == attempt_ct.id:
                per_attempt_usage[tr.object_id].add(usage)
                per_attempt_cost[tr.object_id] += cost
                # Link attempt -> exercise id for per_exercise rollup
                try:
                    attempt = Attempt.objects.only("exercise_id").get(id=tr.object_id)
                    if attempt.exercise_id:
                        per_exercise_usage[attempt.exercise_id].add(usage)
                        per_exercise_cost[attempt.exercise_id] += cost
                except Attempt.DoesNotExist:
                    pass
            elif tr.content_type_id == exercise_ct.id:
                per_exercise_usage[tr.object_id].add(usage)
                per_exercise_cost[tr.object_id] += cost

        # Print summary
        self.stdout.write("=== Token Usage Summary ===")
        self.stdout.write(f"Traces: {num_traces}")
        self.stdout.write(
            f"Totals — prompt={total_usage.prompt_tokens}, completion={total_usage.completion_tokens}, cached={total_usage.cached_tokens}, total={total_usage.total_tokens}"
        )
        self.stdout.write(f"Estimated total cost (USD): {total_cost:.4f}")

        # Averages across all traces
        if num_traces:
            self.stdout.write(
                f"Average per trace — prompt={total_usage.prompt_tokens // num_traces}, completion={total_usage.completion_tokens // num_traces}, cached={total_usage.cached_tokens // num_traces}, total={total_usage.total_tokens // num_traces}"
            )

        limit = options.get("limit")

        if options.get("per_user"):
            self.stdout.write("\n=== Per-User Averages ===")
            # Fetch usernames in one go
            user_ids = list(per_user_usage.keys())
            id_to_username = {u.id: u.get_username() for u in type(Trace._meta.get_field("user").remote_field.model).objects.filter(id__in=user_ids)}
            rows = []
            for uid, u in per_user_usage.items():
                traces_count = Trace.objects.filter(user_id=uid).count()
                rows.append((id_to_username.get(uid, str(uid)), u, per_user_cost[uid], traces_count))
            # Sort by cost desc
            rows.sort(key=lambda r: r[2], reverse=True)
            shown = 0
            for username, u, cost, traces_count in rows:
                if limit is not None and shown >= limit:
                    break
                shown += 1
                avg_prompt = (u.prompt_tokens // traces_count) if traces_count else 0
                avg_completion = (u.completion_tokens // traces_count) if traces_count else 0
                avg_cached = (u.cached_tokens // traces_count) if traces_count else 0
                avg_total = (u.total_tokens // traces_count) if traces_count else 0
                self.stdout.write(
                    f"{username}: traces={traces_count}, total_cost=${cost:.4f}, avg_prompt={avg_prompt}, avg_completion={avg_completion}, avg_cached={avg_cached}, avg_total={avg_total}"
                )

        if options.get("per_attempt"):
            self.stdout.write("\n=== Per-Attempt Totals ===")
            attempt_ids = list(per_attempt_usage.keys())
            id_to_attempt = {a.id: a for a in Attempt.objects.filter(id__in=attempt_ids).select_related("exercise", "user")}
            rows = []
            for aid, u in per_attempt_usage.items():
                att = id_to_attempt.get(aid)
                title = "?"
                user_label = "?"
                if att:
                    title = getattr(att.exercise, "title", None) or str(att.exercise_id)
                    user_label = att.user.get_username()
                rows.append((aid, title, user_label, u, per_attempt_cost[aid]))
            rows.sort(key=lambda r: r[4], reverse=True)
            shown = 0
            for aid, title, user_label, u, cost in rows:
                if limit is not None and shown >= limit:
                    break
                shown += 1
                self.stdout.write(
                    f"attempt#{aid} ({user_label} / {title}): prompt={u.prompt_tokens}, completion={u.completion_tokens}, cached={u.cached_tokens}, total={u.total_tokens}, cost=${cost:.4f}"
                )

        if options.get("per_exercise"):
            self.stdout.write("\n=== Per-Exercise Totals ===")
            ex_ids = list(per_exercise_usage.keys())
            id_to_ex = {e.id: e for e in Exercise.objects.filter(id__in=ex_ids).select_related("module__course")}
            rows = []
            for eid, u in per_exercise_usage.items():
                ex = id_to_ex.get(eid)
                title = getattr(ex, "title", None) or str(eid)
                rows.append((eid, title, u, per_exercise_cost[eid]))
            rows.sort(key=lambda r: r[3], reverse=True)
            shown = 0
            for eid, title, u, cost in rows:
                if limit is not None and shown >= limit:
                    break
                shown += 1
                self.stdout.write(
                    f"exercise#{eid} ({title}): prompt={u.prompt_tokens}, completion={u.completion_tokens}, cached={u.cached_tokens}, total={u.total_tokens}, cost=${cost:.4f}"
                )


