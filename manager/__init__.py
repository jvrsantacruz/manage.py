# -*- coding: utf-8 -*-
import argparse
import sys
import re
import os
import inspect

from clint import args
from clint.textui import colored, puts, min_width, indent


class Error(Exception):
    pass


class InspectedFunction(object):
    def __init__(self, function):
        self.function = function
        self.arguments, self.defaults = self._inspect(function)

    def _inspect(self, function):
        arguments, _, _, defaults = inspect.getargspec(function)
        return arguments, defaults

    @property
    def is_method(self):
        function = self.function
        return hasattr(function, 'im_self') or hasattr(function, '__self__')

    @property
    def argument_names(self):
        start = 1 if self.is_method else 0   # omit self
        return self.arguments[start:]

    @property
    def args(self):
        end = None if not self.defaults else -len(self.defaults)  # omit kw
        return self.argument_names[:end]

    @property
    def kwargs(self):
        if self.defaults is None:
            return {}
        return dict(zip(reversed(self.arguments), reversed(self.defaults)))


def camelcase_to_underscore(text, word_expression=re.compile('(.)([A-Z]{1})')):
    return word_expression.sub(r'\1_\2', text).lower()


class Command(object):
    name = None
    namespace = None
    description = 'no description'
    run = None

    def __init__(self, **kwargs):
        for key in kwargs:
            if hasattr(self, key):
                setattr(self, key, kwargs[key])
            else:
                raise Exception('Invalid keyword argument `%s`' % key)

        if self.name is None:
            self.name = camelcase_to_underscore(self.__class__.__name__)

        self.args = []
        self.arg_names = self.collect_arguments()

    def __call__(self, *args, **kwargs):
        return self.run(*args, **kwargs)

    def _create_arguments(self, args, kwargs):
        for name in args:
            default = kwargs.get(name)
            required = not name in kwargs
            type_ = type(default) if name in kwargs else None

            yield Arg(name, default=default, type=type_, required=required)

    def collect_arguments(self):
        inspected = InspectedFunction(self.run)

        arguments = self._create_arguments(
            inspected.argument_names, inspected.kwargs)

        for arg in arguments:
            self.register_argument(arg, inspected.argument_names)

        return inspected.argument_names

    def register_argument(self, arg, arg_names):
        dest = arg.dest if hasattr(arg, 'dest') else arg.name
        if dest not in arg_names:
            raise Exception('Invalid arg %s' % arg.name)
        if self.has_argument(arg.name):
            position = arg_names.index(dest)
            self.args[position] = arg
        else:
            self.args.append(arg)

    def add_argument(self, arg):
        self.register_argument(arg, self.arg_names)

    def has_argument(self, name):
        return name in [arg.name for arg in self.args]

    def run(self, *args, **kwargs):
        raise NotImplementedError

    def parse(self, input_args):
        parsed_args = self.parser.parse_args(input_args)

        args, kwargs = [], {}
        for arg, arg_name in zip(self.args, self.arg_names):
            if arg.required:
                args.append(getattr(parsed_args, arg_name))
            elif hasattr(parsed_args, arg_name):
                kwargs[arg_name] = getattr(parsed_args, arg_name)

        return args, kwargs

    def execute(self, arguments):
        args, kwargs = self.parse(arguments)

        try:
            result = self.run(*args, **kwargs)
        except Error as result:
            pass
        finally:
            return self.puts(result)

    @property
    def parser(self):
        parser = argparse.ArgumentParser(description=self.description)
        for arg in self.args:
            parser.add_argument(arg.parser_name, **arg.kwargs)
        return parser

    @property
    def path(self):
        return self.name if self.namespace is None else '%s.%s' % \
            (self.namespace, self.name)

    def puts(self, r):
        stdout = sys.stdout.write
        type_ = type(r)
        if type_ == list:
            [puts(i, stream=stdout) for i in r]
        elif type_ == dict:
            for key in r:
                puts(min_width(colored.blue(key), 25) + r[key])
        elif type_ == Error:
            puts(colored.red(str(r)), stream=stdout)
        elif r is not None:
            puts(str(r), stream=stdout)


