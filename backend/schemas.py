"""Pydantic schemas cho request/response."""
from __future__ import annotations
from pydantic import BaseModel, Field


class PackageCreate(BaseModel):
    ma_so: str
    ten: str
    loai: str = "hang_hoa"
    gia_tri_uoc_tinh: float = 0.0
    nguoi_phu_trach: str = ""
    vendors: list[str] = Field(default_factory=list)


class VendorOut(BaseModel):
    id: int
    ten: str
    ma_so_thue: str = ""


class VendorCreate(BaseModel):
    ten: str
    ma_so_thue: str = ""


class PackageOut(BaseModel):
    id: int
    ma_so: str
    ten: str
    loai: str
    gia_tri_uoc_tinh: float
    trang_thai: str
    nguoi_phu_trach: str
    vendors: list[VendorOut] = Field(default_factory=list)
    so_tai_lieu: int = 0
    so_tieu_chi: int = 0
