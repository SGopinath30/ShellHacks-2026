"""Create the additive SYNCHRO schema in the configured PostGIS database."""
from app.challenge.repository import migrate,health

if __name__ == "__main__":
    migrate()
    print(health())
