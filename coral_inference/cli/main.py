import argparse
import json
from pathlib import Path
from typing import Any, Dict

from coral_inference.runtime.validation import (
    build_runtime_binding_from_local_package,
    load_runtime_binding_from_json,
    summarize_runtime_binding_validation,
)


def _read_json_file(path: str) -> Dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="coral-inference")
    subparsers = parser.add_subparsers(dest="command", required=True)

    validate_parser = subparsers.add_parser(
        "validate-runtime-package",
        help="Validate a local package directory or runtime binding against Coral runtime capabilities",
    )
    validate_parser.add_argument("--binding-json", help="Path to a RuntimeModelBinding JSON file")
    validate_parser.add_argument("--package-dir", help="Local package directory to validate")
    validate_parser.add_argument("--loader-type", help="Loader type for local package validation")
    validate_parser.add_argument("--backend-type", help="Backend type for local package validation")
    validate_parser.add_argument("--task-type", help="Task type for local package validation")
    validate_parser.add_argument("--framework", help="Framework/model architecture for local package validation")
    validate_parser.add_argument("--model-name", default="local-package")
    validate_parser.add_argument("--model-id", default="local-package")
    validate_parser.add_argument("--package-id")
    validate_parser.add_argument("--selected-runtime")
    return parser


def _validate_runtime_package(args: argparse.Namespace) -> int:
    if args.binding_json:
        binding = load_runtime_binding_from_json(_read_json_file(args.binding_json))
    else:
        if not args.package_dir or not args.loader_type:
            raise SystemExit(
                "--package-dir and --loader-type are required when --binding-json is not provided"
            )
        binding = build_runtime_binding_from_local_package(
            package_dir=args.package_dir,
            loader_type=args.loader_type,
            backend_type=args.backend_type,
            task_type=args.task_type,
            framework=args.framework,
            model_name=args.model_name,
            model_id=args.model_id,
            package_id=args.package_id,
            selected_runtime=args.selected_runtime,
        )
    summary = summarize_runtime_binding_validation(binding)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if summary["is_supported"] else 1


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    if args.command == "validate-runtime-package":
        return _validate_runtime_package(args)
    raise SystemExit(f"Unsupported command: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())
