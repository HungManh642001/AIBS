import { useEffect, useState } from "react";
import { api, unwrap } from "./client";

export interface ArtifactType { value: string; label: string; nhom: string; mo_ta: string; }

// Nguồn sự thật lấy động từ backend (GET /artifacts) — cache module-level để chỉ fetch 1 lần.
let cache: ArtifactType[] | null = null;
let inflight: Promise<ArtifactType[]> | null = null;

function fetchArtifacts(): Promise<ArtifactType[]> {
  if (cache) return Promise.resolve(cache);
  if (!inflight) {
    inflight = api.get("/artifacts")
      .then((r) => { cache = unwrap<ArtifactType[]>(r); return cache!; })
      .catch((e) => { inflight = null; throw e; });
  }
  return inflight;
}

/** Danh mục loại hồ sơ HSDT (đồng bộ backend). Trả [] cho tới khi tải xong. */
export function useArtifactTypes(): ArtifactType[] {
  const [types, setTypes] = useState<ArtifactType[]>(cache ?? []);
  useEffect(() => {
    let alive = true;
    fetchArtifacts().then((t) => { if (alive) setTypes(t); }).catch(() => {});
    return () => { alive = false; };
  }, []);
  return types;
}

/** Nhãn tiếng Việt cho mã loại hồ sơ. Mã kỹ thuật (don_du_thau) KHÔNG được lọt ra giao diện. */
export function useArtifactLabel(): (code: string) => string {
  const types = useArtifactTypes();
  return (code: string) => types.find((t) => t.value === code)?.label || code;
}

/** Nhãn nhóm tiêu chí (cột `nhom` của rubric). */
export const NHOM_LABEL: Record<string, string> = {
  hop_le: "Tính hợp lệ",
  nang_luc: "Năng lực",
  ky_thuat: "Kỹ thuật",
  tai_chinh: "Tài chính",
};
