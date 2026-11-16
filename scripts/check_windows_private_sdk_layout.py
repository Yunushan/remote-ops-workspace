"""Compare native storage ctypes structure layouts with compiled Windows SDK headers."""

from __future__ import annotations

import argparse
import ast
import ctypes
import json
from ctypes import wintypes
from pathlib import Path

SOURCE = Path(__file__).resolve().parents[1] / "src/remote_ops_workspace/windows_private_storage.py"
LAYOUTS = {
    "Descriptor": (
        "SECURITY_DESCRIPTOR",
        {"revision": "Revision", "reserved": "Sbz1", "control": "Control",
         "owner": "Owner", "group": "Group", "sacl": "Sacl", "dacl": "Dacl"},
    ),
    "Attributes": (
        "SECURITY_ATTRIBUTES",
        {"length": "nLength", "descriptor": "lpSecurityDescriptor", "inherit_handle": "bInheritHandle"},
    ),
    "FileInfo": (
        "BY_HANDLE_FILE_INFORMATION",
        {"attributes": "dwFileAttributes", "creation": "ftCreationTime", "access": "ftLastAccessTime",
         "write": "ftLastWriteTime", "volume": "dwVolumeSerialNumber", "size_high": "nFileSizeHigh",
         "size_low": "nFileSizeLow", "links": "nNumberOfLinks", "index_high": "nFileIndexHigh",
         "index_low": "nFileIndexLow"},
    ),
}
CTYPES_NAMES = {"c": ctypes, "w": wintypes}


def python_layouts() -> dict[str, list[int]]:
    source = ast.parse(SOURCE.read_text(encoding="utf-8"))
    classes = {
        name: [node for node in ast.walk(source) if isinstance(node, ast.ClassDef) and node.name == name]
        for name in LAYOUTS
    }
    result = {}
    for name, (_, members) in LAYOUTS.items():
        [declaration] = classes[name]
        [base] = declaration.bases
        if ast.unparse(base) != "c.Structure" or declaration.keywords or declaration.decorator_list:
            raise ValueError(f"unexpected ctypes base for {name}")
        [assignment] = declaration.body
        if not isinstance(assignment, ast.Assign) or not isinstance(assignment.value, ast.List):
            raise ValueError(f"missing ctypes fields for {name}")
        [target] = assignment.targets
        if not isinstance(target, ast.Name) or target.id != "_fields_":
            raise ValueError(f"missing ctypes fields for {name}")
        fields = []
        for row in assignment.value.elts:
            if not isinstance(row, ast.Tuple):
                raise ValueError(f"unexpected ctypes field for {name}")
            field_name, field_type = row.elts
            if not isinstance(field_type, ast.Attribute) or not isinstance(field_type.value, ast.Name):
                raise ValueError(f"unexpected ctypes type for {name}")
            fields.append((ast.literal_eval(field_name), getattr(CTYPES_NAMES[field_type.value.id], field_type.attr)))
        if [field for field, _ in fields] != list(members):
            raise ValueError(f"unexpected ctypes field names or order for {name}")
        structure = type(name, (ctypes.Structure,), {"_fields_": fields})
        result[name] = [
            ctypes.sizeof(structure),
            ctypes.alignment(structure),
            *(getattr(structure, field).offset for field in members),
        ]
    return result


def write_probe(path: Path) -> None:
    lines = [
        "#include <windows.h>",
        "#include <stddef.h>",
        "#include <stdio.h>",
        "int main(void) {",
        '    puts("{");',
    ]
    for index, (name, (sdk_type, members)) in enumerate(LAYOUTS.items()):
        expressions = [
            f"sizeof({sdk_type})",
            f"__alignof({sdk_type})",
            *(f"offsetof({sdk_type}, {member})" for member in members.values()),
        ]
        values = ", ".join("%zu" for _ in expressions)
        suffix = "" if index == len(LAYOUTS) - 1 else ","
        lines.append(f'    printf("  \\"{name}\\": [{values}]{suffix}\\n", {", ".join(expressions)});')
    lines.extend(['    puts("}");', "    return 0;", "}"])
    with path.open("x", encoding="ascii", newline="\n") as handle:
        handle.write("\n".join(lines) + "\n")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_mutually_exclusive_group(required=True)
    commands.add_argument("--write-probe", type=Path)
    commands.add_argument("--compare", type=Path)
    parser.add_argument("--pointer-bits", type=int, choices=(32, 64))
    args = parser.parse_args()
    if args.write_probe is not None:
        write_probe(args.write_probe)
        return 0
    if args.pointer_bits != ctypes.sizeof(ctypes.c_void_p) * 8:
        parser.error("--compare requires --pointer-bits matching the current interpreter")
    observed = json.loads(args.compare.read_text(encoding="ascii"))
    expected = python_layouts()
    if observed != expected:
        print("Compiled SDK layouts differ from native storage ctypes declarations.")
        print(json.dumps({"sdk": observed, "ctypes": expected}, sort_keys=True))
        return 1
    print(json.dumps({"status": "passed", "layouts": expected}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
