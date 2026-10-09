import copy
import unittest
import unified_value as u
import score_cards as b


class CommonPanelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cards={c['id']:c for c in b.load_cards()}
        cls.reference,_=b.make_reference(list(cls.cards.values()))

    def score(self,c,p=None): return u.score(c,self.reference,p)

    def test_unaffordable_states_keep_their_weight_and_never_record_fake_payment(self):
        x=self.score(self.cards[15])
        self.assertEqual(x['context_count'],72)
        self.assertAlmostEqual(x['weight_sum'],1)
        waiting=[r for r in x['contexts'] if not r['cash_feasibility']['now_payable']]
        self.assertTrue(waiting)
        self.assertTrue(all(r['paid_cost_now'] is None and not r['actual_payment_made'] for r in waiting))
        self.assertLess(x['present_payable_design_weight'],1)
        self.assertLess(x['value_margin_model_gold'],x['intrinsic_net_quote_model_gold'])

    def test_cost_counterfactual_without_extra_delay_is_exactly_one_for_same_full_panel(self):
        p={'delay_rate':{r:0 for r in u.ROLES},'burn_option_multiplier':0}
        c=dict(self.cards[15],cost=4)
        d=dict(c,cost=5)
        a=self.score(c,p); z=self.score(d,p)
        self.assertAlmostEqual(a['value_margin_model_gold']-z['value_margin_model_gold'],1)
        self.assertEqual([r['weight'] for r in a['contexts']],[r['weight'] for r in z['contexts']])

    def test_wait_does_not_discount_nominal_cost_or_reduce_negative_quote_deficiency(self):
        c=dict(self.cards[15],cost=6,effect_readable='Magic: Give a monster +99 HP.')
        p=u.normalize_profile()
        s=u.make_panel(p)[0]
        x=u.quote_state(c,s,self.reference,p)
        self.assertGreater(x['cash_feasibility']['earliest_extra_wait'],0)
        self.assertEqual(x['nominal_cost'],6)
        self.assertAlmostEqual(x['adjusted_net_quote_model_gold'],x['reservation_quote_model_gold']-6)
        # With only hostile targets the Magic is harmful; positivity clipping
        # applies to delay loss only, never to the card's net quote.
        s['ally_bodies_before_play']=[]
        y=u.quote_state(c,s,self.reference,p)
        self.assertLess(y['gross_quote_model_gold'],0)
        self.assertEqual(y['additional_wait_loss'],0)

    def test_more_reserved_budget_or_less_available_income_never_improves_cash_wait(self):
        c=self.cards[43]
        p=u.normalize_profile(); s=u.make_panel(p)[0]
        a=u.affordability(c,s,p)
        z=u.affordability(c,s,u.normalize_profile({'reserved_gold_budget':2,'future_income_available_fraction':.5}))
        self.assertGreaterEqual(z['earliest_extra_wait'],a['earliest_extra_wait'])

    def test_beyond_window_is_retained_not_silently_removed(self):
        x=self.score(self.cards[43],{'future_income_available_fraction':0})
        self.assertGreater(x['no_payment_within_window_weight'],0)
        self.assertAlmostEqual(x['weight_sum'],1)
        self.assertTrue(all(r['weight']>0 for r in x['contexts']))

    def test_fixed_deck_hand_profile_changes_shared_growth_quote_without_name_bonus(self):
        low={'resource_state_weights':{'deployed':.8,'reserved':.2}}
        high={'resource_state_weights':{'deployed':.2,'reserved':.8}}
        c=self.cards[49]
        renamed=dict(c,id=-123,name='Counterfactual body')
        self.assertGreater(self.score(c,high)['value_margin_model_gold'],self.score(c,low)['value_margin_model_gold'])
        self.assertAlmostEqual(self.score(c,high)['value_margin_model_gold'],self.score(renamed,high)['value_margin_model_gold'])

    def test_unknown_mechanisms_stay_partial_and_not_a_false_lower_bound(self):
        x=self.score(self.cards[530])
        self.assertEqual(x['support_status'],'partial')
        self.assertIsNone(x['value_margin_model_gold'])
        self.assertIsNone(x['value_quote_model_gold'])
        self.assertTrue(x['unsupported'])

    def test_invalid_profiles_fail_before_pricing(self):
        for p in ({'role_weights':{'aggro':1}}, {'future_income_available_fraction':float('nan')},
                  {'extra_wait_hand_shadow':True}, {'maximum_extra_wait':1.5},
                  {'context_overrides':{'not-an-id':{}}}):
            with self.assertRaises(ValueError): self.score(self.cards[15],p)

    def test_integer_attack_marginals_are_dense_and_do_not_use_cost_specific_masks(self):
        c=dict(self.cards[15],attack=6,health=7,cost=4,effect_readable='')
        d=dict(c,attack=7)
        a=self.score(c); z=self.score(d)
        delta=z['value_margin_model_gold']-a['value_margin_model_gold']
        self.assertGreater(delta,0)
        self.assertLess(delta,.77)
        self.assertEqual(a['weight_sum'],z['weight_sum'])

    def test_capacity_loss_occurs_only_at_an_additional_burn_threshold(self):
        p=u.normalize_profile(); s=u.make_panel(p)[0]
        s['hand_size_before_play']=3
        self.assertEqual(u.waiting_hand(s,2,p)['additional_natural_burns'],0)
        s['hand_size_before_play']=6
        hand=u.waiting_hand(s,2,p)
        self.assertEqual(hand['hand_before_deployment'],7)
        self.assertEqual(hand['additional_natural_burns'],1)

    def test_cheaper_card_keeps_voluntary_wait_routes_and_cannot_score_worse(self):
        c=dict(self.cards[49],cost=4)
        expensive=dict(c,cost=5)
        a=self.score(c); z=self.score(expensive)
        self.assertGreaterEqual(a['value_margin_model_gold'],z['value_margin_model_gold'])
        self.assertGreaterEqual(a['optional_use_surplus_model_gold'],z['optional_use_surplus_model_gold'])

    def test_reserve_larger_than_current_balance_does_not_create_available_cash(self):
        p=u.normalize_profile({'reserved_gold_budget':6})
        s=u.make_panel(p)[0]
        s['gold_before_play']=4
        x=u.affordability(self.cards[15],s,p)
        # Actual cash 4+4=8; keeping 6 leaves 2, not 4.
        self.assertEqual(x['cash_path'][1]['available_for_candidate'],2)
        self.assertTrue(x['legally_affordable_now'] is False)

    def test_unpayable_poison_does_not_switch_forced_price_to_zero(self):
        c=dict(self.cards[15],attack=2,health=2,cost=5,effect_readable='Magic: Give a monster +99 HP.')
        p=u.normalize_profile({'maximum_extra_wait':0})
        s=u.make_panel(p)[0]
        s['ally_bodies_before_play']=[]
        x=u.quote_state(c,s,self.reference,p)
        self.assertFalse(x['pricing_supported'])
        self.assertNotIn('adjusted_net_quote_model_gold',x)
        self.assertTrue(x['tail_value_not_estimated'])

    def test_unpayable_route_still_reports_actual_extra_capacity_loss(self):
        c=self.cards[43]
        p=u.normalize_profile({'future_income_available_fraction':0})
        s=u.make_panel(p)[0]
        s['hand_size_before_play']=6
        x=u.quote_state(c,s,self.reference,p)
        self.assertGreater(x['extra_hand_wait_loss'],0)
        self.assertEqual(x['forecast_hand']['additional_natural_burns'],1)

    def test_second_player_real_gold_is_not_clipped_to_first_player_cap(self):
        p=u.normalize_profile({'second_player':True,
             'context_overrides':{'aggro-t3-deployed':{'gold_before_play':9}}})
        s=u.make_panel(p)[0]
        self.assertEqual(s['cumulative_base_gold_cap'],9)
        self.assertEqual(s['gold_before_play'],9)
        self.assertEqual(u.forecast_context(s,2,p)[0]['gold_before_play'],19)

    def test_rich_hand_resource_weight_does_not_change_opponent_board_prior(self):
        a=u.make_panel(u.normalize_profile({'resource_state_weights':{'deployed':1,'reserved':0}}))
        z=u.make_panel(u.normalize_profile({'resource_state_weights':{'deployed':0,'reserved':1}}))
        for role in u.ROLES:
            for board in ('pressured','contested','clear'):
                wa=sum(r['weight'] for r in a if r['role']==role and r['board_state']==board)
                wz=sum(r['weight'] for r in z if r['role']==role and r['board_state']==board)
                self.assertAlmostEqual(wa,wz)

    def test_joint_resource_distribution_preserves_one_gold_payment_threshold(self):
        samples={str(t):[{'gold_before_play':6,'hand_size_before_play':3,'weight':.49},
                         {'gold_before_play':7,'hand_size_before_play':3,'weight':.51}]
                 for t in (3,5,8)}
        p=u.normalize_profile({'resource_joint_samples':samples})
        panel=u.make_panel(p)
        self.assertEqual(len({s['context_id'] for s in panel}),len(panel))
        self.assertAlmostEqual(sum(s['weight'] for s in panel),1)
        for cost,expected in ((6,1),(7,.51)):
            c=dict(self.cards[15],cost=cost)
            observed=sum(s['weight'] for s in panel if u.affordability(c,s,p)['now_payable'])
            self.assertAlmostEqual(observed,expected)
        for role in u.ROLES:
            for board,expected in p['board_weights'][role].items():
                weight=sum(s['weight'] for s in panel if s['role']==role and s['board_state']==board)
                self.assertAlmostEqual(weight,p['role_weights'][role]*expected)

    def test_resource_samples_reject_overrides_duplicates_and_over_budget(self):
        samples={str(t):[{'gold_before_play':6,'hand_size_before_play':3,'weight':1}]
                 for t in (3,5,8)}
        p=u.normalize_profile({'resource_joint_samples':samples,
                              'context_overrides':{'aggro-t3-deployed':{'gold_before_play':7}}})
        with self.assertRaises(ValueError): u.make_panel(p)
        p=u.normalize_profile({'resource_joint_samples':samples,
                              'context_overrides':{'aggro-t3-reserved':{'gold_before_play':7}}})
        with self.assertRaises(ValueError): u.make_panel(p)
        samples['3'][0]['gold_before_play']=8
        with self.assertRaises(ValueError): u.make_panel(u.normalize_profile({'resource_joint_samples':samples}))
        samples['3']=[dict(samples['5'][0],weight=.5),dict(samples['5'][0],weight=.5)]
        with self.assertRaises(ValueError): u.normalize_profile({'resource_joint_samples':samples})


if __name__=='__main__': unittest.main()
