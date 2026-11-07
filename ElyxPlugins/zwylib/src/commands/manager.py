import shlex
import inspect
from dataclasses import dataclass, field
from typing import List, Callable, Optional, Any, Union, Dict, Tuple, Type

from typing_extensions import get_origin, get_args

import markdown_utils
from base_plugin import HookResult, HookStrategy

from ..core.companion import _companion
from ..core.locales import L
from ..core.meta import __id__, _get_plugin_id_from_stack, DEFAULT_COMMAND_PREFIX, _ALLOWED_ARG_TYPES, _ALLOWED_ORIGIN
from ..core import state as _state
from ..ui.bulletin import _bulletin
from ..utils.async_tools import async_manager
from ..utils.cache import JsonCacheFile
from ..utils.logs import format_exc_from, format_exc_only, _logger, _cmd_logger
from ..utils.plugin import PluginUtils


class CannotCastError(Exception):
    pass


class WrongArgumentAmountError(Exception):
    pass


class MissingRequiredArguments(Exception):
    pass


class InvalidTypeError(Exception):
    pass


@dataclass
class _CommandTestUnit:
    input: str
    arg_specs: Tuple[inspect.Parameter, ...]
    expected_args: Optional[Tuple[Any, ...]]
    should_succeed: bool
    description: str
    expected_exception: Optional[Type[Exception]] = None


@dataclass
class _ArgSpec:
    name: str
    annotation: Any
    kind: inspect._ParameterKind
    default: Any = inspect.Parameter.empty
    is_optional: bool = False

    @classmethod
    def from_parameter(cls, param: inspect.Parameter) -> "_ArgSpec":
        annotation = param.annotation if param.annotation != inspect.Parameter.empty else Any
        is_optional = get_origin(annotation) in (Union, Optional) and type(None) in get_args(annotation)
        return cls(
            name=param.name,
            annotation=annotation,
            kind=param.kind,
            default=param.default,
            is_optional=is_optional
        )


@dataclass
class _Command:
    func: Callable
    name: str
    aliases: List[str] = field(default_factory=list)
    args: List[_ArgSpec] = field(default_factory=list)
    subcommands: Dict[str, "_Command"] = field(default_factory=dict)
    error_handler: Optional[Callable] = None

    def stub_subcommand(self, name: str):
        sub_cmd = _InternalCmdUtils.create_stub_command(name=name)
        _InternalCmdUtils.register_command(
            target=self.subcommands,
            command=sub_cmd,
            plugin_id=self.name,
            is_subcommand=True
        )
        return sub_cmd

    def subcommand(self, name: str, aliases: List[str] = None):
        def decorator(func: Callable[[], None]):
            sub_cmd = _InternalCmdUtils.create_command(func=func, name=name)
            if aliases:
                sub_cmd.aliases = aliases
            _InternalCmdUtils.register_command(
                target=self.subcommands,
                command=sub_cmd,
                plugin_id=self.name,
                is_subcommand=True
            )
            return sub_cmd
        return decorator

    def register_error_handler(self, func: Callable[[Any, int, Exception], Optional[HookResult]]):
        _cmd_logger.info(f"Registering error handler for {self.name} command...")
        signature = inspect.signature(func)
        if len(signature.parameters) != 3:
            raise MissingRequiredArguments("Error handler must have only 'param', 'account' and 'exception' arguments.")
        self.error_handler = func
        return func

    def __repr__(self):
        return f"{self.__class__.__name__}(name={self.name}, subs={list(self.subcommands.values())})"


