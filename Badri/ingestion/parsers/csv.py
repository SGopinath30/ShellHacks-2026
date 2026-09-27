import csv
from io import StringIO


def parse_csv(data):
    # Explicit UTF-8 and comma-delimited input; never infer types or trim source values.
    rows = csv.reader(StringIO(data.decode("utf-8-sig"), newline=""))
    return {"format": "csv", "sheets": [{"name": "CSV", "rows": [
        {"row_number": i, "values": row} for i, row in enumerate(rows, 1)]}]}
