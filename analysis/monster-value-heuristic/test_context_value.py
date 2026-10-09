import copy
import unittest
import context_value as v
import heuristic_contexts as h
import score_cards as b


class ContextLedgerTests(unittest.TestCase):
    def setUp(self):
        self.cards = {c['id']: c for c in b.load_cards()}
        self.reference, _ = b.make_reference(list(self.cards.values()))
        self.ctx = h.bind_candidate(h.make_contexts()[1], 6)

    def test_self_growth_uses_one_joint_final_body_and_post_play_hand(self):
        c = dict(self.cards[15], attack=2, health=2, cost=6,
                 effect_readable='Magic: Gain ATK +1/HP +1 for each card in your hand.')
        terms, unknown = v.parse(c)
        self.assertFalse(unknown)
        r = v.evaluate_branch(c, self.ctx, terms, self.reference)
        growth = next(t for t in r['ledger'] if t['term']=='joint_self_growth')
        expected = v.body(7, 7, self.reference, 'aggro') - v.body(2, 2, self.reference, 'aggro')
        self.assertAlmostEqual(growth['gross_growth'], expected)
        self.assertAlmostEqual(growth['model_gold'], .8 * expected)
        self.assertEqual(len([x for x in r['ledger'] if x['term']=='joint_self_growth']), 1)

    def test_discount_only_counts_paid_cards_once_and_keeps_cash_separate(self):
        c = dict(self.cards[15], cost=6, effect_readable='Dust: Give all cards in your hand -1 COST.')
        terms, _ = v.parse(c)
        r = v.evaluate_branch(c, self.ctx, terms, self.reference)
        cash = r['ledger'][-1]
        self.assertEqual(cash['conditional_saved_gold'], 2)
        self.assertEqual(cash['payments']['rows'][1]['saved_paid_gold'], 0)
        self.assertAlmostEqual(cash['model_gold'], .45 * .7 * 2)
        self.assertEqual(r['paid_cost'], 6)

    def test_current_choice_never_adds_both_or_reads_future_usage(self):
        c = dict(self.cards[15], cost=7,
                 effect_readable='Magic: Deal 3 DMG to an enemy or give an ally monster +3 ATK.')
        modules, _ = v.parse(c)
        branches = h.enumerate_choice_branches(modules)
        self.assertEqual(len(branches), 2)
        self.assertTrue(all(len(x['selected_module_indexes'])==1 for x in branches))
        for branch in branches:
            chosen = [modules[i] for i in branch['selected_module_indexes']]
            before = v.evaluate_branch(c, self.ctx, chosen, self.reference)['net_model_gold']
            changed = copy.deepcopy(self.ctx)
            changed['death_event_hand_costs'] = [100] * 7
            changed['actually_used_mask'] = [False] * 7
            after = v.evaluate_branch(c, changed, chosen, self.reference)['net_model_gold']
            self.assertEqual(before, after)

    def test_discount_frontier_replaces_mask_savings_and_never_adds_full_bodies(self):
        ctx=copy.deepcopy(self.ctx)
        ctx['death_event_hand_quotes']=[{'cost':c,'gross_model_gold':c+.5} for c in ctx['death_event_hand_costs']]
        ctx['future_payment_play_caps']=[2,2]
        terms,_=v.parse(self.cards[43])
        result=v.evaluate_branch(self.cards[43],ctx,terms,self.reference)
        rows=[x for x in result['ledger'] if x['term'].startswith('dust_')]
        self.assertEqual(len(rows),1)
        frontier=rows[0]['frontier']
        self.assertAlmostEqual(frontier['total_net_improvement_model_gold'],
                               frontier['direct_paid_savings_gold']+frontier['additional_unlocked_net_model_gold'])
        self.assertAlmostEqual(rows[0]['model_gold'],.45*.7*frontier['total_net_improvement_model_gold'])
        ctx['death_event_hand_quotes'][0]['cost']=99
        with self.assertRaises(ValueError):
            v.evaluate_branch(self.cards[43],ctx,terms,self.reference)

    def test_unaffordable_cost_is_not_paid_or_renormalized_into_a_global_rank(self):
        r = v.score(self.cards[15], self.reference)
        self.assertLess(r['payable_design_weight'], 1)
        self.assertTrue(all(x['net_model_gold'] is None for x in r['contexts'] if not x['affordable']))
        self.assertIn('conditional', r['score_scope'])

    def test_same_panel_cost_counterfactual_is_exactly_one(self):
        c = dict(self.cards[15], cost=4,
                 effect_readable='Magic: Gain ATK +1/HP +1 for each card in your hand.')
        d = dict(c, cost=5)
        pair = v.compare_pair(c, d, self.reference)
        self.assertAlmostEqual(pair['full_heuristic_common_context_delta'], 1)
        self.assertLess(pair['right_payable_weight'], pair['left_payable_weight'])

    def test_complex_haste_and_conditional_text_never_gets_a_fake_complete_score(self):
        for cid in (530, 984):
            r = v.score(self.cards[cid], self.reference)
            self.assertEqual(r['support_status'], 'partial')
            self.assertIsNone(r['conditional_net_model_gold'])

    def test_instant_damage_is_preserved_before_both_keyword_counterfactuals(self):
        c = dict(self.cards[21], cost=6,
                 effect_readable='Haste. Magic: Deal 9 DMG to all enemy monsters and 3 DMG to the opponent.')
        terms, unknown = v.parse(c)
        self.assertFalse(unknown)
        result = v.evaluate_branch(c, self.ctx, terms, self.reference)
        contact = result['ledger'][-1]
        self.assertEqual(contact['term'], 'paired_keyword_exchange_increment')
        self.assertAlmostEqual(contact['model_gold'], 0)
        for side in ('post_magic_ordinary', 'keyword_bundle'):
            for outcome in contact['details'][side]['outcomes'].values():
                self.assertTrue(all(t['health']<=0 for t in outcome['state']['enemies']))
        self.assertEqual(len([r for r in result['ledger'] if r['term']=='magic_immediate_resource_delta']), 1)
        self.assertTrue(any(t['health']>0 for t in contact['details']['ordinary']['outcomes']['none']['state']['enemies']))

    def test_keyword_plus_lifecycle_not_silently_accepted(self):
        c = dict(self.cards[168], effect_readable='Dodge (1). Dust: Earn GOLD 2.')
        _, unknown = v.parse(c)
        self.assertTrue(unknown)
        self.assertIsNone(v.score(c, self.reference)['conditional_net_model_gold'])

    def test_magic_uses_damage_instances_before_keyword_window(self):
        ctx=copy.deepcopy(self.ctx)
        ctx['enemy_bodies']=[{'attack':3,'health':1,'dodge':1}]
        terms,_=v.parse(self.cards[21])
        result=v.evaluate_branch(self.cards[21],ctx,terms,self.reference)
        magic=next(r for r in result['ledger'] if r['term']=='magic_immediate_resource_delta')
        self.assertAlmostEqual(result['ledger'][-1]['details']['immediate_damage_only_diagnostic']['component_deltas']['remaining_enemy_bodies'],0)
        self.assertAlmostEqual(magic['model_gold'],3*b.role_parameters('aggro')['face_damage_value'])
        contact=result['ledger'][-1]['details']
        self.assertEqual(contact['post_magic_ordinary']['outcomes']['none']['state']['enemies'][0]['dodge'],0)
        self.assertEqual(contact['ordinary']['outcomes']['none']['state']['enemies'][0]['dodge'],1)

    def test_conditional_haste_family_binds_both_boards_and_received_damage_gate(self):
        c=dict(self.cards[15],attack=3,health=7,cost=6,
               effect_readable='Magic: Deal 1 DMG to a monster for each other monster. If this deals 3 or less DMG, gain Haste.')
        terms,unknown=v.parse(c)
        self.assertFalse(unknown)
        ctx=copy.deepcopy(self.ctx)
        result=v.evaluate_branch(c,ctx,terms,self.reference)
        details=result['ledger'][-1]['details']
        self.assertTrue(details['effective_statuses']['haste'])
        self.assertEqual(details['magic_selection'][0]['targets'][0]['nominal_damage'],ctx['other_monster_count'])
        self.assertAlmostEqual(sum(row['model_gold'] for row in result['ledger'][3:]),details['total_delta_model_gold'])
        ctx['enemy_bodies'][0]['armor']=True
        with self.assertRaises(ValueError): v.evaluate_branch(c,ctx,terms,self.reference)

    def test_hand_damage_prefix_is_quantified_but_linked_trigger_not_faked(self):
        card=self.cards[984]
        terms,unknown=v.parse(card)
        self.assertTrue(unknown)
        result=v.evaluate_branch(card,self.ctx,terms,self.reference)
        hit=result['ledger'][-1]['details']['magic_selection'][0]['targets'][0]
        self.assertEqual(hit['nominal_damage'],self.ctx['hand_size_after_play'])
        self.assertIsNone(v.score(card,self.reference)['conditional_net_model_gold'])

    def test_keyword_only_and_zero_magic_share_terminal_health_boundary(self):
        ctx=copy.deepcopy(self.ctx)
        ctx.update(own_player_hp=1,enemy_bodies=[{'attack':8,'health':8}])
        for text in ('Dodge (1).','Dodge (1). Magic: Deal 0 DMG to the opponent.'):
            c=dict(self.cards[15],attack=2,health=2,effect_readable=text)
            terms,unknown=v.parse(c)
            self.assertFalse(unknown)
            with self.assertRaises(ValueError): v.evaluate_branch(c,ctx,terms,self.reference)

    def test_pure_dodge_has_joint_exchange_price(self):
        terms, unknown = v.parse(self.cards[168])
        self.assertFalse(unknown)
        self.assertEqual(terms[0]['statuses'], {'dodge':1})
        result = v.evaluate_branch(self.cards[168], self.ctx, terms, self.reference)
        self.assertEqual(result['ledger'][-1]['term'], 'paired_keyword_exchange_increment')

    def test_intrinsic_self_damage_not_silence_reversible(self):
        c = self.cards[292]
        terms, unknown = v.parse(c)
        self.assertFalse(unknown)
        result = v.evaluate_branch(c, self.ctx, terms, self.reference)
        self.assertAlmostEqual(result['gross_model_gold'], v.body(c['attack'], c['health']-5, self.reference, 'aggro'))

    def test_ally_all_joint_buff_excludes_caster(self):
        ctx = h.bind_candidate(h.make_contexts()[0], 4)
        c = self.cards[104]
        terms, unknown = v.parse(c)
        self.assertFalse(unknown)
        result = v.evaluate_branch(c, ctx, terms, self.reference)
        entry = next(t for t in result['ledger'] if t['term']=='joint_all_other_ally_buff')
        expected = sum(v.body(t['attack']+1,t['health']+1,self.reference,'aggro')-v.body(t['attack'],t['health'],self.reference,'aggro') for t in ctx['ally_bodies_before_play'])
        self.assertEqual(entry['target_count'],2)
        self.assertAlmostEqual(entry['model_gold'], expected)

    def test_hostile_only_health_target_retains_negative_effect(self):
        c = self.cards[23]
        terms, _ = v.parse(c)
        result = v.evaluate_branch(c, self.ctx, terms, self.reference)
        entry = next(t for t in result['ledger'] if t['term']=='mandatory_any_monster_health')
        self.assertLess(entry['model_gold'], 0)

    def test_enemy_debuff_and_health_gain_share_one_target(self):
        c = self.cards[8]
        ctx = h.bind_candidate(h.make_contexts()[4], 8)
        terms, unknown = v.parse(c)
        self.assertFalse(unknown)
        result = v.evaluate_branch(c, ctx, terms, self.reference)
        entry = next(t for t in result['ledger'] if t['term']=='one_target_attack_to_self_health')
        chosen = entry['coupled_target']
        self.assertAlmostEqual(entry['model_gold'], chosen['enemy_delta'] + .9*chosen['own_growth'])


if __name__ == '__main__':
    unittest.main()
