from fastapi import APIRouter, HTTPException

from app.schemas.salary_comparison import (
    CompareSalaryTablesRequest,
)
from app.services.salary_comparison import (
    SalaryComparisonError,
    compare_salary_tables,
)
from app.services.change_storage import (
    ChangeStorageError,
    store_salary_changes,
)


router = APIRouter(
    prefix="/comparisons",
    tags=["Comparisons"],
)


@router.post("/salary-tables")
def compare_tables(
    payload: CompareSalaryTablesRequest,
) -> dict:
    try:
        return compare_salary_tables(
            old_salary_table_id=str(
                payload.old_salary_table_id
            ),
            new_salary_table_id=str(
                payload.new_salary_table_id
            ),
        )

    except SalaryComparisonError as exc:
        raise HTTPException(
            status_code=422,
            detail=str(exc),
        ) from exc
@router.post("/salary-tables/compare-and-store")
def compare_and_store_tables(
    payload: CompareSalaryTablesRequest,
) -> dict:
    try:
        comparison = compare_salary_tables(
            old_salary_table_id=str(
                payload.old_salary_table_id
            ),
            new_salary_table_id=str(
                payload.new_salary_table_id
            ),
        )

        storage_result = store_salary_changes(comparison)

        return {
            "comparison": comparison,
            "storage": storage_result,
        }

    except (
        SalaryComparisonError,
        ChangeStorageError,
    ) as exc:
        raise HTTPException(
            status_code=422,
            detail=str(exc),
        ) from exc