class _InternalCmdUtils:
    @staticmethod
    def register_command(target: Dict[str, "_Command"], command: "_Command", plugin_id: str, is_subcommand=False):
        log_prefix = f"Command {command.name}:" if is_subcommand else f"Dispatcher {plugin_id}:"
        cmd_type = "Subcommand" if is_subcommand else "Command"
        pending_commands = _companion.module.pending_commands
        all_names = [command.name] + command.aliases

        for n in all_names:
            if not n:
                _cmd_logger.error(f"{log_prefix} {cmd_type} name/alias cannot be empty.")
                return
            if " " in n:
                _cmd_logger.error(f"{log_prefix} {cmd_type} name/alias ({n}) cannot contain spaces")
                return

        if command_manager.temporal and not is_subcommand:
            _cmd_logger.debug(f"{log_prefix} {cmd_type} manager is not initialized, saving command to pending list.")
            if plugin_id not in pending_commands:
                pending_commands[plugin_id] = []

            existing_names = []
            for cmd in pending_commands[plugin_id]:
                existing_names.extend([cmd.name] + cmd.aliases)

            for n in all_names:
                if n in existing_names:
                    _cmd_logger.error(f"{log_prefix} {cmd_type} name/alias '{n}' is already in pending list.")
                    return

            pending_commands[plugin_id].append(command)
            return

        for n in all_names:
            if n in target:
                _cmd_logger.error(f"{log_prefix} {cmd_type} name/alias '{n}' is already registered.")
                return

        for n in all_names:
            target[n] = command
            _cmd_logger.debug(f"{log_prefix} Registered {cmd_type.lower()} key: {n}.")

    @staticmethod
    def _is_allowed_type(arg_type):
        """
        Check if the argument type is supported, including Optional and Union types with NoneType.

        :param arg_type: The type to check.
        :returns: True if the type is supported, False otherwise.
        """
        if arg_type in _ALLOWED_ARG_TYPES:
            return True

        if arg_type is type(None):
            return True

        origin = get_origin(arg_type)
        if origin in _ALLOWED_ORIGIN:
            return all(_InternalCmdUtils._is_allowed_type(t) for t in get_args(arg_type))
        return False

    @staticmethod
    def _cast_arg(arg: str, target_type: type):
        """
        Just casts a string to the target type.
        :raises CannotCastError: If the string cannot be cast to the target type.
        """

        if target_type == str or target_type == Any:
            return arg
        elif target_type == int:
            return int(arg)
        elif target_type == float:
            return float(arg)
        elif target_type == bool:
            if arg.lower() in ("true", "1", "yes", "on"):
                return True
            elif arg.lower() in ("false", "0", "no", "off"):
                return False
            else:
                raise CannotCastError(f"Cannot cast '{arg}' to bool")
        else:
            raise CannotCastError(f"Unsupported target type: {target_type}")

    @staticmethod
    def _smart_cast(arg: str, annotation):
        """
        Casts the string to the type specified in the annotation, including Optional and Union.
        :raises CannotCastError: If the string cannot be cast to any of the types in Union or the annotation is not supported.
        """

        origin = get_origin(annotation)
        args = get_args(annotation)

        if annotation in _ALLOWED_ARG_TYPES:
            try:
                return _InternalCmdUtils._cast_arg(arg, annotation)
            except Exception:
                raise CannotCastError(f"Could not cast '{arg}' to {annotation}")
        elif origin is Union:
            for possible_type in args:
                if possible_type == type(None):
                    continue
                try:
                    return _InternalCmdUtils._cast_arg(arg, possible_type)
                except Exception:
                    continue
            raise CannotCastError(f"Could not cast '{arg}' to any of: {args}")
        raise CannotCastError(f"Unsupported annotation: {annotation}")

    @staticmethod
    def parse_args(raw_args: List[str], command_args: List[_ArgSpec]) -> Tuple[Any, ...]:
        """
        Parses a list of raw argument strings into typed arguments based on the command's argument specifications.

        :param raw_args: List of raw argument strings.
        :param command_args: List of ArgSpec describing the expected arguments.
        :returns: Tuple of parsed arguments.
        :raises WrongArgumentAmountError: If the number of provided arguments is incorrect.
        :raises CannotCastError: If an argument cannot be cast to the expected type.
        """

        out: List[Any] = []
        required_arg_count = sum(
            1 for arg in command_args
            if not arg.is_optional and arg.default == inspect.Parameter.empty and arg.kind != inspect.Parameter.VAR_POSITIONAL
        )
        is_variadic = any(arg.kind == inspect.Parameter.VAR_POSITIONAL for arg in command_args)

        if not is_variadic and len(raw_args) > len(command_args):
            raise WrongArgumentAmountError(f"Expected at most {len(command_args)} arguments, got {len(raw_args)}.")
        if len(raw_args) < required_arg_count:
            raise WrongArgumentAmountError(f"Expected at least {required_arg_count} arguments, got {len(raw_args)}.")

        for i, cmd_arg in enumerate(command_args):
            if cmd_arg.kind == inspect.Parameter.VAR_POSITIONAL:
                variadic_args = raw_args[i:] if i < len(raw_args) else []
                if not variadic_args:
                    _cmd_logger.error(f"No variadic arguments provided for {cmd_arg.name}, returning empty tuple.")
                    break

                for arg in variadic_args:
                    _cmd_logger.debug(f"Processing variadic argument: {arg}, expected type: {cmd_arg.annotation}.")
                    parsed_arg = _InternalCmdUtils._smart_cast(arg, cmd_arg.annotation)
                    _cmd_logger.debug(f"Variadic argument parsed successfully: {parsed_arg}.")
                    out.append(parsed_arg)
                break
            elif i < len(raw_args):
                _cmd_logger.debug(f"Processing argument {i}: {raw_args[i]}, expected type: {cmd_arg.annotation}.")
                parsed_arg = _InternalCmdUtils._smart_cast(raw_args[i], cmd_arg.annotation)
                _cmd_logger.debug(f"Argument {i} parsed successfully: {parsed_arg}.")
                out.append(parsed_arg)
            elif cmd_arg.default != inspect.Parameter.empty:
                _cmd_logger.debug(f"Argument {i} missing, using default value: {cmd_arg.default}.")
                out.append(cmd_arg.default)
            elif cmd_arg.is_optional:
                _cmd_logger.debug(f"Argument {i} missing, using None for Optional type: {cmd_arg.annotation}.")
                out.append(None)
            else:
                _cmd_logger.debug(f"Argument {i} missing for non-Optional, non-default type: {cmd_arg.annotation}.")
                raise WrongArgumentAmountError(f"Expected argument {i} of type {cmd_arg.annotation}, but none provided.")
        return tuple(out)

    @staticmethod
    def create_command(func: Callable, name: str) -> _Command:
        signature = inspect.signature(func)
        parameters = list(signature.parameters.values())
        return_type = signature.return_annotation

        if len(parameters) < 2:
            raise MissingRequiredArguments(
                "Command must have 'param' variable as first argument and 'account' variable as second argument"
            )

        args = [_ArgSpec.from_parameter(param) for param in parameters]

        for index, arg in enumerate(args):
            if arg.kind == inspect.Parameter.VAR_POSITIONAL:
                origin_type = get_origin(arg.annotation) or arg.annotation
                if not _InternalCmdUtils._is_allowed_type(origin_type):
                    raise InvalidTypeError(
                        f"Variadic argument (index: {index}) type must be one of "
                        f"{*_ALLOWED_ARG_TYPES, *_ALLOWED_ORIGIN}, got {arg.annotation}"
                    )
            elif not _InternalCmdUtils._is_allowed_type(arg.annotation):
                raise InvalidTypeError(
                    f"Command argument (index: {index}) signature must be one of "
                    f"{*_ALLOWED_ARG_TYPES, *_ALLOWED_ORIGIN}, got {arg.annotation}"
                )

        is_async = inspect.iscoroutinefunction(func)
        if is_async:
            if return_type not in [inspect.Parameter.empty, None]:
                raise InvalidTypeError(f"Async command function must return NoneType, got {return_type}")
        elif return_type != HookResult:
            return_type_name = "NoneType" if return_type == inspect.Parameter.empty else return_type
            raise InvalidTypeError(f"Command function must return {HookResult} object, got {return_type_name}")

        return _Command(func=func, name=name, args=args)

    @staticmethod
    def create_stub_command(name: str) -> _Command:
        return _Command(func=_InternalCmdUtils.stub_command_callback, name=name, args=_stub_command_args)

    @staticmethod
    def stub_command_callback(_, __, *args) -> HookResult:
        text = L.likely_cmd_name_misspelling if args else L.stub_command_message
        _bulletin.show_info(text)
        return HookResult(strategy=HookStrategy.CANCEL)

    @staticmethod
    def show_command_exception(cmd: _Command, exc: Exception, from_err_handler=False):
        message = f"Uncaught exception occurred while the execution of '{cmd.name}' command"
        if from_err_handler:
            message += "'s ERROR HANDLER"
        message += ":\n" + format_exc_from(exc)

        _cmd_logger.error(message)
        _bulletin.show_error_with_copy(
            L.command_execution_error(cmd_name=cmd.name),
            message
        )


