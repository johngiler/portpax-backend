def normalize_position_short_code(value: str) -> str:
    return value.strip().upper().replace(" ", "")


def position_code_prefix(port_code: str) -> str:
    return f"{port_code.strip().lower()}-"


def position_short_code(port_code: str, full_code: str) -> str:
    prefix = position_code_prefix(port_code)
    if full_code.lower().startswith(prefix):
        return full_code[len(prefix) :]
    return full_code


def build_position_code(port_code: str, user_code: str) -> str:
    short = normalize_position_short_code(user_code)
    prefix = position_code_prefix(port_code)
    if short.lower().startswith(prefix):
        short = short[len(prefix) :]
    return f"{port_code.strip().lower()}-{short}"


def build_combined_position_code(port_code: str, first_short: str, second_short: str) -> str:
    combined_short = (
        f"{normalize_position_short_code(first_short)}+{normalize_position_short_code(second_short)}"
    )
    return build_position_code(port_code, combined_short)
