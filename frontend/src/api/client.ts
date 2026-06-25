import axios from "axios";

export const api = axios.create({ baseURL: "http://localhost:8000/api/v1" });

export interface Envelope<T> { success: boolean; data: T; error: string | null; }

export function unwrap<T>(resp: { data: Envelope<T> }): T {
  if (!resp.data.success) throw new Error(resp.data.error ?? "Lỗi không xác định");
  return resp.data.data;
}