class Dispatcher:
    def __init__(self, plugin_id: str, prefix: str, commands_priority: int):
        self.plugin_id = plugin_id
        self.prefix = prefix
        self.commands_priority = commands_priority
        self.listeners: Dict[str, _Command] = {}  # command_name -> Command

    @staticmethod
    def validate_prefix(prefix: str) -> bool:
        return prefix and " " not in prefix

    def set_prefix(self, prefix: str):
        if not self.validate_prefix(prefix):
            _cmd_logger.error(f"{self.plugin_id} dp: Prefix validation failed (got '{prefix}').")
            return

        _cmd_logger.info(f"{self.plugin_id} dp: Set '{prefix}' prefix.")
        self.prefix = prefix
        command_manager.update_dispatcher_prefix_cache(self.plugin_id)

    def register_command(self, name: str, aliases: List[str] = None):
        def decorator(func: Callable[[], None]):
            command = _InternalCmdUtils.create_command(func=func, name=name)
            if aliases:
                command.aliases = aliases
            _InternalCmdUtils.register_command(
                target=self.listeners,
                command=command,
                plugin_id=self.plugin_id,
            )
            return command
        return decorator

    def register_stub_command(self, name: str):
        command = _InternalCmdUtils.create_stub_command(name=name)
        _InternalCmdUtils.register_command(
            target=self.listeners,
            command=command,
            plugin_id=self.plugin_id,
        )
        return command

    def unregister_command(self, name: str):
        _cmd_logger.info(f"{self.plugin_id} dp: Unregistered command '{name}'.")
        self.listeners.pop(name, None)


