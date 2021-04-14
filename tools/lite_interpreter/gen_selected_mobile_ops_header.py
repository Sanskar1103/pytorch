#!/usr/bin/env python3
import argparse
import os
from typing import Set
from tools.codegen.selective_build.selector import SelectiveBuilder
from tools.codegen.code_template import CodeTemplate

import yaml

if_condition_template_str = """if (kernel_tag_sv.compare("$kernel_tag_name") == 0) {
  return $dtype_checks;
}"""
if_condition_template = CodeTemplate(if_condition_template_str)

selected_kernel_dtypes_h_template_str = """#pragma once
#include <c10/core/ScalarType.h>
#include <c10/util/string_view.h>
#include <c10/macros/Macros.h>

namespace at {
inline constexpr bool should_include_kernel_dtype(
  const char *kernel_tag_str,
  at::ScalarType scalar_type
) {
  c10::string_view kernel_tag_sv C10_UNUSED = c10::string_view(kernel_tag_str);
  $body
  return false;
}
}
"""
selected_kernel_dtypes_h_template = CodeTemplate(selected_kernel_dtypes_h_template_str)

selected_mobile_ops_preamble = """#pragma once
/**
 * Generated by gen_selected_mobile_ops_header.py
 */

"""

def extract_root_operators(selective_builder: SelectiveBuilder) -> Set[str]:
    ops = []
    for (op_name, op) in selective_builder.operators.items():
        if op.is_root_operator:
            ops.append(op_name)
    return set(ops)

def get_selected_kernel_dtypes_code(
        selective_builder: SelectiveBuilder,
) -> str:
    # See https://www.internalfb.com/intern/paste/P153411698/ for an example of the
    # generated code in case all kernel dtypes are selected and in case some kernel
    # dtypes are selected (i.e. both cases).
    #
    body = "return true;"
    if selective_builder.include_all_operators is False and selective_builder.include_all_kernel_dtypes is False:
        body_parts = []
        for kernel_tag, dtypes in selective_builder.kernel_metadata.items():
            conditions = list(map(lambda x: 'scalar_type == at::ScalarType::' + x, dtypes))
            body_parts.append(
                if_condition_template.substitute(
                    kernel_tag_name=kernel_tag,
                    dtype_checks=" || ".join(conditions),
                ),
            )
        body = " else ".join(body_parts)

    header_contents = selected_kernel_dtypes_h_template.substitute(body=body)
    return header_contents


# Write the file selected_mobile_ops.h with optionally:
# 1. The selected root operators
# 2. The selected kernel dtypes
def write_selected_mobile_ops(
        output_file_path: str,
        selective_builder: SelectiveBuilder,
) -> None:
    root_ops = extract_root_operators(selective_builder)
    with open(output_file_path, "wb") as out_file:
        body_parts = [selected_mobile_ops_preamble]
        if not selective_builder.include_all_operators:
            body_parts.append("#define TORCH_OPERATOR_WHITELIST " + (";".join(sorted(root_ops))) + ";\n\n")

        body_parts.append(get_selected_kernel_dtypes_code(selective_builder))
        header_contents = "".join(body_parts)
        out_file.write(header_contents.encode("utf-8"))

# root_ops: a set of selected root operators for selective build
# Write the file selected_mobile_ops.h with optionally:
# 1. The selected root operators from root_ops
# 2. All kernel dtypes
def write_selected_mobile_ops_with_all_dtypes(
    output_file_path: str,
    root_ops: Set[str],
) -> None:
    with open(output_file_path, "wb") as out_file:
        body_parts = [selected_mobile_ops_preamble]
        body_parts.append("#define TORCH_OPERATOR_WHITELIST " + (";".join(sorted(root_ops))) + ";\n\n")

        selective_builder = SelectiveBuilder.get_nop_selector()
        body_parts.append(get_selected_kernel_dtypes_code(selective_builder))

        header_contents = "".join(body_parts)
        out_file.write(header_contents.encode("utf-8"))

def main():
    parser = argparse.ArgumentParser(
        description="Generate selected_mobile_ops.h for selective build."
    )
    parser.add_argument(
        "-p", "--yaml_file_path", type=str, required=True, help="Path to the yaml"
        " file with a list of operators used by the model."
    )
    parser.add_argument(
        "-o", "--output_file_path", type=str, required=True, help="Path to destination"
        "folder where selected_mobile_ops.h will be written."
    )
    parsed_args = parser.parse_args()
    model_file_name = parsed_args.yaml_file_path

    print("Loading yaml file: ", model_file_name)
    loaded_model = {}
    with open(model_file_name, "rb") as model_file:
        loaded_model = yaml.load(model_file)


    root_operators_set = set(loaded_model)
    print("Writing header file selected_mobile_ops.h: ", parsed_args.output_file_path)
    write_selected_mobile_ops_with_all_dtypes(
        os.path.join(parsed_args.output_file_path, "selected_mobile_ops.h"),
        root_operators_set)

if __name__ == "__main__":
    main()
