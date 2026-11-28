import unittest
from unittest.mock import patch

from stem.hybrid import RULES, build_hybrid
from stem.structural_rules import EXPANDED_RULES


class ExpandedStructuralRuleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.hybrid, _, _ = build_hybrid()

    def test_explicit_spoken_and_symbolic_variants(self):
        for phrase, identity, latex in (
            ("F equals m times a", "physics.newton_second:standard", "F=ma"),
            ("V equals I times R", "physics.ohm:standard", "V=IR"),
            ("A equals pi times r squared", "geometry.circle_area:standard", r"A=\pi r^2"),
            ("a sub n equals a sub one times r raised to the power of open parenthesis n minus one close parenthesis",
             "algebra.geometric_sequence:standard", r"a_n=a_1r^{n-1}"),
            ("sigma sub x times sigma sub p is greater than or equal to h bar divided by two",
             "physics.uncertainty:standard", r"\sigma_x\sigma_p\geq\frac{\hbar}{2}"),
            ("cos(2x)=1-2*sin(x)²", "trigonometry.cosine_double_angle:sine_only", r"\cos(2x)=1-2\sin^2 x"),
        ):
            with self.subTest(phrase=phrase):
                text = "Résumé. Equation: " + phrase + "."
                matches = self.hybrid.recognize(text)
                self.assertEqual(len(matches), 1)
                match = matches[0]
                self.assertEqual((match.dictionary_id, match.latex), (identity, latex))
                self.assertEqual(text[match.start:match.end], phrase)

    def test_wrong_scope_sign_case_and_relation_are_not_structural_matches(self):
        for phrase in (
            "F=m/a", "F=m*a^2", "A=π*r^3", "a_n=a_1*r^n-1",
            "x=(-b±√(b^2+4*a*c))/(2*a)", "σ_x*σ_p=ℏ/2",
            "sin(x²)+cos(x²)=1", "cos(2*x)=1+2*sin(x)^2",
            "E^2=p^2*c^2-m^2*c^4", "1/f=1/(d_o+d_i)",
            "ρ=V/m", "p*v=n*r*t", "W=F*d*sin(θ)",
            "λ=p/h", "x=1",
        ):
            with self.subTest(phrase=phrase):
                self.assertEqual(self.hybrid.recognize(phrase), ())

    def test_unsupported_and_out_of_corpus_remain_unrecognized(self):
        for phrase in ("i²=-1", "cos(π/2)=0", "x²+y²=z²", "F=q*(E+v*B)",
                       "the quadratic formula", "x=1+2", "x plus y over z"):
            with self.subTest(phrase=phrase):
                self.assertEqual(self.hybrid.recognize(phrase), ())

    def test_duplicate_rules_fail_closed(self):
        with patch("stem.hybrid.RULES", RULES + (EXPANDED_RULES[0],)):
            with self.assertRaisesRegex(ValueError, "Duplicate structural representation rule"):
                build_hybrid()


if __name__ == "__main__":
    unittest.main()
