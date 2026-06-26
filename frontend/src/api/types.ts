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
export interface ArtifactValidation { match: boolean; suggested_type: string; confidence: number; note: string; }
export interface SubCheck {
  id?: number; ten: string; check_type: string; thong_so: Record<string, unknown>;
  required_artifact: string; blocking: boolean;
}
export interface DeCuongCriteria {
  id?: number; nhom: string; ten: string; yeu_cau: string; required_artifacts: string[];
  kieu: string; trong_so: number; sub_checks: SubCheck[];
}
export interface SubResult {
  id: number; sub_check_ten: string; result: string; evidence: string;
  page_ref: number[]; nguon_file: string; overridden: boolean;
}
export const ARTIFACT_TYPES: { value: string; label: string }[] = [
  { value: "don_du_thau", label: "Đơn dự thầu" },
  { value: "bao_dam_du_thau", label: "Bảo đảm dự thầu (thư BL)" },
  { value: "thoa_thuan_lien_danh", label: "Thỏa thuận liên danh" },
  { value: "tu_cach_phap_ly", label: "Tài liệu tư cách hợp lệ" },
  { value: "bao_cao_tai_chinh", label: "Báo cáo tài chính" },
  { value: "hop_dong_tuong_tu", label: "Hợp đồng tương tự" },
  { value: "bang_gia", label: "Bảng giá dự thầu" },
];
