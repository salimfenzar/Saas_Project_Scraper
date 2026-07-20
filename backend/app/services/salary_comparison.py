from collections import defaultdict
from decimal import Decimal, ROUND_HALF_UP

from app.database import supabase


class SalaryComparisonError(Exception):
    pass


def calculate_percentage_change(
    old_amount: float,
    new_amount: float,
) -> float | None:
    if old_amount == 0:
        return None

    percentage = (
        (Decimal(str(new_amount)) - Decimal(str(old_amount)))
        / Decimal(str(old_amount))
        * Decimal("100")
    )

    return float(
        percentage.quantize(
            Decimal("0.01"),
            rounding=ROUND_HALF_UP,
        )
    )


def get_salary_values(salary_table_id: str) -> list[dict]:
    result = (
        supabase.table("salary_scale_rows")
        .select(
            "id,scale_name,step_name,amount,"
            "component_type,amount_period"
        )
        .eq("salary_table_id", salary_table_id)
        .execute()
    )

    return result.data or []


def build_value_key(row: dict) -> tuple[str, str, str, str]:
    return (
        row["scale_name"],
        row.get("step_name") or "",
        row["component_type"],
        row["amount_period"],
    )


def compare_salary_tables(
    old_salary_table_id: str,
    new_salary_table_id: str,
) -> dict:
    old_rows = get_salary_values(old_salary_table_id)
    new_rows = get_salary_values(new_salary_table_id)

    if not old_rows:
        raise SalaryComparisonError(
            "De oude salaristabel bevat geen salariswaarden."
        )

    if not new_rows:
        raise SalaryComparisonError(
            "De nieuwe salaristabel bevat geen salariswaarden."
        )

    old_lookup = {
        build_value_key(row): row
        for row in old_rows
    }

    new_lookup = {
        build_value_key(row): row
        for row in new_rows
    }

    all_keys = sorted(
        set(old_lookup.keys()) | set(new_lookup.keys())
    )

    changes: list[dict] = []

    for key in all_keys:
        old_row = old_lookup.get(key)
        new_row = new_lookup.get(key)

        scale_name, step_name, component_type, amount_period = key

        if old_row is None:
            changes.append(
                {
                    "change_type": "added",
                    "scale_name": scale_name,
                    "step_name": step_name,
                    "component_type": component_type,
                    "amount_period": amount_period,
                    "old_amount": None,
                    "new_amount": float(new_row["amount"]),
                    "absolute_change": None,
                    "percentage_change": None,
                }
            )
            continue

        if new_row is None:
            changes.append(
                {
                    "change_type": "removed",
                    "scale_name": scale_name,
                    "step_name": step_name,
                    "component_type": component_type,
                    "amount_period": amount_period,
                    "old_amount": float(old_row["amount"]),
                    "new_amount": None,
                    "absolute_change": None,
                    "percentage_change": None,
                }
            )
            continue

        old_amount = float(old_row["amount"])
        new_amount = float(new_row["amount"])

        if old_amount == new_amount:
            continue

        changes.append(
            {
                "change_type": "amount_changed",
                "scale_name": scale_name,
                "step_name": step_name,
                "component_type": component_type,
                "amount_period": amount_period,
                "old_salary_row_id": old_row["id"],
                "new_salary_row_id": new_row["id"],
                "old_amount": old_amount,
                "new_amount": new_amount,
                "absolute_change": round(new_amount - old_amount, 2),
                "percentage_change": calculate_percentage_change(
                    old_amount,
                    new_amount,
                ),
            }
        )

    percentages = [
        change["percentage_change"]
        for change in changes
        if change["percentage_change"] is not None
    ]

    return {
        "old_salary_table_id": old_salary_table_id,
        "new_salary_table_id": new_salary_table_id,
        "old_value_count": len(old_rows),
        "new_value_count": len(new_rows),
        "change_count": len(changes),
        "average_percentage_change": (
            round(sum(percentages) / len(percentages), 2)
            if percentages
            else None
        ),
        "changes": changes,
    }