# -*- coding: utf-8 -*-
import sys
import unittest

try:
    from StringIO import StringIO
except ImportError:
    from io import StringIO
from manager import Arg, Command, Error, Manager


manager = Manager()


class capture(object):
    """Captures the std output.
    """
    def __enter__(self):
        self.backup = sys.stdout
        sys.stdout = StringIO()
        return sys.stdout

    def __exit__(self, type, value, traceback):
        sys.stdout = self.backup


class ClassBased(manager.Command):
    def run(self, name, capitalyze=False):
        if capitalyze:
            return name.upper()
        return name


@manager.command
def simple_command(name, capitalyze=False):
    if capitalyze:
        return name.upper()
    return name


@manager.command(namespace='my_namespace')
def namespaced(name):
    """namespaced command"""
    return name


@manager.command
def raises():
    raise Error('No way dude!')


class ArgTest(unittest.TestCase):
    def test_kwargs_required(self):
        kwargs = Arg('name', required=True).kwargs
        self.assertNotIn('required', kwargs)

    def test_kwargs_bool_false(self):
        kwargs = Arg('name', default=False, type=bool).kwargs
        self.assertNotIn('type', kwargs)
        self.assertEqual(kwargs['action'], 'store_true')

    def test_parser_name_is_name_if_required(self):
        arg = Arg('name', required=True)

        self.assertEqual(arg.parser_name, arg.name)

    def test_parser_name_is_prefixed_with_slashes_if_optional(self):
        arg = Arg('name', required=False)

        self.assertEqual(arg.parser_name, '--' + arg.name)


class CommandTest(unittest.TestCase):
    def test_registration(self):
        class MyCommand(manager.Command):
            pass

        self.assertIn('my_command', manager.commands)
        del manager.commands['my_command']

    def test_inspect_class_based(self):
        args = manager.commands['class_based'].args
        self.assertEqual(len(args), 2)
        self.assertEqual(args[0].name, 'name')
        self.assertTrue(args[0].required)
        self.assertTrue(args[0].default is None)
        self.assertEqual(args[1].name, 'capitalyze')
        self.assertFalse(args[1].required)
        self.assertEqual(args[1].default, False)

    def test_inspect_function_based(self):
        args = manager.commands['simple_command'].args
        self.assertEqual(len(args), 2)
        self.assertEqual(args[0].name, 'name')
        self.assertTrue(args[0].required)
        self.assertTrue(args[0].default is None)
        self.assertEqual(args[1].name, 'capitalyze')
        self.assertFalse(args[1].required)
        self.assertEqual(args[1].default, False)

    def test_path_root(self):
        self.assertEqual(manager.commands['simple_command'].path,
            'simple_command')

    def test_path_namespace(self):
        self.assertEqual(manager.commands['my_namespace.namespaced'].path,
            'my_namespace.namespaced')

    def test_had_argument(self):
        command = Command(run=lambda new_argument: new_argument)
        self.assertEqual(len(command.args), 1)
        arg = Arg('new_argument', help='argument help')
        command.add_argument(arg)
        self.assertEqual(len(command.args), 1)
        self.assertEqual(command.args[0].help,
            'argument help')

    def test_puts_error(self):
        with capture() as c:
            manager.commands['raises'].parse(list())

        self.assertEqual(c.getvalue(), 'No way dude!\n')

    def test_puts_none(self):
        with capture() as c:
            Command().puts(None)

        self.assertEqual(c.getvalue(), '')

    def test_puts_empty(self):
        with capture() as c:
            Command().puts('')

        self.assertEqual(c.getvalue(), '\n')


class ManagerTest(unittest.TestCase):
    def test_command_decorator(self):
        self.assertIn('simple_command', manager.commands)
        self.assertEqual(len(manager.commands['simple_command'].args), 2)

    def test_command_decorator_kwargs(self):
        self.assertIn('my_namespace.namespaced', manager.commands)
        self.assertEqual(len(manager.commands['my_namespace.namespaced'].args),
            1)

    def test_command_decorator_doc(self):
        self.assertEqual(
            manager.commands['my_namespace.namespaced'].description,
            'namespaced command'
        )

    def test_arg_decorator(self):
        @manager.arg('first_arg', help='first help')
        @manager.arg('second_arg', help='second help')
        @manager.command
        def new_command(first_arg, second_arg):
            return first_arg

        command = manager.commands['new_command']
        self.assertEqual(command.args[0].help, 'first help')
        self.assertEqual(command.args[1].help, 'second help')

    def test_merge(self):
        new_manager = Manager()
        new_manager.add_command(Command(name='new_command'))
        manager.merge(new_manager)
        self.assertIn('new_command', manager.commands)

    def test_merge_namespace(self):
        new_manager = Manager()
        new_manager.add_command(Command(name='new_command'))
        manager.merge(new_manager, namespace='new_namespace')
        self.assertIn('new_namespace.new_command', manager.commands)

    def test_parse_env_simple(self):
        new_manager = Manager()
        env = "key=value"
        self.assertEqual(manager.parse_env(env), dict(key='value'))

    def test_parse_env_quote(self):
        new_manager = Manager()
        env = "key='value'"
        self.assertEqual(manager.parse_env(env), dict(key='value'))

    def test_parse_env_double_quote(self):
        new_manager = Manager()
        env = 'key="value"'
        self.assertEqual(manager.parse_env(env), dict(key='value'))

    def test_parse_env_multiline(self):
        new_manager = Manager()
        env = """key="value"
another_key=another value"""
        self.assertEqual(manager.parse_env(env), dict(key='value',
            another_key='another value'))


if __name__ == '__main__':
    unittest.main()
