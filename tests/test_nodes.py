from unittest.case import TestCase

from structured_dpp.factor_tree import *
from structured_dpp.factor_tree.node import Node


class TestNode(TestCase):
    def test_get_connected_nodes(self):
        parent_node = Node()
        main_node = Node()
        child_node_1, child_node_2 = Node(), Node()
        self.assertEqual(
            list(main_node.get_connected_nodes()),
            [],
            "Unconnected node yielded connected nodes"
        )

        main_node.add_child(child_node_1)
        main_node.add_child(child_node_1)
        main_node.add_children([child_node_2])
        yielded_children = list(main_node.get_connected_nodes())
        self.assertEqual(
            len(yielded_children),
            2,
            "Identical children were yielded more than once."
        )
        self.assertIn(
            child_node_1,
            yielded_children,
            "Child not yielded in connected nodes."
        )
        self.assertIn(
            child_node_2,
            yielded_children,
            "Child not yielded in connected nodes."
        )

        yielded_children_excluding = list(main_node.get_connected_nodes(exclude=child_node_1))
        self.assertListEqual(
            yielded_children_excluding,
            [child_node_2],
            "Yielding with exclusion did not exclude child."
        )

        main_node.parent = parent_node
        yielded_with_parent = list(main_node.get_connected_nodes())
        self.assertEqual(
            len(yielded_with_parent),
            3,
            "Parent not yielded in connected nodes."
        )
        self.assertIn(
            parent_node,
            yielded_with_parent,
            "Parent not yielded in connected nodes."
        )

        yielded_parent_excluding = list(main_node.get_connected_nodes(exclude=parent_node))
        self.assertListEqual(
            yielded_parent_excluding,
            yielded_children,
            "Yielding with exclusion did not exclude parent."
        )

    def test_str(self):
        parent_node = Node(name='Beth')
        main_node = Node(parent=parent_node)
        child_node_1, child_node_2, child_node_3 = Node(), Node(), Node()
        self.assertEqual(
            str(parent_node),
            "Beth(parent=None,0 children)",
            "Name of named unconnected node wrong."
        )
        self.assertEqual(
            str(main_node),
            "Node(parent=Beth,0 children)",
            "Name of child node wrong."
        )
        main_node.add_children([child_node_1, child_node_2])
        main_node.add_child(child_node_3)
        self.assertEqual(
            str(main_node),
            "Node(parent=Beth,3 children)",
            "Name of node with children wrong."
        )


class TestFactor(TestCase):
    def test_get_consistent_assignments(self):
        parent_var = Variable(allowed_values=[0, 1, 2])
        factor = Factor(lambda: None, parent=parent_var)
        child_var_1, child_var_2 = Variable(allowed_values='ab'), Variable(allowed_values='cd')

        self.assertListEqual(
            list(factor.get_consistent_assignments(parent_var, 1)),
            [{parent_var: 1}],
            'Getting consistent assignments failed for a factor connected to a single variable.'
        )

        factor.add_children([child_var_1])
        self.assertListEqual(
            list(factor.get_consistent_assignments(parent_var, 1)),
            [
                {parent_var: 1, child_var_1: 'a'},
                {parent_var: 1, child_var_1: 'b'}
            ],
            'Getting consistent assignments failed for a factor connected to two variables.'
        )

        factor.children = [child_var_1, child_var_2]
        self.assertListEqual(
            list(factor.get_consistent_assignments(child_var_1, 'a')),
            [
                {child_var_1: 'a', child_var_2: 'c', parent_var: 0},
                {child_var_1: 'a', child_var_2: 'c', parent_var: 1},
                {child_var_1: 'a', child_var_2: 'c', parent_var: 2},
                {child_var_1: 'a', child_var_2: 'd', parent_var: 0},
                {child_var_1: 'a', child_var_2: 'd', parent_var: 1},
                {child_var_1: 'a', child_var_2: 'd', parent_var: 2},
            ],
            'Getting consistent assignments failed for a factor connected to three variables.'
        )

    def test_create_message(self):
        @assignment_to_var_arguments
        def get_weight1(val):
            return val ** 2

        @assignment_to_var_arguments
        def get_weight2(*values):
            return sum(values)

        parent = Variable(allowed_values=[0, 1, 2, 3], name='ParentVar')
        childless_factor = Factor(get_weight=get_weight1, parent=parent)
        self.assertEqual(
            childless_factor.create_message(to=parent, value=2),
            4,  # With no children the value of the message is just the value of the single connected variable squared
            'Factor created message had wrong value in the case where it was connected to only 1 parent-variable '
            '(aka does not need incoming messages to generate message).'
        )
        parentless_factor = Factor(get_weight=get_weight1, children=[parent])
        self.assertEqual(
            parentless_factor.create_message(to=parent, value=3),
            9,  # With only one other node connection the message is just the value of the single connected var squared.
            'Factor created message had wrong value in the case where it was connected to only 1 child-variable '
            '(aka does not need incoming messages to generate message).'
        )

        children = [Variable(allowed_values=[0, 1, 2], name='Var' + str(i)) for i in range(2)]
        factor = Factor(get_weight=get_weight2, parent=parent, children=children)
        for child in children:
            child.outgoing_messages = {None: {
                factor: {
                    0: 0,
                    1: 1,
                    2: 2
                }
            }}

        self.assertEqual(
            factor.create_message(to=parent, value=0),
            (1 + 1) * 1 * 1 + (1 + 2) * 1 * 2 * 2 + (2 + 2) * 2 * 2,
            'Message was not correct value for message to parent with children.'
        )

        self.assertEqual(
            factor.create_message(to=parent, value=2),
            (2 + 1 + 1) * 1 * 1 + (2 + 1 + 2) * 1 * 2 * 2 + (2 + 2 + 2) * 2 * 2
        )


class TestVariable(TestCase):
    def test_create_message(self):
        parent = Factor(lambda: None)
        childless_var = Variable(allowed_values=[22], parent=parent)
        self.assertEqual(
            childless_var.create_message(parent, 9e10),
            1,
            'Variable connected message had wrong value when connected to only 1 parent-factor '
            '(aka did not need incoming messages to generate new message)'
        )
        self.assertEqual(
            childless_var.create_message(parent, 9e10),
            1,
            'Variable generated message was wrong after change in semiring settings.'
        )

        parentless_var = Variable(allowed_values=[-5])
        parentless_var.add_child(parent)
        self.assertEqual(
            parentless_var.create_message(parent, 9e10),
            1,
            'Variable connected message had wrong value when connected to only 1 child-factor '
            '(aka did not need incoming messages to generate new message)'
        )

        children = [Factor(lambda: None) for _ in range(4)]
        var = Variable(allowed_values='ab', parent=parent, children=children)
        for i, child in enumerate(children):
            child.outgoing_messages = {'run': {var: {'a': 5, 'b': i + 1}}}
        parent.outgoing_messages = {'run': {var: {'b': 100}}}

        self.assertEqual(
            var.create_message(parent, 'a', run='run'),
            5 ** 4
        )
        self.assertEqual(
            var.create_message(children[0], 'b', run='run'),
            2 * 3 * 4 * 100
        )