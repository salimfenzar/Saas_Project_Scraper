from collections import defaultdict

from app.database import supabase


class SalaryStorageError(Exception):
    pass


def create_salary_row_payloads(
    salary_table_id: str,
    row: dict,
    source_page: int | None = None,
) -> list[dict]:
    scale_name = str(row["scale"])

    definitions = [
        {
            "component_type": "minimum",
            "amount_period": "month",
            "amount": row.get("minimum_monthly_salary"),
            "rsp_percentage": row.get("minimum_rsp"),
        },
        {
            "component_type": "minimum",
            "amount_period": "year",
            "amount": row.get("minimum_tvi"),
            "rsp_percentage": row.get("minimum_rsp"),
        },
        {
            "component_type": "rsp_100",
            "amount_period": "month",
            "amount": row.get("rsp100_monthly_salary"),
            "rsp_percentage": 100,
        },
        {
            "component_type": "rsp_100",
            "amount_period": "year",
            "amount": row.get("rsp100_tvi"),
            "rsp_percentage": 100,
        },
        {
            "component_type": "rsp_110",
            "amount_period": "month",
            "amount": row.get("rsp110_monthly_salary"),
            "rsp_percentage": 110,
        },
        {
            "component_type": "rsp_110",
            "amount_period": "year",
            "amount": row.get("rsp110_tvi"),
            "rsp_percentage": 110,
        },
    ]

    payloads: list[dict] = []

    for row_order, definition in enumerate(definitions, start=1):
        amount = definition["amount"]

        if amount is None:
            continue

        payloads.append(
            {
                "salary_table_id": salary_table_id,
                "scale_name": scale_name,
                "step_name": "",
                "amount": amount,
                "component_type": definition["component_type"],
                "amount_period": definition["amount_period"],
                "rsp_percentage": definition["rsp_percentage"],
                "row_order": row_order,
                "source_page": source_page,
                "source_text": None,
                "metadata": {},
            }
        )

    return payloads


def store_salary_rows(
    document_id: str,
    salary_rows: list[dict],
) -> dict:
    if not salary_rows:
        raise SalaryStorageError(
            "Er zijn geen salarisregels om op te slaan."
        )

    grouped_rows: dict[str, list[dict]] = defaultdict(list)

    for row in salary_rows:
        effective_date = row.get("effective_date")

        if not effective_date:
            raise SalaryStorageError(
                "Een salarisregel heeft geen ingangsdatum."
            )

        grouped_rows[effective_date].append(row)

    stored_tables: list[dict] = []
    stored_value_count = 0

    for effective_date, rows in grouped_rows.items():
        existing_table = (
            supabase.table("salary_tables")
            .select("*")
            .eq("document_id", document_id)
            .eq("effective_date", effective_date)
            .limit(1)
            .execute()
        )

        if existing_table.data:
            salary_table = existing_table.data[0]

            supabase.table("salary_scale_rows").delete().eq(
                "salary_table_id",
                salary_table["id"],
            ).execute()

        else:
            table_result = (
                supabase.table("salary_tables")
                .insert(
                    {
                        "document_id": document_id,
                        "title": f"Salarisschalen per {effective_date}",
                        "effective_date": effective_date,
                        "period": "month",
                        "currency": "EUR",
                        "extraction_method": "automatic",
                        "review_status": "pending",
                    }
                )
                .execute()
            )

            if not table_result.data:
                raise SalaryStorageError(
                    f"Salaristabel voor {effective_date} "
                    "kon niet worden aangemaakt."
                )

            salary_table = table_result.data[0]

        row_payloads: list[dict] = []

        for row in rows:
            row_payloads.extend(
                create_salary_row_payloads(
                    salary_table_id=salary_table["id"],
                    row=row,
                )
            )

        if not row_payloads:
            raise SalaryStorageError(
                f"Geen bruikbare salariswaarden gevonden "
                f"voor {effective_date}."
            )

        insert_result = (
            supabase.table("salary_scale_rows")
            .insert(row_payloads)
            .execute()
        )

        if not insert_result.data:
            raise SalaryStorageError(
                f"Salariswaarden voor {effective_date} "
                "konden niet worden opgeslagen."
            )

        stored_tables.append(salary_table)
        stored_value_count += len(insert_result.data)

    return {
        "salary_table_count": len(stored_tables),
        "salary_value_count": stored_value_count,
        "salary_tables": stored_tables,
    }