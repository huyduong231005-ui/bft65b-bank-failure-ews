"""Collect every Markdown result table in outputs/ into one formatted Excel workbook.

Run:  python src/export_excel.py      Out: outputs/results.xlsx (one sheet per table)
"""
from __future__ import annotations

import polars as pl
import xlsxwriter

from common import OUT


def md_tables(text: str) -> list[tuple[str, pl.DataFrame]]:
    """Parse '### title' + pipe tables. ponytail: only the simple tables save_md writes."""
    out, title, rows = [], "", []

    def flush():
        if rows:
            header, body = rows[0], rows[2:]          # rows[1] is the |---| separator
            df = pl.DataFrame([dict(zip(header, r)) for r in body]) if body else pl.DataFrame({h: [] for h in header})
            out.append((title, df))
            rows.clear()

    for line in text.splitlines():
        if line.startswith("|"):
            rows.append([c.strip() for c in line.strip().strip("|").split("|")])
        else:
            flush()
            if line.startswith("### "):
                title = line[4:].strip()
    flush()
    return out


def to_number(df: pl.DataFrame) -> pl.DataFrame:
    """Turn numeric-looking text columns into real numbers so Excel can sort/format them."""
    cols = []
    for c in df.columns:
        num = df[c].cast(pl.Float64, strict=False)
        cols.append(num if num.null_count() == df[c].is_in(["", "null"]).sum() else df[c])
    return pl.DataFrame(cols)


def main() -> None:
    path = OUT / "results.xlsx"
    with xlsxwriter.Workbook(path) as wb:
        for md in sorted(OUT.glob("p*.md")):
            for i, (title, df) in enumerate(md_tables(md.read_text(encoding="utf-8")), 1):
                sheet = f"{md.stem[:26]}_{i}" if i > 1 else md.stem[:31]
                to_number(df).write_excel(wb, worksheet=sheet, position="A3", autofit=True,
                                          table_style="Table Style Medium 2", float_precision=4)
                wb.get_worksheet_by_name(sheet).write("A1", title, wb.add_format({"bold": True, "font_size": 12}))
    print(f"wrote {path}")


if __name__ == "__main__":
    main()
