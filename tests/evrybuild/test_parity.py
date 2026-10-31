"""Checks for scripts/parity.py. The optional real run needs a LocalExile checkout and a saved build:
  python tests/evrybuild/test_parity.py --localexile C:\\LocalExile --build C:\\Builds\\Example.xml -v
"""
import argparse
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
import parity

LOCALEXILE = None
BUILD = None


class Normalize(unittest.TestCase):
    def test_jewels_leave_the_tree(self):
        xml = '<Sockets><Socket nodeId="1" itemId="2"/><Socket itemId="3" nodeId="4" /></Sockets>'
        self.assertEqual('<Sockets></Sockets>', parity.normalize(xml))

    def test_flasks_stop_being_active_wherever_the_attribute_sits(self):
        for tag in ('<Slot active="true" name="Flask 1" itemId="5"/>', '<Slot name="Flask 1" active="true" itemId="5"/>',
                    '<Slot name="Flask 1" itemId="5" active="true"/>'):
            with self.subTest(tag=tag): self.assertNotIn('active', parity.normalize(tag))

    def test_only_slots_lose_active(self):
        self.assertIn('active="true"', parity.normalize('<Other active="true"/>'))

    def test_bandit_and_pantheon_are_cleared(self):
        result = parity.normalize('<Build bandit="Alira" pantheonMajorGod="Lunaris" pantheonMinorGod="Gruthkul"/>')
        self.assertEqual('<Build bandit="None" pantheonMajorGod="None" pantheonMinorGod="None"/>', result)


class Slots(unittest.TestCase):
    def test_clearing_keeps_other_slots_and_works_in_either_attribute_order(self):
        xml = '<Slot name="Boots" itemId="7"/><Slot itemId="8" name="Helmet"/><Slot name="Belt" itemId="9"/>'
        self.assertEqual('<Slot name="Boots" itemId="0"/><Slot itemId="0" name="Helmet"/><Slot name="Belt" itemId="9"/>',
            parity.clear_slots(xml, {'Boots', 'Helmet'}))

    def test_a_slot_name_must_match_exactly(self):
        xml = '<Slot name="Weapon 1 Swap" itemId="7"/>'
        self.assertEqual(xml, parity.clear_slots(xml, {'Weapon 1'}))

    def test_skipped_items_name_their_slot(self):
        warnings = ['Skipped item in Weapon 2 Swap: special sockets on Ornate Quiver are not implemented.', 'Skipped passive 5.', 'Other']
        self.assertEqual({'Weapon 2 Swap'}, parity.skipped_slots(warnings))

    def test_every_equipment_row_has_a_slot(self):
        self.assertEqual({1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 14, 15}, set(parity.SLOTS))


class SkippedLines(unittest.TestCase):
    def test_both_warning_forms_give_base_and_line(self):
        warnings = ["Skipped modifier on Iron Ring: unsupported explicit modifier '+6% Chance to Block'.",
            "Skipped modifier on Plate Vest: no native modifier with matching stats and rolls for '+397 to Armour' on Plate Vest at item level 85.",
            'Skipped gem one.']
        self.assertEqual([dict(base='Iron Ring', line='+6% Chance to Block'), dict(base='Plate Vest', line='+397 to Armour')],
            parity.skipped_lines(warnings))

    def test_a_line_may_hold_a_quote(self):
        warning = "Skipped modifier on Gold Ring: unsupported explicit modifier 'Grants Kitava's Thirst'."
        self.assertEqual("Grants Kitava's Thirst", parity.skipped_lines([warning])[0]['line'])

    def test_only_lines_that_can_change_a_number_are_reported(self):
        lines = ['Paladin Boots: Searing Exarch Item', 'Shield: +6% Chance to Block', 'Helmet: +5 to Strength']
        self.assertEqual(['Helmet: +5 to Strength'], parity.still_counted(lines, ['Shield']))


class Compare(unittest.TestCase):
    def rows(self, pob, server):
        return {r['stat']: r for r in parity.compare(pob, server)}

    def test_statuses(self):
        rows = self.rows({'Life': 100, 'Mana': 100, 'Armour': 100}, {'Life': 100, 'Mana': 101, 'Armour': 90})
        self.assertEqual('match', rows['Life']['status'])
        self.assertEqual('rounding', rows['Mana']['status'])
        self.assertEqual('mismatch', rows['Armour']['status'])
        self.assertEqual(-10, rows['Armour']['difference'])

    def test_a_stat_only_one_side_reports_is_missing_not_a_match(self):
        rows = self.rows({}, {'Life': 100})
        self.assertEqual('missing', rows['Life']['status'])

    def test_every_stat_is_compared_once(self):
        labels = [s[0] for s in parity.STATS]
        self.assertEqual(len(labels), len(set(labels)))

    def test_report_names_inactive_items_and_uncounted_lines(self):
        text = parity.render(parity.compare({}, {}), [dict(base='Ring', line='+1 to Life')], ['Helmet: +5 to Strength'], 'identity', False, ['Boots'])
        self.assertIn('Boots', text); self.assertIn('Helmet: +5 to Strength', text); self.assertNotIn('+1 to Life', text)
        self.assertIn('+1 to Life', parity.render(parity.compare({}, {}), [dict(base='Ring', line='+1 to Life')], [], 'identity', True))


class RealBuild(unittest.TestCase):
    def test_attributes_agree_for_a_real_build(self):
        if not (LOCALEXILE and BUILD): self.skipTest('Pass --localexile and --build to compare a real build.')
        rows = {r['stat']: r for r in parity.run(LOCALEXILE, BUILD)['rows']}
        for stat in ('Strength', 'Dexterity', 'Intelligence', 'Mana', 'Armour', 'Energy Shield'):
            with self.subTest(stat=stat): self.assertEqual('match', rows[stat]['status'], rows[stat])


if __name__ == '__main__':
    parser = argparse.ArgumentParser(); parser.add_argument('--localexile', type=Path); parser.add_argument('--build', type=Path)
    args, remaining = parser.parse_known_args(); LOCALEXILE = args.localexile; BUILD = args.build
    unittest.main(argv=[__file__] + remaining)
