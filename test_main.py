import copy
import random
import unittest

import main


def make_pair(**overrides):
    player = main.Player()
    enemy = main.Enemy()
    player.enemy = enemy
    enemy.enemy = player

    for owner, attrs in overrides.items():
        target = player if owner == 'p' else enemy
        for key, value in attrs.items():
            setattr(target, key, value)

    return player, enemy


def dump(combatants):
    return {
        role: copy.deepcopy({
            key: value for key, value in combatant.__dict__.items()
            if key != 'enemy'
        })
        for role, combatant in zip(('p', 'e'), combatants)
    }


class TurnResolverTests(unittest.TestCase):
    CASES = [
        {
            'name': 'cleanse cancels pre-existing poison dot on the actor',
            'setup': {'p': {'effects': {'poison': 5}}},
            'moves': [('dodge', 'heal'), ('cleanse', 'heal')],
            'expect': [
                {'p.hp': 98, 'p.fx': {'poison': 4}},
                {'p.hp': 98, 'p.fx': {}},
            ],
        },
        {
            'name': 'cleanse does not erase poison applied in the same turn',
            'moves': [('cleanse', 'poison')],
            'expect': [{'p.hp': 100, 'p.fx': {'poison': 5}}],
        },
        {
            'name': 'cleanse does not erase fire applied in the same turn',
            'moves': [('cleanse', 'fire')],
            'expect': [{'p.hp': 100, 'p.fx': {'fire': 3}}],
        },
        {
            'name': 'enemy cleanse does not erase poison cast in the same turn',
            'moves': [('poison', 'cleanse')],
            'expect': [{'e.hp': 100, 'e.fx': {'poison': 5}}],
        },
        {
            'name': 'enemy cleanse does not erase fire cast in the same turn',
            'moves': [('fire', 'cleanse')],
            'expect': [{'e.hp': 100, 'e.fx': {'fire': 3}}],
        },
        {
            'name': 'cleanse removes only pre-existing effects, keeps new ones',
            'setup': {'p': {'effects': {'fire': 3}}},
            'moves': [('cleanse', 'poison')],
            'expect': [{'p.hp': 100, 'p.fx': {'poison': 5}}],
        },
        {
            'name': 'shield blocks consecutive enemy swords for its full duration',
            'moves': [('shield', 'sword'), ('dodge', 'sword'),
                      ('fire', 'sword')],
            'setup': {'p': {'energy': 100}},
            'expect': [
                {'p.hp': 100, 'p.shield': 2},
                {'p.hp': 100, 'p.shield': 1},
                {'p.hp': 90, 'p.shield': 0},
            ],
        },
        {
            'name': 'shielding again while active keeps blocking',
            'moves': [('shield', 'sword'), ('dodge', 'sword'),
                      ('shield', 'sword'), ('dodge', 'sword')],
            'expect': [
                {'p.hp': 100, 'p.shield': 2},
                {'p.hp': 100, 'p.shield': 1},
                {'p.hp': 100, 'p.shield': 2},
                {'p.hp': 100, 'p.shield': 1},
            ],
        },
        {
            'name': 'dodge halves sword damage when no shield remains',
            'moves': [('shield', 'sword'), ('dodge', 'sword'),
                      ('dodge', 'sword')],
            'expect': [
                {'p.hp': 100},
                {'p.hp': 100},
                {'p.hp': 95},
            ],
        },
        {
            'name': 'enemy shield blocks consecutive player swords',
            'moves': [('sword', 'shield'), ('sword', 'dodge'),
                      ('sword', 'heal')],
            'expect': [
                {'e.hp': 100, 'e.shield': 2},
                {'e.hp': 100, 'e.shield': 1},
                {'e.hp': 100, 'e.shield': 0},
            ],
        },
        {
            'name': 'fire applied this turn does not tick until next turn',
            'setup': {'p': {'energy': 100}},
            'moves': [('fire', 'heal'), ('dodge', 'heal')],
            'expect': [
                {'e.hp': 100, 'e.fx': {'fire': 3}, 'p.energy': 97},
                {'e.hp': 95, 'e.fx': {'fire': 2}},
            ],
        },
        {
            'name': 'poison refreshes full duration and ticks once per turn',
            'moves': [('poison', 'heal'), ('poison', 'heal'),
                      ('dodge', 'heal')],
            'expect': [
                {'e.hp': 100, 'e.fx': {'poison': 5}},
                {'e.hp': 98, 'e.fx': {'poison': 4}},
                {'e.hp': 98, 'e.fx': {'poison': 3}},
            ],
        },
        {
            'name': 'heal costs energy and is capped at 100',
            'setup': {'p': {'health': 95}},
            'moves': [('heal', 'heal')],
            'expect': [{'p.hp': 100, 'p.energy': 8}],
        },
        {
            'name': 'sword trades hurt both sides independently',
            'moves': [('sword', 'sword')],
            'expect': [{'p.hp': 90, 'e.hp': 92}],
        },
        {
            'name': 'effects expire at zero and stop dealing damage',
            'setup': {'e': {'effects': {'poison': 1}}},
            'moves': [('dodge', 'heal'), ('dodge', 'heal')],
            'expect': [
                {'e.hp': 98, 'e.fx': {}},
                {'e.hp': 100, 'e.fx': {}},
            ],
        },
        {
            'name': 'both dots tick deterministically and independently',
            'setup': {'e': {'effects': {'fire': 2, 'poison': 2}}},
            'moves': [('dodge', 'heal'), ('dodge', 'heal')],
            'expect': [
                {'e.hp': 93, 'e.fx': {'fire': 1, 'poison': 1}},
                {'e.hp': 93, 'e.fx': {}},
            ],
        },
        {
            'name': 'determinism: repeated seeded runs produce identical worlds',
            'setup': {'p': {'energy': 100},
                      'p_hist': ['sword'] * 6,
                      'e': {'health': 40}},
            'moves': [('fire', None), ('sword', None)],
            'seed': 1234,
            'expect': [],
        },
    ]

    KEYS = {
        'p.hp': ('p', 'health'),
        'e.hp': ('e', 'health'),
        'p.energy': ('p', 'energy'),
        'e.energy': ('e', 'energy'),
        'p.shield': ('p', 'until_shield'),
        'e.shield': ('e', 'until_shield'),
        'p.fx': ('p', 'effects'),
        'e.fx': ('e', 'effects'),
    }

    def run_case(self, case, seed=None, play_order=('enemy', 'player')):
        setup = copy.deepcopy(case.get('setup', {}))
        player, enemy = make_pair(**{k: v for k, v in setup.items()
                                     if k != 'p_hist'})
        history = setup.get('p_hist')
        if history is not None:
            player.history = list(history)

        rng = random.Random(seed if seed is not None else 0)
        moves_log = []
        results = []

        original_choices = main.random.choices
        if case.get('seed') is not None:
            main.random.choices = lambda *args, **kwargs: rng.choices(
                *args, **kwargs)

        try:
            for player_move, enemy_move in case['moves']:
                if enemy_move is None:
                    enemy.take_turn()
                    enemy_move = enemy.move
                moves_log.append((player_move, enemy_move))
                main.resolve_turn(player, enemy, player_move, enemy_move,
                                  play_order=play_order)
                results.append(dump((player, enemy)))
            return results, moves_log
        finally:
            main.random.choices = original_choices

    def assert_expectation(self, state, expected):
        for key, value in expected.items():
            role, attr = self.KEYS[key]
            self.assertEqual(state[role][attr], value, msg=f'field {key}')

    def test_table_driven_cases_with_deepcopy_snapshots(self):
        self.assertGreaterEqual(len(self.CASES), 12)

        for case in self.CASES:
            with self.subTest(case=case['name']):
                seed = case.get('seed')
                results_a, _ = self.run_case(case, seed=seed)
                results_b, _ = self.run_case(
                    copy.deepcopy(case), seed=seed)

                snapshot_before = copy.deepcopy(results_a)
                for index, expected in enumerate(case['expect']):
                    self.assert_expectation(results_a[index], expected)

                self.assertEqual(results_a, results_b)
                self.assertEqual(copy.deepcopy(snapshot_before), results_a)

    def test_play_order_does_not_change_result(self):
        for case in self.CASES:
            with self.subTest(case=case['name']):
                results_normal, moves = self.run_case(
                    copy.deepcopy(case), seed=7)
                results_swapped, _ = self.run_case(
                    copy.deepcopy(case), seed=7,
                    play_order=('player', 'enemy'))
                self.assertEqual(results_normal, results_swapped, msg=moves)

    def test_failure_rolls_back_everything_and_does_not_pollute(self):
        for case in self.CASES[:6]:
            with self.subTest(case=case['name']):
                fresh = copy.deepcopy(case)
                player, enemy = make_pair(**copy.deepcopy(fresh.get('setup', {})))
                before = dump((player, enemy))

                player_move, enemy_move = fresh['moves'][0]

                class Boom(Exception):
                    pass

                def explode(self):
                    raise Boom()

                original_play = main.Player.play
                main.Player.play = explode
                try:
                    with self.assertRaises(Boom):
                        main.resolve_turn(player, enemy, player_move, enemy_move)
                finally:
                    main.Player.play = original_play

                self.assertEqual(dump((player, enemy)), before)
                self.assertIs(player.enemy, enemy)
                self.assertIs(enemy.enemy, player)

                main.resolve_turn(player, enemy, player_move, enemy_move)
                rerun, _ = self.run_case(copy.deepcopy(fresh), seed=1)
                self.assertEqual(dump((player, enemy)), rerun[0])

    def test_snapshots_are_independent_deepcopies(self):
        player, enemy = make_pair(**{'p': {'effects': {'fire': 3}}})
        snapshots = main.snapshot_combatants((player, enemy))
        player.effects['fire'] = 1
        player.health = 1
        self.assertEqual(snapshots[0]['effects'], {'fire': 3})
        self.assertEqual(snapshots[0]['health'], 100)

        main.restore_combatants((player, enemy), snapshots)
        self.assertEqual(player.effects, {'fire': 3})
        self.assertEqual(player.health, 100)
        player.effects['fire'] = 9
        self.assertEqual(snapshots[0]['effects'], {'fire': 3})


if __name__ == '__main__':
    unittest.main()
