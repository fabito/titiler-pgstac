"""
Titiler.pgstac models.

Note: This is mostly a copy of https://github.com/stac-utils/stac-fastapi/blob/master/stac_fastapi/pgstac/stac_fastapi/pgstac/types/search.py
"""

from datetime import datetime
from typing import Any, Dict, List, Literal, Optional

from geojson_pydantic.geometries import Geometry
from geojson_pydantic.types import BBox
from pydantic import BaseModel, Field, ValidationInfo, field_validator, model_validator
from typing_extensions import Annotated

from titiler.core.resources.enums import MediaType

# ref: https://github.com/stac-api-extensions/query
# TODO: add "startsWith", "endsWith", "contains", "in"
Operator = Literal["eq", "neq", "lt", "lte", "gt", "gte"]

# ref: https://github.com/radiantearth/stac-api-spec/tree/master/fragments/filter#get-query-parameters-and-post-json-fields
FilterLang = Literal["cql-json", "cql-text", "cql2-json"]


class Metadata(BaseModel):
    """Metadata Model."""

    type: Literal["mosaic", "search"] = "mosaic"

    # WGS84 bounds
    bounds: Optional[BBox] = None

    # Min/Max zoom for WebMercatorQuad TMS
    minzoom: Optional[int] = None
    maxzoom: Optional[int] = None

    # Name
    name: Optional[str] = None

    # List of available assets
    assets: Optional[List[str]] = None

    # Set of default configuration
    # e.g
    # {
    #     "true_color": {
    #         "assets": ["B4", "B3", "B2"],
    #         "color_formula": "Gamma RGB 3.5 Saturation 1.7 Sigmoidal RGB 15 0.35",
    #     },
    #     "ndvi": {
    #         "expression": "(B4-B3)/(B4+B3)",
    #         "rescale": "-1,1",
    #         "colormap_name": "viridis"
    #     }
    # }
    defaults: Optional[Dict[str, Any]] = None

    model_config = {"extra": "allow"}


class PgSTACSearch(BaseModel):
    """Search Query model.

    Notes/Diff with standard model:
        - 'fields' is not in the Model because it's defined at the tiler level
        - we don't set limit
    """

    collections: Optional[List[str]] = None
    ids: Optional[List[str]] = None
    bbox: Optional[BBox] = None
    intersects: Optional[Geometry] = None
    query: Optional[Dict[str, Dict[Operator, Any]]] = None
    filter: Optional[Dict] = None
    datetime: Optional[str] = None
    sortby: Optional[Any] = None
    filter_lang: Optional[FilterLang] = Field(default=None, alias="filter-lang")

    model_config = {"extra": "allow"}

    @model_validator(mode="before")
    def validate_query_fields(cls, values: Dict) -> Dict:
        """Pgstac does not require the base validator for query fields."""
        return values

    @field_validator("datetime")
    def validate_datetime(cls, v):
        """Pgstac does not require the base validator for datetime."""
        return v

    @field_validator("intersects")
    def validate_spatial(cls, v: Optional[Geometry], info: ValidationInfo):
        """Make sure bbox is not used with Intersects."""
        if v and info.data["bbox"]:
            raise ValueError("intersects and bbox parameters are mutually exclusive")

        return v

    @field_validator("bbox")
    def validate_bbox(cls, v: BBox):
        """Validate BBOX."""
        if v:
            # Validate order
            if len(v) == 4:
                xmin, ymin, xmax, ymax = v
            else:
                xmin, ymin, min_elev, xmax, ymax, max_elev = v
                if max_elev < min_elev:
                    raise ValueError(
                        "Maximum elevation must greater than minimum elevation"
                    )

            if xmax < xmin:
                raise ValueError(
                    "Maximum longitude must be greater than minimum longitude"
                )

            if ymax < ymin:
                raise ValueError(
                    "Maximum longitude must be greater than minimum longitude"
                )

            # Validate against WGS84
            if xmin < -180 or ymin < -90 or xmax > 180 or ymax > 90:
                raise ValueError("Bounding box must be within (-180, -90, 180, 90)")

        return v


class RegisterMosaic(PgSTACSearch):
    """Model of /register endpoint input."""

    metadata: Annotated[Metadata, Field(default_factory=Metadata)]


class Search(BaseModel):
    """PgSTAC Search entry.

    ref: https://github.com/stac-utils/pgstac/blob/3499daa2bfa700ae7bb07503795c169bf2ebafc7/sql/004_search.sql#L907-L915
    """

    id: str = Field(alias="hash")
    input_search: Dict[str, Any] = Field(alias="search")
    sql_where: str = Field(alias="_where")
    orderby: str
    lastused: datetime
    usecount: int
    metadata: Metadata

    @field_validator("metadata", mode="before")
    def validate_metadata(cls, v):
        """Set SearchType.search when not present in metadata."""
        if "type" not in v:
            v["type"] = "search"

        return v


class Link(BaseModel):
    """Link model.

    Ref: http://schemas.opengis.net/ogcapi/features/part1/1.0/openapi/schemas/link.yaml
    """

    rel: Optional[str] = None
    title: Optional[str] = None
    type: Optional[MediaType] = MediaType.json
    href: str
    hreflang: Optional[str] = None
    length: Optional[int] = None

    model_config = {"use_enum_values": True}


class RegisterResponse(BaseModel):
    """Response model for /register endpoint."""

    id: str
    links: Optional[List[Link]] = None


class Info(BaseModel):
    """Response model for /info endpoint."""

    search: Search
    links: Optional[List[Link]] = None


class Context(BaseModel):
    """Context Model."""

    returned: int
    limit: Optional[int] = None
    matched: Optional[int] = None

    @field_validator("limit")
    def validate_limit(cls, v, info: ValidationInfo):
        """validate limit."""
        if info.data["returned"] > v:
            raise ValueError(
                "Number of returned items must be less than or equal to the limit"
            )

        return v


class Infos(BaseModel):
    """Response model for /list endpoint."""

    searches: List[Info]
    links: Optional[List[Link]] = None
    context: Context
