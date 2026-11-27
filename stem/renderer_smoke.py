from .qualify_render import run_batch, safe_svg, png_bytes, preflight


def main():
    examples = ["E=mc^2", r"\boldsymbol{F}=m\boldsymbol{a}", r"\frac{x-\mu}{\sigma}",
                r"\begin{pmatrix}a&b\\c&d\end{pmatrix}", "f'(x)"]
    requests = [{"id": str(i), "value": preflight(tex)} for i, tex in enumerate(examples)]
    rendered = run_batch("svg", requests)
    safe = {key: safe_svg(row["value"]) for key, row in rendered.items()}
    pngs = run_batch("png", [{"id": key, "value": item[0]} for key, item in safe.items()])
    for key, (_, width, height) in safe.items():
        png_bytes(pngs[key]["value"], width, height)
    print(f"SVG and PNG smoke passed: {len(examples)} formulas")


if __name__ == "__main__":
    main()
