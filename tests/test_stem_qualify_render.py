import unittest

from stem.qualify_render import preflight, safe_svg


class RendererPolicyTests(unittest.TestCase):
    def test_allowed_math(self):
        for tex in ("E=mc^2", r"\boldsymbol{F}=m\boldsymbol{a}",
                    r"\begin{pmatrix}a&b\\c&d\end{pmatrix}", "f'(x)"):
            self.assertEqual(preflight(tex), tex)

    def test_untrusted_tex(self):
        for tex in (r"\require{html}", r"\href{https://example.org}{x}",
                    r"\def\x{x}\x", r"\input{foo}", r"\begin{unknown}x\end{unknown}",
                    "x%hidden", "x\ufffd", r"\color{red}x"):
            with self.subTest(tex=tex), self.assertRaises(ValueError):
                preflight(tex)

    def test_svg_policy(self):
        prefix = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1000 500">'
        svg, width, height = safe_svg(prefix + '<g fill="currentColor"><path d="M0 0L1 1"/></g></svg>')
        self.assertEqual((width, height), (32, 16))
        self.assertIn("#ffffff", svg)
        for body in ('<script/>', '<image href="file:///secret"/>', '<g onclick="bad()"/>',
                     '<g style="fill:red"/>', '<text>x</text>', '<path d="M0 0" fill="url(http://example.org)"/>',
                     '<g data-mml-node="merror"><path d="M0 0"/></g>'):
            with self.subTest(body=body), self.assertRaises(ValueError):
                safe_svg(prefix + body + "</svg>")


if __name__ == "__main__":
    unittest.main()
