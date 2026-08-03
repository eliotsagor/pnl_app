from fastapi import APIRouter

import database

router = APIRouter(tags=["calendar"])


@router.get("/calendar/{year}/{month}")
def calendar_month(year: int, month: int):
    totals = database.get_month_totals(year, month)
    return {str(day): v for day, v in totals.items()}


@router.get("/year/{year}")
def year_view(year: int):
    matrix, order = database.get_year_matrix(year)
    sheets = sorted(matrix.keys(), key=lambda s: order[s])
    return {"sheets": sheets, "matrix": matrix}


@router.get("/years")
def years():
    return database.get_years_with_data()


@router.get("/dates-with-data")
def dates_with_data():
    return [str(d) for d in database.get_dates_with_data()]
