from dependency.db.connection import postgis_version

if __name__ == "__main__":
    print(f"PostGIS: {postgis_version()}")
