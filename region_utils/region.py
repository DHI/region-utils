import json
import math
from pathlib import Path
from typing import Optional

import geopandas as gpd
import pyproj
import rasterio as rst
import shapely
from shapely import Polygon
from shapely.ops import transform
from sqlalchemy import create_engine

from .utils import download_blob


class Region:
    def __init__(
        self, polygon, crs: str | pyproj.CRS, name: str | None = None, **kwargs
    ):
        self.polygon = polygon
        self.name = name
        self.crs = pyproj.CRS(crs)  # will raise CRSError if invalid

        for key, value in kwargs.items():
            setattr(self, key, value)

    @classmethod
    def from_shapefile(
        cls, path: str | Path, crs: str, name: str | None = None, **kwargs
    ):
        df = gpd.read_file(path)
        assert len(df) == 1, "Shapefile must contain exactly one polygon"
        return cls.from_polygon(polygon=df.geometry[0], crs=crs, name=name, **kwargs)

    @classmethod
    def from_polygon(
        cls, polygon: Polygon, crs: str, name: str | None = None, **kwargs
    ):
        return cls(polygon=polygon, crs=crs, name=name, **kwargs)

    @classmethod
    def from_dict(cls, json_data: dict):
        pol = shapely.geometry.shape(json_data["geometry"])
        crs = pyproj.CRS.from_json_dict(json_data["crs"])
        return cls.from_polygon(polygon=pol, crs=crs, **json_data["properties"])

    @classmethod
    def from_json(cls, json_data: str | Path):
        if isinstance(json_data, str) and json_data.startswith("{"):
            json_data = json.loads(json_data)
        else:
            with open(json_data) as f:
                json_data = json.load(f)

        return cls.from_dict(json_data)

    @classmethod
    def from_postgis_id(
        cls,
        id: int,
        table_name: str,
        connection_string: str,
        id_column_name: str = "id",
        geometry_column_name: str = "geometry",
        region_name_column_name: Optional[str] = None,
    ):
        engine = create_engine(connection_string)
        df = gpd.read_postgis(
            f"SELECT * FROM {table_name} WHERE {id_column_name} = {id}",
            engine,
            geom_col=geometry_column_name,
        )
        if not region_name_column_name:
            return cls.from_polygon(df.geometry[0], df.crs)
        return cls.from_polygon(
            df.geometry[0], df.crs, name=df[region_name_column_name][0]
        )

    @classmethod
    def from_raster_bounds(
        cls,
        raster_path: str | Path,
        blob_connection_str: str | None = None,
    ):
        if blob_connection_str:
            raster_path = download_blob(raster_path, blob_connection_str)

        with rst.open(raster_path) as src:
            b = src.bounds
            crs = src.crs

        return cls.from_polygon(
            Polygon(
                (
                    (b.left, b.top),
                    (b.right, b.top),
                    (b.right, b.bottom),
                    (b.left, b.bottom),
                )
            ),
            crs=crs,
        )

    @property
    def bounds(self):
        return self.polygon.bounds

    def to_db(self):
        raise NotImplementedError

    def to_dict(self, compact: bool = False):
        json_data = {
            "properties": {
                k: v for k, v in self.__dict__.items() if k not in {"polygon", "crs"}
            },
            "crs": self.crs.to_json_dict() if not compact else self.crs.to_dict(),
            "geometry": json.loads(shapely.to_geojson(self.polygon, indent=4)),
        }
        return json_data

    def to_json(self, file_path: str | Path | None = None, compact: bool = False):
        json_data = self.to_dict(compact=compact)
        if not file_path:
            return json.dumps(json_data, indent=4)

        with open(file_path, "w") as f:
            json.dump(json_data, f, indent=4)

    def with_pixel_buffer(self, pixel_buffer: int, pixel_size_m: int = 10) -> "Region":
        number_of_meters = pixel_buffer * pixel_size_m
        if self.crs.axis_info[0].unit_name == "metre":
            buffer_value = number_of_meters
        elif (
            self.crs.axis_info[0].unit_name == "degree"
        ):  # This is just rough, not exact
            buffer_value = max(
                number_of_meters / 111_111,
                number_of_meters / (111_111 * math.cos(self.bounds[1])),
            )
        else:
            raise ValueError(
                "Currently only supports CRS with units of metres or degrees"
            )

        return Region.from_polygon(
            polygon=self.polygon.buffer(buffer_value),
            crs=self.crs,
            name=self.name,
        )

    def to_crs(self, crs: str | pyproj.CRS) -> "Region":
        if isinstance(crs, str):
            crs = pyproj.CRS(crs)

        projection = pyproj.Transformer.from_proj(
            self.crs,  # source crs
            crs,  # target_crs
            always_xy=True,
        )
        return Region(
            polygon=transform(projection.transform, self.polygon),
            crs=crs,
            name=self.name,
        )

    def to_latlon(self) -> "Region":
        return self.to_crs("EPSG:4326")

    def __repr__(self):
        return f"Region(name={self.name}, crs={self.crs.name})"

    def _repr_svg_(self):
        print(self.__repr__())
        return self.polygon._repr_svg_()

    def difference(self, other: "Region") -> "Region":
        return self.polygon.difference(other.polygon)
