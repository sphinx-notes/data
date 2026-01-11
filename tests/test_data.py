import os
import sys
import unittest
from textwrap import dedent

sys.path.insert(0, os.path.abspath('./src/sphinxnotes'))

from data.data import Field, Registry, BoolFlag, OperFlag

class TestFieldParser(unittest.TestCase):

    # ==========================
    # Basic Types
    # ==========================
    
    def test_basic_scalar(self):
        f = Field.from_dsl('int')
        self.assertEqual(f.parse('123'), 123)
        
        f = Field.from_dsl('bool')
        self.assertTrue(f.parse('true'))
        self.assertTrue(f.parse('y'))
        self.assertFalse(f.parse('false'))

    # ==========================
    # Container Forms
    # ==========================

    def test_list_default_sep(self):
        # Your default list sep is ',' (comma)
        f = Field.from_dsl('list of int')
        self.assertEqual(f.parse('1, 2, 3'), [1, 2, 3])

    def test_words_form(self):
        # words sep is ' ' (arbitrary whitespace)
        f = Field.from_dsl('words of str')
        self.assertEqual(f.parse('a   b\tc'), ['a', 'b', 'c'])

    def test_lines_form(self):
        # lines sep is '\n'
        f = Field.from_dsl('lines of int')
        self.assertEqual(f.parse('1\n2\n3'), [1, 2, 3])

    # ==========================
    # Modifiers
    # ==========================

    def test_sep_by_override(self):
        # Override default comma with pipe
        f = Field.from_dsl("list of int, sep by '|'")
        self.assertEqual(f.parse('1|2|3'), [1, 2, 3])

    def test_sep_by_implies_list(self):
        # 'sep by' without form implies list
        f = Field.from_dsl("int, sep by ';'")
        self.assertEqual(f.parse('1; 2; 3'), [1, 2, 3])

    def test_required(self):
        f = Field.from_dsl('int, req')
        self.assertTrue(f.required)
        f = Field.from_dsl('int, required')
        self.assertTrue(f.required)
        with self.assertRaisesRegex(ValueError, 'argument required'):
            f.parse(None)

    # ==========================
    # Parsing Logic
    # ==========================

    def test_empty_input(self):
        # Optional scalar -> None
        self.assertIsNone(Field.from_dsl('int').parse(None))
        # Optional list -> []
        self.assertEqual(Field.from_dsl('list of int').parse(None), [])

    def test_quoted_separator(self):
        # Test quoted separator parsing in DSL
        f = Field.from_dsl("list of str, sep by ','")
        self.assertEqual(f.parse('a,b,c'), ['a', 'b', 'c'])

    def test_escaped_separator(self):
        # Test escaping \n in DSL
        f = Field.from_dsl(r"list of str, sep by '\n'")
        self.assertEqual(f.parse('a\nb'), ['a', 'b'])

    def test_custom_bool_flags(self):
        Registry.flags['uniq'] = BoolFlag('uniq')
        f = Field.from_dsl(r'int, uniq')
        self.assertTrue(f.uniq)
        f = Field.from_dsl(r'int')
        self.assertFalse(f.uniq)
        
        # Test default value.
        Registry.flags['ref'] = BoolFlag('ref', default=True)
        f = Field.from_dsl(r'int, ref')
        self.assertFalse(f.ref)
        f = Field.from_dsl(r'int')
        self.assertTrue(f.ref)

    def test_custom_oper_flags(self):
        Registry.byflags['group'] = OperFlag('group', etype=str)
        f = Field.from_dsl(r'int, group by foo')
        self.assertEqual(f.group, 'foo')
        f = Field.from_dsl(r'int')
        self.assertEqual(f.group, None)
        
        # Test append
        Registry.byflags['index'] = OperFlag('index', etype=str, store='append')
        f = Field.from_dsl(r'int, index by year')
        self.assertEqual(f.index, ['year'])
        f = Field.from_dsl(r'int, index by year, index by month')
        self.assertEqual(f.index, ['year', 'month'])


    # ==========================
    # Errors
    # ==========================

    def test_unsupported_modifier(self):
        with self.assertRaisesRegex(ValueError, 'unsupported type'):
            Field.from_dsl('list of unknown')
            
        with self.assertRaisesRegex(ValueError, 'unknown modifier'):
            Field.from_dsl('int, random_mod')

if __name__ == '__main__':
    unittest.main()
