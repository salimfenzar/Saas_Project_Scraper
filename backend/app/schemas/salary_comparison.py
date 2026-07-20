from uuid import UUID

from pydantic import BaseModel


class CompareSalaryTablesRequest(BaseModel):
    old_salary_table_id: UUID
    new_salary_table_id: UUID