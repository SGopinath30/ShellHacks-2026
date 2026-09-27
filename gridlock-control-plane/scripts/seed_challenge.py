"""Load the local organizer fixture into the SYNCHRO project-version API store."""
import json
from pathlib import Path
from app.challenge.contracts import ProjectInput
from app.challenge.repository import migrate,save

if __name__ == "__main__":
    migrate()
    fixture = Path(__file__).resolve().parents[1]/"data/fixtures/starter_projects.json"
    projects = json.loads(fixture.read_text())
    for item in projects:
        save(ProjectInput.model_validate(item))
    print(f"Loaded {len(projects)} starter project versions")
