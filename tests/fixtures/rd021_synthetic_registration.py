"""Non-personal PDF fixture for registration interpreter qualification."""
from __future__ import annotations


def synthetic_registration_pdf() -> bytes:
    lines = (
        "SYNTHETIC TEST REGISTRATION - NOT A REAL VEHICLE",
        "Year: 2018", "Make: BMW", "Model: 318I",
        "VIN: WBA12345678901234", "Plate: TEST-1234",
        "Displacement: 1998 cc", "Fuel: gasoline", "Manufacture date: 2018-06",
    )
    commands = ["BT", "/F1 14 Tf", "50 740 Td"]
    for index, line in enumerate(lines):
        if index:
            commands.append("0 -28 Td")
        commands.append(f"({line}) Tj")
    commands.append("ET")
    stream = "\n".join(commands).encode("ascii") + b"\n"
    objects = (
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        b"/Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"endstream",
    )
    raw = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for number, body in enumerate(objects, start=1):
        offsets.append(len(raw))
        raw.extend(f"{number} 0 obj\n".encode() + body + b"\nendobj\n")
    xref = len(raw)
    raw.extend(f"xref\n0 {len(offsets)}\n".encode())
    raw.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        raw.extend(f"{offset:010d} 00000 n \n".encode())
    raw.extend(f"trailer\n<< /Size {len(offsets)} /Root 1 0 R >>\n"
               f"startxref\n{xref}\n%%EOF\n".encode())
    return bytes(raw)
