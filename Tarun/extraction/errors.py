"""Typed failures exposed by the extraction subsystem."""


class ExtractionError(RuntimeError):
    """Base class for extraction failures."""


class IngestionError(ExtractionError):
    """No usable source elements were supplied for extraction."""


class ParsingError(IngestionError):
    """A source was retrieved but produced no usable parsed content."""


class SourceRetrievalError(IngestionError):
    """A configured source could not be read or downloaded."""


class ModelTransportError(ExtractionError):
    """The model endpoint could not return a usable response."""


class StructuredOutputError(ExtractionError):
    """The model response did not conform to the requested Pydantic schema."""
