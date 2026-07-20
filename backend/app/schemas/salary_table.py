from pydantic import BaseModel, Field


class ExtractSalaryTablesRequest(BaseModel):
    page_numbers: list[int] = Field(
        min_length=1,
        description="PDF-paginanummers, beginnend bij 1.",
    )