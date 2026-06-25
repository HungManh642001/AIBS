export interface Vendor { id: number; ten: string; ma_so_thue?: string; }
export interface Package {
  id: number; ma_so: string; ten: string; loai: string;
  gia_tri_uoc_tinh: number; trang_thai: string; nguoi_phu_trach: string;
  vendors: Vendor[]; so_tai_lieu: number; so_tieu_chi: number;
}
export interface Criteria {
  id: number; nhom: string; ten: string; yeu_cau: string; trong_so: number; kieu: string;
}
export interface EvalResult {
  id: number; criteria_id: number; ket_qua: string; diem_so: number;
  dan_chung: string; so_trang: number[]; ghi_chu: string; ai_model: string; overridden: boolean;
}
export interface VendorResults { vendor_id: number; ten: string; results: EvalResult[]; }
export interface RankRow {
  vendor_id: number; evaluated_price: number; technical_score: number;
  rank: number | null; eligible: boolean;
}
export interface ResultsPayload { criteria: Criteria[]; vendors: VendorResults[]; ranking: RankRow[]; }
