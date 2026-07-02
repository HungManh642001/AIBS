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
export interface NoiDungKiemTra {
  id?: number; noi_dung_kiem_tra: string; hsdt_kiem_tra: string; yeu_cau: string;
  can_lam_ro: string; can_tra_cuu: boolean; thong_tin_bo_sung: string; nguon: string;
  can_review: boolean;
}
export interface RubricCriteria {
  id?: number; nhom: string; ten: string; yeu_cau_goc: string;
  hsdt_can_kiem_tra: string[]; tien_quyet: boolean; noi_dung_can_kiem_tra: NoiDungKiemTra[];
}
export interface SubResult {
  id: number; sub_check_ten: string; result: string; evidence: string;
  page_ref: number[]; nguon_file: string; ai_model: string; overridden: boolean;
}
export interface CriteriaBreakdown {
  criteria_id: number; criteria_ten: string; result: string | null;
  score: number; sub_results: SubResult[];
}
export interface Completeness {
  percent: number; missing: string[]; required: string[];
}
export interface VendorBreakdown {
  vendor_id: number; ten: string; completeness: Completeness; criteria: CriteriaBreakdown[];
}
export interface ResultsBreakdown { vendors: VendorBreakdown[]; }

// ---- Đánh giá HSDT (verdict pipeline vision) ----
export interface Verdict {
  id: number; noi_dung_kiem_tra: string; hsdt_kiem_tra: string; yeu_cau: string;
  thong_tin_bo_sung: string; ket_qua: string; bang_chung: string; trang: number[];
  do_tin: number; ghi_chu: string; overridden: boolean;
}
export interface CriterionEval {
  eval_id: number; ten: string; nhom: string; tien_quyet: boolean;
  ket_qua: string; loai: boolean; verdicts: Verdict[];
}
export interface EvalSummary {
  n_tieu_chi: number; n_dat: number; n_khong_dat: number; n_can_lam_ro: number; n_loai: number;
}
export interface VendorEval {
  vendor_id: number; ten: string; summary: EvalSummary; criteria: CriterionEval[];
}
export interface EvalResultsPayload { vendors: VendorEval[]; }
export const ARTIFACT_TYPES: { value: string; label: string }[] = [
  { value: "don_du_thau", label: "Đơn dự thầu" },
  { value: "bao_dam_du_thau", label: "Bảo đảm dự thầu (thư BL)" },
  { value: "thoa_thuan_lien_danh", label: "Thỏa thuận liên danh" },
  { value: "tu_cach_phap_ly", label: "Tài liệu tư cách hợp lệ" },
  { value: "bao_cao_tai_chinh", label: "Báo cáo tài chính" },
  { value: "hop_dong_tuong_tu", label: "Hợp đồng tương tự" },
  { value: "bang_gia", label: "Bảng giá dự thầu" },
];
