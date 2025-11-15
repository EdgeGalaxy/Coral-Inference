from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from importlib import import_module
from typing import Dict, Iterable, Optional

import uvicorn
from coral_inference.config import RuntimeDescriptor
from coral_inference.runtime import RuntimeConfig, init as runtime_init
from coral_inference.runtime import plugins as runtime_plugins


def main(argv: Optional[Iterable[str]] = None) -> int:
    parser = _create_parser()
    args = parser.parse_args(argv)
    try:
        return _dispatch(args)
    except (FileNotFoundError, ValueError, RuntimeError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


def _create_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="coral-runtime", description="Coral runtime configuration utilities"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    config_parser = subparsers.add_parser("config", help="Configuration helpers")
    config_sub = config_parser.add_subparsers(dest="config_command", required=True)
    validate_parser = config_sub.add_parser("validate", help="Validate configuration input")
    _add_descriptor_args(validate_parser)

    init_parser = subparsers.add_parser("init", help="Initialize runtime using a descriptor")
    _add_descriptor_args(init_parser)

    plugins_parser = subparsers.add_parser("plugins", help="Plugin utilities")
    plugins_sub = plugins_parser.add_subparsers(dest="plugins_command", required=True)
    list_parser = plugins_sub.add_parser("list", help="List available entry point plugins")
    list_parser.add_argument(
        "--group",
        choices=sorted(runtime_plugins.PLUGIN_GROUPS.keys()),
        help="Show plugins for a single group",
    )

    web_parser = subparsers.add_parser("web", help="Web server utilities")
    web_sub = web_parser.add_subparsers(dest="web_command", required=True)
    serve_parser = web_sub.add_parser("serve", help="Start the FastAPI web server")
    _add_descriptor_args(serve_parser)
    serve_parser.add_argument(
        "--host",
        default="0.0.0.0",
        help="Host interface to bind (default: 0.0.0.0)",
    )
    serve_parser.add_argument(
        "--port",
        type=int,
        default=9001,
        help="Port to bind (default: 9001)",
    )
    serve_parser.add_argument(
        "--reload",
        action="store_true",
        help="Enable uvicorn reload (development only)",
    )
    serve_parser.add_argument(
        "--app",
        default="docker.config.web:app",
        help="ASGI application path in MODULE:ATTR format (default: docker.config.web:app)",
    )

    return parser


def _add_descriptor_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "-c",
        "--config",
        help="Path to YAML/JSON descriptor file",
    )
    parser.add_argument(
        "--set",
        dest="overrides",
        metavar="KEY=VALUE",
        action="append",
        help="Override descriptor value (can be repeated)",
    )
    parser.add_argument(
        "--no-env",
        action="store_true",
        help="Ignore environment variable overrides",
    )


def _dispatch(args: argparse.Namespace) -> int:
    if args.command == "config" and args.config_command == "validate":
        return _handle_config_validate(args)
    if args.command == "init":
        return _handle_init(args)
    if args.command == "plugins" and args.plugins_command == "list":
        return _handle_plugins_list(args)
    if args.command == "web" and args.web_command == "serve":
        return _handle_web_serve(args)
    raise ValueError("Unknown command")


def _handle_config_validate(args: argparse.Namespace) -> int:
    descriptor = _build_descriptor_from_args(args)
    payload = {
        "descriptor": descriptor.to_dict(),
        "sources": {
            "config_path": args.config,
            "env_enabled": not args.no_env,
            "overrides": _get_parsed_overrides(args),
        },
    }
    _print_json(payload)
    return 0


def _handle_init(args: argparse.Namespace) -> int:
    descriptor = _build_descriptor_from_args(args)
    runtime_config = descriptor.to_runtime_config(RuntimeConfig())
    context = runtime_init(runtime_config)
    payload = {
        "runtime_config": asdict(runtime_config),
        "state": {
            "platform": context.state.platform,
            "patches_enabled": context.state.patches_enabled,
            "backends_enabled": context.state.backends_enabled,
            "plugins_loaded": context.state.plugins_loaded,
        },
        "log_messages": context.log_messages,
    }
    _print_json(payload)
    return 0


def _handle_plugins_list(args: argparse.Namespace) -> int:
    info = runtime_plugins.list_all_plugins(group=args.group)
    _print_json(info)
    return 0


def _handle_web_serve(args: argparse.Namespace) -> int:
    descriptor = _build_descriptor_from_args(args)
    runtime_config = descriptor.to_runtime_config(RuntimeConfig())
    runtime_init(runtime_config)
    app = _resolve_asgi_app(args.app)
    uvicorn.run(app, host=args.host, port=args.port, reload=args.reload)
    return 0


def _build_descriptor_from_args(args: argparse.Namespace) -> RuntimeDescriptor:
    overrides = _get_parsed_overrides(args)
    return _build_descriptor(
        config_path=args.config,
        include_env=not args.no_env,
        overrides=overrides,
    )


def _build_descriptor(
    config_path: Optional[str],
    include_env: bool,
    overrides: Dict[str, str],
) -> RuntimeDescriptor:
    descriptors = [RuntimeDescriptor()]
    if config_path:
        descriptors.append(RuntimeDescriptor.from_file(config_path))
    if include_env:
        descriptors.append(RuntimeDescriptor.from_env())
    if overrides:
        descriptors.append(RuntimeDescriptor.from_overrides(overrides))
    return RuntimeDescriptor.merge_many(descriptors)


def _parse_set_args(values: Iterable[str]) -> Dict[str, str]:
    overrides: Dict[str, str] = {}
    for entry in values:
        if "=" not in entry:
            raise ValueError(f"Invalid override '{entry}', expected KEY=VALUE")
        key, raw = entry.split("=", 1)
        key = key.strip()
        if not key:
            raise ValueError(f"Invalid override '{entry}', empty key")
        overrides[key] = raw.strip()
    return overrides


def _get_parsed_overrides(args: argparse.Namespace) -> Dict[str, str]:
    cache_key = "__parsed_overrides"
    if not hasattr(args, cache_key):
        setattr(args, cache_key, _parse_set_args(args.overrides or []))
    return getattr(args, cache_key)


def _print_json(payload) -> None:
    print(json.dumps(payload, indent=2, sort_keys=True))


def _resolve_asgi_app(path: str):
    if ":" not in path:
        raise ValueError(
            f"Invalid ASGI path '{path}', expected format 'module:attr'",
        )
    module_name, attr_name = path.split(":", 1)
    module = import_module(module_name)
    try:
        return getattr(module, attr_name)
    except AttributeError as exc:  # pragma: no cover - invalid attr
        raise ValueError(f"Module '{module_name}' has no attribute '{attr_name}'") from exc


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
