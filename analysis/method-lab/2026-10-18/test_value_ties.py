import unittest
from prototype_stress import tie_envelope


class ValueTieCheck(unittest.TestCase):
    def test_equal_baseline_choices_do_not_create_mandatory_strategy_gain(self):
        base={'A':2.,'B':2.,'C':1.}
        self.assertEqual(tie_envelope(base,{'A':2.,'B':3.,'C':2.}),(0.,1.,0.))
        self.assertEqual(tie_envelope(dict(reversed(list(base.items()))),{'A':2.,'B':3.,'C':2.}),(0.,1.,0.))
        self.assertEqual(tie_envelope(base,{'A':2.,'B':3.,'C':4.}),(0.,1.,1.))


if __name__=='__main__':unittest.main()