class _CommandManager:
    def __init__(self):
        self._dispatchers: Dict[str, Dispatcher] = {}  # plugin_id -> Dispatcher
        self._prefixes_cache = JsonCacheFile("zwylib__cmds_prefixes", {})
        self.temporal = True

    def mark_as_not_temporal(self):
        self.temporal = False

    def get_dispatcher(self, plugin_id: str | None = None, prefix: str = "default", commands_priority=-1) -> Dispatcher:
        if plugin_id is None:
            plugin_id = _get_plugin_id_from_stack(__id__)

        if not prefix or prefix == "default":
            prefix = DEFAULT_COMMAND_PREFIX

        if plugin_id in self._prefixes_cache.content:
            prefix = self._prefixes_cache.content[plugin_id]

        if plugin_id not in self._dispatchers:
            self._dispatchers[plugin_id] = Dispatcher(
                plugin_id=plugin_id,
                prefix=prefix,
                commands_priority=commands_priority,
            )
            _cmd_logger.debug(f"Dispatcher for '{plugin_id}' was created.")
            self.sort_dispatchers()

        _cmd_logger.debug(f"Got dispatcher for '{plugin_id}' with prefix '{prefix}'.")
        return self._dispatchers[plugin_id]

    def remove_dispatcher(self, plugin_id: str | None):
        if plugin_id is None:
            plugin_id = _get_plugin_id_from_stack(__id__)
        self._dispatchers.pop(plugin_id, None)
        _cmd_logger.debug(f"Removed dispatcher for '{plugin_id}'.")

    def sort_dispatchers(self):
        """Sorts dispatchers by their commands priority. Dispatchers with higher priority will be processed first."""
        self._dispatchers = dict(sorted(self._dispatchers.items(), key=lambda i: i[1].commands_priority, reverse=True))
        _cmd_logger.debug("Dispatchers sorted by priority.")

    def load_pending_commands(self):
        pending_commands: Dict[str, List[_Command]] = _companion.module.pending_commands
        _cmd_logger.debug("Loading pending commands:", pending_commands)

        for plugin_id, commands in pending_commands.items():
            if not commands:
                continue

            if not PluginUtils.is_plugin_loaded_or_loading(plugin_id):
                _cmd_logger.info(f"Pending commands of '{plugin_id}' weren't registered: plugin is missing or it's off.")
                continue

            dispatcher = self.get_dispatcher(plugin_id)
            for command in commands:
                dispatcher.listeners[command.name] = command

            _cmd_logger.info(f"Registered all pending commands for '{plugin_id}'.")
        pending_commands.clear()

    def save_commands_as_pending(self):
        _cmd_logger.info("Saving all commands to pending list...")

        pending_commands: Dict[str, List[_Command]] = _companion.module.pending_commands
        for plugin_id, dp in self._dispatchers.items():
            pending_commands[plugin_id] = list(dp.listeners.values())

    def unregister_all(self):
        _cmd_logger.info("Unregistering all dispatchers...")
        self._dispatchers.clear()

    def update_dispatcher_prefix_cache(self, plugin_id: str):
        _cmd_logger.info(f"Updating prefix cache for '{plugin_id}'...")
        dp = self.get_dispatcher(plugin_id)

        if dp.prefix == DEFAULT_COMMAND_PREFIX:
            _cmd_logger.warning(f"'{plugin_id}' prefix is the same as the default. Removing from cache.")
            self._prefixes_cache.content.pop(plugin_id, None)
            self._prefixes_cache.write()
            return

        self._prefixes_cache.content[plugin_id] = dp.prefix
        self._prefixes_cache.write()

    def handle_send_message_hook(self, params, account: int) -> HookResult:
        original_text = getattr(params, "message")
        if not original_text:
            return HookResult()

        for plugin_id, dp in self._dispatchers.items():
            _cmd_logger.debug(f"Searching for commands in {plugin_id} dispatcher...")

            if not original_text.startswith(dp.prefix):
                continue

            msg_text = original_text[len(dp.prefix):]
            msg_text = msg_text.lstrip()
            args: List[Any] = shlex.split(msg_text.strip())

            if not args:
                continue

            cmd = dp.listeners.get(args[0])
            if not cmd:
                continue

            _cmd_logger.debug(f"Found command: {cmd.name}. Looking for subcommands...")

            args = args[1:]
            while args and args[0] in cmd.subcommands:
                cmd = cmd.subcommands[args[0]]
                args = args[1:]
                _cmd_logger.debug(f"Found subcommand: {cmd.name}. Continuing to search...")

            args.insert(0, params)
            args.insert(1, account)

            try:
                _cmd_logger.debug("Preparing arguments...")
                parsed_args = _InternalCmdUtils.parse_args(args, cmd.args)

                if inspect.iscoroutinefunction(cmd.func):
                    _cmd_logger.debug(f"Executing async command with args {parsed_args}...")
                    async_manager.run_task(cmd.func(*parsed_args))
                    return HookResult(strategy=HookStrategy.CANCEL)
                else:
                    _cmd_logger.debug(f"Executing command with args {parsed_args}...")
                    return cmd.func(*parsed_args)
            except Exception as e:
                if not cmd.error_handler:
                    _InternalCmdUtils.show_command_exception(cmd, e)
                    return HookResult(strategy=HookStrategy.CANCEL)

                _cmd_logger.debug(
                    f"An exception has been caught in '{cmd.name}' command execution.\n"
                    "Running error handler..."
                )

                try:
                    if inspect.iscoroutinefunction(cmd.error_handler):
                        async_manager.run_task(cmd.error_handler(params, account, e))
                        return HookResult(strategy=HookStrategy.CANCEL)
                    else:
                        return cmd.error_handler(params, account, e)
                except Exception as e:
                    # really, bud?
                    _InternalCmdUtils.show_command_exception(cmd, e, from_err_handler=True)
                    return HookResult(strategy=HookStrategy.CANCEL)
        return HookResult()


