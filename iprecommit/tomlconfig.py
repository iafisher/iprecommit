import shlex
from collections import OrderedDict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from . import tomlparse
from .common import IPrecommitTomlError


@dataclass
class PreCommitCheck:
    name: str
    cmd: List[str]
    fix_cmd: List[str]
    pass_files: bool
    filters: List[str]
    working_dir: Optional[str]
    fail_fast: bool
    autofix: bool
    skip: bool


@dataclass
class PrePushCheck:
    name: str
    cmd: List[str]


@dataclass
class CommitMsgCheck:
    name: str
    cmd: List[str]


@dataclass
class Config:
    autofix: bool
    fail_fast: bool
    pre_commit_checks: List[PreCommitCheck]
    pre_push_checks: List[PrePushCheck]
    commit_msg_checks: List[CommitMsgCheck]


def parse(path: Path) -> Config:
    raw_toml = tomlparse.load(path, OrderedDict)

    # TODO: tests for TOML parsing and error messages
    pre_commit_toml_list = raw_toml.pop("pre_commit", [])
    commit_msg_toml_list = raw_toml.pop("commit_msg", [])
    pre_push_toml_list = raw_toml.pop("pre_push", [])
    autofix = raw_toml.pop("autofix", False)
    fail_fast = raw_toml.pop("fail_fast", False)
    ensure_dict_empty(raw_toml, "The top-level table")

    if not isinstance(autofix, bool):
        raise IPrecommitTomlError("'autofix' in your TOML file should be a boolean.")

    if not isinstance(fail_fast, bool):
        raise IPrecommitTomlError("'fail_fast' in your TOML file should be a boolean.")

    if not isinstance(pre_commit_toml_list, list) or any(
        not isinstance(d, dict) for d in pre_commit_toml_list
    ):
        raise IPrecommitTomlError(
            "'pre_commit' in your TOML file should be an array of tables (e.g., [[pre_commit]])."
        )

    if not isinstance(commit_msg_toml_list, list) or any(
        not isinstance(d, dict) for d in commit_msg_toml_list
    ):
        raise IPrecommitTomlError(
            "'commit_msg' in your TOML file should be an array of tables (e.g., [[commit_msg]])."
        )

    if not isinstance(pre_push_toml_list, list) or any(
        not isinstance(d, dict) for d in pre_push_toml_list
    ):
        raise IPrecommitTomlError(
            "'pre_push' in your TOML file should be an array of tables (e.g., [[pre_push]])."
        )

    config = Config(
        autofix=autofix,
        fail_fast=fail_fast,
        pre_commit_checks=[],
        pre_push_checks=[],
        commit_msg_checks=[],
    )

    for pre_commit_toml in pre_commit_toml_list:
        table_name = "[[pre_commit]]"
        cmd = validate_cmd_key(pre_commit_toml, table_name)
        name = validate_optional_string_key(pre_commit_toml, "name", table_name)
        if name is None:
            name = name_from_cmd(cmd)

        fix_cmd = validate_cmd_key(
            pre_commit_toml, table_name, key="fix_cmd", default=[]
        )
        filters = validate_cmd_key(
            pre_commit_toml, table_name, key="filters", default=[]
        )
        working_dir = validate_optional_string_key(
            pre_commit_toml, "working_dir", table_name
        )
        fail_fast = validate_bool_key(
            pre_commit_toml, "fail_fast", value_if_unset=False, table_name="pre_commit"
        )
        pass_files = validate_bool_key(
            pre_commit_toml, "pass_files", value_if_unset=True, table_name="pre_commit"
        )
        autofix = validate_bool_key(
            pre_commit_toml, "autofix", value_if_unset=False, table_name="pre_commit"
        )
        skip = validate_bool_key(
            pre_commit_toml, "skip", value_if_unset=False, table_name="pre_commit"
        )

        ensure_dict_empty(pre_commit_toml, "A [[pre_commit]] entry")
        config.pre_commit_checks.append(
            PreCommitCheck(
                name=name,
                cmd=cmd,
                fix_cmd=fix_cmd,
                pass_files=pass_files,
                filters=filters,
                working_dir=working_dir,
                fail_fast=fail_fast,
                autofix=autofix,
                skip=skip,
            )
        )

    for commit_msg_toml in commit_msg_toml_list:
        table_name = "[[commit_msg]]"
        cmd = validate_cmd_key(commit_msg_toml, table_name)
        name = validate_optional_string_key(commit_msg_toml, "name", table_name)
        if name is None:
            name = name_from_cmd(cmd)

        ensure_dict_empty(commit_msg_toml, "A [[commit_msg]] entry")
        config.commit_msg_checks.append(CommitMsgCheck(name=name, cmd=cmd))

    for pre_push_toml in pre_push_toml_list:
        table_name = "[[pre_push]]"
        cmd = validate_cmd_key(pre_push_toml, table_name)
        name = validate_optional_string_key(pre_push_toml, "name", table_name)
        if name is None:
            name = name_from_cmd(cmd)

        ensure_dict_empty(pre_push_toml, f"A {table_name} entry")
        config.pre_push_checks.append(PrePushCheck(name=name, cmd=cmd))

    return config


def name_from_cmd(cmd: List[str]) -> str:
    return " ".join(map(shlex.quote, cmd))


def validate_optional_string_key(
    table: Dict[str, Any], key: str, table_name: str
) -> Any:
    v = table.pop(key, None)
    if v is not None and not isinstance(v, str):
        raise IPrecommitTomlError(
            f"The '{key}' key of {table_name} entries in your TOML file should be a string."
        )

    return v


_Unset = object()


def validate_cmd_key(
    table: Dict[str, Any], table_name: str, key: str = "cmd", default: Any = _Unset
) -> Any:
    if default is not _Unset:
        v = table.pop(key, default)
    else:
        try:
            v = table.pop(key)
        except KeyError:
            raise IPrecommitTomlError(
                f"A {table_name} table in your TOML file is missing a '{key}' key."
            )

    if not isinstance(v, list) or any(not isinstance(a, str) for a in v):
        raise IPrecommitTomlError(
            "The '{key}' key of {table_name} entries in your TOML file should be a list of strings."
        )

    return v


def validate_bool_key(
    table: Dict[str, Any], key: str, *, value_if_unset: bool, table_name: str
) -> bool:
    value = table.pop(key, value_if_unset)
    if not isinstance(value, bool):
        raise IPrecommitTomlError(
            f"The '{key}' key of [[{table_name}]] entries in your TOML file should be a boolean."
        )

    return value


def ensure_dict_empty(d: dict, name: str) -> None:
    try:
        key = next(iter(d.keys()))
    except StopIteration:
        pass
    else:
        key_lower = key.lower()
        if "fail" in key_lower:
            did_you_mean = " (Did you mean 'fail_fast'?)"
        elif "auto" in key_lower or "fix" in key_lower:
            did_you_mean = " (Did you mean 'autofix'?)"
        else:
            did_you_mean = ""

        raise IPrecommitTomlError(
            f"{name} in your TOML file has a key that iprecommit does not recognize: {key}{did_you_mean}"
        )
