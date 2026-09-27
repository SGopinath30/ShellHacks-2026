"""Convert the organizer workbook into explicitly unverified dev fixtures."""
import argparse
import json
from datetime import datetime, date
from pathlib import Path
import openpyxl
from app.challenge.contracts import ProjectInput


def as_date(raw):
    if raw is None:
        return None
    if isinstance(raw,(datetime,date)):
        return raw.date() if isinstance(raw,datetime) else raw
    return datetime.strptime(raw,"%m/%d/%Y").date()


def convert(source: Path, output: Path):
    workbook = openpyxl.load_workbook(source,read_only=True,data_only=True)
    rows = list(workbook["projects"].values)
    keys = rows[0]
    projects = []
    for row_number,row in enumerate(rows[1:],start=2):
        data = dict(zip(keys,row))
        endpoints = [(data["lon_a"],data["lat_a"]),(data["lon_b"],data["lat_b"])]
        endpoints = [(lon,lat) for lon,lat in endpoints if lon is not None and lat is not None]
        geometry = ({"type":"LineString","coordinates":endpoints} if len(endpoints) == 2
                    else {"type":"Point","coordinates":endpoints[0]} if endpoints else None)
        center = ({"type":"Point","coordinates":[data["lon_center"],data["lat_center"]]}
                  if data["lon_center"] is not None and data["lat_center"] is not None else None)
        name = data["project_name"].lower()
        project_type = ("substation" if "reactor" in name else "rebuild" if "rebuild" in name or "reconductor" in name
                        else "transmission_line")
        milestone = as_date(data["in_service_date"])
        project = ProjectInput(
            project_id=data["project_id"],utility_id=data["utility"],project_name=data["project_name"],
            project_type=project_type,status="unknown",location_text=data["project_name"],
            geometry=geometry,center_point=center,
            geometry_origin="TWO_ENDPOINT_SEGMENT" if len(endpoints)==2 else "SINGLE_LOCATED_POINT",
            geometry_quality="APPROXIMATE" if geometry else "UNRESOLVED",validation_state="NEEDS_REVIEW",
            schedule={"type":"IN_SERVICE_GAP","in_service_date":milestone} if milestone else {"type":"UNKNOWN"},
            evidence=[{"source_id":"organizer-starter-workbook","source_name":source.name,
                       "page_or_row":f"projects row {row_number}"}],is_fixture=True)
        projects.append(project.model_dump(mode="json"))
    overlap_rows = list(workbook["overlaps"].values)
    expected = []
    for row in overlap_rows[1:]:
        data = dict(zip(overlap_rows[0],row))
        expected.append({"project_a":data["project_id_a"],"project_b":data["project_id_b"],
                         "organizer_distance_miles":data["distance_mi"],"organizer_gap_days":data["time_gap (day)"]})
    output.mkdir(parents=True,exist_ok=True)
    (output/"starter_projects.json").write_text(json.dumps(projects,indent=2)+"\n")
    (output/"starter_overlaps.json").write_text(json.dumps(expected,indent=2)+"\n")
    return len(projects),len(expected)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("workbook",type=Path)
    parser.add_argument("--output",type=Path,default=Path("data/fixtures"))
    args = parser.parse_args()
    print(convert(args.workbook,args.output))
