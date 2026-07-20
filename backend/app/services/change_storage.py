from app.database import supabase


class ChangeStorageError(Exception):
    pass


def get_table_context(salary_table_id: str) -> dict:
    table_result = (
        supabase.table("salary_tables")
        .select("id,document_id,effective_date")
        .eq("id", salary_table_id)
        .limit(1)
        .execute()
    )

    if not table_result.data:
        raise ChangeStorageError(
            f"Salaristabel niet gevonden: {salary_table_id}"
        )

    salary_table = table_result.data[0]

    document_result = (
        supabase.table("documents")
        .select("id,cao_version_id")
        .eq("id", salary_table["document_id"])
        .limit(1)
        .execute()
    )

    if not document_result.data:
        raise ChangeStorageError("Document niet gevonden.")

    document = document_result.data[0]

    version_result = (
        supabase.table("cao_versions")
        .select("id,cao_id")
        .eq("id", document["cao_version_id"])
        .limit(1)
        .execute()
    )

    if not version_result.data:
        raise ChangeStorageError("CAO-versie niet gevonden.")

    version = version_result.data[0]

    return {
        "salary_table_id": salary_table["id"],
        "effective_date": salary_table["effective_date"],
        "document_id": document["id"],
        "version_id": version["id"],
        "cao_id": version["cao_id"],
    }


def store_salary_changes(
    comparison: dict,
) -> dict:
    old_context = get_table_context(
        comparison["old_salary_table_id"]
    )
    new_context = get_table_context(
        comparison["new_salary_table_id"]
    )

    if old_context["cao_id"] != new_context["cao_id"]:
        raise ChangeStorageError(
            "De salaristabellen horen niet bij dezelfde cao."
        )

    # Voorkom dubbele resultaten wanneer je dezelfde vergelijking opnieuw uitvoert.
    (
        supabase.table("salary_changes")
        .delete()
        .eq("old_version_id", old_context["version_id"])
        .eq("new_version_id", new_context["version_id"])
        .execute()
    )

    payloads: list[dict] = []

    for change in comparison["changes"]:
        old_amount = change.get("old_amount")
        new_amount = change.get("new_amount")

        summary = (
            f"Schaal {change['scale_name']} "
            f"{change['component_type']} "
            f"({change['amount_period']}): "
            f"{old_amount} → {new_amount}"
        )

        payloads.append(
            {
                "cao_id": new_context["cao_id"],
                "old_version_id": old_context["version_id"],
                "new_version_id": new_context["version_id"],
                "old_salary_row_id": change.get(
                    "old_salary_row_id"
                ),
                "new_salary_row_id": change.get(
                    "new_salary_row_id"
                ),
                "change_type": change["change_type"],
                "scale_name": change["scale_name"],
                "step_name": change.get("step_name") or "",
                "component_type": change["component_type"],
                "amount_period": change["amount_period"],
                "old_amount": old_amount,
                "new_amount": new_amount,
                "absolute_change": change.get(
                    "absolute_change"
                ),
                "percentage_change": change.get(
                    "percentage_change"
                ),
                "effective_date": new_context[
                    "effective_date"
                ],
                "summary": summary,
            }
        )

    if not payloads:
        return {
            "stored_change_count": 0,
            "changes": [],
        }

    result = (
        supabase.table("salary_changes")
        .insert(payloads)
        .execute()
    )

    if not result.data:
        raise ChangeStorageError(
            "De wijzigingen konden niet worden opgeslagen."
        )

    return {
        "stored_change_count": len(result.data),
        "changes": result.data,
    }