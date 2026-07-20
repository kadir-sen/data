#!/usr/bin/env python3
"""Repository içindeki sıkıştırılmış parçalardan orijinal satış CSV'sini üretir.

Bu dosya veri üzerinde hiçbir iş kuralı uygulamaz. Tek görevi, repoda metin olarak
saklanan base64 + bzip2 parçalarını birleştirip kaynağın birebir baytlarını yeniden
oluşturmak ve SHA-256 ile doğrulamaktır.
"""

from __future__ import annotations

import argparse
import base64
import bz2
import hashlib
from pathlib import Path

EXPECTED_SHA256 = "b49ade73e618ea4ec9592f60c9ce4d775df75661ccdb2fc62d35dffd011efa35"
EXPECTED_BYTES = 1_201_875
EXPECTED_LINES = 10_001  # Başlık dahil.


def reconstruct(repo_root: Path, output: Path, force: bool = False) -> None:
    chunks_dir = repo_root / "data" / "raw" / "chunks"
    parts = sorted(chunks_dir.glob("sales_data.csv.bz2.b64.part*"))
    if not parts:
        raise SystemExit(f"Veri parçası bulunamadı: {chunks_dir}")

    payload = "".join(part.read_text(encoding="ascii").strip() for part in parts)
    try:
        compressed = base64.b64decode(payload, validate=True)
        raw = bz2.decompress(compressed)
    except Exception as exc:  # noqa: BLE001 - kullanıcıya tek ve anlaşılır hata veriyoruz.
        raise SystemExit(f"Veri parçaları çözülemedi: {exc}") from exc

    digest = hashlib.sha256(raw).hexdigest()
    line_count = raw.count(b"\n")

    failures: list[str] = []
    if digest != EXPECTED_SHA256:
        failures.append(f"SHA-256 beklenen={EXPECTED_SHA256}, bulunan={digest}")
    if len(raw) != EXPECTED_BYTES:
        failures.append(f"bayt beklenen={EXPECTED_BYTES}, bulunan={len(raw)}")
    if line_count != EXPECTED_LINES:
        failures.append(f"satır beklenen={EXPECTED_LINES}, bulunan={line_count}")
    if failures:
        raise SystemExit("Kaynak doğrulaması başarısız:\n- " + "\n- ".join(failures))

    if output.exists() and not force:
        current = hashlib.sha256(output.read_bytes()).hexdigest()
        if current == EXPECTED_SHA256:
            print(f"Dosya zaten doğru ve değişmedi: {output}")
            return
        raise SystemExit(
            f"Çıktı zaten var fakat checksum farklı: {output}. "
            "Üzerine yazmak için --force kullanın."
        )

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(raw)
    print(f"Üretildi: {output}")
    print(f"Bayt: {len(raw):,}")
    print(f"Satır (başlık dahil): {line_count:,}")
    print(f"SHA-256: {digest}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data/raw/sales_data.csv"),
        help="Üretilecek CSV yolu",
    )
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parents[1]
    output = args.output if args.output.is_absolute() else repo_root / args.output
    reconstruct(repo_root, output, force=args.force)


if __name__ == "__main__":
    main()
