from collections import OrderedDict
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

from . import tomlparse
from .common import IPrecommitTomlError


@dataclass
class PreCommitCheck:
    name: Optional[str]
    cmd: List[str]
    fix_cmd: List[str]
    pass_files: bool
    filters: List[str]
    working_dir: Optional[str]


@dataclass
class PrePushCheck:
    name: Optional[str]
    cmd: List[str]


@dataclass
class CommitMsgCheck:
    name: Optional[str]
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
    fail_fast = raw_toml.pop("failfast", False)
    ensure_dict_empty(raw_toml, "The top-level table")

    if not isinstance(autofix, bool):
        raise IPrecommitTomlError("'autofix' in your TOML file should be a boolean.")

    if not isinstance(fail_fast, bool):
        raise IPrecommitTomlError("'failfast' in your TOML file should be a boolean.")

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
        name = validate_optional_string_key(pre_commit_toml, "name", table_name)
        cmd = validate_cmd_key(pre_commit_toml, table_name)
        fix_cmd = validate_cmd_key(
            pre_commit_toml, table_name, key="fix_cmd", default=[]
        )
        filters = validate_cmd_key(
            pre_commit_toml, table_name, key="filters", default=[]
        )
        working_dir = validate_optional_string_key(
            pre_commit_toml, "working_dir", table_name
        )

        pass_files = pre_commit_toml.pop("pass_files", True)
        if not isinstance(pass_files, bool):
            raise IPrecommitTomlError(
                "The 'pass_files' key of [[pre_commit]] entries in your TOML file should be a boolean."
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
            )
        )

    for commit_msg_toml in commit_msg_toml_list:
        table_name = "[[commit_msg]]"
        name = validate_optional_string_key(commit_msg_toml, "name", table_name)
        cmd = validate_cmd_key(commit_msg_toml, table_name)

        ensure_dict_empty(commit_msg_toml, "A [[commit_msg]] entry")
        config.commit_msg_checks.append(CommitMsgCheck(name=name, cmd=cmd))

    for pre_push_toml in pre_push_toml_list:
        table_name = "[[pre_push]]"
        name = validate_optional_string_key(pre_push_toml, "name", table_name)
        cmd = validate_cmd_key(pre_push_toml, table_name)

        ensure_dict_empty(pre_push_toml, f"A {table_name} entry")
        config.pre_push_checks.append(PrePushCheck(name=name, cmd=cmd))

    return config


def validate_optional_string_key(table, key, table_name):
    v = table.pop(key, None)
    if v is not None and not isinstance(v, str):
        raise IPrecommitTomlError(
            f"The '{key}' key of {table_name} entries in your TOML file should be a string."
        )

    return v


_Unset = object()


def validate_cmd_key(table, table_name, key="cmd", default=_Unset):
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


def ensure_dict_empty(d, name):
    top_level_keys = ["autofix", "failfast"]
    for key in top_level_keys:
        if key in d:
            raise IPrecommitTomlError(
                f"The '{key}' key belongs at the top level of the TOML file."
            )

    try:
        key = next(iter(d.keys()))
    except StopIteration:
        pass
    else:
        key_lower = key.lower()
        if "fail" in key_lower:
            did_you_mean = " (Did you mean 'failfast'?)"
        elif "auto" in key_lower or "fix" in key_lower:
            did_you_mean = " (Did you mean 'autofix'?)"
        else:
            did_you_mean = ""

        raise IPrecommitTomlError(
            f"{name} in your TOML file has a key that iprecommit does not recognize: {key}{did_you_mean}"
        )