def _register_zwylib_commands():
    _logger.debug("Registering ZwyLib commands...")
    dp = command_manager.get_dispatcher(__id__)

    zwylib = dp.register_stub_command("zwylib")

    @zwylib.subcommand("cmds")
    def zwylib_cmds(params, _) -> HookResult:
        def collect_commands(command: _Command, prefix=""):
            full_name = (prefix + " " + command.name).strip()
            names = [full_name]
            for sub in command.subcommands.values():
                names.extend(collect_commands(sub, prefix=full_name))
            return names

        lines = []
        # noinspection PyProtectedMember
        for dispatcher in command_manager._dispatchers.values():
            lines.append(f"\n- {dispatcher.plugin_id}:")
            for cmd in dispatcher.listeners.values():
                for name in collect_commands(cmd):
                    lines.append(f"\t- {name}")

        text = "\n".join(lines)
        parsed = markdown_utils.parse_markdown(text)

        params.message = parsed.text
        for ent in parsed.entities:
            params.entities.add(ent.to_tlrpc_object())

        return HookResult(strategy=HookStrategy.MODIFY_FINAL, params=params)

    @zwylib_cmds.subcommand("test")
    def test_command_system(params, _) -> HookResult:
        test_cases = [
            _CommandTestUnit(
                input="",
                arg_specs=(),
                expected_args=(),
                should_succeed=True,
                description="No arguments"
            ),
            _CommandTestUnit(
                input="hi",
                arg_specs=(
                    inspect.Parameter(name="arg1", kind=inspect.Parameter.POSITIONAL_OR_KEYWORD, annotation=inspect.Parameter.empty),
                ),
                expected_args=("hi",),
                should_succeed=True,
                description="Single mandatory not annotated argument"
            ),
            _CommandTestUnit(
                input="hi",
                arg_specs=(
                    inspect.Parameter(name="arg1", kind=inspect.Parameter.POSITIONAL_OR_KEYWORD, annotation=Any),
                ),
                expected_args=("hi",),
                should_succeed=True,
                description="Single mandatory Any argument"
            ),
            _CommandTestUnit(
                input="hi",
                arg_specs=(
                    inspect.Parameter(name="arg1", kind=inspect.Parameter.POSITIONAL_OR_KEYWORD, annotation=str),
                ),
                expected_args=("hi",),
                should_succeed=True,
                description="Single mandatory str argument"
            ),
            _CommandTestUnit(
                input="42.5",
                arg_specs=(
                    inspect.Parameter(name="arg1", kind=inspect.Parameter.POSITIONAL_OR_KEYWORD, annotation=float),
                ),
                expected_args=(42.5,),
                should_succeed=True,
                description="Float argument"
            ),
            _CommandTestUnit(
                input="true",
                arg_specs=(
                    inspect.Parameter(name="arg1", kind=inspect.Parameter.POSITIONAL_OR_KEYWORD, annotation=bool),
                ),
                expected_args=(True,),
                should_succeed=True,
                description="Single mandatory bool argument"
            ),
            _CommandTestUnit(
                input="",
                arg_specs=(
                    inspect.Parameter(name="arg1", kind=inspect.Parameter.POSITIONAL_OR_KEYWORD, annotation=int),
                ),
                expected_args=None,
                should_succeed=False,
                description="Missing mandatory int argument",
                expected_exception=WrongArgumentAmountError
            ),
            _CommandTestUnit(
                input="",
                arg_specs=(
                    inspect.Parameter(name="arg1", kind=inspect.Parameter.POSITIONAL_OR_KEYWORD, annotation=str, default="default"),
                ),
                expected_args=("default",),
                should_succeed=True,
                description="Argument with default value"
            ),
            _CommandTestUnit(
                input="42 default 1",
                arg_specs=(
                    inspect.Parameter(name="arg1", kind=inspect.Parameter.POSITIONAL_OR_KEYWORD, annotation=int),
                    inspect.Parameter(name="arg2", kind=inspect.Parameter.POSITIONAL_OR_KEYWORD, annotation=str),
                    inspect.Parameter(name="arg3", kind=inspect.Parameter.POSITIONAL_OR_KEYWORD, annotation=int),
                ),
                expected_args=(42, "default", 1),
                should_succeed=True,
                description="Multiple arguments with int and str"
            ),
            _CommandTestUnit(
                input="hi",
                arg_specs=(
                    inspect.Parameter(name="arg1", kind=inspect.Parameter.POSITIONAL_OR_KEYWORD, annotation=Optional[str]),
                ),
                expected_args=("hi",),
                should_succeed=True,
                description="Optional str argument with valid input"
            ),
            _CommandTestUnit(
                input="",
                arg_specs=(
                    inspect.Parameter(name="arg1", kind=inspect.Parameter.POSITIONAL_OR_KEYWORD, annotation=Optional[str]),
                ),
                expected_args=(None,),
                should_succeed=True,
                description="Optional str argument with no input"
            ),
            _CommandTestUnit(
                input="hi",
                arg_specs=(
                    inspect.Parameter(name="arg1", kind=inspect.Parameter.POSITIONAL_OR_KEYWORD, annotation=Optional[int]),
                ),
                expected_args=(None,),
                should_succeed=False,
                description="Optional int argument with invalid input",
                expected_exception=CannotCastError
            ),
            _CommandTestUnit(
                input="1 2 3",
                arg_specs=(
                    inspect.Parameter(name="args", kind=inspect.Parameter.VAR_POSITIONAL, annotation=int),
                ),
                expected_args=(1, 2, 3),
                should_succeed=True,
                description="Variadic int arguments"
            ),
            _CommandTestUnit(
                input="1 two 3",
                arg_specs=(
                    inspect.Parameter(name="args", kind=inspect.Parameter.VAR_POSITIONAL, annotation=int),
                ),
                expected_args=(None, None, None),
                should_succeed=False,
                description="Variadic int arguments with invalid input",
                expected_exception=CannotCastError
            ),
            _CommandTestUnit(
                input="",
                arg_specs=(
                    inspect.Parameter(name="args", kind=inspect.Parameter.VAR_POSITIONAL, annotation=str),
                ),
                expected_args=(),
                should_succeed=True,
                description="Variadic str arguments with no input"
            ),
            _CommandTestUnit(
                input="",
                arg_specs=(
                    inspect.Parameter(name="args", kind=inspect.Parameter.VAR_POSITIONAL, annotation=inspect.Parameter.empty),
                ),
                expected_args=(),
                should_succeed=True,
                description="Variadic Any arguments with no input"
            ),
        ]

        results = []
        for i, case in enumerate(test_cases):
            test_number = i + 1

            try:
                cmd_parameters = [_ArgSpec.from_parameter(param) for param in case.arg_specs]
                args = shlex.split(case.input) if case.input.strip() else []
                parsed_args = _InternalCmdUtils.parse_args(args, cmd_parameters)

                if case.should_succeed:
                    if parsed_args == case.expected_args:
                        results.append(f"Test {test_number} ({case.description}): Passed")
                    else:
                        results.append(f"Test {test_number} ({case.description}): Failed - Expected args {case.expected_args}, got {parsed_args}\nInput: {case.input}")
                else:
                    results.append(f"Test {test_number} ({case.description}): Failed - Expected to fail, but succeeded with args {parsed_args}\nInput: {case.input}")
            except Exception as e:
                if case.should_succeed:
                    results.append(f"Test {test_number} ({case.description}): Failed with {format_exc_only(e)}\nInput: {case.input}")
                elif case.expected_exception and isinstance(e, case.expected_exception):
                    results.append(f"Test {test_number} ({case.description}): Passed")
                else:
                    results.append(f"Test {test_number} ({case.description}): Failed with unexpected error {format_exc_only(e)}\nInput: {case.input}")

        text = "Command system tests:\n\n" + "\n\n".join(results)
        parsed = markdown_utils.parse_markdown(text)

        params.message = parsed.text
        for ent in parsed.entities:
            params.entities.add(ent.to_tlrpc_object())

        return HookResult(strategy=HookStrategy.MODIFY_FINAL, params=params)

    zwylib_au = zwylib.stub_subcommand("au")

    @zwylib_au.subcommand("list")
    def zwylib_au_list(params, _) -> HookResult:
        text = "ZwyLib autoupdater tasks:\n" + "\n".join([f"\t- [{i.plugin_id}](https://t.me/c/{i.channel_id}/{i.message_id})" for i in _state.autoupdater.tasks])
        new_msg = markdown_utils.parse_markdown(text)

        params.message = new_msg.text
        for i in new_msg.entities:
            params.entities.add(i.to_tlrpc_object())

        return HookResult(strategy=HookStrategy.MODIFY_FINAL, params=params)


_stub_command_signature = inspect.signature(_InternalCmdUtils.stub_command_callback)
_stub_command_args = [_ArgSpec.from_parameter(param) for param in _stub_command_signature.parameters.values()]

command_manager = _CommandManager()
