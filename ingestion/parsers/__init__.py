from ingestion.common import IngestionError


def parse(data, file_format, source_crs=None):
    if file_format == "xlsx":
        from .xlsx import parse_xlsx
        return parse_xlsx(data)
    if file_format == "csv":
        from .csv import parse_csv
        return parse_csv(data)
    if file_format == "pdf":
        from .pdf import parse_pdf
        return parse_pdf(data)
    if file_format == "docx":
        from .docx import parse_docx
        return parse_docx(data)
    if file_format in ("geojson", "shapefile"):
        from .gis import parse_geojson, parse_shapefile
        return (parse_geojson if file_format == "geojson" else parse_shapefile)(data, source_crs)
    if file_format == "html":
        from .html import parse_html
        return parse_html(data)
    raise IngestionError("UNSUPPORTED_FORMAT", file_format)
