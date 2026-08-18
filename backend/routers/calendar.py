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


@router.get("/strategy-year/{year}/{sheet_name}")
def strategy_year(year: int, sheet_name: str):
    matrix = database.get_strategy_year_matrix(year, sheet_name)
    weekday = database.get_strategy_weekday_totals(year, sheet_name)
    return {
        "days": {str(d): {str(m): v for m, v in months.items()} for d, months in matrix.items()},
        "weekday": {str(k): v for k, v in weekday.items()},
    }


@router.get("/total-year/{year}")
def total_year(year: int):
    matrix = database.get_aggregate_year_matrix(year, "include_in_total")
    weekday = database.get_aggregate_weekday_totals(year, "include_in_total")
    return {
        "days": {str(d): {str(m): v for m, v in months.items()} for d, months in matrix.items()},
        "weekday": {str(k): v for k, v in weekday.items()},
    }


@router.get("/all-bics-year/{year}")
def all_bics_year(year: int):
    matrix = database.get_aggregate_year_matrix(year, "include_in_all_bics")
    weekday = database.get_aggregate_weekday_totals(year, "include_in_all_bics")
    return {
        "days": {str(d): {str(m): v for m, v in months.items()} for d, months in matrix.items()},
        "weekday": {str(k): v for k, v in weekday.items()},
    }


@router.get("/years")
def years():
    return database.get_years_with_data()


@router.get("/dates-with-data")
def dates_with_data():
    return [str(d) for d in database.get_dates_with_data()]