class Manager(object):
    def __init__(self):
        self.commands = {}

    @property
    def Command(self):
        manager = self

        class BoundMeta(type):
            def __new__(meta, name, bases, dict_):
                new = type.__new__(meta, name, bases, dict_)
                if name != 'BoundCommand':
                    manager.add_command(new())

                return new

        return BoundMeta('BoundCommand', (Command, ), {})

    def add_command(self, command):
        self.commands[command.path] = command

    def arg(self, name, **kwargs):
        def wrapper(command):
            def wrapped(**kwargs):
                command.add_argument(Arg(name, **kwargs))
                return command
            return wrapped(**kwargs)

        return wrapper

    def merge(self, manager, namespace=None):
        for command_name in manager.commands:
            command = manager.commands[command_name]
            if namespace is not None:
                command.namespace = namespace
            self.add_command(command)

    def command(self, *args, **kwargs):
        def register(fn):
            def wrapped(**kwargs):
                if not 'name' in kwargs:
                    kwargs['name'] = fn.__name__
                if not 'description' in kwargs and fn.__doc__:
                    kwargs['description'] = fn.__doc__
                command = self.Command(run=fn, **kwargs)
                self.add_command(command)
                return command
            return wrapped(**kwargs)

        if len(args) == 1 and callable(args[0]):
            fn = args[0]
            return register(fn)
        else:
            return register

    def update_env(self):
        path = os.path.join(os.getcwd(), '.env')
        if os.path.isfile(path):
            env = self.parse_env(open(path).read())
            for key in env:
                os.environ[key] = env[key]

    def parse_env(self, content):
        def strip_quotes(string):
            for quote in "'", '"':
                if string.startswith(quote) and string.endswith(quote):
                    return string.strip(quote)
            return string

        regexp = re.compile('^([A-Za-z_0-9]+)=(.*)$', re.MULTILINE)
        founds = re.findall(regexp, content)
        return {key: strip_quotes(value) for key, value in founds}

    @property
    def parser(self):
        parser = argparse.ArgumentParser(
            usage='%(prog)s [<namespace>.]<command> [<args>]')
        parser.add_argument('command', help='the command to run')
        return parser

    def usage(self):
        def format_line(command, w):
            return "%s%s" % (min_width(command.name, w),
                command.description)

        self.parser.print_help()
        if len(self.commands) > 0:
            puts('\navailable commands:')
            with indent(2):
                namespace = None
                for command_path in sorted(self.commands,
                        key=lambda c: '%s%s' % (c.count('.'), c)):
                    command = self.commands[command_path]
                    if command.namespace is not None:
                        if command.namespace != namespace:
                            puts(colored.red('\n[%s]' % command.namespace))
                        with indent(2):
                            puts(format_line(command, 23))
                    else:
                        puts(format_line(command, 25))
                    namespace = command.namespace

    def main(self):
        if len(args) == 0 or args[0] in ('-h', '--help'):
            return self.usage()
        command = args.get(0)
        try:
            command = self.commands[command]
        except KeyError:
            puts(colored.red('Invalid command `%s`\n' % command))
            return self.usage()
        self.update_env()
        command.execute(args.all[1:])


class positional(object):
    def __init__(self, value):
        self.value = value


class Arg(object):
    defaults = {
        'help': 'no description',
        'required': False,
        'type': None,
    }

    def __init__(self, name, **kwargs):
        self.name = name
        self._kwargs = dict(self.defaults)
        self._kwargs.update(kwargs)

        for k, v in self._kwargs.items():
            setattr(self, k, v)

    @property
    def parser_name(self):
        return self.name if self.positional else '--%s' % self.name

    @property
    def positional(self):
        default = getattr(self, 'default', None)
        return self.required or isinstance(default, positional)

    def unwrap_default(self, default):
        if isinstance(default, positional):
            return default.value
        return default

    @property
    def kwargs(self):
        dict_ = self._kwargs.copy()
        if 'required' in dict_ and self.positional:
            del dict_['required']

        if 'default' in dict_:
            dict_['default'] = self.unwrap_default(self.default)

        if not self.required and self.positional:
            dict_['nargs'] = '?'

        if self.type == bool and self.default is False:
            dict_['action'] = 'store_true'
            del dict_['type']

        return dict_
